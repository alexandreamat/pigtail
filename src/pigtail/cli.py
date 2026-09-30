from __future__ import annotations

import shutil
import subprocess
import warnings
from pathlib import Path
from typing import Annotated

import typer

from pigtail.models.house import House
from pigtail.nec import NECUnchecked, NECViolation
from pigtail.outputs.diagram import circuit_diagram

app = typer.Typer(
    add_completion=False,
    help="House wiring as code: describe it in YAML, draw it, check it against the NEC.",
)


@app.callback()
def _root() -> None:
    """Keep sub-command structure (`pigtail build ...`) even with one command."""


@app.command("build")
def build_command(
    spec: Annotated[
        Path, typer.Argument(exists=True, dir_okay=False, readable=True, help="house .yaml")
    ],
    out: Annotated[
        Path | None,
        typer.Option(help="write netlist / dot / schedules into this directory"),
    ] = None,
) -> None:
    """Load a YAML house (which assembles it) and print its topology."""
    house = House.from_yaml(spec)

    n_cables = sum(1 for _ in house.cables())
    n_devices = sum(1 for _ in house.devices())
    n_splices = sum(len(c.splices) for c in house.cables())
    typer.echo(f"# {house.meta.project}   ({house.meta.code_edition})")
    typer.echo(
        f"# {n_cables} cables, {n_devices} devices, {len(house.boxes)} boxes, {n_splices} splices\n"
    )
    typer.echo(house.panel_schedule())
    typer.echo("")
    typer.echo(house.conductor_schedule())
    typer.echo("")
    typer.echo(house.net_summary())

    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        stem = spec.stem
        house.built_circuit().generate_netlist(file_=str(out / f"{stem}.net"))
        (out / f"{stem}.dot").write_text(circuit_diagram(house, title=house.meta.project))
        (out / f"{stem}.panel.txt").write_text(house.panel_schedule() + "\n")
        (out / f"{stem}.conductors.txt").write_text(house.conductor_schedule() + "\n")
        (out / f"{stem}.nets.txt").write_text(house.net_summary() + "\n")
        (out / f"{stem}.raceways.txt").write_text(house.raceway_schedule() + "\n")
        typer.echo(
            f"\nwrote {stem}.{{net,dot,panel.txt,conductors.txt,nets.txt,raceways.txt}} -> {out}/"
        )


@app.command("check")
def check_command(
    spec: Annotated[
        Path, typer.Argument(exists=True, dir_okay=False, readable=True, help="house .yaml")
    ],
) -> None:
    """Run the NEC checks and print every violation, then every rule that could
    not be checked for want of a recorded value. Nothing is rejected -- an
    as-built house may hold violations. (``House.check()`` is the same pass; it
    raises each as a ``nec.NECViolation`` / ``nec.NECUnchecked`` Python warning.)
    """
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", NECViolation)
        warnings.simplefilter("always", NECUnchecked)
        House.from_yaml(spec).check()
    found = [str(w.message) for w in caught if issubclass(w.category, NECViolation)]
    unchecked = [str(w.message) for w in caught if issubclass(w.category, NECUnchecked)]
    for message in found:
        typer.echo(message)
    for message in unchecked:
        typer.echo(f"not checked -- {message}")
    typer.echo(f"\n{len(found)} violation(s)" if found else "\nno violations")
    if unchecked:
        typer.echo(f"{len(unchecked)} rule(s) not checked: a value they need is not recorded")


@app.command("bom")
def bom_command(
    spec: Annotated[
        Path, typer.Argument(exists=True, dir_okay=False, readable=True, help="house .yaml")
    ],
) -> None:
    """Print the bill of materials."""
    typer.echo(House.from_yaml(spec).bom())


@app.command("draw")
def draw_command(
    spec: Annotated[
        Path, typer.Argument(exists=True, dir_okay=False, readable=True, help="house .yaml")
    ],
    output: Annotated[
        Path, typer.Option("--output", "-o", help="drawing to write: .svg, .png, or .pdf")
    ],
    circuit: Annotated[
        str | None, typer.Option(help="draw only what carries this branch circuit")
    ] = None,
) -> None:
    """Draw the wiring diagram (needs Graphviz's `dot` on the PATH)."""
    fmt = output.suffix.lstrip(".").lower()
    if fmt not in ("svg", "png", "pdf"):
        raise typer.BadParameter(
            "the output must end in .svg, .png, or .pdf", param_hint="--output"
        )
    dot = shutil.which("dot")
    if dot is None:
        raise typer.BadParameter(
            "Graphviz `dot` not found -- install Graphviz (e.g. `brew install graphviz`, "
            "`apt install graphviz`)"
        )
    source = circuit_diagram(House.from_yaml(spec), only=circuit)
    subprocess.run([dot, f"-T{fmt}", "-o", str(output)], input=source, text=True, check=True)
    typer.echo(f"wrote {output}")
