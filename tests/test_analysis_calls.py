"""Acceptance (analysis-source-and-window-2): the analysis calls ``pair``, ``psd``, ``spectrogram`` and ``ccf``, each
reading its signals only through the source's raw re-read on one grid; their shapes, bands, guards (G1, G2, G4),
refusals of a record they cannot analyse, and the ceilings on every count they take."""

from __future__ import annotations

import math
import random

import pytest

from ergostat import datasources
from ergostat import model as mdl
from ergostat.query import spectra
from ergostat.query.frequency import Refused
from ergostat.store import Measurements, Project
from tests import test_data_sources as ds
from tests.test_analysis_source import HOUR, T, ask, codes

prom = ds.prom                                 # (a fixture)


def store(tmp_path, **series) -> Project:
    """A model whose metrics store holds each named series' readings ``[(t, v)]``."""
    (tmp_path / "ergostat.yaml").write_text("name: calls\nstocks:\n  queue: {unit: tickets}\n")
    p = Project(mdl.load(tmp_path))
    (tmp_path / "m").mkdir()
    p.measurements = Measurements(tmp_path / "m", tiers=[(600.0, 1e9)])
    p.measurements.add_many([(n, t, v) for n, rs in series.items() for t, v in rs])
    return p


def sine(period=300.0, every=10.0, n=720, noise=0.3, seed=1, after=0.0):
    rng = random.Random(seed)
    return [(T + every * i, (math.sin(2 * math.pi * every * i / period) if every * i >= after else 0.0)
             + rng.gauss(0, noise)) for i in range(n)]


def series(name):
    return {"source": "series", "series": name}


def call(text):
    return {"source": "analysis", "text": text}


def peak(r):
    s = r["series"][0]
    return max(range(len(s["values"])), key=s["values"].__getitem__)


