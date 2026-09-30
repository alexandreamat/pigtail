"""Panelboards -- where branch circuits originate, and the root of the wiring
tree: the runs leaving the cabinet hang under it, and its splices say which
wire lands on which breaker terminal or busbar.
"""

from __future__ import annotations

from functools import cached_property
from typing import Any, ClassVar

from skidl import Net

from pigtail.models._base import BaseModel, join
from pigtail.models._dot import bus_ref
from pigtail.models.cable import Cable, Splice
from pigtail.models.circuit import BranchCircuit
from pigtail.models.types import Line, PanelboardBus


class MainBreaker(BaseModel):
    """The panelboard's main overcurrent device (NEC 408.36) -- a circuit
    breaker sized to the panelboard / service rating.
    """

    ampere_rating: int


class Panelboard(BaseModel):
    """NEC Art. 100 (Panelboard): a panel (or units assembled as one) with buses
    and overcurrent devices, with or without switches, mounted in a cabinet and
    accessible only from the front.

    Each busbar (``BUSES``) is a net, created at construction inside the circuit
    context opened by House.from_yaml.

    ``cables`` are the runs leaving the cabinet. ``splices`` are the landings:
    each wire on a breaker's LOAD terminal (``<circuit>.LOAD``, a 2-pole's
    ``LOAD1`` / ``LOAD2``) or a busbar (``<panelboard>.NEUTRAL`` / ``.EGC``) --
    including an EMT run's tubing, bonded to the cabinet (``<run>.egc``).
    """

    BUSES: ClassVar[tuple[PanelboardBus, ...]] = ("L1", "L2", "NEUTRAL", "EGC")

    id: str
    # `service` marks this as service equipment (Art. 100): the grounded
    # (neutral) and equipment grounding buses are joined by the main bonding
    # jumper (250.24(A)(5)). A sub-panel (False) keeps them isolated (250.142,
    # 408.40).
    service: bool = True
    main_breaker: MainBreaker | None = None  # None = main-lug-only / sub-panel
    branch_circuits: list[BranchCircuit] = []  # the breakers
    cables: list[Cable] = []  # runs leaving the cabinet
    splices: list[Splice] = []  # landings on breaker terminals and busbars

    def model_post_init(self, _context: Any, /) -> None:
        _ = (self.l1_net, self.l2_net, self.neutral_net, self.egc_net)

    @cached_property
    def l1_net(self) -> Net:
        return Net(f"{self.id}:L1")

    @cached_property
    def l2_net(self) -> Net:
        return Net(f"{self.id}:L2")

    @cached_property
    def neutral_net(self) -> Net:
        return Net(f"{self.id}:NEUTRAL")

    @cached_property
    def egc_net(self) -> Net:
        return Net(f"{self.id}:EGC")

    def leg_net(self, line: Line) -> Net:
        return self.l1_net if line == "L1" else self.l2_net

    # --- assembly ------------------------------------------------------
    def wire_circuits(self) -> None:
        """Clip each branch circuit's breaker onto the busbars: LINE (1-pole) or
        LINE1 / LINE2 (2-pole) onto the leg net(s). The LOAD side is wired by
        the panelboard's ``splices``.
        """
        for bc in self.branch_circuits:
            breaker = bc.breaker_part
            if bc.circuit_breaker.poles == 2:
                join(self.l1_net, breaker["LINE1"])
                join(self.l2_net, breaker["LINE2"])
            else:
                join(self.leg_net(bc.circuit_breaker.leg), breaker["LINE"])

    def bus_net(self, bus: str) -> Net | None:
        """The net of a busbar a wire may land on (NEUTRAL, EGC); None otherwise."""
        return {"NEUTRAL": self.neutral_net, "EGC": self.egc_net}.get(bus)

    def bus_nets(self) -> list[tuple[Net, str]]:
        """``(net, label)`` per busbar -- lets a conductor schedule name the
        panelboard bus a conductor is bonded to.
        """
        return [
            (self.l1_net, f"{self.id}:L1"),
            (self.l2_net, f"{self.id}:L2"),
            (self.neutral_net, f"{self.id}:NEUTRAL"),
            (self.egc_net, f"{self.id}:EGC"),
        ]

    # --- diagram ---------------------------------------------------
    def bus_ref(self, bus: str) -> str:
        """DOT node id of one busbar (``bus`` in L1 / L2 / N / EGC)."""
        return bus_ref(self.id, bus)

    def diagram_buses(self, *, hot_used: set[str]) -> str:
        """The four busbars as one node -- a vertical stack of rows, each row a
        busbar reachable as ``"<id>_bus":<bus>``. L1 / L2 dim when the drawn
        circuits do not use that leg.
        """

        def row(bus: str, fill: str, *, dim: bool = False) -> str:
            text = f'<font color="#9a9a9a">{bus}</font>' if dim else bus
            border = ' border="1" color="#111111"' if bus == "N" else ""
            return f'<tr><td port="{bus}"{border} bgcolor="{fill}">{text}</td></tr>'

        rows = "".join(
            [
                row("L1", "#e9a6a6" if "L1" in hot_used else "#efefef", dim="L1" not in hot_used),
                row("L2", "#e9a6a6" if "L2" in hot_used else "#efefef", dim="L2" not in hot_used),
                row("N", "#ffffff"),
                row("EGC", "#a9d3b6"),
            ]
        )
        return (
            f'  "{self.id}_bus" [shape=plaintext label=<'
            f'<table border="1" cellborder="0" cellspacing="3" cellpadding="7" bgcolor="#cfd6ef">'
            f"{rows}</table>>];"
        )
