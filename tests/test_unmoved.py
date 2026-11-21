"""A change that cannot move the replay, judged by structure (SPEC §12e; docs/roadmap/overnight/the-judge-almost-never-
decides.md): on the slow queue of test_slowjudge, a change whose replay is exactly the model's, on a record that
exercised what it touches, is passed, failed or said inconclusive by the redesign scorecard (the fit only against it),
under the proposals' lock, stamped with the version of the model the scorecard read, and never written by ``auto``."""

from __future__ import annotations

import math

import pytest

from ergostat import model as mdl
from ergostat.numbers import improve as im
from ergostat.numbers import judge as jd
from ergostat.numbers import proposals as pr
from ergostat.numbers import scorecard as sc
from ergostat.numbers import trial as tr
from ergostat.numbers import unmoved as un
from ergostat.spec import read
from ergostat.store import Project

from .test_slowjudge import BEFORE, SLOW, WEEK, slow_world

H = 3600.0
BASE = SLOW.format(k=0.05)
K_LINE = "    value: 0.05          # what we believe"
SERVED = "  served:\n    from: queue\n"
DONE = BASE.replace(SERVED, SERVED + "    to: done\n", 1).replace("flows:", "  done:\n    unit: jobs\nflows:", 1)
AUTO = "    accept: {structure: auto, parameter: auto}\n"

# served jobs leave the model: answers stock-without-outflow@stock.done, moves no replayed stock (done is not read)
LEAVE = {"kind": "structure", "parts": ["flow.served", "stock.done"], "title": "served jobs leave",
         "edit": [{"file": "ergostat.yaml", "replace": "    to: done\n", "with": ""},
                  {"file": "ergostat.yaml", "replace": "  done:\n    unit: jobs\n", "with": ""}],
         "reasons": [{"says": "nothing drains done", "evidence": "finding:stock-without-outflow@stock.done"}]}
# served jobs go to done, which nothing drains: makes stock-without-outflow@stock.done
INTO = {"kind": "structure", "parts": ["flow.served", "stock.done"], "title": "served jobs are kept",
        "edit": [{"file": "ergostat.yaml", "replace": SERVED, "with": SERVED + "    to: done\n"},
                 {"file": "ergostat.yaml", "replace": "flows:\n", "with": "  done:\n    unit: jobs\nflows:\n"}],
        "reasons": [{"says": "where served jobs go is not said", "evidence": "finding:no-description@flow.served"}]}
# served jobs go to done, drained by shipped, both described: no structural measure moves
SHIP_DESCRIBED = ("  done:\n    unit: jobs\n    description: jobs served\nflows:\n", "  shipped:\n    from: done\n"
                  "    description: jobs shipped\n    driven-by: +stock.done\n    equation: k * stock.done\nblocks:\n")
STILL = {"kind": "structure", "parts": ["flow.served", "stock.done"], "title": "served jobs are shipped",
         "edit": [{"file": "ergostat.yaml", "replace": SERVED, "with": SERVED + "    to: done\n"},
                  {"file": "ergostat.yaml", "replace": "flows:\n", "with": SHIP_DESCRIBED[0]},
                  {"file": "ergostat.yaml", "replace": "blocks:\n", "with": SHIP_DESCRIBED[1]}],
         "reasons": [{"says": "where served jobs go is not said", "evidence": "finding:no-description@flow.served"}]}
# done drained by shipped: answers stock-without-outflow@stock.done and removes nothing
SHIP = {"kind": "structure", "parts": ["flow.served", "flow.shipped"], "title": "done is shipped",
        "edit": {"file": "ergostat.yaml", "replace": "blocks:\n",
                 "with": "  shipped:\n    from: done\n    driven-by: +stock.done\n    equation: k * stock.done\nblocks:\n"},
        "reasons": [{"says": "nothing drains done", "evidence": "finding:stock-without-outflow@stock.done"}]}


@pytest.fixture(autouse=True)
def _identified(monkeypatch):
    """What is measured is the judge: the improver's own hold on a value the record cannot yet identify is put aside."""
    from ergostat.numbers import identify as idf
    monkeypatch.setattr(idf, "record_says", lambda *a, **k: None)


def reloaded(p):
    """The project as the engine holds it after it reads the model files again (a hand edit is seen from then on)."""
    return Project(mdl.load(p.model.path.parent))


