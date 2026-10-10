"""NEC checks -- a warn-only pass over an assembled house.

``check(house)`` runs every check and raises a ``NECViolation`` warning for each
non-compliance, and an ``NECUnchecked`` warning for each rule it cannot evaluate
because a value it needs is not recorded (a box's volume, a run's length, a
conductor's size). It
returns nothing and never raises an exception -- an as-built house may hold
violations; run this, read the warnings, and fix the YAML (or accept them).

Each check is a generator yielding one message string per violation -- or an
``Unchecked`` string where it lacks the data -- each led by its NEC article. Add
one and list it in ``_CHECKS``. Rules are NEC 2023 (NFPA 70); a jurisdiction may
adopt it with amendments. Checks that would depend on data the model does not
carry (room, mounting height, geometry) are left out rather than guessed.
"""

from __future__ import annotations

import warnings
from collections.abc import Iterator
from typing import TYPE_CHECKING

from pigtail import raceway
from pigtail.fill import required_cu_in, ungauged
from pigtail.models._dot import wire_nuts
from pigtail.models.device import Receptacle, SnapSwitch
from pigtail.nec_tables import (
    CHAPTER_9_TABLE_4,
    SECTION_210_19_A_1_CONTINUOUS,
    SECTION_210_19_A_IN_4,
    SECTION_240_4_D,
    SECTION_310_3_C_STRANDED_FROM_AWG,
    SECTION_314_24_B,
    SECTION_358_26_MAX_BENDS_DEG,
    TABLE_210_21_B_3,
    TABLE_250_122,
)

if TYPE_CHECKING:
    from pigtail.models.cable import Cable
    from pigtail.models.circuit import BranchCircuit
    from pigtail.models.conductor import Conductor
    from pigtail.models.house import House


class NECViolation(UserWarning):
    """An assembled house breaks a Code rule."""


class NECUnchecked(UserWarning):
    """A Code rule the model cannot evaluate: a value it needs is not recorded."""


class Unchecked(str):
    """A check's message for a rule it cannot evaluate (raised as ``NECUnchecked``)."""


def check(house: House) -> None:
    """Raise a ``NECViolation`` warning for every violation found and an
    ``NECUnchecked`` warning for every rule left unchecked. Returns nothing.
    """
    for check_fn in _CHECKS:
        for message in check_fn(house):
            category = NECUnchecked if isinstance(message, Unchecked) else NECViolation
            warnings.warn(str(message), category, stacklevel=2)


# --- checks -------------------------------------------------------------


def _limit(conductor: Conductor, bc: BranchCircuit, amps: float, binding: str) -> str | None:
    """A finding if ``bc``'s breaker exceeds what a conductor of ampacity
    ``amps`` may have (240.4(B) rounding, 240.4(D) cap); ``binding`` names the
    rule that set ``amps``. None when it complies.
    """
    rating = bc.circuit_breaker.ampere_rating
    if rating <= raceway.largest_breaker(conductor, bc, amps):
        return None
    awg = conductor.size_awg
    cap = None if awg is None else SECTION_240_4_D.get(conductor.material, {}).get(awg)
    return "240.4(D)" if cap is not None and cap < rating and cap <= amps else binding


def _unsized(article: str, cable: Cable, conductor: Conductor, bc: BranchCircuit) -> Unchecked:
    """The finding for a conductor energized from ``bc`` whose size is not recorded."""
    return Unchecked(
        f"{article}: cable {cable.id} -- {conductor.handle} size not recorded; its rating "
        f"against circuit {bc.id}'s {bc.circuit_breaker.ampere_rating} A breaker is not checked"
    )


