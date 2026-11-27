"""A queue whose shared environment is down waits and blames no item (SPEC §9.5, *Faults*): ``takes: {faults:
{healthy: R}}``. Unhealthy or unknown, nothing new is taken, and the hold is an event with its start and end; a run
that fails through an outage spends no attempt; one failing while healthy counts as before; a model with no
``faults:`` is unchanged; ``check`` refuses a ``healthy`` naming a part the model lacks."""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
import time

import pytest

from ergostat import model as mdl
from ergostat.leases import ENDED, TAKEN, faults
from ergostat.spec import items as its
from ergostat.spec.engine import Engine
from ergostat.spec.ir import Ref
from ergostat.store import Project

BODY = """
name: t
projections:
  ticket:
    match:
      key: ticket/*
    states: [ready, doing, done]
    events:
      ticket.done:
        state: set('done')
    otherwise: rest
stocks:
  up:
    unit: flag
    sensor: {run: "cat up", every: 0.5s, timeout: 1s}
blocks:
  worker:
    type: program
    takes: {projection: ticket, at: ready{faults}}
    lease: {attempts: 1}
    run: {run}
"""

FAULTS = ", faults: {healthy: sensor.up}"
DONE = 'echo "{\\"event\\": \\"ticket.done\\"}"'
WAIT_FAIL = 'while [ ! -f release ]; do sleep 0.05; done; exit 1'


def text(run: str = DONE, faults_: str = FAULTS) -> str:
    return BODY.replace("{faults}", faults_).replace("{run}", json.dumps(run))


def project(tmp_path, body: str) -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(body))
    m = mdl.load(tmp_path)
    assert m.spec is not None, [x.message for x in m.problems]
    return Project(m)


def wait_for(cond, seconds=20.0):
    end = time.time() + seconds
    while time.time() < end:
        got = cond()
        if got:
            return got
        time.sleep(0.05)
    return cond()


def up(tmp_path, v) -> None:
    (tmp_path / "up.tmp").write_text(f"{v}\n")
    (tmp_path / "up.tmp").replace(tmp_path / "up")


def reads(e, v: float) -> None:
    assert wait_for(lambda: e.get(Ref("stock", "up")) == v), f"the stock read {v}"


class Looks:
    """The dispatcher's looks at the block's health, counted: a wait on the next few, not on a clock."""

    def __init__(self, e):
        self.n, was = 0, e.dispatch.holds.open

        def counted(b):
            self.n += 1
            return was(b)
        e.dispatch.holds.open = counted

    def wait(self, more: int = 3) -> None:
        to = self.n + more
        assert wait_for(lambda: self.n >= to), "the dispatcher kept looking"


def start(p) -> tuple[Engine, Looks]:
    e = Engine(p, say=lambda s: None)
    looks = Looks(e)
    e.start_all()
    return e, looks


def item(p, i: str = "ticket/0"):
    return its.one(p.events, p.model.spec, i)


def events(p, t: str) -> list[dict]:
    return p.events.query(n=None, type=t)


# ---- 1. an unhealthy queue starts nothing, and starts again when it recovers


def test_an_unhealthy_queue_starts_nothing_and_starts_again_when_it_recovers(tmp_path):
    up(tmp_path, 0)
    p = project(tmp_path, text())
    for i in range(2):
        p.events.add("ticket.opened", item=f"ticket/{i}", source="t")
    e, looks = start(p)
    try:
        reads(e, 0)
        assert wait_for(lambda: events(p, faults.HELD)), "the hold was recorded"
        looks.wait(4)
        assert not events(p, TAKEN), "nothing is taken while it reads unhealthy"
        held = events(p, faults.HELD)
        assert len(held) == 1 and held[0]["item"] == "worker"
        assert held[0]["data"]["cause"] == "unhealthy" and held[0]["data"]["healthy"] == "stock.up"
        up(tmp_path, 1)
        assert wait_for(lambda: all(item(p, f"ticket/{i}").state == "done" for i in range(2))), "it took again"
        back = events(p, faults.RESUMED)
        assert len(back) == 1 and back[0]["causedby"] == held[0]["id"]
        d = back[0]["data"]
        assert d["since"] == held[0]["data"]["since"] and d["until"] >= d["since"] and d["held"] >= 0
        assert len(events(p, faults.HELD)) == 1, "said once"
    finally:
        e.close()


