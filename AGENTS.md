# AGENTS.md — pigtail

Notes for whoever (person or agent) changes this code. Read this file and the docstrings of the
file you are editing — not the whole tree. User-facing documentation is [README.md](README.md).

## Layout

```
src/pigtail/
  cli.py            Typer entry point: build, check, draw, bom
  nec.py            the warn-only NEC checks (NECViolation / NECUnchecked warnings)
  nec_tables.py     every NEC number the checks use, named after its table or section
  trace.py          which circuit each conductor, run and device is on, from the wiring
  raceway.py        conduit fill, current-carrying conductors, ampacity, loads, voltage drop
  fill.py           box fill (314.16), shared by the check, the BOM and the drawing
  bom.py            House.bom() -- the bill of materials
  models/
    types.py        every Literal alias, named (no inline Literal but for discriminators)
    _base.py        BaseModel (extra=forbid), BuildError, require(), join(), _make_part()
    _dot.py         shared Graphviz primitives
    box device conductor cable circuit panelboard house   -- one file per domain
  outputs/diagram.py   circuit_diagram(house, only=) -- the one drawing
examples/           runnable YAML; quickstart.yaml is the README's example
docs/quickstart.svg the README's drawing: `pigtail draw examples/quickstart.yaml -o docs/quickstart.svg`
```

## Rules

- **The YAML is topology only.** Runs, boxes, splices, devices, landings. Nothing declares a
  wire's or run's circuit; `trace.py` derives it. A conductor's `role` is declared (intent) and
  checked against the wiring.
- **Every NEC value comes from `nec_tables.py`**, named after its table (`TABLE_310_16`,
  `CHAPTER_9_TABLE_4`, `SECTION_240_4_D`). No literal numbers in checks.
- **Missing data is reported, never guessed.** A check that lacks a value yields
  `nec.Unchecked(message)` (raised as `NECUnchecked`); a model field that may be unknown is
  optional (`None` = not recorded).
- **Messages read `<section>: <subject> -- <detail>`**, in the Code's terms ("box volume",
  "box fill", "in.³").
- **Pydantic models are the domain model.** No mirrored dataclasses; behaviour lives on the
  models; SKiDL objects are eager `@cached_property`, forced in `model_post_init`.
- **SKiDL owns electrical connectivity** (nets, merges, netlist); pigtail owns everything else.
- Python 3.13. PEP 695 `type X = ...` aliases, all in `types.py`. `X | None` only when `None`
  is a real domain value. Never `getattr` to reach a field: devices expose typed methods
  (e.g. `demand_va()`).
- Errors → raise (`BuildError`); never return `None`/`False` for failure.
- All imports at module top level. No `__all__`. No re-export `__init__.py`.
- The drawing's layout, ports and spacing are settled; change them only on request.
- Nothing about a particular house belongs in this repo.

## Adding a check

A generator in `nec.py` yielding one message per violation (or `Unchecked(...)`), listed in
`_CHECKS`, with a test in `tests/`.

## Gate

```bash
uv run ruff check --fix && uv run ruff format && uv run mypy && uv run pytest -q
```

After a change to the drawing or `examples/quickstart.yaml`, regenerate
`docs/quickstart.svg` and the README's check output. The README loads the drawing from GitHub
(`main`), so PyPI shows it too.

## Releasing

Bump `version` in `pyproject.toml`, commit, and tag the bare version (`0.1.1`, no `v`); push the
branch and the tag, then `uv build` and `uv publish`.
