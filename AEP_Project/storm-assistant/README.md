# Storm Assistant

The integrated HackOHI/O storm simulation uses the four teammates' real synthetic
data/network, analytics, customer services, and messaging implementations.
The default replay is offline and dry-run. It never needs Twilio credentials.

## Run

From this directory, use a Python 3.11+ virtual environment. Integration was
validated with Python 3.13.17, NetworkX 3.7, and pytest 9.1.1.

```sh
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python3 -m tests.storm_replay.replay
python3 -m tests.storm_replay.replay --integrated --crews-available 1
python3 -m pytest -q -rs
```

On the integration lead's current machine, `/tmp/storm-full-system-env` is an
already-validated isolated environment. `source /tmp/storm-full-system-env/bin/activate`
can replace the environment creation/install steps. The installed system Python
3.14.1 with NetworkX 3.6 raised a dataclass error during import; the isolated
environment avoids changing application code to work around that combination.

The CLI's configured default of one simulated crew is an explicit demo assumption,
not a live crew inventory. `--crews-available` changes that assumption. Domain
time is Ohio local ISO time. The loader normalizes the source JSON's explicit
offsets in memory; canonical models keep their original string timestamp fields.

## Presentation and audit

```sh
python3 -m tests.storm_replay.replay --speed fast
python3 -m tests.storm_replay.replay --step
python3 -m tests.storm_replay.replay --verbose --audit-json /tmp/storm-integrated-audit.json
python3 -m tests.storm_replay.replay --demo --speed fast
```

`--demo` deliberately selects the old labeled Person 3 fixture adapters. The
default and `--integrated` use real implementations. Audit export refuses to
overwrite existing files and omits names, phones, medical flags, and message text.
SMS bodies remain available to the internal handler/guardrail tests; the provider
prints only a redacted dry-run receipt. Display speed and stepping do not change
simulated timestamps. Noninteractive step mode completes without prompting.

The supplied real scenario emits 11 source alerts and processes 12 handler calls:
10 accepted dry-run messages, one consent block, and one initial throttle result.
The throttled crew update drains at its exact 30-minute eligibility deadline.
Both affected customers restore; both other customers retain power.

See [`INTEGRATION_REPORT.md`](INTEGRATION_REPORT.md) for the full compatibility
matrix, merge history, test evidence, limitations, and review instructions.
Live SMS was not enabled or tested against a real provider. Any later phone demo
requires separate authorization, verified team recipients, consent, and review
of the fixed safety copy.
