"""A single conductor -- derived from its cable, never written in YAML."""

from __future__ import annotations

from functools import cached_property
from typing import Any

from skidl import Net

from pigtail.models._base import BaseModel
from pigtail.models._dot import COLOUR_CELL, html_esc
from pigtail.models.types import (
    AwgSize,
    ConductorColor,
    ConductorMaterial,
    ConductorRole,
    Insulation,
    Stranding,
)


class Conductor(BaseModel):
    """A single conductor of a cable. NEC Art. 100 distinguishes an insulated
    conductor (encased in Code-recognised insulation) from a bare one (no
    covering whatsoever); the EGC of Type NM is bare.
    """

    cable_id: str
    # how it is addressed within its run (``<cable>.<name>``): its role for a
    # cable assembly, the name given in YAML for a conductor pulled into EMT
    name: str
    role: ConductorRole  # the role it is installed to serve (a cable's factory position)
    size_awg: AwgSize | None  # None = not recorded
    color: ConductorColor
    insulation: Insulation = "THHN"
    material: ConductorMaterial = "Cu"
    # True when this EGC is a metal raceway (EMT) serving as the equipment
    # grounding conductor rather than a wire -- NEC 250.118(A)(4).
    raceway: bool = False
    # NEC 200.7(C)(1) / 250.119: a conductor re-marked at every termination to
    # serve a role other than its factory colour. None = used as its colour says.
    reidentified_as: ConductorRole | None = None
    # a marking band at each end: the re-identification colour, or (EMT) a plain
    # identification mark telling apart two conductors of one colour
    tape: ConductorColor | None = None
    stranding: Stranding | None = None  # 310.3(C); None = not recorded

    def model_post_init(self, _context: Any, /) -> None:
        _ = self.net  # create the net now, inside the circuit context

    @property
    def handle(self) -> str:
        return f"{self.cable_id}.{self.name}"  # same `owner.part` form as a device terminal

    @property
    def played_role(self) -> ConductorRole:
        """The role this conductor actually serves -- its re-identified role if
        it carries tape, else its factory role.
        """
        return self.reidentified_as or self.role

    @cached_property
    def net(self) -> Net:
        return Net(self.handle)

    def cable_cell(self, *, gauge: bool = False) -> str:
        """This conductor as one coloured row of its cable's diagram node,
        reachable as ``"<cable id>":<name>``. The cell takes the conductor's
        insulation colour (bare copper and a raceway draw as EGC green); a taped
        conductor gains a tape band at each end and, if re-identified, is
        labelled by the role it now serves. ``gauge`` adds its ``size_awg`` in a
        column of its own -- for wires pulled into a raceway, which can differ.
        """
        bg, fg, extra = COLOUR_CELL[self.color]
        label = "EGC · raceway" if self.raceway else (self.reidentified_as or self.name)
        band = f'<td bgcolor="{self.tape}" width="8"> </td>' if self.tape is not None else ""
        size = (
            f'<td align="right"><font color="{fg}" point-size="7"> {self.size_awg or "?"} AWG </font></td>'
            if gauge and not self.raceway
            else ""
        )
        if not band and not size:
            return (
                f'<tr><td port="{self.name}"{extra} bgcolor="{bg}">'
                f'<font color="{fg}">{html_esc(label)}</font></td></tr>'
            )
        return (
            f'<tr><td port="{self.name}"{extra} bgcolor="{bg}">'
            f'<table border="0" cellborder="0" cellspacing="0" cellpadding="0"><tr>'
            f'{band}<td align="left"><font color="{fg}"> {html_esc(label)} </font></td>{size}{band}'
            f"</tr></table></td></tr>"
        )

    def schedule_row(self, *, method: str, path: str, buses: list[tuple[Net, str]]) -> str:
        """One CONDUCTOR SCHEDULE row -- column widths track House.conductor_schedule."""
        landed = next((label for bus, label in buses if self.net.is_attached(bus)), self.handle)
        colour: str = "raceway" if self.raceway else self.color
        if self.tape is not None:
            colour = f"{self.color}/{self.tape}"  # insulation / tape mark
        return (
            f"  {self.handle:<22} {method:<14} {self.played_role:<10} {self.size_awg or '?':<4} "
            f"{colour:<11} {path:<26} {landed}"
        )
