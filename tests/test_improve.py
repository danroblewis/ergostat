"""Improving the model as a loop (SPEC §12e): a propose line from any block, validated the same way whoever
made it and queued attributed to it (numbers/improve.py); the model's own measures as sensors
(numbers/measures.py); the judge of candidates on the record after each, and the acceptance policy
(numbers/judge.py)."""

from __future__ import annotations

import json
import textwrap
import time

import pytest

from ergostat import model as mdl
from ergostat.numbers import improve as im
from ergostat.numbers import judge as jd
from ergostat.numbers import measures as ms
from ergostat.numbers import proposals as pr
from ergostat.numbers import review as rv
from ergostat.spec import read
from ergostat.store import Project

from .test_numbers import QUEUE, queue_project

LINE = "    value: 2          # what we believe"
LEAKS = QUEUE + "  leaks:\n    from: queue\n    driven-by: +flow.arrivals\n"     # a rate driven by a rate


def value_edit(v) -> dict:
    return {"file": "ergostat.yaml", "replace": LINE, "with": LINE.replace("2 ", f"{v} ", 1)}


def raw(v=3, **more) -> dict:
    return {"kind": "parameter", "parts": ["parameter.k"], "title": f"k is {v}", "edit": value_edit(v),
            "reasons": [{"says": "the replay of queue runs high", "evidence": "fit:stock.queue.um"}],
            "confidence": 0.7, **more}


def long_queue(tmp_path, k_true=3.0, text=QUEUE):
    return queue_project(tmp_path, k_true=k_true, text=text, minutes=600)


# ---- 1. a propose line, from any block

def test_a_propose_line_from_a_program_block_lands_in_the_queue_attributed_to_it(tmp_path):
    from ergostat.spec.engine import Engine
    text = QUEUE + textwrap.dedent("""\
        blocks:
          reviewer:
            type: program
            run: cat propose.json
            every: 1h
        """)
    p, _ = queue_project(tmp_path, text=text)
    (tmp_path / "propose.json").write_text(json.dumps({"propose": raw()}) + "\n" +
                                           json.dumps({"propose": {**raw(), "reasons": [{"says": "trust me"}]}}) + "\n")
    e = Engine(p, say=lambda s: None)
    e.run_block(p.model.spec.blocks["reviewer"], "test")
    ran = p.events.query(type="agent.ran", item="reviewer")[-1]["data"]
    assert ran["proposed"] == 1 and ran["not_proposed"] == 1 and ran["refused"] == 0   # a line turned away is not malformed
    x = next(x for x in pr.pending(p) if x.get("proposed_by") == "reviewer")
    assert x["by_rung"] == "program" and x["kind"] == "parameter" and x["parameters"] == {"k": 3.0}
    ev = p.events.query(type="model.proposed")[-1]
    assert ev["item"] == f"proposal/{x['id']}" and ev["source"] == "reviewer"
    e_ = next(y for y in rv.entries(p, p.model.spec) if y["id"] == x["id"])
    assert e_["proposed_by"] == "reviewer" and e_["what"].endswith("proposed by reviewer")
    assert e_["reasons"][0]["verified"][0].startswith("stock.queue um =")
    gone = im.not_proposed(p)
    assert gone and gone[0]["by"] == "reviewer" and "no reason with evidence" in gone[0]["why"]
    assert p.events.query(type="model.refused")[-1]["item"].startswith("proposal/")


