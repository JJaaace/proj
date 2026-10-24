"""Session-local opt-outs override even stale opted-in snapshots."""
_stopped = set()


def _field(snapshot, key):
    """Read an object or wire mapping."""
    return snapshot.get(key) if isinstance(snapshot, dict) else getattr(snapshot, key, None)


def is_allowed(snapshot):
    """Require explicit source consent and no customer or phone STOP override."""
    return (_field(snapshot, 'sms_opt_in') is True
            and not any(_field(snapshot, key) in _stopped for key in ('phone', 'customer_id')))


def record_stop(phone_or_customer_id):
    """Record an opt-out for a customer ID or exact phone number."""
    _stopped.add(phone_or_customer_id)


def handle_inbound(phone_or_customer_id, body):
    """Process STOP locally; no public inbound webhook is installed."""
    if isinstance(body, str) and body.strip().upper() in {'STOP', 'STOPALL', 'UNSUBSCRIBE', 'CANCEL', 'END', 'QUIT'}:
        record_stop(phone_or_customer_id)
        return True
    return False


def reset_for_test():
    """Clear in-memory opt-outs for isolated tests or synthetic replays."""
    _stopped.clear()
