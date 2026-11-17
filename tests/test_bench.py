"""How we know the improver works (docs/MODEL-TOOLS.md): the improvement loop's pipeline through the adapter
(ergostat/bench/adapter.py), the judge on changes known better, worse or neutral, the recovery benchmark with the
stand-in on a small subset, the prediction check and the loop's own measures."""

from __future__ import annotations

import pytest

from ergostat.bench import adapter as ad
from ergostat.bench import defects as df
from ergostat.bench import form as fm
from ergostat.bench import improvers, judging, recovery, truth
from ergostat.numbers import meta, verify
from ergostat.numbers import observe as ob
from ergostat.numbers import review as rv
from ergostat.numbers import yamledit as ye

HOLD = 2 * 3600.0


def queue(tmp_path, k: float = 2.0, train: float = 6.0, after: float = 8.0):
    """The judge's queue world (truth k = 3), written with k as given; the record runs ``after`` hours past the
    training window."""
    case = truth.cases()["judge-queue"]
    m = case.form()
    m["description"] = None
    m["parameters"]["k"]["value"] = k
    return recovery.prepare(case, tmp_path, rounds=0, train_h=train, round_h=2.0, forecast_h=after, damaged=m)


def k_raw(s, v, **more) -> dict:
    text = s.p.model.path.read_text()
    return {"kind": "parameter", "parts": ["parameter.k"], "title": f"k is {v}", "edit": judging._value_edit(text, "k", v),
            "reasons": [{"says": "the replay of queue runs high", "evidence": "fit:stock.queue.um"}], "confidence": 0.7, **more}


def judged(loop, at, times=3) -> list[str]:
    """The judge run once a hold-out for ``times`` hold-outs; what it wrote."""
    out = []
    for j in range(1, times + 1):
        out += loop.judge(at=at + j * HOLD)["accepted"]
    return out


def submit(s, loop, raw, at=None):
    at = at or s.t(s.train_h)
    return loop.submit("tester", raw, data=ob.measured(s.p, ob.reference(s.p, at)), at=at)


# ---- 1. the pipeline

def test_a_proposal_without_evidence_is_refused(tmp_path):
    s = queue(tmp_path)
    loop = ad.Loop(s.p)
    before = s.p.model.path.read_text()
    for reasons in ([{"says": "trust me"}], [{"says": "it is obvious", "evidence": "because"}], [],
                    [{"says": "a rule I made up", "evidence": "rule:vibes"}], [{"says": "no such stock", "evidence": "fit:stock.nope.r2"}]):
        got = submit(s, loop, k_raw(s, 3, reasons=reasons))
        assert got["status"] == "refused" and "no reason with evidence" in got["why"], (reasons, got)
    assert not loop.pending() and s.p.model.path.read_text() == before


def test_an_edit_that_does_not_compile_is_refused(tmp_path):
    s = queue(tmp_path)
    loop = ad.Loop(s.p)
    for edit, why in (({"file": "ergostat.yaml", "replace": "    equation: k * stock.queue", "with": "    equation: k * stock.nope"},
                       "does not compile"),
                      ({"file": "ergostat.yaml", "replace": "    equation: k * stock.queue", "with": "    equation: k * ("},
                       "does not compile"),
                      ({"file": "ergostat.yaml", "replace": "no such line", "with": "x"}, "found 0 times"),
                      ({"file": "../elsewhere.yaml", "replace": "x", "with": "y"}, "not one of the model's files")):
        got = submit(s, loop, k_raw(s, 3, edit=edit, kind="equation"))
        assert got["status"] == "refused" and why in got["why"], (edit, got)
    assert not loop.pending()


def test_accept_writes_exactly_the_shown_diff(tmp_path):
    s = queue(tmp_path)
    loop = ad.Loop(s.p)
    got = submit(s, loop, k_raw(s, 3))
    assert got["status"] == "proposed"
    x = loop.changes()[got["id"]]
    shown = rv.diff_of(x, s.root)
    before = s.p.model.path.read_text()
    with pytest.raises(Exception, match="changed since the diff was shown"):
        loop.accept(got["id"], at=s.t(s.train_h), expect="not-what-was-shown")
    assert s.p.model.path.read_text() == before
    loop.accept(got["id"], at=s.t(s.train_h), expect=shown["hash"])
    after = s.p.model.path.read_text()
    assert ye.unified(before, after, "ergostat.yaml") == shown["unified"]
    assert [x["id"] for x in loop.accepted()] == [got["id"]]


