"""Shared primitives for the circuit diagram (one Graphviz DOT view).

Each renderable model returns its own fragment -- ``Panelboard.diagram_buses``,
``CircuitBreaker.diagram_node``, ``Cable.diagram_node`` (+ ``Conductor.cable_cell``),
``<Device>.diagram_node``, ``Box.diagram_cluster``, ``Splice.diagram_cell`` /
``diagram_edges`` -- and ``outputs/diagram.py`` composes them.
"""

from __future__ import annotations

from collections.abc import Mapping

# conductor role -> edge colour
ROLE_COLOUR = {
    "ungrounded": "#111111",
    "traveler": "#d33333",
    "neutral": "#808080",  # a grey line -- a true white line would be invisible
    "egc": "#0a8a0a",
}
# insulation colour -> edge colour: a wire is drawn in its own colour, white as
# grey (a true white line would be invisible), bare copper / raceway as EGC green
EDGE_COLOUR: dict[str, str] = {
    "black": ROLE_COLOUR["ungrounded"],
    "red": ROLE_COLOUR["traveler"],
    "blue": "#2459c9",
    "yellow": "#e0b000",
    "white": ROLE_COLOUR["neutral"],
    "gray": ROLE_COLOUR["neutral"],
    "green": ROLE_COLOUR["egc"],
    "bare": ROLE_COLOUR["egc"],
}
# conductor role -> (cell background, text colour, extra <td> attributes) for HTML nodes
ROLE_CELL = {
    "ungrounded": ("#111111", "#ffffff", ""),
    "traveler": ("#d33333", "#ffffff", ""),
    "neutral": ("#ffffff", "#000000", ' border="1" color="#111111"'),
    "egc": ("#0a8a0a", "#ffffff", ""),
}
# insulation colour -> the same (background, text, extra) triple, for a cable
# row. Bare copper (and a raceway EGC) draws as EGC green, as ROLE_CELL does.
COLOUR_CELL: dict[str, tuple[str, str, str]] = {
    "black": ROLE_CELL["ungrounded"],
    "red": ROLE_CELL["traveler"],
    "blue": ("#2459c9", "#ffffff", ""),
    "yellow": ("#f2c318", "#000000", ""),
    "white": ROLE_CELL["neutral"],
    "gray": ("#9a9a9a", "#000000", ""),
    "green": ROLE_CELL["egc"],
    "bare": ROLE_CELL["egc"],
}


def wire_nuts(joins: list[list[str]]) -> list[list[str]]:
    """Merge splice member-lists that share any member into one group per
    physical wire nut -- so a conductor that passes through a box (its incoming
    run, its outgoing run and a device tap all on one net) is a single splice
    point, not several. Members keep first-seen order.
    """
    parent: dict[str, str] = {}
    order: list[str] = []

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for join in joins:
        for member in join:
            if member not in parent:
                parent[member] = member
                order.append(member)
        for member in join[1:]:
            parent[find(join[0])] = find(member)

    groups: dict[str, list[str]] = {}
    for member in order:
        groups.setdefault(find(member), []).append(member)
    return list(groups.values())


def role_of(members: list[str], roles: Mapping[str, str]) -> str:
    """The conductor role a wire nut carries, from its first cable member.
    ``roles`` maps each conductor handle (``<cable>.<name>``) to its role.
    """
    for member in members:
        if member in roles:
            return roles[member]
    return "ungrounded"


def esc(text: str) -> str:
    """Escape a plain double-quoted DOT string."""
    return text.replace('"', '\\"')


def html_esc(text: str) -> str:
    """Escape text placed inside an HTML-like (``label=<...>``) node."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def bus_ref(panel_id: str, bus: str) -> str:
    """Port reference of one busbar row on the panelboard's bus node -- ``bus``
    in L1 / L2 / N / EGC.
    """
    return f'"{panel_id}_bus":{bus}'


def device_record(node_id: str, tag: str, terminals: tuple[str, ...], *, fill: str) -> str:
    """A device as an HTML-like node: name (``tag``, ``\\n`` -> line break) on
    top, one terminal cell per entry in ``terminals`` in a row along the bottom,
    each reachable as ``"node_id":TERMINAL``.
    """
    head = html_esc(tag).replace("\\n", "<br/>")
    cells = "".join(f'<td port="{t}">{t}</td>' for t in terminals)
    return (
        f'  "{node_id}" [shape=plaintext label=<'
        f'<table border="1" cellborder="1" cellspacing="0" cellpadding="4" bgcolor="{fill}">'
        f'<tr><td colspan="{len(terminals)}">{head}</td></tr>'
        f"<tr>{cells}</tr></table>>];"
    )


def breaker_record(node_id: str, tag: str, *, poles: int) -> str:
    """A breaker as a series element: LINE terminal(s) down the left column
    (entered from the west), LOAD terminal(s) down the right (exited east), name
    spanning the top -- so power reads left to right like the rest of the diagram.
    """
    head = html_esc(tag).replace("\\n", "<br/>")
    if poles == 1:
        rows = '<tr><td port="LINE">LINE</td><td port="LOAD">LOAD</td></tr>'
    else:
        rows = (
            '<tr><td port="LINE1">LINE1</td><td port="LOAD1">LOAD1</td></tr>'
            '<tr><td port="LINE2">LINE2</td><td port="LOAD2">LOAD2</td></tr>'
        )
    return (
        f'  "{node_id}" [shape=plaintext label=<'
        f'<table border="1" cellborder="1" cellspacing="0" cellpadding="4" bgcolor="#ffe9d6">'
        f'<tr><td colspan="2">{head}</td></tr>{rows}</table>>];'
    )
