"""Devices: a flat discriminated union, one model per kind."""

from __future__ import annotations

from functools import cached_property
from typing import Annotated, Any, Literal

from pydantic import Field
from skidl import Part

from pigtail.models._base import BaseModel
from pigtail.models._dot import device_record
from pigtail.models.types import BreakerPoles, NemaConfig, SwitchFunction, Terminal, TerminalTemp


class SnapSwitch(BaseModel):
    """NEC Art. 100 (Switch, General-Use Snap): a general-use switch built to
    mount in a device box or on a box cover, for use with Code-recognised
    wiring methods.
    """

    type: Literal["snap_switch"] = "snap_switch"
    id: str
    function: SwitchFunction = "single_pole"  # NEC 404.2

    def model_post_init(self, _context: Any, /) -> None:
        _ = self.part

    def demand_va(self) -> tuple[float, float]:
        """(continuous, noncontinuous) load it serves: a switch serves none."""
        return 0.0, 0.0

    @property
    def terminals(self) -> tuple[Terminal, ...]:
        return ("LINE", "LOAD", "EGC")

    def diagram_node(self) -> str:
        return device_record(
            self.id, f"{self.id}\\n{self.function} switch", self.terminals, fill="#e8f0fe"
        )

    @cached_property
    def part(self) -> Part:
        return self._make_part("SNAP_SWITCH", self.id, self.terminals, value=self.function)


class Luminaire(BaseModel):
    """NEC Art. 100 (Luminaire): a complete lighting unit -- light source(s)
    plus the parts that position them and connect them to power. A lampholder
    alone is not a luminaire.
    """

    type: Literal["luminaire"] = "luminaire"
    id: str
    load_va: float | None = Field(default=None, gt=0)  # NEC Art. 220; None = not recorded

    def model_post_init(self, _context: Any, /) -> None:
        _ = self.part

    def demand_va(self) -> tuple[float, float]:
        """(continuous, noncontinuous) load it serves: its rating, noncontinuous;
        none when not recorded.
        """
        return 0.0, self.load_va or 0.0

    @property
    def terminals(self) -> tuple[Terminal, ...]:
        return ("LINE", "NEUTRAL", "EGC")

    def diagram_node(self) -> str:
        return device_record(
            self.id, f"{self.id}\\n{_load(self.load_va)}", self.terminals, fill="#fff8dc"
        )

    @cached_property
    def part(self) -> Part:
        return self._make_part(
            "LUMINAIRE", self.id, self.terminals, value=_load(self.load_va), load_va=self.load_va
        )


class Appliance(BaseModel):
    """NEC Art. 100 (Appliance): utilization equipment installed or connected as
    a unit to perform one or more functions -- here hardwired, fastened in
    place with no plug (e.g. a furnace). ``poles`` 1 is 120 V
    (LINE/NEUTRAL/EGC); 2 is 240 V (LINE1/LINE2/EGC).
    """

    type: Literal["appliance"] = "appliance"
    id: str
    poles: BreakerPoles = 1
    load_va: float | None = Field(default=None, gt=0)  # nameplate, Art. 220; None = not recorded
    continuous: bool = False  # a load running 3 h or more

    def model_post_init(self, _context: Any, /) -> None:
        _ = self.part

    def demand_va(self) -> tuple[float, float]:
        """(continuous, noncontinuous) load it serves: its ``load_va``,
        continuous when marked so; none when not recorded.
        """
        va = self.load_va or 0.0
        return (va, 0.0) if self.continuous else (0.0, va)

    @property
    def terminals(self) -> tuple[Terminal, ...]:
        return ("LINE", "NEUTRAL", "EGC") if self.poles == 1 else ("LINE1", "LINE2", "EGC")

    def diagram_node(self) -> str:
        tags = [_load(self.load_va)] + (["240 V"] if self.poles == 2 else [])
        return device_record(
            self.id, f"{self.id}\\nappliance · {' · '.join(tags)}", self.terminals, fill="#f3e8fd"
        )

    @cached_property
    def part(self) -> Part:
        return self._make_part(
            "APPLIANCE", self.id, self.terminals, value=_load(self.load_va), poles=self.poles
        )


def _load(load_va: float | None) -> str:
    return "load not recorded" if load_va is None else f"{load_va:g} VA"


class Receptacle(BaseModel):
    """NEC Art. 100 (Receptacle): a contact device installed at an outlet for
    the connection of an attachment plug. ``poles`` 1 is a 120 V device
    (LINE/NEUTRAL/EGC); 2 is a 240 V device: LINE1/LINE2/EGC for a straight
    240 V NEMA 6-xx, plus NEUTRAL for a 120/240 V NEMA 14-xx.
    """

    type: Literal["receptacle"] = "receptacle"
    id: str
    poles: BreakerPoles = 1
    nema: NemaConfig | None = None  # ANSI/NEMA WD 6 configuration; None = not recorded
    gfci: bool = False  # NEC 210.8 -- ground-fault circuit interrupter
    grounding: bool = True  # False = ungrounded (no EGC), as-built pre-1962 wiring (406.4(D))
    tamper_resistant: bool = True  # NEC 406.12
    weather_resistant: bool = False  # NEC 406.9(B), damp/wet locations
    terminal_c: TerminalTemp | None = None  # as marked; None = unmarked, 110.14(C)(1) default
    load_va: float | None = Field(default=None, gt=0)  # the load it serves, if known (Art. 220)
    continuous: bool = False  # a load running 3 h or more -- e.g. EV charging (625.42)

    def model_post_init(self, _context: Any, /) -> None:
        _ = self.part

    def demand_va(self) -> tuple[float, float]:
        """(continuous, noncontinuous) load it serves: its declared ``load_va``,
        continuous when marked so; none when undeclared.
        """
        va = self.load_va or 0.0
        return (va, 0.0) if self.continuous else (0.0, va)

    @property
    def terminals(self) -> tuple[Terminal, ...]:
        if self.poles == 2:  # 14-xx is 120/240 V with a neutral; 6-xx is 240 V only
            return (
                ("LINE1", "LINE2", "NEUTRAL", "EGC")
                if self.nema is not None and self.nema.startswith(("14-", "L14-"))
                else ("LINE1", "LINE2", "EGC")
            )
        return ("LINE", "NEUTRAL", "EGC")

    def diagram_node(self) -> str:
        tags = [self.nema or "NEMA not recorded"] + [
            t
            for t, on in (
                ("GFCI", self.gfci),
                ("no-EGC", not self.grounding),
                ("240 V", self.poles == 2),
            )
            if on
        ]
        return device_record(
            self.id, f"{self.id}\\n{' · '.join(tags)}", self.terminals, fill="#eafaea"
        )

    @cached_property
    def part(self) -> Part:
        return self._make_part(
            "RECEPTACLE",
            self.id,
            self.terminals,
            value=self.nema or "",
            poles=self.poles,
            gfci=self.gfci,
            grounding=self.grounding,
        )


# NEC Art. 100 (Device): a unit of an electrical system, other than a conductor,
# that carries or controls electric energy as its principal function.
type Device = Annotated[
    SnapSwitch | Luminaire | Receptacle | Appliance, Field(discriminator="type")
]
