"""Lifecycle, electrical scope, data validation, and estimate stability."""

from dataclasses import asdict, replace
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from services.context.contracts import Town, local_time
from services.context.lifecycle import OperationalState, customer_status
from services.context.snapshot import SnapshotBuilder


def operation(now, kind, device="TX-17", **details):
    """Build one original-contract timeline record."""
    return dict(time=now.isoformat(), type=kind, device_id=device, **details)


@pytest.mark.parametrize("risk,hours,expected", [
    (0.5, 12, "at_risk"), (0.8, 0, "at_risk"), (0.49, 1, "normal"),
    (0.8, 12.01, "normal"), (0.8, -1, "normal"),
])
def test_warning_threshold_and_arrival_window(now, risk, hours, expected):
    """Only an evidenced imminent storm can trigger a risk state."""
    assert customer_status(None, affected=False, risk_score=risk,
                           storm_arrival=now + timedelta(hours=hours), sim_time=now) == expected


def test_high_risk_without_arrival_is_not_outage(now):
    """Predictions alone establish neither warning arrival nor actual power loss."""
    assert customer_status(None, affected=False, risk_score=1,
                           storm_arrival=None, sim_time=now) == "normal"


def test_active_wind_zone_policy(now):
    """A known arrival still supports risk while the actual wind zone is present."""
    assert customer_status(None, affected=False, risk_score=.8,
                           storm_arrival=now - timedelta(minutes=10),
                           sim_time=now, in_wind_zone=True) == "at_risk"


@pytest.mark.parametrize("device,expected", [
    ("TX-17", {"C-1", "C-2", "C-4"}), ("TX-18", {"C-3"}),
    ("FDR-1", {"C-1", "C-2", "C-4"}), ("FDR-2", {"C-3"}),
    ("SUB-1", {"C-1", "C-2", "C-3", "C-4"}),
])
def test_electrical_failure_scope(runtime, now, device, expected):
    """Trace transformer, feeder, and substation failures through graph edges."""
    state = OperationalState([operation(now, "device_failed", device)], runtime.town.device_ids)
    state.advance(now)
    builder = SnapshotBuilder(runtime.town, runtime.dependencies)
    snapshots = builder.build_all_snapshots(runtime.storm, state, {})
    assert {key for key, value in snapshots.items() if value.status == "outage_confirmed"} == expected


def test_overlapping_failures_restore_only_after_last_one(runtime, now):
    """Restoring a transformer cannot bypass an outstanding feeder failure."""
    timeline = [operation(now, "device_failed"), operation(now, "device_failed", "FDR-1"),
                operation(now + timedelta(minutes=10), "device_restored"),
                operation(now + timedelta(minutes=20), "device_restored", "FDR-1")]
    state = OperationalState(timeline, runtime.town.device_ids)
    builder = SnapshotBuilder(runtime.town, runtime.dependencies, crews_available=1)
    snapshots = {}
    for minutes, expected in ((0, "outage_confirmed"), (10, "outage_confirmed"), (20, "restored"), (30, "restored")):
        state.advance(now + timedelta(minutes=minutes))
        snapshots = builder.build_all_snapshots(runtime.storm, state, snapshots)
        assert snapshots["C-1"].status == expected
        if minutes == 0:
            assert snapshots["C-1"].cause == "unknown"
            assert snapshots["C-1"].etr_start is None
        if minutes >= 20:
            assert snapshots["C-1"].cause is None
            assert snapshots["C-1"].crew_status is None
            assert snapshots["C-1"].etr_start is None
        assert snapshots["C-3"].status == "normal"


def test_new_failure_after_restoration(runtime, now):
    """A new operational failure starts another occurrence after restoration."""
    timeline = [operation(now, "device_failed"),
                operation(now + timedelta(minutes=10), "device_restored"),
                operation(now + timedelta(minutes=20), "device_failed")]
    state = OperationalState(timeline, runtime.town.device_ids)
    builder, snapshots = SnapshotBuilder(runtime.town, runtime.dependencies), {}
    for minutes, expected in ((0, "outage_confirmed"), (10, "restored"), (20, "outage_confirmed")):
        state.advance(now + timedelta(minutes=minutes))
        snapshots = builder.build_all_snapshots(runtime.storm, state, snapshots)
        assert snapshots["C-1"].status == expected