def test_reasons_need_evidence_ergostat_can_check(tmp_path):
    p, _ = queue_project(tmp_path)
    (tmp_path / "notes.md").write_text("one\ntwo\nthree\n")
    ev = im.Evidence(p, p.model.spec)
    assert "um" in ev.check("fit:stock.queue.um") and "nmse" in ev.check("fit:total.nmse")
    assert ev.check("notes.md:2").endswith("two") and ev.check("docs/MODELLING.md:1").startswith("docs/MODELLING.md:1")
    assert ev.check("https://example.org/x").startswith("a reference")
    assert "Sterman" in ev.check("rule:extreme-conditions")
    assert "stock queue" in ev.check("residual:stock.queue")
    for bad, why in (("finding:units-mismatch@flow.served", "does not find it now"), ("fit:stock.nope.r2", "no r2"),
                     ("notes.md:9", "it has 4 lines"), ("rule:vibes", "no such modelling rule"), ("because", "not evidence"),
                     ("../../etc/passwd:1", "no such file"), ("", "no evidence")):
        with pytest.raises(im.ProposeError, match=why):
            ev.check(bad)
    got = im.submit(p, "x", {**raw(), "reasons": [{"says": "a", "evidence": "rule:vibes"}, {"says": "b"}]})
    assert got["status"] == "not-proposed" and "no reason with evidence" in got["why"]
    got = im.submit(p, "x", {**raw(), "reasons": [{"says": "a", "evidence": ["rule:vibes", "fit:total.nmse"]}, {"says": "b"}]})
    x = pr.stored(p)[got["id"]]
    assert x["reasons"] == [{"says": "a", "evidence": ["fit:total.nmse"], "verified": [x["reasons"][0]["verified"][0]]}]
    assert [r["says"] for r in x["refused_reasons"]] == ["b"]


def test_a_finding_is_evidence_by_its_id(tmp_path):
    text = LEAKS
    p, _ = queue_project(tmp_path, text=text)
    found = im.Evidence(p, p.model.spec).findings()
    assert "rate-driven-by-rate@flow.leaks" in found
    got = im.submit(p, "x", {"kind": "structure", "parts": ["flow.leaks"], "title": "leaks at once",
                             "edit": {"file": "ergostat.yaml", "replace": "    driven-by: +flow.arrivals",
                                      "with": "    driven-by:\n      - {cause: +flow.arrivals, instant: true}\n      - +stock.queue"},
                             "reasons": [{"says": "a rate on a rate", "evidence": "finding:rate-driven-by-rate@flow.leaks"}]})
    x = pr.stored(p)[got["id"]]
    assert got["status"] == "proposed" and x["kind"] == "structure"
    assert "rate-driven-by-rate@flow.leaks" in x["findings"]["answered"]


def test_what_cannot_be_made_or_compiled_or_worsens_the_fit_is_not_proposed(tmp_path):
    p, _ = long_queue(tmp_path)
    cases = [
        ({"edit": {"file": "ergostat.yaml", "replace": "no such line", "with": "x"}}, "found 0 times"),
        ({"edit": {"file": "../elsewhere.yaml", "replace": LINE, "with": "x"}}, "not one of the model's files"),
        ({"edit": {"file": "ergostat.yaml", "replace": "    equation: k * stock.queue", "with": "    equation: k * stock.nope"}},
         "does not compile"),
        ({"edit": value_edit(40)}, "clearly worsens the fit"),
        ({"kind": "vibes"}, "kind: one of"),
        ({"confidence": 3}, "confidence"),
    ]
    for more, why in cases:
        got = im.submit(p, "x", raw(**more))
        assert got["status"] == "not-proposed" and why in got["why"], (more, got)
    assert len(im.not_proposed(p)) == len(cases)
    assert not pr.pending(p)


