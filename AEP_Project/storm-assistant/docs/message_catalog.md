# Storm Assistant messaging

Person 4 implementation on `person4/messaging-sms`. All examples are synthetic.
Templates use plain, short sentences and `STOP=end`. Facts are deterministic; no
model or network is used to compose. Only English is supported. Safe ASCII
alphabetic first names of at most 20 characters are optional, and omitted if they
would overflow. Messages are never truncated. Character and GSM-7 limits are both
160; extension characters cost two septets. Exact canonical equality is a guardrail.

## Integration and limits

```python
from messaging import handle_alert
result = handle_alert(event)  # simulated by default
# Only the replay's explicit --live branch may call:
# result = handle_alert(event, dry_run=False)
```

Public APIs match the master spec without deviations:
`compose(event: AlertEvent) -> str`, `check(message: str, event: AlertEvent) -> list[str]`,
`allow(customer_id: str, alert_type: str, sim_time: datetime) -> bool`,
`send(phone: str, body: str, dry_run: bool = True) -> dict`, and
`handle_alert(event: AlertEvent, dry_run: bool = True) -> dict`.
Schema annotations import the team's `data.schemas.models.AlertEvent` for type
checking; runtime accepts its attributes or an equivalent wire mapping. There is
no replacement production schema. Each result contains exactly sent/body/reason.

Person 3 owns trigger decisions and per-outage deduplication. Ordinary sends are
limited to one per customer per 30 simulated minutes. Restoration and medical
priority bypass throttling only. Consent and guardrails always apply. Successful
dry runs consume a slot and print a redacted `DRY RUN` trace; failures do not.
Throttle and pending state persist in this process. A new synthetic replay can
call `messaging.reset_for_test()`; never reset consent during a live session.

A throttled event is deep-copied to a per-customer pending-latest store. The next
eligible incoming event uses the newest event and snapshot. Out-of-order normal
alerts are blocked. No worker or timer flushes pending messages: if no subsequent
event arrives, nothing is automatically delivered. Person 3 must agree a replay
tick/flush integration if eventual delivery without another event is needed.

STOP is processed with `consent.handle_inbound(phone_or_customer_id, body)` or
`record_stop(...)`; it suppresses every type even if a stale snapshot opts in.
State resets on process restart. There is no inbound webhook, START enrollment,
or OUT/STATUS reply feature. Twilio's provider-side STOP enforcement supplements
local state; it does not populate local state without an inbound integration.

## Pre-storm (`pre_storm`)

Trigger: status becomes at_risk with risk >= 0.5 and arrival within 12 hours;
once per customer, subject to throttle. Requires at_risk status. A valid arrival
gets its explicit local calendar date and time; null/invalid arrival omits timing.
If timing will not fit, a shorter version omits it. Says possible outages, never
predicts a definite outage. No storm name is available in the snapshot.

## Outage (`outage_confirmed`)

Trigger: status changes to outage_confirmed; once per outage, subject to throttle.
Requires outage_confirmed status. Known causes use the exact root-spec mapping;
null, unknown or unrecognized causes say the cause is not confirmed. Medical
priority replaces optional cause detail with literal `medical.txt` text and
bypasses throttle. Medical copy is DRAFT pending team approval. It fits without
removing safety text or opt-out information.

## Crew (`crew_assigned`)

Trigger: crew state changes from null to assigned/on_site; once per outage,
subject to throttle. Requires outage_confirmed status. Assigned says 'is assigned';
on_site says 'is on site'. Null/unknown says no confirmed crew update. Neither
variant promises arrival or completion times. Medical priority bypasses throttle.

## Estimate (`etr_update`)

Trigger: first ETR, confidence change, or a bound moves by more than 60 minutes;
as needed, subject to throttle. Requires outage_confirmed status. Both valid
bounds, end > start and known confidence are required to show a window. Low
confidence says exactly 'our best early estimate'; medium/high say 'We estimate'.
Missing, inverted or incompatible bounds use 'We do not have a reliable return
time yet.' Cross-date windows include calendar dates on both bounds; oversized
windows use that same fallback. No next-update deadline is invented. Medical
priority bypasses throttle.

