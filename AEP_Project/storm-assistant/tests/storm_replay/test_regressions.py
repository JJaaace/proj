"""P0 regressions found while auditing the committed Person 3 implementation."""

from collections import Counter
from dataclasses import replace
from datetime import timedelta

import pytest

from services.context.lifecycle import OperationalState
from services.context.snapshot import SnapshotBuilder
from services.events.triggers import AlertHistory, get_alert_events
from .demo import DemoAlert
from .replay import run_replay
from .test_lifecycle import operation


def test_same_timestamp_cycles_remain_observable(runtime, now):
    """Failure, restoration, and a new failure at one time retain source order."""
    timeline = [operation(now, "device_failed"), operation(now, "device_restored"),
                operation(now, "device_failed"), operation(now, "device_restored")]
    result = run_replay(replace(runtime, timeline=timeline), log=lambda line: None)
    types = [event.alert_type for event in result.alerts if event.customer_id == "C-1"]
    assert types == ["pre_storm", "outage_confirmed", "restored", "outage_confirmed", "restored"]


def test_duplicate_network_ids_do_not_hide_cause(runtime, now):
    """An accidental duplicate trace entry still represents one failed device."""
    original = runtime.dependencies.downstream_customers
    deps = replace(runtime.dependencies, downstream_customers=lambda device: original(device) * 2)
    state = OperationalState([operation(now, "device_failed", damage_type="blown_fuse")], runtime.town.device_ids)
    state.advance(now)
    snapshots = SnapshotBuilder(runtime.town, deps, crews_available=1).build_all_snapshots(runtime.storm, state, {})
    assert snapshots["C-1"].cause == "blown_fuse"
    assert snapshots["C-1"].etr_start is not None


def test_known_but_electrically_unrelated_network_customer_rejected(runtime, now):
    """A valid customer ID is insufficient if the network trace contradicts its wiring."""
    deps = replace(runtime.dependencies, downstream_customers=lambda device: ["C-3"])
    state = OperationalState([operation(now, "device_failed")], runtime.town.device_ids)
    state.advance(now)
    with pytest.raises(ValueError, match="electrical"):
        SnapshotBuilder(runtime.town, deps).build_all_snapshots(runtime.storm, state, {})


def test_future_previous_snapshot_rejected(snapshot):
    """A trigger cannot use a future assessment as its previous known state."""
    previous = replace(snapshot, updated_at=snapshot.updated_at + timedelta(minutes=1))
    with pytest.raises(ValueError, match="future"):
        get_alert_events(previous, replace(snapshot, status="outage_confirmed"), snapshot.updated_at,
                         AlertHistory(), alert_model=DemoAlert)


@pytest.mark.parametrize("first_repaired", ["TX-17", "FDR-1"])
def test_partial_restoration_in_both_directions(runtime, now, first_repaired):
    """Repairing either end of a failed supply path cannot bypass the other."""
    other = "TX-17" if first_repaired == "FDR-1" else "FDR-1"
    timeline = [operation(now, "device_failed"), operation(now, "device_failed", "FDR-1"),
                operation(now + timedelta(minutes=1), "device_restored", first_repaired),
                operation(now + timedelta(minutes=2), "device_restored", other)]
    result = run_replay(replace(runtime, timeline=timeline), log=lambda line: None)
    restored = [event for event in result.alerts if event.customer_id == "C-1" and event.alert_type == "restored"]
    assert len(restored) == 1
    assert restored[0].sim_time == now + timedelta(minutes=2)


def test_no_future_operational_facts_leak(runtime):
    """Prior snapshots cannot acquire crew facts or ETRs from later timeline entries."""
    result = run_replay(runtime, crews_available=1, log=lambda line: None)
    out = next(event for event in result.alerts if event.customer_id == "C-1" and event.alert_type == "outage_confirmed")
    crew = next(event for event in result.alerts if event.customer_id == "C-1" and event.alert_type == "crew_assigned")
    assert out.snapshot.crew_status is None and out.snapshot.etr_start is None
    assert crew.previous_snapshot.crew_status is None
    assert crew.snapshot.crew_status == "assigned" and crew.snapshot.etr_start is None
    assert out.snapshot.updated_at < crew.snapshot.updated_at


def test_duplicate_operational_reports_are_diagnostic_noops(runtime, now):
    """Repeated fail/restore reports are consumed without resetting an occurrence."""
    timeline = [operation(now, "device_failed"), operation(now, "device_failed"),
                operation(now + timedelta(minutes=1), "device_restored"),
                operation(now + timedelta(minutes=1), "device_restored")]
    result = run_replay(replace(runtime, timeline=timeline), log=lambda line: None)
    counts = Counter(event.alert_type for event in result.alerts if event.customer_id == "C-1")
    assert counts == {"pre_storm": 1, "outage_confirmed": 1, "restored": 1}
    assert len(result.applied_events) == 4
