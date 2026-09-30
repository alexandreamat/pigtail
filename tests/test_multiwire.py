"""One tube carrying two circuits' hots and one white -- a multiwire branch
circuit once the white is traced to both circuits' loads -- and the panelboard
landings that say which wire is on which breaker.
"""

from __future__ import annotations

import warnings
from typing import Any

import pytest

from pigtail.models._base import BuildError
from pigtail.models.house import House
from pigtail.nec import NECViolation
from pigtail.outputs.diagram import circuit_diagram


def _lamp(run: str, box: str, lamp: str) -> dict[str, Any]:
    """A run from J to ``box``: a hot and a white to one lamp."""
    return {
        "id": run,
        "type": "EMT",
        "trade_size": "1/2",
        "size_awg": 14,
        "to": box,
        "pulled": [
            {"name": "hot", "role": "ungrounded", "color": "black"},
            {"name": "neutral", "role": "neutral", "color": "white"},
        ],
        "devices": [{"id": lamp, "type": "luminaire", "load_va": 60}],
        "splices": [
            {"join": [f"{run}.hot", f"{lamp}.LINE"]},
            {"join": [f"{run}.neutral", f"{lamp}.NEUTRAL"]},
        ],
    }


def _house(
    *, c12_line: str = "L2", traced: bool = True, landings: dict[str, str] | None = None
) -> dict[str, Any]:
    """Panel -> E1 -> box J: black on C5, red on C12, one white. In J the black
    goes on (E2) to lamp A, the red (E3) to lamp B, the white to both.
    Untraced: the red and the white end at nuts in J.
    """
    splices = [
        {"join": ["E1.hot", "E2.hot"]},
        {"join": ["E1.hot_c12", "E3.hot"]},
        {"join": ["E1.neutral", "E2.neutral", "E3.neutral"]},
    ]
    onward = [_lamp("E2", "K", "A"), _lamp("E3", "M", "B")]
    if not traced:
        splices = [{"join": ["E1.hot", "E2.hot"]}, {"join": ["E1.hot_c12"]}]
        splices.append({"join": ["E1.neutral", "E2.neutral"]})
        onward = onward[:1]
    land = {"hot": "C5.LOAD", "hot_c12": "C12.LOAD", "neutral": "MP.NEUTRAL", **(landings or {})}
    e1: dict[str, Any] = {
        "id": "E1",
        "type": "EMT",
        "trade_size": "1/2",
        "size_awg": 14,
        "to": "J",
        "pulled": [
            {"name": "hot", "role": "ungrounded", "color": "black"},
            {"name": "hot_c12", "role": "ungrounded", "color": "red"},
            {"name": "neutral", "role": "neutral", "color": "white"},
        ],
        "splices": splices,
        "cables": onward,
    }
    return {
        "meta": {"project": "x"},
        "boxes": [
            {"id": b, "type": "junction", "material": "metal", "volume_cu_in": 21.0}
            for b in ("J", "K", "M")
        ],
        "panelboards": [
            {
                "id": "MP",
                "branch_circuits": [
                    {"id": "C5", "circuit_breaker": {"line": "L1", "ampere_rating": 15}},
                    {"id": "C12", "circuit_breaker": {"line": c12_line, "ampere_rating": 20}},
                ],
                "cables": [e1],
                "splices": [{"join": [f"E1.{w}", t]} for w, t in land.items()],
            }
        ],
    }


def _violations(house: House) -> list[str]:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        house.check()
    return [str(w.message) for w in caught if issubclass(w.category, NECViolation)]


def test_each_hot_lands_on_its_own_breaker() -> None:
    house = House.from_dict(_house())
    e1 = house.cable("E1")
    c5, c12 = house.branch_circuit("C5").breaker_part, house.branch_circuit("C12").breaker_part
    assert e1.wire("hot").net.is_attached(c5["LOAD"].net)
    assert e1.wire("hot_c12").net.is_attached(c12["LOAD"].net)
    assert not e1.wire("hot").net.is_attached(e1.wire("hot_c12").net)
    assert e1.wire("neutral").net.is_attached(house.panelboard("MP").neutral_net)