def _small_conductor_ocpd(house: House) -> Iterator[str]:
    """240.4 / 334.80 / 110.14(C) -- a cable assembly conductor (NM-B,
    knob-and-tube) carries its breaker: Table 310.16 at the lowest of its
    insulation, its terminals, and for NM the 60 C column (334.80); 240.4(D)
    caps 14-10 AWG. Raceway conductors are checked per run instead.
    """
    for cable in house.cables():
        if cable.type == "EMT":
            continue
        for w in cable.wires:
            bc = raceway.feeder(house, w)
            if bc is None:
                continue
            if w.size_awg is None:
                yield _unsized("240.4(D)", cable, w, bc)
                continue
            amps = raceway.cable_ampacity(w, bc, cable.type)
            article = _limit(w, bc, amps, "334.80" if cable.type == "NM-B" else "310.16")
            if article:
                yield (
                    f"{article}: cable {cable.id} -- {w.handle} ({w.size_awg} AWG {cable.spec_label}) "
                    f"carries {amps:g} A, under circuit {bc.id}'s "
                    f"{bc.circuit_breaker.ampere_rating} A breaker"
                )


def _afci(house: House) -> Iterator[str]:
    """210.12(A) -- 120 V, 15/20 A dwelling branch circuits require AFCI
    protection.
    """
    for pb in house.panelboards:
        for bc in pb.branch_circuits:
            cb = bc.circuit_breaker
            if cb.poles == 1 and cb.ampere_rating <= 20 and not cb.afci:
                yield f"210.12(A): circuit {bc.id} -- 120 V branch circuit without AFCI protection"


def _ungrounded_receptacle(house: House) -> Iterator[str]:
    """406.4(D)(2) -- where no EGC exists, a grounding-type receptacle is allowed
    only if GFCI-protected and marked "GFCI" and "No Equipment Ground".
    """
    for d in house.devices():
        if isinstance(d, Receptacle) and not d.grounding and not d.gfci:
            yield (f"406.4(D)(2): receptacle {d.id} -- no equipment ground and not GFCI-protected")


def _tamper_resistant(house: House) -> Iterator[str]:
    """406.12 -- 125 V, 15/20 A receptacles in dwelling units must be
    tamper-resistant (few exceptions: >5.5 ft, dedicated appliance, ...).
    """
    for d in house.devices():
        if isinstance(d, Receptacle) and d.poles == 1 and not d.tamper_resistant:
            yield f"406.12: receptacle {d.id} -- not tamper-resistant"


def _reidentification(house: House) -> Iterator[str]:
    """200.7(C)(1) -- a white/gray conductor of a cable assembly used as an
    ungrounded conductor (energized from a breaker, e.g. the second hot of a
    240 V run) must be permanently re-identified at every termination.
    """
    for cable in house.cables():
        if cable.pulled:  # individually pulled wires: no assembly white to re-mark
            continue
        for w in cable.wires:
            if w.role == "neutral" and w.reidentified_as is None and raceway.feeder(house, w):
                yield (
                    f"200.7(C)(1): cable {cable.id} -- white conductor used as ungrounded "
                    "but not re-identified"
                )


def _knob_and_tube(house: House) -> Iterator[str]:
    """394.12 -- knob-and-tube is not permitted for new work (394.10 allows it
    only as an extension of an existing installation).
    """
    seen: set[str] = set()
    for cable in house.cables():
        if cable.type == "knob_and_tube" and cable.upstream not in seen:
            seen.add(cable.upstream)
            yield f"394.12: cable {cable.id} -- knob-and-tube; not permitted for new work"


def _box_fill(house: House) -> Iterator[str]:
    """314.16 -- the box volume (314.16(A)) is not less than the box fill
    (314.16(B), see ``pigtail.fill``).
    """
    for box in house.boxes:
        fill = required_cu_in(house, box.id)
        if fill is None:
            yield Unchecked(
                f"314.16: box {box.id} -- conductor size not recorded in "
                f"{', '.join(ungauged(house, box.id))}; box fill not calculated"
            )
            continue
        volume = box.box_volume_cu_in
        if volume is None:
            if fill:
                yield Unchecked(
                    f"314.16: box {box.id} -- box volume not recorded; box fill {fill:.2f} in.³"
                )
            continue
        if fill > volume + 1e-6:
            yield (
                f"314.16: box {box.id} -- box volume {volume:g} in.³ ({box.volume_basis}), "
                f"less than box fill {fill:.2f} in.³"
            )


