"""Improving the model as a loop (SPEC §12e): every change to the model an item of the built-in kind
ergostat.model-change, the record its only store (numbers/proposals.py); a propose line from any block, checked
the same way whoever made it (numbers/improve.py); ergostat's built-in measures, read by sensors
(numbers/measures.py); the judge, a built-in block, testing each change on the record after it, and its
acceptance policy (numbers/judge.py)."""

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
from ergostat.spec import items as its
from ergostat.spec import read
from ergostat.store import Project

from .test_numbers import QUEUE, queue_project

LINE = "    value: 2          # what we believe"
LEAKS = QUEUE + "  leaks:\n    from: queue\n    driven-by: +flow.arrivals\n"     # a rate driven by a rate
KIND = "ergostat.model-change"


def judge_block(**policy) -> str:
    keys = "".join(f"    {k}: {v}\n" for k, v in policy.items())
    return "blocks:\n  judge:\n    type: judge\n" + keys


def value_edit(v) -> dict:
    return {"file": "ergostat.yaml", "replace": LINE, "with": LINE.replace("2 ", f"{v} ", 1)}


def raw(v=3, **more) -> dict:
    return {"kind": "parameter", "parts": ["parameter.k"], "title": f"k is {v}", "edit": value_edit(v),
            "reasons": [{"says": "the replay of queue runs high", "evidence": "fit:stock.queue.um"}],
            "confidence": 0.7, **more}


def long_queue(tmp_path, k_true=3.0, text=QUEUE):
    return queue_project(tmp_path, k_true=k_true, text=text, minutes=600)


AGO = 8 * 3600                    # a change made this long ago has the record since as its record held out


def made_ago(p, by, x, ago=AGO):
    return im.submit(p, by, x, at=time.time() - ago)


def item(p, pid):
    return its.detail(p.events, p.model.spec, f"{KIND}/{pid}")


# ---- the built-in item kind, and the record as the only store

def test_every_project_has_the_built_in_kind_and_none_may_take_its_prefix(tmp_path):
    (tmp_path / "ergostat.yaml").write_text(QUEUE)
    spec, _ = read(tmp_path / "ergostat.yaml")
    k = spec.items[KIND]
    assert k.id == f"{KIND}/*" and k.states[:5] == ["made", "checked", "testing", "passed", "accepted"]
    assert {"refused", "failed", "dismissed", "superseded"} <= set(k.states)
    assert k.on[f"{KIND}.passed"] == "passed"
    (tmp_path / "ergostat.yaml").write_text(QUEUE + "items:\n  mine:\n    id: ergostat.model-change/*\n    states: [a]\n")
    assert any(x.code == "reserved-id" for x in read(tmp_path / "ergostat.yaml")[1])


def test_ergostats_own_proposals_are_items_made_by_ergostat_and_the_queue_reads_them(tmp_path):
    p, snap = queue_project(tmp_path, k_true=3.0)
    got = pr.make(p, snap)
    x = got[0]
    ev = p.events.query(n=None, type=f"{KIND}.*")
    assert [e["type"].rsplit(".", 1)[1] for e in ev] == ["made", "checked"]
    assert ev[0]["source"] == "ergostat" and ev[0]["item"] == f"{KIND}/{x['id']}"
    it = item(p, x["id"])
    assert it["state"] == "checked" and it["fields"]["made_by"] == "ergostat" and it["fields"]["kind"] == "parameter"
    assert [e["id"] for e in rv.entries(p, p.model.spec)] == [x["id"]]          # the queue is the open items
    assert not (p.dir / "proposals.json").exists()                                # the record is the only store
    assert its.listing(p.events, p.model.spec, kind=KIND)                        # Items lists them, as any kind


def test_a_what_if_is_made_by_the_owner(tmp_path):
    p, snap = queue_project(tmp_path, k_true=3.0)
    x = pr.propose_values(p, {"k": "3"}, snap)
    assert item(p, x["id"])["fields"]["made_by"] == "owner"
    assert p.events.query(type=f"{KIND}.made")[-1]["source"] == "owner"


# ---- 1. a propose line, from any block

