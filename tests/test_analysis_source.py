"""Acceptance (analysis-source-and-window-1): the ``analysis`` source's ``raw(A)``, read from the readings and never
their roll-ups, on one grid with its gap mask; the window ledger (``meta.sampling``) on every answer, its observable
band and its nulls; the warning of a request whose answers differ in step or range windows; and the refusals and bounds
of the call language. A stub Prometheus (tests/test_data_sources.py) stands in for a source."""

from __future__ import annotations

import base64
import json
import types

import pytest

from ergostat import datasources
from ergostat import model as mdl
from ergostat.query import analysis, engine, sampling
from ergostat.query import parse as parsing
from ergostat.store import Measurements, Project
from ergostat.web.server import Live, api
from tests import test_data_sources as ds

T = ds.T                                       # a multiple of 600
prom = ds.prom                                 # (a fixture)
HOUR = 3600.0


def record(tmp_path, readings, raw=None) -> Project:
    """A model whose metrics store holds ``readings`` of ``s`` and their 600 s roll-ups (``raw``: how long the
    readings are kept; rolled long after, so they are past it)."""
    (tmp_path / "ergostat.yaml").write_text("name: an\nstocks:\n  queue: {unit: tickets}\n")
    p = Project(mdl.load(tmp_path))
    (tmp_path / "m").mkdir()
    p.measurements = Measurements(tmp_path / "m", raw=raw, tiers=[(600.0, 1e9)])
    p.measurements.add_many([("s", t, v) for t, v in readings])
    p.measurements.roll(now=T + 3 * HOUR + (raw or 0) * 2)
    return p


def ask(p, *queries, since=2 * HOUR, until=T + 2 * HOUR, points=120) -> list[dict]:
    body = {"since": since, "until": until, "points": points, "queries": [{"id": i, **x} for i, x in queries]}
    q = base64.urlsafe_b64encode(json.dumps(body).encode()).decode().rstrip("=")
    return api(Live(p), "query", {"q": [q]})["results"]


A = ("A", {"source": "series", "series": "s"})
SAW = [(T + 10 * i, float(i % 7)) for i in range(720)]           # 10 s apart; each 600 s roll-up's mean is about 3


def codes(r: dict) -> list[str]:
    return [x["code"] for x in r["meta"]["verdict"]["reasons"]]


def test_raw_reads_readings_not_rollups(tmp_path):
    p = record(tmp_path, SAW)
    with p.measurements._c() as c:                    # roll-ups unlike the readings: reading them cannot pass for raw
        c.execute("update tiers set sum = n * 100.0, min = 100, max = 100, first_v = 100, last_v = 100")
    a, r = ask(p, A, ("R", {"source": "analysis", "text": "raw(A)"}), points=12)
    assert a["step"] == 600 and set(a["series"][0]["values"]) == {100}                # A at 600 s: the roll-ups
    assert "error" not in r and r["shape"] == "series" and r["step"] == 10, r
    assert r["times"] == [t for t, _ in SAW] and r["series"][0]["values"] == [v for _, v in SAW]
    assert r["meta"]["sampling"]["scrape_s"] == 10 and r["meta"]["source"] == "analysis" and r["gaps"] == []
    assert r["meta"]["sampling"]["observable_period_s"] == [20, HOUR]
    assert a["meta"]["sampling"]["scrape_s"] == 10                                 # the plain query's scrape, read too


def test_raw_masks_a_gap(tmp_path):
    hole = [(t, v) for t, v in SAW if not T + 1200 < t < T + 1500 and t != T + 2500]   # 5 minutes, and one reading
    p = record(tmp_path, hole)
    [r] = ask(p, A, ("R", {"source": "analysis", "text": "raw(A)"}))[1:]
    assert r["gaps"] == [[T + 1200, T + 1500]], r["gaps"]                           # the single miss is no gap
    v = r["series"][0]["values"]
    assert all(x is None for x in v[121:150]) and v[120] is not None and v[150] is not None
    assert v[250] == (v[249] + v[251]) / 2                                          # a short hole is a straight line


