"""Run with python -m tests.storm_replay.replay; dry-run is always the default."""

import argparse
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import math
import re
from pathlib import Path
from typing import Any, Callable

from services.context.contracts import local_time
from services.context.lifecycle import OperationalState
from services.context.snapshot import SnapshotBuilder
from services.events.triggers import AlertHistory, get_alert_events
from services.events.audit import AuditTrail, delivery_decision, safe_text, snapshot_details
from .integration import Runtime, load_runtime
from .presentation import Playback, export_audit


@dataclass
class ReplayResult:
    """Inspect snapshots, events, and delivery outcomes without parsing logs."""

    snapshots: dict[str, Any] = field(default_factory=dict)
    alerts: list[Any] = field(default_factory=list)
    outcomes: list[dict] = field(default_factory=list)
    applied_events: list[dict] = field(default_factory=list)
    audit: AuditTrail = field(default_factory=AuditTrail)
    summary: dict = field(default_factory=dict)
    handler_calls: int = 0
    deferred_outcomes: list[dict] = field(default_factory=list)


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


def simulation_frames(state: OperationalState, times: list[datetime], next_delivery_time=None):
    """Expose each operational report before a later same-time report can erase it."""
    for now in times:
        if next_delivery_time is not None:
            due = next_delivery_time()
            while due is not None and state.sim_time is not None and state.sim_time < due < now:
                yield due, state.advance(due)
                due = next_delivery_time()
        if state.cursor < len(state.events) and state.events[state.cursor]["time"] <= now:
            while state.cursor < len(state.events) and state.events[state.cursor]["time"] <= now:
                yield now, state.advance(now, max_events=1)
        else:
            yield now, state.advance(now)
    if next_delivery_time is not None:
        due = next_delivery_time()
        while due is not None and state.sim_time is not None and due > state.sim_time:
            yield due, state.advance(due)
            due = next_delivery_time()


