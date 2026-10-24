"""Public entry point for consented, grounded storm SMS alerts."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import is_dataclass, replace
from datetime import timedelta
import logging
import os
from threading import RLock
from typing import TYPE_CHECKING

from .composer import compose, field, parse_time, validate_event
from .guardrails import check
from . import throttle
from channels.sms import consent, provider

if TYPE_CHECKING:
    from data.schemas.models import AlertEvent

_pending = {}
_lock = RLock()
_log = logging.getLogger(__name__)


def handle_alert(event: AlertEvent, dry_run: bool = True) -> dict:
    """Validate eligibility and send one customer-facing SMS for an alert."""
    with _lock:
        return _handle(event, dry_run)


def _handle(event, dry_run):
    """Serialize consent, pending coalescing, delivery and throttle state updates."""
    result = {'sent': False, 'body': None, 'reason': None}
    cid = field(event, 'customer_id')
    try:
        s = field(event, 'snapshot')
        if not consent.is_allowed(s):
            if isinstance(cid, str):
                _pending.pop(cid, None)
            return {**result, 'reason': 'no_sms_consent'}
        validate_event(event)
        now = parse_time(field(event, 'sim_time'))
        pending = _pending.get(cid)
        selected = event
        if pending and parse_time(field(pending, 'sim_time')) > now:
            selected = pending
        # Eligibility uses the incoming tick, never a future pending timestamp.
        if field(s, 'medical_priority') is not True and not throttle.allow(cid, field(event, 'alert_type'), now):
            _pending[cid] = deepcopy(selected)
            return {**result, 'reason': 'throttled'}
        s = field(selected, 'snapshot')
        if not consent.is_allowed(s):
            return {**result, 'reason': 'no_sms_consent'}
        body = compose(selected)
        issues = check(body, selected)
        if issues:
            _log.warning('SMS guardrail failure customer_id=%s', cid)
            return {**result, 'reason': 'guardrail_failed: ' + '; '.join(issues)}
        if not dry_run and field(s, 'medical_priority') is True and field(selected, 'alert_type') == 'outage_confirmed' and os.getenv('STORM_SAFETY_COPY_APPROVED') != '1':
            return {**result, 'reason': 'guardrail_failed: safety copy needs team approval'}
        delivery = provider.send(field(s, 'phone'), body, dry_run=dry_run)
        if not delivery.get('ok'):
            return {**result, 'reason': 'provider_error: ' + delivery.get('error', 'delivery_failed')}
        throttle._mark_sent(cid, max(now, parse_time(field(selected, 'sim_time'))))
        _pending.pop(cid, None)
        return {'sent': True, 'body': body, 'reason': None}
    except (ValueError, TypeError, AttributeError, KeyError):
        return {**result, 'reason': 'guardrail_failed: invalid event or unsupported message'}
    except Exception:
        return {**result, 'reason': 'provider_error: delivery_failed'}


def reset_for_test():
    """Reset all process state for a new synthetic replay, never during live use."""
    with _lock:
        _pending.clear()
        throttle.reset()
        consent.reset_for_test()


def _next_pending_time():
    """Expose an optional replay clock deadline without changing handle_alert's contract."""
    with _lock:
        due = [throttle._sent[cid] + timedelta(minutes=30)
               for cid in _pending if cid in throttle._sent]
        return min(due) if due else None


def _advance_clock(sim_time, snapshots, dry_run=True):
    """Drain eligible pending alerts using current facts and the original public pipeline."""
    now = parse_time(sim_time)
    if now is None:
        raise ValueError('A valid simulated clock is required')
    completed = []
    with _lock:
        for cid in sorted(list(_pending)):
            queued = _pending[cid]
            if parse_time(field(queued, 'sim_time')) > now:
                continue
            current = snapshots.get(cid)
            kind = field(queued, 'alert_type')
            expected = {'pre_storm': 'at_risk', 'restored': 'restored'}.get(kind, 'outage_confirmed')
            if current is None or field(current, 'status') != expected:
                _pending.pop(cid, None)  # Never send an obsolete outage after restoration.
                continue
            updated = parse_time(field(current, 'updated_at'))
            if updated is None or updated > now:
                raise ValueError('Pending delivery cannot use a future or undated snapshot')
            timestamp = now.isoformat() if isinstance(field(queued, 'sim_time'), str) else now
            if isinstance(queued, dict):
                selected = {**deepcopy(queued), 'snapshot': current, 'sim_time': timestamp}
            elif is_dataclass(queued):
                selected = replace(queued, snapshot=current, sim_time=timestamp)
            else:
                selected = deepcopy(queued)
                selected.snapshot, selected.sim_time = current, timestamp
            _pending[cid] = selected  # Coalesce even changes that did not emit another alert.
            if (consent.is_allowed(current) and field(current, 'medical_priority') is not True
                    and not throttle.allow(cid, kind, now)):
                continue
            outcome = handle_alert(selected, dry_run=dry_run)
            completed.append({'event': selected, 'outcome': outcome})
    return completed
