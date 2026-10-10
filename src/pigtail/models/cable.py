"""Cables, the conductors they carry, and in-box splices."""

from __future__ import annotations

import re
from functools import cached_property
from typing import Any

from pydantic import Field, PrivateAttr, field_validator, model_validator
from skidl import Net

from pigtail.models._base import BaseModel, BuildError, require
from pigtail.models._dot import html_esc
from pigtail.models.conductor import Conductor
from pigtail.models.device import Device
from pigtail.models.types import (
    AwgSize,
    ConductorColor,
    ConductorCount,
    ConductorRole,
    EmtTradeSize,
    Insulation,
    Stranding,
    WiringMethod,
)

_MAKEUP_FT = 1.0  # NEC 300.14: 6 in. of free conductor at each end of a run

# a splice member is  "cableId.conductor"  or  "deviceId.TERMINAL"  -- one form
_SPLICE_MEMBER = re.compile(r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_]+$")
# NEC 200.7 / 250.119: a re-identification mark may not be white, gray, or green
_UNLAWFUL_MARK = frozenset({"white", "gray", "green", "bare"})
# an EMT run's raceway is its EGC, always addressed ``<cable>.egc``
_RACEWAY = "egc"


def _lawful_mark(tape: str) -> str:
    if tape in _UNLAWFUL_MARK:
        raise ValueError(
            f"tape {tape!r} is unlawful (NEC 200.7 / 250.119): "
            "a marking must not be white, gray, or green"
        )
    return tape


class Reidentification(BaseModel):
    """NEC 200.7(C)(1) / 250.119: a conductor of a cable assembly re-marked at
    every termination (tape, paint) to serve a role other than its factory
    colour -- e.g. the white conductor of NM-B /2 used as the second ungrounded
    conductor of a 240 V circuit. The mark must not be white, gray, or green.
    """

    conductor: ConductorRole  # the factory position being re-marked
    plays: ConductorRole  # the role it actually serves
    tape: ConductorColor  # the marking colour

    @field_validator("tape")
    @classmethod
    def _lawful(cls, v: str) -> str:
        return _lawful_mark(v)


def _awg(size: int | None) -> str:
    """A conductor size for a label: "?" where it is not recorded."""
    return "?" if size is None else str(size)


class PulledConductor(BaseModel):
    """One insulated conductor pulled into a raceway (NEC 300.3, Art. 310). In
    EMT each wire is pulled on its own, so a run can carry any mix of colours
    and roles -- two red switch legs, a red hot -- and is described wire by
    wire. ``name`` addresses it in splices (``<cable>.<name>``); ``tape`` is an
    identification band at each end, e.g. blue on one of two red switch legs.
    A switch leg is an ``ungrounded`` conductor. The raceway is the run's EGC
    and is not listed: it is added as ``<cable>.egc``. Which circuit a wire is
    on is not written: it follows from what the wire connects to
    (:mod:`pigtail.trace`).
    """

    name: str = Field(pattern=r"^[A-Za-z0-9_]+$")
    role: ConductorRole
    color: ConductorColor
    tape: ConductorColor | None = None
    stranding: Stranding | None = None  # 310.3(C); None = not recorded
    size_awg: AwgSize | None = None  # this wire's size where it differs from the run's
    insulation: Insulation = "THHN"  # its temperature rating comes from Table 310.4(1)

    @field_validator("name")
    @classmethod
    def _not_the_raceway(cls, v: str) -> str:
        if v == _RACEWAY:
            raise ValueError(
                f"{_RACEWAY!r} is the raceway itself; give a pulled wire EGC another name"
            )
        return v

    @field_validator("tape")
    @classmethod
    def _lawful(cls, v: str | None) -> str | None:
        return None if v is None else _lawful_mark(v)


class Splice(BaseModel):
    """Conductors spliced or joined at one point (NEC 110.14(B)), made inside a
    box or fitting (300.15). Members are ``cableId.conductor`` or
    ``deviceId.TERMINAL``. Two ``Splice`` entries that share a member describe
    the same physical wire nut -- the diagram merges them (``_dot.wire_nuts``).
    A single member is a conductor capped on its own, e.g. a neutral brought to
    a switch box for 404.2(C) and not used there. ``through`` marks one wire
    pulled through the box without a splice -- the incoming and outgoing run's
    conductor are the same wire, counted once for box fill (314.16(B)(1)).
    """

    join: list[str] = Field(min_length=1)
    through: bool = False

    @field_validator("join")
    @classmethod
    def _well_formed(cls, v: list[str]) -> list[str]:
        bad = [m for m in v if not _SPLICE_MEMBER.match(m)]
        if bad:
            raise ValueError(
                f"malformed splice member(s) {bad}; expected 'cableId.conductor' or 'deviceId.TERMINAL'"
            )
        return v

    @model_validator(mode="after")
    def _through_is_one_wire(self) -> Splice:
        if self.through and len(self.join) != 2:
            raise ValueError(f"a through wire joins exactly two run conductors, not {self.join}")
        return self


