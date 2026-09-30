"""The circuit diagram -- one Graphviz DOT view of a house, or of one circuit.

Assembled from fragments each model renders itself:

* ``Panelboard.diagram_buses``   -- the vertical busbar column
* ``CircuitBreaker.diagram_node`` / ``BranchCircuit.clip_edges``
* ``Cable.diagram_node``          -- a colour band per conductor (+ ``Conductor.cable_cell``)
* ``<Device>.diagram_node``       -- a square: name on top, terminal cells along the bottom
* ``Box.diagram_cluster``         -- the box enclosing its devices and splice bar

The drawing follows the wiring tree: the panelboard, the runs leaving it (each
landing wire drawn from its breaker terminal or busbar), and every box they
reach. Cables are the runs *between* boxes: free-standing nodes, never box
contents. A box's splices are merged into physical wire nuts
(``_dot.wire_nuts``) so a conductor passing through a box is one splice point,
not several. A run whose far end is not traced is drawn with its near end only.

Render with ``dot -Tsvg`` / ``-Tpng``. ``circuit_diagram(house)`` is the whole
house; ``only="C5"`` restricts it to what carries one branch circuit. Every
element carries the SVG class ``circuit-<id>`` of each circuit it is on (traced,
:mod:`pigtail.trace`) -- a run or box shared by several carries several -- so a
viewer can hide circuits without re-laying out the drawing. The panelboard and
its busbars carry none.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping

from pigtail.fill import required_cu_in
from pigtail.models._base import BuildError
from pigtail.models._dot import EDGE_COLOUR, ROLE_CELL, bus_ref, esc, role_of, wire_nuts
from pigtail.models.house import House

_BUS_PORT = {"NEUTRAL": "N", "EGC": "EGC"}  # busbar -> its row on the bus node


def circuit_diagram(house: House, *, only: str | None = None, title: str | None = None) -> str:
    trace = house.trace
    if only is not None and not any(
        bc.id == only for pb in house.panelboards for bc in pb.branch_circuits
    ):
        raise BuildError(f"unknown circuit {only!r}")

    def on(ids: Iterable[str]) -> bool:
        return only is None or only in ids

    # conductor handle -> role / insulation colour / the circuits it is on (an
    # EGC: those of its run); device id -> its circuit
    roles: dict[str, str] = {}
    colours: dict[str, str] = {}
    circuits: dict[str, list[str]] = {}
    for c in house.cables():
        run_ids = [bc.id for bc in trace.run_circuits(c)]
        for w in c.wires:
            roles[w.handle] = w.role
            colours[w.handle] = w.color
            circuits[w.handle] = [bc.id for bc in trace.circuits(w)] or run_ids
    for d in house.devices():
        bc = trace.device_circuit(d)
        circuits[d.id] = [bc.id] if bc else []

    runs = [c for c in house.cables() if on(bc.id for bc in trace.run_circuits(c))]
    drawn = {c.id for c in runs}

    def visible(member: str) -> bool:
        owner = member.split(".", 1)[0]
        if member in roles:
            return owner in drawn and on(circuits[member])
        return on(circuits.get(owner, []))

    heading = title or house.meta.project
    if only:
        heading = f"{heading} — circuit {only}"
    lines = [
        "digraph circuit {",
        "  rankdir=LR; newrank=true; compound=true; splines=true;",
        "  nodesep=0.28; ranksep=0.9;",
        "  node [fontname=Helvetica fontsize=9];",
        "  edge [fontname=Helvetica fontsize=8 arrowhead=none];",
        f'  labelloc=t; labeljust=l; label="{esc(heading)}";',
    ]

    for pb in house.panelboards:
        picked = [bc for bc in pb.branch_circuits if on([bc.id])]
        lines.append(f'  subgraph "cluster_{pb.id}" {{')
        lines.append(
            f'    label="panelboard {esc(pb.id)}"; labelloc=t; '
            'style="rounded,filled"; fillcolor="#eef1fb"; color="#9aa7d0"; fontsize=9;'
        )
        hot_used: set[str] = set()
        for bc in picked:
            cb = bc.circuit_breaker
            hot_used |= {"L1", "L2"} if cb.poles == 2 else {cb.leg}
        lines.append(f"  {pb.diagram_buses(hot_used=hot_used)}")
        for bc in picked:
            lines.append(f"    {bc.circuit_breaker.diagram_node(bc.id).strip()}")
            lines.append(_classed(bc.id, [bc.id]))
        lines.append("  }")
        for bc in picked:
            lines += bc.clip_edges(panel_id=pb.id)
        lines += _landing_edges(
            pb.id, [sp.join for sp in pb.splices], roles, colours, circuits, visible
        )

    for cable in runs:
        lines.append(cable.diagram_node())
        lines.append(_classed(cable.id, [bc.id for bc in trace.run_circuits(cable)]))

    # each box a run lands in: the devices mounted there and one splice bar
    anchor: dict[str, str] = {}  # box id -> a node in it, for rank threading
    for cable in runs:
        if cable.to is None:
            continue
        box_id = cable.to
        dev_ids = [d.id for d in cable.devices if on(circuits[d.id])]
        inner: list[str] = []
        for d in cable.devices:
            if d.id in dev_ids:
                inner += [d.diagram_node(), _classed(d.id, circuits[d.id])]
        nuts = [
            kept
            for nut in wire_nuts([sp.join for sp in cable.splices])
            if (kept := [m for m in nut if visible(m)])
        ]
        nut_ids = _ids(
            circuits[m] if m in roles else circuits[m.split(".", 1)[0]] for n in nuts for m in n
        )
        in_box = _ids([nut_ids, *(circuits[d] for d in dev_ids)])
        if in_box:  # the box itself, shown while any circuit in it is
            inner.insert(0, f'  graph [class="{_class(in_box)}"];')
        same = dev_ids[:1]  # the splice bar sits under the first device
        if nuts:
            inner += [_splice_bar(box_id, nuts, roles), _classed(f"spl_{box_id}", nut_ids)]
            same.append(f"spl_{box_id}")
        elif not dev_ids:  # nothing recorded in the box: a point to thread runs through
            inner.append(f'  "spl_{box_id}" [shape=point width=0 height=0 style=invis label=""];')
            same.append(f"spl_{box_id}")
        anchor[box_id] = same[-1] if len(same) > 1 or not dev_ids else dev_ids[0]
        lines += house.box(box_id).diagram_cluster(
            inner, same_rank=same, fill=required_cu_in(house, box_id)
        )
        lines += _splice_edges(box_id, nuts, roles, colours, circuits, incoming=cable.id)
        # a box's devices side by side, left to right
        lines += [f'  "{a}" -> "{b}" [style=invis];' for a, b in zip(dev_ids, dev_ids[1:])]

    # thread the flow left to right so boxes chain horizontally: each run into
    # its landing box, then that box out to the runs continuing from it.
    for cable in runs:
        if cable.to is None:
            continue
        lines.append(f'  "{cable.id}" -> "{anchor[cable.to]}" [style=invis];')
        lines += _fork(anchor[cable.to], [o.id for o in cable.cables if o.id in drawn])

    lines.append("}")
    return "\n".join(line for line in lines if line)


def _class(ids: Iterable[str]) -> str:
    return " ".join(f"circuit-{i}" for i in ids)


def _ids(groups: Iterable[Iterable[str]]) -> list[str]:
    """The distinct ids of several lists, in first-seen order."""
    return list(dict.fromkeys(i for g in groups for i in g))


def _classed(node: str, ids: Iterable[str]) -> str:
    """Tag an already-declared node with the circuits it is on."""
    cls = _class(ids)
    return f'  "{node}" [class="{cls}"];' if cls else ""


def _landing_edges(
    panel_id: str,
    joins: list[list[str]],
    roles: Mapping[str, str],
    colours: Mapping[str, str],
    circuits: Mapping[str, list[str]],
    visible: Callable[[str], bool],
) -> list[str]:
    """The panelboard's landings: each wire from the breaker terminal it lands
    on (east of the breaker, west of the run), or to the busbar it lands on,
    in its own colour.
    """
    out: list[str] = []
    for join in joins:
        wires = [m for m in join if m in roles and visible(m)]
        ends = [m for m in join if m not in roles]
        for wire in wires:
            run, name = wire.split(".", 1)
            colour = EDGE_COLOUR[colours[wire]]
            style = " style=dashed" if roles[wire] == "egc" else ""
            cls = f' class="{_class(circuits[wire])}"' if circuits[wire] else ""
            for end in ends:
                owner, part = end.split(".", 1)
                if owner == panel_id:
                    out.append(
                        f'  "{run}":{name}:w -> {bus_ref(panel_id, _BUS_PORT[part])}:e '
                        f'[color="{colour}"{style}{cls}];'
                    )
                else:
                    out.append(
                        f'  "{owner}":{part}:e -> "{run}":{name}:w [color="{colour}"{style}{cls}];'
                    )
    return out


def _fork(anchor: str, onward: list[str]) -> list[str]:
    """Link a box to the runs leaving it. With two or more, the runs straddle
    the box's height -- the first listed on top, the rest below in order -- held
    by invisible same-column links; the middle run (odd count) or an invisible
    point between the middle two (even count) is pinned to the box's height.
    """
    out = [f'  "{anchor}" -> "{run}" [style=invis];' for run in onward]
    if len(onward) < 2:
        return out
    column = list(onward)
    middle = len(onward) // 2
    if len(onward) % 2:
        pin = onward[middle]
    else:
        pin = f"fork_{anchor}"
        column.insert(middle, pin)
        out.append(f'  "{pin}" [shape=point width=0 height=0 style=invis label=""];')
    out.append(f'  "{anchor}" -> "{pin}" [style=invis weight=100];')
    out.append("  { rank=same; " + " ".join(f'"{n}";' for n in column) + " }")
    out.append("  " + " -> ".join(f'"{n}"' for n in column) + " [style=invis];")
    return out


def _splice_bar(box_id: str, nuts: list[list[str]], roles: Mapping[str, str]) -> str:
    """One node per box: a horizontal row of small squares, one per wire nut,
    coloured by conductor role, each reachable as ``"spl_<box>":s<i>``. A tall
    empty spacer row above the squares keeps them clear of the device so the
    wires have room to route.
    """
    cells = ""
    for i, members in enumerate(nuts):
        bg, _fg, extra = ROLE_CELL[role_of(members, roles)]
        cells += f'<td port="s{i}"{extra} bgcolor="{bg}" width="16" height="16"></td>'
    return (
        f'  "spl_{box_id}" [shape=plaintext label=<'
        f'<table border="0" cellborder="1" cellspacing="6" cellpadding="0">'
        f'<tr><td border="0" colspan="{len(nuts)}" height="34"></td></tr>'
        f"<tr>{cells}</tr></table>>];"
    )


def _splice_edges(
    box_id: str,
    nuts: list[list[str]],
    roles: Mapping[str, str],
    colours: Mapping[str, str],
    circuits: Mapping[str, list[str]],
    *,
    incoming: str,
) -> list[str]:
    """From each wire nut to every member's port. Every wire lands on the nut's
    top edge (``:n``) so the nut reads as a knot. The far end: a device terminal
    from below (``:s``); the box's incoming cable from its east (``:e``); an
    onward cable from its west (``:w``). ``constraint`` off: wiring detail, the
    flow is set by the invisible threading edges. Each edge takes its wire's
    colour (``colours``: handle -> insulation colour) and circuits; an edge to a
    device terminal takes the colour of the nut's first cable wire and the
    device's circuit.
    """
    out: list[str] = []
    for i, members in enumerate(nuts):
        role = role_of(members, roles)
        style = "dashed" if role == "egc" else "solid"
        nut_colour = next((colours[m] for m in members if m in colours), "black")
        for member in members:
            colour = EDGE_COLOUR[colours.get(member, nut_colour)]
            owner, part = member.split(".", 1)
            if member not in roles:  # a device terminal
                far = ":s"
                ids = circuits.get(owner, [])
            else:
                far = ":e" if owner == incoming else ":w"
                ids = circuits.get(member, [])
            cls = f' class="{_class(ids)}"' if ids else ""
            out.append(
                f'  "spl_{box_id}":s{i}:n -> "{owner}":{part}{far} '
                f'[color="{colour}" style={style} constraint=false{cls}];'
            )
    return out