def test_raw_never_draws_over_a_listed_gap(tmp_path):
    """Readings 1 s into their 10 s buckets: a hole just over GAP_SAMPLES spacings (31 s) is three buckets wide, as a
    hole of exactly 30 s is. The first is listed and stays empty; the second is not listed and is a straight line."""
    near = {i: T + 1 + 10 * i for i in range(720) if i not in (101, 102, 201, 202)}
    near[103], near[203] = T + 1001 + 31, T + 2001 + 30
    p = record(tmp_path, [(t, float(i % 7)) for i, t in sorted(near.items())])
    [r] = ask(p, A, ("R", {"source": "analysis", "text": "raw(A)"}))[1:]
    assert r["step"] == 10 and r["gaps"] == [[T + 1001, T + 1032]], r["gaps"]
    v = r["series"][0]["values"]
    assert v[101] is None and v[102] is None and v[100] is not None and v[103] is not None   # listed: never filled
    assert v[201] is not None and v[202] is not None                                      # not listed: a line


def test_raw_refuses_when_only_rollups_remain(tmp_path):
    p = record(tmp_path, SAW, raw=60.0)
    assert p.measurements.count("s", T, T + 2 * HOUR) == len(SAW)                   # (in the roll-ups, n of each)
    a, r = ask(p, A, ("R", {"source": "analysis", "text": "raw(A)"}))
    assert "error" not in a and a["series"][0]["values"][0] is not None              # A still answers, from roll-ups
    assert "series" not in r and "only roll-ups" in r["error"] and codes(r) == ["only-rollups"]
    assert r["meta"]["verdict"]["level"] == "refuse"
    assert codes(a) == ["scrape-unknown"] and a["meta"]["sampling"]["scrape_s"] is None    # never read as fine
    (tmp_path / "half").mkdir()
    p = record(tmp_path / "half", SAW)
    p.measurements.raw = HOUR                         # the first hour's readings forgotten, its roll-ups kept
    p.measurements.roll(now=T + 2 * HOUR + 60)
    [r] = ask(p, A, ("R", {"source": "analysis", "text": "raw(A)"}))[1:]
    assert set(r["series"][0]["values"][:360]) == {None} and r["series"][0]["values"][360:] == [v for _, v in SAW[360:]]
    assert f"from {T:.0f} to {T + HOUR:.0f} only roll-ups are kept" in str(r["meta"]["verdict"])
    with pytest.raises(datasources.SourceError, match="no raw readings"):        # a store that cannot tell them apart
        analysis.raw(object(), parsing.Query("A", "series", "avg", series="s"), T, T + HOUR, analysis.call("raw(A)"))


def test_ledger_records_promql_range_windows(tmp_path, prom):
    p = ds.project(tmp_path, f'prom: {{type: prometheus, url: "{prom}"}}')
    ds.Stub.seen.clear()
    q, c, r = ask(p, ("P", {"source": "prom", "text": "rate(x[5m]) + avg_over_time(y[1h:1m])"}), ("C", {"source": "counts"}),
                  ("R", {"source": "analysis", "text": "raw(P)"}))
    s = q["meta"]["sampling"]
    assert s["range_windows_s"] == [300, HOUR] and s["step_s"] == 60 and s["scrape_s"] is None
    assert c["meta"]["sampling"]["step_s"] == 60 and c["meta"]["sampling"]["range_windows_s"] == []   # a plain query
    assert c["meta"]["sampling"]["observable_period_s"] == [120, HOUR]
    assert [a["step"] for _, _, a in ds.Stub.seen] == ["60", "8"]                   # asked again at the finest step
    assert r["step"] == 8 and "not-raw" in codes(r) and "not its raw readings" in str(r["meta"]["verdict"])
    assert r["meta"]["sampling"]["range_windows_s"] == [300, HOUR]
    assert sampling.windows('x{a="[9m]"}[2h] # [7d]\n + y[90s:] + z[1h30m:5m]') == [90, 5400, 7200]
    v, = ask(p, ("V", {"source": "prom", "text": "rate(x[$w])", "vars": {"w": ["10m"]}}))
    assert v["meta"]["sampling"]["range_windows_s"] == [600]                       # a window given by a variable


