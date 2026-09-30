"""Overcurrent devices and branch circuits."""

from __future__ import annotations

from functools import cached_property
from typing import Any

from pydantic import PrivateAttr, model_validator
from skidl import Part

from pigtail.models._base import BaseModel, BuildError, require
from pigtail.models._dot import breaker_record, bus_ref
from pigtail.models.cable import Cable
from pigtail.models.device import Device
from pigtail.models.types import BreakerPoles, Line, Terminal, TerminalTemp


class CircuitBreaker(BaseModel):
    """NEC Art. 100 (Circuit Breaker): a device that opens and closes a circuit
    by non-automatic means and opens it automatically on a predetermined
    overcurrent, without damaging itself, when applied within its rating.
    """

    # the leg a 1-pole breaker clips onto; a 2-pole breaker spans both legs and
    # takes none
    line: Line | None = None
    poles: BreakerPoles = 1
    ampere_rating: int  # NEC 240.6
    afci: bool = False  # NEC 210.12
    gfci: bool = False  # NEC 210.8
    terminal_c: TerminalTemp | None = None  # as marked; None = unmarked, 110.14(C)(1) default

    @model_validator(mode="after")
    def _leg_matches_poles(self) -> CircuitBreaker:
        if self.poles == 1 and self.line is None:
            raise ValueError("a 1-pole breaker needs its line (L1 or L2)")
        if self.poles == 2 and self.line is not None:
            raise ValueError("a 2-pole breaker spans both legs; omit line")
        return self

    @property
    def leg(self) -> Line:
        """The one leg a 1-pole breaker clips onto."""
        if self.line is None:
            raise BuildError("a 2-pole breaker spans both legs; it has no single leg")
        return self.line

    @property
    def terminals(self) -> tuple[Terminal, ...]:
        # 1-pole: LINE/LOAD. 2-pole: a terminal per leg (LINE1/2, LOAD1/2).
        return ("LINE", "LOAD") if self.poles == 1 else ("LINE1", "LINE2", "LOAD1", "LOAD2")

    def part(self, ref: str) -> Part:
        # `ref` is the branch-circuit id: a breaker is identified by its circuit.
        return self._make_part(
            f"CIRCUIT_BREAKER_{self.poles}P",
            ref,
            self.terminals,
            value=f"{self.ampere_rating}A/{self.poles}P",
            ampere_rating=self.ampere_rating,
            poles=self.poles,
            afci=self.afci,
            gfci=self.gfci,
            line=self.line,
        )

    def diagram_node(self, ref: str) -> str:
        """The breaker: id + rating on top, LINE terminal(s) on the left, LOAD
        terminal(s) on the right -- a series element read left to right.
        """
        tag = [ref, f"{self.ampere_rating} A / {self.poles}P"]
        if self.afci:
            tag.append("AFCI")
        if self.gfci:
            tag.append("GFCI")
        return breaker_record(ref, "\\n".join(tag), poles=self.poles)


class BranchCircuit(BaseModel):
    """NEC Art. 100 (Branch Circuit): the circuit conductors between the final
    overcurrent device protecting the circuit and the outlet(s). Only the
    breaker is written; the runs and devices on the circuit are traced from
    the wiring (:mod:`pigtail.trace`) once the house is assembled.
    """

    id: str
    circuit_breaker: CircuitBreaker

    _runs: list[Cable] = PrivateAttr()  # set by House after tracing
    _devices: list[Device] = PrivateAttr()

    def model_post_init(self, _context: Any, /) -> None:
        _ = self.breaker_part

    @cached_property
    def breaker_part(self) -> Part:
        return self.circuit_breaker.part(self.id)

    # --- traced ---------------------------------------------------------
    def bind(self, runs: list[Cable], devices: list[Device]) -> None:
        self._runs = runs
        self._devices = devices

    def all_cables(self) -> list[Cable]:
        """Every run carrying one of this circuit's conductors."""
        return require(lambda: self._runs, f"circuit {self.id} runs")

    def devices(self) -> list[Device]:
        """Every device on this circuit."""
        return require(lambda: self._devices, f"circuit {self.id} devices")

    # --- diagram ------------------------------------------------------
    def clip_edges(self, *, panel_id: str) -> list[str]:
        """The busbars to the breaker's LINE terminal(s) -- the breaker's clips,
        not wires, drawn black.
        """
        black = "#111111"
        cls = f'class="circuit-{self.id}"'

        def bus(name: str) -> str:  # busbars feed off their east edge
            return f"{bus_ref(panel_id, name)}:e"

        if self.circuit_breaker.poles == 2:  # LINE terminals on the breaker's west
            return [
                f'  {bus("L1")} -> "{self.id}":LINE1:w [color="{black}" {cls}];',
                f'  {bus("L2")} -> "{self.id}":LINE2:w [color="{black}" {cls}];',
            ]
        return [f'  {bus(self.circuit_breaker.leg)} -> "{self.id}":LINE:w [color="{black}" {cls}];']