def test_a_propose_line_from_a_program_block_is_made_by_it_and_checked(tmp_path):
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
    ran = p.events.query(type="agent.ran", item="reviewer")[-1]
    assert ran["data"]["proposed"] == 1 and ran["data"]["not_proposed"] == 1 and ran["data"]["refused"] == 0
    made = p.events.query(n=None, type=f"{KIND}.made")
    assert len(made) == 2 and all(m["source"] == "reviewer" for m in made)
    assert all(m["causedby"] == p.events.query(type="agent.started", item="reviewer")[-1]["id"] for m in made)
    x = next(x for x in pr.pending(p) if x.get("made_by") == "reviewer")
    assert x["made_by_rung"] == "program" and x["kind"] == "parameter" and x["parameters"] == {"k": 3.0}
    assert item(p, x["id"])["state"] == "checked"
    e_ = next(y for y in rv.entries(p, p.model.spec) if y["id"] == x["id"])
    assert e_["made_by"] == "reviewer" and e_["by_block"] and e_["what"].endswith("proposed by reviewer")
    assert e_["reasons"][0]["verified"][0].startswith("stock.queue um =")
    gone = im.not_proposed(p)
    assert gone and gone[0]["by"] == "reviewer" and "no reason with evidence" in gone[0]["why"]
    assert item(p, gone[0]["id"])["state"] == "refused"


def test_a_block_may_not_publish_ergostats_events():
    from ergostat.runner import OWN_TYPES
    assert f"{KIND}.made".startswith(OWN_TYPES) and "ergostat.model.changed".startswith(OWN_TYPES)


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
    assert x["reasons"] == [{"says": "a", "evidence": ["fit:total.nmse"], "verified": [x["reasons"][0]["verified"][0]],
                             "supports": [None], "supported": True}]
    assert [r["says"] for r in x["refused_reasons"]] == ["b"]


def test_a_finding_is_evidence_by_its_id(tmp_path):
    p, _ = queue_project(tmp_path, text=LEAKS)
    assert "rate-driven-by-rate@flow.leaks" in im.Evidence(p, p.model.spec).findings()
    got = im.submit(p, "x", {"kind": "structure", "parts": ["flow.leaks"], "title": "leaks at once",
                             "edit": {"file": "ergostat.yaml", "replace": "    driven-by: +flow.arrivals",
                                      "with": "    driven-by:\n      - {cause: +flow.arrivals, instant: true}\n      - +stock.queue"},
                             "reasons": [{"says": "a rate on a rate", "evidence": "finding:rate-driven-by-rate@flow.leaks"}]})
    x = pr.stored(p)[got["id"]]
    assert got["status"] == "proposed" and x["kind"] == "structure"
    assert "rate-driven-by-rate@flow.leaks" in x["findings"]["answered"]


def test_what_cannot_be_made_or_compiled_or_worsens_the_fit_is_refused(tmp_path):
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
    assert len(p.events.query(n=None, type=f"{KIND}.refused")) == len(cases)


def test_the_kind_is_what_the_edit_does_and_the_same_change_is_made_once(tmp_path):
    p, snap = queue_project(tmp_path, k_true=3.0)
    got = im.submit(p, "x", raw(3, kind="structure"))
    assert pr.stored(p)[got["id"]]["kind"] == "parameter"          # values only: a parameter change, whatever it was called
    again = im.submit(p, "y", raw(3))
    assert again["status"] == "not-proposed" and "waiting already" in again["why"] and got["id"] in again["why"]
    pr.make(p, snap)                                               # ergostat's own calibration never lets a block's change go
    assert got["id"] in {x["id"] for x in pr.pending(p)}