def world(d, text: str, hours: float = 48.0, seed: int = 1, flat: bool = False):
    """The slow queue's record (or, ``flat``, a queue that never moves), the model written as ``text``."""
    if flat:
        d.mkdir(parents=True, exist_ok=True)
        (d / "ergostat.yaml").write_text(text)
        p = Project(mdl.load(d))
        made = 1.79e9
        t = made - BEFORE * H
        while t <= made + hours * H:
            p.measurements.add("sensor/queue.main", 10.0, at=t)
            p.measurements.add("sensor/arrivals.main", 0.0, at=t)
            t += 900
        return p, made
    _, made = slow_world(d, seed, 0.05, 0.05, hours=hours)
    (d / "ergostat.yaml").write_text(text)
    return Project(mdl.load(d)), made


def submit(p, raw: dict, made: float) -> str:
    got = im.submit(p, "tester", raw, at=made)
    assert got["status"] == "proposed", got
    return got["id"]


def measured_coherence(monkeypatch, after_raises: bool = False, mismatches_before: int = 0):
    """Coherence compared on the record (one kind, both sides alike), or raising on the after side."""
    from ergostat import coherence as co
    calls = []

    def compare(spec, events, since, until, problems):
        calls.append(spec)
        if after_raises and len(calls) % 2 == 0:
            raise OSError("the record cannot be read")
        return {"kinds": {"job": {"agree": 3, "compared": 4}},
                "findings": [{"level": "mismatch", "id": f"m{i}", "kind": "job", "code": "c", "about": "x"}
                             for i in range(mismatches_before if len(calls) % 2 else 0)]}
    monkeypatch.setattr(co, "compare", compare)


def measured_fit(monkeypatch, before: float | None = 0.2, after: float | None = 0.2):
    """The fit as worked out on the model as it is (the first call of a score) and with the change (the second)."""
    calls = []

    def fit(p, spec):
        calls.append(spec)
        v = before if len(calls) % 2 else after
        return {"total": {"nmse": v} if v is not None else None, "stocks": {}, "equations": {}}
    monkeypatch.setattr(sc, "fit", fit)


def test_an_unmoved_change_that_answers_a_finding_is_passed_on_structure(tmp_path):
    p, made = world(tmp_path / "w", DONE)
    pid = submit(p, LEAVE, made)
    out = jd.run(p, "judge", at=made + 24 * H)                  # its first decided look: the record it needs (a day)
    x = pr.stored(p)[pid]
    assert x["state"] == "passed", (x.get("undecided"), x.get("verdict"))
    v = x["verdict"]
    assert v["on"] == "structure" and v["version"] == x["version"]
    assert "stock-without-outflow@stock.done" in v["scorecard"]["findings"]["resolved"] and v["scorecard"]["verdict"] == "better"
    assert out["verdicts"][0]["verdict"] == "passed"


def test_an_unmoved_change_that_is_structurally_worse_is_failed(tmp_path):
    p, made = world(tmp_path / "w", BASE)
    pid = submit(p, INTO, made)
    jd.run(p, "judge", at=made + 24 * H)
    x = pr.stored(p)[pid]
    assert x["state"] == "failed", (x.get("undecided"), x.get("verdict"))
    assert x["verdict"]["on"] == "structure" and "stock-without-outflow@stock.done" in x["verdict"]["why"]


def test_measured_and_unchanged_is_inconclusive(tmp_path, monkeypatch):
    p, made = world(tmp_path / "w", BASE)
    pid = submit(p, STILL, made)
    measured_coherence(monkeypatch)
    measured_fit(monkeypatch)
    jd.run(p, "judge", at=made + 24 * H)
    x = pr.stored(p)[pid]
    assert x["state"] == "inconclusive", (x.get("undecided"), x.get("verdict"))
    assert "no structural measure moves" in x["verdict"]["why"] and x["verdict"]["on"] == "structure"
    assert x["verdict"]["scorecard"]["coherence"]["measurable"]


