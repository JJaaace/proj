"""Dry-run-first SMS delivery; Twilio is imported only for explicit live calls."""
import os
import re

from messaging.composer import septets


def send(phone: str, body: str, dry_run: bool = True) -> dict:
    """Simulate delivery or send once to an explicitly allowlisted verified phone."""
    result = {'ok': False, 'dry_run': dry_run, 'sid': None}
    if not isinstance(phone, str) or not re.fullmatch(r'\+[1-9][0-9]{7,14}', phone):
        return {**result, 'error': 'invalid_phone'}
    try:
        if not isinstance(body, str) or not body.strip() or len(body) > 160 or septets(body) > 160 or '\n' in body or '\r' in body:
            return {**result, 'error': 'invalid_body'}
    except ValueError:
        return {**result, 'error': 'invalid_body'}
    if dry_run:
        print(f'DRY RUN TO [redacted-demo-phone]: validated SMS ({len(body)} characters)')
        return {**result, 'ok': True}
    allowed = {p.strip() for p in os.getenv('TWILIO_VERIFIED_TO_NUMBERS', '').split(',') if p.strip()}
    if phone not in allowed:
        return {**result, 'error': 'unverified_recipient'}
    sid, token, sender = (os.getenv(key) for key in ('TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_FROM_NUMBER'))
    if not all((sid, token, sender)) or not re.fullmatch(r'\+[1-9][0-9]{7,14}', sender):
        return {**result, 'error': 'missing_or_invalid_configuration'}
    try:
        from twilio.rest import Client
        message = Client(sid, token).messages.create(to=phone, from_=sender, body=body)
        if message.status in {'failed', 'undelivered', 'canceled'}:
            return {**result, 'error': 'delivery_rejected'}
        return {**result, 'ok': True, 'sid': message.sid}
    except Exception:
        return {**result, 'error': 'twilio_delivery_failed'}
