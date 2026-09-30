from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from pigtail.models.house import House


def test_netlist_written(house: House, tmp_path: Path) -> None:
    path = tmp_path / "switch_loop.net"
    house.built_circuit().generate_netlist(file_=str(path))
    text = path.read_text()
    assert text.startswith("(export")
    for ref in ("LTG-1", "SW1", "L1"):
        assert f'(ref "{ref}")' in text


def test_net_summary_mentions_nodes(house: House) -> None:
    summary = house.net_summary()
    assert "SW1.LINE" in summary
    assert "L1.NEUTRAL" in summary


def test_conductor_schedule_resolves_merged_nets(house: House) -> None:
    schedule = house.conductor_schedule()
    row = next(line for line in schedule.splitlines() if line.strip().startswith("C1.neutral"))
    assert "MP:NEUTRAL" in row


def test_panel_schedule_lists_circuits(house: House) -> None:
    schedule = house.panel_schedule()
    assert "PANEL SCHEDULE" in schedule
    assert "LTG-1" in schedule


def test_two_loads_are_independent(load_example: Callable[[], House]) -> None:
    a, b = load_example(), load_example()
    assert a.built_circuit() is not b.built_circuit()
    assert a.cable("C1").wire("neutral").net is not b.cable("C1").wire("neutral").net
