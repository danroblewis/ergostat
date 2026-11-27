"""A block's pool read from a stock (SPEC §9.5, ``pool: {now: stock.NAME, most: N}``): compiled with its most, read at
each dispatch under the dispatcher's lock, clamped to its most, drained when lowered, nothing new on no reading; the
estimates and the Blocks view read the pool now, and say so when it is 0 or unread."""

from __future__ import annotations

import json
import sys
import textwrap
import time

import pytest

from ergostat import model as mdl
from ergostat.leases import ENDED, TAKEN, poolnow
from ergostat.numbers import blockmodels, eta, etamodel
from ergostat.numbers import observe as ob
from ergostat.spec import items as its
from ergostat.spec.engine import Engine
from ergostat.spec.ir import Ref
from ergostat.store import Project

KIND = """
name: t
projections:
  ticket:
    id: ticket/*
    states: [ready, doing, done]
    on: {ticket.started: doing, ticket.done: done}
stocks:
  p:
    unit: runs
    sensor: {sensor}
"""

BLOCK = """
blocks:
  worker:
    type: program
    takes: {projection: ticket, at: ready}
    pool: {pool}
    run: {run}
"""

READ = '{run: "cat level", every: 0.2s, timeout: 1s}'
WAIT = ('echo "start $ERGOSTAT_ITEM" >> runs.log; n=${ERGOSTAT_ITEM#ticket/}; '
        'while [ ! -f release-$n ] && [ ! -f release ]; do sleep 0.05; done; '
        'echo "{\\"event\\": \\"ticket.done\\"}"; echo "end $ERGOSTAT_ITEM" >> runs.log')


def text(pool: str = "{now: stock.p, most: 4}", sensor: str = READ, run: str = "true", block: str = BLOCK) -> str:
    return (KIND.replace("{sensor}", sensor)
            + block.replace("{pool}", pool).replace("{run}", json.dumps(run)))


def compiled(tmp_path, body: str):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(body))
    return mdl.load(tmp_path)


def project(tmp_path, body: str) -> Project:
    m = compiled(tmp_path, body)
    assert m.spec is not None, [x.message for x in m.problems]
    return Project(m)


def wait_for(cond, seconds=15.0):
    end = time.time() + seconds
    while time.time() < end:
        got = cond()
        if got:
            return got
        time.sleep(0.05)
    return cond()


def opened(p, n: int):
    for i in range(n):
        p.events.add("ticket.opened", item=f"ticket/{i}", source="t")


def held(p) -> int:
    return sum(1 for i in its.project(p.events, p.model.spec, "ticket", transcript=False) if i.state == "leased")


def taken(p) -> int:
    return len(p.events.query(n=None, type=TAKEN))


class Ticks:
    """The dispatcher's reads of the block's pool, counted: a wait on the next few ticks, not on a clock."""

    def __init__(self, e):
        self.n, was = 0, e.dispatch.pool_now

        def counted(b):
            self.n += 1
            return was(b)
        e.dispatch.pool_now = counted

    def wait(self, more: int = 3) -> None:
        to = self.n + more
        assert wait_for(lambda: self.n >= to), "the dispatcher kept looking"


def start(p, said: list | None = None) -> tuple[Engine, Ticks]:
    e = Engine(p, say=(said.append if said is not None else lambda s: None))
    ticks = Ticks(e)
    e.start_all()
    return e, ticks


def level(tmp_path, v) -> None:
    (tmp_path / "level.tmp").write_text(f"{v}\n")
    (tmp_path / "level.tmp").replace(tmp_path / "level")


def reads(e, v: float) -> None:
    assert wait_for(lambda: e.get(Ref("stock", "p")) == v), f"the stock read {v}"


def release_all(tmp_path, p, e) -> None:
    (tmp_path / "release").write_text("")
    try:
        wait_for(lambda: held(p) == 0, 20)
    finally:
        e.close()


# ---- the model language


def test_pool_from_a_stock_compiles_with_its_most(tmp_path):
    b = compiled(tmp_path, text()).spec.blocks["worker"]
    assert b.pool == 4 and b.pool_now == Ref("stock", "p")
    (tmp_path / "n").mkdir()
    b = compiled(tmp_path / "n", text(pool="3")).spec.blocks["worker"]
    assert b.pool == 3 and b.pool_now is None


NO_TAKES = """
blocks:
  worker:
    type: program
    pool: {pool}
    run: {run}
    every: 1m
"""