class Cable(BaseModel):
    """One physical run -- a cable, or a tube and the wires pulled into it --
    from the box (or panelboard) it hangs under in the YAML tree to the box
    ``to``. A run belongs to no circuit: it carries whatever wires it carries,
    of one circuit or several. ``type`` selects the method:

    * ``NM-B``          -- Type NM cable (NEC 334.2): insulated conductors plus a
      wire equipment grounding conductor in a nonmetallic sheath.
    * ``knob_and_tube`` -- concealed knob-and-tube (NEC Art. 394): two loose
      conductors, ungrounded and grounded, with NO equipment grounding
      conductor. Permitted only as an extension of an existing installation
      (394.10); this models the as-built condition.
    * ``EMT``           -- electrical metallic tubing (NEC Art. 358): the
      conductors are pulled into a steel raceway, and the raceway itself is the
      equipment grounding conductor (250.118(A)(4)).

    ``conductors`` is the insulated count (the "/2" or "/3"); ``wires`` are the
    conductor objects it expands to, plus an EGC unless the method is K&T. An
    EMT run may instead list every wire pulled into it (``pulled``) -- then
    ``conductors`` is left out, and the raceway is added as the EGC.

    ``devices``, ``splices`` and ``cables`` are the contents of the box ``to``:
    the devices mounted in it, its splices, and the runs leaving it. A run
    without ``to`` is one whose far end is not traced yet; it has none.
    """

    id: str
    type: WiringMethod
    size_awg: AwgSize | None = None  # None = not recorded
    conductors: ConductorCount | None = None  # None when ``pulled`` lists them
    pulled: list[PulledConductor] = []  # EMT: each wire pulled in, by name
    to: str | None = None  # the box this run lands in; None = far end not traced yet
    trade_size: EmtTradeSize | None = None  # EMT only -- the tubing you buy
    ambient_c: float = 30.0  # EMT only: ambient around the tube, 310.15(B); 30 C = no correction
    bends_deg: float | None = Field(
        default=None, ge=0
    )  # EMT only: total bends between pull points, 358.26
    length_ft: float | None = Field(default=None, gt=0)  # routed run distance; None = not measured
    devices: list[Device] = []
    splices: list[Splice] = []
    reidentify: list[Reidentification] = []  # NEC 200.7(C)(1) / 250.119
    cables: list[Cable] = []  # runs continuing from the landing box

    _upstream: str = PrivateAttr()  # set by House during wiring

    def model_post_init(self, _context: Any, /) -> None:
        _ = self.wires

    @model_validator(mode="after")
    def _trade_size_matches_method(self) -> Cable:
        if self.type == "EMT" and self.trade_size is None:
            raise ValueError(f"cable {self.id!r}: an EMT run needs a trade_size")
        if self.type != "EMT" and self.trade_size is not None:
            raise ValueError(f"cable {self.id!r}: trade_size applies only to EMT")
        return self

    @model_validator(mode="after")
    def _untraced_end_is_empty(self) -> Cable:
        if self.to is None and (self.devices or self.splices or self.cables):
            raise ValueError(
                f"cable {self.id!r}: devices, splices and onward cables are in the box it lands "
                "in -- give its `to`"
            )
        return self

    @model_validator(mode="after")
    def _conductors_described_once(self) -> Cable:
        if self.pulled:
            if self.type != "EMT":
                raise ValueError(f"cable {self.id!r}: pulled applies only to EMT")
            if self.conductors is not None:
                raise ValueError(f"cable {self.id!r}: give conductors or pulled, not both")
            if self.reidentify:
                raise ValueError(
                    f"cable {self.id!r}: a pulled wire carries its own tape; "
                    "reidentify is for cable assemblies"
                )
            names = [p.name for p in self.pulled]
            if len(set(names)) != len(names):
                raise ValueError(f"cable {self.id!r}: pulled wire names must be unique")
        elif self.conductors is None:
            raise ValueError(f"cable {self.id!r}: needs conductors (or, for EMT, pulled)")
        return self

    @property
    def bom_length_ft(self) -> float | None:
        """Length to buy for this run: the routed distance plus 6 in. of makeup
        at each end (NEC 300.14). ``None`` until ``length_ft`` is measured. For
        EMT this is the per-conductor pull length; the tubing itself is
        ``length_ft`` (no makeup).
        """
        return None if self.length_ft is None else self.length_ft + _MAKEUP_FT

    @property
    def has_egc(self) -> bool:
        """Whether this run carries an equipment grounding path at all -- a wire
        for Type NM, the raceway for EMT, nothing for knob-and-tube.
        """
        return self.type != "knob_and_tube"

    @property
    def spec_label(self) -> str:
        """Short method + size label for diagrams and schedules."""
        if self.type == "knob_and_tube":
            return f"K&T {_awg(self.size_awg)}" + ("/3" if self.conductors == 3 else "")
        if self.pulled:
            insulated = [w.size_awg for w in self.wires if w.role != "egc"]
            ground = " w/G" if any(w.role == "egc" and not w.raceway for w in self.wires) else ""
            if len(set(insulated)) == 1:
                return f"{self.type} {_awg(insulated[0])}/{len(insulated)}{ground}"
            sizes = " + ".join(
                f"{insulated.count(a)}×{_awg(a)}"
                for a in sorted(set(insulated), key=lambda a: (a is None, -(a or 0)))
            )
            return f"{self.type} {sizes}{ground}"  # mixed sizes, e.g. EMT 2×14 + 1×12
        return f"{self.type} {_awg(self.size_awg)}/{self.conductors}"

    @property
    def diagram_label(self) -> str:
        """The diagram header after the run's id: for a raceway its method and
        trade size (each wire shows its own gauge), for a cable assembly its
        spec; then the routed length, when measured.
        """
        text = f'{self.type} {self.trade_size}"' if self.type == "EMT" else self.spec_label
        return text if self.length_ft is None else f"{text} · {self.length_ft:g} ft"

    @cached_property
    def wires(self) -> list[Conductor]:
        if self.pulled:
            return [
                *(
                    Conductor(
                        cable_id=self.id,
                        name=p.name,
                        role=p.role,
                        size_awg=p.size_awg or self.size_awg,
                        insulation=p.insulation,
                        color=p.color,
                        tape=p.tape,
                        stranding=p.stranding,
                    )
                    for p in self.pulled
                ),
                Conductor(
                    cable_id=self.id,
                    name=_RACEWAY,
                    role="egc",
                    size_awg=self.size_awg,
                    color="bare",
                    insulation="bare",
                    raceway=True,
                ),
            ]
        insul: Insulation = "rubber" if self.type == "knob_and_tube" else "THHN"
        remark = {r.conductor: r for r in self.reidentify}

        def conductor(role: ConductorRole, color: ConductorColor, **kw: Any) -> Conductor:
            r = remark.get(role)
            return Conductor(
                cable_id=self.id,
                name=role,
                role=role,
                size_awg=self.size_awg,
                color=color,
                reidentified_as=r.plays if r else None,
                tape=r.tape if r else None,
                **kw,
            )

        wires = [conductor("ungrounded", "black", insulation=insul)]
        if self.conductors == 3:
            wires.append(conductor("traveler", "red", insulation=insul))
        wires.append(conductor("neutral", "white", insulation=insul))
        if self.has_egc:
            wires.append(conductor("egc", "bare", insulation="bare", raceway=self.type == "EMT"))

        unknown = remark.keys() - {w.role for w in wires}
        if unknown:
            raise BuildError(f"cable {self.id!r}: reidentify names absent conductor(s) {unknown}")
        return wires

    def wire(self, name: str) -> Conductor:
        for w in self.wires:
            if w.name == name:
                return w
        raise KeyError(f"cable {self.id!r} has no {name!r} conductor")

    @property
    def egcs(self) -> list[Conductor]:
        """Every equipment grounding path in the run: the wire EGC of a cable
        assembly, the raceway of EMT (plus any wire EGC pulled into it), none
        for knob-and-tube.
        """
        return [w for w in self.wires if w.role == "egc"]

    def schedule_rows(self, buses: list[tuple[Net, str]]) -> list[str]:
        """One CONDUCTOR SCHEDULE row per conductor (each rendered by itself)."""
        path = f"{self.upstream} -> {self.to or '(not traced)'}"
        return [w.schedule_row(method=self.spec_label, path=path, buses=buses) for w in self.wires]

    def diagram_node(self) -> str:
        """This cable as one diagram node: a grey header (``id`` + method/size)
        over one coloured row per conductor, each reachable as ``"<id>":<role>``.
        """
        rows = "".join(
            [
                f'<tr><td align="left" cellpadding="4">'
                f"<b>{html_esc(self.id)}</b>  {html_esc(self.diagram_label)}</td></tr>",
                *(w.cable_cell(gauge=self.type == "EMT") for w in self.wires),
            ]
        )
        return (
            f'  "{self.id}" [shape=plaintext label=<'
            f'<table border="1" cellborder="0" cellspacing="2" cellpadding="3" bgcolor="#ededed">'
            f"{rows}</table>>];"
        )

    @property
    def upstream(self) -> str:
        return require(lambda: self._upstream, f"cable {self.id} upstream")

    @upstream.setter
    def upstream(self, ref: str) -> None:
        self._upstream = ref


Cable.model_rebuild()
