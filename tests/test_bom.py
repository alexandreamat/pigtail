"""Length + the bill of materials."""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import get_args

import pytest
import yaml
from pydantic import ValidationError

from pigtail.fill import required_cu_in
from pigtail.models.box import Box
from pigtail.models.house import House
from pigtail.models.types import BoxShape
from pigtail.nec_tables import TABLE_314_16_A

EXAMPLES = Path(__file__).parent.parent / "examples"


def test_bom_length_adds_makeup() -> None:
    c = House.from_yaml(EXAMPLES / "switch_loop.yaml").cable("C1")
    assert c.length_ft == 24
    assert c.bom_length_ft == 25  # +6 in. at each end (NEC 300.14)


def test_unmeasured_run_has_no_bom_length() -> None:
    assert House.from_yaml(EXAMPLES / "knob_and_tube.yaml").cable("K1").bom_length_ft is None


def test_bom_splits_cable_from_conduit() -> None:
    bom = House.from_yaml(EXAMPLES / "emt_conduit.yaml").bom()
    assert 'EMT 1/2"' in bom  # tubing line
    assert "12 AWG THHN" in bom  # conductor pulled through it, separately
    assert "conduit (buy tubing + conductor separately)" in bom
    # 22 + 14 ft of tubing, no makeup
    assert "~    36 ft" in bom


def test_box_fill_counts_insulated_conductors_not_the_raceway() -> None:
    house = House.from_yaml(EXAMPLES / "emt_conduit.yaml")
    # EMB1: 4 insulated 12 AWG (E1 in, E2 out) x 2.25 + one yoke 2 x 2.25; the
    # tubing is the EGC -- no wire EGC enters, so no 314.16(B)(5) allowance
    assert required_cu_in(house, "EMB1") == 13.5


def test_box_fill_counts_all_wire_egcs_once() -> None:
    house = House.from_yaml(EXAMPLES / "switch_loop.yaml")
    # SB1: C1 lands (2 insulated), C2 leaves (2 insulated) = 4 x 2.0, one
    # switch yoke 2 x 2.0, and both bare EGCs together one 2.0 allowance
    assert required_cu_in(house, "SB1") == 14.0


def test_a_luminaire_is_not_a_yoke() -> None:
    house = House.from_yaml(EXAMPLES / "switch_loop.yaml")
    # FB1: C2 lands (2 insulated 14 AWG) = 2 x 2.0, its bare EGC one 2.0; the
    # luminaire on the box is on no yoke -- no 314.16(B)(4) allowance
    assert required_cu_in(house, "FB1") == 6.0


def test_bom_box_fill_flags_short_boxes_with_a_suggestion() -> None:
    data = yaml.safe_load((EXAMPLES / "emt_conduit.yaml").read_text())
    data["boxes"][0]["volume_cu_in"] = 12.0  # EMB1 needs 13.5
    bom = House.from_dict(data).bom()
    assert "box volume vs box fill (314.16) -- 1 short" in bom
    assert "EMB1" in bom and "13.50" in bom
    assert "18 in.³" in bom  # the smallest standard box that fits


def test_switch_loop_bom_counts() -> None:
    bom = House.from_yaml(EXAMPLES / "switch_loop.yaml").bom()
    assert "NM-B 14/2          2 run(s)" in bom
    assert "1-pole 15 A AFCI" in bom
    assert "luminaire" in bom


