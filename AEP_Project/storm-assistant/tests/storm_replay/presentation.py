"""Presenter-only controls and sanitized export; never calculate customer state."""

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import sys
import time
from typing import Callable

from services.events.audit import safe_value


@dataclass
class Playback:
    """Wall-clock pacing independent of simulated timestamps and alert rules."""

    speed: str = "instant"
    step: bool = False
    interactive: bool | None = None
    sleep: Callable[[float], None] = time.sleep
    read: Callable[[str], str] = input
    frames: int = 0

    def __post_init__(self) -> None:
        """Validate presets and fall back to noninteractive playback in pipelines."""
        if self.speed not in ("instant", "fast", "normal"):
            raise ValueError("speed must be instant, fast, or normal")
        if self.interactive is None:
            self.interactive = sys.stdin.isatty()

    def wait(self, sim_time: datetime) -> None:
        """Wait only between visible frames; never change the supplied domain clock."""
        if self.step and self.interactive:
            try:
                self.read(f"Enter for simulated {sim_time.isoformat(timespec='minutes')}: ")
            except EOFError:
                self.interactive = False
        elif self.frames:
            delay = {"instant": 0, "fast": .05, "normal": .3}[self.speed]
            if delay:
                self.sleep(delay)
        self.frames += 1


def export_audit(path: Path, result, *, mode: str, dry_run: bool) -> None:
    """Create a sanitized JSON report exclusively; never overwrite existing work."""
    document = {
        "format_version": 1, "mode": mode, "dry_run": dry_run,
        "notification_delivery": "Handler reports only; no carrier delivery receipts",
        "deferred_delivery": result.summary.get("deferred_support", "UNVERIFIED"),
        "summary": result.summary, "entries": result.audit.to_records(),
    }
    with path.open("x", encoding="utf-8") as destination:
        json.dump(safe_value(document), destination, indent=2, allow_nan=False)
        destination.write("\n")