def test_a_fit_only_improvement_is_inconclusive(tmp_path, monkeypatch):
    p, made = world(tmp_path / "w", BASE)
    pid = submit(p, STILL, made)
    measured_coherence(monkeypatch)
    measured_fit(monkeypatch, before=0.5, after=0.1)              # the fit far better with it: it counts for nothing
    jd.run(p, "judge", at=made + 24 * H)
    x = pr.stored(p)[pid]
    assert x["state"] == "inconclusive", (x.get("undecided"), x.get("verdict"))
    card = x["verdict"]["scorecard"]
    card["fit"] = {**card["fit"], "made_measurable": True, "measurable_before": False, "worse": False}
    assert sc.verdict(card, fit_counts=True)[0] == "better"      # the redesign path: made measurable counts for it
    assert sc.verdict(card, fit_counts=False)[0] == "no better"  # the judge's: never


def test_coherence_that_cannot_be_compared_never_makes_it_better(tmp_path, monkeypatch):
    p, made = world(tmp_path / "w", BASE)
    spec, problems = read(p.model.path)
    card = sc.score(p, spec, problems, spec, problems, at=made, fit_counts=False)   # (a) no kind compared either side
    assert card["coherence"]["measurable"] is False and "no kind is compared" in card["coherence"]["says"]
    assert card["verdict"] != "better"
    measured_coherence(monkeypatch, after_raises=True, mismatches_before=2)       # (b) the after side cannot be read
    card = sc.score(p, spec, problems, spec, problems, at=made, fit_counts=False)
    assert card["coherence"]["mismatches_before"] == 2 and card["coherence"]["mismatches_after"] == 0
    assert card["coherence"]["measurable"] is False and "OSError" in card["coherence"]["says"]
    assert card["verdict"] != "better" and "mismatches fewer" not in card["why"], card["why"]


def test_coherence_lost_after_the_change_blocks_a_pass(tmp_path, monkeypatch):
    p, made = world(tmp_path / "w", DONE)
    pid = submit(p, LEAVE, made)                                   # it resolves a finding ...
    measured_coherence(monkeypatch, after_raises=True)             # ... and coherence cannot be compared with it
    jd.run(p, "judge", at=made + 24 * H)
    x = pr.stored(p)[pid]
    assert x["state"] == "failed", (x.get("undecided"), x.get("verdict"))
    assert "coherence down" in x["verdict"]["why"]


def test_the_fit_lost_after_the_change_blocks_a_pass(tmp_path, monkeypatch):
    p, made = world(tmp_path / "w", DONE)
    pid = submit(p, LEAVE, made)
    measured_fit(monkeypatch, before=0.2, after=None)              # measurable before, not after
    jd.run(p, "judge", at=made + 24 * H)
    x = pr.stored(p)[pid]
    assert x["state"] == "failed" and "the fit worse" in x["verdict"]["why"], (x.get("undecided"), x.get("verdict"))


def test_a_fit_unmeasurable_before_and_after_never_makes_it_better(tmp_path, monkeypatch):
    p, made = world(tmp_path / "w", BASE)
    pid = submit(p, STILL, made)
    measured_coherence(monkeypatch)
    measured_fit(monkeypatch, before=None, after=None)
    jd.run(p, "judge", at=made + 24 * H)
    x = pr.stored(p)[pid]
    assert x["state"] == "testing" and "the fit" in x["undecided"] and "verdict" not in x, x.get("undecided")
    card = sc.score(p, *read(p.model.path), *read(p.model.path), at=made, fit_counts=False)
    assert card["fit"]["measurable_before"] is False and card["verdict"] != "better"


@pytest.mark.slow
def test_an_unmeasurable_scorecard_stays_under_test_and_says_why(tmp_path, monkeypatch):
    from ergostat import coherence as co
    p, made = world(tmp_path / "w", BASE, hours=WEEK + 2)
    pid = submit(p, STILL, made)

    def broken(*a, **k):
        raise OSError("the record cannot be read")
    monkeypatch.setattr(co, "compare", broken)
    measured_fit(monkeypatch, before=None, after=None)
    jd.run(p, "judge", at=made + 24 * H)
    x = pr.stored(p)[pid]
    assert x["state"] == "testing" and "coherence" in x["undecided"] and "the fit" in x["undecided"], x.get("undecided")
    jd.run(p, "judge", at=made + jd.horizon(86400.0) + 60)
    x = pr.stored(p)[pid]
    assert x["state"] == "inconclusive", (x.get("undecided"), x.get("verdict"))
    assert "coherence" in x["verdict"]["why"] and "the fit" in x["verdict"]["why"] and x["verdict"]["on"] == "structure"