def test_observable_band_and_nulls():
    got, said = sampling.ledger({"step": 60, "scrape_s": 90, "range_windows_s": [HOUR]}, None, 86400)
    assert got["observable_period_s"] == [180, 43200] and said == []                # 2 × the scrape, the larger
    assert got["nulls_s"] == [HOUR / k for k in range(1, 21)]                       # each W/k down to 180 s
    got, _ = sampling.ledger({"step": 60, "scrape_s": 15, "range_windows_s": [86400]}, None, 2 * HOUR)
    assert got["observable_period_s"] == [120, HOUR]                                 # a day's W/24 to W/720 are in it:
    assert got["nulls_s"] == [86400 / k for k in range(24, 74)]                     # the longest 50 are listed
    got, said = sampling.ledger({"step": 60, "scrape_s": None, "range_windows_s": [HOUR]}, None, 86400)
    assert got["observable_period_s"] == [120, 43200] and [c for c, _ in said] == ["scrape-unknown"]
    got, said = sampling.ledger({"step": 60}, types.SimpleNamespace(transform="moving_avg", window=5), HOUR)
    assert got["range_windows_s"] == [300] and got["nulls_s"] == [300, 150] and said == []    # an average's span; not sampled
    got, _ = sampling.ledger({"step": 10, "scrape_s": 10, "range_windows_s": [HOUR, 86400]}, None, 86400)
    every = {HOUR / k for k in range(1, 181)} | {86400 / k for k in range(2, 4321)}     # both windows' W/k in [20, 43200]
    assert got["nulls_s"] == sorted(every, reverse=True)[:50] and got["nulls_s"][:2] == [43200, 28800]


def test_shaped_answers_carry_their_scrape(tmp_path, monkeypatch):
    sig = {"source": "series", "series": "s"}
    shaped = [("O", {**sig, "agg": "ohlc"}), ("F", {"source": "frequency", "input": sig, "output": sig})]
    for r in ask(record(tmp_path, SAW), *shaped):
        assert "error" not in r and r["meta"]["sampling"]["scrape_s"] == 10 and "scrape-unknown" not in codes(r), r
    (tmp_path / "gone").mkdir()                       # readings pruned: unknown, and warned (a frequency is then
    [r] = ask(record(tmp_path / "gone", SAW, raw=60.0), shaped[0])                # refused: 12 roll-ups are too few)
    assert "error" not in r and r["meta"]["sampling"]["scrape_s"] is None and "scrape-unknown" in codes(r), r
    (tmp_path / "late").mkdir()                       # 10 s apart, then the newest 40 readings 30 s apart
    p = record(tmp_path / "late", [*SAW[:600], *((SAW[599][0] + 30 * i, 1.0) for i in range(1, 41))])
    monkeypatch.setattr(analysis, "SCRAPE_READINGS", 30)
    a, r = ask(p, A, ("R", {"source": "analysis", "text": "raw(A)"}))
    assert a["meta"]["sampling"]["scrape_s"] == 30 and r["meta"]["sampling"]["scrape_s"] == 10   # the newest 30 only


def test_mixed_windows_warn(tmp_path, prom):
    p = ds.project(tmp_path, f'prom: {{type: prometheus, url: "{prom}"}}')
    a, b = ask(p, ("a", {"source": "counts", "bucket": 120}), ("b", {"source": "prom", "text": "rate(x[5m])"}))
    for r in (a, b):
        [said] = [x["says"] for x in r["meta"]["verdict"]["reasons"] if x["code"] == "mixed-windows"]
        assert "steps 60 s, 120 s" in said and "range windows 300 s" in said, said
    one, two = ask(p, ("a", {"source": "counts"}), ("b", {"source": "events"}))
    assert codes(one) == codes(two) == []                                             # alike: nothing said