def test_a_superseded_change_is_never_applied(tmp_path):
    s = queue(tmp_path)
    loop = ad.Loop(s.p, ad.Policy.auto(hold_out=HOLD))
    a = submit(s, loop, k_raw(s, 3))
    b = submit(s, loop, k_raw(s, 2.9, title="k is nearly 3"))
    assert a["status"] == b["status"] == "proposed"
    at = s.t(s.train_h)
    assert judged(loop, at) == [a["id"]]
    assert "    value: 3" in s.p.model.path.read_text().split("  k:", 1)[1].split("\n", 3)[1]
    assert loop.changes()[b["id"]]["state"] in ("superseded", "failed")
    with pytest.raises(Exception):  # noqa: B017 (whichever error the backend raises: it is never written)
        loop.accept(b["id"], at=at + 4 * HOLD)
    assert [x["id"] for x in loop.accepted()] == [a["id"]]
    assert "2.9" not in s.p.model.path.read_text()


def test_a_change_made_against_values_since_rewritten_is_never_applied(tmp_path):
    """A structural change made beside a parameter change, both passed: once the value is written, the structural
    one was fitted against a model that no longer is (only its numbers changed, not its structure), and is never
    written."""
    s = queue(tmp_path)
    loop = ad.Loop(s.p, ad.Policy.auto(hold_out=HOLD))
    a = submit(s, loop, k_raw(s, 3))
    text = s.p.model.path.read_text()
    m = fm.of_spec(s.p.model.spec)
    m["parameters"]["leak"] = {"value": 1.0, "unit": "1/h", "estimate": True}
    m["flows"]["leaks"] = {"from": "queue", "to": None, "driven_by": ["+stock.queue"], "equation": "leak * stock.queue"}
    b = submit(s, loop, {"kind": "structure", "title": "the queue leaks", "parts": ["flow.leaks"],
                         "edit": {"files": [{"file": "ergostat.yaml", "hunks": fm.hunks(text, fm.render(m))}]},
                         "reasons": [{"says": "it drains faster than k says", "evidence": "fit:total.nmse"}]})
    assert a["status"] == b["status"] == "proposed"
    at = s.t(s.train_h)
    assert judged(loop, at) == [a["id"]]
    assert loop.changes()[b["id"]]["state"] in ("superseded", "failed")
    assert "leaks" not in s.p.model.path.read_text() and [x["id"] for x in loop.accepted()] == [a["id"]]


def test_nothing_is_written_without_acceptance_under_the_default_policy(tmp_path):
    s = queue(tmp_path)
    loop = ad.Loop(s.p, ad.Policy(hold_out=HOLD))          # accept: owner, for every kind
    before = s.p.model.path.read_bytes()
    got = submit(s, loop, k_raw(s, 3))
    assert judged(loop, s.t(s.train_h)) == []
    assert loop.changes()[got["id"]]["state"] == "passed"
    assert s.p.model.path.read_bytes() == before and not loop.accepted()


# ---- 2. the judge

def test_the_judge_never_writes_a_worse_or_neutral_change():
    trials = [judging.trial(w, seed, fam, kind) for seed in (1, 2)
              for w, fam in (("judge-queue", "value"), ("judge-delay", "delay")) for kind in ("better", "worse", "neutral")]
    got = judging.rates(trials)
    assert got["false_accepts"] == 0, got["false_accept_examples"]
    assert got["written_by_kind"]["judge-queue/value/better"] == "2/2"     # a clearly better value is written


# ---- 3. the recovery benchmark (the stand-in, a small fast subset)

def test_the_catalogue_plants_each_defect_and_says_where_it_shows():
    case = truth.cases()["004-chain-3"]
    t = case.form()
    for d, gone in (({"kind": "stock-merged", "stock": "b"}, "stock.b"), ({"kind": "flow-removed", "flow": "c-out"}, "flow.c-out"),
                    ({"kind": "parameter-x3", "parameter": "b-to-c-per-b"}, None),
                    ({"kind": "spurious-link", "flow": "c-out", "cause": "stock.a"}, None)):
        m, planted = df.damaged(t, [d])
        text = fm.render(m)
        truth.spec_of(text)                                   # it compiles
        assert planted[0]["locus"] and text != fm.render(t)
        if gone:
            assert gone.split(".")[1] not in (m["stocks"] if gone.startswith("stock") else m["flows"])
    m, _ = df.damaged(truth.cases()["063-delay3-supply-line"].form(), [{"kind": "delay-missing", "flow": "b-arrives"}])
    assert "DELAY3" not in m["flows"]["b-arrives"]["equation"]
    m, _ = df.damaged(truth.cases()["011-goal-gap"].form(), [{"kind": "sign-flipped", "flow": "orders"}])
    assert m["flows"]["orders"]["equation"] == "orders-base + orders-per-i * stock.i"
    assert m["flows"]["orders"]["driven_by"] == ["+stock.i"]