def test_the_kind_is_what_the_edit_does_and_the_same_change_is_one_entry(tmp_path):
    p, snap = queue_project(tmp_path, k_true=3.0)
    got = im.submit(p, "x", raw(3, kind="structure"))
    assert pr.stored(p)[got["id"]]["kind"] == "parameter"          # values only: a parameter change, whatever it was called
    pr.make(p, snap)                                               # ergostat's own calibration: let go of its own, never a candidate's
    assert got["id"] in {x["id"] for x in pr.pending(p)}
    own = next(x for x in pr.pending(p) if not pr.candidate(x) and x["kind"] == "parameter")
    files = own["edit"]["files"]
    again = im.submit(p, "improver", {**raw(), "edit": {"files": files}})
    assert again["status"] == "also" and again["id"] == own["id"]
    assert pr.stored(p)[own["id"]]["proposed_by"] == "improver"
    assert im.submit(p, "other", {**raw(), "edit": {"files": files}})["status"] == "also"
    assert pr.stored(p)[own["id"]]["also_by"] == ["other"]
    pr.make(p, snap)
    assert own["id"] in {x["id"] for x in pr.pending(p)}           # a candidate now: not let go by the next calibration


def test_a_new_parameter_to_estimate_is_refitted(tmp_path):
    p, _ = long_queue(tmp_path)
    got = im.submit(p, "x", {"kind": "structure", "parts": ["flow.served"], "title": "served at its own rate",
                             "edit": {"file": "ergostat.yaml", "replace": "    equation: k * stock.queue",
                                      "with": "    equation: k2 * stock.queue"} | {},
                             "reasons": [{"says": "a rate of its own", "evidence": "rule:first-order-drain"}]})
    assert got["status"] == "not-proposed" and "does not compile" in got["why"]     # k2 is not a parameter yet
    edit = [{"file": "ergostat.yaml", "replace": "    equation: k * stock.queue", "with": "    equation: k2 * stock.queue"},
            {"file": "ergostat.yaml", "replace": "parameters:",
             "with": "parameters:\n  k2:\n    value: 1\n    unit: 1/h\n    estimate: true"}]
    got = im.submit(p, "x", {"kind": "structure", "parts": ["flow.served"], "title": "k2", "edit": edit,
                             "reasons": [{"says": "a rate of its own", "evidence": "rule:first-order-drain"}]})
    x = pr.stored(p)[got["id"]]
    assert got["status"] == "proposed", got
    assert x["refit"] and abs(x["refit"]["values"]["k2"] - 3.0) < 0.3
    assert x["refit"]["fit"]["total"]["nmse"] < x["fit_after"]["total"]["nmse"]    # judged as written; refitted, said beside


def test_trial_says_what_would_happen_and_keeps_nothing(tmp_path):
    p, _ = queue_project(tmp_path)
    got = im.trial(p, raw())
    assert got["would"] == "be proposed" and got["scaled_error_after"] < got["scaled_error_before"] and "k" not in got["diff"][:2]
    assert im.trial(p, raw(40))["would"] == "not be proposed"
    assert not pr.stored(p) and not im.not_proposed(p)


def test_the_mcp_server_checks_a_change_and_names_findings_by_id(tmp_path):
    from ergostat.mcp import Server
    text = LEAKS
    queue_project(tmp_path, text=text)
    s = Server(tmp_path)
    chk = json.loads(s.call("check", {})["content"][0]["text"])
    assert any(x.get("id") == "rate-driven-by-rate@flow.leaks" for x in chk["problems"])
    got = json.loads(s.call("try_change", {"propose": raw()})["content"][0]["text"])
    assert got["would"] == "be proposed"
    m = json.loads(s.call("measures", {})["content"][0]["text"])
    assert set(m) >= {"fit", "unexplained", "loops-unidentified", "findings"} and m["findings"] >= 1


def test_an_ai_block_is_told_how_to_propose():
    from ergostat.spec.engine import AI_FOOTER
    assert '{"propose":' in AI_FOOTER and "evidence" in AI_FOOTER


# ---- 2. the model's own measures

MEASURED = QUEUE + textwrap.dedent("""\
    auxiliaries:
      model-error:
        unit: "1"
        sensor:
          model: fit
          every: 1m
    goals:
      model-fits:
        auxiliary: model-error
        hold: "<= 0.05"
    """)


