"""The measure sensors stop starving the load sensors (dev/records/measure-sensors-share-one-listing.md): a 15-second
sensor reads on a lane of its own however many slow readings are under way (engine.lane), and the measure sensors of
one kind share one recent listing of it (dev/bin/listing.py)."""

from __future__ import annotations

import importlib.util
import json
import os
import queue
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat.spec.ir import Ref, Sensor
from ergostat.store import Project

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "dev" / "bin"
SLOW = 12                                     # more slow readings than the sensor pool's READERS (8)


def load(name: str):
    sys.path.insert(0, str(BIN))
    try:
        spec = importlib.util.spec_from_file_location(f"factory_{name}", BIN / f"{name}.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        sys.path.remove(str(BIN))


listing = load("listing")


# ---- 1. a slow sensor cannot delay a fast one

class Seen(queue.Queue):
    """The engine's results queue, which also says when the fast sensor's reading is posted."""
    def __init__(self, series: str):
        super().__init__()
        self.series, self.got, self.back = series, threading.Event(), None

    def put(self, item, *a, **k):
        if item[0].series == self.series:
            self.back = item
            self.got.set()
        super().put(item, *a, **k)


def test_many_slow_sensors_do_not_make_a_15_second_sensor_stale(tmp_path):
    from ergostat.spec.engine import Engine
    gate = tmp_path / "gate"                  # the slow readings run until it is gone: none ends on its own
    gate.write_text("")
    wait = f'while [ -e {gate} ]; do sleep 0.05; done; echo 1'
    stocks = "".join(f"  slow{i}: {{unit: x, sensor: {{run: {json.dumps(wait)}, every: 1h, timeout: 10m}}}}\n"
                     for i in range(SLOW))
    d = tmp_path / "lanes"
    d.mkdir()
    (d / "ergostat.yaml").write_text(textwrap.dedent("""
        name: lanes
        stocks:
          load: {unit: x, sensor: {run: echo 3, every: 15s, timeout: 20s}}
        """) + stocks)
    p = Project(mdl.load(d))
    e = Engine(p, say=lambda s: None)
    try:
        sensors = p.model.spec.sensors()
        fast = next(s for s in sensors if s.of.name == "load")
        slow = [s for s in sensors if s is not fast]
        e.results = Seen(fast.series)
        e._begin(slow, False, False, False, set())               # the slow ones first: every reader taken
        handed = time.time()
        e._begin([fast], False, False, False, set())
        assert e.results.got.wait(20), "the 15 s sensor waited behind the slow readings"
        s, v, why, at, err = e.results.back
        assert err is None and v == 3.0 and at - handed < 15     # read within its interval: not stale
        with e.pool_lock:                                         # while every slow reading is still under way
            assert len(e.pool_out) == SLOW and all(x.series in e.pool_out for x in slow)
    finally:
        gate.unlink()
        e.close()


def test_a_sensor_reads_on_the_fast_lane_only_when_read_and_stopped_within_FAST():
    from ergostat.spec.engine import FAST, LANES, lane
    one = lambda **k: Sensor(name="s", of=Ref("stock", "x"), run="true", **k)   # noqa: E731
    assert lane(one(every=15.0, timeout=20.0)) == "fast_"
    assert lane(one(every=FAST, timeout=FAST)) == "fast_"
    assert lane(one(every=15.0, timeout=FAST + 1)) == ""                  # a reading that may run long: the slow lane
    assert lane(one(every=1800.0, timeout=60.0)) == ""
    assert lane(one(every=None, cron="*/1 * * * *")) == ""
    assert lane(one(every=float("nan"), timeout=20.0)) == ""
    assert lane(one(every=0.0, timeout=20.0)) == ""
    assert sum(LANES.values()) <= 14                                       # fixed: the model sets no pool's size


def test_the_fast_lane_wedged_is_mended_like_the_sensor_pool(tmp_path):
    from types import SimpleNamespace

    from ergostat.spec import watchdog as wd
    now = time.monotonic()
    old = SimpleNamespace(shutdown=lambda **k: None)
    e = SimpleNamespace(p=SimpleNamespace(dir=tmp_path, events=SimpleNamespace(add=lambda *a, **k: None)),
                        passed_at=now, pool_lock=threading.Lock(), lock=threading.Lock(), reading={"sensor/x"},
                        pool=None, pool_out={}, pool_done_at=now, fast_pool=old, fast_pool_out={},
                        fast_pool_done_at=0.0, say=lambda s: None, wedged=None, restart_hard=None,
                        wake=threading.Event())
    e.fast_pool_out["sensor/x"] = (now - 100, 5.0, now - 100)
    wd.Watchdog(e).look(now)
    assert e.fast_pool is None and not e.fast_pool_out and "sensor/x" not in e.reading


# ---- 2. one listing of a kind, shared

FAKE = r'''
import json, sys, time
from pathlib import Path
here = Path(__file__).parent
args = sys.argv[1:]
with open(here / "calls.log", "a") as f:
    f.write(" ".join(args) + "\n")
if args[0] == "item" and "--kind" in args:
    time.sleep(0.5)                           # a slow listing: the others arrive while it runs
    if (here / "fail").exists():
        sys.exit("the record cannot be read")
    kind = args[args.index("--kind") + 1]
    got = [i for i in json.loads((here / "record.json").read_text()) if i["kind"] == kind]
    print(json.dumps({"items": got, "total": len(got)}))
else:
    sys.exit(f"the fake ergostat does not know {args}")
'''


def gap(n: int, merged_h: float, ready_h: float) -> dict:
    now = time.time()
    return {"id": f"gap/g{n}", "kind": "gap", "state": "merged",
            "fields": {"merged_at": now - merged_h * 3600, "ready_at": now - ready_h * 3600}}


def test_concurrent_measure_readings_of_one_kind_make_one_listing(tmp_path):
    (tmp_path / "fake.py").write_text(FAKE)
    (tmp_path / "record.json").write_text(json.dumps([gap(1, 1, 3), gap(2, 2, 6)]))
    state = tmp_path / "state"
    env = {**{k: v for k, v in os.environ.items() if not k.startswith("ERGOSTAT_")},
           "ERGOSTAT_CMD": f"{sys.executable} {tmp_path / 'fake.py'}", "ERGOSTAT_STATE_DIR": str(state)}
    names = ["cycle-hours", "fix-rounds", "cost-per-merged", "merges-per-hour", "cycle-hours", "queue-minutes"]
    runs = [subprocess.Popen([sys.executable, str(BIN / "measure.py"), n], cwd=tmp_path, env=env, text=True,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE) for n in names]
    out = [r.communicate(timeout=60) for r in runs]
    assert all(r.returncode == 0 for r in runs), [o[1] for o in out]
    assert out[0][0].strip() == out[4][0].strip() == "3.0"                # (2h and 4h from ready to merged)
    calls = (tmp_path / "calls.log").read_text().splitlines()
    assert calls == ["item --kind gap --json -n 5000"]                     # six readings at once, one listing


def test_without_the_engines_state_folder_nothing_is_shared(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(listing.fac, "items", lambda kind: calls.append(kind) or [])
    monkeypatch.delenv("ERGOSTAT_STATE_DIR", raising=False)
    listing.items("gap")
    listing.items("gap")
    assert calls == ["gap", "gap"] and not (tmp_path / "listings").exists()


# ---- 3. never older than the window; a failed listing not kept

class Lister:
    """fac.items, counted: each call's kind, and the failure it raises while ``fail`` is set."""
    def __init__(self):
        self.calls: list[str] = []
        self.fail: Exception | None = None

    def __call__(self, kind):
        self.calls.append(kind)
        if self.fail is not None:
            raise self.fail
        return [{"id": f"{kind}/{len(self.calls)}"}]

    def __len__(self):
        return len(self.calls)


@pytest.fixture
def counted(monkeypatch):
    lister = Lister()
    monkeypatch.setattr(listing.fac, "items", lister)
    return lister


def test_a_listing_is_shared_within_the_window_and_listed_again_past_it(tmp_path, counted):
    assert listing.items("gap", tmp_path) == [{"id": "gap/1"}]
    assert listing.items("gap", tmp_path) == [{"id": "gap/1"}]            # within the window: the same listing
    assert listing.items("review", tmp_path) == [{"id": "review/2"}]       # another kind: its own
    kept = tmp_path / "listings" / "gap.json"
    got = json.loads(kept.read_text())
    for begun in (time.time() - listing.SHARE - 1, time.time() + 60, "soon", float("nan")):   # too old, future, junk
        kept.write_text(json.dumps({**got, "begun": begun}))
        n = len(counted)
        listing.items("gap", tmp_path)
        assert len(counted) == n + 1, begun
    assert listing.fresh(kept, listing.SHARE, now=json.loads(kept.read_text())["begun"] + listing.SHARE + 0.01) is None


def test_the_age_counts_from_when_the_listing_began_not_when_it_ended(tmp_path, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(listing.time, "time", lambda: clock[0])

    def slow(kind):
        clock[0] += 50.0                      # the listing itself took 50 s
        return []
    monkeypatch.setattr(listing.fac, "items", slow)
    listing.items("gap", tmp_path, window=60)
    assert json.loads((tmp_path / "listings" / "gap.json").read_text())["begun"] == 1000.0
    clock[0] = 1061.0                         # 11 s after it ended, 61 s after it began: past a 60 s window
    assert listing.fresh(tmp_path / "listings" / "gap.json", 60) is None


def test_a_failed_listing_is_not_kept(tmp_path, counted):
    counted.fail = RuntimeError("ergostat item: exit 1")
    with pytest.raises(RuntimeError):
        listing.items("gap", tmp_path)
    assert not (tmp_path / "listings" / "gap.json").exists()
    counted.fail = None
    assert listing.items("gap", tmp_path) == [{"id": "gap/2"}]            # listed again, not a cached failure
    kept = tmp_path / "listings" / "gap.json"
    kept.write_text(json.dumps({**json.loads(kept.read_text()), "begun": time.time() - listing.SHARE - 1}))
    counted.fail = RuntimeError("ergostat item: exit 1")                  # stale, and the next listing fails
    with pytest.raises(RuntimeError):
        listing.items("gap", tmp_path)
    assert listing.fresh(kept, listing.SHARE) is None                     # the stale one is never served instead


def test_a_failed_measure_listing_is_listed_again_by_the_next_reading(tmp_path):
    (tmp_path / "fake.py").write_text(FAKE)
    (tmp_path / "record.json").write_text(json.dumps([gap(1, 1, 3)]))
    (tmp_path / "fail").write_text("")
    env = {**{k: v for k, v in os.environ.items() if not k.startswith("ERGOSTAT_")},
           "ERGOSTAT_CMD": f"{sys.executable} {tmp_path / 'fake.py'}", "ERGOSTAT_STATE_DIR": str(tmp_path / "state")}
    run = lambda: subprocess.run([sys.executable, str(BIN / "measure.py"), "cycle-hours"], cwd=tmp_path, env=env,  # noqa: E731
                                 capture_output=True, text=True, timeout=60)
    assert run().returncode != 0                                          # no value, never 0 from a cached failure
    (tmp_path / "fail").unlink()
    r = run()
    assert r.returncode == 0 and r.stdout.strip() == "2.0"
    assert len((tmp_path / "calls.log").read_text().splitlines()) == 2
