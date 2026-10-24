"""Run a small outage-tracing example against the synthetic town."""

from analytics.network.root_cause import infer_root_cause
from analytics.network.tracing import downstream_customers


def main() -> None:
    """Print the customers affected by the sample transformer failure."""
    affected = downstream_customers("TR-101")
    print(f"Customers affected by TR-101: {', '.join(affected)}")
    print(f"Most likely failed device: {infer_root_cause(affected)}")
    print("CUST-003 remains outside TR-101's supply path on transformer TR-102.")


if __name__ == "__main__":
    main()
