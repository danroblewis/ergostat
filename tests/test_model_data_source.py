"""The model as a data source (dev/records/model-data-source.md; ergostat/datasources/model.py): Bode, Nyquist and
pole-zero from a goal's declared or identified process, or a transfer function the query writes; a step test's fit with
its quality; the from-data estimate refusing unrelated signals; and the bounds on what the source answers."""

from __future__ import annotations

import base64
import cmath
import json
import math
import random
import time

import pytest

from ergostat import datasources
from ergostat import model as mdl
from ergostat.control import loop as lp
from ergostat.control import lti
from ergostat.datasources import _frames
from ergostat.store import Project
from ergostat.web.server import Live, api
from tests.test_control import TAU, THETA, TUNE, H, K, loop_with_tests

T = 1_795_400_400.0
DECLARED = TUNE.replace("    description: the level held\n",
                        "    description: the level held\n    process:\n      gain: 2\n      time-constant: 100s\n"
                        "      dead-time: 20s\n")


def ask(p, *queries, since=3600.0, until=T, points=60, reader=False) -> list[dict]:
    body = {"since": since, "until": until, "points": points, "queries": [{"id": str(i), **x} for i, x in enumerate(queries)]}
    q = base64.urlsafe_b64encode(json.dumps(body).encode()).decode().rstrip("=")
    return api(Live(p), "query", {"q": [q]}, reader=reader)["results"]


@pytest.fixture
def tune(tmp_path):
    """The tuning loop of tests/test_control.py, its goal declaring K = 2, τ = 100 s and θ = 20 s."""
    d = tmp_path / "tune"
    d.mkdir()
    (d / "ergostat.yaml").write_text(DECLARED)
    return Project(mdl.load(d))


def model(p, text: str, **kw) -> dict:
    return ask(p, {"source": "model", "text": text}, **kw)[0]


def at(f: dict, hz: float) -> int:
    return min(range(len(f["hz"])), key=lambda i: abs(math.log(f["hz"][i] / hz)))


# ---- done 1: known transfer functions match analytic gain and phase

@pytest.mark.parametrize("text, gain, tau, delay", [
    ("fopdt gain=2 tau=100s delay=20s", 2.0, 100.0, 20.0),
    ("fopdt gain=-0.5 tau=5m", -0.5, 300.0, 0.0),
    ("ipdt gain=0.01 delay=30s", 0.01, None, 30.0),
    ("goal level-held", 2.0, 100.0, 20.0),                    # the goal's declared process
])
def test_known_transfer_functions_match_analytic_gain_and_phase(tune, text, gain, tau, delay):
    r = model(tune, text)
    assert "error" not in r, r
    assert r["shape"] == "response" and r["has"] == ["frequency", "system"] and r["method"] == "model"
    assert r["meta"]["verdict"]["level"] == "ok" and r["meta"]["provenance"] == "declared"
    f = r["frequency"]
    for hz in (1e-4, 1e-3, 3e-3, 1e-2):
        i = at(f, hz)
        w = 2 * math.pi * f["hz"][i]
        h = gain * cmath.exp(-1j * w * delay) / (1j * w if tau is None else 1 + 1j * w * tau)
        lag = math.degrees(w * delay) + (90.0 if tau is None else math.degrees(math.atan(w * tau)))
        want = (180.0 if gain < 0 else 0.0) - lag
        assert f["magnitude_db"][i] == pytest.approx(20 * math.log10(abs(h)), abs=1e-6)
        assert f["phase_deg"][i] == pytest.approx(want, abs=1e-6)       # unwrapped: a delay's phase falls without bound
        assert complex(f["re"][i], f["im"][i]) == pytest.approx(h, abs=1e-9)
    assert r["system"]["gain"] == gain and r["system"]["delay"] == delay