def _box_depth(house: House) -> Iterator[str]:
    """314.24(B) -- a box enclosing a switch or receptacle is at least as deep
    as the conductors supplying it need: 2-1/16 in for 8-4 AWG (B)(3), 1-3/16 in
    for 12-10 AWG (B)(4), 15/16 in for 14 AWG and smaller (B)(5); larger than
    4 AWG, a box identified for the purpose (B)(2). The internal depth includes
    any extension box, plaster ring, or raised cover. The rearward projection of
    the device ((B)(1), (B)(4)) is not modelled.
    """
    sizes = {w.handle: w.size_awg for c in house.cables() for w in c.wires}
    for cable in house.cables():
        if cable.to is None:
            continue
        enclosed = [d for d in cable.devices if isinstance(d, SnapSwitch | Receptacle)]
        terminals = {f"{d.id}.{t}" for d in enclosed for t in d.terminals if t != "EGC"}
        supplying = [
            sizes[m]
            for nut in wire_nuts([sp.join for sp in cable.splices])
            if terminals & set(nut)
            for m in nut
            if m in sizes
        ]
        if not supplying:
            continue
        box = house.box(cable.to)
        if None in supplying:
            yield Unchecked(
                f"314.24(B): box {box.id} -- size of the conductors supplying its device not "
                "recorded; the depth they need is not known"
            )
            continue
        awg = min(s for s in supplying if s is not None)  # the largest conductor
        rule = next((k for k, (awgs, _) in SECTION_314_24_B.items() if awg in awgs), None)
        if rule is None:
            yield Unchecked(
                f"314.24(B)(2): box {box.id} -- a device supplied by {awg} AWG needs a box "
                "identified for the purpose"
            )
            continue
        need = SECTION_314_24_B[rule][1]
        parts = box.depth_parts
        known = sum(d for _, d in parts if d is not None)
        unknown = [kind for kind, d in parts if d is None]
        if known >= need - 1e-9:
            continue
        head = f"314.24{rule}: box {box.id} -- "
        if unknown:
            yield Unchecked(
                head + f"depth of its {' and '.join(unknown)} not recorded; a device supplied by "
                f"{awg} AWG needs {_fraction(need)} in."
            )
        else:
            yield (
                head
                + f"internal depth {_fraction(known)} in., less than the {_fraction(need)} in. "
                f"a device supplied by {awg} AWG needs"
            )


def _fraction(inches: float) -> str:
    """Inches to the nearest 1/16, as a trade dimension: 2.0625 -> "2-1/16"."""
    sixteenths = round(inches * 16)
    whole, rest = divmod(sixteenths, 16)
    if not rest:
        return f"{whole}"
    num, den = rest, 16
    while num % 2 == 0:
        num, den = num // 2, den // 2
    return f"{whole}-{num}/{den}" if whole else f"{num}/{den}"