def test_a_new_parameter_to_estimate_is_refitted(tmp_path):
    p, snap = long_queue(tmp_path)
    edit = [{"file": "ergostat.yaml", "replace": "    equation: k * stock.queue", "with": "    equation: k2 * stock.queue"},
            {"file": "ergostat.yaml", "replace": "parameters:",
             "with": "parameters:\n  k2:\n    value: 1\n    unit: 1/h\n    estimate: true"}]
    got = im.submit(p, "x", {"kind": "structure", "parts": ["flow.served"], "title": "k2", "edit": edit,
                             "reasons": [{"says": "a rate of its own", "evidence": ["rule:first-order-drain", "fit:stock.queue.r2"]}]})
    x = pr.stored(p)[got["id"]]
    assert got["status"] == "proposed", got
    assert x["refit"] and abs(x["refit"]["values"]["k2"] - 3.0) < 0.3
    assert x["refit"]["fit"]["total"]["nmse"] < x["fit_after"]["total"]["nmse"]    # judged as written; refitted, said beside
    assert f"+     inferred: {KIND}/{got['id']}" in x["edit"]["diff"]          # what a block's change adds is marked inferred
    again = im.submit(p, "y", {"kind": "structure", "parts": ["flow.served"], "title": "k2", "edit": edit,
                               "reasons": [{"says": "a rate of its own", "evidence": ["fit:stock.queue.r2"]}]})
    assert again["status"] == "not-proposed" and got["id"] in again["why"]       # the same edit, though its id differs
    pr.accept(p, got["id"], snap, expect=rv.diff_of(x, p.model.path.parent)["hash"])
    spec, _ = read(p.model.path)
    assert spec.parameters["k2"].inferred == f"{KIND}/{got['id']}" and not spec.parameters["k"].inferred


def test_trial_says_what_would_happen_and_records_nothing(tmp_path):
    p, _ = queue_project(tmp_path)
    got = im.trial(p, raw())
    assert got["would"] == "be proposed" and got["scaled_error_after"] < got["scaled_error_before"]
    assert im.trial(p, raw(40))["would"] == "not be proposed"
    assert not p.events.query(n=None, type=f"{KIND}.*")


def test_the_mcp_server_checks_a_change_and_names_findings_by_id(tmp_path):
    from ergostat.mcp import Server
    queue_project(tmp_path, text=LEAKS)
    s = Server(tmp_path)
    chk = json.loads(s.call("check", {})["content"][0]["text"])
    assert any(x.get("id") == "rate-driven-by-rate@flow.leaks" for x in chk["problems"])
    assert json.loads(s.call("try_change", {"propose": raw()})["content"][0]["text"])["would"] == "be proposed"
    m = json.loads(s.call("measures", {})["content"][0]["text"])
    assert set(m) >= set(ms.READERS) and m["ergostat.model.open-findings"] >= 1


def test_an_ai_block_is_told_how_to_propose():
    from ergostat.spec.engine import AI_FOOTER
    assert '{"propose":' in AI_FOOTER and "evidence" in AI_FOOTER


# ---- 2. the built-in measures

MEASURED = QUEUE + textwrap.dedent("""\
    auxiliaries:
      model-error:
        unit: "1"
        sensor:
          builtin: ergostat.model.fit
          every: 1m
    goals:
      model-fits:
        auxiliary: model-error
        hold: "<= 0.05"
    """)


def test_a_sensor_reads_a_built_in_measure_by_its_reference(tmp_path):
    (tmp_path / "ergostat.yaml").write_text(MEASURED)
    spec, problems = read(tmp_path / "ergostat.yaml")
    assert not [x for x in problems if x.level == "error"]
    s = spec.auxiliaries["model-error"].sensors["main"]
    assert s.builtin == "ergostat.model.fit" and s.run.endswith("-m ergostat -C . measure ergostat.model.fit")
    assert s.measured and s.timeout == 120
    for bad in ("builtin: fit", "builtin: ergostat.model.vibes", "builtin: ergostat.model.fit\n      run: echo 1"):
        (tmp_path / "ergostat.yaml").write_text(MEASURED.replace("builtin: ergostat.model.fit", bad))
        assert [x for x in read(tmp_path / "ergostat.yaml")[1] if x.level == "error"], bad
    for name in ms.READERS:
        (tmp_path / "ergostat.yaml").write_text(MEASURED.replace("ergostat.model.fit", name))
        assert not [x for x in read(tmp_path / "ergostat.yaml")[1] if x.level == "error"], name


def test_the_measures_read_the_model_against_the_record(tmp_path):
    from ergostat.numbers import fit as ft
    p, _ = queue_project(tmp_path, text=MEASURED)
    _, _, got = ft.compute(p, {"at": time.time()})
    assert ms.measure(p, "ergostat.model.fit") == pytest.approx(got["total"]["nmse"], rel=1e-4)
    assert ms.measure(p, "fit") == pytest.approx(ms.measure(p, "ergostat.model.fit"), rel=1e-4)    # by hand, short
    assert 0.0 <= ms.measure(p, "ergostat.model.unexplained") <= 1.0
    assert ms.measure(p, "ergostat.model.open-findings") == sum(1 for x in read(p.model.path)[1] if x.level == "finding")
    assert ms.measure(p, "ergostat.model.unidentified-loops") == 0         # the goal's loop does not close: nothing to identify
    with pytest.raises(ms.MeasureError):
        ms.measure(p, "vibes")