def test_the_corner_of_a_first_order_lag_is_minus_three_db_and_minus_45_degrees(tune):
    r = model(tune, "fopdt gain=1 tau=10s")
    f = r["frequency"]
    i = at(f, 1 / (2 * math.pi * 10))
    assert abs(f["hz"][i] * 2 * math.pi * 10 - 1) < 0.03
    assert f["magnitude_db"][i] == pytest.approx(-3.01, abs=0.15) and f["phase_deg"][i] == pytest.approx(-45, abs=1)
    assert r["domain"] == "s" and r["poles"] == [{"re": -0.1, "im": 0.0}] and r["zeros"] == [] and "dt" not in r


# ---- the amendment: pole-zero of a delayed process is the sampled model's, and states dt

def test_a_delayed_process_has_the_poles_and_zeros_of_its_sampled_model_at_the_dt_it_states(tune):
    r = model(tune, "fopdt gain=1 tau=10s delay=25s dt=10s")       # 2.5 periods of delay: 2 whole and a half
    assert r["domain"] == "z" and r["dt"] == 10.0 and r["system"]["dt"] == 10.0
    a, a1 = math.exp(-1), math.exp(-0.5)
    b0, b1 = 1 - a1, a1 - a
    poles = sorted(z["re"] for z in r["poles"])
    assert poles == pytest.approx([0.0] * 3 + [a]) and all(z["im"] == 0 for z in r["poles"])   # z^3 (z − a)
    assert [z["re"] for z in r["zeros"]] == pytest.approx([-b1 / b0]) and r["zeros"][0]["im"] == 0
    whole = model(tune, "fopdt gain=1 tau=10s delay=20s dt=10s")   # whole periods: no zero, and one pole fewer
    assert whole["zeros"] == [] and sorted(z["re"] for z in whole["poles"]) == pytest.approx([0.0, 0.0, a])


def test_a_delayed_process_with_no_dt_is_sampled_at_its_goals_controller_period_or_a_quarter_of_its_delay(tune):
    assert model(tune, "goal level-held")["dt"] == 10.0                 # the tuner runs every 10s
    r = model(tune, "fopdt gain=1 tau=10s delay=20s")
    assert r["dt"] == 5.0 and r["domain"] == "z" and len(r["poles"]) == 5


def test_a_long_declared_delay_under_a_short_controller_period_is_still_drawn_at_a_longer_dt(tmp_path):
    """Dead time 15 min under a 10 s tuner is 90 periods: with no dt asked, the sampled model's dt is lengthened to keep
    the delay within lti.MOST_PERIODS, so Bode, Nyquist and pole-zero all draw, by the source and the old route."""
    (tmp_path / "ergostat.yaml").write_text(DECLARED.replace("dead-time: 20s", "dead-time: 15m"))
    p = Project(mdl.load(tmp_path))
    new, old = ask(p, {"source": "model", "text": "goal level-held"}, {"source": "frequency", "model": {"goal": "level-held"}})
    for r in (new, old):
        assert "error" not in r, r
        assert r["frequency"]["hz"] and r["domain"] == "z" and r["dt"] == pytest.approx(900 / lti.MOST_PERIODS)
        assert lti.MOST_PERIODS <= len(r["poles"]) <= lti.MOST_PERIODS + 2
    assert model(p, "goal level-held dt=60s")["dt"] == 60.0              # (a longer dt asked is kept)


def test_a_delay_of_too_many_periods_is_refused_and_says_to_ask_with_a_longer_dt(tune):
    r = model(tune, "fopdt gain=1 tau=10s delay=1h dt=1s")
    assert r["meta"]["verdict"]["level"] == "refuse" and "longer dt" in r["error"] and r["error_at"] == [1, 31]
    assert "frequency" not in r


# ---- done 2: a simulated step test recovers gain, time constant and delay

