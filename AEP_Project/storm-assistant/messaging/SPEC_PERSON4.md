# Storm Assistant — Person 4 Implementation Specification

**Workstream:** Messaging, safety guardrails, customer consent, notification throttling, and SMS delivery  
**Owner:** Person 4  
**Target branch:** `person4/messaging-sms`  
**Repository:** `https://github.com/JJaaace/proj`  
**Runtime:** Python 3.11+  
**Status:** Implementation handoff for Codex  
**Authority:** The team's root `SPEC.md` remains the **single source of truth**. This file elaborates Person 4's implementation without changing Sections 3, 5–8, 10, or 11 of that spec.

> **Codex: READ FIRST.** You are implementing **Person 4 only**. Before writing code, read this file in full and the team's master specification (`SPEC.md` if present in the repository, or the original `SPEC.md.pdf` provided by the team). If anything here differs from that master specification, obey the master specification and report the conflict. Do not silently modify data contracts or edit other owners' code. Build the smallest reliable, testable implementation. **Do not send real texts by default.**

---

## 1. Mission and success criteria

Storm Assistant uses synthetic storm, grid, and operational data to produce customer-specific SMS updates. Person 3's service produces an `AlertEvent` with a full `CustomerSnapshot`; your job is to convert that event into a clear, factually grounded, consented SMS, validate it, avoid excessive messages, and optionally send it through Twilio.

**Definition of done:**

1. The five event types (`pre_storm`, `outage_confirmed`, `crew_assigned`, `etr_update`, `restored`) each have a working text template.
2. The exact `compose`, `check`, `allow`, `send`, and `handle_alert` signatures from the root spec exist and work.
3. All outgoing messages are **at most 160 characters** and fit within one GSM-7 SMS segment; all factual details are supported by the event snapshot or a separately approved fixed template.
4. The default is a **dry run** that logs/prints messages, with **no Twilio call**. Real sending requires the demo's explicit `--live` path and `dry_run=False`.
5. Non-opted-in customers and customers who text `STOP` receive no further sends (including restoration messages); consent overrides priority and throttle exceptions.
6. The 30-minute simulated-time throttle works; `restored` and medically prioritized customers bypass **throttling only**.
7. The shared replay can call `messaging.handle_alert(event)` unchanged.
8. `docs/message_catalog.md` explains trigger timing and shows examples for all five types, including no-ETR, low-confidence, medical, opt-out, and restored cases.
9. Automated tests cover the acceptance matrix in Section 13.
10. For a real-phone demo, a Twilio **trial sender** and a team-controlled **verified recipient** are configured privately (not committed) and **at least one** real message is observed on a device.

## 2. Ownership and strict scope

Person 4 may create and modify:

```text
messaging/
  __init__.py                 # PUBLIC entry point: handle_alert
  composer.py                 # compose(event)
  guardrails.py               # check(message, event)
  throttle.py                 # allow(customer_id, alert_type, sim_time)
  templates/
    pre_storm.txt
    outage_confirmed.txt
    crew_assigned.txt
    etr_update.txt
    restored.txt
  safety/                     # Fixed, reviewed safety snippets; not LLM-generated
channels/
  sms/
    __init__.py
    provider.py               # send(phone, body, dry_run=True)
    consent.py                # consent + STOP handling

docs/
  message_catalog.md         # Person 4 explicitly owns this document

messaging/SPEC_PERSON4.md     # This handoff specification
```

Put **Person-4-specific tests** under the owned `messaging/` or `channels/sms/` trees if cross-team `tests/` ownership has not been approved. If the team agrees to shared test files, add them to `tests/` in a separate coordination step.

**Do not change** `data/schemas/models.py`, `data/sample/`, `analytics/`, `services/`, `tests/storm_replay/replay.py`, the root `SPEC.md`, or the root `README.md` without explicit team approval. If integration requires changes elsewhere, document the required change and provide a suggested patch for the owning teammate instead of silently editing it. The future `channels/web/`, `channels/voice/`, and `dashboard/` paths are out of scope.

## 3. External contracts — preserve these exactly

### 3.1 Incoming `CustomerSnapshot`

