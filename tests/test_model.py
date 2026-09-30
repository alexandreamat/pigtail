from __future__ import annotations

from collections.abc import Iterator

import pytest
from pydantic import ValidationError

from pigtail.models.cable import Cable
from pigtail.models.circuit import CircuitBreaker
from pigtail.models.house import House


def _all_cables(cables: list[Cable]) -> Iterator[Cable]:
    for cable in cables:
        yield cable
        yield from _all_cables(cable.cables)


def test_example_parses(house: House) -> None:
    assert house.meta.project == "Switch loop"
    assert len(house.boxes) == 2
    assert len(house.panelboards) == 1
    circuits = house.panelboards[0].branch_circuits
    assert len(circuits) == 1
    assert circuits[0].circuit_breaker.ampere_rating == 15
    assert [c.id for c in _all_cables(house.panelboards[0].cables)] == ["C1", "C2"]
    assert [c.id for c in circuits[0].all_cables()] == ["C1", "C2"]  # traced


def test_two_wire_cable_has_three_wires(house: House) -> None:
    c1 = house.panelboards[0].cables[0]
    assert [w.role for w in c1.wires] == ["ungrounded", "neutral", "egc"]


def test_device_discriminated_by_type(house: House) -> None:
    devices = house.panelboards[0].cables[0].devices
    assert devices[0].type == "snap_switch"
    assert devices[0].function == "single_pole"


def test_unknown_key_rejected() -> None:
    with pytest.raises(ValidationError):
        House.model_validate({"meta": {"project": "x"}, "gremlins": []})


def test_bad_breaker_line_rejected() -> None:
    with pytest.raises(ValidationError):
        House.model_validate(
            {
                "meta": {"project": "x"},
                "panelboards": [
                    {
                        "id": "MP",
                        "branch_circuits": [
                            {"id": "c", "circuit_breaker": {"line": "L3", "ampere_rating": 15}}
                        ],
                    }
                ],
            }
        )


def test_malformed_splice_member_rejected() -> None:
    with pytest.raises(ValidationError):
        House.model_validate(
            {
                "meta": {"project": "x"},
                "panelboards": [
                    {
                        "id": "MP",
                        "branch_circuits": [
                            {"id": "c", "circuit_breaker": {"line": "L1", "ampere_rating": 15}}
                        ],
                        "cables": [
                            {
                                "id": "C1",
                                "type": "NM-B",
                                "size_awg": 14,
                                "conductors": 2,
                                "to": "B",
                                "splices": [{"join": ["C1 ungrounded", "SW1.LINE"]}],
                            }
                        ],
                    }
                ],
            }
        )


@pytest.mark.parametrize(
    ("breaker", "match"),
    [
        ({"poles": 1, "ampere_rating": 15}, "1-pole breaker needs its line"),
        ({"line": "L1", "poles": 2, "ampere_rating": 20}, "2-pole breaker spans both legs"),
    ],
)
def test_breaker_line_is_required_for_1_pole_and_rejected_for_2_pole(
    breaker: dict[str, object], match: str
) -> None:
    with pytest.raises(ValidationError, match=match):
        CircuitBreaker.model_validate(breaker)