def test_a_simulated_step_test_recovers_gain_time_constant_and_delay(tmp_path):
    """Tolerance: K within 5%, τ within 10%, θ within one sample (10 s), as in tests/test_control.py."""
    p = loop_with_tests(tmp_path / "s", [(2700, 5.0, 420)])
    now = time.time()
    for text in ("goal level-held identified", "goal level-held"):     # (it declares none: the identified one)
        r = model(p, text, until=now)
        assert "error" not in r, r
        s = r["system"]
        assert s["form"] == "fopdt" and s["gain"] == pytest.approx(K, rel=0.05) and s["tau"] == pytest.approx(TAU, rel=0.1)
        assert s["delay"] == pytest.approx(THETA, abs=H)
        assert r["process_from"] == "identified" and r["meta"]["provenance"] == "derived"
        fit = r["fit"]
        assert fit["from"] == "step tests" and fit["closed_loop"] is False and fit["proposable"] is True
        assert fit["follows_held_out"] > 50 and 0 < fit["standard_errors"]["K"] < 0.05 * K
        assert r["path"] == {"input": "stock.setting", "output": "stock.level"}
    assert "declares no process" in model(p, "goal level-held declared", until=now)["error"]


def test_a_record_that_does_not_identify_the_process_is_refused_with_its_reasons_and_no_curve(tmp_path):
    (tmp_path / "ergostat.yaml").write_text(TUNE)
    r = model(Project(mdl.load(tmp_path)), "goal level-held")
    assert r["meta"]["verdict"]["level"] == "refuse" and "does not identify its process" in r["error"]
    assert "frequency" not in r


def test_a_process_found_but_not_told_apart_is_refused_not_drawn(tmp_path, monkeypatch):
    """A fit is found, but the record does not tell its numbers apart (ident.judge): it is not drawn as a model."""
    (tmp_path / "ergostat.yaml").write_text(TUNE)
    unsure = {"found": True, "form": "fopdt", "K": K, "tau": TAU, "theta": THETA, "told_apart": False, "proposable": False,
              "why": ["its time constant τ is not told apart by the record"]}
    monkeypatch.setattr(lp, "identify", lambda p, sig, at=None: (dict(unsure), {}))
    r = model(Project(mdl.load(tmp_path)), "goal level-held")
    assert r["meta"]["verdict"]["level"] == "refuse" and "does not identify its process" in r["error"]
    assert "not told apart" in r["error"] and "frequency" not in r
    monkeypatch.setattr(lp, "identify", lambda p, sig, at=None: ({**unsure, "told_apart": True}, {}))
    assert model(Project(mdl.load(tmp_path)), "goal level-held")["system"]["tau"] == TAU      # (told apart: drawn)


# ---- done 3: the from-data estimate takes an input and an output, and refuses unrelated ones

def test_uncorrelated_input_and_output_yield_the_refusal_not_a_curve(tmp_path):
    (tmp_path / "ergostat.yaml").write_text("name: noise\nstocks:\n  queue: {unit: tickets}\n")
    p = Project(mdl.load(tmp_path))
    rnd, n, step = random.Random(11), 1024, 30.0
    xs, ys, zs = ([rnd.gauss(0, 1) for _ in range(n)] for _ in range(3))
    p.measurements.add_many([("in", T + i * step, xs[i]) for i in range(n)] + [("out", T + i * step, ys[i]) for i in range(n)]
                            + [("related", T + i * step, 2 * xs[i] + 0.3 * zs[i]) for i in range(n)])
    q = {"source": "frequency", "input": {"source": "series", "series": "in"}, "output": {"source": "series", "series": "out"}}
    r = ask(p, q, since=n * step, until=T + n * step)[0]
    assert r["supported"] is False and r["meta"]["verdict"]["level"] == "refuse"
    assert all(v == [] for v in r["frequency"].values()) and "no frequency is coherent past chance" in r["refused"]
    r2 = ask(p, {**q, "output": {"source": "series", "series": "related"}}, since=n * step, until=T + n * step)[0]
    assert r2["supported"] is True and r2["frequency"]["hz"]       # the same path draws a related pair