## Restoration (`restored`)

Trigger: outage_confirmed becomes restored; once per outage. Requires restored
status. Bypasses throttle and records the successful send time. STOP or lack of
opt-in blocks delivery even for medical priority. Advises contacting the utility
if service remains out, without claiming a reply handler exists.

## Safety review and live demo

All files in `messaging/safety/` are explicitly DRAFT: medical resources, downed
wires, immediate danger/911, and gas smell. Only medical is included by current
templates. Exact byte-for-byte medical copy is pinned in tests. The remaining
snippets are reserved; free-text additions are rejected. Team review is needed
before using safety copy live. After review, set `STORM_SAFETY_COPY_APPROVED=1`
to permit live medical outage alerts. This flag records an operator assertion,
not an automated safety certification.

The master spec asks for next-update timing and illustrates Storm Ava/Reply OUT,
but the shared contract provides no deadline or storm name and replies are
stretch-only. This implementation omits those unsupported claims, as the handoff
instructs. No shared data contracts or other owners' files were changed.

For live delivery install the official `twilio` package locally and privately set
`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`, and a comma-separated
`TWILIO_VERIFIED_TO_NUMBERS` allowlist of team-controlled verified recipients.
Do not commit any values. The replay owner must route synthetic demo events to
an authorized phone and pass dry_run=False only from the explicit --live path.
No real delivery has been attempted. A queued Twilio response means accepted by
the provider, not confirmed handset delivery; observe the handset for acceptance.
No retries are performed. Provider failures expose only safe error codes.

Pending team items: approve safety copy, agree optional flush ticks, configure
verified demo-phone routing, and run the shared replay when Person 1/3 modules
exist. Live verification and the complete storm replay remain integration tasks.

Run tests: `python3 -m unittest discover -s messaging/tests -v`.
All Twilio tests use mocks. No credentials or SDK are needed for dry runs.

Suggested PR: Add Person 4 deterministic storm SMS templates and guardrails,
consent/STOP suppression, simulated-time throttle with latest-event coalescing,
and a dry-run-first Twilio adapter restricted to configured verified recipients.
Include isolated synthetic acceptance tests and this integration runbook.

## Canonical examples

Counts below include names, punctuation and STOP=end. All examples use GSM-7
basic characters, so characters and septets are equal (one segment each).

**pre_storm** (106 characters / 106 septets):

> Hi Maria, Storms may cause outages near you around 10/24/2026 9:15 PM. Charge devices if you can. STOP=end

**outage_confirmed** (73 characters / 73 septets):

> Hi Maria, Your power is out. Cause: a tree fell on a power line. STOP=end

**crew_assigned** (60 characters / 60 septets):

> Hi Maria, A repair crew is assigned to your outage. STOP=end

**etr_update** (74 characters / 74 septets):

> Hi Maria, We estimate power may return between 9 PM and 10:30 PM. STOP=end

**restored** (108 characters / 108 septets):

> Hi Maria, Power has been restored in your area. If yours is still out, please contact your utility. STOP=end

**low confidence** (96 characters / 96 septets):

> Hi Maria, Based on our best early estimate, power may return between 9 PM and 10:30 PM. STOP=end

**no ETR** (61 characters / 61 septets):

> Hi Maria, We do not have a reliable return time yet. STOP=end

**medical outage (draft)** (109 characters / 109 septets):

> Hi Maria, Your power is out. Use your existing medical backup plan or emergency resources if needed. STOP=end

**crew on site** (60 characters / 60 septets):

> Hi Maria, A repair crew is on site for your outage. STOP=end

**Opt-out example:** sms_opt_in=False or a recorded STOP returns `{"sent": false, "body": null, "reason": "no_sms_consent"}`; no SMS (0 segments).