def test_an_unreadable_healthy_holds_the_queue_and_says_unknown(tmp_path, monkeypatch):
    monkeypatch.setattr(faults, "QUIET", 2.0)                      # (its first reading's wait, shortened)
    p = project(tmp_path, text())                                  # no file: the sensor never reads
    p.events.add("ticket.opened", item="ticket/0", source="t")
    e, looks = start(p)
    try:
        looks.wait(1)
        assert not events(p, faults.HELD) and not events(p, TAKEN), "held, unsaid, while a first reading may come"
        assert wait_for(lambda: events(p, faults.HELD)), "the hold was recorded"
        looks.wait(4)
        assert not events(p, TAKEN)
        assert events(p, faults.HELD)[0]["data"]["cause"] == "unknown"
        up(tmp_path, 1)
        assert wait_for(lambda: item(p).state == "done")
    finally:
        e.close()


class Eng:
    """What ``faults.read`` reads of an engine."""

    def __init__(self, spec, signals=None, seen=None, born=0.0, stale=None):
        self.spec, self.signals, self.seen, self.born, self.stale = spec, signals or {}, seen or {}, born, stale or {}

    def get(self, r):
        return self.signals.get(str(r))


GOAL = BODY + """
goals:
  reachable: {stock: up, hold: ">= 1"}
"""


def test_unknown_is_never_healthy(tmp_path):
    spec = project(tmp_path, GOAL.replace("{faults}", "").replace("{run}", "true")).model.spec
    s = Ref("stock", "up")
    series = spec.stocks["up"].sensors[next(iter(spec.stocks["up"].sensors))].series
    now = 1000.0
    for v in (None, float("nan"), float("inf"), True, "x"):
        assert faults.read(Eng(spec, {"stock.up": v}), s, now)[0] is None, v
    assert faults.read(Eng(spec, {"stock.up": 1.0}, {series: now - 0.5}), s, now)[0] is True
    assert faults.read(Eng(spec, {"stock.up": 0.0}, {series: now - 0.5}), s, now)[0] is False
    stale = faults.read(Eng(spec, {"stock.up": 1.0}, {series: now - 60}), s, now)
    assert stale[0] is None and "stale" in stale[1], "a stale reading is not healthy"
    g = Ref("goal", "reachable")
    assert faults.read(Eng(spec, {}), g, now)[0] is None, "a goal not worked out yet"
    assert faults.read(Eng(spec, {"goal.reachable.off": 0.0}, {series: now - 0.5}), g, now)[0] is True
    assert faults.read(Eng(spec, {"goal.reachable.off": 1.0}, {series: now - 0.5}), g, now)[0] is False
    assert faults.read(Eng(spec, {"goal.reachable.off": 0.0}, {series: now - 60}), g, now)[0] is None
    assert faults.read(Eng(spec, {"goal.reachable.off": 0.0}, {series: now - 0.5}, stale={"reachable": 9}), g, now)[0] is None

    class Broken(Eng):
        def get(self, r):
            raise RuntimeError("no")
    assert faults.read(Broken(spec), s, now)[0] is None


def test_a_hold_an_earlier_engine_left_open_is_ended_once(tmp_path):
    up(tmp_path, 1)
    p = project(tmp_path, text())
    old = p.events.add(faults.HELD, item="worker", source="ergostat",
                       data={"block": "worker", "healthy": "stock.up", "cause": "unhealthy", "why": "", "since": 5.0})
    e, looks = start(p)
    try:
        reads(e, 1)
        assert wait_for(lambda: events(p, faults.RESUMED))
        looks.wait(3)
        back = events(p, faults.RESUMED)
        assert len(back) == 1 and back[0]["causedby"] == old["id"] and back[0]["data"]["since"] == 5.0
    finally:
        e.close()


# ---- 2. a run failing during the outage spends no attempt and parks nothing


@pytest.mark.parametrize("recovers", [False, True])
def test_a_run_failing_during_the_outage_spends_no_attempt(tmp_path, recovers):
    up(tmp_path, 1)
    p = project(tmp_path, text(run=WAIT_FAIL))
    p.events.add("ticket.opened", item="ticket/0", source="t")
    e, looks = start(p)
    try:
        assert wait_for(lambda: events(p, TAKEN))
        assert not events(p, faults.HELD), "taken while healthy"
        up(tmp_path, 0)
        assert wait_for(lambda: events(p, faults.HELD)), "the outage was seen while it ran"
        assert events(p, faults.HELD)[0]["data"]["cause"] == "unhealthy"
        if recovers:                                       # down and up again during the run: it still went through it
            up(tmp_path, 1)
            assert wait_for(lambda: events(p, faults.RESUMED))
        (tmp_path / "release").write_text("")
        assert wait_for(lambda: events(p, ENDED))
        d = events(p, ENDED)[0]["data"]
        assert d["how"] == "nack" and d["count"] is False and d["fault"]
        assert ("during the run" in d["fault"]) if recovers else d["fault"].startswith("unhealthy")
        assert d["state"] == "ready" and d["terminal"] is False, "parked nothing: back in the queue"
        it = item(p)
        first = it.fields["lease"]["history"][0]
        assert first["counted"] is False and "not counted" in first["why"], "the cause is on the item"
        if not recovers:                                   # still held: not taken again
            assert it.state == "ready" and int(it.fields["lease"].get("attempts") or 0) == 0, "spent no attempt"
        else:                                              # taken again while healthy, failing again: that one counts
            assert wait_for(lambda: item(p).state == "dead")
            second = item(p).fields["lease"]["history"][1]
            assert second["counted"] is True and item(p).fields["lease"]["attempts"] == 1
    finally:
        (tmp_path / "release").write_text("")
        e.close()


