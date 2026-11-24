"""Acceptance (group-and-yield-forecasts): from the one simulation (numbers/eta.py), a group's counts (numbers/yields.py):
how many of its open members come out by a date, the chance at least N do, the expected loss, and how many to start
to get N out at a stated confidence.

Done 1: ``test_a_known_yield_is_recovered_within_stated_bounds`` (a record of units passed or scrapped, 0.8 a
pass). Done 2: ``test_a_job_shop_with_rework_gets_correct_group_answers`` (a machine of 2, inspection sending a
quarter back and scrapping a twentieth, no special case). Done 3:
``test_a_panel_reads_the_group_counts_through_the_sql_source`` and
``test_a_model_read_as_a_remote_exposes_its_group_counts`` (two instances).

The bounds: 200 runs. A count's mean over them is within 4 standard errors of the truth (±1.0 for 50 members at
0.8, ±0.4 for 30 at 14/15), a chance within ±0.1 (3 standard errors at most), a number to start within ±2 (±1 for
the job shop, where 28 / y, blind to the spread, is 2 short)."""

from __future__ import annotations

import base64
import json
import math
import textwrap
import time
import types
from collections import OrderedDict
from urllib.parse import quote

import pytest

from ergostat import model as mdl
from ergostat.numbers import eta, etamodel, forecast, yields
from ergostat.numbers.closedloop import parse_whatif
from ergostat.numbers.etamodel import Attempt, BlockIn, Inputs, ItemAt, KindIn
from ergostat.numbers.survival import KM
from ergostat.store import Project
from ergostat.web import eta_api

YIELD = """
name: lots
items:
  unit:
    id: unit/*
    states: [made, passed, scrapped]
    on: {unit.made: made, unit.passed: passed, unit.scrapped: scrapped}
    finished: [passed, scrapped]
    lost: [scrapped]
    relations:
      lot: {kind: lot, group: true}
  lot:
    id: lot/*
    states: [open, shipped]
    on: {lot.opened: open, lot.shipped: shipped}
"""
SQL = "sources:\n  record: {type: sql}\n"
MEMBERS, BY = 50, 4000.0


def binom_tail(m: int, n: int, y: float) -> float:
    """P(Binomial(m, y) ≥ n), exactly (the test's own, not yields.py's)."""
    return sum(math.comb(m, j) * y ** j * (1 - y) ** (m - j) for j in range(n, m + 1))


def least_start(n: int, c: float, y: float) -> int:
    m = n
    while binom_tail(m, n, y) < c:
        m += 1
    return m