def test_bad_calls_refuse_alone(tmp_path):
    p = record(tmp_path, SAW)
    texts = {"call": "spectrum(A)", "id": "raw(Z)", "self": "raw(self)", "deep": "raw(call)", "syntax": "raw(A",
             "option": "raw(A, bins=3)", "after": "raw(points=20, A)", "two": "raw(A, A)"}
    got = dict(zip(["A", "C", *texts], ask(p, A, ("C", {"source": "counts"}),
                                           *((k, {"source": "analysis", "text": t}) for k, t in texts.items())), strict=True))
    assert "error" not in got["A"] and "error" not in got["C"]                       # the siblings still answer
    for k in texts:
        assert "series" not in got[k] and got[k]["meta"]["verdict"]["level"] == "refuse", k
    assert "'spectrum' is not a call; the calls are raw" in got["call"]["error"]
    assert "no query 'Z' in this request" in got["id"]["error"] and "reads itself" in got["self"]["error"]
    assert "'call' is itself an analysis" in got["deep"]["error"]
    assert got["syntax"]["error_at"] == [1, 6] and "column 6: , or ) was expected, not the end" in got["syntax"]["error"]
    assert got["option"]["error_at"] == [1, 8] and "'bins' is not an option of raw" in got["option"]["error"]
    assert "comes after an option" in got["after"]["error"] and "given 2" in got["two"]["error"]
    [bad, r] = ask(p, ("B", {"source": "series", "series": "nothing"}), ("R", {"source": "analysis", "text": "raw(B)"}))
    assert "error" in bad and "'B' was not answered" in r["error"]                   # a failure is never read as empty


def test_bounds_hold(tmp_path, monkeypatch):
    p = record(tmp_path, [(T + i, float(i % 5)) for i in range(7200)])               # a reading a second
    [r] = ask(p, A, ("R", {"source": "analysis", "text": "raw(A, points=100)"}))[1:]
    assert len(r["times"]) <= 100 and r["step"] > 1 and "averaged into steps" in str(r["meta"]["verdict"]), r["step"]
    monkeypatch.setattr(analysis, "RAW_POINTS", 50)
    [r] = ask(p, A, ("R", {"source": "analysis", "text": "raw(A)"}))[1:]
    assert len(r["times"]) <= 50 and r["meta"]["sampling"]["scrape_s"] == 1
    [r] = ask(p, A, ("R", {"source": "analysis", "text": "raw(A, points=51)"}))[1:]
    assert "points is a whole number from 16 to 50" in r["error"]
    monkeypatch.setattr(analysis, "READINGS_MOST", 100)
    [r] = ask(p, A, ("R", {"source": "analysis", "text": "raw(A)"}))[1:]
    assert r["error_kind"] == "limit" and "more than the 100 one raw answer reads" in r["error"]
    monkeypatch.undo()
    many = ask(p, A, *((f"R{i}", {"source": "analysis", "text": "raw(A, points=16)"}) for i in range(parsing.MOST_ANALYSIS + 1)))
    assert all("error" not in r for r in many[:-1]) and "past the 8 analysis queries" in many[-1]["error"]
    real = engine.parse

    def lenient(d):                                   # parse lets more through: the run holds the bound again
        monkeypatch.setattr(parsing, "MOST_ANALYSIS", 99)
        got = real(d)
        monkeypatch.setattr(parsing, "MOST_ANALYSIS", 2)
        return got
    monkeypatch.setattr(engine, "parse", lenient)
    got = ask(p, A, *((f"R{i}", {"source": "analysis", "text": "raw(A, points=16)"}) for i in range(3)))
    assert "error" not in got[2] and "past the 2 analysis queries" in got[3]["error"]


def test_analysis_is_offered_and_reserved(tmp_path, prom):
    p = record(tmp_path, SAW)
    assert api(Live(p), "query/fields", {})["datasources"] == [datasources.ANALYSIS, ds.OWN]   # (and the model's own)
    assert datasources.ANALYSIS["name"] == parsing.ANALYSIS
    (tmp_path / "q").mkdir()
    q = ds.project(tmp_path / "q", f'analysis: {{type: prometheus, url: "{prom}"}}')     # declared: never listed, never asked
    assert api(Live(q), "query/fields", {})["datasources"] == [datasources.ANALYSIS, ds.OWN]
    ds.Stub.seen.clear()
    [r] = ask(q, ("R", {"source": "analysis", "text": "up"}))
    assert ds.Stub.seen == [] and "'up' is not a call" in r["error"] and r["error_at"] == [1, 1]
