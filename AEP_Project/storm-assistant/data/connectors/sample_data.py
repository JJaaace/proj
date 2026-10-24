"""Load the bundled synthetic town and storm data."""

import json
from pathlib import Path
from typing import Any

SAMPLE_DIRECTORY = Path(__file__).resolve().parents[1] / "sample"
SAMPLE_FILES = (
    "substations",
    "feeders",
    "transformers",
    "customers",
    "storm",
    "storm_timeline",
)


def load_sample_data() -> dict[str, Any]:
    """Load and return all sample JSON documents by name."""
    return {
        name: json.loads(
            (SAMPLE_DIRECTORY / f"{name}.json").read_text(encoding="utf-8")
        )
        for name in SAMPLE_FILES
    }