def lots(tmp_path, now: float, extra: str = "") -> Project:
    """200 units of record, unit j made, then after 1000 + 30·j s passed, or scrapped when j is a multiple of 5 (a
    yield of 0.8, its stays even over 1000..6970 s whatever the outcome); then lot/A's 50 units, made 10 s ago."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(YIELD) + extra)
    p = Project(mdl.load(tmp_path))
    evs = []
    for j in range(200):
        t = now - 10 * 86400 + j * 3000
        evs.append({"at": t, "type": "unit.made", "item": f"unit/h{j}", "data": {}, "source": "test"})
        evs.append({"at": t + 1000 + 30 * j, "type": "unit.scrapped" if j % 5 == 0 else "unit.passed",
                    "item": f"unit/h{j}", "data": {}, "source": "test"})
    for j in range(MEMBERS):
        evs.append({"at": now - 10, "type": "unit.made", "item": f"unit/a{j}", "data": {"lot": "lot/A"},
                    "source": "test"})
    p.events.add_many(evs)
    return p


def worked(p, now: float, monkeypatch) -> dict:
    monkeypatch.setattr(eta_api, "time", types.SimpleNamespace(time=lambda: now, monotonic=time.monotonic))
    w = parse_whatif(p.model.spec, {})[1]
    fc, _ = eta_api._work(p, p.model.spec, eta_api.kinds_of(p.model.spec), w)
    return fc


def test_a_known_yield_is_recovered_within_stated_bounds(tmp_path, monkeypatch):
    now = 1_790_000_000.0
    p = lots(tmp_path, now)
    inp = etamodel.read(p, p.model.spec, ["unit", "lot"], now)
    assert inp.kinds["unit"].lost == {"scrapped"} and dict(inp.kinds["unit"].next["made"]) == {"passed": 0.8,
                                                                                               "scrapped": 0.2}
    fc = worked(p, now, monkeypatch)
    c = fc["groups"]["lot/A"]["count"]
    assert c["members"] == MEMBERS and fc["runs"] == eta.RUNS                 # the parent is not a member
    assert abs(c["out"]["mean"] - 40) <= 1.0 and abs(c["lost"]["mean"] - 10) <= 1.0
    assert abs(c["yield"] - 0.8) <= 0.02 and abs(c["out"]["p50"] - 40) <= 1
    assert c["out"]["p10"] <= 37 and c["out"]["p90"] >= 43                   # Binomial(50, 0.8): 36 and 44
    share = 0.8 * 101 / 200                                                   # out by now + BY: passed, stay ≤ BY + 10
    a = forecast.asked(fc, yields.parse({"group": "lot/A", "by": str(now + BY), "at_least": "25"}))
    assert abs(a["out"]["mean"] - MEMBERS * share) <= 1.0, a
    assert abs(a["chance"] - binom_tail(MEMBERS, 25, share)) <= 0.1, a
    assert abs(a["lost"]["mean"] - MEMBERS * 0.2 * 101 / 200) <= 1.0, a
    s = forecast.asked(fc, yields.parse({"group": "lot/A", "at_least": "40", "confidence": "0.9"}))
    assert abs(s["start"]["n"] - least_start(40, 0.9, 0.8)) <= 2, s
    assert s["start"]["n"] == least_start(40, 0.9, s["start"]["yield"]), s   # exact, at the yield it simulated
    assert abs(s["chance"] - binom_tail(MEMBERS, 40, 0.8)) <= 0.1, s
    by = {k: (p50, p90) for k, p50, p90 in c["by"]}                           # the k-th out's date
    assert len(by) == MEMBERS and by[1][0] <= by[20][0] <= by[20][1]
    assert by[45] == (None, None)                                             # 45 out in under half the runs
    half = forecast.asked(fc, yields.parse({"group": "lot/A", "by": str(by[20][0]), "at_least": "20"}))
    assert half["chance"] >= 0.5                                              # (the curve and the asks agree)
    nothing = forecast.asked(fc, yields.parse({"group": "lot/B"}))
    assert nothing["none"] == "no such group in the forecast"
    assert "draws" not in forecast.served(fc) and "asked" not in forecast.served(fc)


def job_shop(others: int = 10, members: int = 30) -> Inputs:
    """A machine (2 at once, 600 s a run) takes jobs from ``queued``; inspection (60 s, no block) passes 70%, sends a
    quarter back to ``queued`` (rework) and scraps 5%. ``others`` older jobs wait ahead of order/7's ``members``."""
    at = 1_790_000_000.0
    k = KindIn("job", ["queued", "inspect", "done", "scrapped"], {"done", "scrapped"},
               {"inspect": [("done", 0.70), ("queued", 0.25), ("scrapped", 0.05)]}, {"inspect": [60.0] * 10},
               {s: KM([60.0] * 10) for s in ("queued", "inspect", "done", "scrapped")}, {})
    k.lost = {"scrapped"}
    atts = [Attempt(600.0, "ack", "inspect")] * 20
    b = BlockIn("machine", "job", ["queued"], 2, [], False, 99, attempts=atts, run=KM([600.0] * 20))
    items = {f"job/o{i}": ItemAt(f"job/o{i}", "job", "queued", at - 9000 + i, at - 9000 + i) for i in range(others)}
    items |= {f"job/m{i}": ItemAt(f"job/m{i}", "job", "queued", at - 1000 + i, at - 1000 + i) for i in range(members)}
    inp = Inputs(at, {"job": k}, [b], items)
    inp.groups = {"order/7": [f"job/m{i}" for i in range(members)]}
    return inp


