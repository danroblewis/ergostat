"""scripts/factory_fixture.py: a factory-size state directory (dev/records/perf-factory-size-fixture.md), through the
session's ``factory_state`` (tests/conftest.py): its sizes, read back from the model and the record; two builds of
one seed byte for byte; and the page server's answers on it."""

import json
import subprocess
import sys
import urllib.request

import pytest

from ergostat.spec import items as its
from tests.conftest import FactoryState, build_factory_state, clean_env, here

sys.path.insert(0, str(here().parent / "scripts"))
import factory_fixture as ff  # noqa: E402

pytestmark = pytest.mark.slow


def test_its_sizes_match_the_factorys_measured_shape(factory_state):
    s = factory_state.stats
    shape = {k: s[k] for k in ("files", "systems", "goals", "sensors", "machine", "kinds")}
    assert shape == {"files": 25, "systems": 8, "goals": 60, "sensors": 260, "machine": 37, "kinds": 8}, s
    p = factory_state.project()
    spec = p.model.spec
    assert sorted(set(spec.systems) - set(ff.SYSTEMS)) == ["modelling", "upkeep"], sorted(spec.systems)
    by = {k["name"]: k["counts"] for k in its.listing(p.events, spec, n=1)["kinds"]}
    mine = {k: sum(v.values()) for k, v in by.items() if k in ff.KINDS}
    assert mine == {k: n for k, (n, _, _) in ff.KINDS.items()} and sum(mine.values()) == 1500, by
    assert by["gap"].get("parked") == 40 and by["gap"].get("dead") == 10, by["gap"]
    gaps = its.fold_all(p.events, spec, "gap", None, False)
    assert len([g for g in gaps if g.fields.get("depends_on")]) >= 250, "most gaps depend on the one before"
    assert [r for g in gaps for r in g.refused] == []                    # every lease event applies, as a real run's would
    history = [h for g in gaps for h in (g.fields.get("lease") or {}).get("history", [])]
    assert sum(h["how"] == "nack" and not h["counted"] for h in history) == s["uncounted"], len(history)
    assert len(list((factory_state.record / "events").glob("seg-*.idx"))) == 30
    assert s["end"] - 86400 <= p.events.first_time() and p.events.count() == s["events"] > 30 * 32768

    taken = p.events.query(n=None, type="ergostat.lease.taken")
    ended = p.events.query(n=None, type="ergostat.lease.ended")
    uncounted = [e for e in ended if e["data"].get("count") is False]
    assert len(taken) == len(ended) == s["lease_attempts"] and 1800 <= len(taken) <= 2200, len(taken)
    assert abs(len(uncounted) / len(taken) - 0.6) < 0.02, (len(uncounted), len(taken))
    assert {e["data"]["run"] for e in uncounted} <= {e["data"]["run"] for e in taken if e["data"]["block"] == ff.GATED}
    assert spec.blocks[ff.GATED].params["actions"] == ["ship"] and spec.actions["ship"].gate == "approve"

    off = {e["item"]: e["time"] for e in p.events.query(n=None, type="loop.off")}
    back = {e["item"]: e["time"] for e in p.events.query(n=None, type="loop.holding")}
    assert sorted(off) == sorted(s["off"]) and list(back) == [ff.OFF_GOAL] and back[ff.OFF_GOAL] - off[ff.OFF_GOAL] == 1200
    oldest = next(x.name for x in p.model.sensors.values() if x.measures == spec.goals[ff.OFF_GOAL].of.name)
    read = p.measurements.range(f"sensor/{oldest}", off[ff.OFF_GOAL], back[ff.OFF_GOAL])
    assert len(read) == 20 and min(v for _, v in read) > spec.goals[ff.OFF_GOAL].hold.value
    upkept = {str(x.of) for x in spec.sensors() if (x.builtin or "").startswith("ergostat.upkeep.")}
    assert [str(spec.goals[g].of) in upkept for g in s["off"] if g != ff.OFF_GOAL] == [True]

    checked = subprocess.run([sys.executable, "-m", "ergostat", "-C", str(factory_state.model), "check"], capture_output=True,
                             text=True, timeout=900, env=clean_env(ERGOSTAT_HOME=str(factory_state.home)))
    assert checked.returncode == 0, checked.stdout[-3000:] + checked.stderr[-3000:]     # its own process: its memory let go


def test_one_seed_builds_a_byte_identical_record(factory_state, tmp_path):
    out = tmp_path / "again"
    again = FactoryState(out, build_factory_state(out, "--seed", "1", "--end", str(factory_state.stats["end"])))
    assert again.record != factory_state.record
    assert len(again.digests) > 90 and again.digests == factory_state.digests


def test_the_page_server_answers_status_and_items_from_it(factory_state):
    def get(url):
        with urllib.request.urlopen(url, timeout=600) as r:
            assert r.status == 200
            return json.loads(r.read())
    with factory_state.serve() as url:
        status, listed = get(url + "/api/status"), get(url + "/api/items")
    loops, (upkeep,) = status["loops"], [g for g in factory_state.stats["off"] if g != ff.OFF_GOAL]
    assert loops[ff.OFF_GOAL]["status"] == "holding" and loops[upkeep]["status"] == "off", (loops[ff.OFF_GOAL], loops[upkeep])
    gap = next(k for k in listed["kinds"] if k["name"] == "gap")
    assert sum(gap["counts"].values()) == 430 and gap["counts"]["parked"] == 40 and listed["items"], list(listed)
