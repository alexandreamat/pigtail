"""Raceways and conductor ampacity -- conduit fill (NEC 358.22, Chapter 9),
current-carrying conductors (310.15(E), (F)), ampacity after adjustment and
correction and at the terminals (310.15, 110.14(C)), the overcurrent device a
conductor may have (240.4), and voltage drop (210.19(A) IN No. 4). Every number
comes from :mod:`pigtail.nec_tables`.

A raceway is an EMT run (``Cable.type == "EMT"``): one tube, whatever circuits
its wires are on (:mod:`pigtail.trace`). The tubing serving as the EGC is not a
conductor in it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pigtail.models._base import BuildError
from pigtail.models.device import Appliance, Luminaire, Receptacle
from pigtail.nec_tables import (
    CHAPTER_9_TABLE_1,
    CHAPTER_9_TABLE_4,
    CHAPTER_9_TABLE_5,
    CHAPTER_9_TABLE_8,
    SECTION_110_14_C_1,
    SECTION_220_5_A,
    SECTION_240_4_B_MAX_AMPERES,
    SECTION_240_4_D,
    SECTION_334_80_TEMP_C,
    TABLE_240_6_A,
    TABLE_310_4_1,
    TABLE_310_15_B_1_1,
    TABLE_310_15_C_1,
    TABLE_310_16,
)

if TYPE_CHECKING:
    from pigtail.models.cable import Cable
    from pigtail.models.circuit import BranchCircuit
    from pigtail.models.conductor import Conductor
    from pigtail.models.house import House


# --- raceways --------------------------------------------------------------


def raceways(house: House) -> list[Cable]:
    """Every EMT run."""
    return [c for c in house.cables() if c.type == "EMT"]


def feeder(house: House, conductor: Conductor) -> BranchCircuit | None:
    """The breaker a conductor is energized from; None for one that is not (a
    neutral, an EGC, a dead wire).
    """
    fed = house.trace.fed_by(conductor.handle)
    return fed[0] if fed else None


def size(conductor: Conductor) -> int:
    """The conductor's size, AWG -- for a calculation that needs it."""
    if conductor.size_awg is None:
        raise BuildError(f"{conductor.handle}: size not recorded")
    return conductor.size_awg


def conductor_area(conductor: Conductor) -> float:
    """Chapter 9 Table 5: the conductor's cross-section, sq in."""
    try:
        return CHAPTER_9_TABLE_5[conductor.insulation][size(conductor)]["area_sq_in"]
    except KeyError:
        raise BuildError(
            f"{conductor.handle}: no Chapter 9 Table 5 area for {conductor.insulation} "
            f"{conductor.size_awg} AWG"
        ) from None


def ungauged(cable: Cable) -> list[Conductor]:
    """The wires in a run whose size is not recorded (the raceway is not a wire)."""
    return [w for w in cable.wires if w.size_awg is None and not w.raceway]


def fill(cable: Cable) -> tuple[float, float] | None:
    """(fraction of the tube's area the wires take, the fraction Chapter 9
    Table 1 allows for that many wires); None when a wire's size is not
    recorded.
    """
    if cable.trade_size is None:
        raise BuildError(f"cable {cable.id!r} has no trade size -- not a raceway")
    if ungauged(cable):
        return None
    wires = [w for w in cable.wires if not w.raceway]
    area = sum(conductor_area(w) for w in wires)
    row = "1" if len(wires) == 1 else "2" if len(wires) == 2 else "over 2"
    total = CHAPTER_9_TABLE_4[cable.type][cable.trade_size]["total_area_sq_in"]
    return area / total, CHAPTER_9_TABLE_1[row]


def current_carrying(house: House, cable: Cable) -> int:
    """Current-carrying conductors in the run (310.15(E), (F)): every conductor
    energized from a breaker; a neutral too, except one carrying only the
    unbalanced current (310.15(E)(1)) -- the neutral of a 120/240 V 2-pole
    circuit, or one shared by 1-pole circuits on different legs -- and one
    that returns no load (capped). A neutral continuing into a run whose far
    end is not traced counts. EGCs never count.
    """
    count = 0
    for w in cable.wires:
        if w.role == "egc":
            continue
        if feeder(house, w) is not None:
            count += 1
            continue
        if w.played_role != "neutral":
            continue  # a dead wire: energized from nothing
        if house.trace.open_ended(w):
            count += 1
            continue
        circuits = house.trace.served(w)
        if not circuits:
            continue
        if len(circuits) == 1:
            count += circuits[0].circuit_breaker.poles == 1
            continue
        one_pole = [c for c in circuits if c.circuit_breaker.poles == 1]
        legs = {c.circuit_breaker.leg for c in one_pole}
        count += not (len(one_pole) == len(circuits) and len(legs) == len(one_pole))
    return count


