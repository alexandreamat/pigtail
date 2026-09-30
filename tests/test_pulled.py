"""EMT runs described wire by wire (``Cable.pulled``) and single-member caps."""

from __future__ import annotations

from typing import Any

import pytest

from pigtail.fill import required_cu_in
from pigtail.models.house import House
from pigtail.outputs.diagram import circuit_diagram


def _house(**overrides: Any) -> dict[str, Any]:
    """Panel -> E1 (EMT home run: red hot + white) -> box J -> E2 (EMT: black
    hot, two red switch legs -- one taped blue -- and a capped white) -> box SW
    with two single-pole switches.
    """
    e2: dict[str, Any] = {
        "id": "E2",
        "type": "EMT",
        "trade_size": "1/2",
        "size_awg": 14,
        "to": "SW",
        "pulled": [
            {"name": "hot", "role": "ungrounded", "color": "black"},
            {"name": "leg_a", "role": "ungrounded", "color": "red"},
            {"name": "leg_b", "role": "ungrounded", "color": "red", "tape": "blue"},
            {"name": "neutral", "role": "neutral", "color": "white"},
        ],
        "devices": [
            {"id": "SA", "type": "snap_switch"},
            {"id": "SB", "type": "snap_switch"},
        ],
        "splices": [
            {"join": ["E2.hot", "SA.LINE", "SB.LINE"]},
            {"join": ["E2.leg_a", "SA.LOAD"]},
            {"join": ["E2.leg_b", "SB.LOAD"]},
            {"join": ["E2.neutral"]},  # capped, 404.2(C)
            {"join": ["E2.egc", "SA.EGC", "SB.EGC"]},
        ],
    }
    e2.update(overrides)
    return {
        "meta": {"project": "x"},
        "boxes": [
            {"id": "J", "type": "junction", "material": "metal", "volume_cu_in": 21.5},
            {"id": "SW", "type": "device", "material": "metal", "volume_cu_in": 21.0},
        ],
        "panelboards": [
            {
                "id": "MP",
                "branch_circuits": [
                    {"id": "C", "circuit_breaker": {"line": "L1", "poles": 1, "ampere_rating": 15}}
                ],
                "cables": [
                    {
                        "id": "E1",
                        "type": "EMT",
                        "trade_size": "1/2",
                        "size_awg": 14,
                        "to": "J",
                        "pulled": [
                            {"name": "hot", "role": "ungrounded", "color": "red"},
                            {"name": "neutral", "role": "neutral", "color": "white"},
                        ],
                        "splices": [
                            {"join": ["E1.hot", "E2.hot"]},
                            {"join": ["E1.neutral", "E2.neutral"]},
                            {"join": ["E1.egc", "E2.egc"]},
                        ],
                        "cables": [e2],
                    }
                ],
                "splices": [
                    {"join": ["E1.hot", "C.LOAD"]},
                    {"join": ["E1.neutral", "MP.NEUTRAL"]},
                    {"join": ["E1.egc", "MP.EGC"]},
                ],
            }
        ],
    }


@pytest.fixture
def house() -> House:
    return House.from_dict(_house())


def test_pulled_wires_are_named_plus_the_raceway(house: House) -> None:
    e2 = house.cable("E2")
    assert [w.name for w in e2.wires] == ["hot", "leg_a", "leg_b", "neutral", "egc"]
    assert e2.wire("leg_b").color == "red" and e2.wire("leg_b").tape == "blue"
    assert e2.wire("egc").raceway is True
    assert e2.spec_label == "EMT 14/4"


def test_two_switch_legs_of_one_colour_stay_apart(house: House) -> None:
    a, b = house.cable("E2").wire("leg_a").net, house.cable("E2").wire("leg_b").net
    assert house.device("SA").part["LOAD"].net.is_attached(a)
    assert house.device("SB").part["LOAD"].net.is_attached(b)
    assert not a.is_attached(b)


def test_home_run_lands_by_role(house: House) -> None:
    mp = house.panelboard("MP")
    breaker = house.branch_circuit("C").breaker_part
    assert house.cable("E1").wire("hot").net.is_attached(breaker["LOAD"].net)
    assert house.cable("E1").wire("neutral").net.is_attached(mp.neutral_net)
    assert house.device("SA").part["EGC"].net.is_attached(mp.egc_net)  # via the raceway


def test_capped_neutral_reaches_the_switch_box_and_stops(house: House) -> None:
    mp = house.panelboard("MP")
    assert house.cable("E2").wire("neutral").net.is_attached(mp.neutral_net)


def test_box_fill_counts_pulled_wires_but_not_the_raceway(house: House) -> None:
    # SW: 4 insulated x 2.0 + two switch yokes 2 x 2 x 2.0; no wire EGC enters
    assert required_cu_in(house, "SW") == 16.0


