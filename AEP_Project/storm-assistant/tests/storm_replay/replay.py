"""Run with python -m tests.storm_replay.replay; dry-run is always the default."""

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import math
import re
from typing import Any, Callable

from services.context.contracts import local_time
from services.context.lifecycle import OperationalState
from services.context.snapshot import SnapshotBuilder
from services.events.triggers import AlertHistory, get_alert_events
from .integration import Runtime, load_runtime


@dataclass
class ReplayResult:
    """Inspect snapshots, events, and delivery outcomes without parsing logs."""

    snapshots: dict[str, Any] = field(default_factory=dict)
    alerts: list[Any] = field(default_factory=list)
    outcomes: list[dict] = field(default_factory=list)
    applied_events: list[dict] = field(default_factory=list)


def simulation_times(state: OperationalState, storm: dict, step_minutes: int) -> list[datetime]:
    """Include exact event times so short failures between regular ticks survive."""
    if type(step_minutes) is not int or step_minutes <= 0:
        raise ValueError("step_minutes must be a positive integer")
    step = timedelta(minutes=step_minutes)
    event_times = [event["time"] for event in state.events]
    storm_start = local_time(storm["start_time"])
    start = min([storm_start, *event_times]) - step
    end = max([storm_start, *event_times]) + step
    times = set(event_times)
    now = start
    while now <= end:
        times.add(now)
        now += step
    times.add(end)
    return sorted(times)


def run_replay(
    runtime: Runtime, *, step_minutes: int = 10, dry_run: bool = True,
    crews_available: int | None = None, verified_demo_phones: frozenset[str] = frozenset(),
    log: Callable[[str], None] = print,
) -> ReplayResult:
    """Replay facts in order and pass every emitted event to the message boundary."""
    if type(dry_run) is not bool:
        raise ValueError("dry_run must be a boolean")
    if not dry_run:
        if runtime.mode != "integrated" or not verified_demo_phones:
            raise ValueError("Live mode needs real integrations and explicit verified team demo phones")
        if any(not re.fullmatch(r"\+[1-9]\d{7,14}", phone) for phone in verified_demo_phones):
            raise ValueError("Verified demo phones must use E.164 format")
    state = OperationalState(runtime.timeline, runtime.town.device_ids)
    builder = SnapshotBuilder(runtime.town, runtime.dependencies, crews_available=crews_available)
    times = simulation_times(state, runtime.storm, step_minutes)
    history, result = AlertHistory(), ReplayResult()
    mode = "DRY-RUN" if dry_run else "LIVE verified team recipients only"
    log(f"{mode}; dependencies={runtime.mode}")
    if runtime.mode == "demo":
        log("OFFLINE FIXTURES: models, analytics, graph adapter, and messaging are simulated; no SMS delivery.")
    log(f"Simulated crews_available={crews_available!r}; unknown damage has no ETR.")
    for now in times:
        applied = state.advance(now)
        result.applied_events.extend(applied)
        position = runtime.dependencies.storm_position(runtime.storm, now)
        if len(position) != 2 or any(not math.isfinite(value) for value in position):
            raise ValueError(f"Invalid storm position: {position!r}")
        snapshots = builder.build_all_snapshots(runtime.storm, state, result.snapshots)
        for event in applied:
            details = " ".join(f"{key}={event[key]}" for key in ("damage_type", "crew_id") if key in event)
            log(f"[{now.isoformat(timespec='minutes')}] {event['type']} {event['device_id']} {details}".rstrip())
        affected = sorted(key for key, snapshot in snapshots.items() if snapshot.status == "outage_confirmed")
        at_risk = sum(snapshot.status == "at_risk" for snapshot in snapshots.values())
        log(f"[{now.isoformat(timespec='minutes')}] storm=({position[0]:.4f}, {position[1]:.4f}) "
            f"at_risk={at_risk} outages={len(affected)} affected={','.join(affected) or '-'}")
        events = []
        for identifier, snapshot in snapshots.items():
            events.extend(get_alert_events(
                result.snapshots.get(identifier), snapshot, now, history,
                alert_model=runtime.dependencies.alert_model,
            ))
        for event in events:
            # This is only a live-recipient boundary. Person 4 still owns consent,
            # throttle, wording, guardrails, and any deferred message handling.
            if not dry_run and (
                event.snapshot.phone not in verified_demo_phones or not event.snapshot.sms_opt_in
            ):
                outcome = {"sent": False, "body": None, "reason": "live_recipient_not_authorized"}
            else:
                outcome = runtime.dependencies.handle_alert(event, dry_run=dry_run)
            if (not isinstance(outcome, dict) or type(outcome.get("sent")) is not bool
                    or "body" not in outcome or "reason" not in outcome
                    or (outcome["body"] is not None and not isinstance(outcome["body"], str))
                    or (outcome["reason"] is not None and not isinstance(outcome["reason"], str))):
                raise ValueError("handle_alert must return {sent: bool, body: str|None, reason: str|None}")
            result.alerts.append(event)
            result.outcomes.append(outcome)
            log(f"[{now.isoformat(timespec='minutes')}] ALERT {event.alert_type} {event.customer_id} "
                f"mode={'dry-run' if dry_run else 'live'} handler_sent={outcome['sent']} "
                f"reason={outcome['reason']!r} body={outcome['body']!r}")
        result.snapshots = snapshots
    unresolved = sorted(state.active_failures)
    log(f"Replay complete: {len(result.applied_events)} operational events, {len(result.alerts)} alerts; "
        f"active_failures={','.join(unresolved) or 'none'}")
    return result


def main(argv: list[str] | None = None) -> int:
    """Parse the only live opt-in and return useful errors for missing integrations."""
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--demo", action="store_true", help="Use explicitly simulated offline fixtures")
    mode.add_argument("--integrated", action="store_true", help="Require real team modules and sample files")
    parser.add_argument("--live", action="store_true", help="Intentionally send to verified opted-in team demo phones")
    parser.add_argument("--verified-demo-phone", action="append", default=[], metavar="E164",
                        help="Attest this recipient is team-controlled, verified, opted-in; repeat for each phone")
    parser.add_argument("--step-minutes", type=int, default=10)
    parser.add_argument("--crews-available", type=int, default=None,
                        help="Explicit simulated crew-count assumption; absent disables integrated ETRs")
    args = parser.parse_args(argv)
    try:
        runtime = load_runtime("demo" if args.demo else "integrated" if args.integrated or args.live else "auto")
        crews = args.crews_available
        if runtime.mode == "demo" and crews is None:
            crews = 1  # Labeled fixture assumption only; not an upstream crew inventory.
        run_replay(runtime, step_minutes=args.step_minutes, dry_run=not args.live,
                   crews_available=crews, verified_demo_phones=frozenset(args.verified_demo_phone))
    except (ValueError, ImportError, AttributeError, KeyError, TypeError, OSError) as error:
        parser.exit(2, f"Replay error: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