def test_psd_finds_a_planted_period(tmp_path):
    p = store(tmp_path, s=sine())
    _, r = ask(p, ("A", series("s")), ("P", call("psd(A, segments=4)")))
    assert "error" not in r and r["shape"] == "points" and r["order"] == "x", r
    s, i = r["series"][0], peak(r)
    assert s["xs"] == sorted(s["xs"]) and r["x"]["label"] == "period" and r["x"]["unit"] == "s"
    bin_hz = 1 / (r["segment_samples"] * r["sample_seconds"])
    assert abs(1 / s["xs"][i] - 1 / 300) <= bin_hz, s["xs"][i]                  # within one frequency bin
    assert s["lower"][i] < s["values"][i] < s["upper"][i] and r["segments"] >= 4
    assert s["values"][i] > 10 * sorted(s["values"])[len(s["values"]) // 2]      # a peak, not the noise floor
    assert r["meta"]["source"] == "analysis" and r["meta"]["sampling"]["scrape_s"] == 10
    rng = random.Random(5)                            # the band: white noise's true density, 2σ²dt, inside about 95%
    got = spectra.psd("N", [rng.gauss(0, 1) for _ in range(2048)], 1.0, None, segments=8)["series"][0]
    inside = sum(lo <= 2.0 <= hi for lo, hi in zip(got["lower"], got["upper"], strict=True)) / len(got["lower"])
    assert 0.88 <= inside <= 0.995, inside
    for how in ("mean", "none"):
        [r] = ask(p, ("A", series("s")), ("P", call(f"psd(A, detrend={how})")))[1:]
        assert abs(1 / r["series"][0]["xs"][peak(r)] - 1 / 300) <= bin_hz, how


def test_psd_refuses_a_windowed_signal_without_raw(tmp_path, prom, monkeypatch):
    p = ds.project(tmp_path, f'prom: {{type: prometheus, url: "{prom}"}}')
    real = datasources.query

    def one(spec, source, text, g, *a, **k):          # the source answers one signal, a 300 s sine, at every step
        real(spec, source, text, g, *a, **k)
        return {"times": g.times, "step": g.step, "unit": "", "capped": 0, "read_log": False,
                "series": [{"name": "x", "values": [math.sin(2 * math.pi * t / 300) for t in g.times]}]}
    monkeypatch.setattr(datasources, "query", one)
    a, r, s, b, f = ask(p, ("A", {"source": "prom", "text": "rate(x[5m])"}), ("P", call("psd(A)")),
                        ("S", call("spectrogram(A)")), ("B", {"source": "prom", "text": "x"}), ("F", call("psd(B)")))
    assert "error" not in a and a["meta"]["sampling"]["range_windows_s"] == [300]   # A itself still answers
    for x in (r, s):
        assert "series" not in x and "rows" not in x and codes(x) == ["windowed"], x   # never the windowed values
        assert "(G1)" in x["error"] and "300 s" in x["error"] and x["meta"]["verdict"]["level"] == "refuse"
    assert "error" not in f and {"not-raw", "scrape-unknown"} <= set(codes(f)), f   # no window: answered, warned
    (tmp_path / "gone").mkdir()                       # a series whose raw readings are pruned: refused, not roll-ups
    q = store(tmp_path / "gone", s=sine())
    q.measurements.raw = 60.0
    q.measurements.roll(now=T + 3 * HOUR + 120)
    [r] = ask(q, ("A", series("s")), ("P", call("psd(A)")))[1:]
    assert "series" not in r and codes(r) == ["only-rollups"], r


def test_psd_marks_periods_below_twice_the_step_unobservable(tmp_path):
    p = store(tmp_path, s=sine(every=10.0))
    [r] = ask(p, ("A", series("s")), ("P", call("psd(A)")))[1:]
    lo = 2 * max(r["meta"]["sampling"]["scrape_s"], r["step"])
    assert r["not_observable_s"] == [0, lo] == [0, r["meta"]["sampling"]["observable_period_s"][0]]
    assert min(r["series"][0]["xs"]) >= lo
    rng = random.Random(2)                            # a scrape coarser than the grid: the guard cuts what the FFT holds
    v = [rng.gauss(0, 1) for _ in range(512)]
    got = spectra.psd("A", v, 10.0, 60.0)
    assert got["not_observable_s"] == [0, 120.0] and min(got["series"][0]["xs"]) >= 120
    full = spectra.psd("A", v, 10.0, None)
    assert min(full["series"][0]["xs"]) < 120 and len(full["series"][0]["xs"]) > len(got["series"][0]["xs"])
    with pytest.raises(Refused, match="none is observable"):
        spectra.psd("A", v, 10.0, 1e6)


def test_spectrogram_shows_when_a_period_starts(tmp_path):
    p = store(tmp_path, s=sine(n=1440, noise=0.1, after=7200.0))                   # the sine starts halfway
    [r] = ask(p, ("A", series("s")), ("G", call("spectrogram(A, length=20m)")), until=T + 4 * HOUR, since=4 * HOUR)[1:]
    assert "error" not in r and r["shape"] == "table" and [d["name"] for d in r["dims"]] == ["start", "frequency"], r
    assert len(r["rows"]) <= spectra.MOST_CELLS
    near = min({row[1] for row in r["rows"]}, key=lambda hz: abs(hz - 1 / 300))
    at = {row[0]: row[2] for row in r["rows"] if row[1] == near}
    span = r["segment_samples"] * r["sample_seconds"]
    before = [v for t, v in at.items() if t + span <= T + 7200]
    after = [v for t, v in at.items() if t >= T + 7200]
    assert before and after and max(before) * 20 < min(after), (before, after)
    [r] = ask(p, ("A", series("s")), ("G", call("spectrogram(A, length=20m, cells=100)")), until=T + 4 * HOUR,
              since=4 * HOUR)[1:]
    assert 0 < len(r["rows"]) <= 100 and "partial" in codes(r), r                  # thinned to the cells asked


def test_ccf_names_the_lag_and_its_sign(tmp_path):
    rng = random.Random(3)
    a = [rng.gauss(0, 1) for _ in range(720)]
    p = store(tmp_path, a=[(T + 10 * i, v) for i, v in enumerate(a)],
              b=[(T + 10 * i, a[i - 12] if i >= 12 else 0.0) for i in range(720)])   # B = A, 120 s later
    _, _, r, w = ask(p, ("A", series("a")), ("B", series("b")), ("C", call("ccf(A, B, most_lag=5m)")),
                     ("W", call("ccf(B, A, most_lag=5m)")))
    assert "error" not in r and r["shape"] == "points" and r["order"] == "x" and r["x"]["unit"] == "s", r
    s = r["series"][0]
    assert s["xs"] == sorted(s["xs"]) and s["xs"][0] == -300 and s["xs"][-1] == 300
    assert s["xs"][peak(r)] == 120 and s["values"][peak(r)] > 0.9 and s["values"][peak(r)] > s["upper"][peak(r)]
    assert all(lo == -hi for lo, hi in zip(s["lower"], s["upper"], strict=True))
    assert w["series"][0]["xs"][peak(w)] == -120
    inside = []                                       # two independent white signals: about 95% of lags inside
    for seed in range(4):
        rng = random.Random(10 + seed)
        got = spectra.ccf(["A", "B"], *([rng.gauss(0, 1) for _ in range(1000)] for _ in "ab"), 1.0, 100)["series"][0]
        inside += [lo <= x <= hi for x, lo, hi in zip(got["values"], got["lower"], got["upper"], strict=True)]
    assert 0.9 <= sum(inside) / len(inside) <= 0.99, sum(inside) / len(inside)


def test_pair_is_ordered_by_time_on_one_grid(tmp_path):
    rng = random.Random(4)
    p = store(tmp_path, a=[(T + 10 * i, rng.gauss(0, 1)) for i in range(720)],
              b=[(T + 30 * i + 5, rng.gauss(0, 1)) for i in range(240)])
    [r] = ask(p, ("A", series("a")), ("B", series("b")), ("P", call("pair(A, B)")))[2:]
    assert "error" not in r and r["shape"] == "points" and r["order"] == "time", r
    s = r["series"][0]
    t = s["times"]
    assert t == sorted(t) and len(set(t)) == len(t) and len(t) == len(s["xs"]) == len(s["values"]) >= 230
    assert {round(b - a) for a, b in zip(t, t[1:], strict=False)} == {30} and r["step"] == 30    # one grid, the coarser
    [said] = [x["says"] for x in r["meta"]["verdict"]["reasons"] if x["code"] == "mixed-windows" and "was read" in x["says"]]
    assert "'A' was read at a step of 10 s" in said and "'B' was read at a step of 30 s" in said, said
    (tmp_path / "same").mkdir()                       # alike: no such warning of the call's own
    q = store(tmp_path / "same", a=[(T + 10 * i, rng.gauss(0, 1)) for i in range(720)],
              b=[(T + 10 * i, rng.gauss(0, 1)) for i in range(720)])
    [r] = ask(q, ("A", series("a")), ("B", series("b")), ("P", call("pair(A, B)")))[2:]
    assert "error" not in r and r["step"] == 10, r
    assert not any(x["code"] == "mixed-windows" and "was read at" in x["says"] for x in r["meta"]["verdict"]["reasons"])


GOOD = [math.sin(i / 3) + 0.1 * (i % 5) for i in range(400)]
BAD = {"short": (GOOD[:20], "too short"), "nonfinite": ([*GOOD[:200], math.nan, *GOOD[201:]], "NaN or ±inf"),
       "gappy": ([None if i % 10 == 0 else x for i, x in enumerate(GOOD)], "no stretch is long enough"),
       "flat": ([2.0] * 400, "flat")}


def test_calls_refuse_short_gappy_flat_or_nonfinite_records(tmp_path):
    calls = {"psd": lambda v: spectra.psd("A", v, 10.0, 10.0),
             "spectrogram": lambda v: spectra.spectrogram("A", v, 10.0, T, 10.0),
             "ccf": lambda v: spectra.ccf(["A", "B"], v, list(GOOD), 10.0),
             "pair": lambda v: spectra.pair(["A", "B"], v, list(GOOD), list(range(len(v))))}
    for name, run in calls.items():
        assert run(list(GOOD))                        # the good record answers
        for case, (v, words) in BAD.items():
            with pytest.raises(Refused, match=words):
                run(v + [None] * (len(GOOD) - len(v)) if case == "short" and name in ("ccf", "pair") else v)
    held = {"short": [i for i in range(20)], "gappy": [i for i in range(400) if i % 10 < 6],   # 50 s holes: listed
            "flat": list(range(400))}
    for case, at in held.items():                     # through the source: a refusal, never zeros or an empty curve
        (tmp_path / case).mkdir()
        p = store(tmp_path / case, a=[(T + 10 * i, 2.0 if case == "flat" else GOOD[i]) for i in at],
                  b=[(T + 10 * i, x) for i, x in enumerate(GOOD)])
        for text in ("psd(A)", "spectrogram(A)", "ccf(A, B)", "pair(A, B)"):
            [r] = ask(p, ("A", series("a")), ("B", series("b")), ("X", call(text)))[2:]
            assert "error" in r and "series" not in r and "rows" not in r and codes(r) == ["unanalysable"], (case, text, r)
            assert BAD[case][1] in r["error"], (case, text, r["error"])


def test_every_count_a_call_takes_has_a_ceiling(tmp_path):
    p = store(tmp_path, a=sine(), b=sine(seed=2))
    texts = {"segments": "psd(A, segments=65)", "length": "spectrogram(A, length=1d)", "cells": "spectrogram(A, cells=5001)",
             "most_lag": "ccf(A, B, most_lag=1d)", "huge": "psd(A, segments=99999999999)", "detrend": "psd(A, detrend=cubic)",
             "dur": "ccf(A, B, most_lag=soon)"}
    got = dict(zip(texts, ask(p, ("A", series("a")), ("B", series("b")),
                              *((k, call(t)) for k, t in texts.items()))[2:], strict=True))
    for k, r in got.items():
        assert "error" in r and r["meta"]["verdict"]["level"] == "refuse" and "series" not in r and "rows" not in r, k
    assert "segments is a whole number from 1 to 64" in got["segments"]["error"]
    assert "segments is a whole number from 1 to 64" in got["huge"]["error"]
    assert "a stretch is 16 to 1024 samples" in got["length"]["error"]
    assert "cells is a whole number from 1 to 5000" in got["cells"]["error"]
    assert "it is 1 to 256 samples" in got["most_lag"]["error"]
    assert "detrend is one of linear, mean, none" in got["detrend"]["error"] and "is a duration" in got["dur"]["error"]
    [r] = ask(p, ("A", series("a")), ("G", call("spectrogram(A, length=320s, cells=3)")))[1:]
    assert "more than the 3 cells asked" in r["error"]                              # one stretch over the cells: refused
    [r] = ask(p, ("A", series("a")), ("P", call("psd(A, segments=64)")))[1:]
    assert "error" not in r and r["segments"] >= 64, r                              # at the ceiling: answered
