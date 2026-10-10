"""A run whose conductor size is not recorded: every rule that needs it is
reported as not checked, nothing is guessed, and the outputs still render."""

from __future__ import annotations

import warnings
from typing import Any

from pigtail.models.house import House
from pigtail.nec import NECUnchecked, NECViolation
from pigtail.outputs.diagram import circuit_diagram


def _receptacle(**run: Any) -> House:
    """A 20 A circuit over EMT to a receptacle in box B (4 x 1-1/2 square)."""
    e1 = {
        "id": "E1",
        "type": "EMT",
        "trade_size": "1/2",
        "to": "B",
        "pulled": [
            {"name": "hot", "role": "ungrounded", "color": "black"},
            {"name": "n", "role": "neutral", "color": "white"},
        ],
        "devices": [{"id": "R", "type": "receptacle", "nema": "5-20R"}],
        "splices": [
            {"join": ["E1.hot", "R.LINE"]},
            {"join": ["E1.n", "R.NEUTRAL"]},
            {"join": ["E1.egc", "R.EGC"]},
        ],
        **run,
    }
    return House.from_dict(
        {
            "meta": {"project": "x"},
            "boxes": [
                {
                    "id": "B",
                    "type": "device",
                    "material": "metal",
                    "shape": "square",
                    "trade_size": "4 x 1-1/2",
                }
            ],
            "panelboards": [
                {
                    "id": "MP",
                    "branch_circuits": [
                        {"id": "C", "circuit_breaker": {"line": "L1", "ampere_rating": 20}}
                    ],
                    "cables": [e1],
                    "splices": [
                        {"join": ["E1.hot", "C.LOAD"]},
                        {"join": ["E1.n", "MP.NEUTRAL"]},
                        {"join": ["E1.egc", "MP.EGC"]},
                    ],
                }
            ],
        }
    )


def _findings(house: House) -> tuple[list[str], list[str]]:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        house.check()
    return (
        [str(w.message) for w in caught if issubclass(w.category, NECViolation)],
        [str(w.message) for w in caught if issubclass(w.category, NECUnchecked)],
    )


def test_size_not_recorded_is_not_checked() -> None:
    found, unchecked = _findings(_receptacle())
    assert not [m for m in found if m.startswith(("240.4", "310.16", "358.22", "314."))]
    assert (
        "240.4(D): cable E1 -- E1.hot size not recorded; its rating against circuit C's 20 A "
        "breaker is not checked"
    ) in unchecked
    assert "358.22: tube E1 -- size not recorded for E1.hot, E1.n; fill not calculated" in unchecked
    assert (
        "314.16: box B -- conductor size not recorded in E1; box fill not calculated" in unchecked
    )
    assert any(m.startswith("314.24(B): box B -- size of the conductors") for m in unchecked)


def test_recorded_size_is_checked() -> None:
    found, unchecked = _findings(_receptacle(size_awg=14))
    assert any(m.startswith("240.4(D): cable E1 -- E1.hot (14 AWG") for m in found)
    assert not [m for m in unchecked if "size not recorded" in m]


def test_a_wire_sized_on_its_own() -> None:
    """Sizes given wire by wire leave nothing unknown in a run without one."""
    house = _receptacle(
        pulled=[
            {"name": "hot", "role": "ungrounded", "color": "black", "size_awg": 12},
            {"name": "n", "role": "neutral", "color": "white", "size_awg": 12},
        ]
    )
    _, unchecked = _findings(house)
    assert not [m for m in unchecked if "size not recorded" in m]


def test_outputs_render() -> None:
    house = _receptacle()
    assert "? AWG" in circuit_diagram(house)
    assert "box fill not calculated" in circuit_diagram(house)
    assert "E1.hot" in house.conductor_schedule()
    assert "E1" in house.raceway_schedule()
    assert "size ? THHN" in house.bom()
