"""Synthetic acceptance tests; never contact Twilio or real recipients."""
from copy import deepcopy
from datetime import datetime, timedelta
import io
import os
import sys
from contextlib import redirect_stdout
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock

import messaging
from messaging.composer import compose, septets, safety
from messaging.guardrails import check
from messaging import throttle
from channels.sms import consent, provider


def event(kind='outage_confirmed', minutes=0, **changes):
    """Build a complete fictional wire fixture, independent of production schemas."""
    now = datetime(2026, 10, 24, 20, 0) + timedelta(minutes=minutes)
    snapshot = dict(customer_id='C-1042', first_name='Maria', phone='+16145550123',
                    language='en', sms_opt_in=True, medical_priority=False,
                    feeder_id='FDR-3', transformer_id='TX-17',
                    status={'pre_storm': 'at_risk', 'restored': 'restored'}.get(kind, 'outage_confirmed'),
                    risk_score=.72, storm_arrival='2026-10-24T21:15:00', cause='tree_on_line',
                    etr_start='2026-10-24T21:00:00', etr_end='2026-10-24T22:30:00',
                    confidence='high', crew_status='assigned', updated_at=now.isoformat())
    snapshot.update(changes)
    return dict(alert_type=kind, customer_id=snapshot['customer_id'], snapshot=snapshot,
                previous_snapshot=None, sim_time=now)


