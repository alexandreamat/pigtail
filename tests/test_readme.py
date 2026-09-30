"""The README's quickstart is the real thing: its YAML is examples/quickstart.yaml,
its check output is what pigtail reports, and the draw command writes the drawing.
"""

from __future__ import annotations

import re
import shutil
import warnings
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pigtail.cli import app
from pigtail.models.house import House
from pigtail.nec import NECViolation

ROOT = Path(__file__).parent.parent
README = (ROOT / "README.md").read_text()
QUICKSTART = ROOT / "examples" / "quickstart.yaml"


def test_readme_yaml_is_the_quickstart_example() -> None:
    block = re.search(r"```yaml\n(.*?)```", README, re.S)
    assert block is not None
    assert block.group(1) == QUICKSTART.read_text()


def test_readme_check_output_is_what_pigtail_reports() -> None:
    block = re.search(r"\$ pigtail check examples/quickstart.yaml\n(.*?)\n\n", README, re.S)
    assert block is not None
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        House.from_yaml(QUICKSTART).check()
    found = [str(w.message) for w in caught if issubclass(w.category, NECViolation)]
    assert block.group(1).splitlines() == found


@pytest.mark.skipif(shutil.which("dot") is None, reason="Graphviz is not installed")
def test_draw_writes_the_drawing(tmp_path: Path) -> None:
    out = tmp_path / "quickstart.svg"
    result = CliRunner().invoke(app, ["draw", str(QUICKSTART), "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert out.read_text().lstrip().startswith(("<?xml", "<!DOCTYPE", "<svg"))
