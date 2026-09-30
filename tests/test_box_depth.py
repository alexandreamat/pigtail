"""314.24(B): a box's depth against the conductors supplying the device in it."""

from __future__ import annotations

import warnings
from typing import Any

import pytest
from pydantic import ValidationError

from pigtail.models.box import Box
from pigtail.models.house import House
from pigtail.nec import NECUnchecked, NECViolation


def _receptacle_on_8_awg(**box: Any) -> House:
    """A 14-50R in box B on three 8 AWG in EMT."""
    run = {
        "id": "E1",
        "type": "EMT",
        "trade_size": "3/4",
        "size_awg": 8,
        "to": "B",
        "pulled": [
            {"name": "l1", "role": "ungrounded", "color": "black"},
            {"name": "l2", "role": "ungrounded", "color": "red"},
            {"name": "n", "role": "neutral", "color": "white"},
        ],
        "devices": [{"id": "R", "type": "receptacle", "poles": 2, "nema": "14-50R"}],
        "splices": [
            {"join": ["E1.l1", "R.LINE1"]},
            {"join": ["E1.l2", "R.LINE2"]},
            {"join": ["E1.n", "R.NEUTRAL"]},
            {"join": ["E1.egc", "R.EGC"]},
        ],
    }
    return House.from_dict(
        {
            "meta": {"project": "x"},
            "boxes": [{"id": "B", "type": "device", "material": "metal", **box}],
            "panelboards": [
                {
                    "id": "MP",
                    "branch_circuits": [
                        {"id": "C", "circuit_breaker": {"poles": 2, "ampere_rating": 40}}
                    ],
                    "cables": [run],
                    "splices": [
                        {"join": ["E1.l1", "C.LOAD1"]},
                        {"join": ["E1.l2", "C.LOAD2"]},
                        {"join": ["E1.n", "MP.NEUTRAL"]},
                        {"join": ["E1.egc", "MP.EGC"]},
                    ],
                }
            ],
        }
    )


def _depth_findings(house: House) -> tuple[list[str], list[str]]:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        house.check()
    pick = [w for w in caught if str(w.message).startswith("314.24")]
    return (
        [str(w.message) for w in pick if issubclass(w.category, NECViolation)],
        [str(w.message) for w in pick if issubclass(w.category, NECUnchecked)],
    )


SQUARE_1_1_2 = {"shape": "square", "trade_size": "4 x 1-1/2"}


def test_8_awg_needs_2_1_16_in() -> None:
    assert _depth_findings(_receptacle_on_8_awg(shape="square", trade_size="4 x 2-1/8")) == ([], [])
    found, _ = _depth_findings(_receptacle_on_8_awg(**SQUARE_1_1_2))
    assert found == [
        "314.24(B)(3): box B -- internal depth 1-1/2 in., less than the 2-1/16 in. a device "
        "supplied by 8 AWG needs"
    ]


def test_a_raised_cover_adds_its_depth() -> None:
    def with_cover(cover: dict[str, Any]) -> tuple[list[str], list[str]]:
        return _depth_findings(_receptacle_on_8_awg(**SQUARE_1_1_2, additions=[cover]))

    assert with_cover({"kind": "raised cover", "depth_in": 0.625}) == ([], [])  # 2-1/8 in.
    found, _ = with_cover({"kind": "raised cover", "depth_in": 0.5})
    assert found and found[0].startswith("314.24(B)(3): box B -- internal depth 2 in., less than")
    _, unchecked = with_cover({"kind": "raised cover"})
    assert unchecked == [
        "314.24(B)(3): box B -- depth of its raised cover not recorded; a device supplied by "
        "8 AWG needs 2-1/16 in."
    ]


def test_a_box_given_by_marked_volume_needs_its_depth() -> None:
    _, unchecked = _depth_findings(_receptacle_on_8_awg(volume_cu_in=30.0))
    assert unchecked[0].startswith("314.24(B)(3): box B -- depth of its box not recorded")
    assert _depth_findings(_receptacle_on_8_awg(volume_cu_in=30.0, depth_in=2.25)) == ([], [])


def test_a_trade_size_gives_the_depth() -> None:
    with pytest.raises(ValidationError, match="gives its depth"):
        Box.model_validate(
            {"id": "B", "type": "device", "material": "metal", **SQUARE_1_1_2, "depth_in": 1.5}
        )