def _multiwire(house: House) -> Iterator[str]:
    """210.4(B) / 200.4(A) -- a neutral returning the loads of two or more
    branch circuits is shared: a multiwire branch circuit. Its hots must
    disconnect together, at a multi-pole breaker or handle-tied breakers
    (210.4(B); handle ties are not modelled, so separate breakers are flagged),
    and must sit on different legs -- otherwise the shared neutral carries their
    summed current and serves more than one branch circuit (200.4(A)). Every
    length of the shared neutral must carry the largest of their breakers.
    """
    flagged: set[str] = set()
    for cable in house.cables():
        for n in cable.wires:
            if n.played_role != "neutral" or raceway.feeder(house, n) is not None:
                continue
            circuits = house.trace.served(n)
            if cable.to is None:
                yield Unchecked(
                    f"210.4(B) / 200.4(A): cable {cable.id} -- far end not traced; the loads on "
                    f"neutral {n.handle}, and whether it is shared, are not known"
                )
            if len(circuits) < 2:
                continue
            ids = "+".join(c.id for c in circuits)
            if ids not in flagged:
                flagged.add(ids)
                yield (
                    f"210.4(B): cable {cable.id} -- multiwire branch circuit {ids} on separate "
                    "breakers; its hots must disconnect together (2-pole breaker or handle tie)"
                )
                legs = [c.circuit_breaker.leg for c in circuits if c.circuit_breaker.poles == 1]
                if len(set(legs)) < len(legs):
                    yield (
                        f"200.4(A): cable {cable.id} -- neutral shared by {ids} on the same leg; "
                        "it carries their combined current"
                    )
            # the shared neutral carries up to the larger hot's current, which only
            # the larger breaker limits -- it must be good for that breaker
            largest = max(circuits, key=lambda c: c.circuit_breaker.ampere_rating)
            if n.size_awg is None:
                yield Unchecked(
                    f"240.4(D): cable {cable.id} -- shared neutral {n.handle} size not recorded; "
                    f"whether it is good for circuit {largest.id}'s "
                    f"{largest.circuit_breaker.ampere_rating} A breaker is not checked"
                )
                continue
            if cable.type == "EMT":
                factor = raceway.adjustment(raceway.current_carrying(house, cable))
                amps = raceway.ampacity(n, largest, factor=factor, ambient_c=cable.ambient_c)
            else:
                amps = raceway.cable_ampacity(n, largest, cable.type)
            article = _limit(n, largest, amps, "210.19(A)(1)")
            if article:
                yield (
                    f"{article}: cable {cable.id} -- shared neutral {n.handle} ({n.size_awg} AWG) "
                    f"is good for {min(amps, raceway.largest_breaker(n, largest, amps)):g} A but carries "
                    f"up to {largest.circuit_breaker.ampere_rating} A from circuit {largest.id}'s breaker "
                    f"(multiwire branch circuit {ids})"
                )


def _raceway_fill(house: House) -> Iterator[str]:
    """358.22 / Chapter 9 Tables 1, 4, 5 -- the wires in an EMT tube may take no
    more of its area than Table 1 allows for their number.
    """
    for cable in raceway.raceways(house):
        filled = raceway.fill(cable)
        if filled is None:
            names = ", ".join(w.handle for w in raceway.ungauged(cable))
            yield Unchecked(
                f"358.22: tube {cable.id} -- size not recorded for {names}; fill not calculated"
            )
            continue
        used, allowed = filled
        if used > allowed + 1e-9:
            wires = [w for w in cable.wires if not w.raceway]
            area = CHAPTER_9_TABLE_4[cable.type][cable.trade_size or ""]["total_area_sq_in"]
            yield (
                f"358.22: tube {cable.id} -- {len(wires)} wires, "
                f'{used * area:.4f} of {area} sq in ({used:.1%}) in {cable.trade_size}" EMT; '
                f"Chapter 9 Table 1 allows {allowed:.0%}"
            )