def test_a_change_leaving_the_model_uncompilable_is_failed(tmp_path, monkeypatch):
    from ergostat.spec.load import Problem
    p, made = world(tmp_path / "w", DONE)
    pid = submit(p, LEAVE, made)
    real = tr.compiled

    def compiled(main, texts, findings=False):
        spec, problems = real(main, texts, findings)
        return spec, ([*problems, Problem("error", "it breaks", code="bad")] if findings else problems)
    monkeypatch.setattr(tr, "compiled", compiled)
    scored = []
    monkeypatch.setattr(sc, "score", lambda *a, **k: scored.append(1))
    jd.run(p, "judge", at=made + 24 * H)
    x = pr.stored(p)[pid]
    assert x["state"] == "failed" and "no longer compiles" in x["verdict"]["why"], x.get("verdict")
    assert not scored and x["verdict"]["scorecard"] is None


def _same_after(monkeypatch, delta: float | None):
    """compare's second replay (with the change) read as exactly the first's, or with ``delta`` added to one reading."""
    real, calls = jd.readings, []

    def readings(*a, **k):
        got = real(*a, **k)
        calls.append(got)
        if len(calls) % 2:
            return got
        out = {r: dict(v) for r, v in calls[-2].items()}
        if delta is not None:
            r = sorted(out)[0]
            i = sorted(out[r])[3]
            out[r][i] = (out[r][i][0] + delta, out[r][i][1])
        return out
    monkeypatch.setattr(jd, "readings", readings)


def test_identical_means_exactly_equal(tmp_path, monkeypatch):
    k_to = {"kind": "parameter", "parts": ["parameter.k"], "title": "k a trifle more",
            "edit": {"file": "ergostat.yaml", "replace": K_LINE, "with": K_LINE.replace("0.05 ", "0.05000000005 ", 1)},
            "reasons": [{"says": "the replay of queue drifts", "evidence": "fit:stock.queue.um"}], "confidence": 0.5}
    readings = jd.readings
    p, made = world(tmp_path / "a", BASE)                         # a real change: the replay moves by about 1e-9
    pid = submit(p, k_to, made)
    jd.run(p, "judge", at=made + 24 * H)
    x = pr.stored(p)[pid]
    assert x["state"] == "testing" and "structural" not in str(x.get("undecided")), x.get("undecided")
    assert "on" not in (x.get("verdict") or {}) and "within" in x["undecided"]   # by the bound: within the threshold so far
    p, made = world(tmp_path / "b", BASE)
    pid = submit(p, k_to, made)
    _same_after(monkeypatch, None)                               # the same change, its replay exactly the model's
    jd.run(p, "judge", at=made + 24 * H)
    x = pr.stored(p)[pid]
    assert "no structural measure moves" in str(x.get("undecided") or x.get("verdict")), (x.get("undecided"), x.get("verdict"))
    for delta, same in ((None, True), (1e-9, False), (math.nan, False)):
        monkeypatch.setattr(jd, "readings", readings)
        _same_after(monkeypatch, delta)
        ev = jd.compare(p, p.model.spec, p.model.spec, made, made + 24 * H, 0.0, ["stock.queue"])
        assert ev["same"] is same, delta


def test_a_record_that_did_not_exercise_it_still_waits(tmp_path, monkeypatch):
    p, made = world(tmp_path / "w", BASE, flat=True)              # the queue read, but it never moves
    pid = submit(p, STILL, made)
    scored = []
    monkeypatch.setattr(un, "judged", lambda *a, **k: scored.append(1))
    jd.run(p, "judge", at=made + 24 * H)
    x = pr.stored(p)[pid]
    assert x["state"] == "testing" and "waits for record in which it moves" in x["undecided"], x.get("undecided")
    assert not scored and "verdict" not in x
    q = Project(mdl.load(tmp_path / "w"))                         # and a stock with no readings is not exercised
    nd = {"stocks": ["stock.done", "stock.queue"]}
    assert un.exercised_now(q, q.model.spec, {"stocks": ["stock.done"]}, made, made + 24 * H) == []
    assert un.exercised_now(q, q.model.spec, nd, made, made + 24 * H) == []
    assert un.exercised_now(q, q.model.spec, {"stocks": []}, made, made + 24 * H) == []


def _hand_edit(p):
    path = p.model.path
    path.write_text(path.read_text().replace(K_LINE, K_LINE.replace("0.05 ", "0.06 ", 1), 1))


