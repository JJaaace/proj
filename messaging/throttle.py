"""In-process simulated-time rate limiting; checks do not reserve a send slot."""
from datetime import datetime, timedelta

_sent = {}


def allow(customer_id: str, alert_type: str, sim_time: datetime) -> bool:
    """Allow restoration or a normal message at least 30 minutes after delivery."""
    if alert_type == 'restored':
        return True
    previous = _sent.get(customer_id)
    return previous is None or sim_time - previous >= timedelta(minutes=30)


def _mark_sent(customer_id, sim_time):
    """Record successful delivery without rewinding the customer's clock."""
    previous = _sent.get(customer_id)
    _sent[customer_id] = max(previous, sim_time) if previous else sim_time


def reset():
    """Clear delivery state before an independent replay."""
    _sent.clear()