def _raceway_ampacity(house: House) -> Iterator[str]:
    """310.15 / 110.14(C) / 240.4 -- every energized conductor in an EMT run
    carries its breaker. Its ampacity is the smaller of the middle of the run
    (Table 310.16 at its insulation's rating, Table 310.4(1), x the 310.15(C)(1)
    adjustment for the tube's current-carrying conductors x the 310.15(B)(1)
    ambient correction) and its ends (Table 310.16 at the lowest terminal rating
    on its circuit, 110.14(C)(1)); then 240.4(B) rounding and the 240.4(D) cap.
    """
    for cable in raceway.raceways(house):
        count = raceway.current_carrying(house, cable)
        factor = raceway.adjustment(count)
        ambient = cable.ambient_c
        for w in cable.wires:
            bc = raceway.feeder(house, w)
            if bc is None:
                continue
            if w.size_awg is None:
                yield _unsized("240.4(D)", cable, w, bc)
                continue
            rating = raceway.insulation_rating(w)
            corr = raceway.correction(ambient, rating)
            middle = raceway.table_310_16(w, rating) * factor * corr
            terminal = raceway.terminal_rating(bc)
            ends = raceway.table_310_16(w, terminal)
            amps = min(middle, ends)
            if ends < middle:
                binding = "110.14(C)(1)"
            elif factor < 1:
                binding = "310.15(C)(1)"
            elif corr < 1:
                binding = "310.15(B)(1)"
            else:
                binding = "310.16"
            article = _limit(w, bc, amps, binding)
            if article:
                yield (
                    f"{article}: cable {cable.id} -- {w.handle} ({w.size_awg} AWG {w.insulation} "
                    f"{rating} C; {count} current-carrying in the tube, {factor:.0%}; {ambient:g} C "
                    f"ambient, {corr:g}) -- middle {middle:g} A, ends {ends} A at {terminal} C -- "
                    f"carries {amps:g} A, under circuit {bc.id}'s {bc.circuit_breaker.ampere_rating} A breaker"
                )


def _solid_in_raceway(house: House) -> Iterator[str]:
    """310.3(C) -- conductors 8 AWG and larger in a raceway are stranded."""
    for cable in house.cables():
        if cable.type != "EMT":
            continue
        for w in cable.wires:
            if w.stranding != "solid":
                continue
            if w.size_awg is None:
                yield Unchecked(
                    f"310.3(C): cable {cable.id} -- {w.handle} is solid, size not recorded; "
                    "whether it must be stranded is not checked"
                )
            elif w.size_awg <= SECTION_310_3_C_STRANDED_FROM_AWG:
                yield f"310.3(C): cable {cable.id} -- {w.handle} is solid {w.size_awg} AWG in a raceway"


def _neutral_colour(house: House) -> Iterator[str]:
    """200.6(A) -- a neutral 6 AWG or smaller has white or gray insulation;
    only 4 AWG and larger may be re-identified at its terminations (200.6(B)).
    """
    for cable in house.cables():
        for w in cable.wires:
            if w.played_role != "neutral" or w.color in ("white", "gray"):
                continue
            if w.size_awg is None:
                yield Unchecked(
                    f"200.6(A): cable {cable.id} -- neutral {w.handle} is {w.color}, size not "
                    "recorded; whether it must be white or gray is not checked"
                )
            elif w.size_awg >= 6:
                yield (
                    f"200.6(A): cable {cable.id} -- neutral {w.handle} is {w.color}; "
                    f"a {w.size_awg} AWG neutral must be white or gray"
                )


def _circuit_hots(house: House, bc: BranchCircuit) -> Iterator[tuple[Cable, Conductor]]:
    """Every conductor energized from ``bc``'s breaker, with its run."""
    for cable in bc.all_cables():
        for w in cable.wires:
            if raceway.feeder(house, w) is bc:
                yield cable, w