def test_ergostat_measure_prints_the_number_a_sensor_reads(tmp_path, capsys):
    from ergostat.cli import main
    p, _ = queue_project(tmp_path, text=MEASURED)
    assert main(["-C", str(tmp_path), "measure", "ergostat.model.fit"]) == 0
    assert float(capsys.readouterr().out) == pytest.approx(ms.measure(p, "fit"), rel=1e-3)


# ---- 3. the judge, a built-in block, and its policy

def test_the_policy_is_the_judge_blocks(tmp_path):
    def policy(extra):
        (tmp_path / "ergostat.yaml").write_text(QUEUE + extra)
        return read(tmp_path / "ergostat.yaml")
    spec, _ = policy("")
    assert set(spec.improve.accept.values()) == {"owner"} and set(spec.improve.accept) == {   # nothing automatic
        "parameter", "equation", "structure", "description", "unit", "rename", "redesign"}
    assert spec.improve.block is None
    spec, probs = policy(judge_block(accept="{parameter: auto}", threshold="5%", **{"hold-out": "3m"}, windows="[1, 3]"))
    assert not [x for x in probs if x.level == "error"], probs
    assert spec.improve.block == "judge" and spec.blocks["judge"].builtin
    assert spec.improve.accept["parameter"] == "auto" and spec.improve.accept["structure"] == "owner"
    assert spec.improve.threshold == pytest.approx(0.05) and spec.improve.hold_out == 180 and spec.improve.windows == [1, 3]
    every = policy(judge_block(accept="auto"))[0].improve.accept
    assert {k for k, v in every.items() if v != "auto"} == {"rename", "redesign"}   # promoted only by name
    for bad in (judge_block(accept="always"), judge_block(accept="{loops: auto}"), judge_block(threshold="150%"),
                judge_block(windows="[0]"), judge_block(run="echo"), judge_block(out="{kept: flow.arrivals}"),
                judge_block() + "  judge-2:\n    type: judge\n"):
        assert [x for x in policy(bad)[1] if x.level == "error"], bad
    assert [x for x in policy("improve:\n  accept: auto\n")[1] if x.level == "error"]   # the policy is the judge's, not the file's


def test_the_judge_is_on_the_program_rung():
    from ergostat.spec.legacy import to_model
    spec, _ = read_text(QUEUE + judge_block())
    assert to_model(spec, []).agents["judge"].kind == "program"


def read_text(text):
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    (d / "ergostat.yaml").write_text(text)
    return read(d / "ergostat.yaml")


def test_a_change_is_tested_until_its_hold_out_then_passes_when_better_in_every_window(tmp_path):
    p, _ = long_queue(tmp_path, text=QUEUE + judge_block())
    got = im.submit(p, "improver", raw(3))
    first = jd.run(p, "judge")
    assert first["testing"] == 1 and not first["verdicts"] and first["waiting"]     # no record after it yet
    assert item(p, got["id"])["state"] == "testing"
    assert p.events.query(type=f"{KIND}.testing")[-1]["source"] == "ergostat"
    (tmp_path / "w").mkdir()
    p, _ = long_queue(tmp_path / "w", text=QUEUE + judge_block())
    got = made_ago(p, "improver", raw(3))
    out = jd.run(p, "judge")
    assert out["passed"] == 1 and out["accepted"] == 0                              # the owner's, by default
    x = pr.stored(p)[got["id"]]
    assert x["status"] == "pending" and x["state"] == "passed" and len(x["verdict"]["windows"]) == 7
    assert all(w["after"] < w["before"] for w in x["verdict"]["windows"])
    e = next(y for y in rv.entries(p, p.model.spec) if y["id"] == got["id"])
    assert e["verdict"]["verdict"] == "passed" and e["verdict"]["windows"] == 7 and e["state"] == "passed"
    assert jd.run(p, "judge")["passed"] == 0                                        # judged once