def test_a_model_sensor_reads_one_of_the_models_measures(tmp_path):
    (tmp_path / "ergostat.yaml").write_text(MEASURED)
    spec, problems = read(tmp_path / "ergostat.yaml")
    assert not [x for x in problems if x.level == "error"]
    s = spec.auxiliaries["model-error"].sensors["main"]
    assert s.model == "fit" and s.run.endswith("-m ergostat -C . measure fit") and s.measured and s.timeout == 120
    for bad, why in (("model: vibes", "one of the model's own measures"), ("model: model.findings", None)):
        (tmp_path / "ergostat.yaml").write_text(MEASURED.replace("model: fit", bad))
        _, problems = read(tmp_path / "ergostat.yaml")
        errs = [x.message for x in problems if x.level == "error"]
        assert (why in " ".join(errs)) if why else not errs
    (tmp_path / "ergostat.yaml").write_text(MEASURED.replace("model: fit", "model: fit\n      run: echo 1"))
    assert any(x.code == "sensor-kind" for x in read(tmp_path / "ergostat.yaml")[1])


def test_the_measures_read_the_model_against_the_record(tmp_path):
    from ergostat.numbers import fit as ft
    p, snap = queue_project(tmp_path, text=MEASURED)
    _, _, got = ft.compute(p, {"at": time.time()})
    assert ms.measure(p, "fit") == pytest.approx(got["total"]["nmse"])
    assert ms.measure(p, "model.fit") == pytest.approx(ms.measure(p, "fit"), rel=1e-4)
    assert 0.0 <= ms.measure(p, "unexplained") <= 1.0
    assert ms.measure(p, "findings") == sum(1 for x in read(p.model.path)[1] if x.level != "error")
    assert ms.measure(p, "loops-unidentified") == 0                 # the goal's loop does not close: nothing to identify
    with pytest.raises(ms.MeasureError):
        ms.measure(p, "vibes")


def test_ergostat_measure_prints_the_number_a_sensor_reads(tmp_path, capsys):
    from ergostat.cli import main
    p, _ = queue_project(tmp_path, text=MEASURED)
    assert main(["-C", str(tmp_path), "measure", "fit"]) == 0
    assert float(capsys.readouterr().out) == pytest.approx(ms.measure(p, "fit"), rel=1e-4)


# ---- 3. the judge, and the policy

def test_the_policy_is_read_from_the_main_file(tmp_path):
    def policy(extra):
        (tmp_path / "ergostat.yaml").write_text(QUEUE + extra)
        return read(tmp_path / "ergostat.yaml")
    spec, _ = policy("")
    assert spec.improve.accept == {"parameter": "owner", "equation": "owner", "structure": "owner"}   # never automatic by default
    spec, probs = policy("improve:\n  accept:\n    parameter: auto\n  threshold: 5%\n  hold-out: 3m\n")
    assert spec.improve.accept["parameter"] == "auto" and spec.improve.accept["structure"] == "owner"
    assert spec.improve.threshold == pytest.approx(0.05) and spec.improve.hold_out == 180
    assert policy("improve:\n  accept: auto\n")[0].improve.accept == dict.fromkeys(("parameter", "equation", "structure"), "auto")
    for bad in ("improve:\n  accept: always\n", "improve:\n  accept:\n    loops: auto\n", "improve:\n  threshold: 150%\n",
                "improve:\n  speed: 3\n"):
        assert [x for x in policy(bad)[1] if x.level == "error"], bad
    (tmp_path / "more.yaml").write_text("improve:\n  accept: auto\n")
    (tmp_path / "ergostat.yaml").write_text(QUEUE + "include: [more.yaml]\n")
    assert any(x.code == "improve-in-include" for x in read(tmp_path / "ergostat.yaml")[1])


def proposed_ago(p, x: dict, hours: float) -> None:
    """Pretend a candidate was proposed some hours ago, so the record since is its record held out."""
    props = pr.stored(p)
    props[x["id"]]["created"] = props[x["id"]]["proposed"] = time.time() - hours * 3600
    pr.save(p, props)