def _continuous_load(house: House) -> Iterator[str]:
    """210.20(A) / 625.41 and 210.19(A)(1) -- the breaker and every conductor of
    a circuit are rated for 125 % of its continuous load plus its noncontinuous
    load (declared ``load_va``; ``continuous`` for EV charging and the like).
    """
    for pb in house.panelboards:
        for bc in pb.branch_circuits:
            unrecorded = raceway.unrecorded_loads(bc)
            if unrecorded:
                yield Unchecked(
                    f"210.20(A): circuit {bc.id} -- load not recorded for "
                    f"{', '.join(d.id for d in unrecorded)}; the breaker's load is not checked"
                )
                continue
            cont, noncont = raceway.load_amperes(bc)
            if not cont:
                continue
            need = SECTION_210_19_A_1_CONTINUOUS * cont + noncont
            if bc.circuit_breaker.ampere_rating < need:
                yield (
                    f"210.20(A): circuit {bc.id} -- {bc.circuit_breaker.ampere_rating} A breaker, "
                    f"under 125 % of {cont:g} A continuous + {noncont:g} A = {need:g} A"
                )
            for cable, w in _circuit_hots(house, bc):
                if w.size_awg is None:
                    yield _unsized("210.19(A)(1)", cable, w, bc)
                    continue
                if cable.type == "EMT":
                    factor = raceway.adjustment(raceway.current_carrying(house, cable))
                    amps = raceway.ampacity(w, bc, factor=factor, ambient_c=cable.ambient_c)
                else:
                    amps = raceway.cable_ampacity(w, bc, cable.type)
                if amps < need:
                    yield (
                        f"210.19(A)(1): cable {cable.id} -- {w.handle} ({w.size_awg} AWG) carries "
                        f"{amps:g} A, under 125 % of {cont:g} A continuous + {noncont:g} A = {need:g} A"
                    )


def _receptacle_rating(house: House) -> Iterator[str]:
    """210.21(B) -- a single receptacle on an individual branch circuit is rated
    at least the circuit (B)(1); on a circuit with two or more, its rating is
    one Table 210.21(B)(3) permits (B)(3). A receptacle with no recorded
    configuration, or one alone on a circuit that continues past an untraced
    run where the two rules disagree, is not checked.
    """
    for pb in house.panelboards:
        for bc in pb.branch_circuits:
            receptacles = [d for d in bc.devices() if isinstance(d, Receptacle)]
            rating = bc.circuit_breaker.ampere_rating
            for r in receptacles:
                if r.nema is None:
                    yield Unchecked(
                        f"210.21(B): receptacle {r.id} -- configuration (NEMA) not recorded; "
                        f"its rating against circuit {bc.id}'s {rating} A is not checked"
                    )
                    continue
                amps = int(r.nema.rstrip("R").rsplit("-", 1)[1])  # NEMA WD 6: "14-50R" -> 50
                alone = amps < rating  # 210.21(B)(1)
                shared = amps not in TABLE_210_21_B_3.get(rating, (amps,))  # 210.21(B)(3)
                if len(receptacles) == 1 and raceway.untraced(bc) and alone != shared:
                    yield Unchecked(
                        f"210.21(B): receptacle {r.id} -- {amps} A ({r.nema}) on circuit {bc.id}'s "
                        f"{rating} A, which continues past an untraced run; whether it is the "
                        "circuit's only receptacle is not known"
                    )
                elif len(receptacles) == 1 and alone:
                    yield (
                        f"210.21(B)(1): receptacle {r.id} -- {amps} A ({r.nema}) alone on "
                        f"circuit {bc.id}'s {rating} A"
                    )
                elif len(receptacles) > 1 and shared:
                    yield (
                        f"210.21(B)(3): receptacle {r.id} -- {amps} A ({r.nema}) on a {rating} A "
                        f"circuit; Table 210.21(B)(3) permits {TABLE_210_21_B_3[rating]}"
                    )


def _egc_size(house: House) -> Iterator[str]:
    """Table 250.122 -- a wire equipment grounding conductor is at least the
    size the table gives for the largest breaker ahead of the circuits in its
    run, 250.122(C) (a raceway EGC is not a wire).
    """
    for cable in house.cables():
        ratings = [bc.circuit_breaker.ampere_rating for bc in house.trace.run_circuits(cable)]
        if not ratings:
            continue
        rating = max(ratings)
        for w in cable.wires:
            if w.role != "egc" or w.raceway:
                continue
            need = next(awg for amps, awg in TABLE_250_122[w.material] if rating <= amps)
            if w.size_awg is None:
                yield Unchecked(
                    f"Table 250.122: cable {cable.id} -- EGC {w.handle} size not recorded; "
                    f"a {rating} A circuit needs {need} AWG"
                )
            elif w.size_awg > need:
                yield (
                    f"Table 250.122: cable {cable.id} -- EGC {w.handle} is {w.size_awg} AWG; "
                    f"a {rating} A circuit needs {need} AWG"
                )


