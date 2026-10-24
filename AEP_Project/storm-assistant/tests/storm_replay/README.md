# Storm replay and integration testing

Run from `AEP_Project/storm-assistant` in the validated environment:

```sh
source /tmp/storm-full-system-env/bin/activate
python3 -m tests.storm_replay.replay
python3 -m tests.storm_replay.replay --integrated --crews-available 1
python3 -m tests.storm_replay.replay --speed fast
python3 -m tests.storm_replay.replay --step
python3 -m tests.storm_replay.replay --verbose --audit-json /tmp/storm-integrated-audit.json
python3 -m pytest -q -rs
```

Default mode now loads the real canonical town, graph, prediction/geospatial
functions, schemas, and messaging handler. No teammate module is mocked on this
path. `--demo` intentionally retains the old offline Person 3 fixtures:

```sh
python3 -m tests.storm_replay.replay --demo --speed fast
python3 -m tests.storm_replay.replay --demo --verbose --audit-json /tmp/storm-audit.json
```

Use a fresh audit filename; existing files are preserved. The full-system run
emits 11 source alerts, whereas the earlier fixture demo emits 18. These are
different scenarios. See the [current integration report](../../INTEGRATION_REPORT.md)
for the actual per-type/customer outcomes. The [earlier improvement report](IMPROVEMENT_REPORT.md)
is historical evidence for commit `52cd167`, not current integration status.

## Contracts and operational semantics

Canonical `CustomerSnapshot` and `AlertEvent` classes remain Person 1's unchanged
models. The constructor helper honors their declared ISO-string timestamps;
mock-unit models can retain datetime attributes. Source offsets are normalized
in memory to America/New_York local wall time, then the simulation consistently
uses naive local datetimes. Mixed aware/naive source documents fail clearly.

Confirmed device failures alone cause outages. Traces are checked against source
electrical IDs. Multiple upstream/downstream failures remain independent until
all relevant repairs occur. Reports at the same timestamp are evaluated in source
order; duplicate fail/restore reports are diagnostic no-ops. Repeated clock ticks
do not produce duplicate source events. Snapshots and prior-state times are
validated before typed alerts are built.

The trigger thresholds remain risk >= 0.5 with upcoming arrival within 12 hours,
strictly more than 60 minutes for an ETR bound shift, first ETR appearance, and
confidence changes. Restoration is sticky until a new confirmed failure. For the
MVP, an unoutaged at-risk customer retains that state after storm passage. Unknown
damage has no snapshot ETR; after known damage, Teja's predictor supplies an
anchored range/confidence using the configured simulated crew count (default 1).
Timeline ETR hints lack a shared confidence/precedence contract and are not used
as an alternative predictor.

## Deferred delivery extension

All required public functions and their signatures are unchanged. Messaging owns
the only pending queue, consent, throttle, templates, guardrails, and SMS provider.
Two optional **private integration hooks**, `messaging._advance_clock` and
`messaging._next_pending_time`, let the replay advance to the earliest pending
30-minute deadline, refresh the pending alert from the current canonical snapshot,
and re-enter the existing `handle_alert` pipeline. This is an additive internal
extension, not a new public shared contract. Review it with Atharva before merging.

Deferred results have separate audit/outcome records and do not fabricate new
source AlertEvents. Restored events clear old pending information immediately.
STOP and source opt-out override ordinary, medical, restoration, and pending
messages. Future snapshot facts cannot enter the pending delivery path. Failed
provider attempts do not consume a successful-send throttle slot.

Independent dry-run replays reset the actual messaging layer through its existing
`reset_for_test` hook. That reset is never performed automatically for live runs.
Medical-priority flags remain on internal canonical snapshots/events, but are
excluded from console and exported audit details. Fixed safety text is unchanged.

## Audit and playback

Structured categories cover operational events, network traces, snapshot changes,
all five candidate decisions, source delivery outcomes, and deferred outcomes.
Every emitted source alert has an `alert_sequence` linking its handler outcome;
a deferred outcome links to the previously throttled source alert. Unknown handler
reasons remain unknown, while actual consent/throttle/guardrail/provider result
codes are recognized conservatively. Medical flags, names, phones, raw SMS bodies,
raw handler reasons, and exception text are excluded from public output.

`--speed instant|fast|normal` changes only wall-clock waits (0 / 0.05 / 0.3 seconds).
`--step` prompts only with interactive input, with a noninteractive/EOF fallback.
`--step-minutes` changes simulated sampling cadence, not presentation speed.
The default console shows meaningful frames and network-based exclusions;
`--verbose` explains every evaluated candidate.

## Test coverage and provenance

- Mock-unit: isolated source-shaped fixtures exercise Person 3 edge cases.
- Real integration: actual four-person code, canonical fixtures and schemas,
  actual messaging/guardrails, dry-run provider, and blocked outbound sockets.
- Person 2-only: a temporary archive of the already-fetched teammate branch
  verifies its APIs without a branch switch or merge. Other roles are labeled
  stand-ins in that additional test.

The previously skipped real integration test now runs. `test_full_system.py`
adds real graph validation, multiple-failure restoration, canonical wire types,
consent/STOP, medical safety/bypass, deferred/latest ETR delivery without a new
alert, exact deadlines, repeatability, and export privacy. Person 2's original
calibration suites retain their assertions and use an isolated calibration catalog
so their example FDR IDs are not confused with the integrated town's IDs. Training
test artifacts go to temporary directories. Every original teammate test remains.