def test_a_from_data_estimate_needs_its_input_and_its_output_named(tune):
    r = ask(tune, {"source": "frequency", "input": {"source": "series", "series": "in"}})[0]
    assert "output is missing" in r["error"]


# ---- the source: its language, its refusals, and who may ask it

@pytest.mark.parametrize("text, word, col", [
    ("bode level-held", "starts goal, fopdt or ipdt", 1),
    ("goal", "needs a goal's name", 5),
    ("goal nope", "not in the model", 6),
    ("fopdt gain=2", "needs tau=", 1),
    ("fopdt gain=0 tau=1s", "other than 0", 7),
    ("fopdt gain=2 tau=1s tau=2s", "given twice", 21),
    ("ipdt gain=1 tau=3s", "takes gain=, delay=, dt=", 13),
    ("fopdt gain=nan tau=1s", "finite number", 7),
    ("fopdt gain=1 tau=soon", "not a duration", 14),
    ("goal level-held dt=-1", "not a duration", 17),
])
def test_a_bad_model_query_is_refused_in_words_at_its_place(tune, text, word, col):
    r = model(tune, text)
    assert word in r["error"] and r["error_at"] == [1, col] and r["error_kind"] == "refused" and "frequency" not in r


def test_the_model_source_is_there_undeclared_and_a_declared_source_of_that_name_wins(tune, tmp_path):
    assert {"name": "model", "type": "model", "language": "model"} in datasources.listed(tune.model.spec)
    (tmp_path / "ergostat.yaml").write_text("name: x\nstocks:\n  q: {unit: t}\nsources:\n"
                                            "  model: {type: prometheus, url: 'http://127.0.0.1:9'}\n  own: {type: model}\n")
    spec = mdl.load(tmp_path).spec
    assert sorted((s["name"], s["type"]) for s in datasources.listed(spec)) == [("model", "prometheus"), ("own", "model")]
    assert not datasources.own(spec, "model") and datasources.own(spec, "own") and not datasources.own(spec, "nope")


def test_a_public_reader_may_ask_the_model_source_but_no_outside_one(tmp_path):
    (tmp_path / "ergostat.yaml").write_text(DECLARED + "sources:\n  prom: {type: prometheus, url: 'http://127.0.0.1:9'}\n")
    p = Project(mdl.load(tmp_path))
    own, outside = ask(p, {"source": "model", "text": "goal level-held"}, {"source": "prom", "text": "up"}, reader=True)
    assert "error" not in own and own["frequency"]["hz"]
    assert "public name" in outside["error"]
    offered = api(Live(p), "query/fields", {}, reader=True)["datasources"]
    assert offered == [{"name": "model", "type": "model", "language": "model"}]


def test_a_public_reader_is_not_given_an_identification_and_the_owner_is(tmp_path, monkeypatch):
    (tmp_path / "ergostat.yaml").write_text(TUNE)
    p = Project(mdl.load(tmp_path))
    ran = []
    found = {"found": True, "form": "fopdt", "K": K, "tau": TAU, "theta": THETA, "told_apart": True, "proposable": True}
    monkeypatch.setattr(lp, "identify", lambda p, sig, at=None: (ran.append(at) or dict(found), {}))
    for text in ("goal level-held", "goal level-held identified"):
        r = model(p, text, reader=True)
        assert "public name" in r["error"] and r["error_kind"] == "refused" and "frequency" not in r
    assert ran == []                                                  # refused before any fitting
    assert "declares no process" in model(p, "goal level-held declared", reader=True)["error"]
    assert model(p, "goal level-held")["system"]["tau"] == TAU and len(ran) == 1


