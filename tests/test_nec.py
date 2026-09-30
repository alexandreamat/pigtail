"""The NEC checks -- a warn-only pass over an assembled house."""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

import pytest
import yaml

from pigtail.models.house import House
from pigtail.nec import NECUnchecked, NECViolation, check

EXAMPLES = Path(__file__).parent.parent / "examples"


def _violations(house: House) -> list[str]:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", NECViolation)
        check(house)
    return [str(w.message) for w in caught if issubclass(w.category, NECViolation)]


def _articles(house: House) -> set[str]:
    return {v.split(":", 1)[0] for v in _violations(house)}


def _one_circuit(
    *, ampere_rating: int = 15, afci: bool = False, size_awg: int = 14
) -> dict[str, Any]:
    return {
        "meta": {"project": "x"},
        "boxes": [
            {
                "id": "B",
                "type": "device",
                "material": "nonmetallic",
                "volume_cu_in": 30.0,
                "depth_in": 2.5,
            }
        ],
        "panelboards": [
            {
                "id": "MP",
                "branch_circuits": [
                    {
                        "id": "C",
                        "circuit_breaker": {
                            "line": "L1",
                            "poles": 1,
                            "ampere_rating": ampere_rating,
                            "afci": afci,
                        },
                    }
                ],
                "cables": [
                    {
                        "id": "W",
                        "type": "NM-B",
                        "size_awg": size_awg,
                        "conductors": 2,
                        "to": "B",
                        "devices": [{"id": "R", "type": "receptacle"}],
                        "splices": [
                            {"join": ["W.ungrounded", "R.LINE"]},
                            {"join": ["W.neutral", "R.NEUTRAL"]},
                            {"join": ["W.egc", "R.EGC"]},
                        ],
                    }
                ],
                "splices": [
                    {"join": ["W.ungrounded", "C.LOAD"]},
                    {"join": ["W.neutral", "MP.NEUTRAL"]},
                    {"join": ["W.egc", "MP.EGC"]},
                ],
            }
        ],
    }


def test_switch_loop_is_clean(house: House) -> None:
    # 15 A on 14 AWG, AFCI breaker, no receptacles -- nothing to flag
    assert _violations(house) == []


def test_afci_missing_is_a_violation() -> None:
    assert "210.12(A)" in _articles(House.from_dict(_one_circuit()))
    assert "210.12(A)" not in _articles(House.from_dict(_one_circuit(afci=True)))


def test_240_4d_breaker_larger_than_conductor() -> None:
    # 14 AWG maxes at 15 A; a 30 A breaker is a 240.4(D) violation
    house = House.from_dict(_one_circuit(ampere_rating=30, afci=True, size_awg=14))
    assert "240.4(D)" in _articles(house)


def test_knob_and_tube_flags_ungrounded_receptacles_and_394() -> None:
    articles = _articles(House.from_yaml(EXAMPLES / "knob_and_tube.yaml"))
    assert "406.4(D)(2)" in articles  # BR1-R1 is ungrounded, not GFCI
    assert "394.12" in articles


def test_house_check_raises_nec_warnings() -> None:
    house = House.from_yaml(EXAMPLES / "knob_and_tube.yaml")
    with pytest.warns(NECViolation), pytest.warns(NECUnchecked):
        house.check()


def _unchecked(house: House) -> list[str]:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        check(house)
    return [str(w.message) for w in caught if issubclass(w.category, NECUnchecked)]


def test_a_rule_missing_a_value_is_reported_not_checked() -> None:
    house = House.from_yaml(EXAMPLES / "knob_and_tube.yaml")  # runs without lengths
    assert _unchecked(house) == [
        "210.19(A) IN No. 4: circuit BR-6 -- voltage drop not checked; no length recorded for K1, K2"
    ]
    assert _unchecked(House.from_yaml(EXAMPLES / "switch_loop.yaml")) == []  # all recorded


def test_a_box_without_a_volume_is_not_checked() -> None:
    data = yaml.safe_load((EXAMPLES / "emt_conduit.yaml").read_text())
    del data["boxes"][0]["volume_cu_in"]
    house = House.from_dict(data)
    assert _unchecked(house) == ["314.16: box EMB1 -- box volume not recorded; box fill 13.50 in.³"]
    assert not any(v.startswith("314.16") for v in _violations(house))
    assert "box volume vs box fill (314.16) -- 1 adequate, 1 box volume not recorded" in house.bom()