It is defined by Person 1 in `data/schemas/models.py` and built by Person 3. **Every listed field is present**, with `None`/`null` when unknown. Sample wire shape:

```json
{
  "customer_id": "C-1042",
  "first_name": "Maria",
  "phone": "+16145550123",
  "language": "en",
  "sms_opt_in": true,
  "medical_priority": false,
  "feeder_id": "FDR-3",
  "transformer_id": "TX-17",
  "status": "outage_confirmed",
  "risk_score": 0.72,
  "storm_arrival": "2026-10-24T19:15:00",
  "cause": "tree_on_line",
  "etr_start": "2026-10-24T21:00:00",
  "etr_end": "2026-10-24T22:30:00",
  "confidence": "high",
  "crew_status": "on_site",
  "updated_at": "2026-10-24T20:05:00"
}
```

Allowed values:

- `status`: `normal`, `at_risk`, `outage_confirmed`, `restored`
- `cause`: `unknown`, `tree_on_line`, `blown_fuse`, `broken_pole`, `transformer_failure`, `substation_damage`, or `None`
- `confidence`: `low`, `medium`, `high`, or `None` when ETR is unavailable
- `crew_status`: `None`, `assigned`, `on_site`
- `language`: `en` for MVP; Spanish is explicitly stretch-only
- Timestamp fields are local-time ISO-8601 strings in the fixture/wire examples. Dataclass/Pydantic instances may expose Python `datetime` values.

**Important:** There is **no `storm_name`, `next_update_at`, `address`, or `emergency_resources_url` field** in this contract. Do not fabricate those values. You may use a constant such as `Storm Assistant` as a service label, not as evidence of a particular storm or utility. Do not promise a next update by a specific time unless a team-approved data source is added under an agreed contract revision.

### 3.2 Incoming `AlertEvent`

```json
{
  "alert_type": "etr_update",
  "customer_id": "C-1042",
  "snapshot": {"...": "complete CustomerSnapshot"},
  "previous_snapshot": null,
  "sim_time": "2026-10-24T20:05:00"
}
```

`previous_snapshot` can be a full snapshot or `None`. `alert_type` is exactly one of the five names below. The event's `customer_id` should match `snapshot.customer_id`; a mismatch must be rejected, not guessed around.

### 3.3 Required public Python API — **do not rename**

```python
# messaging/composer.py
def compose(event: AlertEvent) -> str: ...

# messaging/guardrails.py
def check(message: str, event: AlertEvent) -> list[str]: ...

# messaging/throttle.py
def allow(customer_id: str, alert_type: str, sim_time: datetime) -> bool: ...

# channels/sms/provider.py
def send(phone: str, body: str, dry_run: bool = True) -> dict: ...

# messaging/__init__.py
def handle_alert(event: AlertEvent, dry_run: bool = True) -> dict: ...
# Returns {"sent": bool, "body": str | None, "reason": str | None}
```

Import `AlertEvent` from the **existing** `data.schemas.models` when available. For early isolated tests, use a matching lightweight test fixture rather than redefining the production schema. Permit standard Python object attributes; optionally support mappings internally when needed for tests, without changing the official contract.

### 3.4 Allowed cause labels — exact shared keys

| `cause` key | Approved plain-language phrase |
|---|---|
| `unknown` | `crews are checking the cause` |
| `tree_on_line` | `a tree fell on a power line` |
| `blown_fuse` | `a fuse protecting your area tripped` |
| `broken_pole` | `a damaged utility pole` |
| `transformer_failure` | `equipment serving your street failed` |
| `substation_damage` | `damage at a local substation` |

The human-readable phrases above come from the root spec. A `None` cause means **unconfirmed**; do not accidentally state one. Internal IDs, feeder names, transformer IDs, fault codes, and model risk percentages are never SMS content.

## 4. Event types and trigger ownership

Person 3 generates events; Person 4 **must not independently calculate** whether an outage exists, which customers are affected, or whether an ETR has changed enough to merit an event.