def test_emt_requires_trade_size_and_nm_forbids_it() -> None:
    ok = {
        "meta": {"project": "x"},
        "boxes": [
            {
                "id": "B",
                "type": "device",
                "material": "metal",
                "volume_cu_in": 30.0,
                "depth_in": 2.125,
            }
        ],
        "panelboards": [
            {
                "id": "MP",
                "branch_circuits": [
                    {"id": "C", "circuit_breaker": {"line": "L1", "poles": 1, "ampere_rating": 20}}
                ],
                "cables": [
                    {
                        "id": "W",
                        "type": "EMT",
                        "trade_size": "1/2",
                        "size_awg": 12,
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
    House.from_dict(ok)

    no_size = ok["panelboards"][0]["cables"][0].copy()  # type: ignore[index]
    del no_size["trade_size"]
    bad = {**ok}
    bad["panelboards"][0]["cables"] = [no_size]  # type: ignore[index]
    with pytest.raises(Exception, match="trade_size"):
        House.from_dict(bad)


def _box(**volume: object) -> dict[str, object]:
    return {"id": "B", "type": "junction", "material": "metal", **volume}


def test_box_volume_from_its_trade_size_or_its_marking() -> None:
    by_size = Box.model_validate(_box(shape="square", trade_size="4 x 2-1/8"))
    assert by_size.box_volume_cu_in == 30.3  # Table 314.16(A)
    assert by_size.volume_basis == "Table 314.16(A), 4 x 2-1/8 square"
    marked = Box.model_validate(_box(volume_cu_in=11.9))
    assert marked.box_volume_cu_in == 11.9 and marked.volume_basis == "marked"
    unknown = Box.model_validate(_box())
    assert unknown.box_volume_cu_in is None and unknown.volume_basis == "not recorded"


@pytest.mark.parametrize(
    ("volume", "match"),
    [
        ({"shape": "square", "trade_size": "4 x 2-1/8", "volume_cu_in": 30.3}, "not both"),
        ({"shape": "square"}, "together"),
        ({"shape": "round/octagonal", "trade_size": "3-1/2 x 1-1/2"}, "not in Table 314.16"),
    ],
)
def test_box_volume_is_given_one_way(volume: dict[str, object], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        Box.model_validate(_box(**volume))


def test_box_shapes_are_the_tables() -> None:
    assert set(get_args(BoxShape.__value__)) == set(TABLE_314_16_A)


def test_a_short_box_names_where_its_volume_comes_from() -> None:
    data = yaml.safe_load((EXAMPLES / "emt_conduit.yaml").read_text())
    del data["boxes"][0]["volume_cu_in"], data["boxes"][0]["depth_in"]
    data["boxes"][0] |= {"shape": "device", "trade_size": "3 x 2 x 2"}  # 10.0 in.3; EMB1 needs 13.5
    found = [
        str(w.message)
        for w in _checked(House.from_dict(data))
        if str(w.message).startswith("314.16")
    ]
    assert found == [
        "314.16: box EMB1 -- box volume 10 in.³ (Table 314.16(A), 3 x 2 x 2 device), "
        "less than box fill 13.50 in.³"
    ]


def _checked(house: House) -> list[warnings.WarningMessage]:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        house.check()
    return caught


def test_rings_and_covers_add_the_space_that_counts() -> None:
    box = Box.model_validate(
        _box(
            shape="square",
            trade_size="4 x 2-1/8",
            additions=[
                {"kind": "extension ring", "shape": "square", "trade_size": "4 x 1-1/2"},
                {"kind": "raised cover", "volume_cu_in": 4.5},
                {"kind": "domed cover"},  # not marked: 314.16(A) gives it no space
            ],
        )
    )
    assert box.box_volume_cu_in == pytest.approx(30.3 + 21.0 + 4.5)
    assert box.volume_basis == (
        "Table 314.16(A), 4 x 2-1/8 square; "
        "+ extension ring 21 in.³ (Table 314.16(A), 4 x 1-1/2 square); "
        "+ raised cover 4.5 in.³ (marked); domed cover not marked, not counted"
    )


def test_a_ring_on_a_box_of_unrecorded_volume_leaves_it_unrecorded() -> None:
    box = Box.model_validate(_box(additions=[{"kind": "extension ring", "volume_cu_in": 21.0}]))
    assert box.box_volume_cu_in is None


def test_an_addition_volume_is_given_one_way() -> None:
    ring = {"kind": "extension ring", "shape": "square", "trade_size": "4 x 1-1/2"}
    with pytest.raises(ValidationError, match="extension ring: give its trade size"):
        Box.model_validate(_box(additions=[{**ring, "volume_cu_in": 21.0}]))
