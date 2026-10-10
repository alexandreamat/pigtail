"""Bill of materials -- what to buy for an assembled house.

``bom(house)`` is a text report. Counts are exact where the model carries the
data (devices, boxes, breakers); conductor footage needs ``Cable.length_ft`` and
is shown with ``~`` (routed distance + 6 in. makeup per end, NEC 300.14);
connector / plate / tape lines are simple per-run / per-device estimates.

NM-B and knob-and-tube are bought as an assembly (so many feet of "NM-B 12/2").
EMT is bought as tubing *plus* the conductors pulled through it, so an EMT run
produces a tubing line and one THHN line per AWG.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from pigtail.fill import required_cu_in, suggest
from pigtail.models._dot import wire_nuts
from pigtail.models.cable import Cable
from pigtail.models.device import Device, Luminaire, Receptacle, SnapSwitch

if TYPE_CHECKING:
    from pigtail.models.house import House


def bom(house: House) -> str:
    cables = list(house.cables())
    devices = list(house.devices())
    blocks = [
        f"BILL OF MATERIALS -- {house.meta.project}",
        _conductor(cables),
        _boxes(house),
        _devices(devices),
        _overcurrent(house),
        _consumables(house, cables, devices),
    ]
    return "\n\n".join(blocks)


def _ft(feet: float, unmeasured: int) -> str:
    have = f"~{feet:>6.0f} ft" if feet else "     -- ft"
    return have + (f"   ({unmeasured} run(s) unmeasured)" if unmeasured else "")


def _conductor(cables: list[Cable]) -> str:
    assembly: dict[str, list[float]] = {}  # label -> [runs, feet, unmeasured]
    tubing: dict[str, list[float]] = {}
    thhn: dict[int | None, list[float]] = {}  # awg (None: not recorded) -> [feet, unmeasured]

    for c in cables:
        buy_len = c.bom_length_ft or 0.0
        if c.type == "EMT":
            t = tubing.setdefault(f'EMT {c.trade_size}"', [0, 0.0, 0])
            t[0] += 1
            t[1] += c.length_ft or 0.0
            t[2] += c.length_ft is None
            for w in c.wires:  # each wire at its own size
                if w.raceway:
                    continue
                row = thhn.setdefault(w.size_awg, [0.0, 0])
                row[0] += buy_len
                row[1] += c.length_ft is None
        else:
            a = assembly.setdefault(c.spec_label, [0, 0.0, 0])
            a[0] += 1
            a[1] += buy_len
            a[2] += c.length_ft is None

    out = ["CABLE / CONDUCTOR"]
    if assembly:
        out.append("  cable (buy as assembly)")
        for label, (runs, feet, un) in sorted(assembly.items()):
            out.append(f"    {label:<16} {int(runs):>3} run(s)  {_ft(feet, int(un))}")
    if tubing:
        out.append("  conduit (buy tubing + conductor separately)")
        for label, (runs, feet, un) in sorted(tubing.items()):
            out.append(f"    {label:<16} {int(runs):>3} run(s)  {_ft(feet, int(un))}")
        for awg, (feet, un) in sorted(thhn.items(), key=lambda kv: (kv[0] is None, kv[0] or 0)):
            size = "size ?" if awg is None else f"{awg} AWG"
            out.append(f"      {size} THHN{'':<6} {'':<9} {_ft(feet, int(un))}")
    return "\n".join(out)


def _boxes(house: House) -> str:
    kinds: Counter[str] = Counter(
        f"{b.type} - {b.material} - "
        + (
            "box volume not recorded"
            if b.box_volume_cu_in is None
            else f"{b.box_volume_cu_in:g} in.³"
        )
        for b in house.boxes
    )
    out = ["BOXES", *(f"  {k:<34} {n:>3}" for k, n in sorted(kinds.items()))]

    short = []
    ok = 0
    unknown = 0
    uncalculated = 0
    for b in house.boxes:
        need = required_cu_in(house, b.id)
        if need is None:
            uncalculated += 1
            continue
        if need == 0:
            continue
        volume = b.box_volume_cu_in
        if volume is None:
            unknown += 1
        elif need > volume + 1e-6:
            short.append((b.id, volume, need))
        else:
            ok += 1
    unrecorded = f", {unknown} box volume not recorded" if unknown else ""
    if uncalculated:
        unrecorded += f", {uncalculated} box fill not calculated (conductor size not recorded)"
    if short:
        out.append("")
        out.append(
            f"  box volume vs box fill (314.16) -- {len(short)} short, {ok} adequate{unrecorded}"
        )
        out.append(f"  {'box':<20} {'box volume':>10} {'box fill':>10}   suggest (Table 314.16(A))")
        for box_id, have, need in sorted(short, key=lambda r: r[1] - r[2]):
            out.append(f"  {box_id:<20} {have:>10.1f} {need:>10.2f}   {suggest(need) or '-'}")
    else:
        out.append(f"  box volume vs box fill (314.16) -- {ok} adequate{unrecorded}")
    return "\n".join(out)


def _devices(devices: list[Device]) -> str:
    recep: Counter[str] = Counter()
    switch: Counter[str] = Counter()
    lum_n = 0
    lum_va = 0.0
    lum_unrecorded = 0
    appliances = 0
    for d in devices:
        if isinstance(d, Receptacle):
            tags: list[str] = [d.nema or "NEMA not recorded"]
            tags += [t for t, on in (("GFCI", d.gfci), ("no-ground", not d.grounding)) if on]
            recep[" ".join(tags)] += 1
        elif isinstance(d, SnapSwitch):
            switch[d.function] += 1
        elif isinstance(d, Luminaire):
            lum_n += 1
            lum_va += d.load_va or 0.0
            lum_unrecorded += d.load_va is None
        else:
            appliances += 1  # hardwired equipment: bought with the appliance, listed for the count

    out = ["DEVICES"]
    for k, n in sorted(recep.items()):
        out.append(f"  receptacle {k:<24} {n:>3}")
    for k, n in sorted(switch.items()):
        out.append(f"  switch {k:<28} {n:>3}")
    if lum_n:
        unrecorded = f", {lum_unrecorded} not recorded" if lum_unrecorded else ""
        out.append(f"  luminaire {'':<25} {lum_n:>3}   ({lum_va:g} VA total{unrecorded})")
    if appliances:
        out.append(f"  appliance (hardwired) {'':<13} {appliances:>3}")
    return "\n".join(out)


def _overcurrent(house: House) -> str:
    out = ["OVERCURRENT"]
    for pb in house.panelboards:
        if pb.main_breaker:
            out.append(f"  main breaker {pb.main_breaker.ampere_rating} A  (panel {pb.id})")
        breakers: Counter[str] = Counter()
        for bc in pb.branch_circuits:
            cb = bc.circuit_breaker
            tags = [f"{cb.poles}-pole {cb.ampere_rating} A"]
            tags += [t for t, on in (("AFCI", cb.afci), ("GFCI", cb.gfci)) if on]
            breakers[" ".join(tags)] += 1
        for k, n in sorted(breakers.items()):
            out.append(f"  breaker {k:<24} {n:>3}")
    return "\n".join(out)


def _consumables(house: House, cables: list[Cable], devices: list[Device]) -> str:
    nm_connectors = 2 * sum(1 for c in cables if c.type == "NM-B")
    emt_connectors = 2 * sum(1 for c in cables if c.type == "EMT")
    nuts = sum(
        len(wire_nuts([sp.join for c in cables if c.to == b.id for sp in c.splices]))
        for b in house.boxes
    )
    plates = sum(1 for d in devices if isinstance(d, Receptacle | SnapSwitch))
    tape: Counter[str] = Counter(r.tape for c in cables for r in c.reidentify)

    out = ["CONNECTORS / CONSUMABLES (estimated)"]
    if nm_connectors:
        out.append(f"  NM cable connectors {'':<14} {nm_connectors:>3}   (2 per run)")
    if emt_connectors:
        out.append(f"  EMT connectors {'':<19} {emt_connectors:>3}   (2 per run)")
    out.append(f"  wire connectors (nuts) {'':<11} {nuts:>3}")
    out.append(f"  device / switch plates {'':<11} {plates:>3}")
    for colour, n in sorted(tape.items()):
        out.append(f"  {colour} re-identification tape {'':<6} {n:>3} location(s)")
    return "\n".join(out)
