"""Electrical-topology assertions for the switch-loop example.

The switch interrupts only the ungrounded conductor; the neutral bypasses the
switch; the EGC is continuous end to end.
"""

from __future__ import annotations

import pytest
from skidl import Net

from pigtail.models.house import House


def net_of(house: House, ref: str) -> Net:
    part_ref, terminal = ref.split(".")
    for net in house.built_circuit().get_nets():
        for pin in net.pins:
            if pin.part.ref == part_ref and pin.name == terminal:
                return net
    raise AssertionError(f"no net carries {ref}")


def refs_on(net: Net) -> set[str]:
    return {f"{pin.part.ref}.{pin.name}" for pin in net.pins}


def test_ungrounded_from_breaker_reaches_switch(house: House) -> None:
    assert "SW1.LINE" in refs_on(net_of(house, "LTG-1.LOAD"))


def test_switched_ungrounded_reaches_luminaire(house: House) -> None:
    net = net_of(house, "SW1.LOAD")
    assert "L1.LINE" in refs_on(net)
    assert "LTG-1.LOAD" not in refs_on(net)


def test_neutral_bypasses_switch(house: House) -> None:
    on = refs_on(net_of(house, "L1.NEUTRAL"))
    assert not any(ref.startswith("SW1.") for ref in on)


def test_neutral_is_panelboard_neutral(house: House) -> None:
    assert house.cable("C2").wire("neutral").net.is_attached(house.panelboard("MP").neutral_net)


def test_egc_continuous_and_bonds_switch(house: House) -> None:
    assert "SW1.EGC" in refs_on(net_of(house, "L1.EGC"))
    assert house.cable("C1").wire("egc").net.is_attached(house.panelboard("MP").egc_net)


def test_ungrounded_isolated_from_grounded(house: House) -> None:
    ungrounded = house.cable("C1").wire("ungrounded").net
    assert not ungrounded.is_attached(house.panelboard("MP").neutral_net)
    assert not ungrounded.is_attached(house.panelboard("MP").egc_net)


def test_breaker_line_on_l1(house: House) -> None:
    assert net_of(house, "LTG-1.LINE").is_attached(house.panelboard("MP").l1_net)


@pytest.mark.parametrize(
    ("cable_id", "role"),
    [
        ("C1", "ungrounded"),
        ("C1", "neutral"),
        ("C1", "egc"),
        ("C2", "ungrounded"),
        ("C2", "neutral"),
        ("C2", "egc"),
    ],
)
def test_every_conductor_landed(house: House, cable_id: str, role: str) -> None:
    assert house.cable(cable_id).wire(role).net.get_pins()
