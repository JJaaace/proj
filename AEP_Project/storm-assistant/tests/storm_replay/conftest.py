"""Source-shaped offline dependencies shared by Person 3 tests."""

from datetime import datetime

import pytest

from .demo import DemoSnapshot
from .integration import load_runtime


@pytest.fixture
def runtime():
    """Use explicitly simulated dependencies, never upstream or live messaging."""
    return load_runtime("demo")


@pytest.fixture
def now():
    """Provide a local simulated clock unrelated to the machine's current time."""
    return datetime(2026, 10, 24, 18)


@pytest.fixture
def snapshot(now):
    """Provide a full 17-field snapshot for transition tests."""
    return DemoSnapshot(
        "C-1", "Demo One", "+16145550101", "en", True, True,
        "FDR-1", "TX-17", "normal", 0.8, now, None, None, None, None, None, now,
    )
