"""Which branch circuit each conductor, run and device is on -- worked out from
the wiring alone. The YAML says only what connects to what; nothing names a
wire's circuit.

* A conductor energized from a breaker is on that breaker's circuit: the
  splices it is joined through reach the breaker's LOAD terminal, directly or
  through a switch (its LOAD to its LINE).
* A neutral is on the circuits of the loads it returns: the devices whose
  NEUTRAL terminal it reaches going downstream, away from the panelboard. One
  serving two or more circuits is shared -- a multiwire branch circuit. Loads
  beyond a run whose far end is not traced are not known, so neither are
  their circuits: such a neutral is open-ended.
* A device is on the circuit its LINE (LINE1) terminal is energized from.
* A run carries the circuits of its conductors.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pigtail.models._dot import wire_nuts
from pigtail.models.device import SnapSwitch

if TYPE_CHECKING:
    from pigtail.models.cable import Cable
    from pigtail.models.circuit import BranchCircuit
    from pigtail.models.conductor import Conductor
    from pigtail.models.device import Device
    from pigtail.models.house import House


class Trace:
    """The traced circuits of an assembled house (``House.trace``)."""

    def __init__(self, house: House) -> None:
        self._order = [bc for pb in house.panelboards for bc in pb.branch_circuits]
        self._breakers = {bc.id: bc for bc in self._order}
        self._devices: dict[str, Device] = {d.id: d for d in house.devices()}
        self._runs = {c.id: c for c in house.cables()}
        joins = [sp.join for pb in house.panelboards for sp in pb.splices]
        joins += [sp.join for c in house.cables() for sp in c.splices]
        # every splice member -> the members it is joined with (a wire's handle
        # is one member at both of its ends, so this spans the whole wire)
        self._joined: dict[str, list[str]] = {}
        for group in wire_nuts(joins):
            for member in group:
                self._joined[member] = group
        self._fed: dict[str, list[BranchCircuit]] = {}
        self._served: dict[str, tuple[list[BranchCircuit], bool]] = {}

    def fed_by(self, member: str) -> list[BranchCircuit]:
        """The breakers a conductor (its handle) or a terminal is energized from
        -- normally one; more is a fault.
        """
        if member not in self._fed:
            found: set[str] = set()
            seen: set[str] = set()
            todo = [member]
            while todo:
                m = todo.pop()
                if m in seen:
                    continue
                for joined in self._joined.get(m, [m]):
                    seen.add(joined)
                    owner, part = joined.split(".", 1)
                    if owner in self._breakers and part.startswith("LOAD"):
                        found.add(owner)
                    elif isinstance(self._devices.get(owner), SnapSwitch) and part != "EGC":
                        todo.append(f"{owner}.{'LOAD' if part == 'LINE' else 'LINE'}")
            self._fed[member] = [bc for bc in self._order if bc.id in found]
        return self._fed[member]

    def device_circuit(self, device: Device) -> BranchCircuit | None:
        """The circuit a device is on: its LINE (LINE1) terminal's breaker."""
        line = "LINE" if "LINE" in device.terminals else "LINE1"
        fed = self.fed_by(f"{device.id}.{line}")
        return fed[0] if fed else None

    def served(self, wire: Conductor) -> list[BranchCircuit]:
        """The circuits whose loads return on a neutral: the devices whose
        NEUTRAL terminal it reaches through the boxes downstream of it.
        """
        return self._walk(wire)[0]

    def open_ended(self, wire: Conductor) -> bool:
        """Whether a neutral continues into a run whose far end is not traced
        -- it may return loads not in the model.
        """
        return self._walk(wire)[1]

    def _walk(self, wire: Conductor) -> tuple[list[BranchCircuit], bool]:
        if wire.handle not in self._served:
            found: set[str] = set()
            seen: set[str] = set()
            open_end = False
            todo = [(self._runs[wire.cable_id], wire.handle)]
            while todo:
                run, handle = todo.pop()
                if handle in seen:
                    continue
                seen.add(handle)
                open_end |= run.to is None
                for nut in wire_nuts([sp.join for sp in run.splices]):  # the box it lands in
                    if handle not in nut:
                        continue
                    for member in nut:
                        owner, part = member.split(".", 1)
                        device = self._devices.get(owner)
                        onward = self._runs.get(owner)
                        if device is not None and part == "NEUTRAL":
                            bc = self.device_circuit(device)
                            if bc is not None:
                                found.add(bc.id)
                        elif onward is not None and onward.upstream == run.to:
                            todo.append((onward, member))
            self._served[wire.handle] = ([bc for bc in self._order if bc.id in found], open_end)
        return self._served[wire.handle]

    def circuits(self, wire: Conductor) -> list[BranchCircuit]:
        """The circuit(s) a conductor is on: the breaker it is energized from,
        or -- a neutral -- the circuits of the loads it returns. None for an EGC,
        which serves every circuit in its run.
        """
        if wire.role == "egc":
            return []
        fed = self.fed_by(wire.handle)
        if fed or wire.played_role != "neutral":
            return fed
        return self.served(wire)

    def run_circuits(self, run: Cable) -> list[BranchCircuit]:
        """The circuits whose conductors a run carries."""
        found = {bc.id for w in run.wires for bc in self.circuits(w)}
        return [bc for bc in self._order if bc.id in found]
