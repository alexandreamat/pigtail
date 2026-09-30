from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from pigtail.models.house import House

EXAMPLE = Path(__file__).parent.parent / "examples" / "switch_loop.yaml"


@pytest.fixture
def house() -> House:
    """The switch-loop example, parsed and assembled (from_yaml builds it)."""
    return House.from_yaml(EXAMPLE)


@pytest.fixture
def load_example() -> Callable[[], House]:
    def _load() -> House:
        return House.from_yaml(EXAMPLE)

    return _load