| Event | Person 3 trigger (reference only) | Messaging behavior |
|---|---|---|
| `pre_storm` | Status becomes `at_risk`, risk >= 0.5, storm arrival within 12 hours; once per customer | Warn about **possible** outages, describe preparation, optionally use known `storm_arrival` time; never guarantee an outage. |
| `outage_confirmed` | Status changes to `outage_confirmed`; once per outage | Confirm outage, describe known cause or uncertainty; medical-priority text points to emergency resources or immediate safety guidance. |
| `crew_assigned` | `crew_status` changes from null to `assigned` or `on_site`; once per outage | Say crew assigned or on site **only if reflected in the snapshot**. No inferred arrival or repair promise. |
| `etr_update` | ETR first appears, confidence changes, or start/end moves by **more than** 60 min | Show ETR as a range **only if both bounds exist**; otherwise say no dependable estimate yet. Use careful language for low confidence. |
| `restored` | Status changes from `outage_confirmed` to `restored`; once per outage | State that service has been restored per the snapshot. Deliver despite throttle, but never without SMS consent. |

**Duplicate suppression:** Person 3 owns event generation / per-outage trigger counts. Person 4 owns rate limiting and can add narrowly scoped duplicate-send protection as an internal implementation detail if it does not drop legitimate ETR changes or violate restoration/medical exceptions.

## 5. Message content and templates

Create exactly one `.txt` file for each alert type. Templates must be easy to audit. Prefer **deterministic code and fixed text**; an LLM is a stretch goal only. Plain-language reading level is approximately grade 8. Avoid fear, absolutes, jargon, fake precision, and marketing language.

### 5.1 Formatting rules

- **Hard cap: 160 characters including spaces and opt-out suffix.** To actually fit in one SMS segment, also validate **GSM-7 encoded length <= 160 septets**. GSM-7 extension characters count as two septets; unsupported Unicode can cause multipart delivery, so replace safely before validation or reject.
- Always include an opt-out footer where required; for this demo use `STOP=end` consistently. It is explicitly permitted in the root spec as a short form of `Reply STOP to opt out`.
- Trim and normalize whitespace; SMS should be one physical line (even if the source template spans multiple lines).
- Use real first names only if present and safely displayable; otherwise use a generic greeting. Test with long names; prefer dropping the greeting over clipping essential facts.
- No internal identifiers like `FDR-3`, `TX-17`, `lateral`, or a raw customer ID in SMS.
- Avoid specific times for storm arrival, next update, or restoration unless directly grounded in the snapshot/approved data.
- An ETR is always a **window**, e.g., `between 9 PM and 10:30 PM`. Never output just `at 9 PM` as a firm restoration promise.
- `confidence=low`: include the exact qualification `our best early estimate` where an ETR range is shown. Medium/high may say `we estimate`; never guarantee.
- If either `etr_start` or `etr_end` is null, show **no ETR**, never infer a missing bound. If the range is invalid (`end < start`), suppress the ETR and surface a guardrail failure or a safe no-ETR fallback.
- Treat all time values as **local time**, consistent with the root spec; do not append an unverified time zone. For a cross-date range, show date context rather than saying `tonight` incorrectly. If a date-aware window will not fit, omit the time range and explain that an estimate is not ready rather than truncating it.
- Use only ASCII/GSM-safe punctuation in templates (straight apostrophes/hyphens). Never cut off the opt-out text or emergency safety text to meet the cap.

### 5.2 Suggested template intentions (implementation examples, not a new schema)

The initial fixed text below deliberately avoids fields absent from the snapshot. Codex should refine the final text to meet all 160-character, consent, and safety checks:

**`pre_storm.txt`**  
`Hi {first_name}, storms may cause outages near you {arrival_phrase}. Charge devices if you can. STOP=end`  
`arrival_phrase` is computed **only when `storm_arrival` is valid**; otherwise use a phrase without timing.

**`outage_confirmed.txt`**  
`{first_name}, your power is out. Cause: {cause_phrase}. Crews are working to assess the problem. STOP=end`  
If unknown, do not write `Cause: crews are checking the cause` awkwardly; use a distinct safe variant. For medically prioritized customers, include a **reviewed fixed emergency/backup-plan pointer**, and shorten other optional wording as needed. Do not claim a specific assistance phone number or web link not provided by the team.

**`crew_assigned.txt`**  
`{first_name}, a repair crew has been assigned to your outage. We will share an update when we know more. STOP=end`  
When `crew_status=on_site`, replace `assigned` with `is on site`; do not imply both states are the same.

