"""Test real-module wiring with isolated doubles; mark missing team code honestly."""

from dataclasses import make_dataclass
import json
from pathlib import Path
import sys
from types import ModuleType
from unittest.mock import Mock

import pytest

from .demo import DemoAlert, DemoSnapshot
from .integration import PROJECT_ROOT, _export, load_runtime
from .replay import run_replay


def write_samples(root, runtime):
    """Write source-shaped temporary records without touching team-owned files."""
    sample = root / "data" / "sample"
    sample.mkdir(parents=True)
    for name, value in {
        "substations": runtime.town.substations, "feeders": runtime.town.feeders,
        "transformers": runtime.town.transformers, "customers": runtime.town.customers,
        "storm": runtime.storm, "storm_timeline": runtime.timeline,
    }.items():
        (sample / f"{name}.json").write_text(json.dumps(value))


def install_package(monkeypatch, name, **exports):
    """Install a temporary package double scoped to one wiring test."""
    module = ModuleType(name)
    module.__path__ = []
    module.__dict__.update(exports)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def test_integrated_loader_uses_injected_canonical_factories(runtime, tmp_path, monkeypatch):
    """Verify integration imports and constructor identity without claiming real-team coverage."""
    write_samples(tmp_path, runtime)
    snapshot_model = make_dataclass("StubCanonicalSnapshot", [], bases=(DemoSnapshot,), frozen=True)
    event_model = make_dataclass("StubCanonicalAlert", [], bases=(DemoAlert,), frozen=True)
    install_package(monkeypatch, "data")
    install_package(monkeypatch, "data.schemas")
    install_package(monkeypatch, "data.schemas.models", CustomerSnapshot=snapshot_model, AlertEvent=event_model)
    install_package(monkeypatch, "analytics")

    class Graph:
        """Represent only the documented directed graph interface in this test."""

        def is_directed(self):
            """Declare directed substation-to-customer edges."""
            return True

        def has_edge(self, parent, child):
            """Check the actual fixture electrical relationships."""
            return any(row["id"] == child and row[key] == parent
                       for rows, key in ((runtime.town.feeders, "substation_id"),
                                         (runtime.town.transformers, "feeder_id"),
                                         (runtime.town.customers, "transformer_id")) for row in rows)

    build_graph = Mock(return_value=Graph())
    install_package(monkeypatch, "analytics.network", build_graph=build_graph,
                    downstream_customers=runtime.dependencies.downstream_customers)
    install_package(monkeypatch, "analytics.predictive", outage_risk=runtime.dependencies.outage_risk,
                    predict_etr=runtime.dependencies.predict_etr)
    install_package(monkeypatch, "analytics.geospatial", storm_position=runtime.dependencies.storm_position,
                    storm_arrival_time=runtime.dependencies.storm_arrival_time,
                    in_high_wind_zone=runtime.dependencies.in_high_wind_zone)
    handler = Mock(return_value={"sent": False, "body": None, "reason": "isolated_wiring_test"})
    install_package(monkeypatch, "messaging", handle_alert=handler)
    integrated = load_runtime("integrated", tmp_path)
    result = run_replay(integrated, crews_available=1, log=lambda line: None)
    build_graph.assert_called_once_with()
    assert all(type(value) is snapshot_model for value in result.snapshots.values())
    assert all(type(event) is event_model for event in result.alerts)
    assert all(type(event.snapshot) is snapshot_model for event in result.alerts)
    assert handler.call_count == len(result.alerts)
    assert all(call.kwargs == {"dry_run": True} for call in handler.call_args_list)


def test_original_spec_submodule_import_paths(monkeypatch):
    """Support graph_builder/tracing/etc. when the package has no re-exports."""
    install_package(monkeypatch, "example_network")
    function = Mock()
    install_package(monkeypatch, "example_network.tracing", downstream_customers=function)
    assert _export("example_network", "tracing", "downstream_customers") is function


def test_absent_integrations_auto_mode_is_labeled(tmp_path):
    """A completely empty scaffolding can run only the explicitly labeled fixture demo."""
    assert load_runtime("auto", tmp_path).mode == "demo"


def test_partial_integrations_do_not_silently_fall_back(tmp_path):
    """Once upstream work appears, require it to work or choose --demo explicitly."""
    (tmp_path / "messaging").mkdir()
    with pytest.raises(ValueError, match="Integration unavailable"):
        load_runtime("auto", tmp_path)
    assert load_runtime("demo", tmp_path).mode == "demo"


def test_integrated_mode_requires_real_sample_files(tmp_path):
    """An explicit integrated run must not substitute invented source data."""
    with pytest.raises(ValueError, match="missing"):
        load_runtime("integrated", tmp_path)


@pytest.mark.skipif(
    not all((PROJECT_ROOT / marker).exists() for marker in (
        "data/schemas/models.py", "data/sample/storm_timeline.json", "analytics/network",
        "analytics/predictive", "analytics/geospatial", "messaging",
    )), reason="Awaiting Shaun's canonical models/data/network, Teja's analytics, and Atharva's messaging",
)
def test_actual_team_modules_end_to_end():
    """Run real canonical models and messaging once all upstream pieces are present."""
    runtime = load_runtime("integrated")
    result = run_replay(runtime, log=lambda line: None)
    assert result.applied_events
    assert result.alerts
    assert not any(snapshot.status == "outage_confirmed" for snapshot in result.snapshots.values())