def test_an_identification_is_kept_by_the_records_version_and_done_one_at_a_time(tmp_path, monkeypatch):
    from ergostat.datasources import model as source
    (tmp_path / "ergostat.yaml").write_text(TUNE)
    p = Project(mdl.load(tmp_path))
    ran = []
    found = {"found": True, "form": "fopdt", "K": K, "tau": TAU, "theta": THETA, "told_apart": True, "proposable": True}
    monkeypatch.setattr(lp, "identify", lambda p, sig, at=None: (ran.append(at) or dict(found), {}))
    for _ in range(3):
        assert model(p, "goal level-held")["system"]["gain"] == K
    assert len(ran) == 1                                              # asked again: kept, not fitted again
    p.measurements.add_many([("stock.level", T - 60, 1.0)])
    assert model(p, "goal level-held")["system"]["gain"] == K and len(ran) == 2     # the record moved: fitted again
    assert model(p, "goal level-held", until=T - 600)["system"]["gain"] == K and len(ran) == 3   # another time
    monkeypatch.setattr(datasources, "MOST_SECONDS", 0.5)            # (the query's bound, short to wait out)
    assert source._IDENTIFYING.acquire(timeout=1)                     # another identification under way
    try:
        p.measurements.add_many([("stock.level", T - 30, 2.0)])
        t0 = time.monotonic()
        r = model(p, "goal level-held")
        assert r["error_kind"] == "limit" and "busy" in r["error"] and len(ran) == 3
        assert time.monotonic() - t0 < 5                              # waited no longer than a query may take
    finally:
        source._IDENTIFYING.release()


def test_the_old_model_route_answers_as_the_model_source_does(tune):
    old, new = ask(tune, {"source": "frequency", "model": {"goal": "level-held"}},
                   {"source": "model", "text": "goal level-held declared"})
    assert old["frequency"] == new["frequency"] and old["poles"] == new["poles"] and old["dt"] == new["dt"] == 10.0


@pytest.mark.parametrize("frame, word", [
    ({"frequency": {"hz": [1.0], "re": [1.0], "im": [0.0], "magnitude_db": [0.0], "phase_deg": [0.0]}, "supported": False},
     "refused carries no curve"),
    ({"frequency": {"hz": [1.0, 2.0], "re": [1.0], "im": [0.0], "magnitude_db": [0.0], "phase_deg": [0.0]}}, "one length"),
    ({"frequency": {k: [1.0] for k in ("hz", "re", "im", "magnitude_db", "phase_deg")}, "system": {"poles": [[1.0]]}},
     "two finite numbers"),
    ({"system": {"poles": []}}, "holds frequency"),
])
def test_a_response_frame_that_is_not_one_is_refused(frame, word):
    with pytest.raises(_frames.Bad, match=word):
        _frames.answer({"shape": "response", **frame}, None, 50)


def test_what_a_response_says_of_itself_holds_only_what_json_can():
    ok = {"frequency": {k: [] for k in ("hz", "re", "im", "magnitude_db", "phase_deg")}}
    got = _frames.answer({"shape": "response", **ok, "fit": {"se": {"K": math.inf, "tau": 2.0}, "why": ["a"]}}, None, 50)
    assert got["fit"] == {"se": {"K": None, "tau": 2.0}, "why": ["a"]}
    with pytest.raises(_frames.Bad, match="nested too deep"):
        _frames.answer({"shape": "response", **ok, "fit": {"a": {"b": {"c": 1}}}}, None, 50)
    with pytest.raises(_frames.Bad, match="holds object"):
        _frames.answer({"shape": "response", **ok, "path": object()}, None, 50)


def test_poles_and_zeros_of_a_process_without_delay_need_no_dt_and_one_with_delay_does():
    assert lti.poles_zeros({"form": "integrating", "K": 1.0, "theta": 0.0}) == {"domain": "s", "poles": [[0.0, 0.0]], "zeros": []}
    with pytest.raises(ValueError, match="give dt"):
        lti.poles_zeros({"form": "fopdt", "K": 1.0, "tau": 5.0, "theta": 3.0})