**`etr_update.txt`**  
`{first_name}, {confidence_phrase} power may return between {start} and {end}. STOP=end`  
When no valid range exists: `{first_name}, crews are assessing the outage. We do not have a reliable return time yet. STOP=end`  
For low confidence, the `confidence_phrase` must contain `our best early estimate` in a grammatical form.

**`restored.txt`**  
`{first_name}, power has been restored in your area. If yours is still out, please contact your utility. STOP=end`  
The root spec's illustrative restored SMS says `Reply OUT`, but two-way SMS is explicitly a stretch goal. Do **not** promise `Reply OUT` works until that feature is implemented.

These are **starting templates**. A pure formatter may select short/long variants based on field availability, as long as the canonical five `.txt` files exist and messages remain deterministic and auditable. Document every variant.

### 5.3 Safety messages are fixed, never AI-generated

Create `messaging/safety/` for reviewed safety snippets. The root spec requires fixed wording for downed wires, gas smell, calling 911, and medical-priority emergency resources. It **does not supply the exact approved strings**. Obtain team sign-off on those snippets before a live safety-focused demonstration. Until then, use clearly marked draft copy in the codebase and **do not invent emergency phone numbers, utility hotlines, or URLs**. For serious immediate danger, a candidate reviewed warning is `Stay away from downed wires. If in immediate danger, call 911.`; do not assert an unapproved detail about the specific customer.

For medical-priority outage alerts, reserve a fixed slot to advise use of existing backup or emergency resources. The root spec requires this outreach for the outage alert. Ensure it fits 160 characters and does not supersede consent. Tests should compare safety snippets **byte-for-byte** against fixed approved files.

## 6. Composer (`messaging/composer.py`)

Implement exactly `compose(event: AlertEvent) -> str`.

**Responsibilities:**

1. Validate the `alert_type` and event/snapshot shape well enough to fail safely.
2. Map `cause` to the exact approved plain-language phrase without inserting internal IDs.
3. Format known times in a readable local style, only if known and valid.
4. Distinguish between assigned and on-site crews; unknown crew state stays unknown.
5. Use high/medium/low confidence wording with the required low-confidence qualification.
6. Include medical-priority emergency-resource wording in `outage_confirmed`, using fixed reviewed text.
7. Include a short opt-out suffix and normalize spaces.
8. Prefer explicit, deterministic short variants if length becomes tight; **never blindly truncate** names, ETR windows, opt-out info, or safety copy.

**Implementation advice:** use `pathlib.Path(__file__).parent / "templates"` to load template files; use tiny helper functions like `_get_field`, `_parse_time`, `_format_time`, `_cause_phrase`, `_render_template`. Keep the public signature exact. No network I/O, no Twilio calls, no random wording, and no model calls here.

**Error handling:** unrecognized alert types or malformed mandatory identifiers should fail closed (clear error to caller). Missing optional facts should use a generic truthful variant. Let `handle_alert` catch errors and return a non-send result with a reason, rather than allowing demo replay to crash.

## 7. Guardrails (`messaging/guardrails.py`)

Implement exactly `check(message: str, event: AlertEvent) -> list[str]`. Return `[]` on success; otherwise return **human-readable issue strings**. **Do not send** messages with any issues.

At minimum validate:

1. Nonempty body, <=160 Unicode characters and <=160 GSM-7 septets (single segment), no unsupported characters or line breaks.
2. `event.customer_id == event.snapshot.customer_id`; required event/snapshot data can be read.
3. `sms_opt_in is True` (the consent module also checks this before composing).
4. The body includes the agreed opt-out suffix for the demo.
5. No internal IDs (reject patterns for feeder/transformer/customer IDs, not merely the example `FDR-3`), no forbidden jargon.
6. If an ETR is present **in the message**, both snapshot ETR bounds exist, are valid, and are represented as a **range**. Never convey exact restoration as a promise.
7. When a range appears with `confidence=low`, required phrase `our best early estimate` is present.
8. Any claimed cause belongs to the approved mapping and matches the snapshot; if cause is null or `unknown`, no confident specific cause appears.
9. Claims that a crew has arrived/been assigned are supported by `crew_status`.
10. `outage_confirmed` messages to `medical_priority=True` contain the approved, literal fixed medical-emergency text.
11. Any safety sentence included is an exact approved snippet from `messaging/safety/`, not a paraphrase.
12. An invalid/unknown `alert_type` is blocked.

