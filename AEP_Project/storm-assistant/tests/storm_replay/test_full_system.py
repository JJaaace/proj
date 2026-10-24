"""Real four-person regressions; no substituted analytics, schemas, or messaging."""

from collections import Counter
from copy import deepcopy
from dataclasses import fields, replace
from datetime import datetime, timedelta
from importlib import import_module
import json
from pathlib import Path
import socket
from unittest.mock import Mock

import pytest

import messaging
from analytics.network.graph_builder import build_graph
from analytics.network.root_cause import infer_root_cause
from analytics.network.tracing import downstream_customers, upstream_path
from channels.sms import consent
from data.connectors.sample_data import load_sample_data
from data.schemas.models import AlertEvent, CustomerSnapshot
from messaging.composer import safety, septets
from messaging.guardrails import check
from services.context.contracts import SNAPSHOT_FIELDS, construct_model, local_time
from .integration import PROJECT_ROOT, load_runtime, normalize_scenario_times, require_signature
from .presentation import export_audit
from .replay import run_replay


@pytest.fixture
def real_runtime(monkeypatch):
    """Keep real owners' code active while forbidding every outbound socket connection."""
    blocked = Mock(side_effect=AssertionError("Network access is forbidden in integration tests"))
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    messaging.reset_for_test()
    runtime = load_runtime("integrated")
    yield runtime
    messaging.reset_for_test()
    blocked.assert_not_called()


def message_event(runtime, now, kind="outage_confirmed", *, medical=False, opted_in=True, **changes):
    """Build a canonical event with synthetic source attributes and local ISO fields."""
    customer = next(row for row in runtime.town.customers if row["id"] == "CUST-002")
    values = dict(
        customer_id=customer["id"], first_name=customer["first_name"], phone=customer["phone"],
        language="en", sms_opt_in=opted_in, medical_priority=medical,
        feeder_id="FDR-01", transformer_id="TR-101",
        status={"pre_storm": "at_risk", "restored": "restored"}.get(kind, "outage_confirmed"),
        risk_score=.62, storm_arrival=now + timedelta(hours=1), cause="tree_on_line",
        etr_start=now + timedelta(hours=2), etr_end=now + timedelta(hours=3),
        confidence="high", crew_status="assigned", updated_at=now,
    )
    values.update(changes)
    snapshot = construct_model(CustomerSnapshot, **values)
    return construct_model(AlertEvent, alert_type=kind, customer_id=snapshot.customer_id,
                           snapshot=snapshot, previous_snapshot=None, sim_time=now)


def test_all_owners_and_canonical_wire_types_are_real(real_runtime):
    """Validate provenance and serialized field types instead of merely counting outputs."""
    deps = real_runtime.dependencies
    assert deps.snapshot_model is CustomerSnapshot and deps.alert_model is AlertEvent
    assert deps.handle_alert is messaging.handle_alert
    for function in (deps.downstream_customers, deps.outage_risk, deps.predict_etr,
                     deps.storm_position, deps.storm_arrival_time, deps.in_high_wind_zone):
        assert Path(import_module(function.__module__).__file__).is_relative_to(PROJECT_ROOT)
    result = run_replay(real_runtime, crews_available=1, log=lambda line: None)
    assert {field.name for field in fields(CustomerSnapshot)} == set(SNAPSHOT_FIELDS)
    for event in result.alerts:
        assert type(event) is AlertEvent and type(event.snapshot) is CustomerSnapshot
        assert isinstance(event.sim_time, str) and isinstance(event.snapshot.updated_at, str)
        assert local_time(event.sim_time).tzinfo is None
        for name in ("storm_arrival", "etr_start", "etr_end"):
            value = getattr(event.snapshot, name)
            assert value is None or isinstance(value, str)


@pytest.mark.parametrize("device,customers", [
    ("TR-101", {"CUST-001", "CUST-002"}), ("TR-102", {"CUST-003"}),
    ("TR-201", {"CUST-004"}), ("FDR-01", {"CUST-001", "CUST-002", "CUST-003"}),
    ("SUB-01", {"CUST-001", "CUST-002", "CUST-003", "CUST-004"}),
])
def test_real_electrical_scope(real_runtime, device, customers):
    """Trace exact transformer, feeder, and substation descendants in Shaun's graph."""
    assert set(downstream_customers(device)) == customers


def test_upstream_and_root_cause_contracts(real_runtime):
    """Verify the two remaining network APIs as implemented by Person 1."""
    require_signature(upstream_path, "upstream_path", ("customer_id",))
    require_signature(infer_root_cause, "infer_root_cause", ("out_customer_ids",))
    assert upstream_path("CUST-001") == ["TR-101", "FDR-01", "SUB-01"]
    assert infer_root_cause(["CUST-001", "CUST-002"]) == "TR-101"
    assert infer_root_cause(["CUST-001", "CUST-003"]) == "FDR-01"