# --- ampacity ----------------------------------------------------------------


def adjustment(count: int) -> float:
    """Table 310.15(C)(1): the factor for ``count`` current-carrying conductors."""
    return next(f for (low, high), f in TABLE_310_15_C_1.items() if low <= count <= high)


def correction(ambient_c: float, rating: int) -> float:
    """Table 310.15(B)(1)(1): the ambient-temperature factor for insulation
    rated ``rating`` C; 0 where the insulation may not be used at that ambient.
    """
    for (low, high), factors in TABLE_310_15_B_1_1.items():
        if low <= ambient_c <= high:
            return factors[rating] or 0.0
    return 0.0


def insulation_rating(conductor: Conductor) -> int:
    """Table 310.4(1): the insulation's temperature rating, C."""
    try:
        return TABLE_310_4_1[conductor.insulation]
    except KeyError:
        raise BuildError(
            f"{conductor.handle}: no temperature rating for {conductor.insulation}"
        ) from None


def terminal_rating(bc: BranchCircuit) -> int:
    """110.14(C): the lowest temperature rating among the circuit's breaker and
    receptacles -- the ends of every conductor on it. Unmarked equipment takes
    the 110.14(C)(1) default for the circuit's rating.
    """
    unmarked = (
        SECTION_110_14_C_1["(a)"]["temp_c"]
        if bc.circuit_breaker.ampere_rating <= SECTION_110_14_C_1["(a)"]["max_amperes"]
        else SECTION_110_14_C_1["(b)"]["temp_c"]
    )
    marks = [bc.circuit_breaker.terminal_c]
    marks += [d.terminal_c for d in bc.devices() if isinstance(d, Receptacle)]
    return min(unmarked if m is None else m for m in marks)


def table_310_16(conductor: Conductor, rating: int) -> int:
    try:
        return TABLE_310_16[conductor.material][rating][size(conductor)]
    except KeyError:
        raise BuildError(
            f"{conductor.handle}: no Table 310.16 ampacity for {conductor.material} "
            f"{conductor.size_awg} AWG at {rating} C"
        ) from None


def ampacity(conductor: Conductor, bc: BranchCircuit, *, factor: float, ambient_c: float) -> float:
    """The current a conductor may carry: the smaller of the middle of its run
    -- its insulation's Table 310.16 column x the adjustment x the ambient
    correction -- and its ends, the Table 310.16 column of the lowest terminal
    rating on its circuit (110.14(C)).
    """
    rating = insulation_rating(conductor)
    middle = table_310_16(conductor, rating) * factor * correction(ambient_c, rating)
    ends = table_310_16(conductor, terminal_rating(bc))
    return min(middle, ends)


def cable_ampacity(conductor: Conductor, bc: BranchCircuit, method: str) -> float:
    """A cable assembly conductor (NM-B, knob-and-tube): the Table 310.16 column
    of the lowest of its insulation, its terminals, and -- for NM -- 334.80.
    """
    ratings = [insulation_rating(conductor), terminal_rating(bc)]
    if method == "NM-B":
        ratings.append(SECTION_334_80_TEMP_C)
    return float(table_310_16(conductor, min(ratings)))


def untraced(bc: BranchCircuit) -> bool:
    """Whether the circuit continues past a run whose far end is not traced --
    so its devices beyond it are not known.
    """
    return any(c.to is None for c in bc.all_cables())


def unrecorded_loads(bc: BranchCircuit) -> list[Luminaire | Appliance]:
    """The circuit's luminaires and appliances whose load is not recorded."""
    return [d for d in bc.devices() if isinstance(d, Luminaire | Appliance) and d.load_va is None]