def test_unoutaged_risk_state_is_stable(runtime, now):
    """The documented MVP retains at-risk status when an unaffected storm passes."""
    state = OperationalState([], runtime.town.device_ids)
    builder = SnapshotBuilder(runtime.town, runtime.dependencies)
    state.advance(now)
    snapshots = builder.build_all_snapshots(runtime.storm, state, {})
    state.advance(now + timedelta(days=1))
    assert builder.build_all_snapshots(runtime.storm, state, snapshots)["C-1"].status == "at_risk"


@pytest.mark.parametrize("representation", ["dataclass", "dict", "attributes"])
def test_estimate_representation_and_cache(runtime, now, representation):
    """Read typed ETR fields and avoid estimate drift on unchanged ticks."""
    original = runtime.dependencies.predict_etr

    def predict(damage_type, crews_available, clock):
        """Return the agreed ETR fields through three compatible interfaces."""
        result = original(damage_type, crews_available, clock)
        return asdict(result) if representation == "dict" else (
            SimpleNamespace(**asdict(result)) if representation == "attributes" else result
        )

    predictor = Mock(side_effect=predict)
    dependencies = replace(runtime.dependencies, predict_etr=predictor)
    state = OperationalState([operation(now, "device_failed", damage_type="blown_fuse")], runtime.town.device_ids)
    builder = SnapshotBuilder(runtime.town, dependencies, crews_available=1)
    state.advance(now)
    first = builder.build_all_snapshots(runtime.storm, state, {})
    state.advance(now + timedelta(hours=2))
    second = builder.build_all_snapshots(runtime.storm, state, first)
    assert predictor.call_count == 1  # Also shared across customers on one device.
    assert first["C-1"].etr_start == second["C-1"].etr_start


def test_unknown_damage_and_unspecified_crews_have_no_etr(runtime, now):
    """Never invent an estimate without known damage and a crew assumption."""
    predictor = Mock(side_effect=AssertionError("Must not predict"))
    dependencies = replace(runtime.dependencies, predict_etr=predictor)
    for damage, crews in (("unknown", 1), ("broken_pole", None)):
        state = OperationalState([operation(now, "device_failed", damage_type=damage)], runtime.town.device_ids)
        state.advance(now)
        snapshots = SnapshotBuilder(runtime.town, dependencies, crews_available=crews).build_all_snapshots(runtime.storm, state, {})
        assert snapshots["C-1"].etr_start is None
        assert snapshots["C-1"].confidence is None


@pytest.mark.parametrize("change,match", [
    ({"type": "invented_event"}, "event type"), ({"device_id": "MISSING"}, "device ID"),
    ({"damage_type": "invented_damage"}, "damage_type"),
    ({"type": "crew_assigned"}, "crew_id"),
])
def test_invalid_timeline_rejected(runtime, now, change, match):
    """Invalid events fail before any snapshot or message can be fabricated."""
    event = operation(now, "device_failed") | change
    with pytest.raises(ValueError, match=match):
        OperationalState([event], runtime.town.device_ids)


def test_invalid_operational_sequence_rejected(runtime, now):
    """Crew activity without an active incident is an explicit data error."""
    with pytest.raises(ValueError, match="inactive failure"):
        OperationalState([operation(now, "crew_on_site", crew_id="CREW-2")], runtime.town.device_ids)


def test_bad_customer_mapping_rejected(runtime):
    """A missing transformer is never replaced by a nearby device."""
    customers = [dict(row) for row in runtime.town.customers]
    customers[0]["transformer_id"] = "MISSING"
    with pytest.raises(ValueError, match="transformer_id"):
        Town(runtime.town.substations, runtime.town.feeders, runtime.town.transformers, customers)


def test_unknown_network_customer_rejected(runtime, now):
    """Network traces cannot silently introduce an unknown customer."""
    state = OperationalState([operation(now, "device_failed")], runtime.town.device_ids)
    state.advance(now)
    with pytest.raises(ValueError, match="unknown customer"):
        state.affected_customers(lambda device: ["MISSING"], {"C-1"})


def test_local_time_policy(now):
    """Reject aware timestamps rather than mixing UTC and local wall time."""
    assert local_time(now.isoformat()) == now
    with pytest.raises(ValueError, match="without timezone"):
        local_time("2026-10-24T18:00:00+00:00")


def test_invalid_risk_rejected(runtime, now):
    """Out-of-range upstream predictions must not enter a snapshot."""
    state = OperationalState([], runtime.town.device_ids)
    state.advance(now)
    deps = replace(runtime.dependencies, outage_risk=lambda feeder, storm: float("nan"))
    with pytest.raises(ValueError, match="risk score"):
        SnapshotBuilder(runtime.town, deps).build_all_snapshots(runtime.storm, state, {})