@pytest.mark.parametrize("pool, sensor, block, code", [
    ("{now: stock.p}", READ, BLOCK, "bad-number"),
    ("{now: stock.p, most: 0}", READ, BLOCK, "bad-number"),
    ("{now: stock.p, most: true}", READ, BLOCK, "bad-number"),
    ("{now: stock.p, most: 2.5}", READ, BLOCK, "bad-number"),
    ("{now: flow.x, most: 2}", READ, BLOCK, "wrong-kind"),
    ("{now: p, most: 2}", READ, BLOCK, "bad-ref"),
    ("{now: stock.nope, most: 2}", READ, BLOCK, "unknown-ref"),
    ("{now: stock.pp, most: 2}", READ, BLOCK, "unknown-ref"),
    ("{now: stock.p.x, most: 2}", READ, BLOCK, "bad-ref"),
    ("{now: stock.p, most: 2}", "{manual: true}\n  q: {unit: x}", BLOCK, None),      # (measured by hand: compiles)
    ("{now: stock.q, most: 2}", READ + "\n  q: {unit: x}", BLOCK, "pool-unmeasured"),
    ("{now: stock.p, most: 2, least: 1}", READ, BLOCK, "unknown-key"),
    ("{now: stock.p, most: 2}", READ, NO_TAKES, "pool-without-takes"),
])
def test_pool_from_a_stock_refuses_what_it_cannot_hold(tmp_path, pool, sensor, block, code):
    from ergostat import spec as sp
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text(pool=pool, sensor=sensor, block=block)))
    _, problems = sp.read(tmp_path / "ergostat.yaml", extremes=False)
    codes = [x.code for x in problems if x.level == "error"]
    if code is None:
        assert not codes, codes
        return
    assert code in codes, [x.message for x in problems]
    bad = next(x for x in problems if x.code == code)
    assert bad.where is not None, "said with where it was written"
    if "stock.pp" in pool:
        assert "(did you mean p?)" in bad.message
    if code == "pool-unmeasured":
        assert "nothing reads its level" in bad.message


def test_pool_now_clamps_and_fails_closed(tmp_path):
    b = compiled(tmp_path, text()).spec.blocks["worker"]
    for v in (None, float("nan"), float("inf"), float("-inf"), "x", -2, True, False):
        assert poolnow.now(b, v) == 0, v
    assert poolnow.now(b, 2.7) == 2 and poolnow.now(b, 9) == 4 and poolnow.now(b, 4.0) == 4 and poolnow.now(b, 1) == 1
    (tmp_path / "n").mkdir()
    n = compiled(tmp_path / "n", text(pool="3")).spec.blocks["worker"]
    assert all(poolnow.now(n, v) == 3 for v in (None, 0, 9, float("nan")))


# ---- dispatch


def test_dispatch_reads_the_pool_now_at_each_tick(tmp_path):
    level(tmp_path, 1)
    p = project(tmp_path, text(run=WAIT))
    opened(p, 6)
    e, ticks = start(p)
    try:
        reads(e, 1.0)
        assert wait_for(lambda: held(p) == 1)
        ticks.wait(5)
        assert held(p) == 1 and taken(p) == 1, "a pool of 1 now: one run at a time, not its most of 4"
        level(tmp_path, 3)                                   # no reload: the next ticks read 3
        assert wait_for(lambda: held(p) == 3)
        reads(e, 3.0)
        ticks.wait(5)
        assert held(p) == 3 and taken(p) == 3, "3 at once, never 4"
    finally:
        release_all(tmp_path, p, e)


def test_a_lowered_pool_drains_and_stops_nothing(tmp_path):
    level(tmp_path, 3)
    p = project(tmp_path, text(run=WAIT))
    opened(p, 6)
    e, ticks = start(p)
    try:
        assert wait_for(lambda: held(p) == 3)
        first = {x["item"] for x in p.events.query(n=None, type=TAKEN)}
        level(tmp_path, 1)
        reads(e, 1.0)
        ticks.wait(5)
        assert taken(p) == 3 and held(p) == 3 and not p.events.query(n=None, type=ENDED), "nothing running is stopped"
        for k, x in enumerate(sorted(first)):
            (tmp_path / f"release-{x.split('/')[1]}").write_text("")       # each ends on its own signal
            assert wait_for(lambda x=x: its.one(p.events, p.model.spec, x).state == "done")
            if k < 2:
                ticks.wait(5)
                assert taken(p) == 3, "no new lease while as many as the pool now are held"
        assert wait_for(lambda: taken(p) == 4)
        ticks.wait(5)
        assert taken(p) == 4 and held(p) == 1, "then exactly 1"
        ended = p.events.query(n=None, type=ENDED)
        assert sorted(x["item"] for x in ended) == sorted(first) and all(x["data"]["how"] == "ack" for x in ended)
        log = (tmp_path / "runs.log").read_text()
        assert all(f"end {x}" in log for x in first), "the three ran to their own end"
    finally:
        release_all(tmp_path, p, e)


