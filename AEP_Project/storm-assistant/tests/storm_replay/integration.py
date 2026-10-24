"""Load real Section 6 modules lazily; never mask a broken partial integration."""

from dataclasses import dataclass
from importlib import import_module
import json
from pathlib import Path

from services.context.contracts import Dependencies, Town, local_time


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Runtime:
    """Replay inputs plus a visible distinction between integrated and demo mode."""

    town: Town
    storm: dict
    timeline: list[dict]
    dependencies: Dependencies
    mode: str


def _export(package: str, module: str, name: str):
    """Support package exports or the original spec's named source modules."""
    imported = import_module(package)
    result = getattr(imported, name, None)
    if not callable(result):
        result = getattr(import_module(f"{package}.{module}"), name)
    if not callable(result):
        raise ValueError(f"{package}.{name} must be callable")
    return result


def load_runtime(mode: str = "auto", project_root: Path = PROJECT_ROOT) -> Runtime:
    """Use actual teammate modules, or an explicitly labeled fully offline demo."""
    if mode not in ("auto", "demo", "integrated"):
        raise ValueError(f"Unknown runtime mode: {mode}")
    markers = [project_root / path for path in (
        "data/schemas/models.py", "data/sample/customers.json", "analytics/network",
        "analytics/predictive", "analytics/geospatial", "messaging",
    )]
    if mode == "demo" or (mode == "auto" and not any(path.exists() for path in markers)):
        from .demo import demo_dependencies, demo_inputs

        town, storm, timeline = demo_inputs()
        return Runtime(town, storm, timeline, demo_dependencies(town), "demo")
    sample = project_root / "data" / "sample"
    records = {}
    for name in ("substations", "feeders", "transformers", "customers", "storm", "storm_timeline"):
        path = sample / f"{name}.json"
        if not path.is_file():
            raise ValueError(f"Integration unavailable: missing {path}. Use --demo for labeled fixtures.")
        with path.open() as source:
            records[name] = json.load(source)
        expected = dict if name == "storm" else list
        if not isinstance(records[name], expected):
            raise ValueError(f"{path} must contain a JSON {expected.__name__}")
    town = Town(*(records[name] for name in ("substations", "feeders", "transformers", "customers")))
    local_time(records["storm"]["start_time"])
    models = import_module("data.schemas.models")
    graph = _export("analytics.network", "graph_builder", "build_graph")()
    if not graph.is_directed():
        raise ValueError("The grid graph must be directed")
    for rows, parent in ((town.feeders, "substation_id"),
                         (town.transformers, "feeder_id"), (town.customers, "transformer_id")):
        for row in rows:
            if not graph.has_edge(row[parent], row["id"]):
                raise ValueError(f"Grid graph missing electrical edge {row[parent]} -> {row['id']}")
    deps = Dependencies(
        models.CustomerSnapshot, models.AlertEvent,
        _export("analytics.network", "tracing", "downstream_customers"),
        _export("analytics.predictive", "outage_risk", "outage_risk"),
        _export("analytics.predictive", "etr", "predict_etr"),
        _export("analytics.geospatial", "storm_overlay", "storm_position"),
        _export("analytics.geospatial", "storm_overlay", "storm_arrival_time"),
        _export("analytics.geospatial", "storm_overlay", "in_high_wind_zone"),
        getattr(import_module("messaging"), "handle_alert"),
    )
    return Runtime(town, records["storm"], records["storm_timeline"], deps, "integrated")