def test_a_model_edited_before_the_scorecard_reads_gets_no_verdict(tmp_path, monkeypatch):
    p, made = world(tmp_path / "w", DONE)
    pid = submit(p, LEAVE, made)
    real = un._read

    def read_after_an_edit(p_):
        _hand_edit(p_)
        return real(p_)
    monkeypatch.setattr(un, "_read", read_after_an_edit)
    out = jd.run(p, "judge", at=made + 24 * H)
    x = pr.stored(p)[pid]
    assert "verdict" not in x and x["state"] == "testing" and not out["verdicts"], x.get("verdict")
    assert not [e for e in p.events.query(n=None) if e["type"].endswith(".passed")]
    monkeypatch.setattr(un, "_read", real)
    q = reloaded(p)
    out = jd.run(q, "judge", at=made + 25 * H)
    assert {"id": pid, "verdict": "superseded"}.items() <= out["verdicts"][0].items() and pid not in pr.stored(q)


def test_a_verdict_carries_the_version_the_scorecard_read(tmp_path, monkeypatch):
    p, made = world(tmp_path / "w", DONE.replace("    hold-out: 1h\n", "    hold-out: 1h\n" + AUTO))
    pid = submit(p, SHIP, made)
    was = pr.stored(p)[pid]["version"]
    real = sc.score

    def score_then_an_edit(*a, **k):
        card = real(*a, **k)
        _hand_edit(p)                                             # after the read, before the event
        return card
    monkeypatch.setattr(sc, "score", score_then_an_edit)
    out = jd.run(p, "judge", at=made + 24 * H)
    x = pr.stored(p)[pid]
    assert x["state"] == "passed" and x["verdict"]["version"] == was, x.get("verdict")
    assert not out["accepted"]
    q = reloaded(p)
    with pytest.raises(pr.ProposalError, match="the model has changed"):
        pr.accept(q, pid, {"at": made + 24 * H, "window": 86400.0})
    assert pid not in [x["id"] for x in pr.pending(q)]
    monkeypatch.setattr(sc, "score", real)
    out = jd.run(q, "judge", at=made + 25 * H)
    assert not out["accepted"] and pid not in pr.stored(q) and out["verdicts"][0]["verdict"] == "superseded"


def test_a_pass_on_structure_is_never_written_by_auto(tmp_path):
    p, made = world(tmp_path / "w", DONE.replace("    hold-out: 1h\n", "    hold-out: 1h\n" + AUTO))
    pid = submit(p, SHIP, made)
    x = pr.stored(p)[pid]
    assert not jd.removes(x) and not x.get("rewires")             # nothing else makes it the owner's
    out = jd.run(p, "judge", at=made + 24 * H)
    x = pr.stored(p)[pid]
    assert x["state"] == "passed" and x["verdict"]["on"] == "structure", (x.get("undecided"), x.get("verdict"))
    assert jd.owners(x) and not out["accepted"]
    jd.run(p, "judge", at=made + 25 * H)
    assert pr.stored(p)[pid]["state"] == "passed" and "shipped" not in p.model.path.read_text()


def _week(p, made: float, pid: str, step_h: float = 6.0) -> tuple[str | None, float | None]:
    """The judge every ``step_h`` hours of a week of record after the change: its verdict and the hours it came at."""
    for j in range(1, int(WEEK / step_h) + 1):
        jd.run(p, "judge", at=made + j * step_h * H)
        x = pr.changes(p).get(pid)
        if x and x[0] not in ("checked", "testing"):
            return x[0], j * step_h
    return None, None