def test_the_pool_now_never_passes_its_most(tmp_path):
    level(tmp_path, 50)
    run = ('echo "start $ERGOSTAT_ITEM" >> runs.log; sleep 0.4; echo "{\\"event\\": \\"ticket.done\\"}"; '
           'echo "end $ERGOSTAT_ITEM" >> runs.log')
    p = project(tmp_path, text(pool="{now: stock.p, most: 2}", run=run))
    e, _ = start(p)
    try:
        reads(e, 50.0)
        opened(p, 6)
        assert wait_for(lambda: all(its.one(p.events, p.model.spec, f"ticket/{i}").state == "done" for i in range(6)), 20)
    finally:
        e.close()
    going, most = 0, 0
    for x in (tmp_path / "runs.log").read_text().splitlines():
        going += 1 if x.startswith("start") else -1
        most = max(most, going)
    assert most == 2, "its most, never the stock's 50"


def test_an_unread_pool_takes_nothing_new(tmp_path):
    # with no level file the sensor hangs until its timeout: no reading, and dispatch goes on looking
    sensor = '{run: "test -f level && cat level || sleep 30", every: 0.2s, timeout: 1s}'
    p = project(tmp_path, text(sensor=sensor, run=WAIT))
    opened(p, 3)
    said: list[str] = []
    e, ticks = start(p, said)
    try:
        ticks.wait(8)                                    # (a hung sensor stalls no dispatch: the store is read)
        assert taken(p) == 0, "no reading: a pool of 0, nothing new taken"
        no = [s for s in said if "has no reading" in s]
        assert no == ["worker: its pool (stock.p) has no reading: it takes nothing new"], said
        level(tmp_path, 1)
        assert wait_for(lambda: taken(p) == 1)
        ticks.wait(5)
        assert taken(p) == 1, "read 1: exactly 1"
    finally:
        release_all(tmp_path, p, e)


def test_no_reading_is_not_said_before_the_first_pass(tmp_path):
    # the dispatcher may tick before the engine's first pass loads the readings: 0 then, and nothing said
    p = project(tmp_path, text(sensor="{manual: true}"))
    p.measurements.add(series_of(p), 2.0, at=time.time() - 5)
    said: list[str] = []
    e = Engine(p, say=said.append)
    b = p.model.spec.blocks["worker"]
    assert e.dispatch.pool_now(b) == 0 and not said, "not loaded yet: closed, and quiet"
    e.measure()
    assert e.dispatch.pool_now(b) == 2 and not said
    (tmp_path / "u").mkdir()
    u = project(tmp_path / "u", text(sensor="{manual: true}"))
    e = Engine(u, say=said.append)
    e.measure()
    assert e.dispatch.pool_now(u.model.spec.blocks["worker"]) == 0
    assert said == ["worker: its pool (stock.p) has no reading: it takes nothing new"], "loaded, and still unread: said"


def test_the_pool_is_read_under_the_dispatch_lock(tmp_path):
    level(tmp_path, 1)
    p = project(tmp_path, text(run=WAIT))
    opened(p, 3)
    e = Engine(p, say=lambda s: None)
    seen: list[bool] = []
    get = e.get

    def watched(r):
        if r != Ref("stock", "p") or sys._getframe(1).f_code.co_name != "pool_now":
            return get(r)                                # (the engine's own passes read it too)
        if not seen:
            seen.append(e.dispatch.lock._is_owned())
            # another engine's lease, written in that moment, on the item this one would take first
            p.events.add(TAKEN, item="ticket/0", source="ergostat",
                         data={"item": "ticket/0", "run": "other", "block": "worker", "fence": 1, "ttl": 600, "max": 3,
                               "back": "ready"})
        else:
            seen.append(e.dispatch.lock._is_owned())
        return get(r)
    e.get = watched
    ticks = Ticks(e)
    e.start_all()
    try:
        reads(e, 1.0)
        ticks.wait(5)
        assert seen and all(seen), "the pool is read with the dispatcher's lock held"
        leases = [x for x in p.events.query(n=None, type=TAKEN)]
        mine = [x for x in leases if x["data"]["run"] != "other"]
        refused = its.one(p.events, p.model.spec, "ticket/0").refused
        # (held to the pool by the record: the fold refuses this engine's second lease on ticket/0; SPEC §9.5)
        assert held(p) == 1, "the competing lease stands, and the pool of 1 is not passed"
        assert not mine or all(x["item"] == "ticket/0" for x in mine) and refused
    finally:
        (tmp_path / "release").write_text("")
        e.close()


# ---- the estimates and the Blocks view


ETA = KIND + """
flows:
  worked:
    from: p
    sensor: {projection: ticket, entering: done, over: 10m}
blocks:
  worker:
    type: program
    takes: {projection: ticket, at: ready}
    pool: {now: stock.p, most: 4}
    run: "true"
    out: flow.worked
"""


def series_of(p) -> str:
    return next(iter(p.model.spec.stocks["p"].sensors.values())).series