def test_circuits_are_traced_from_the_wiring() -> None:
    house = House.from_dict(_house())
    trace, e1 = house.trace, house.cable("E1")
    assert [bc.id for bc in trace.circuits(e1.wire("hot"))] == ["C5"]
    assert [bc.id for bc in trace.circuits(e1.wire("hot_c12"))] == ["C12"]
    assert [bc.id for bc in trace.circuits(e1.wire("neutral"))] == ["C5", "C12"]
    assert [bc.id for bc in trace.circuits(house.cable("E3").wire("neutral"))] == ["C12"]
    assert [c.id for c in house.branch_circuit("C12").all_cables()] == ["E1", "E3"]
    assert [d.id for d in house.branch_circuit("C12").devices()] == ["B"]


def test_shared_neutral_on_separate_breakers_is_flagged() -> None:
    found = _violations(House.from_dict(_house()))
    assert any(m.startswith("210.4(B): cable E1 -- multiwire branch circuit C5+C12") for m in found)
    assert not any(m.startswith("200.4(A)") for m in found)  # opposite legs
    assert any(
        m.startswith(
            "240.4(D): cable E1 -- shared neutral E1.neutral (14 AWG) is good for 15 A but "
            "carries up to 20 A from circuit C12's breaker"
        )
        for m in found
    )


def test_shared_neutral_on_one_leg_is_flagged() -> None:
    found = _violations(House.from_dict(_house(c12_line="L1")))
    assert any(
        m.startswith("200.4(A): cable E1 -- neutral shared by C5+C12 on the same leg")
        for m in found
    )


def test_a_white_whose_loads_are_not_traced_is_not_shared() -> None:
    house = House.from_dict(_house(traced=False))
    assert [bc.id for bc in house.trace.circuits(house.cable("E1").wire("neutral"))] == ["C5"]
    assert not any(m.startswith(("210.4(B)", "200.4(A)")) for m in _violations(house))


def test_diagram_lands_each_wire_from_its_breaker() -> None:
    house = House.from_dict(_house())
    dot = circuit_diagram(house)
    assert '"C12":LOAD:e -> "E1":hot_c12:w [color="#d33333" class="circuit-C12"];' in dot
    assert '"E1" [class="circuit-C5 circuit-C12"];' in dot
    only = circuit_diagram(house, only="C12")
    assert '"E1" [' in only and '"E3" [' in only and '"E2" [' not in only


@pytest.mark.parametrize(
    ("landings", "match"),
    [
        ({"hot_c12": "C9.LOAD"}, "unknown reference 'C9'"),
        ({"hot_c12": "C12.LINE"}, "no LOAD terminal 'LINE'"),
        ({"neutral": "MP.L1"}, "NEUTRAL or EGC"),
    ],
)
def test_panel_landings_are_checked(landings: dict[str, str], match: str) -> None:
    with pytest.raises(BuildError, match=match):
        House.from_dict(_house(landings=landings))


def test_a_breaker_is_reachable_only_in_its_panelboard() -> None:
    data = _house()
    data["panelboards"][0]["cables"][0]["splices"].append({"join": ["E1.hot", "C5.LOAD"]})
    with pytest.raises(BuildError, match="unknown reference 'C5'"):
        House.from_dict(data)


def test_miswiring_against_the_declared_roles_is_flagged() -> None:
    found = _violations(
        House.from_dict(_house(landings={"neutral": "C12.LOAD", "hot_c12": "MP.NEUTRAL"}))
    )
    assert any(
        m.startswith("200.11: cable E1 -- neutral E1.neutral is energized from circuit C12")
        for m in found
    )
    assert any(
        m.startswith("110.7: cable E1 -- ungrounded E1.hot_c12 is joined to the neutral or EGC bus")
        for m in found
    )