def test_diagram_draws_real_colours_and_the_tape_band(house: House) -> None:
    dot = circuit_diagram(house)
    assert '<td port="leg_b" bgcolor="#d33333">' in dot  # red, not black
    assert '<td bgcolor="blue" width="8"> </td>' in dot  # the blue identification band
    assert (
        '"C":LOAD:e -> "E1":hot:w [color="#d33333" class="circuit-C"];' in dot
    )  # the red hot is red from the breaker
    assert '"E1":egc:w -> "MP_bus":EGC:e' in dot
    # a named conductor is a cable member, not a device terminal (never entered from below):
    assert '-> "E2":leg_a:e' in dot  # in SW, E2 is the incoming run -- its east side
    assert '-> "E2":hot:w' in dot  # in J, E2 is the onward run -- its west side
    assert '"E2":leg_a:s' not in dot


def test_single_member_splice_is_a_cap(house: House) -> None:
    dot = circuit_diagram(house)
    assert dot.count('-> "E2":neutral:e') == 1  # one edge into the SW cap from E2


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"type": "NM-B", "trade_size": None}, "pulled applies only to EMT"),
        ({"conductors": 2}, "not both"),
        ({"pulled": []}, "needs conductors"),
        (
            {"reidentify": [{"conductor": "neutral", "plays": "ungrounded", "tape": "black"}]},
            "own tape",
        ),
    ],
)
def test_pulled_validation(overrides: dict[str, Any], match: str) -> None:
    with pytest.raises(Exception, match=match):
        House.from_dict(_house(**overrides))


def test_pulled_names_are_unique_and_egc_is_the_raceway() -> None:
    dup = [{"name": "x", "role": "ungrounded", "color": "black"}] * 2
    with pytest.raises(Exception, match="unique"):
        House.from_dict(_house(pulled=dup))
    green = [{"name": "egc", "role": "egc", "color": "green"}]
    with pytest.raises(Exception, match="raceway itself"):
        House.from_dict(_house(pulled=green))


def test_pulled_tape_may_not_be_white() -> None:
    bad = [{"name": "x", "role": "ungrounded", "color": "red", "tape": "white"}]
    with pytest.raises(Exception, match="unlawful"):
        House.from_dict(_house(pulled=bad))


def test_pulled_wire_egc_counts_once_in_fill() -> None:
    house = House.from_dict(
        _house(
            pulled=[
                {"name": "hot", "role": "ungrounded", "color": "black"},
                {"name": "leg_a", "role": "ungrounded", "color": "red"},
                {"name": "leg_b", "role": "ungrounded", "color": "red", "tape": "blue"},
                {"name": "neutral", "role": "neutral", "color": "white"},
                {"name": "green", "role": "egc", "color": "green"},
            ],
            splices=[
                {"join": ["E2.hot", "SA.LINE", "SB.LINE"]},
                {"join": ["E2.leg_a", "SA.LOAD"]},
                {"join": ["E2.leg_b", "SB.LOAD"]},
                {"join": ["E2.neutral"]},
                {"join": ["E2.egc", "E2.green", "SA.EGC", "SB.EGC"]},
            ],
        )
    )
    assert house.cable("E2").spec_label == "EMT 14/4 w/G"
    assert required_cu_in(house, "SW") == 18.0  # 16.0 + one 2.0 wire-EGC allowance


def test_splice_edges_take_the_wire_colour_and_devices_sit_side_by_side(house: House) -> None:
    dot = circuit_diagram(house)
    red = "#d33333"
    assert f'"spl_SW":s2:n -> "E2":leg_b:e [color="{red}"' in dot  # red switch leg, red line
    assert f'"spl_SW":s2:n -> "SB":LOAD:s [color="{red}"' in dot  # its device end too
    assert '"spl_J":s0:n -> "E1":hot:e [color="#d33333"' in dot  # the red home-run hot
    assert '"spl_J":s0:n -> "E2":hot:w [color="#111111"' in dot  # spliced to a black
    assert '"SA" -> "SB" [style=invis];' in dot  # left to right, not stacked


def test_yellow_identification_tape_is_drawn() -> None:
    pulled = [
        {"name": "hot", "role": "ungrounded", "color": "black"},
        {"name": "leg_a", "role": "ungrounded", "color": "red", "tape": "yellow"},
        {"name": "leg_b", "role": "ungrounded", "color": "red", "tape": "blue"},
        {"name": "neutral", "role": "neutral", "color": "white"},
    ]
    house = House.from_dict(_house(pulled=pulled))
    assert house.cable("E2").wire("leg_a").tape == "yellow"
    assert '<td bgcolor="yellow" width="8"> </td>' in circuit_diagram(house)
