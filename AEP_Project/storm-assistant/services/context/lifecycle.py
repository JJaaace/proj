"""Authoritative operational failures and deterministic customer lifecycle."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable

from .contracts import DAMAGE_TYPES, EVENT_TYPES, local_time


def customer_status(
    previous_status: str | None, *, affected: bool, risk_score: float,
    storm_arrival: datetime | None, sim_time: datetime, in_wind_zone: bool = False,
) -> str:
    """Keep outages operational, restoration sticky, and warnings evidence based."""
    if affected:
        return "outage_confirmed"
    if previous_status in ("outage_confirmed", "restored"):
        return "restored"
    # For this MVP, an unoutaged at-risk customer retains that state after passage.
    if previous_status == "at_risk":
        return "at_risk"
    imminent = storm_arrival is not None and (
        timedelta(0) <= storm_arrival - sim_time <= timedelta(hours=12)
        or (storm_arrival <= sim_time and in_wind_zone)
    )
    return "at_risk" if risk_score >= 0.5 and imminent else "normal"


@dataclass
class Failure:
    """Facts for one active incident; estimates are cached by input revision."""

    device_id: str
    started_at: datetime
    damage_type: str = "unknown"
    crew_id: str | None = None
    crew_status: str | None = None
    revised_at: datetime | None = None
    revision: int = 0
    estimate_key: tuple | None = None
    estimate: Any = None


class OperationalState:
    """Apply a validated, stably sorted timeline once, including repeated ticks."""

    def __init__(self, timeline: list[dict], device_ids: set[str]) -> None:
        """Validate the whole timeline before any replay or delivery begins."""
        self.events = []
        for source_index, raw in enumerate(timeline):
            event = dict(raw)
            event["_source_index"] = source_index
            event["time"] = local_time(event["time"])
            kind, device = event.get("type"), event.get("device_id")
            if kind not in EVENT_TYPES:
                raise ValueError(f"Unexpected timeline event type: {kind!r}")
            if device not in device_ids:
                raise ValueError(f"Unknown timeline device ID: {device!r}")
            if kind in ("device_failed", "damage_assessed"):
                damage = event.get("damage_type", "unknown")
                if damage not in DAMAGE_TYPES:
                    raise ValueError(f"{device}: invalid damage_type={damage!r}")
                event["damage_type"] = damage
            if kind.startswith("crew_") and not event.get("crew_id"):
                raise ValueError(f"{kind} for {device} requires crew_id")
            self.events.append(event)
        self.events.sort(key=lambda event: event["time"])
        self.active_failures: dict[str, Failure] = {}
        self.cursor = 0
        self.sim_time: datetime | None = None
        # Validate sequencing before the first alert can be dispatched.
        active: set[str] = set()
        restored: set[str] = set()
        for event in self.events:
            kind, device = event["type"], event["device_id"]
            if kind == "device_failed":
                if device in active:
                    event["_diagnostic"] = "DUPLICATE_FAILURE_REPORT"
                active.add(device)
            elif kind == "device_restored" and device in restored and device not in active:
                event["_diagnostic"] = "DUPLICATE_RESTORATION_REPORT"
            elif device not in active:
                raise ValueError(f"{kind} references inactive failure {device}")
            elif kind == "device_restored":
                active.remove(device)
                restored.add(device)

    def advance(self, sim_time: datetime, *, max_events: int | None = None) -> list[dict]:
        """Apply all not-yet-consumed events at or before a monotonic clock."""
        sim_time = local_time(sim_time)
        if self.sim_time is not None and sim_time < self.sim_time:
            raise ValueError("Replay clock cannot move backwards")
        if max_events is not None and (type(max_events) is not int or max_events < 1):
            raise ValueError("max_events must be a positive integer or None")
        applied = []
        while self.cursor < len(self.events) and self.events[self.cursor]["time"] <= sim_time:
            event = self.events[self.cursor]
            device, kind = event["device_id"], event["type"]
            if event.get("_diagnostic"):
                pass  # Consume duplicate reports without resetting or removing an incident.
            elif kind == "device_failed":
                self.active_failures[device] = Failure(
                    device, event["time"], event["damage_type"], revised_at=event["time"],
                )
            elif kind == "device_restored":
                del self.active_failures[device]
            else:
                failure = self.active_failures[device]
                before = (failure.damage_type, failure.crew_id, failure.crew_status)
                if kind == "damage_assessed":
                    failure.damage_type = event["damage_type"]
                else:
                    failure.crew_id = event["crew_id"]
                    failure.crew_status = "assigned" if kind == "crew_assigned" else "on_site"
                if before != (failure.damage_type, failure.crew_id, failure.crew_status):
                    failure.revision += 1
                    failure.revised_at = event["time"]
            applied.append(event)
            self.cursor += 1
            if max_events is not None and len(applied) >= max_events:
                break
        self.sim_time = sim_time
        return applied

    def affected_customers(
        self, downstream_customers: Callable[[str], list[str]], customer_ids: set[str],
    ) -> dict[str, list[Failure]]:
        """Trace each active device through network connectivity, never distance."""
        affected: dict[str, list[Failure]] = {}
        for failure in self.active_failures.values():
            for customer_id in sorted(set(downstream_customers(failure.device_id))):
                if customer_id not in customer_ids:
                    raise ValueError(f"Network returned unknown customer {customer_id!r}")
                affected.setdefault(customer_id, []).append(failure)
        return affected
