"""REAL-PERSON2-ONLY checks; models, graph, data, and messaging remain mock-unit."""

import io
from pathlib import Path
import subprocess
import sys
import tarfile

import pytest

from .integration import PROJECT_ROOT


@pytest.fixture(scope="module")
def person2_source(tmp_path_factory):
    """Read an already-fetched teammate ref into a temp directory; never switch or merge."""
    repository = PROJECT_ROOT.parents[1]
    reference = "origin/teja/predictions"
    available = subprocess.run(["git", "rev-parse", "--verify", reference], cwd=repository,
                               capture_output=True, text=True)
    if available.returncode:
        pytest.skip("Real Person 2 check needs the already-fetched origin/teja/predictions ref; no network fetch is run by tests")
    path = "AEP_Project/storm-assistant/analytics"
    archive = subprocess.run(["git", "archive", reference, path], cwd=repository, capture_output=True, check=True)
    root = tmp_path_factory.mktemp("real-person2")
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as source:
        for member in source.getmembers():
            if member.isfile():
                target = (root / member.name).resolve()
                if not target.is_relative_to(root.resolve()):
                    raise ValueError("Unsafe path in teammate archive")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.extractfile(member).read())
    return root / "AEP_Project" / "storm-assistant"


def test_real_person2_public_contracts_and_partial_replay(person2_source):
    """Exercise unmodified Teja code with explicit synthetic Person 1/4 stand-ins."""
    code = r'''
from collections import Counter
from dataclasses import replace
from datetime import datetime
import json
from pathlib import Path
import sys
sys.path.insert(0, sys.argv[1])
sys.path.insert(1, sys.argv[2])
from analytics.predictive import outage_risk, predict_etr
from analytics.geospatial import storm_position, storm_arrival_time, in_high_wind_zone
from services.context.contracts import DAMAGE_TYPES, local_time
from tests.storm_replay.integration import load_runtime, require_signature
from tests.storm_replay.replay import run_replay
runtime = load_runtime('demo')
# Supply the same fixture feeder records to the real loader. This is test data,
# not a claim that Shaun's real sample town has been integrated.
sample = Path('data/sample')
sample.mkdir(parents=True)
(sample / 'feeders.json').write_text(json.dumps(runtime.town.feeders))
for function, names in (
    (outage_risk, ('feeder_id', 'storm')),
    (predict_etr, ('damage_type', 'crews_available', 'now')),
    (storm_position, ('storm', 't')),
    (storm_arrival_time, ('storm', 'lat', 'lon')),
    (in_high_wind_zone, ('storm', 'lat', 'lon', 't')),
):
    require_signature(function, function.__name__, names)
now = datetime(2026, 10, 24, 18)
for damage in DAMAGE_TYPES:
    etr = predict_etr(damage, 1, now)
    assert etr['etr_start'] < etr['etr_end']
    assert etr['confidence'] in ('low', 'medium', 'high')
    if damage == 'unknown':
        assert etr['confidence'] == 'low'
assert predict_etr('blown_fuse', 1, now)['etr_end'] < predict_etr('broken_pole', 1, now)['etr_end']
for feeder in runtime.town.feeders:
    assert 0 <= outage_risk(feeder['id'], runtime.storm) <= 1
arrival = storm_arrival_time(runtime.storm, 40, -83)
assert arrival is not None and local_time(arrival) == arrival
assert storm_arrival_time(runtime.storm, 10, 10) is None
assert in_high_wind_zone(runtime.storm, *storm_position(runtime.storm, now), now)
deps = replace(runtime.dependencies, outage_risk=outage_risk, predict_etr=predict_etr,
               storm_position=storm_position, storm_arrival_time=storm_arrival_time,
               in_high_wind_zone=in_high_wind_zone)
mixed = replace(runtime, dependencies=deps, mode='real-person2-only; other dependencies MOCK')
first = run_replay(mixed, crews_available=1, log=lambda line: None)
second = run_replay(mixed, crews_available=1, log=lambda line: None)
sequence = lambda result: [(e.sim_time, e.customer_id, e.alert_type, e.snapshot.etr_start, e.snapshot.confidence) for e in result.alerts]
assert sequence(first) == sequence(second)
assert first.snapshots['C-3'].status != 'outage_confirmed'
assert first.snapshots['C-1'].status == 'restored'
assert all(outcome['sent'] is False for outcome in first.outcomes)
print('REAL_PERSON2_ONLY', json.dumps(dict(Counter(e.alert_type for e in first.alerts)), sort_keys=True))
'''
    process = subprocess.run([sys.executable, "-c", code, str(person2_source), str(PROJECT_ROOT)],
                             cwd=person2_source, capture_output=True, text=True, timeout=30)
    assert process.returncode == 0, process.stderr
    assert "REAL_PERSON2_ONLY" in process.stdout
    print(process.stdout.strip())