def test_estimates_read_the_pool_now(tmp_path):
    p = project(tmp_path, ETA.replace("{sensor}", "{manual: true}"))
    t1 = time.time() - 600
    for i in range(4):
        p.events.add("ticket.opened", item=f"ticket/{i}", source="t", at=t1 - 1800)
    spec = p.model.spec
    blk = lambda at: next(b for b in etamodel.read(p, spec, ["ticket"], at).blocks if b.name == "worker")  # noqa: E731
    unread = etamodel.read(p, spec, ["ticket"], t1 - 900)
    b = next(x for x in unread.blocks if x.name == "worker")
    assert b.pool == 1 and "has no reading" in b.pool_said
    why = eta.reasons(unread)
    assert "its pool (stock.p) has no reading: estimated at 1 run at once" in why["ticket/3"]["why"]
    assert "has no reading" not in eta.reasons(unread, {"worker": 2})["ticket/3"]["why"]
    p.measurements.add(series_of(p), 1.0, at=t1 - 300)
    p.measurements.add(series_of(p), 3.0, at=t1)
    assert blk(t1 - 100).pool == 1 and blk(t1 + 100).pool == 3
    assert blk(t1 + 100).capacity({"worker": 2}) == 2, "block.worker.pool=2 still overrides the pool now"
    p.measurements.add(series_of(p), 0.0, at=t1 + 200)
    z = etamodel.read(p, spec, ["ticket"], t1 + 300)
    assert next(x for x in z.blocks if x.name == "worker").pool == 1
    assert "its pool (stock.p) is 0 now: estimated at 1 run at once" in eta.reasons(z)["ticket/3"]["why"]


def test_read_at_picks_as_the_engine_measures(tmp_path):
    two = "    sensors:\n      a: {manual: true}\n      b: {manual: true}"
    p = project(tmp_path, ETA.replace("    sensor: {sensor}", two))
    spec, b = p.model.spec, p.model.spec.blocks["worker"]
    sa, sb = (s.series for s in spec.stocks["p"].sensors.values())
    t = time.time() - 100
    p.measurements.add(sa, 3.0, at=t)
    p.measurements.add(sb, 1.0, at=t + 10)                  # the later stamp wins, whichever sensor
    e = Engine(p, say=lambda s: None)
    e.measure()
    assert poolnow.read_at(p, spec, b, t + 20) == e.get(Ref("stock", "p")) == 1.0
    assert poolnow.read_at(p, spec, b, t + 5) == 3.0
    p.measurements.add(sb, 2.0, at=t + 30)
    p.measurements.add(sa, 4.0, at=t + 30)                  # equal stamps: the sensor first in the model, as measure
    e.measure()
    assert poolnow.read_at(p, spec, b, t + 40) == e.get(Ref("stock", "p")) == 4.0


def test_the_blocks_view_servers_are_the_pool_now(tmp_path):
    from ergostat.web.server import Live, api
    p = project(tmp_path, ETA.replace("{sensor}", "{manual: true}"))
    now = time.time()
    for i in range(121):
        p.measurements.add(series_of(p), 2.0, at=now - 7200 + i * 60)
    m = blockmodels.identify(p, p.model.spec, ob.measured(p, ob.Grid(now - 3600, now, 60)))["flow.worked"]
    assert m.form == "servers" and m.servers == 2
    got = api(Live(p), "series", {"since": ["2h"], "refs": ["stock.p"], "replay": ["1"], "loops": ["closed"]})
    assert [x["pool"] for x in got["models"] if x["block"] == "worker"] == [2]
    (tmp_path / "u").mkdir()
    u = project(tmp_path / "u", ETA.replace("{sensor}", "{manual: true}"))
    m = blockmodels.identify(u, u.model.spec, ob.measured(u, ob.Grid(now - 3600, now, 60)))["flow.worked"]
    assert m.servers == 1 and "its pool (stock.p) has no reading: estimated at 1 run at once" in m.basis


def rows_of(spec, snap: dict) -> list:
    from ergostat.blockdiagram import _Diagram
    d = _Diagram(spec, snap)
    d.build()
    return d.block_fn("worker")["rows"]


def test_the_block_box_shows_the_pool_now_and_its_most(tmp_path):
    spec = compiled(tmp_path, ETA.replace("{sensor}", "{manual: true}")).spec
    assert ["pool", "2 now, at most 4 (stock.p)"] in rows_of(spec, {"stocks": {"p": {"value": 2.0}}})
    assert ["pool", "no reading, at most 4 (stock.p)"] in rows_of(spec, {"stocks": {}})
    (tmp_path / "n").mkdir()
    n = compiled(tmp_path / "n", text(pool="3")).spec
    assert ["pool", "3"] in rows_of(n, {})