def _miswired(house: House) -> Iterator[str]:
    """110.7 / 200.11 -- the wiring agrees with each conductor's declared role:
    no conductor energized from two breakers, no ungrounded conductor joined to
    the neutral or EGC bus (a short circuit or ground fault), and no neutral
    landed on a breaker (reversed polarity).
    """
    for cable in house.cables():
        for w in cable.wires:
            fed = house.trace.fed_by(w.handle)
            if len(fed) > 1:
                yield (
                    f"110.7: cable {cable.id} -- {w.handle} is energized from "
                    f"{' and '.join(bc.id for bc in fed)}"
                )
            if fed and w.played_role in ("neutral", "egc"):
                article = "200.11" if w.played_role == "neutral" else "110.7"
                yield (
                    f"{article}: cable {cable.id} -- {w.played_role} {w.handle} is energized "
                    f"from circuit {fed[0].id}'s breaker"
                )
            if w.played_role in ("ungrounded", "traveler") and any(
                w.net.is_attached(bus)
                for pb in house.panelboards
                for bus in (pb.neutral_net, pb.egc_net)
            ):
                yield f"110.7: cable {cable.id} -- ungrounded {w.handle} is joined to the neutral or EGC bus"


def _bends(house: House) -> Iterator[str]:
    """358.26 -- no more than 360 degrees of bends between pull points."""
    for cable in house.cables():
        if cable.bends_deg is not None and cable.bends_deg > SECTION_358_26_MAX_BENDS_DEG:
            yield (
                f"358.26: cable {cable.id} -- {cable.bends_deg:g} degrees of bends between pull "
                f"points; the limit is {SECTION_358_26_MAX_BENDS_DEG}"
            )


def _voltage_drop(house: House) -> Iterator[str]:
    """210.19(A) Informational Note No. 4 -- advice, not a requirement: a
    branch circuit dropping more than 3 % at its farthest loaded outlet (runs
    with ``length_ft``, Chapter 9 Table 8 resistance, the declared load).
    """
    limit = SECTION_210_19_A_IN_4["branch_circuit"]
    for pb in house.panelboards:
        for bc in pb.branch_circuits:
            missing = []
            unmeasured = raceway.unmeasured(house, bc)
            if unmeasured:
                missing.append(f"no length recorded for {', '.join(c.id for c in unmeasured)}")
            unrecorded = raceway.unrecorded_loads(bc)
            if unrecorded:
                missing.append(f"load not recorded for {', '.join(d.id for d in unrecorded)}")
            unsized = raceway.ungauged_hots(house, bc)
            if unsized:
                missing.append(
                    f"conductor size not recorded for {', '.join(c.id for c in unsized)}"
                )
            if missing:
                yield Unchecked(
                    f"210.19(A) IN No. 4: circuit {bc.id} -- voltage drop not checked; "
                    + "; ".join(missing)
                )
            if unrecorded:  # the circuit's current is not known
                continue
            for device, drop in raceway.voltage_drop(house, bc).items():
                if drop > limit:
                    yield (
                        f"210.19(A) IN No. 4: circuit {bc.id} -- {drop:.1%} voltage drop at {device}, "
                        f"over the {limit:.0%} the note recommends"
                    )


_CHECKS = (
    _small_conductor_ocpd,
    _afci,
    _ungrounded_receptacle,
    _tamper_resistant,
    _reidentification,
    _knob_and_tube,
    _box_fill,
    _box_depth,
    _multiwire,
    _raceway_fill,
    _raceway_ampacity,
    _miswired,
    _solid_in_raceway,
    _neutral_colour,
    _continuous_load,
    _receptacle_rating,
    _egc_size,
    _bends,
    _voltage_drop,
)