def largest_breaker(conductor: Conductor, bc: BranchCircuit, amps: float) -> float:
    """The largest breaker that may protect a conductor of ampacity ``amps``:
    ``amps``, or the next 240.6(A) standard rating up when ``amps`` is not one,
    the circuit supplies at most one receptacle -- known only when no run on it
    is untraced -- and the rating stays within 800 A (240.4(B)); never above
    the 240.4(D) limit for 14-10 AWG.
    """
    permitted = amps
    receptacles = sum(1 for d in bc.devices() if isinstance(d, Receptacle))
    if amps not in TABLE_240_6_A and receptacles <= 1 and not untraced(bc):
        up = next((s for s in TABLE_240_6_A if s >= amps), amps)
        permitted = up if up <= SECTION_240_4_B_MAX_AMPERES else amps
    awg = conductor.size_awg
    cap = None if awg is None else SECTION_240_4_D.get(conductor.material, {}).get(awg)
    return permitted if cap is None else min(permitted, cap)


# --- loads -------------------------------------------------------------------


def nominal_volts(bc: BranchCircuit) -> int:
    """220.5(A): the circuit's nominal voltage."""
    return SECTION_220_5_A[bc.circuit_breaker.poles]


def load_amperes(bc: BranchCircuit) -> tuple[float, float]:
    """(continuous, noncontinuous) amperes the circuit's devices draw, from
    each device's ``demand_va()`` at the circuit's 220.5(A) nominal voltage.
    """
    volts = nominal_volts(bc)
    demands = [d.demand_va() for d in bc.devices()]
    return sum(c for c, _ in demands) / volts, sum(n for _, n in demands) / volts


# --- voltage drop ------------------------------------------------------------


def resistance_per_ft(conductor: Conductor) -> float:
    """Chapter 9 Table 8: DC resistance at 75 C, ohm per ft (stranded where the
    stranding is not recorded or the size is tabulated stranded only).
    """
    row = CHAPTER_9_TABLE_8[size(conductor)]
    return row.get(conductor.stranding or "stranded", row["stranded"]) / 1000


def unmeasured(house: House, bc: BranchCircuit) -> list[Cable]:
    """The runs with no ``length_ft`` between the panelboard and a device with a
    declared load on the circuit -- what keeps its voltage drop from being
    calculated.
    """
    loaded = [d for d in bc.devices() if any(d.demand_va())]
    out: dict[str, Cable] = {}
    for run in house.cables():
        if any(x is d for d in loaded for x in run.devices):
            for c in house.path(run):
                if c.length_ft is None:
                    out.setdefault(c.id, c)
    return list(out.values())


def ungauged_hots(house: House, bc: BranchCircuit) -> list[Cable]:
    """The runs between the panelboard and a device with a declared load on the
    circuit whose hot has no recorded size -- what keeps its voltage drop from
    being calculated.
    """
    loaded = [d for d in bc.devices() if any(d.demand_va())]
    out: dict[str, Cable] = {}
    for run in house.cables():
        if any(x is d for d in loaded for x in run.devices):
            for c in house.path(run):
                hot = next((w for w in c.wires if feeder(house, w) is bc), None)
                if hot is not None and hot.size_awg is None:
                    out.setdefault(c.id, c)
    return list(out.values())


def voltage_drop(house: House, bc: BranchCircuit) -> dict[str, float]:
    """Voltage drop, as a fraction of nominal, to each device with a declared
    load, where every run from the panelboard to it has a ``length_ft``: the
    circuit's full declared current over the out-and-back path (2 x length x
    resistance of the circuit's hot in each run).
    """
    cont, noncont = load_amperes(bc)
    amps = cont + noncont
    if not amps:
        return {}
    volts = nominal_volts(bc)
    out: dict[str, float] = {}
    for run in house.cables():
        for d in run.devices:
            if not any(d.demand_va()) or not any(x is d for x in bc.devices()):
                continue
            drop = 0.0
            for c in house.path(run):
                hot = next((w for w in c.wires if feeder(house, w) is bc), None)
                if c.length_ft is None or hot is None or hot.size_awg is None:
                    break
                drop += 2 * c.length_ft * amps * resistance_per_ft(hot)
            else:
                out[d.id] = drop / volts
    return out