def test_a_candidate_is_tested_until_its_hold_out_then_kept_when_better_in_every_window(tmp_path):
    p, _ = long_queue(tmp_path)
    got = im.submit(p, "improver", raw(3))
    first = jd.run(p, "judge")
    assert first["testing"] == 1 and not first["verdicts"] and first["waiting"]     # no record after it yet
    assert p.events.query(type="model.testing")[-1]["item"] == f"proposal/{got['id']}"
    proposed_ago(p, got, 8)
    out = jd.run(p, "judge")
    assert out["kept"] == 1 and out["accepted"] == 0                                # the owner's, by default
    x = pr.stored(p)[got["id"]]
    assert x["status"] == "pending" and x["verdict"]["verdict"] == "kept" and len(x["verdict"]["windows"]) == 7
    assert all(w["after"] < w["before"] for w in x["verdict"]["windows"])
    e = next(y for y in rv.entries(p, p.model.spec) if y["id"] == got["id"])
    assert e["verdict"]["verdict"] == "kept" and e["verdict"]["windows"] == 7
    assert p.events.query(type="model.kept")[-1]["data"]["why"].startswith("better in every one of 7 windows")
    assert jd.run(p, "judge")["kept"] == 0                                          # judged once


def test_a_kept_parameter_change_is_written_when_the_policy_says_auto(tmp_path):
    p, _ = long_queue(tmp_path, text=QUEUE + "improve:\n  accept:\n    parameter: auto\n")
    got = im.submit(p, "improver", raw(3))
    proposed_ago(p, got, 8)
    out = jd.run(p, "judge")
    assert out["kept"] == 1 and out["accepted"] == 1
    assert "    value: 3          # what we believe" in (tmp_path / "ergostat.yaml").read_text()   # the smallest edit
    ev = p.events.query(type="model.accepted")[-1]
    assert ev["item"] == f"proposal/{got['id']}" and ev["source"] == "judge"
    assert ev["data"]["policy"] == "improve.accept.parameter: auto" and ev["data"]["why"].startswith("the judge kept it")
    assert ev["data"]["proposed_by"] == "improver" and ev["data"]["fit_after"]["nmse"] < ev["data"]["fit_before"]["nmse"]
    assert ev["data"]["reason"] == "the replay of queue runs high"


def test_a_structural_change_waits_for_the_owner_even_kept(tmp_path):
    text = LEAKS
    p, _ = long_queue(tmp_path, text=text + "improve:\n  accept:\n    parameter: auto\n")
    got = im.submit(p, "x", {"kind": "structure", "parts": ["flow.leaks"], "title": "leaks at once",
                             "edit": {"file": "ergostat.yaml", "replace": "    driven-by: +flow.arrivals",
                                      "with": "    driven-by:\n      - {cause: +flow.arrivals, instant: true}\n      - +stock.queue"},
                             "reasons": [{"says": "a rate on a rate", "evidence": "finding:rate-driven-by-rate@flow.leaks"}]})
    proposed_ago(p, got, 8)
    out = jd.run(p, "judge")
    x = pr.stored(p)[got["id"]]
    assert out["kept"] == 1 and out["accepted"] == 0 and x["status"] == "pending"
    assert "answers 2 findings" in x["verdict"]["why"]                              # the fit cannot see it; check can


def test_a_change_worse_on_the_record_held_out_is_dropped_with_the_windows(tmp_path):
    p, _ = long_queue(tmp_path, text=QUEUE.replace(LINE, LINE.replace("2 ", "3 ", 1)))
    got = im.submit(p, "x", {**raw(), "edit": {"file": "ergostat.yaml", "replace": LINE.replace("2 ", "3 ", 1),
                                               "with": LINE.replace("2 ", "2.97", 1)}})
    assert got["status"] == "proposed", got                                        # worse, but by a trifle: proposed
    proposed_ago(p, got, 8)
    out = jd.run(p, "judge")
    x = pr.stored(p)[got["id"]]
    assert out["dropped"] == 1 and x["status"] == "dropped" and x["verdict"]["why"].startswith("worse in")
    assert got["id"] not in {y["id"] for y in pr.pending(p)}
    assert p.events.query(type="model.dropped")[-1]["data"]["scaled_error"]


