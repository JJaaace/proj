"""Build the electrical supply graph from the bundled town data."""

from typing import Any

import networkx as nx

from data.connectors.sample_data import load_sample_data


def build_graph() -> nx.DiGraph:
    """Load the sample town and return its directed supply graph."""
    data = load_sample_data()
    graph = nx.DiGraph()

    for item in data["substations"]:
        _add_asset(graph, item, "substation")

    for item in data["feeders"]:
        _require_parent(graph, item["substation_id"], "substation", item["id"])
        _add_asset(graph, item, "feeder")
        graph.add_edge(item["substation_id"], item["id"])

    for item in data["transformers"]:
        _require_parent(graph, item["feeder_id"], "feeder", item["id"])
        _add_asset(graph, item, "transformer")
        graph.add_edge(item["feeder_id"], item["id"])

    for item in data["customers"]:
        _require_parent(graph, item["transformer_id"], "transformer", item["id"])
        _add_asset(graph, item, "customer")
        graph.add_edge(item["transformer_id"], item["id"])

    return graph


def _add_asset(graph: nx.DiGraph, item: dict[str, Any], asset_type: str) -> None:
    """Add one uniquely identified asset and its data attributes to the graph."""
    identifier = item["id"]
    if identifier in graph:
        raise ValueError(f"Duplicate network device ID: {identifier}")

    attributes = {key: value for key, value in item.items() if key != "id"}
    graph.add_node(identifier, asset_type=asset_type, **attributes)


def _require_parent(
    graph: nx.DiGraph,
    parent_id: str,
    expected_type: str,
    child_id: str,
) -> None:
    """Ensure a child references an existing parent of the expected type."""
    if parent_id not in graph:
        raise ValueError(f"{child_id} references unknown device {parent_id}")
    if graph.nodes[parent_id]["asset_type"] != expected_type:
        raise ValueError(
            f"{child_id} must reference a {expected_type}, not {parent_id}"
        )