def test_a_job_shop_with_rework_gets_correct_group_answers():
    inp = job_shop()
    sets, left = forecast.sets(inp)
    sim = eta.simulate(inp, sets=sets, counted=forecast.counted(inp))
    fc = forecast.build(inp, sim, eta.reasons(inp), 1.0, 1, [], {}, left)
    c = fc["groups"]["order/7"]["count"]
    y = 0.70 / 0.75                                       # out at last, however many times reworked: 14/15
    assert c["members"] == 30 and abs(c["yield"] - y) <= 0.015
    assert abs(c["out"]["mean"] - 30 * y) <= 0.4 and abs(c["lost"]["mean"] - 30 / 15) <= 0.4

    def asked(**q):
        return forecast.asked(fc, yields.parse({"group": "order/7", **{k: str(v) for k, v in q.items()}}))
    t0 = inp.at                                           # the 10 ahead take 5 rounds; order/7's first two at 3000 s
    early = asked(by=t0 + 3659, at_least=1)
    assert early["out"]["mean"] == 0 and early["chance"] == 0      # none can be out before 3000 + 600 + 60 s
    first = asked(by=t0 + 3661, at_least=1)                # two inspected once: Binomial(2, 0.7)
    assert abs(first["out"]["mean"] - 1.4) <= 0.15 and abs(first["chance"] - 0.91) <= 0.06, first
    assert abs(asked(by=t0 + 3661, at_least=2)["chance"] - 0.49) <= 0.1
    s = asked(at_least=28, confidence=0.9)
    assert abs(s["start"]["n"] - least_start(28, 0.9, y)) <= 1, s       # (28 / y, ignoring the spread: 30)
    assert s["start"]["n"] == least_start(28, 0.9, s["start"]["yield"]), s   # exact, at the yield it simulated
    assert asked(at_least=30)["chance"] <= binom_tail(30, 30, y) + 0.1     # all 30 out: about one run in eight
    plain = eta.simulate(inp, sets=sets)                  # the counts kept change nothing the forecast said before
    assert plain["items"] == sim["items"] and plain["sets"] == sim["sets"] and plain["counts"] == {}


def test_how_many_to_start_and_the_asks_refused():
    assert yields.start_for(10, 0.9, 1.0) == {"n": 10, "yield": 1.0}
    assert yields.start_for(40, 0.9, 0.8)["n"] == least_start(40, 0.9, 0.8)
    assert yields.start_for(5, 0.5, 0.0)["n"] is None and "no member comes out" in yields.start_for(5, 0.5, 0.0)["none"]
    big = yields.start_for(yields.MOST_N, 0.99, 0.5)
    assert big["n"] is None and "more than" in big["none"]
    assert yields.parse({}) is None
    for bad in ({"group": ""}, {"group": "g", "by": "soon"}, {"group": "g", "by": "inf"},
                {"group": "g", "at_least": "0"}, {"group": "g", "at_least": "2.5"}, {"group": "g", "at_least": 2.5},
                {"group": "g", "at_least": True}, {"group": "g", "at_least": "3", "confidence": "1"},
                {"group": "g", "confidence": "0.9"}, {"group": "g", "at_least": "1e400"}):
        with pytest.raises(ValueError):
            yields.parse(bad)
    assert yields.parse({"group": "g", "at_least": 3.0, "by": 5, "confidence": 0.5}) == {
        "group": "g", "at_least": 3, "by": 5.0, "confidence": 0.5}


def test_a_lost_state_is_declared_on_the_kind(tmp_path):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(YIELD.replace("lost: [scrapped]", "lost: [made]")))
    with pytest.raises(Exception, match="lost"):
        mdl.load(tmp_path)
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "ergostat.yaml").write_text(textwrap.dedent(YIELD.replace("    lost: [scrapped]\n", "")))
    p = Project(mdl.load(plain))
    p.events.add("unit.made", item="unit/x", data={}, at=1_790_000_000.0)
    assert etamodel.read(p, p.model.spec, ["unit"], 1_790_000_001.0).kinds["unit"].lost == set()   # off unless said


@pytest.fixture
def fresh(monkeypatch):
    for name in ("_CACHE", "_WANT", "_CAL", "_CAL_WANT"):
        monkeypatch.setattr(eta_api, name, OrderedDict())