Use deterministic checks: known template variants, canonical rendered facts, and exact safety fragments are preferable to attempting unreliable free-text NLP. One practical approach is to **re-compose the canonical expected message** and require equality, then run length/segment/safety checks; this makes it harder for unsupported facts to bypass checks while preserving the public `check(...)` API. Ensure no circular import between composer and guardrails.

**Logging:** log a safe code/reason and `customer_id`; avoid logging secrets. In live mode, be mindful that full body and telephone number are customer data. Only use fake numbers/team-controlled recipient numbers for the hackathon.

## 8. Throttle (`messaging/throttle.py`)

Implement exactly:

```python
def allow(customer_id: str, alert_type: str, sim_time: datetime) -> bool: ...
```

**Rules from root spec:** no more than **one message per customer every 30 simulated minutes**; `restored` always bypasses throttle; medically prioritized customers receive all types without throttling. Medical priority is **not an argument** to the required `allow` signature, so **do not add a required argument**. Keep the public API unchanged and implement medical bypass in `handle_alert` based on `event.snapshot.medical_priority`.

**Suggested simple design:**

- Maintain per-customer **successful delivery** time in a small in-memory store for a replay process. A `reset()` helper for tests is fine; don't modify `allow`'s signature.
- `allow(...)` evaluates against `sim_time`, never wall-clock time.
- **Only commit/update throttle state after successful `send`** (or successful dry-run print), not before a guardrail failure or provider exception. If `allow` must be implemented as stateful for simplicity, add a private `_mark_sent(...)` method and document its internal behavior.
- If the last sent time is `19:00`, normal alerts at `19:29:59` are blocked; `19:30:00` is eligible.
- Suppression is **per customer**, not per event type.
- `restored` always bypasses throttle, but it still needs consent and valid guardrails; record a successful restoration as a send.
- For out-of-order simulated timestamps, **do not mistakenly allow another send** by interpreting negative elapsed time as sufficient elapsed time. Handle as a block or explicit reset for a new replay.

**Required coalescing behavior:** If a message is blocked, the **latest information** should appear in the next allowed message (root spec Section 7). Person 3 controls future event emission, and the public `handle_alert` API has no scheduled flush argument. Implement a **small internal pending-latest queue per customer** *or* explicitly coordinate a replay-driven flush mechanism with Person 3 **without changing signatures**. Store the newest event/snapshot, not a stale rendered SMS. When the next eligible event is handled, send the newest relevant snapshot rather than an outdated one. Note and test that a blocked event with **no future events** cannot be delivered automatically without an agreed replay tick/flush integration. Do not quietly claim that it will send itself later.

Keep this simple: no Celery, Redis, background workers, sleeping, or external queue for a hackathon replay.

## 9. Consent and STOP (`channels/sms/consent.py`)

There is no prescribed public function signature here; choose small, documented helpers such as `is_allowed(snapshot)`, `record_stop(phone_or_customer_id)`, and `reset_for_test()`.

Requirements:

- Initial eligibility requires `snapshot.sms_opt_in is True`.
- Honor opt-outs recorded during the session even if the initial snapshot still says `sms_opt_in=True` (the opt-out overrides stale snapshot data).
- Treat `STOP` (case-insensitive, trimmed; optionally Twilio's equivalent opt-out words) as opt-out. `START` handling is optional and must not silently override source-of-truth consent without a documented policy.
- Do **not** send a routine alert, including `restored` or a medical-priority alert, after STOP.
- Restrict test sends to team-controlled, verified phone numbers in live Twilio trial mode; a `+1...` shape alone is not authorization.
- Do not commit a real recipient directory. Use environment variables or a local ignored config for the demo.
- If using Twilio's built-in Advanced Opt-Out behavior, document how provider-level STOP enforcement and the app-level opt-out state interact. An inbound webhook is optional integration and should never be assumed operational if no endpoint exists.
- For in-memory STOP state, document that it resets when the program restarts. A local ignored persistent file is acceptable if the team needs STOP to survive restart; **do not store real phone numbers in git**.

## 10. SMS adapter (`channels/sms/provider.py`)

Implement exactly:

```python
def send(phone: str, body: str, dry_run: bool = True) -> dict: ...
```

Dry-run path (default): print/log a readable `TO [redacted-demo-phone]: [body]` trace and return a success-shaped dictionary for the simulated delivery. **Do not instantiate a Twilio client, require Twilio credentials, or make any outbound request** when `dry_run=True`.

Live path (`dry_run=False`):

- Use the official `twilio` Python package. Read `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER` from environment variables (possibly via `python-dotenv`, but never check in `.env`).
- Require an explicit allowlist of the team's **verified recipient** numbers (e.g. a `TWILIO_VERIFIED_TO_NUMBERS` env var). If the recipient is not listed, fail closed. Trial restrictions also apply on Twilio's side.
- Validate nonempty E.164-like phone input and body; do not reinterpret/guess recipient numbers.
- Return meaningful adapter information such as `{"ok": true, "dry_run": true, "sid": null}` or a consistent error representation. This is **implementation detail**, not a change to `handle_alert`'s public return contract.
- Catch Twilio/transport errors and return/report failure without claiming success. Do not reveal credentials in logs or exception text.
- Make no retry loop that could send duplicates during the demo.

**Privacy:** The provided sample customer phone is synthetic. Never send it live merely because it looks formatted correctly. For the demo, use **only verified team-controlled recipients**, configured outside version control. Person 3 may route sample events to the verified test recipient by agreed demo-only configuration; do not change the shared `CustomerSnapshot` schema to accomplish this.

## 11. Public orchestration (`messaging/__init__.py`)

Implement exactly:

```python
def handle_alert(event: AlertEvent, dry_run: bool = True) -> dict:
    """Validate eligibility and send one customer-facing SMS for an alert."""
    ...
```

Required processing order from the root spec:

```text
Person 3 produces AlertEvent
   ↓
1. Consent / STOP eligibility
   ↓
2. Throttle eligibility (except restored or medical_priority)
   ↓
3. Compose a message grounded in the snapshot
   ↓
4. Guardrail validation
   ↓
5. SMS provider (DRY RUN BY DEFAULT)
   ↓
6. Mark successful send / update pending state / return result
```

Return **exactly the documented keys**:

```python
{"sent": True, "body": "...", "reason": None}
{"sent": False, "body": None, "reason": "no_sms_consent"}
{"sent": False, "body": None, "reason": "throttled"}
{"sent": False, "body": None, "reason": "guardrail_failed: ..."}
{"sent": False, "body": None, "reason": "provider_error: ..."}
```

Reason strings above are **recommended**, not extra required schema fields. A successful dry run can count as `sent=True` for replay/demo purposes **only if clearly labeled as simulated** in logs. A provider exception or failed guardrail cannot count as a send or consume a throttle slot. Avoid exposing full phone numbers in routine logs.

**Integration contract:** Person 3 should only need:

```python
from messaging import handle_alert
result = handle_alert(event)                # simulated by default
result = handle_alert(event, dry_run=False) # only when replay invoked with --live
```

If actual `AlertEvent` uses dataclasses or Pydantic classes, honor its attributes; do not force Person 3 to emit a different shape.

## 12. Implementation sequence for Codex

Work in small, testable commits **on `person4/messaging-sms`**, following this order:

1. Inspect the master specification (the repository root `SPEC.md`, if it exists, otherwise the supplied `SPEC.md.pdf`), repository tree, current branch, and schemas (if present). Do not overwrite teammates' files.
2. Add the five canonical template files and fixed safety text files (mark any unapproved safety wording for human approval).
3. Implement `composer.py` with exact cause mapping, time formatting, safe variants, and opt-out suffix.
4. Implement `guardrails.py` with length, GSM-7, factual support, ID/jargon, ETR range/confidence, consent, and safety checks.
5. Implement `throttle.py` and an isolated deterministic way to reset state for tests; add pending-latest handling or document the Person 3 flush hook needed for a no-future-event case.
6. Implement `channels/sms/consent.py`, including in-session STOP handling and testable opt-out checks.
7. Implement `channels/sms/provider.py` with a pure dry-run default, environment-controlled Twilio live mode, trial restrictions, and clear success/failure.
8. Wire `handle_alert` in `messaging/__init__.py` with exact public keys, error handling, and mark-on-success behavior.
9. Write automated tests and `docs/message_catalog.md`.
10. Run all tests, check formatting/imports, exercise the complete replay **if teammate modules exist**, and show sample stdout. Do not create dummy production schemas that conflict with Person 1's eventual schema.
11. Commit changes only to Person 4-owned files. Report blockers separately; do not modify other owners' work to "make tests pass."

**Dependency handling:** Missing Person 1/3 modules must not halt your progress. Use fixtures in tests that match the exact snapshot/event fields. Keep imports contained so a missing shared schema during early development is a documented integration dependency, not a silent contract replacement.

## 13. Test and acceptance matrix

Automate the following using the Python standard library or `pytest`. Use **synthetic customers only** and mock Twilio for all tests.

| ID | Given | Expected |
|---|---|---|
| P4-01 | Each of five valid event types | A rendered, nonempty canonical SMS from its matching template |
| P4-02 | Long first name and long ETR strings | Still <=160 chars and <=160 GSM-7 septets, or blocked with a reason; never silently truncated |
| P4-03 | Unknown `cause`/null cause | No fabricated failure diagnosis |
| P4-04 | `tree_on_line` | Uses `a tree fell on a power line`, not an internal failure ID |
| P4-05 | `etr_start=None`, `etr_end=None` | No invented return time |
| P4-06 | Exactly one ETR bound present | No incomplete range sent |
| P4-07 | Both ETR bounds and high confidence | Human-readable **range**, not point estimate |
| P4-08 | Both bounds and low confidence | Range includes `our best early estimate` |
| P4-09 | Invalid end before start | Guardrail failure or safe no-ETR variant; never display inverted interval |
| P4-10 | `crew_status=None` | Never claim a crew is assigned/on site |
| P4-11 | `crew_status=assigned` vs `on_site` | Correct, different phrasing |
| P4-12 | `sms_opt_in=False` | No provider call, `sent=False` |
| P4-13 | A recorded `STOP` followed by an alert | No provider call, even for restored/medical |
| P4-14 | Normal alerts at T and T+29 min | First sent, second throttled |
| P4-15 | Normal alerts at T and T+30 min | Both eligible after successful first send |
| P4-16 | A restored alert at T+1 min | Eligible despite throttle, subject to consent and guardrails |
| P4-17 | `medical_priority=True` two minutes apart | Both allowed through throttle, subject to consent/guardrails |
| P4-18 | Medical outage alert | Includes approved fixed emergency-resource text, fits length |
| P4-19 | A throttled ETR update later superseded | Latest eligible snapshot is reflected, never obsolete ETR |
| P4-20 | Failed guardrails or failed Twilio call | `sent=False`; no throttle slot consumed |
| P4-21 | Default `send(...)` and `handle_alert(...)` | No Twilio client/network call; stdout/log clearly dry-run |
| P4-22 | Live mode with missing credentials or unverified recipient | Safely fails; never sends |
| P4-23 | Body contains `FDR-3`, `TX-17`, or forbidden jargon | Guardrail issue and no send |
| P4-24 | Canonical safety snippet is altered | Guardrail issue and no send |
| P4-25 | `event.customer_id` mismatches snapshot | Guardrail issue and no send |
| P4-26 | Cross-date ETR or storm arrival | No false `tonight` label; conservative date-aware wording |
| P4-27 | Multiple customer IDs | Throttle state isolated per customer |
| P4-28 | Same customer, out-of-order simulated time | No accidental throttle bypass |
| P4-29 | Non-GSM Unicode / extension characters | Correct segment-length check or safe rejection |
| P4-30 | Full replay, when integrated | Pre-storm → outage → crew → ETR → restored; dry-run works without Twilio |

For test speed, **do not sleep**. Pass explicit `sim_time` values. Where the actual schema package does not yet exist, test with small fixtures that expose the same field names and value types.

## 14. Message catalog requirements

Create `docs/message_catalog.md` with a section for every event. Each should include:

- exact event name; Person 3 trigger rule; frequency/30-minute limits and exceptions;
- required snapshot fields and safe behavior when optional data is null;
- canonical example output and total characters / GSM-7 septets;
- plain-English rationale, reading-level choice, confidence semantics;
- medical-priority treatment if relevant, fixed safety wording, and opt-out suffix;
- at least one edge case: no ETR, revised ETR, assigned vs on site, restored despite throttle, or STOP;
- indication of which snippets need team sign-off before live demonstration.

Avoid documenting unsupported replies such as `OUT` as active features unless implemented.

## 15. Integration contract with Person 3 and demo runbook

**Person 3 provides:** actual `AlertEvent` objects with snapshots, correctly scoped affected customers, and simulated timestamps. Person 4 never traces the grid or computes customer risk. Share a short note with Person 3 documenting the `handle_alert` import, `dry_run` flag, persistent replay-time throttle state, and any optional pending-alert flush needed when no future event occurs.

**Demo preflight:**

1. Run `python -m tests.storm_replay.replay` in dry run: no Twilio credentials needed, no actual messages.
2. Verify that a simulated nonaffected neighbor receives **no outage** alert; this is Person 1/3's tracing responsibility, not a messaging heuristic.
3. Verify that the medically prioritized customer receives timely alerts and approved emergency-resource wording.
4. Confirm all printed messages pass `check(...)`, fit one segment, and include required opt-out info.
5. Verify STOP suppression locally and ensure no real personal information is in the repo.
6. For live demo, separately configure the Twilio trial account, trial sender, and team-owned verified numbers; test a single permitted recipient.
7. Run `python -m tests.storm_replay.replay --live` **only with team consent and verified numbers**; the replay owner controls the flag. Confirm one physical handset receives an alert.
8. Do not live-send to fictional customer phone numbers from the sample data.

## 16. Implementation constraints and change policy

- Stay inside Person 4-owned paths; do not edit data contracts without team agreement.
- Standard library + `twilio`, `python-dotenv` (optional), and `pytest` are enough. Prefer readable synchronous code over infrastructure.
- Provide a docstring for **every function**, as required by root Section 11.
- Keep sample fixtures fictional. Never commit `.env`, account SIDs/tokens, personal phone numbers, or a real recipient list.
- Preserve the demo-ready mainline: do not merge a broken replay into `main`.
- No LLM-generated safety facts; any later model-based personalization is **stretch-only**, downstream of approved structured facts and deterministic guardrails.
- For missing/ambiguous data, say less rather than guessing.

### Known interface boundaries to discuss, not silently "fix"

1. **Storm name absent from snapshot:** root example references `Storm Ava`; the contracted snapshot does not. Omit the name unless an approved fixed external context is provided.
2. **Next-update deadline absent:** root outage example says `Next update by 9 PM`; the snapshot lacks a next-update field. Do not generate such a promise.
3. **`Reply OUT` is stretch-only:** root restoration example includes it, but inbound status/reply processing is not an MVP goal. Don't claim it works.
4. **Medical priority vs throttle signature:** `allow` has no medical-priority parameter; bypass in `handle_alert`, without changing the signature.
5. **Throttled events without future ticks:** latest-event coalescing needs either a later event or a Person-3-driven flush. Document the limitation and coordinate the smallest integration hook.
6. **Exact safety copy unspecified:** draft safety text needs team approval before live safety claims.
7. **GSM vs character count:** the root spec specifies <=160 characters; additionally ensuring one GSM segment is a conservative implementation detail, not a change to the outward data contract.

## 17. Final output required from Codex

When implementation is complete, report:

- current branch name and files changed;
- public API signatures and any deviations (there should be none);
- test command(s), passing counts, and example dry-run console output;
- sample outputs for all five alert types with character/segment counts;
- Twilio live-mode environment variable names (never values), whether live delivery was actually tested, and any verification blockers;
- outstanding team sign-offs (safety copy, optional flush behavior, demo-phone routing);
- integration instructions for Person 3 and a short PR description.

**No silent assumptions. No real SMS until explicitly enabled. No edits outside Person 4's scope.**