@pytest.mark.parametrize("problem", ["duplicate", "missing_parent"])
def test_real_graph_rejects_bad_source_relationships(real_runtime, monkeypatch, problem):
    """Exercise real validation code with malformed source fixtures, not a graph stub."""
    source = deepcopy(load_sample_data())
    if problem == "duplicate":
        source["customers"].append(dict(source["customers"][0]))
    else:
        source["customers"][0]["transformer_id"] = "MISSING"
    module = import_module("analytics.network.graph_builder")
    monkeypatch.setattr(module, "load_sample_data", lambda: source)
    with pytest.raises(ValueError, match="Duplicate|unknown device"):
        build_graph()


@pytest.mark.parametrize("first_repaired", ["TR-101", "FDR-01"])
def test_real_overlapping_failures_require_both_repairs(real_runtime, first_repaired):
    """Keep unrepaired supply paths outaged using real tracing and message handling."""
    now = datetime(2026, 10, 24, 17, 15)
    other = "FDR-01" if first_repaired == "TR-101" else "TR-101"
    timeline = [dict(time=now.isoformat(), type="device_failed", device_id=device)
                for device in ("TR-101", "FDR-01")]
    timeline += [dict(time=(now + timedelta(minutes=minutes)).isoformat(),
                      type="device_restored", device_id=device)
                 for minutes, device in ((1, first_repaired), (2, other))]
    result = run_replay(replace(real_runtime, timeline=timeline), crews_available=1, log=lambda line: None)
    restored = [event for event in result.alerts if event.customer_id == "CUST-001" and event.alert_type == "restored"]
    assert len(restored) == 1 and local_time(restored[0].sim_time) == now + timedelta(minutes=2)
    assert result.snapshots["CUST-004"].status == "normal"


def test_real_replay_counts_consent_pending_and_final_power(real_runtime):
    """Explain every scenario alert and prove a pending crew message sends at its deadline."""
    result = run_replay(real_runtime, crews_available=1, log=lambda line: None)
    assert Counter(event.alert_type for event in result.alerts) == {
        "pre_storm": 3, "outage_confirmed": 2, "crew_assigned": 2, "etr_update": 2, "restored": 2,
    }
    assert result.summary["handler_calls"] == 12
    assert result.summary["successful_dry_runs"] == 10
    assert result.summary["delivery_reason_counts"] == {
        "MESSAGING_SENT_DRY_RUN": 10, "MESSAGING_THROTTLED": 1, "MESSAGING_NO_CONSENT": 1,
    }
    assert len(result.deferred_outcomes) == 1
    pending = result.deferred_outcomes[0]
    assert pending["event"].customer_id == "CUST-002"
    assert pending["event"].sim_time == "2026-10-24T17:45:00"
    assert pending["outcome"]["sent"] is True
    assert {key: value.status for key, value in result.snapshots.items()} == {
        "CUST-001": "restored", "CUST-002": "restored", "CUST-003": "at_risk", "CUST-004": "normal",
    }
    assert not messaging._pending


def test_real_medical_categories_bypass_and_fixed_copy(real_runtime):
    """Use actual messaging to prove bypass and literal emergency-resource wording."""
    result = run_replay(real_runtime, crews_available=1, log=lambda line: None)
    priority = [(event, outcome) for event, outcome in zip(result.alerts, result.outcomes)
                if event.snapshot.medical_priority]
    assert {event.alert_type for event, _ in priority} == {
        "pre_storm", "outage_confirmed", "crew_assigned", "etr_update", "restored",
    }
    assert all(outcome["sent"] for _, outcome in priority)
    outage = next(outcome["body"] for event, outcome in priority if event.alert_type == "outage_confirmed")
    assert safety("medical") in outage
    assert "emergency resources" in outage and "dispatched" not in outage and "en route" not in outage
    for event, outcome in priority:
        assert len(outcome["body"]) <= 160 and septets(outcome["body"]) <= 160
        assert check(outcome["body"], event) == []


def test_pending_etr_flushes_latest_snapshot_without_new_alert(real_runtime):
    """A clock-only drain uses the newest range at exactly the next allowed instant."""
    now = datetime(2026, 10, 24, 18)
    assert messaging.handle_alert(message_event(real_runtime, now), dry_run=True)["sent"]
    queued = message_event(real_runtime, now + timedelta(minutes=5), "etr_update")
    assert messaging.handle_alert(queued, dry_run=True)["reason"] == "throttled"
    latest = replace(queued.snapshot, etr_end="2026-10-24T23:00:00", updated_at="2026-10-24T18:29:00")
    assert messaging._advance_clock(now + timedelta(minutes=29), {latest.customer_id: latest}, dry_run=True) == []
    assert messaging._next_pending_time() == now + timedelta(minutes=30)
    delivered = messaging._advance_clock(now + timedelta(minutes=30), {latest.customer_id: latest}, dry_run=True)
    assert len(delivered) == 1 and delivered[0]["outcome"]["sent"]
    assert "11 PM" in delivered[0]["outcome"]["body"]
    assert delivered[0]["event"].snapshot is latest
    assert not messaging._pending