def test_a_run_silent_through_the_outage_expires_uncounted(tmp_path):
    up(tmp_path, 1)
    p = project(tmp_path, text(run="sleep 60").replace("lease: {attempts: 1}", "lease: {ttl: 2s, attempts: 1}"))
    p.events.add("ticket.opened", item="ticket/0", source="t")
    e, _ = start(p)
    try:
        assert wait_for(lambda: events(p, TAKEN))
        up(tmp_path, 0)
        assert wait_for(lambda: p.events.query(n=None, type="ergostat.lease.expired"))
        d = p.events.query(n=None, type="ergostat.lease.expired")[0]["data"]
        assert d["count"] is False and d["fault"] and d["state"] == "ready", d
    finally:
        e.close()


# ---- 3. a run failing while healthy is treated as today; 4. no faults: as today


@pytest.mark.parametrize("faults_", [FAULTS, ""])
def test_a_run_failing_while_healthy_counts_as_today(tmp_path, faults_):
    up(tmp_path, 1)
    p = project(tmp_path, text(run="exit 1", faults_=faults_))
    assert (p.model.spec.blocks["worker"].takes.healthy is None) == (faults_ == "")
    p.events.add("ticket.opened", item="ticket/0", source="t")
    e, _ = start(p)
    try:
        if faults_:
            reads(e, 1)
        assert wait_for(lambda: events(p, ENDED))
        d = events(p, ENDED)[0]["data"]
        assert d["how"] == "nack" and "count" not in d and "fault" not in d
        assert d["why"] == "exited 1" or "not counted" not in d["why"]
        assert wait_for(lambda: item(p).state == "dead"), "its one attempt spent: a dead letter, as today"
        assert not p.events.query(n=None, type="ergostat.queue.*"), "no hold"
    finally:
        e.close()


def test_a_model_with_no_faults_reads_nothing_for_health(tmp_path):
    p = project(tmp_path, text(faults_=""))
    b = p.model.spec.blocks["worker"]
    h = faults.Holds(None)                                 # (no engine: one read would fail)
    assert h.open(b) is True and h.fault(b, 0) is None and h.fault(b, None) is None


# ---- 5. check refuses a healthy naming a part that does not exist


@pytest.mark.parametrize("ref, code", [
    ("sensor.nope", "unknown-ref"),
    ("sensor.quiet", "unknown-ref"),              # a stock no sensor reads
    ("stock.nope", "unknown-ref"),
    ("auxiliary.nope", "unknown-ref"),
    ("goal.nope", "unknown-ref"),
    ("block.nope", "unknown-ref"),
    ("block.worker", "unknown-ref"),              # its own command
    ("stock.up.x", "unknown-ref"),
    ("nope", "bad-ref"),
    ("sensor.up", None),
    ("stock.up", None),
    ("goal.reachable", None),
])
def test_check_refuses_a_healthy_naming_a_part_that_does_not_exist(tmp_path, ref, code):
    from ergostat import spec as sp
    body = (GOAL.replace("{faults}", f", faults: {{healthy: {ref}}}").replace("{run}", "true")
            .replace("stocks:\n", "stocks:\n  quiet: {unit: x}\n"))
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(body))
    _, problems = sp.read(tmp_path / "ergostat.yaml", extremes=False)
    codes = [x.code for x in problems if x.level == "error"]
    if code is None:
        assert not codes, [x.message for x in problems]
        return
    assert code in codes, [x.message for x in problems]
    assert any("healthy" in x.message for x in problems if x.code == code)


def test_ergostat_check_refuses_it(tmp_path):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text().replace("sensor.up", "sensor.upp")))
    r = subprocess.run([sys.executable, "-m", "ergostat", "-C", str(tmp_path), "check"], capture_output=True, text=True,
                       timeout=60)
    assert r.returncode != 0 and "healthy" in (r.stdout + r.stderr), r.stdout + r.stderr
