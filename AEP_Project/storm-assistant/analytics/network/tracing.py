"""Trace customers supplied by and connected to network devices."""

import networkx as nx

from analytics.network.graph_builder import build_graph


def downstream_customers(device_id: str) -> list[str]:
    """Return sorted customers supplied downstream of a network device."""
    graph = build_graph()
    if device_id not in graph:
        raise ValueError(f"Unknown network device: {device_id}")
    if graph.nodes[device_id]["asset_type"] == "customer":
        raise ValueError(f"{device_id} is a customer, not a supply device")

    return sorted(
        node
        for node in nx.descendants(graph, device_id)
        if graph.nodes[node]["asset_type"] == "customer"
    )


def upstream_path(customer_id: str) -> list[str]:
    """Return the customer's transformer-to-substation supply path."""
    graph = build_graph()
    if customer_id not in graph:
        raise ValueError(f"Unknown customer: {customer_id}")
    if graph.nodes[customer_id]["asset_type"] != "customer":
        raise ValueError(f"{customer_id} is not a customer")

    path: list[str] = []
    current = customer_id
    while True:
        parents = list(graph.predecessors(current))
        if len(parents) != 1:
            raise ValueError(f"{current} does not have exactly one supply parent")

        current = parents[0]
        path.append(current)
        if graph.nodes[current]["asset_type"] == "substation":
            return path
