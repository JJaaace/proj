# Person 3 integration and replay

Run commands from the application root, `AEP_Project/storm-assistant`:

```sh
python -m tests.storm_replay.replay
python -m tests.storm_replay.replay --demo
python -m pytest tests/storm_replay -q -rs
python -m tests.storm_replay.replay --demo --speed fast
python -m tests.storm_replay.replay --demo --step
python -m tests.storm_replay.replay --demo --verbose --audit-json /tmp/storm-audit.json
```

Python 3.11+ is supported. The replay itself uses only the standard library.
Tests require `pytest` (`python -m pip install pytest` in your development
environment). No credentials are needed for the offline demo. Importing the
replay does not import messaging, instantiate SMS clients, or access the network.

All code lives in Person 3's `services/` and `tests/` directories. No shared
contracts or teammate implementations are replaced. The original Section 6
snapshot has exactly 17 fields; all fields are supplied, including `None` values.
The improvement audit, validation results, and precise teammate actions are in
[`IMPROVEMENT_REPORT.md`](IMPROVEMENT_REPORT.md).

## Decision audit and playback

Each source report, changed network impact, changed snapshot, candidate alert,
and messaging outcome has a structured record. `ReplayResult.audit` keeps these
records in memory. `--audit-json` exports them with the final counts and mode.
Version 1 has `format_version`, `mode`, `dry_run`, `notification_delivery`,
`deferred_delivery`, `summary`, and ordered `entries`. Entries have stable sequence
numbers, local simulated time, category, customer/asset IDs, alert type, decision,
reason code, and whitelisted operational details. An emitted alert and its handler
outcome share `details.alert_sequence`. Equal simulated times remain ordered by
entry sequence and operational source index.

The export omits customer names, phones, customer coordinates, message bodies,
raw handler reasons, exception text, and credentials. Unknown handler reasons
produce `MESSAGING_OUTCOME_UNAVAILABLE`; they are not interpreted as consent or
queue behavior. A throttled result is recorded as blocked by messaging, with
deferred support explicitly unverified. A handler exception records a failed
outcome and replay continues; malformed return dictionaries fail clearly.

The console separates `ALERT ... emitted` from `DELIVERY ... handler_sent=...`.
An offline adapter never claims delivery or successful message composition.
`NO_ALERT C-3 reason=NOT_DOWNSTREAM_OF_FAILED_DEVICE` explains the demo neighbor.
The default display shows meaningful frames, ETR ranges/confidence, medical
flags on eligible alerts, and a final per-type/messaging summary. `--verbose`
prints every evaluated candidate type, including non-events and duplicates.

`--speed instant|fast|normal` changes only wall-clock waits between visible
frames (0 / 0.05 / 0.3 seconds). `--step` waits for Enter on interactive input,
and falls back automatically for noninteractive input or EOF. Playback controls
do not change simulated times, audit records, predictions, or alert order.
`--step-minutes` retains its earlier meaning: simulated sampling cadence, not
display speed. Report creation refuses to overwrite any existing file.

## Runtime modes

The default invocation runs the real team modules if integration files exist.
On the current scaffold, where all upstream components are absent, it runs a
prominently labeled **offline fixture demo**. A partial integration fails with a
traceable error; use `--demo` explicitly to work independently. `--integrated`
requires real inputs and never falls back. The fixture handler returns
`sent=False`, `body=None`, and a simulation reason. It does not compose SMS or
implement Atharva's consent, throttling, safety wording, or delivery.

```sh
python -m tests.storm_replay.replay --integrated --crews-available 1
python -m tests.storm_replay.replay --demo --step-minutes 10
```

`--crews-available` is an explicit **simulated assumption**, not a crew inventory
in the shared contract. The offline fixture demo uses one crew by default and
logs this. Integrated mode leaves ETRs unknown unless a crew count is supplied;
agree that count with Teja before the team demo. An assessed known damage type
and an explicit crew count permit `predict_etr`; unknown damage has no estimate.

`--live` is the sole CLI opt-in to live dispatch. It requires integrated mode
and at least one repeated `--verified-demo-phone E164` argument. Providing that
argument attests the phone is team-controlled, verified with the SMS provider,
and opted in. The snapshot must also show opt-in. Other recipients are blocked
before the handler is called. The real messaging layer still applies consent
and guardrails. Do not pass real numbers until Jace explicitly authorizes the
live demonstration. No live demonstration was run during implementation.

## Internal choices

- Operational events are stably sorted by local ISO timestamp. Every timeline
  entry applies exactly once. Equal timestamps retain source order. The replay
  evaluates regular ticks **and exact operational timestamps**, preserving
  failures shorter than one tick. A baseline tick precedes the first event;
  every operational report is evaluated in source order, including reports sharing
  a timestamp. This preserves failure/restoration/new-failure transitions at the
  same local time. Normal `OperationalState.advance()` still consumes all due
  events; the replay driver requests single-event substeps internally.
