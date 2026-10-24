"""Section 7 alert conditions, without composing, filtering, or throttling SMS."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable

from services.context.contracts import local_time


@dataclass
class CustomerAlertHistory:
    """Retain once-per-customer and once-per-outage trigger history."""

    warned: bool = False
    outage_open: bool = False
    occurrence: int = 0
    crew_alerted: bool = False
    restored_alerted: bool = False
    evaluated: set[tuple] = field(default_factory=set)


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


def get_alert_events(
    previous_snapshot: Any, snapshot: Any, sim_time: datetime,
    alert_history: AlertHistory, *, alert_model: Callable[..., Any],
) -> list[Any]:
    """Emit typed, ordered events and suppress repeated transition evaluation."""
    sim_time = local_time(sim_time)
    if local_time(snapshot.updated_at) != sim_time:
        raise ValueError("Snapshot updated_at must match simulated alert time")
    if previous_snapshot is not None and previous_snapshot.customer_id != snapshot.customer_id:
        raise ValueError("Cannot compare snapshots for different customers")
    history = alert_history.customers.setdefault(snapshot.customer_id, CustomerAlertHistory())
    marker = (sim_time, snapshot.status, snapshot.crew_status, snapshot.cause,
              snapshot.etr_start, snapshot.etr_end, snapshot.confidence,
              snapshot.risk_score, snapshot.storm_arrival)
    if marker in history.evaluated:
        return []
    history.evaluated.add(marker)
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
    return [alert_model(
        alert_type=kind, customer_id=snapshot.customer_id, snapshot=snapshot,
        previous_snapshot=previous, sim_time=sim_time,
    ) for kind in types]