def run_replay(
    runtime: Runtime, *, step_minutes: int = 10, dry_run: bool = True,
    crews_available: int | None = None, verified_demo_phones: frozenset[str] = frozenset(),
    log: Callable[[str], None] = print, verbose: bool = False, playback: Playback | None = None,
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
    if dry_run and runtime.dependencies.reset_for_replay is not None:
        runtime.dependencies.reset_for_replay()
    playback = playback or Playback()
    last_active_devices: tuple | None = None
    pending_sequences: dict[str, int] = {}
    mode = "DRY-RUN" if dry_run else "LIVE verified team recipients only"
    log(f"{mode}; dependencies={runtime.mode}")
    if runtime.mode == "demo":
        log("OFFLINE FIXTURES: models, analytics, graph adapter, and messaging are simulated; no SMS delivery.")
    log(f"Simulated crews_available={crews_available!r}; unknown damage has no ETR.")
    deferred_support = runtime.dependencies.advance_clock is not None
    log("Deferred delivery: messaging clock drain enabled." if deferred_support else
        "Deferred delivery: UNVERIFIED; no pending-message clock hook is available.")
    if playback.step and not playback.interactive:
        log("Step playback: noninteractive input; continuing without prompts.")
    for now, applied in simulation_frames(state, times, runtime.dependencies.next_delivery_time):
        audit_start = len(result.audit.entries)
        result.applied_events.extend(applied)
        position = runtime.dependencies.storm_position(runtime.storm, now)
        if len(position) != 2 or any(not math.isfinite(value) for value in position):
            raise ValueError(f"Invalid storm position: {position!r}")
        snapshots = builder.build_all_snapshots(runtime.storm, state, result.snapshots)
        for event in applied:
            result.audit.record(now, "operational_event", "diagnostic_noop" if event.get("_diagnostic") else "applied",
                                event.get("_diagnostic", "OPERATIONAL_FACT_APPLIED"), asset_id=event["device_id"],
                                details={"event_type": event["type"], "source_index": event["_source_index"],
                                         "cause": event.get("damage_type")})
        affected = sorted(key for key, snapshot in snapshots.items() if snapshot.status == "outage_confirmed")
        at_risk = sum(snapshot.status == "at_risk" for snapshot in snapshots.values())
        active_devices = tuple(sorted(state.active_failures))
        result.audit.record(now, "replay_step", "evaluated", "SIMULATION_FRAME",
                            details={"position": list(position), "active_devices": list(active_devices),
                                     "affected_customers": affected,
                                     "powered_customers": sorted(set(snapshots) - set(affected))})
        if active_devices != last_active_devices:
            for identifier, snapshot in snapshots.items():
                failures = builder.affected_failures.get(identifier, [])
                result.audit.record(now, "network_trace", "affected" if failures else "powered",
                                    "DOWNSTREAM_OF_FAILED_DEVICE" if failures else (
                                        "NOT_DOWNSTREAM_OF_FAILED_DEVICE" if active_devices else "NO_ACTIVE_FAILURES"),
                                    customer_id=identifier,
                                    details={"active_devices": sorted(f.device_id for f in failures),
                                             "primary_device": builder.primary_failures.get(identifier)})
        last_active_devices = active_devices
        events = []
        for identifier, snapshot in snapshots.items():
            previous = result.snapshots.get(identifier)
            if previous is None or snapshot_details(previous) != snapshot_details(snapshot):
                result.audit.record(now, "snapshot_change", "changed", "SNAPSHOT_INITIALIZED" if previous is None else "SNAPSHOT_UPDATED",
                                    customer_id=identifier, details=snapshot_details(snapshot) | {
                                        "previous_status": previous.status if previous is not None else None,
                                    })
            events.extend(get_alert_events(
                previous, snapshot, now, history,
                alert_model=runtime.dependencies.alert_model, audit=result.audit,
            ))
        pending_due = runtime.dependencies.next_delivery_time() if runtime.dependencies.next_delivery_time is not None else None
        visible = (verbose or bool(applied or events) or not result.snapshots or now == times[-1]
                   or (pending_due is not None and pending_due <= now))
        if visible:
            playback.wait(now)
            log(f"[{now.isoformat(timespec='minutes')}] storm=({position[0]:.4f}, {position[1]:.4f}) "
                f"at_risk={at_risk} outages={len(affected)} affected={','.join(affected) or '-'}")
        for entry in result.audit.entries[audit_start:]:
            prefix = f"[{now.isoformat(timespec='minutes')}]"
            if entry.category == "operational_event":
                log(f"{prefix} {entry.details['event_type'].upper()} {entry.asset_id} reason={entry.reason_code}")
            elif entry.category == "network_trace" and entry.reason_code == "NOT_DOWNSTREAM_OF_FAILED_DEVICE":
                log(f"{prefix} NO_ALERT {entry.customer_id} reason={entry.reason_code}")
            elif entry.category == "alert_decision" and entry.decision == "emitted":
                context = ""
                if entry.alert_type == "pre_storm":
                    context = f" risk={entry.details['risk_score']:.2f} arrival={entry.details['storm_arrival']}"
                elif entry.alert_type == "etr_update":
                    context = f" ETR={entry.details['etr_start']}..{entry.details['etr_end']} confidence={entry.details['confidence']}"
                elif entry.alert_type == "outage_confirmed":
                    context = f" cause={entry.details['cause']}"
                log(f"{prefix} ALERT {entry.alert_type} {entry.customer_id} emitted reason={entry.reason_code}{context}")
            elif verbose and entry.category == "alert_decision":
                log(f"{prefix} DECISION {entry.customer_id} {entry.alert_type} {entry.decision} reason={entry.reason_code}")
        for event in events:
            # This is only a live-recipient boundary. Person 4 still owns consent,
            # throttle, wording, guardrails, and any deferred message handling.
            if not dry_run and (
                event.snapshot.phone not in verified_demo_phones or not event.snapshot.sms_opt_in
            ):
                outcome = {"sent": False, "body": None, "reason": "live_recipient_not_authorized"}
            else:
                result.handler_calls += 1
                try:
                    outcome = runtime.dependencies.handle_alert(event, dry_run=dry_run)
                except Exception:
                    # Preserve the source alert and continue replay. Arbitrary
                    # exception text can contain provider secrets or phone numbers.
                    outcome = {"sent": False, "body": None, "reason": "handler_exception"}
            if (not isinstance(outcome, dict) or type(outcome.get("sent")) is not bool
                    or "body" not in outcome or "reason" not in outcome
                    or (outcome["body"] is not None and not isinstance(outcome["body"], str))
                    or (outcome["reason"] is not None and not isinstance(outcome["reason"], str))):
                raise ValueError("handle_alert must return {sent: bool, body: str|None, reason: str|None}")
            result.alerts.append(event)
            result.outcomes.append(outcome)
            decision, reason = delivery_decision(outcome, dry_run)
            if reason == "MESSAGING_THROTTLED":
                pending_sequences[event.customer_id] = len(result.alerts)
            else:
                pending_sequences.pop(event.customer_id, None)
            entry = result.audit.record(now, "delivery_outcome", decision, reason,
                                        customer_id=event.customer_id, alert_type=event.alert_type,
                                        details={"handler_sent": outcome["sent"], "dry_run": dry_run,
                                                 "body_present": outcome["body"] is not None,
                                                 "body_length": len(outcome["body"] or ""),
                                                 "alert_sequence": len(result.alerts),
                                                 "deferred_support": "AVAILABLE" if deferred_support else "UNVERIFIED"})
            log(f"[{now.isoformat(timespec='minutes')}] DELIVERY {entry.customer_id} {event.alert_type} "
                f"mode={'dry-run' if dry_run else 'live'} handler_sent={outcome['sent']} "
                f"decision={decision} reason={reason}")
        if runtime.dependencies.advance_clock is not None:
            for deferred in runtime.dependencies.advance_clock(now, snapshots, dry_run=dry_run):
                event, outcome = deferred["event"], deferred["outcome"]
                result.handler_calls += 1
                result.deferred_outcomes.append(deferred)
                decision, reason = delivery_decision(outcome, dry_run)
                entry = result.audit.record(now, "deferred_delivery_outcome", decision, reason,
                                            customer_id=event.customer_id, alert_type=event.alert_type,
                                            details={"handler_sent": outcome["sent"], "dry_run": dry_run,
                                                     "alert_sequence": pending_sequences.pop(event.customer_id, None),
                                                     "deferred_support": "AVAILABLE"})
                log(f"[{now.isoformat(timespec='minutes')}] DEFERRED_DELIVERY {entry.customer_id} {event.alert_type} "
                    f"handler_sent={outcome['sent']} reason={reason}")
        result.snapshots = snapshots
    unresolved = sorted(state.active_failures)
    delivery_counts = Counter(entry.reason_code for entry in result.audit.entries
                              if entry.category in ("delivery_outcome", "deferred_delivery_outcome"))
    all_outcomes = result.outcomes + [row["outcome"] for row in result.deferred_outcomes]
    result.summary = {
        "operational_events": len(result.applied_events), "alerts_emitted": len(result.alerts),
        "alerts_by_type": dict(sorted(Counter(event.alert_type for event in result.alerts).items())),
        "alerts_by_customer": dict(sorted(Counter(event.customer_id for event in result.alerts).items())),
        "handler_calls": result.handler_calls,
        "handler_reported_sent": sum(outcome["sent"] for outcome in all_outcomes),
        "successful_dry_runs": sum(outcome["sent"] for outcome in all_outcomes) if dry_run else 0,
        "not_sent": sum(not outcome["sent"] for outcome in all_outcomes),
        "deferred_deliveries": len(result.deferred_outcomes),
        "deferred_support": "AVAILABLE" if deferred_support else "UNVERIFIED",
        "delivery_reason_counts": dict(sorted(delivery_counts.items())),
        "ever_affected": sorted({event.customer_id for event in result.alerts if event.alert_type == "outage_confirmed"}),
        "restored_customers": sorted(key for key, snapshot in result.snapshots.items() if snapshot.status == "restored"),
        "powered_customers": sorted(key for key, snapshot in result.snapshots.items() if snapshot.status != "outage_confirmed"),
        "active_failures": unresolved,
    }
    log(f"Replay complete: {len(result.applied_events)} operational events, {len(result.alerts)} alerts; "
        f"active_failures={','.join(unresolved) or 'none'}")
    log(f"SUMMARY alerts_by_type={result.summary['alerts_by_type']}")
    log(f"SUMMARY affected={','.join(result.summary['ever_affected']) or '-'} "
        f"restored={','.join(result.summary['restored_customers']) or '-'} "
        f"handler_calls={result.handler_calls} successful_dry_runs={result.summary['successful_dry_runs']} "
        f"not_sent={result.summary['not_sent']} outcomes={result.summary['delivery_reason_counts']}")
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
    parser.add_argument("--verbose", action="store_true", help="Explain every candidate alert for every customer/frame")
    parser.add_argument("--speed", choices=("instant", "fast", "normal"), default="instant",
                        help="Wall-clock presentation delays only; simulated time is unchanged")
    parser.add_argument("--step", action="store_true", help="Enter advances visible frames; noninteractive runs never prompt")
    parser.add_argument("--audit-json", type=Path, help="Create a sanitized audit report; existing files are preserved")
    parser.add_argument("--crews-available", type=int, default=1,
                        help="Simulated crew-count assumption (default: 1); never a live crew inventory")
    args = parser.parse_args(argv)
    try:
        if args.audit_json is not None and args.audit_json.exists():
            raise ValueError("Audit output already exists; choose a new path to preserve existing work")
        runtime = load_runtime("demo" if args.demo else "integrated" if args.integrated or args.live else "auto")
        crews = args.crews_available
        if runtime.mode == "demo" and crews is None:
            crews = 1  # Labeled fixture assumption only; not an upstream crew inventory.
        result = run_replay(runtime, step_minutes=args.step_minutes, dry_run=not args.live,
                            crews_available=crews, verified_demo_phones=frozenset(args.verified_demo_phone),
                            verbose=args.verbose, playback=Playback(speed=args.speed, step=args.step))
        if args.audit_json is not None:
            export_audit(args.audit_json, result, mode=runtime.mode, dry_run=not args.live)
            print("Sanitized audit JSON created.")
    except (ValueError, ImportError, AttributeError, KeyError, TypeError, OSError) as error:
        parser.exit(2, f"Replay error: {safe_text(str(error))}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