def test_ergostats_own_changes_are_judged_too(tmp_path):
    p, snap = long_queue(tmp_path, text=QUEUE + judge_block())
    x = pr.make(p, snap)[0]
    jd.run(p, "judge", at=time.time() + 3 * 3600)                                   # its record held out, three hours on
    assert item(p, x["id"])["state"] in ("testing", "passed", "failed", "inconclusive")


def test_a_passed_parameter_change_is_written_when_the_judge_says_auto(tmp_path):
    p, _ = long_queue(tmp_path, text=QUEUE + judge_block(accept="{parameter: auto}"))
    got = made_ago(p, "improver", raw(3))
    out = jd.run(p, "judge")
    assert out["passed"] == 1 and out["accepted"] == 1
    assert "    value: 3          # what we believe" in (tmp_path / "ergostat.yaml").read_text()   # the smallest edit
    acc = p.events.query(type=f"{KIND}.accepted")[-1]
    assert acc["item"] == f"{KIND}/{got['id']}" and acc["source"] == "judge"      # who decided: the judge's policy
    assert acc["data"]["applied"]["policy"] == "judge judge: accept parameter: auto"
    ch = p.events.query(type="ergostat.model.changed")[-1]
    assert ch["source"] == "ergostat" and ch["data"]["change"] == got["id"] and ch["data"]["made_by"] == "improver"
    assert ch["data"]["version_before"] != ch["data"]["version_after"] and "value: 3" in ch["data"]["diff"]
    assert ch["data"]["fit_after"]["nmse"] < ch["data"]["fit_before"]["nmse"]
    assert ch["data"]["why"].startswith("the judge passed it") and ch["data"]["reason"] == "the replay of queue runs high"
    assert pr.accepted(p)[-1]["proposal"] == got["id"]


def test_accepting_one_change_supersedes_the_others_made_against_the_old_version(tmp_path):
    p, snap = long_queue(tmp_path, text=LEAKS)
    a = im.submit(p, "x", raw(3))
    b = im.submit(p, "x", {"kind": "structure", "parts": ["flow.leaks"], "title": "leaks at once",
                           "edit": {"file": "ergostat.yaml", "replace": "    driven-by: +flow.arrivals",
                                    "with": "    driven-by:\n      - {cause: +flow.arrivals, instant: true}\n      - +stock.queue"},
                           "reasons": [{"says": "a rate on a rate", "evidence": "finding:rate-driven-by-rate@flow.leaks"}]})
    pr.accept(p, a["id"], snap)
    assert item(p, a["id"])["state"] == "accepted" and item(p, b["id"])["state"] == "superseded"
    assert b["id"] not in {x["id"] for x in pr.pending(p)}


def test_a_structural_change_waits_for_the_owner_even_passed(tmp_path):
    p, _ = long_queue(tmp_path, text=LEAKS + judge_block(accept="{parameter: auto}"))
    got = made_ago(p, "x", {"kind": "structure", "parts": ["flow.leaks"], "title": "leaks at once",
                            "edit": {"file": "ergostat.yaml", "replace": "    driven-by: +flow.arrivals",
                                     "with": "    driven-by:\n      - {cause: +flow.arrivals, instant: true}\n      - +stock.queue"},
                            "reasons": [{"says": "a rate on a rate", "evidence": "finding:rate-driven-by-rate@flow.leaks"}]})
    out = jd.run(p, "judge")
    x = pr.stored(p)[got["id"]]
    assert out["passed"] == 1 and out["accepted"] == 0 and x["state"] == "passed"
    v = x["verdict"]                     # the fit cannot see it (its replay is the model's): the scorecard judges it
    assert v["on"] == "structure" and v["scorecard"]["verdict"] == "better" and jd.owners(x), v["why"]


def test_a_change_worse_on_the_record_held_out_fails_with_the_windows(tmp_path):
    p, _ = long_queue(tmp_path, text=QUEUE.replace(LINE, LINE.replace("2 ", "3 ", 1)) + judge_block())
    got = made_ago(p, "x", {**raw(), "edit": {"file": "ergostat.yaml", "replace": LINE.replace("2 ", "3 ", 1),
                                               "with": LINE.replace("2 ", "2.97", 1)}})
    assert got["status"] == "proposed", got                                        # worse, but by a trifle: checked
    jd.run(p, "judge")
    x = pr.stored(p)[got["id"]]
    assert x["state"] in ("failed", "inconclusive") and x["state"] != "passed"     # worse by a trifle, within the noise:
    assert got["id"] not in {y["id"] for y in pr.pending(p)}                        # never passed
    assert p.events.query(type=f"{KIND}.{x['state']}")[-1]["data"]["verdict"]["windows"]