class MessagingTests(unittest.TestCase):
    """Verify composition, grounding, consent, throttling and delivery failures."""

    def setUp(self):
        """Isolate all process state and capture dry-run traces."""
        messaging.reset_for_test()
        self.output = io.StringIO()
        self.capture = redirect_stdout(self.output)
        self.capture.__enter__()
        self.addCleanup(self.capture.__exit__, None, None, None)

    def test_five_types_and_objects(self):
        """Every canonical type supports both mappings and object attributes."""
        for kind in ('pre_storm', 'outage_confirmed', 'crew_assigned', 'etr_update', 'restored'):
            e = event(kind)
            body = compose(e)
            self.assertEqual(check(body, e), [])
            self.assertLessEqual(septets(body), 160)
            e['snapshot'] = SimpleNamespace(**e['snapshot'])
            self.assertEqual(compose(SimpleNamespace(**e)), body)

    def test_names_causes_and_missing_times(self):
        """Long or unsafe names and unknown facts cannot inject claims."""
        for cause in (None, 'unknown', 'invalid'):
            body = compose(event(cause=cause, first_name='x' * 300))
            self.assertNotIn('tree fell', body)
            self.assertLessEqual(len(body), 160)
        self.assertIn('a tree fell on a power line', compose(event()))
        for start, end in ((None, None), (None, '2026-10-24T22:00:00'), ('2026-10-24T23:00:00', None),
                           ('2026-10-24T23:00:00', '2026-10-24T21:00:00')):
            body = compose(event('etr_update', etr_start=start, etr_end=end))
            self.assertIn('no', body)
            self.assertNotIn('between', body)

    def test_ranges_and_crew_states(self):
        """Windows, early confidence and crew facts have distinct accurate wording."""
        self.assertIn('between 9 PM and 10:30 PM', compose(event('etr_update')))
        self.assertIn('our best early estimate', compose(event('etr_update', confidence='low')).lower())
        for status, expected in ((None, 'no confirmed'), ('assigned', 'is assigned'), ('on_site', 'is on site')):
            self.assertIn(expected, compose(event('crew_assigned', crew_status=status)))
        body = compose(event('etr_update', etr_end='2026-10-25T01:00:00'))
        self.assertIn('10/25/2026', body)
        self.assertNotIn('tonight', body)

    def test_consent_and_stop_override_exceptions(self):
        """Consent overrides restoration and medical priority without provider calls."""
        with patch.object(provider, 'send') as send:
            self.assertFalse(messaging.handle_alert(event(sms_opt_in=False))['sent'])
            consent.handle_inbound('+16145550123', ' stop ')
            for kind in ('outage_confirmed', 'restored'):
                self.assertFalse(messaging.handle_alert(event(kind, medical_priority=True))['sent'])
            send.assert_not_called()

    def test_throttle_boundaries_and_isolation(self):
        """Successful sends consume one slot per customer for exactly 30 minutes."""
        self.assertTrue(messaging.handle_alert(event())['sent'])
        self.assertFalse(messaging.handle_alert(event(minutes=29))['sent'])
        self.assertFalse(messaging.handle_alert(event(minutes=-1))['sent'])
        self.assertTrue(messaging.handle_alert(event(customer_id='C-1043'))['sent'])
        self.assertTrue(messaging.handle_alert(event(minutes=30))['sent'])
        self.assertFalse(throttle.allow('C-1042', 'etr_update', datetime(2026, 10, 24, 20, 59, 59)))
        self.assertTrue(messaging.handle_alert(event('restored', 31))['sent'])

    def test_medical_and_literal_safety(self):
        """Medical alerts bypass throttle and retain exact fixed draft copy."""
        expected = 'Use your existing medical backup plan or emergency resources if needed.'
        self.assertEqual(safety('medical'), expected)
        for minute in (0, 2):
            e = event(minutes=minute, medical_priority=True)
            body = compose(e)
            self.assertIn(expected, body)
            self.assertTrue(messaging.handle_alert(e)['sent'])
            self.assertTrue(check(body.replace('backup plan', 'plan'), e))
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(messaging.handle_alert(event(medical_priority=True), dry_run=False)['sent'])

    def test_coalescing_latest_snapshot(self):
        """A later eligible event replaces a throttled outdated ETR snapshot."""
        messaging.handle_alert(event())
        self.assertEqual(messaging.handle_alert(event('etr_update', 5))['reason'], 'throttled')
        result = messaging.handle_alert(event('etr_update', 30, etr_end='2026-10-24T23:00:00'))
        self.assertIn('11 PM', result['body'])
        self.assertNotIn('10:30 PM', result['body'])
        self.assertFalse(messaging._pending)

    def test_failed_sends_do_not_consume_slots(self):
        """Guardrail and provider failure both permit a subsequent valid attempt."""
        e = event()
        e['customer_id'] = 'wrong'
        self.assertFalse(messaging.handle_alert(e)['sent'])
        with patch.object(provider, 'send', return_value={'ok': False, 'error': 'mock'}):
            self.assertFalse(messaging.handle_alert(event())['sent'])
        with patch.object(provider, 'send', side_effect=RuntimeError('secret')):
            self.assertNotIn('secret', messaging.handle_alert(event())['reason'])
        self.assertTrue(messaging.handle_alert(event())['sent'])

    def test_guardrails_reject_edits_and_bad_shapes(self):
        """Canonical equality blocks unsupported causes, promises, IDs and safety edits."""
        e = event()
        for body in ('FDR-123 STOP=end', 'TX-99 lateral STOP=end', 'Power back at 9 PM. STOP=end',
                     compose(e).replace('tree', 'truck'), compose(e) + '\n', '🙂 STOP=end', 'x' * 161):
            self.assertTrue(check(body, e))
        for key, value in (('alert_type', 'bad'), ('customer_id', 'mismatch')):
            broken = deepcopy(e)
            broken[key] = value
            self.assertTrue(check(compose(e), broken))
            self.assertFalse(messaging.handle_alert(broken)['sent'])
        self.assertEqual(septets('^{}'), 6)
        self.assertTrue(check('^' * 81, e))

    def test_provider_dry_run_and_live_fail_closed(self):
        """Dry run needs no SDK; live recipients and configuration are mandatory."""
        with patch.dict(sys.modules, {'twilio': None, 'twilio.rest': None}):
            self.assertTrue(provider.send('+16145550123', 'Demo STOP=end')['ok'])
        self.assertIn('DRY RUN TO [redacted-demo-phone]', self.output.getvalue())
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(provider.send('+16145550123', 'Demo STOP=end', False)['ok'])
        with patch.dict(os.environ, {'TWILIO_VERIFIED_TO_NUMBERS': '+16145550123'}, clear=True):
            self.assertEqual(provider.send('+16145550123', 'Demo', False)['error'], 'missing_or_invalid_configuration')
        self.assertFalse(provider.send('invalid', 'Demo')['ok'])
        self.assertFalse(provider.send('+16145550123', '🙂')['ok'])

    def test_mock_live_delivery(self):
        """Mock the official SDK, including transport failure, without network activity."""
        client = Mock()
        client.return_value.messages.create.return_value = SimpleNamespace(sid='fake', status='queued')
        env = dict(TWILIO_VERIFIED_TO_NUMBERS='+16145550123', TWILIO_ACCOUNT_SID='fake',
                   TWILIO_AUTH_TOKEN='fake', TWILIO_FROM_NUMBER='+16145550124')
        with patch.dict(os.environ, env, clear=True), patch.dict(sys.modules, {'twilio': Mock(), 'twilio.rest': SimpleNamespace(Client=client)}):
            self.assertTrue(provider.send('+16145550123', 'Demo', False)['ok'])
            client.return_value.messages.create.side_effect = RuntimeError('secret')
            self.assertEqual(provider.send('+16145550123', 'Demo', False)['error'], 'twilio_delivery_failed')


if __name__ == '__main__':
    unittest.main()
