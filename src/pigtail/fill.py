"""Box fill -- NEC 314.16. Shared by the NEC check, the BOM, and the diagram.

``required_cu_in(house, box_id)`` is the box fill (314.16(B) Box Fill
Calculations, Table 314.16(B) volume allowances) for everything in that box;
314.16 requires the box volume (314.16(A), ``Box.box_volume_cu_in``) to be not
less than it. ``suggest`` names the smallest Table 314.16(A) box that holds it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pigtail.models._base import BuildError
from pigtail.models.device import Receptacle, SnapSwitch
from pigtail.nec_tables import SECTION_314_16_B_4_PER_YOKE, TABLE_314_16_A, TABLE_314_16_B

if TYPE_CHECKING:
    from pigtail.models.house import House


def allowance(awg: int) -> float:
    """Table 314.16(B): the volume one conductor of this size takes, cu in."""
    try:
        return TABLE_314_16_B[awg]
    except KeyError:
        raise BuildError(
            f"{awg} AWG is outside Table 314.16(B) -- boxes for 4 AWG and larger are sized by 314.28"
        ) from None


def required_cu_in(house: House, box_id: str) -> float:
    """Free space Table 314.16(B) requires for box ``box_id``: one allowance per
    insulated circuit conductor entering it (B)(1), two of the largest per
    yoke or strap carrying a switch or receptacle (B)(4), and one of the
    largest for all wire EGCs together (B)(5) -- an EMT raceway serving as the
    EGC is not a conductor in the box. A luminaire mounted on the box is on no
    yoke; its fixture stud or hickey (B)(3) is not modelled, nor are clamps
    (B)(2). Conductors that never leave the box (pigtails) are not counted, and
    a wire pulled through unspliced (``Splice.through``) counts once, not once
    per run (B)(1).
    """

    here = [c for c in house.cables() if box_id in (c.to, c.upstream)]
    extra = sum(allowance(awg) * n for awg, n in house.box(box_id).extra_conductors.items())
    if not here:
        return extra
    largest = allowance(
        min(w.size_awg for c in here for w in c.wires)
    )  # smallest AWG = largest wire
    conductors = sum(allowance(w.size_awg) for c in here for w in c.wires if w.role != "egc")
    for sp in (sp for c in here if c.to == box_id for sp in c.splices if sp.through):
        owner, name = sp.join[0].split(".", 1)
        wire = house.cable(owner).wire(name)
        if wire.role != "egc":  # the in-run and out-run both counted it; it is one wire
            conductors -= allowance(wire.size_awg)
    yokes = sum(
        1
        for c in here
        if c.to == box_id
        for d in c.devices
        if isinstance(d, SnapSwitch | Receptacle)
    )
    devices = SECTION_314_16_B_4_PER_YOKE * largest * yokes
    wire_egc = any(w.role == "egc" and not w.raceway for c in here for w in c.wires)
    egc = largest if wire_egc else 0.0
    return conductors + extra + devices + egc


def suggest(required: float) -> str | None:
    """The smallest Table 314.16(A) box whose minimum volume holds ``required`` in.³."""
    boxes = sorted(
        (row["in3"], f"{size} {shape}")
        for shape, sizes in TABLE_314_16_A.items()
        for size, row in sizes.items()
    )
    return next((f"{name} ({volume:g} in.³)" for volume, name in boxes if volume >= required), None)
