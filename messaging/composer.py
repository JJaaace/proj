"""Deterministic, snapshot-grounded single-segment SMS composition."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from data.schemas.models import AlertEvent

ROOT = Path(__file__).parent
TYPES = {'pre_storm', 'outage_confirmed', 'crew_assigned', 'etr_update', 'restored'}
CAUSES = {
    'unknown': 'crews are checking the cause',
    'tree_on_line': 'a tree fell on a power line',
    'blown_fuse': 'a fuse protecting your area tripped',
    'broken_pole': 'a damaged utility pole',
    'transformer_failure': 'equipment serving your street failed',
    'substation_damage': 'damage at a local substation',
}
GSM = set("@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà")
EXT = set('^{}\\[~]|€')


def field(obj, name, default=None):
    """Read an object attribute or wire mapping without changing the contract."""
    return obj.get(name, default) if isinstance(obj, dict) else getattr(obj, name, default)


def parse_time(value):
    """Read an ISO timestamp or datetime, returning None for invalid input."""
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def septets(body):
    """Count GSM-7 septets, rejecting characters outside its alphabet."""
    if any(c not in GSM and c not in EXT for c in body):
        raise ValueError('unsupported GSM-7 character')
    return sum(2 if c in EXT else 1 for c in body)


def validate_event(event):
    """Validate mandatory identifiers, event type, simulated time and snapshot status."""
    snapshot = field(event, 'snapshot')
    cid = field(event, 'customer_id')
    kind = field(event, 'alert_type')
    if not isinstance(cid, str) or not cid.strip() or cid != field(snapshot, 'customer_id'):
        raise ValueError('customer_id missing or mismatched')
    if kind not in TYPES or parse_time(field(event, 'sim_time')) is None:
        raise ValueError('invalid alert_type or sim_time')
    expected = {'pre_storm': 'at_risk', 'restored': 'restored'}
    if field(snapshot, 'status') != expected.get(kind, 'outage_confirmed'):
        raise ValueError('snapshot status does not support alert')
    if field(snapshot, 'language') != 'en':
        raise ValueError('unsupported language')
    return snapshot


def clock(value, dated=False):
    """Format the supplied local clock without asserting a time zone."""
    time = f'{value.hour % 12 or 12}'
    if value.minute:
        time += f':{value.minute:02d}'
    time += ' AM' if value.hour < 12 else ' PM'
    return f'{value.month}/{value.day}/{value.year} {time}' if dated else time


def safety(name):
    """Load literal fixed draft safety copy; live use requires explicit sign-off."""
    return (ROOT / 'safety' / f'{name}.txt').read_text().strip()


def compose(event: AlertEvent) -> str:
    """Render one canonical SMS from validated structured facts, never truncating."""
    s = validate_event(event)
    kind = field(event, 'alert_type')
    detail = ''
    if kind == 'pre_storm':
        arrival = parse_time(field(s, 'storm_arrival'))
        detail = f' around {clock(arrival, True)}' if arrival else ''
    elif kind == 'outage_confirmed':
        cause = field(s, 'cause')
        detail = ('Cause: ' + CAUSES[cause] + '.') if cause in CAUSES and cause != 'unknown' else 'The cause is not confirmed.'
        if field(s, 'medical_priority') is True:
            detail = safety('medical')
    elif kind == 'crew_assigned':
        detail = {'assigned': 'A repair crew is assigned to your outage.',
                  'on_site': 'A repair crew is on site for your outage.'}.get(
                      field(s, 'crew_status'), 'There is no confirmed crew update yet.')
    elif kind == 'etr_update':
        start, end = (parse_time(field(s, key)) for key in ('etr_start', 'etr_end'))
        valid = False
        try:
            valid = start is not None and end is not None and end > start
        except TypeError:
            pass
        confidence = field(s, 'confidence')
        if valid and confidence in {'low', 'medium', 'high'}:
            dated = start.date() != end.date() or start.date() != parse_time(field(event, 'sim_time')).date()
            prefix = 'Based on our best early estimate,' if confidence == 'low' else 'We estimate'
            detail = f'{prefix} power may return between {clock(start, dated)} and {clock(end, dated)}.'
        else:
            detail = 'We do not have a reliable return time yet.'
    template = (ROOT / 'templates' / f'{kind}.txt').read_text().strip()
    body = ' '.join(template.format(detail=detail).split())
    # Optional names are used only when short, plain and free of injected content.
    name = field(s, 'first_name')
    if isinstance(name, str) and name.isascii() and name.isalpha() and len(name) <= 20:
        candidate = f'Hi {name}, {body}'
        if len(candidate) <= 160 and septets(candidate) <= 160:
            body = candidate
    if len(body) > 160 or septets(body) > 160:
        if kind == 'etr_update':
            body = 'We do not have a reliable return time yet. STOP=end'
        elif kind == 'pre_storm':
            body = 'Storms may cause outages near you. Charge devices if you can. STOP=end'
        else:
            raise ValueError('canonical message exceeds one SMS segment')
    return body