def ask(p, text: str) -> dict:
    from ergostat.web.server import Live, api
    body = {"since": 3600.0, "until": time.time() + 3600, "points": 4, "queries": [{"id": "a", "source": "record", "text": text}]}
    q = base64.urlsafe_b64encode(json.dumps(body).encode()).decode().rstrip("=")
    [r] = api(Live(p), "query", {"q": [q]})["results"]
    return r


def test_a_panel_reads_the_group_counts_through_the_sql_source(tmp_path, fresh):
    from ergostat.web.server import BadSet, Live, api
    p = lots(tmp_path, time.time(), SQL)
    r = ask(p, "select forecast_out('lot/A', null)")                   # none yet: refused, never empty
    assert r.get("error_kind") == "unknown" and "being worked out" in r["error"], r
    fc = eta_api.estimates(p, p.model, wait=60)
    c = fc["groups"]["lot/A"]["count"]
    r = ask(p, "select parent, members, out, lost, yield from forecast_groups")
    assert r["rows"] == [["lot/A", MEMBERS, c["out"]["mean"], c["lost"]["mean"], c["yield"]]], r
    r = ask(p, "select printf('%d', n) as k, p50, p90 from forecast_group_by where parent = 'lot/A' order by n")
    assert r.get("rows") == [[str(k), p50, p90] for k, p50, p90 in c["by"]], r
    by = fc["at"] + BY
    a = forecast.asked(fc, yields.parse({"group": "lot/A", "by": by, "at_least": 25, "confidence": 0.9}))
    r = ask(p, f"select forecast_out('lot/A', {by}) as o, forecast_lost('lot/A', {by}) as l, "
               f"forecast_chance('lot/A', 25, {by}) as c, forecast_start('lot/A', 25, 0.9, {by}) as s, "
               "forecast_out('lot/B', null) as none")
    assert r["rows"] == [["1", a["out"]["mean"], a["lost"]["mean"], a["chance"], a["start"]["n"], None]], r
    assert ask(p, "select forecast_chance('lot/A', 0, null)").get("error_kind") == "refused"
    got = api(Live(p), "forecast", {"group": ["lot/A"], "by": [str(by)], "at_least": ["25"], "confidence": ["0.9"]})
    assert got["asked"] == a and "draws" not in got
    with pytest.raises(BadSet):
        api(Live(p), "forecast", {"group": ["lot/A"], "at_least": ["many"]})


def test_a_model_read_as_a_remote_exposes_its_group_counts(tmp_path, fresh):
    from ergostat.remote import items as remote_items
    from ergostat.remote import tokens
    from ergostat.web import serve as web_serve
    from tests.ports import free_port
    from tests.test_forecast_result import _get
    there = lots(tmp_path / "shop", time.time())
    a, a_url = web_serve(there, free_port())
    b = None
    try:
        tok = tokens.issue(there.dir, "reader")
        here_dir = tmp_path / "reader"
        here_dir.mkdir()
        (here_dir / "shop.token").write_text(tok)
        (here_dir / "ergostat.yaml").write_text(textwrap.dedent(f"""
            name: reader
            remotes:
              shop:
                url: {a_url}
                token-file: shop.token
                every: 60s
            stocks:
              queue:
                sensor: {{run: echo 1}}
            """))
        here = Project(mdl.load(here_dir))
        b, b_url = web_serve(here, free_port())
        fc = eta_api.estimates(there, there.model, wait=60)
        by = fc["at"] + BY
        q = f"group={quote('lot/A', safe='')}&by={by}&at_least=40&confidence=0.9"
        code, got = _get(f"{b_url}/api/forecast?remote=shop&{q}")
        assert code == 200 and got["ok"], got
        read = got["forecast"]
        assert read["groups"]["lot/A"]["count"] == fc["groups"]["lot/A"]["count"]
        want = forecast.asked(fc, yields.parse({"group": "lot/A", "by": str(by), "at_least": "40", "confidence": "0.9"}))
        assert read["asked"] == want and "draws" not in read
        assert _get(f"{a_url}/remote/v1/forecast?group=lot/A&at_least=-1", tok)[0] == 400
        with pytest.raises(remote_items.RemoteRefused):
            remote_items.forecast(here.model.spec, "shop", ask={"group": "../events"})
    finally:
        for s in (a, b):
            if s is not None:
                s.shutdown()
                s.server_close()
        remote_items._state.clear()