def test_restoration_clears_pending_and_bypasses_throttle(real_runtime):
    """No queued outage/ETR can be delivered after a real restoration event."""
    now = datetime(2026, 10, 24, 18)
    assert messaging.handle_alert(message_event(real_runtime, now), dry_run=True)["sent"]
    assert messaging.handle_alert(message_event(real_runtime, now + timedelta(minutes=5), "etr_update"), dry_run=True)["reason"] == "throttled"
    restored = message_event(real_runtime, now + timedelta(minutes=6), "restored")
    assert messaging.handle_alert(restored, dry_run=True)["sent"]
    assert messaging._advance_clock(now + timedelta(minutes=30), {restored.customer_id: restored.snapshot}, dry_run=True) == []


def test_pending_clock_rejects_future_snapshot(real_runtime):
    """The deferred path shares the source replay's protection against future facts."""
    now = datetime(2026, 10, 24, 18)
    assert messaging.handle_alert(message_event(real_runtime, now), dry_run=True)["sent"]
    queued = message_event(real_runtime, now + timedelta(minutes=5), "etr_update")
    assert messaging.handle_alert(queued, dry_run=True)["reason"] == "throttled"
    future = replace(queued.snapshot, updated_at="2026-10-24T19:00:00")
    with pytest.raises(ValueError, match="future"):
        messaging._advance_clock(now + timedelta(minutes=30), {future.customer_id: future}, dry_run=True)


@pytest.mark.parametrize("kind", ["outage_confirmed", "restored"])
def test_stop_overrides_priority_and_pending_delivery(real_runtime, kind):
    """The approved bypasses never override a STOP or source opt-out."""
    now = datetime(2026, 10, 24, 18)
    ordinary = message_event(real_runtime, now)
    assert messaging.handle_alert(ordinary, dry_run=True)["sent"]
    assert messaging.handle_alert(message_event(real_runtime, now + timedelta(minutes=5), "etr_update"), dry_run=True)["reason"] == "throttled"
    consent.record_stop(ordinary.customer_id)
    assert messaging.handle_alert(message_event(real_runtime, now + timedelta(minutes=6), kind, medical=True), dry_run=True)["reason"] == "no_sms_consent"
    assert not messaging._pending
    assert messaging.handle_alert(message_event(real_runtime, now + timedelta(minutes=31), kind, opted_in=False), dry_run=True)["reason"] == "no_sms_consent"


def test_low_confidence_window_is_uncertain_and_bounded(real_runtime):
    """Validate real composition/guardrails for an unknown-damage early estimate."""
    event = message_event(real_runtime, datetime(2026, 10, 24, 18), "etr_update", confidence="low")
    result = messaging.handle_alert(event, dry_run=True)
    assert result["sent"] and "our best early estimate" in result["body"]
    assert "between" in result["body"] and check(result["body"], event) == []


def test_source_offset_normalization_and_mixing_rejection():
    """Align original sample offsets to Ohio local ISO, preserving source documents."""
    storm = {"start_time": "2026-10-24T16:00:00-04:00"}
    timeline = [dict(time="2026-10-24T17:15:00-04:00", type="device_failed", device_id="TR-101")]
    normalized, events = normalize_scenario_times(storm, timeline)
    assert normalized["start_time"] == "2026-10-24T16:00:00"
    assert events[0]["time"] == "2026-10-24T17:15:00"
    assert storm["start_time"].endswith("-04:00") and timeline[0]["time"].endswith("-04:00")
    with pytest.raises(ValueError, match="Mixed"):
        normalize_scenario_times(storm, [dict(time="2026-10-24T17:15:00")])


def test_real_replays_are_repeatable_and_public_audits_hide_health(real_runtime, tmp_path, capsys):
    """Reset synthetic run state and exclude medical flags, names, phones, and SMS text."""
    logs = []
    first = run_replay(real_runtime, crews_available=1, log=logs.append)
    second = run_replay(real_runtime, crews_available=1, log=lambda line: None)
    assert first.alerts == second.alerts and first.summary == second.summary
    assert first.audit.to_records() == second.audit.to_records()
    output = tmp_path / "audit.json"
    export_audit(output, first, mode="integrated", dry_run=True)
    public = "\n".join(logs) + capsys.readouterr().out + output.read_text()
    for customer in real_runtime.town.customers:
        assert customer["phone"] not in public and customer["first_name"] not in public
    assert "medical_priority" not in public and safety("medical") not in public
    assert "STORM_SAFETY_COPY_APPROVED" not in public
    document = json.loads(output.read_text())
    assert document["mode"] == "integrated" and document["deferred_delivery"] == "AVAILABLE"
