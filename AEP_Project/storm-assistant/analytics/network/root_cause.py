"""Infer a likely failed device from a set of outaged customers."""

from analytics.network.tracing import upstream_path


def infer_root_cause(out_customer_ids: list[str]) -> str:
    """Return the nearest shared upstream device for outaged customers."""
    if not out_customer_ids:
        raise ValueError("At least one outaged customer is required")

    paths = [upstream_path(customer_id) for customer_id in out_customer_ids]
    shared_devices = set(paths[0]).intersection(*paths[1:])
    for device_id in paths[0]:
        if device_id in shared_devices:
            return device_id

    raise ValueError("Outaged customers do not share an upstream device")
