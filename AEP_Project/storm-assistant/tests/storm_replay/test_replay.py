"""Offline end-to-end replay, operational ordering, and live gating."""

from dataclasses import replace
from datetime import timedelta
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock

import pytest

from services.context.lifecycle import OperationalState
from .replay import main, run_replay, simulation_times
from .test_lifecycle import operation


def test_entire_replay_handoff_and_neighbor(runtime):
    """All five types reach messaging; a co-located unrelated customer stays on."""
    handler = Mock(return_value={"sent": False, "body": None, "reason": "throttled"})
    runtime = replace(runtime, dependencies=replace(runtime.dependencies, handle_alert=handler))
    lines = []
    result = run_replay(runtime, crews_available=1, log=lines.append)
    assert handler.call_count == len(result.alerts) == 18
    assert all(call.kwargs == {"dry_run": True} for call in handler.call_args_list)
    assert {event.alert_type for event in result.alerts} == {
        "pre_storm", "outage_confirmed", "crew_assigned", "etr_update", "restored",
    }
    assert not any(event.customer_id == "C-3" for event in result.alerts)
    assert result.snapshots["C-3"].status == "normal"
    assert result.snapshots["C-1"].status == "restored"
    assert result.snapshots["C-1"].risk_score >= .5
    assert result.snapshots["C-1"].medical_priority is True
    assert all(event.snapshot.medical_priority for event in result.alerts if event.customer_id == "C-1")
    assert any(event.customer_id == "C-4" and not event.snapshot.sms_opt_in for event in result.alerts)
    assert len(result.applied_events) == len(runtime.timeline)
    assert all("handler_sent=False" in line and "throttled" in line for line in lines if "ALERT" in line)
    assert not any("delivered" in line for line in lines)


def test_ordering_idempotence_and_equal_timestamp_source_order(runtime, now):
    """Sort events stably, apply each once, and reject backwards time."""
    timeline = [operation(now + timedelta(minutes=10), "crew_assigned", crew_id="CREW-2"),
                operation(now, "device_failed"),
                operation(now + timedelta(minutes=10), "crew_on_site", crew_id="CREW-2")]
    state = OperationalState(timeline, runtime.town.device_ids)
    assert [event["type"] for event in state.advance(now + timedelta(minutes=10))] == [
        "device_failed", "crew_assigned", "crew_on_site",
    ]
    assert state.advance(now + timedelta(minutes=10)) == []
    assert state.active_failures["TX-17"].crew_status == "on_site"
    with pytest.raises(ValueError, match="backwards"):
        state.advance(now)


def test_short_failure_between_ticks_is_not_lost(runtime, now):
    """Exact event times preserve outages shorter than the regular interval."""
    timeline = [operation(now + timedelta(minutes=1), "device_failed"),
                operation(now + timedelta(minutes=2), "device_restored")]
    result = run_replay(replace(runtime, timeline=timeline), step_minutes=10, log=lambda line: None)
    assert [event.alert_type for event in result.alerts if event.customer_id == "C-1"] == [
        "pre_storm", "outage_confirmed", "restored",
    ]


def test_two_outages_emit_two_restorations(runtime, now):
    """Full orchestration resets occurrence-based alert deduplication."""
    timeline = [operation(now, "device_failed"), operation(now + timedelta(minutes=1), "device_restored"),
                operation(now + timedelta(minutes=2), "device_failed"),
                operation(now + timedelta(minutes=3), "device_restored")]
    result = run_replay(replace(runtime, timeline=timeline), log=lambda line: None)
    types = [event.alert_type for event in result.alerts if event.customer_id == "C-1"]
    assert types.count("outage_confirmed") == types.count("restored") == 2


def test_live_requires_real_integrations_and_allowlist(runtime):
    """The default fixture runtime cannot reach a live handler under any allowlist."""
    handler = Mock()
    deps = replace(runtime.dependencies, handle_alert=handler)
    with pytest.raises(ValueError, match="real integrations"):
        run_replay(replace(runtime, dependencies=deps), dry_run=False,
                   verified_demo_phones=frozenset({"+16145550101"}))
    with pytest.raises(ValueError, match="verified"):
        run_replay(replace(runtime, mode="integrated", dependencies=deps), dry_run=False)
    handler.assert_not_called()


def test_live_only_calls_mock_for_authorized_opted_in_recipient(runtime):
    """Exercise live routing with a mock; no real provider is imported or called."""
    handler = Mock(return_value={"sent": True, "body": "mock", "reason": None})
    deps = replace(runtime.dependencies, handle_alert=handler)
    result = run_replay(replace(runtime, mode="integrated", dependencies=deps), dry_run=False,
                        verified_demo_phones=frozenset({"+16145550101", "+16145550104"}), log=lambda line: None)
    assert handler.call_count > 0
    assert all(call.args[0].customer_id == "C-1" and call.kwargs == {"dry_run": False}
               for call in handler.call_args_list)
    assert all(not outcome["sent"] for event, outcome in zip(result.alerts, result.outcomes)
               if event.customer_id != "C-1")


@pytest.mark.parametrize("arguments,dry_run", [([], True), (["--live", "--verified-demo-phone", "+16145550101"], False)])
def test_cli_live_is_explicit(runtime, monkeypatch, arguments, dry_run):
    """The CLI passes dry_run=False only in response to --live."""
    load = Mock(return_value=replace(runtime, mode="integrated"))
    run = Mock()
    monkeypatch.setattr("tests.storm_replay.replay.load_runtime", load)
    monkeypatch.setattr("tests.storm_replay.replay.run_replay", run)
    assert main(arguments) == 0
    assert run.call_args.kwargs["dry_run"] is dry_run


def test_default_cli_without_secrets_exits_cleanly():
    """The mandated module command works in a fresh process without API keys."""
    env = {key: value for key, value in os.environ.items()
           if not any(word in key.upper() for word in ("TWILIO", "OPENAI", "API_KEY"))}
    process = subprocess.run([sys.executable, "-m", "tests.storm_replay.replay"],
                             cwd=Path(__file__).resolve().parents[2], env=env,
                             capture_output=True, text=True, timeout=20)
    assert process.returncode == 0, process.stderr
    assert "DRY-RUN" in process.stdout and "active_failures=none" in process.stdout
    assert "simulated_handler" in process.stdout


@pytest.mark.parametrize("minutes", [0, -1])
def test_invalid_step_rejected(runtime, minutes):
    """Invalid step sizes cannot cause an infinite clock loop."""
    with pytest.raises(ValueError, match="positive integer"):
        simulation_times(OperationalState([], runtime.town.device_ids), runtime.storm, minutes)


def test_bad_handler_result_is_explicit(runtime):
    """Do not report malformed handler results as successful delivery."""
    deps = replace(runtime.dependencies, handle_alert=lambda event, dry_run=True: {"sent": "yes"})
    with pytest.raises(ValueError, match="handle_alert must return"):
        run_replay(replace(runtime, dependencies=deps), log=lambda line: None)


def test_import_is_offline():
    """Importing replay must neither import providers nor make network requests."""
    code = """
import socket, sys
def blocked(*args, **kwargs):
    raise AssertionError('Network access during import')
socket.socket = blocked
import tests.storm_replay.replay
assert not any(name == 'twilio' or name.startswith('twilio.') for name in sys.modules)
assert 'messaging' not in sys.modules
"""
    process = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[2],
                             capture_output=True, text=True, timeout=20)
    assert process.returncode == 0, process.stderr