- All timestamps are naive local datetimes, as specified by Section 6. Offset
  timestamps are rejected. No lifecycle decisions use the machine's clock.
- Only active graph-connected failures can establish an outage. Failures on
  overlapping transformers/feeders/substations are tracked independently.
- For multiple failures, the oldest incident (then device ID) is tracked as the
  internal primary incident. The public cause is `unknown`, with no combined
  ETR or crew claim, because a single confirmed cause is unsupported. Resolving
  one failure leaves the other failures active.
- Restoration is sticky until a new active failure. Outage details clear on
  restoration. An at-risk customer who never loses power retains `at_risk` for
  the MVP; a fifth status or storm-passed reset is not introduced. Known arrival
  in the current high-wind zone supports an at-risk state; pre-storm warnings
  require arrival in the upcoming 12 hours (including now).
- ETRs are cached per device and meaningful operational revision. Recalculation
  uses that revision's event time, not each replay tick. Crew facts or damage
  changes can invalidate an estimate; duplicate unchanged facts do not. A crew
  count supplied to the builder is fixed for the replay.
- Alert ordering for one customer is `pre_storm`, `outage_confirmed`,
  `crew_assigned`, `etr_update`, `restored`. All eligible types are passed to the
  handler, including opted-out customers in dry-run. Person 4 owns delivery
  eligibility, priority, the 30-minute throttle, and its deferred queue.
- ETR updates compare immediate prior known snapshots. A shift of exactly 60
  minutes alone does not alert; 61 minutes does. Confidence changes and initial
  ETR appearance alert once. Losing confidence during an ongoing outage also
  alerts, carrying `None` values instead of fabricating a replacement range.
- `handler_sent` is the handler's reported value, with mode and reason logged;
  the replay does not describe a dry-run or throttle result as phone delivery.
- Timeline references and event sequencing are validated before dispatch.
  Crew events for inactive failures and orphan restoration reports fail clearly.
  Duplicate active failure and repeated restoration reports are consumed once
  as explicit diagnostic no-ops; they do not reset incidents or estimates.
- Network traces are deduplicated and checked against the source electrical
  mappings. A known but incorrectly connected customer is an error. Canonical
  snapshots must have the complete valid contract, and previous snapshots cannot
  come from a future simulated time.

## Upstream handoff

**Shaun:** provide the six `data/sample/*.json` files, canonical
`data.schemas.models.CustomerSnapshot` and `AlertEvent`, and directed network
functions. The loader calls `build_graph()` and verifies expected electrical
edges against record IDs. Supported network imports are package exports or
`analytics.network.graph_builder.build_graph` and
`analytics.network.tracing.downstream_customers`. Confirm whether tracing
initializes its own graph. No alternate graph arguments are added to signatures.

**Teja:** provide `outage_risk` and `predict_etr` as package exports or in
`analytics.predictive.outage_risk` / `analytics.predictive.etr`. Geospatial
functions can be package exports or live in `analytics.geospatial.storm_overlay`,
as named in the original spec. Confirm import locations, crew-count assumption,
arrival semantics for an active storm, and operational anchoring of ETRs.
ETR attributes can be dataclass/Pydantic fields or the specified dictionary.

**Atharva:** export `messaging.handle_alert(event, dry_run=True)` and return
`{sent: bool, body: str | None, reason: str | None}`. Confirm no secrets are
needed in dry-run. **Still unresolved:** document how throttled updates retain
the latest snapshot and flush at the next allowed simulated time, including
when no new event fires. Person 3 does not add a competing deferred queue or
invent a new public API. Confirm same-tick alert ordering, restored bypass,
medical-priority bypass/emergency wording, consent/STOP, and verified live phones.

The isolated wiring test supplies fake canonical factories and fake upstream
packages to exercise constructor identity and public signatures. It is **not**
validation of missing teammate code. The separate real-team end-to-end test is
explicitly skipped until every upstream component is available. Shared schema
serialization, real predictive behavior, Person 4's deferred delivery, medical
message wording, and actual SMS remain integration checkpoints.

## Teja's available branch

`test_person2_branch.py` checks the already-fetched `origin/teja/predictions` ref
using a temporary `git archive`. It never fetches, switches, merges, writes into
`analytics/`, or replaces team code in the working tree. It runs the actual five
Person 2 functions in a subprocess, using labeled fixture data/models/network
and an offline messaging stub for the other roles. If the ref is unavailable,
that test skips with instructions. This is **real Person 2-only coverage**, not
the full real-integration test. At ref `26d8fe4` it yields 19 events: four risk
warnings and the same 15 operational alerts. Both fixture feeders have the same
high-risk attributes under real analytics, unlike the fixture predictor's lower
score for `FDR-2`; `C-3` is warned but remains powered.