def test_a_candidate_whose_model_changed_under_it_is_dropped(tmp_path):
    p, _ = long_queue(tmp_path)
    im.submit(p, "x", raw(3))
    (tmp_path / "ergostat.yaml").write_text(QUEUE.replace("    estimate: true\n", ""))
    p.model = mdl.load(tmp_path)
    out = jd.run(p, "judge")
    assert out["dropped"] == 1 and "changed since" in out["verdicts"][0]["why"]


def test_the_verdict_rules():
    w = lambda b, a: {"since": 0, "until": 600, "before": b, "after": a, "change": (b - a) / b}   # noqa: E731
    assert jd.decide([w(1, 0.9)] * 3, 0.02, 0, 0, 600, 600)[0] == "kept"
    assert jd.decide([w(1, 0.9), w(1, 0.9), w(1, 0.99)], 0.02, 0, 0, 600, 600)[1].startswith("not consistently better")
    assert jd.decide([w(1, 0.9), w(1, 0.9), w(1, 1.1)], 0.02, 0, 0, 600, 600)[1].startswith("worse in 1 of 3")
    assert jd.decide([w(1, 1.0)] * 3, 0.02, 2, 0, 600, 600) == ("kept", jd.decide([w(1, 1.0)] * 3, 0.02, 2, 0, 600, 600)[1])
    assert jd.decide([w(1, 1.0)] * 3, 0.02, 2, 1, 600, 600)[0] == "dropped"           # it answers two and makes one
    assert jd.decide([w(1, 0.9)] * 2, 0.02, 0, 0, 600, 600) is None                   # too few windows yet: testing
    assert jd.decide([], 0.02, 0, 0, 3600, 600)[1].startswith("too little record")
    assert jd.windows(0, 3600) == [(0, 3600), (0, 1800), (1800, 3600), (0, 900), (900, 1800), (1800, 2700), (2700, 3600)]
    assert jd.windows(0, 100) == [(0, 100)]                                          # halves under a minute are not judged


def test_the_judges_lines_are_what_it_moved_on_its_blocks_ports(tmp_path):
    (tmp_path / "ergostat.yaml").write_text(QUEUE + textwrap.dedent("""\
        blocks:
          judge:
            type: program
            run: echo
            every: 1m
            out:
              kept: flow.arrivals
        """))
    spec, _ = read(tmp_path / "ergostat.yaml")
    got = {"testing": 1, "kept": 2, "dropped": 0, "accepted": 0}
    assert jd.lines(spec, "judge", got) == [{"out": "kept", "moved": 2}]
    assert jd.lines(spec, "nobody", got) == []


def test_ergostat_judge_prints_its_blocks_lines(tmp_path, capsys, monkeypatch):
    from ergostat.cli import main
    p, _ = long_queue(tmp_path, text=QUEUE + textwrap.dedent("""\
        blocks:
          judge:
            type: program
            run: echo
            every: 1m
            out:
              testing: flow.arrivals
        """))
    im.submit(p, "x", raw(3))
    monkeypatch.setenv("ERGOSTAT_BLOCK", "judge")
    assert main(["-C", str(tmp_path), "judge"]) == 0
    assert json.loads(capsys.readouterr().out.strip()) == {"out": "testing", "moved": 1}
    monkeypatch.delenv("ERGOSTAT_BLOCK")
    assert main(["-C", str(tmp_path), "improve"]) == 0
    assert Project(mdl.load(tmp_path)).events.query(type="model.testing")
