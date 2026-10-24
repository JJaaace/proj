"""Section 7 alert conditions, without composing, filtering, or throttling SMS."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable

from services.context.contracts import construct_model, local_time, validate_snapshot
from .audit import AuditTrail, snapshot_details


@dataclass
class CustomerAlertHistory:
    """Retain once-per-customer and once-per-outage trigger history."""

    warned: bool = False
    outage_open: bool = False
    occurrence: int = 0
    crew_alerted: bool = False
    restored_alerted: bool = False
    last_evaluation: tuple | None = None


@dataclass
class AlertHistory:
    """Replay-local alert history; never shared between independent runs."""

    customers: dict[str, CustomerAlertHistory] = field(default_factory=dict)


def _etr_changed(previous: Any, current: Any) -> bool:
    """Compare the immediate prior estimate using the strict >60 minute rule."""
    if previous.confidence != current.confidence:
        return True
    if current.etr_start is None or current.etr_end is None:
        return False
    if previous.etr_start is None or previous.etr_end is None:
        return True
    return any(
        abs(local_time(getattr(current, name)) - local_time(getattr(previous, name)))
        > timedelta(minutes=60)
        for name in ("etr_start", "etr_end")
    )


def _etr_reason(previous: Any, current: Any) -> str:
    """Explain the same ETR rule used for event generation, with stable reason precedence."""
    if (current.etr_start is not None and current.etr_end is not None
            and (previous.etr_start is None or previous.etr_end is None)):
        return "ETR_FIRST_AVAILABLE"
    if previous.confidence != current.confidence:
        return "ETR_CONFIDENCE_CHANGED"
    return "ETR_BOUND_SHIFT_OVER_60_MIN" if _etr_changed(previous, current) else "NO_MEANINGFUL_ETR_CHANGE"


def _audit_decisions(
    audit: AuditTrail | None, previous: Any, current: Any, sim_time: datetime,
    history: CustomerAlertHistory, emitted: list[str], *, duplicate: bool = False,
) -> None:
    """Explain each candidate type without implementing any messaging delivery policy."""
    if audit is None:
        return
    before = previous.status if previous is not None else None
    arrival = local_time(current.storm_arrival) if current.storm_arrival is not None else None
    warning_reason = (
        "LOW_RISK" if current.risk_score < .5 else
        "STORM_ARRIVAL_UNKNOWN" if arrival is None else
        "STORM_TOO_DISTANT" if arrival - sim_time > timedelta(hours=12) else
        "STORM_ALREADY_ARRIVED" if arrival < sim_time else
        "NOT_AT_RISK" if current.status != "at_risk" else
        "DUPLICATE_EVENT_SUPPRESSED" if history.warned else
        "NO_STATUS_CHANGE" if current.status == before else "NOT_AT_RISK"
    )
    reasons = {
        "pre_storm": "RISK_THRESHOLD_MET" if "pre_storm" in emitted else warning_reason,
        "outage_confirmed": (
            "DOWNSTREAM_OF_FAILED_DEVICE" if "outage_confirmed" in emitted else
            "FIRST_SNAPSHOT_BASELINE" if previous is None else
            "ALREADY_IN_OUTAGE" if current.status == "outage_confirmed" else "NO_CONFIRMED_OUTAGE"
        ),
        "crew_assigned": (
            "CREW_ASSIGNED_NOW" if "crew_assigned" in emitted else
            "NO_CONFIRMED_OUTAGE" if current.status != "outage_confirmed" else
            "FIRST_SNAPSHOT_BASELINE" if previous is None else
            "DUPLICATE_EVENT_SUPPRESSED" if history.crew_alerted and current.crew_status is not None else
            "CREW_ALREADY_KNOWN" if previous.crew_status is not None else "NO_CREW_ASSIGNMENT"
        ),
        "etr_update": (
            _etr_reason(previous, current) if "etr_update" in emitted else
            "NO_CONFIRMED_OUTAGE" if current.status != "outage_confirmed" else
            "FIRST_SNAPSHOT_BASELINE" if previous is None else "NO_MEANINGFUL_ETR_CHANGE"
        ),
        "restored": "RESTORATION_CONFIRMED" if "restored" in emitted else "NO_RESTORATION_TRANSITION",
    }
    details = snapshot_details(current) | {
        "previous_status": before, "outage_occurrence": history.occurrence,
        "arrival_delta_minutes": None if arrival is None else (arrival - sim_time).total_seconds() / 60,
        "previous_etr_start": previous.etr_start if previous is not None else None,
        "previous_etr_end": previous.etr_end if previous is not None else None,
        "previous_confidence": previous.confidence if previous is not None else None,
    }
    for name in ("etr_start", "etr_end"):
        old = getattr(previous, name) if previous is not None else None
        new = getattr(current, name)
        details[f"{name}_shift_minutes"] = None if old is None or new is None else (
            local_time(new) - local_time(old)
        ).total_seconds() / 60
    for kind, reason in reasons.items():
        decision = "emitted" if kind in emitted else "not_applicable"
        if duplicate or reason == "DUPLICATE_EVENT_SUPPRESSED":
            decision, reason = "suppressed_duplicate", "DUPLICATE_EVENT_SUPPRESSED"
        audit.record(sim_time, "alert_decision", decision, reason,
                     customer_id=current.customer_id, alert_type=kind, details=details)


def get_alert_events(
    previous_snapshot: Any, snapshot: Any, sim_time: datetime,
    alert_history: AlertHistory, *, alert_model: Callable[..., Any], audit: AuditTrail | None = None,
) -> list[Any]:
    """Emit typed, ordered events and suppress repeated transition evaluation."""
    sim_time = local_time(sim_time)
    validate_snapshot(snapshot)
    if local_time(snapshot.updated_at) != sim_time:
        raise ValueError("Snapshot updated_at must match simulated alert time")
    if previous_snapshot is not None and previous_snapshot.customer_id != snapshot.customer_id:
        raise ValueError("Cannot compare snapshots for different customers")
    if previous_snapshot is not None:
        validate_snapshot(previous_snapshot)
        if local_time(previous_snapshot.updated_at) > sim_time:
            raise ValueError("Previous snapshot cannot come from the future")
    history = alert_history.customers.setdefault(snapshot.customer_id, CustomerAlertHistory())
    marker = (sim_time, snapshot.status, snapshot.crew_status, snapshot.cause,
              snapshot.etr_start, snapshot.etr_end, snapshot.confidence,
              snapshot.risk_score, snapshot.storm_arrival,
              None if previous_snapshot is None else (
                  previous_snapshot.status, previous_snapshot.crew_status, previous_snapshot.cause,
                  previous_snapshot.etr_start, previous_snapshot.etr_end, previous_snapshot.confidence,
              ))
    if marker == history.last_evaluation:
        _audit_decisions(audit, previous_snapshot, snapshot, sim_time, history, [], duplicate=True)
        return []
    history.last_evaluation = marker
    previous = previous_snapshot
    previous_status = previous.status if previous is not None else None
    types = []
    arrival = local_time(snapshot.storm_arrival) if snapshot.storm_arrival is not None else None
    if (snapshot.status == "at_risk" and previous_status != "at_risk"
            and snapshot.risk_score >= 0.5 and arrival is not None
            and timedelta(0) <= arrival - sim_time <= timedelta(hours=12)
            and not history.warned):
        types.append("pre_storm")
        history.warned = True
    if snapshot.status == "outage_confirmed":
        new_outage = not history.outage_open
        if new_outage:
            history.occurrence += 1
            history.outage_open = True
            history.crew_alerted = False
            history.restored_alerted = False
        # A first snapshot establishes state; it cannot prove a transition.
        if new_outage and previous is not None and previous_status != "outage_confirmed":
            types.append("outage_confirmed")
        if (previous is not None and previous.crew_status is None
                and snapshot.crew_status in ("assigned", "on_site")
                and not history.crew_alerted):
            types.append("crew_assigned")
            history.crew_alerted = True
        if previous is not None and _etr_changed(previous, snapshot):
            types.append("etr_update")
    if (previous_status == "outage_confirmed" and snapshot.status == "restored"
            and not history.restored_alerted):
        types.append("restored")
        history.restored_alerted = True
        history.outage_open = False
    events = [construct_model(alert_model,
        alert_type=kind, customer_id=snapshot.customer_id, snapshot=snapshot,
        previous_snapshot=previous, sim_time=sim_time,
    ) for kind in types]
    _audit_decisions(audit, previous, snapshot, sim_time, history, types)
    return events