def test_every_truth_case_compiles_simulates_and_takes_its_defects():
    for c in truth.cases().values():
        rec = truth.simulate(c, 1_800_000_000.0, 2.0)
        assert rec.measured and all(len(rec.clean[r]) == 120 for r in rec.measured)
        m, planted = df.damaged(c.form(), c.defects, rec)
        truth.spec_of(fm.render(m))
        assert len(planted) == len(c.defects)


def test_the_stand_in_recovers_a_wrong_parameter_and_a_missing_flow(tmp_path):
    results = []
    for cid in ("002-inflow-outflow", "003-chain-2"):
        s = recovery.prepare(truth.cases()[cid], tmp_path / cid, rounds=3)
        results.append(recovery.run(s, improvers.StandIn()))
    for r in results:
        sc = r.scores
        assert sc["recall"] == 1.0, (r.case, sc["defects"])
        assert sc["damage"] == 0, (r.case, r.accepted)
        assert sc["fit"]["final"] < sc["fit"]["damaged"] and sc["forecast"]["final"] < sc["forecast"]["damaged"]
    j, m = recovery.save(results, tmp_path / "out")
    assert "Recovery benchmark: stand-in" in m.read_text() and j.exists()


# ---- 4. the prediction check, and 5. the loop's own measures

def test_a_written_change_is_verified_or_flagged_for_revert_on_the_record_after_it(tmp_path):
    s = queue(tmp_path, k=3.0, train=6.0, after=10.0)          # the model is right: k = 3
    loop = ad.Loop(s.p, ad.Policy(hold_out=HOLD))
    at = s.t(s.train_h)
    thin = ob.measured(s.p, ob.Grid(at - 300, at, 2))           # checked on five minutes of record: nothing to say it is worse
    bad = loop.submit("tester", k_raw(s, 4.5, reasons=[{"says": "I think so", "evidence": "rule:parameter-assessment"}]),
                      data=thin, at=at)
    assert bad["status"] == "proposed"
    loop.accept(bad["id"], at=at)                             # and the owner wrote it, without waiting for the judge
    early = verify.run(s.p, at=at + HOLD, hold_out=HOLD)
    assert early["waiting"] and not early["regressed"]
    got = verify.run(s.p, at=at + 4 * HOLD, hold_out=HOLD, propose=True)
    assert [x["id"] for x in got["regressed"]] == [bad["id"]]
    ev = s.p.events.query(type=ad.REGRESSED)[-1]
    assert ev["item"] == f"{ad.ITEM}/{bad['id']}" and ev["data"]["revert"]["files"]
    undo = got["regressed"][0]["proposed"]
    assert undo["status"] == "proposed" and "    value: 3" in loop.changes()[undo["id"]]["edit"]["diff"].replace("+ ", "")
    assert verify.run(s.p, at=at + 5 * HOLD, hold_out=HOLD)["regressed"] == []     # checked once
    m = meta.all_of(s.p, now=at + 4 * HOLD + 1)
    assert m["ergostat.model.regressed"] == 1 and m["ergostat.model.verified-share"] == 0.0
    assert m["ergostat.model.accepted-per-day"] > 0


def test_a_good_change_is_verified_and_the_loop_measures_what_it_cost(tmp_path):
    s = queue(tmp_path, k=2.0, train=6.0, after=10.0)
    loop = ad.Loop(s.p, ad.Policy.auto(hold_out=HOLD))
    at = s.t(s.train_h)
    got = submit(s, loop, k_raw(s, 3))
    s.p.events.add("session.ran", item="session/tester-1", source="tester", data={"cost_usd": 0.5}, at=at)
    assert judged(loop, at, 2) == [got["id"]]
    v = verify.run(s.p, at=at + 5 * HOLD, hold_out=HOLD)
    assert [x["id"] for x in v["verified"]] == [got["id"]]
    m = meta.all_of(s.p, now=at + 5 * HOLD)
    assert m["ergostat.model.verified-share"] == 1.0 and m["ergostat.model.fit-gained"] > 0
    assert m["ergostat.model.cost-per-accepted"] == pytest.approx(0.5)
    assert set(m) == set(meta.MEASURES)


def test_the_judge_with_its_proposed_changes_is_not_fooled_by_a_slowed_stock():
    from ergostat.bench import judge_fixes
    with judge_fixes.variant(like=True, warm=True):
        t = [judging.trial("judge-delay", 2, "value", k) for k in ("slowed", "better")]
    assert not t[0].written and t[1].written, t


def test_verified_and_regressed_are_states_of_the_change_item():
    from ergostat.numbers.proposals import STATUS
    from ergostat.spec.ir import MODEL_CHANGE_STATES, MODEL_MEASURES
    assert {"verified", "regressed"} <= set(MODEL_CHANGE_STATES) and STATUS["verified"] == STATUS["regressed"] == "accepted"
    assert set(meta.MEASURES) <= set(MODEL_MEASURES)