@pytest.mark.slow
def test_measured_on_the_slow_world(tmp_path, monkeypatch):
    """The measurement (docs/roadmap/overnight/the-judge-almost-never-decides.md): unmoved structural changes on the slow
    queue, a week of record each, before (the structural path off: the judge as on main) and after; and the table's
    no-difference case (k 0.05 → 0.0501), which moves the replay and so is judged by the bound as before."""
    cases = {"answers a finding": (DONE, LEAVE), "makes a finding": (BASE, INTO), "moves nothing": (BASE, STILL),
             "answers one, opens a note": (DONE, SHIP)}
    seeds, rows = range(5), {}
    for side in ("before", "after"):
        with monkeypatch.context() as m:
            if side == "before":
                m.setattr(un, "exercised_now", lambda *a, **k: [])
            for name, (text, raw) in cases.items():
                got = []
                for s in seeds:
                    p, made = world(tmp_path / f"{side}-{name[:5]}-{s}", text, hours=WEEK, seed=s)
                    got.append(_week(p, made, submit(p, raw, made)))
                rows[(side, name)] = got
    for (side, name), got in rows.items():
        vs = [v for v, _ in got]
        print(f"MEASURED {side:6} {name:26} passed {vs.count('passed')} failed {vs.count('failed')} inconclusive "
              f"{vs.count('inconclusive')} undecided {vs.count(None)}; hours {sorted(h for _, h in got if h)}")
    after = {n: [v for v, _ in rows[("after", n)]] for n in cases}
    assert after["answers a finding"] == ["passed"] * 5 and after["makes a finding"] == ["failed"] * 5
    assert after["moves nothing"].count("passed") == 0
    nodiff = []
    for s in range(20):
        p, made = slow_world(tmp_path / f"k{s}", s, 0.05, 0.05)
        raw = {"kind": "parameter", "parts": ["parameter.k"], "title": "k is 0.0501",
               "edit": {"file": "ergostat.yaml", "replace": K_LINE, "with": K_LINE.replace("0.05 ", "0.0501 ", 1)},
               "reasons": [{"says": "the replay of queue drifts", "evidence": "fit:stock.queue.um"}], "confidence": 0.5}
        got = im.submit(p, "tester", raw, at=made)
        nodiff.append(_week(p, made, got["id"], step_h=1.0)[0] if got["status"] == "proposed" else "not proposed")
    print("MEASURED no difference (k 0.05 -> 0.0501):", {v: nodiff.count(v) for v in set(nodiff)})
    assert nodiff == ["inconclusive"] * 20, nodiff


def test_a_remade_change_keeps_no_structural_pass(tmp_path, monkeypatch):
    p, made = world(tmp_path / "w", BASE.replace("    hold-out: 1h\n", "    hold-out: 1h\n" + AUTO))
    k_to = {"kind": "parameter", "parts": ["parameter.k"], "title": "k is 0.04",
            "edit": {"file": "ergostat.yaml", "replace": K_LINE, "with": K_LINE.replace("0.05 ", "0.04 ", 1)},
            "reasons": [{"says": "the replay of queue drifts", "evidence": "fit:stock.queue.um"}], "confidence": 0.5}
    pid = submit(p, k_to, made)
    readings = jd.readings
    _same_after(monkeypatch, None)                               # its replay the model's ...
    real = sc.score

    def better(*a, **k):                                         # ... and better on structure
        card = real(*a, **k)
        card["verdict"], card["why"] = "better", "better: 1 finding resolved"
        return card
    monkeypatch.setattr(sc, "score", better)
    jd.run(p, "judge", at=made + 24 * H)
    x = pr.stored(p)[pid]
    assert x["state"] == "passed" and x["verdict"]["on"] == "structure", x.get("verdict")
    monkeypatch.setattr(jd, "readings", readings)
    monkeypatch.setattr(sc, "score", real)
    judges = ("id", "state", "status", "verdict", "testing", "looked", "undecided", "more", "hold_out", "judging", "judged_by")
    made_as = {k: v for k, v in x.items() if k not in judges}     # the change as its maker makes it, nothing the judge said
    pr.event(p, pid, "superseded", {"why": "the owner edited elsewhere"})
    pr.save(p, {pid: {**made_as, "status": "pending", "made": made + 26 * H}})   # made again under its id, as a finder does
    assert pr.stored(p)[pid]["state"] == "checked"
    monkeypatch.setattr(jd, "decide", lambda *a, **k: ("kept", "better by the record", None))
    monkeypatch.setattr(jd, "quiet_held", lambda *a, **k: None)
    out = jd.run(p, "judge", at=made + 50 * H)
    x = pr.stored(p)[pid]
    assert out["accepted"] == 1 and x["state"] == "accepted", (x["state"], x.get("verdict"), out["verdicts"])
    assert "on" not in x and "scorecard" not in x and "0.04 " in p.model.path.read_text()
    assert x["verdict"]["why"] == "better by the record" and "on" not in x["verdict"] and "scorecard" not in x["verdict"]
