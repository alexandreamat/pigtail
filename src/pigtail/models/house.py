"""The whole house: the parsed spec plus assembly.

Nets/parts live on the models that own them (a conductor's net, a panelboard's
bus nets, a device's part) and are created at construction. ``from_yaml`` opens
the circuit context first, then validates -- so every model's ``model_post_init``
lands its SKiDL objects in this house's circuit -- then wires the connections.

Wiring performs referential checks only -- it never judges compliance. Once
wired, each branch circuit is bound to the runs and devices traced onto it
(:mod:`pigtail.trace`).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from functools import cached_property
from pathlib import Path

import yaml
from pydantic import PrivateAttr
from skidl import Circuit, Net, Pin

from pigtail import raceway
from pigtail.bom import bom as nec_bom
from pigtail.models._base import BaseModel, BuildError, join, require
from pigtail.models.box import Box
from pigtail.models.cable import Cable
from pigtail.models.circuit import BranchCircuit
from pigtail.models.device import Device
from pigtail.models.panelboard import Panelboard
from pigtail.nec import check as nec_check
from pigtail.trace import Trace

logging.getLogger("skidl").setLevel(logging.ERROR)  # skidl is chatty on stderr

type SpliceMember = Net | Pin


class Meta(BaseModel):
    """Project identity and the code edition its NEC references are read against."""

    project: str
    code_edition: str = "NEC-2023"  # the edition the checks follow; a local adoption may amend it


class House(BaseModel):
    """The premises wiring system (NEC Art. 100) as one document: the physical
    boxes, and the panelboards -- each with its breakers and the tree of runs
    leaving it.
    """

    meta: Meta
    boxes: list[Box] = []
    panelboards: list[Panelboard] = []

    _circuit: Circuit = PrivateAttr()  # set by from_yaml

    # --- loading ---------------------------------------------------------
    @classmethod
    def from_dict(cls, data: object) -> House:
        """Validate a plain mapping and assemble the circuit.

        The circuit context is opened *before* validation so every model's
        ``model_post_init`` creates its nets/parts in it.
        """
        with Circuit() as circuit:
            house = cls.model_validate(data)
            house._circuit = circuit
            house._wire()
        for pb in house.panelboards:
            for bc in pb.branch_circuits:
                bc.bind(
                    [
                        c
                        for c in house.cables()
                        if any(x is bc for x in house.trace.run_circuits(c))
                    ],
                    [d for d in house.devices() if house.trace.device_circuit(d) is bc],
                )
        return house

    @classmethod
    def from_yaml(cls, path: Path) -> House:
        """Parse a YAML file and assemble it (see :meth:`from_dict`)."""
        return cls.from_dict(yaml.safe_load(path.read_text()))

    # --- tree lookups --------------------------------------------------
    def box(self, box_id: str) -> Box:
        for b in self.boxes:
            if b.id == box_id:
                return b
        raise BuildError(f"unknown box {box_id!r}")

    def panelboard(self, panelboard_id: str) -> Panelboard:
        for pb in self.panelboards:
            if pb.id == panelboard_id:
                return pb
        raise BuildError(f"unknown panelboard {panelboard_id!r}")

    def branch_circuit(self, circuit_id: str) -> BranchCircuit:
        for pb in self.panelboards:
            for bc in pb.branch_circuits:
                if bc.id == circuit_id:
                    return bc
        raise BuildError(f"unknown circuit {circuit_id!r}")

    def cables(self) -> Iterator[Cable]:
        def walk(cables: list[Cable]) -> Iterator[Cable]:
            for c in cables:
                yield c
                yield from walk(c.cables)

        for pb in self.panelboards:
            yield from walk(pb.cables)

    def cable(self, cable_id: str) -> Cable:
        for c in self.cables():
            if c.id == cable_id:
                return c
        raise BuildError(f"unknown cable {cable_id!r}")

    def devices(self) -> Iterator[Device]:
        for c in self.cables():
            yield from c.devices

    def device(self, device_id: str) -> Device:
        for d in self.devices():
            if d.id == device_id:
                return d
        raise BuildError(f"unknown device {device_id!r}")

    def built_circuit(self) -> Circuit:
        return require(lambda: self._circuit, "house circuit")

    @cached_property
    def trace(self) -> Trace:
        """The circuits traced from the wiring (see :mod:`pigtail.trace`)."""
        return Trace(self)

    def path(self, cable: Cable) -> list[Cable]:
        """The runs from the panelboard down to ``cable``, in order."""
        landing = {c.to: c for c in self.cables() if c.to is not None}
        out = [cable]
        while out[0].upstream in landing:
            out.insert(0, landing[out[0].upstream])
        return out

    # --- text reports -------------------------------------------------
    def net_summary(self) -> str:
        """The electrical nets and the part terminals on each."""
        rows: list[str] = []
        for net in sorted(self.built_circuit().get_nets(), key=lambda n: n.name):
            terminals = sorted(f"{pin.part.ref}.{pin.name}" for pin in net.pins)
            if terminals:
                rows.append(f"  {net.name:<16} {', '.join(terminals)}")
        return "NETS (electrical)\n" + "\n".join(rows)

    def panel_schedule(self) -> str:
        """One row per branch circuit: rating, leg, AFCI/GFCI, wiring method(s),
        and the device ids it feeds.
        """
        header = (
            f"  {'circuit':<10} {'rating':<9} {'leg':<6} {'AFCI':<5} {'GFCI':<5} "
            f"{'wiring':<20} feeds\n"
            f"  {'-' * 10} {'-' * 9} {'-' * 6} {'-' * 5} {'-' * 5} {'-' * 20} {'-' * 30}"
        )
        out: list[str] = ["PANEL SCHEDULE", header]
        for pb in self.panelboards:
            main = f"{pb.main_breaker.ampere_rating} A" if pb.main_breaker else "MLO"
            out.append(f"  PANEL {pb.id}  (main {main}, service={pb.service})")
            for bc in pb.branch_circuits:
                cb = bc.circuit_breaker
                leg = "L1+L2" if cb.poles == 2 else cb.leg
                wiring = "+".join(sorted({c.type for c in bc.all_cables()})) or "-"
                feeds = ", ".join(d.id for d in bc.devices()) or "-"
                out.append(
                    f"  {bc.id:<10} {f'{cb.ampere_rating} A/{cb.poles}P':<9} {leg:<6} "
                    f"{('yes' if cb.afci else '-'):<5} {('yes' if cb.gfci else '-'):<5} "
                    f"{wiring:<20} {feeds}"
                )
        return "\n".join(out)

    def conductor_schedule(self) -> str:
        """Every physical conductor, one row (rendered by the conductor itself):
        run, method, role, size, colour, path, and the net it lands on -- named
        after a panelboard busbar when it is bonded to one.
        """
        buses = [bn for pb in self.panelboards for bn in pb.bus_nets()]
        header = (
            f"  {'handle':<22} {'method':<14} {'role':<10} {'AWG':<4} {'colour':<11} "
            f"{'path':<26} net\n"
            f"  {'-' * 22} {'-' * 14} {'-' * 10} {'-' * 4} {'-' * 11} {'-' * 26} {'-' * 14}"
        )
        rows = [row for cable in self.cables() for row in cable.schedule_rows(buses)]
        return "CONDUCTOR SCHEDULE (physical)\n" + "\n".join([header, *rows])

    def raceway_schedule(self) -> str:
        """Every EMT run: trade size, wires, fill against its Chapter 9 limit,
        current-carrying conductors and their 310.15(C)(1) adjustment, and the
        energized conductor with the least margin over its breaker after
        derating and terminal limits.
        """
        header = (
            f"  {'run':<16} {'EMT':<6} {'wires':>5} {'fill':>5} {'limit':>5} {'CCC':>4} "
            f"{'adjust':>6}  tightest conductor\n"
            f"  {'-' * 16} {'-' * 6} {'-' * 5} {'-' * 5} {'-' * 5} {'-' * 4} {'-' * 6}  {'-' * 36}"
        )
        rows: list[str] = []
        for cable in raceway.raceways(self):
            filled = raceway.fill(cable)
            count = raceway.current_carrying(self, cable)
            factor = raceway.adjustment(count)
            margins = []
            for w in cable.wires:
                bc = raceway.feeder(self, w)
                if bc is not None and w.size_awg is not None:
                    amps = raceway.ampacity(w, bc, factor=factor, ambient_c=cable.ambient_c)
                    margins.append((amps, bc, w))
            tight = "-"
            if margins:
                amps, bc, w = min(margins, key=lambda m: m[0] - m[1].circuit_breaker.ampere_rating)
                tight = (
                    f"{w.handle} {w.size_awg} AWG: {amps:g} A on "
                    f"{bc.id} {bc.circuit_breaker.ampere_rating} A"
                )
            wires = sum(1 for w in cable.wires if not w.raceway)
            size = f'{cable.trade_size}"'
            used, allowed = (f"{f:.0%}" for f in filled) if filled else ("?", "?")
            rows.append(
                f"  {cable.id:<16} {size:<6} {wires:>5} {used:>5} "
                f"{allowed:>5} {count:>4} {factor:>6.0%}  {tight}"
            )
        return "RACEWAYS (EMT)\n" + "\n".join([header, *rows])

    def bom(self) -> str:
        """A text bill of materials (see :mod:`pigtail.bom`)."""
        return nec_bom(self)

    # --- NEC checks -------------------------------------------------
    def check(self) -> None:
        """Run the NEC checks the model supports and raise a ``nec.NECViolation``
        warning per violation. Returns nothing and never raises -- an as-built
        house may hold violations; read the warnings and fix the YAML (or accept
        them). (Named ``check``, not ``validate`` -- pydantic owns ``validate``.)
        """
        nec_check(self)

    # --- wiring (nets/parts already exist; just connect them) ----------
    def _wire(self) -> None:
        """The panelboard clips its breakers onto the buses; House walks each
        run leaving it, making the splices in every box it reaches; then the
        panelboard's own splices land wires on breaker terminals and busbars.
        """
        for pb in self.panelboards:
            pb.wire_circuits()
            for run in pb.cables:
                run.upstream = pb.id
                self._walk_downstream(run)
            for splice in pb.splices:
                join(*(self._resolve(pb.id, member, panel=pb) for member in splice.join))

    def _walk_downstream(self, cable: Cable) -> None:
        """The box this cable lands in: referential-check it, register onward
        cables, then make its splices.
        """
        if cable.to is None:  # far end not traced: nothing beyond it
            return
        self.box(cable.to)  # referential check
        for onward in cable.cables:
            onward.upstream = cable.to
            self._walk_downstream(onward)
        for splice in cable.splices:
            join(*(self._resolve(cable.to, member) for member in splice.join))

    def _resolve(self, where: str, member: str, *, panel: Panelboard | None = None) -> SpliceMember:
        """``owner.part`` -> a cable conductor's net or a device pin; in a
        panelboard also a breaker's LOAD terminal or a busbar.
        """
        owner, part = member.split(".", 1)
        if panel is not None:
            bc = next((b for b in panel.branch_circuits if b.id == owner), None)
            if bc is not None:
                if not part.startswith("LOAD") or part not in bc.circuit_breaker.terminals:
                    raise BuildError(
                        f"splice in {where}: breaker {owner} has no LOAD terminal {part!r}"
                    )
                pin: Pin = bc.breaker_part[part]
                return pin
            if owner == panel.id:
                bus = panel.bus_net(part)
                if bus is None:
                    raise BuildError(
                        f"splice in {where}: a wire lands on NEUTRAL or EGC, not {part!r}"
                    )
                return bus
        try:
            cable = self.cable(owner)
        except BuildError:
            cable = None
        if cable is not None:
            try:
                return cable.wire(part).net
            except KeyError:
                raise BuildError(f"splice in {where}: {owner} has no {part!r} conductor") from None
        try:
            pins = self.device(owner).part
        except BuildError:
            raise BuildError(f"splice in {where}: unknown reference {owner!r}") from None
        try:
            return pins[part]
        except Exception as exc:
            raise BuildError(f"splice in {where}: {owner} has no terminal {part!r}") from exc
