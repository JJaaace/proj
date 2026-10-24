"""Load real Section 6 modules lazily; never mask a broken partial integration."""

from dataclasses import dataclass, fields, is_dataclass
from importlib import import_module
import inspect
import json
from pathlib import Path

from services.context.contracts import Dependencies, SNAPSHOT_FIELDS, Town, local_time


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INTEGRATION_PATHS = {
    "Shaun: canonical schemas": ("data/schemas/models.py",),
    "Shaun: sample data": tuple(f"data/sample/{name}.json" for name in (
        "substations", "feeders", "transformers", "customers", "storm", "storm_timeline",
    )),
    "Shaun: electrical network": ("analytics/network",),
    "Teja: predictions": ("analytics/predictive",),
    "Teja: geospatial": ("analytics/geospatial",),
    "Atharva: messaging": ("messaging/__init__.py",),
}


def integration_inventory(project_root: Path = PROJECT_ROOT) -> list[dict]:
    """Report precise missing local dependencies without importing or faking them."""
    return [dict(component=component, state="MISSING" if missing else "NOT_TESTED", missing=missing)
            for component, paths in INTEGRATION_PATHS.items()
            for missing in [[path for path in paths if not (project_root / path).exists()]]]


def require_signature(function, name: str, parameters: tuple[str, ...]) -> None:
    """Fail with the actual signature instead of adapting incompatible shared APIs."""
    if not callable(function):
        raise ValueError(f"Contract mismatch: {name} is not callable")
    signature = inspect.signature(function)
    try:
        signature.bind(*([None] * len(parameters)))
        signature.bind(**dict.fromkeys(parameters))
    except TypeError as error:
        raise ValueError(f"Contract mismatch: {name}{signature}; expected ({', '.join(parameters)})") from error


def require_model(factory, name: str, expected: tuple[str, ...]) -> None:
    """Verify canonical constructors and declared fields without replacing models."""
    try:
        inspect.signature(factory).bind(**dict.fromkeys(expected))
    except TypeError as error:
        raise ValueError(f"Contract mismatch: {name} constructor must accept {expected}") from error
    declared = (
        {item.name for item in fields(factory)} if is_dataclass(factory)
        else set(getattr(factory, "model_fields", None) or getattr(factory, "__fields__", {}))
    )
    if declared and declared != set(expected):
        raise ValueError(f"Contract mismatch: {name} fields differ; missing={set(expected) - declared}, extra={declared - set(expected)}")


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
    require_model(models.CustomerSnapshot, "CustomerSnapshot", SNAPSHOT_FIELDS)
    require_model(models.AlertEvent, "AlertEvent", ("alert_type", "customer_id", "snapshot", "previous_snapshot", "sim_time"))
    build_graph = _export("analytics.network", "graph_builder", "build_graph")
    require_signature(build_graph, "build_graph", ())
    graph = build_graph()
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
    for name, parameters in (
        ("downstream_customers", ("device_id",)), ("outage_risk", ("feeder_id", "storm")),
        ("predict_etr", ("damage_type", "crews_available", "now")),
        ("storm_position", ("storm", "t")), ("storm_arrival_time", ("storm", "lat", "lon")),
        ("in_high_wind_zone", ("storm", "lat", "lon", "t")),
        ("handle_alert", ("event", "dry_run")),
    ):
        require_signature(getattr(deps, name), name, parameters)
    for device in sorted(town.device_ids):
        if set(deps.downstream_customers(device)) != town.expected_downstream(device):
            raise ValueError(f"Network electrical trace disagrees with source links for {device}")
    return Runtime(town, records["storm"], records["storm_timeline"], deps, "integrated")
