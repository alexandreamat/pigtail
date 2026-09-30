"""The single circuit diagram (`circuit_diagram`)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

from pigtail.models._base import BuildError
from pigtail.models.house import House
from pigtail.outputs.diagram import circuit_diagram

EXAMPLES = Path(__file__).parent.parent / "examples"


def test_one_circuit_diagram_shape(house: House) -> None:
    dot = circuit_diagram(house, only="LTG-1")
    assert dot.startswith("digraph circuit {")
    assert dot.rstrip().endswith("}")
    # panel bus node, breaker, both cables, both boxes, both devices
    for token in (
        '"MP_bus"',
        '"LTG-1"',
        '"C1"',
        '"C2"',
        '"cluster_SB1"',
        '"cluster_FB1"',
        '"SW1"',
        "spl_SB1",
    ):
        assert token in dot, token


def test_cables_are_not_box_contents(house: House) -> None:
    """A cable is the run *between* boxes -- its node must be emitted before any
    box cluster, never nested inside one.
    """
    lines = circuit_diagram(house, only="LTG-1").splitlines()
    first_cluster = next(
        i for i, ln in enumerate(lines) if ln.startswith('  subgraph "cluster_SB1"')
    )
    c1_node = next(
        i for i, ln in enumerate(lines) if ln.strip().startswith('"C1" [shape=plaintext')
    )
    assert c1_node < first_cluster


def test_diagram_routes_conductors_by_role(house: House) -> None:
    dot = circuit_diagram(house, only="LTG-1")
    # the home run's grounded conductor returns to the panel N bus
    assert '"C1":neutral:w -> "MP_bus":N:e' in dot
    # and its EGC to the panel EGC bus, dashed
    assert (
        '"C1":egc:w -> "MP_bus":EGC:e [color="#0a8a0a" style=dashed class="circuit-LTG-1"];' in dot
    )


def test_unknown_circuit_raises(house: House) -> None:
    with pytest.raises(BuildError, match="nope"):
        circuit_diagram(house, only="nope")


def test_whole_house_diagram_covers_every_circuit(load_example: Callable[[], House]) -> None:
    house = load_example()
    dot = circuit_diagram(house)
    for bc in house.panelboards[0].branch_circuits:
        assert f'"{bc.id}"' in dot


def test_knob_and_tube_diagram_has_no_egc_row() -> None:
    house = House.from_yaml(EXAMPLES / "knob_and_tube.yaml")
    dot = circuit_diagram(house, only="BR-6")
    assert '<td port="egc"' not in dot  # K&T cables have no EGC conductor
    assert '"MP_bus":EGC' not in dot  # nothing bonds to the EGC bus


def test_emt_diagram_marks_raceway_egc() -> None:
    house = House.from_yaml(EXAMPLES / "emt_conduit.yaml")
    dot = circuit_diagram(house, only="GAR-12")
    assert "EGC · raceway" in dot
    assert '"E1":egc:w -> "MP_bus":EGC:e' in dot


def test_every_circuit_element_carries_its_circuit_class() -> None:
    """A viewer hides a circuit by its SVG class: the breaker and everything
    traced onto it are tagged ``circuit-<id>``; the panelboard's busbars are not.
    """
    dot = circuit_diagram(House.from_yaml(EXAMPLES / "switch_loop.yaml"))
    tag = 'class="circuit-LTG-1"'
    for node in ("LTG-1", "C1", "C2", "SW1", "L1", "spl_SB1", "spl_FB1"):
        assert f'"{node}" [{tag}];' in dot, node
    assert f"graph [{tag}];" in dot  # the boxes
    assert '"MP_bus" [shape' in dot and '"MP_bus" [class' not in dot  # busbars stay untagged


def test_a_run_shared_by_circuits_carries_each_class() -> None:
    """A tube with two circuits' wires shows while either is on: it carries
    both classes, and each wire's lines carry its own.
    """
    data = yaml.safe_load((EXAMPLES / "emt_conduit.yaml").read_text())
    mp = data["panelboards"][0]
    mp["branch_circuits"].append(
        {"id": "C9", "circuit_breaker": {"line": "L2", "ampere_rating": 20}}
    )
    mp["cables"][0]["pulled"] = [
        {"name": "ungrounded", "role": "ungrounded", "color": "black"},
        {"name": "neutral", "role": "neutral", "color": "white"},
        {"name": "red", "role": "ungrounded", "color": "red"},
    ]
    del mp["cables"][0]["conductors"]
    mp["cables"][0]["splices"].append({"join": ["E1.red"]})
    mp["splices"].append({"join": ["E1.red", "C9.LOAD"]})
    dot = circuit_diagram(House.from_dict(data))
    assert '"E1" [class="circuit-GAR-12 circuit-C9"];' in dot
    assert '"C9":LOAD:e -> "E1":red:w [color="#d33333" class="circuit-C9"];' in dot
    assert '"E2" [class="circuit-GAR-12"];' in dot  # E2 carries only GAR-12


def test_runs_leaving_a_box_straddle_it() -> None:
    """Two runs out of one box: an invisible point pinned to the box's height,
    the first run above it and the second below.
    """
    data = yaml.safe_load((EXAMPLES / "emt_conduit.yaml").read_text())
    e1 = data["panelboards"][0]["cables"][0]
    e3 = {
        **e1["cables"][0],
        "id": "E3",
        "to": "EMB3",
        "devices": [],
        "splices": [{"join": ["E3.ungrounded"]}, {"join": ["E3.neutral"]}],
    }
    e1["cables"].append(e3)
    data["boxes"].append(
        {"id": "EMB3", "type": "junction", "material": "metal", "volume_cu_in": 21.0}
    )
    dot = circuit_diagram(House.from_dict(data))
    assert '"spl_EMB1" -> "fork_spl_EMB1" [style=invis weight=100];' in dot
    assert '{ rank=same; "E2"; "fork_spl_EMB1"; "E3"; }' in dot
    assert '"E2" -> "fork_spl_EMB1" -> "E3" [style=invis];' in dot