def test_a_change_whose_model_changed_under_it_is_superseded(tmp_path):
    p, _ = long_queue(tmp_path)
    got = im.submit(p, "x", raw(3))
    (tmp_path / "ergostat.yaml").write_text(QUEUE.replace("    estimate: true\n", ""))
    p.model = mdl.load(tmp_path)
    out = jd.run(p, "judge")
    assert out["verdicts"][0] == {"id": got["id"], "verdict": "superseded", "why": "the model changed since it was made"}
    assert item(p, got["id"])["state"] == "superseded"


def test_the_verdict_rules():
    from .test_slowjudge import evidence as w
    assert jd.decide(w(1, 0.9), 0.02, 0, 0, 600, 600)[0] == "kept"
    assert jd.decide(w(1, 0.99), 0.02, 0, 0, 600, 600)[:1] == (None,)              # better, but by less than 2%: more record
    assert jd.decide(w(1, 1.1), 0.02, 0, 0, 600, 600)[1].startswith("worse near what it touches")
    assert jd.decide(w(1, 1.0), 0.02, 2, 0, 600, 600)[0] == "kept"                 # no worse, and answers two findings
    assert jd.decide(w(1, 1.0), 0.02, 2, 1, 600, 600)[0] == "dropped"              # ... but makes one
    assert jd.decide(w(1, 0.9, n=0), 0.02, 0, 0, 600, 600)[:1] == (None,)          # nothing read yet: testing
    assert jd.decide(w(1, 0.9, n=0), 0.02, 0, 0, 3600, 600)[1].startswith("too little record")
    assert jd.windows(0, 3600) == [(0, 3600), (0, 1800), (1800, 3600), (0, 900), (900, 1800), (1800, 2700), (2700, 3600)]
    assert jd.windows(0, 3600, [1, 3]) == [(0, 3600), (0, 1200), (1200, 2400), (2400, 3600)]
    assert jd.windows(0, 100) == [(0, 100)]                                        # halves under a minute are not judged


def test_the_engine_runs_the_judge_and_records_what_it_moved_on_its_ports(tmp_path):
    from ergostat.spec.engine import Engine
    p, _ = long_queue(tmp_path, text=QUEUE + judge_block(**{"every": "1m"}) + "    out:\n      testing: flow.arrivals\n")
    im.submit(p, "x", raw(3))
    e = Engine(p, say=lambda s: None)
    e.judge(p.model.spec.blocks["judge"])
    ran = p.events.query(type="agent.ran", item="judge")[-1]["data"]
    assert ran["testing"] == 1 and ran["moved"] == {"arrivals": 1.0}
    assert p.events.query(type="valve.opened")[-1]["data"]["flow"] == "arrivals"
    assert jd.lines(p.model.spec, "judge", {"testing": 2, "passed": 0, "failed": 0, "accepted": 0}) == \
        [{"out": "testing", "moved": 2}]
    import time
    first = e.judge_next["judge"] - time.monotonic()
    assert 50 < first <= 61                                     # it moved something: again after its every
    e.judge(p.model.spec.blocks["judge"])                       # nothing moved, the change not due: it backs off
    assert e.judge_next["judge"] - time.monotonic() > 61 and e.judge_idle["judge"] == 1
    from ergostat.spec.engine import Said
    Said(e, p.model.spec.blocks["judge"], "run").take({"propose": raw(4)})   # a change proposed: it looks at once
    assert e.judge_next == {}


def test_ergostat_judge_runs_a_pass_by_hand(tmp_path, capsys):
    from ergostat.cli import main
    p, _ = long_queue(tmp_path)
    made_ago(p, "x", raw(3))
    assert main(["-C", str(tmp_path), "judge"]) == 0
    assert "passed" in capsys.readouterr().out
    assert Project(mdl.load(tmp_path)).events.query(type=f"{KIND}.passed")[-1]["source"] == "ergostat"
    assert main(["-C", str(tmp_path), "improve"]) == 0
