"""Fail-closed validation against deterministic approved template variants."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING
from .composer import compose, field, septets

if TYPE_CHECKING:
    from data.schemas.models import AlertEvent


def check(message: str, event: AlertEvent) -> list[str]:
    """Return human-readable issues; exact canonical equality grounds every claim."""
    issues = []
    if not isinstance(message, str) or not message.strip():
        return ['empty or invalid message']
    if len(message) > 160:
        issues.append('message exceeds 160 characters')
    try:
        if septets(message) > 160:
            issues.append('message exceeds 160 GSM-7 septets')
    except ValueError:
        issues.append('unsupported GSM-7 character')
    if '\n' in message or '\r' in message:
        issues.append('message contains a line break')
    if not message.endswith('STOP=end'):
        issues.append('missing opt-out suffix')
    s = field(event, 'snapshot')
    if field(s, 'sms_opt_in') is not True:
        issues.append('no SMS consent')
    if re.search(r'\b(?:FDR|TX|SUB|C|CREW)-[\w-]+\b|\b(?:lateral|feeder|transformer|fault code)\b', message, re.I):
        issues.append('internal identifier or jargon')
    for key in ('customer_id', 'feeder_id', 'transformer_id'):
        identifier = field(s, key)
        if isinstance(identifier, str) and identifier and re.search(r'(?<!\w)' + re.escape(identifier) + r'(?!\w)', message):
            issues.append('snapshot identifier exposed')
    try:
        if message != compose(event):
            issues.append('message differs from canonical grounded template or fixed safety text')
    except (ValueError, TypeError, AttributeError) as exc:
        issues.append(f'invalid event: {exc}')
    return issues
