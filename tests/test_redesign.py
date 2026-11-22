"""Redesign beside refinement (SPEC §12e, *Redesign*): a change set of many coordinated edits made in order on a scratch
copy (numbers/changeset.py), judged as a whole by a scorecard (numbers/scorecard.py), kept as one ergostat.model-change
of kind redesign (numbers/redesign.py), made by the redesigner over rounds on its scratch copy (numbers/redesigner.py),
never written without the owner unless accept: {redesign: auto}, and drawn as it would leave the model."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat.numbers import changeset as cs
from ergostat.numbers import judge as jd
from ergostat.numbers import proposals as pr
from ergostat.numbers import redesign as rd
from ergostat.numbers import redesigner as rdr
from ergostat.numbers import scorecard as sc
from ergostat.spec import read
from ergostat.store import Project


def thirteen(dest: Path):
    """A model shaped like the owner's 13 disconnected stocks (as the verification harness on ``selfimprove`` writes
    it): one kind through 13 states, a stock a state, every move written as an outflow to a cloud, a goal and a block a
    step. Returns whether a spec has them chained."""
    states = [f"s{i:02d}" for i in range(1, 14)]
    lines = ["name: thirteen", "items:", "  request:", "    id: request/*", "    description: a request worked through 13 steps",
             f"    states: [{', '.join(states)}, done]", "    on:"]
    lines += [f"      request.{s}-reached: {s}" for s in states] + ["      request.finished: done"]
    lines += ["stocks:"]
    for s in states:
        lines += [f"  {s}-waiting:", "    unit: requests", f"    description: requests at step {s}",
                  f"    sensor: {{items: request, state: {s}, every: 5s}}"]
    lines += ["flows:", "  arrivals:", "    to: s01-waiting", "    description: requests arriving",
              "    sensor: {items: request, entering: s01, over: 10m}"]
    for i, s in enumerate(states):
        nxt = states[i + 1] if i + 1 < len(states) else "done"
        lines += [f"  {s}-worked:", f"    from: {s}-waiting", f"    description: requests leaving step {s}",
                  f"    driven-by: +stock.{s}-waiting", f"    sensor: {{items: request, entering: {nxt}, over: 10m}}"]
    lines += ["goals:"]
    for s in states:
        lines += [f"  {s}-clear:", f"    stock: {s}-waiting", '    hold: "<= 0"', f"    description: nothing waits at {s}"]
    lines += ["blocks:"]
    for i, s in enumerate(states):
        nxt = states[i + 1] if i + 1 < len(states) else "done"
        lines += [f"  step-{s}:", "    type: program", f"    description: works step {s}", f"    goal: {s}-clear",
                  "    run: python3 -c pass", f"    takes: {{kind: request, at: {s}, to: [{nxt}]}}", f"    out: flow.{s}-worked"]
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "ergostat.yaml").write_text("\n".join(lines) + "\n\nuses:\n  modelling: {use: modelling}\n", encoding="utf-8")

    def chained(spec):
        return all(spec.flows[f"{s}-worked"].target == (f"{states[i + 1]}-waiting" if i + 1 < len(states) else None)
                   for i, s in enumerate(states))
    return chained


PIECES = """\
name: t
items:
  alert:
    id: alert/*
    description: an alert from the pager
    states: [new, triaged, closed]
    on:
      alert.fired: new
      alert.triaged: triaged
      alert.closed: closed
stocks:
  triage:
    sensor: {items: alert, state: new, every: 2s}
  investigate:
    unit: alerts
    description: alerts triaged, not yet closed
    sensor: {items: alert, state: triaged, every: 2s}
flows:
  in:
    to: triage
    description: alerts from the pager
    sensor: {run: python3 bin/watch.py, every: 2s, description: the pager}
  triaged:
    from: triage
    description: alerts triaged
    sensor: {items: alert, entering: triaged}
  closed:
    from: investigate
    description: alerts closed
    sensor: {items: alert, entering: closed}
goals:
  triage-ok:
    stock: triage
    hold: "<= 0"
    tolerance: 0
    description: nothing waits for triage
blocks:
  step:
    type: program
    description: triages each alert
    run: python3 bin/step.py
    goal: triage-ok
    takes: {kind: alert, at: new, to: [triaged]}
    out: flow.triaged
"""

def project(d: Path, text: str = PIECES) -> Project:
    d.mkdir(parents=True, exist_ok=True)
    (d / "bin").mkdir(exist_ok=True)
    (d / "bin" / "watch.py").write_text("print(0)\n")
    (d / "bin" / "step.py").write_text("print('{}')\n")
    (d / "ergostat.yaml").write_text(textwrap.dedent(text))
    m = mdl.load(d)
    assert not [x for x in m.problems if x.level == "error"], [str(x) for x in m.problems]
    return Project(m)


JUDGE = "\n  judge:\n    type: judge\n    every: 30s\n    accept: ACCEPT\n"
ENTER = "    sensor: {items: alert, entering: triaged}\n"
BUSY = PIECES.replace(ENTER, "    to: investigate\n" + ENTER, 1) + "AUXILIARIES"   # chained; busy: driven by nothing
BUSY_AUX = "auxiliaries:\n  busy:\n    unit: alerts\n    description: alerts being looked at\n"
READ = [{"part": "auxiliary.busy", "set": {"driven-by": ["+stock.investigate"], "equation": "stock.investigate"},
         "why": "what it reads"}]                      # better, and it rewires nothing, removes nothing, changes no control


def busy(d: Path, accept: str) -> Project:
    return project(d, BUSY.replace("AUXILIARIES", JUDGE.replace("ACCEPT", accept).lstrip("\n") + BUSY_AUX))


CHAIN = [
    {"rename": "stock.triage", "to": "new-alerts", "why": "a quantity, not a step"},
    {"part": "stock.new-alerts", "set": {"unit": "alerts", "description": "alerts not yet triaged"}, "why": "its unit"},
    {"part": "flow.triaged", "set": {"to": "investigate"}, "why": "a move from one state to the next is a flow between them"},
]


def test_a_change_set_is_made_in_order_on_a_scratch_copy_and_never_on_disk(tmp_path):
    p = project(tmp_path / "m")
    disk = p.model.path.read_text()
    s = cs.Scratch(p)
    for e in CHAIN:
        s.apply(e)
    assert p.model.path.read_text() == disk                       # the files as they were
    t = s.texts[str(p.model.path.resolve())]
    assert "  new-alerts:\n    formerly: [triage]" in t           # renamed, its history kept
    assert "to: new-alerts" in t and "stock: new-alerts" in t      # every reference followed
    assert "triage:" not in t.replace("triage-ok:", "")
    assert not s.errors()
    # the change set is one diff from the files as they are, and applying it gives exactly the scratch copy
    from ergostat.numbers import yamledit as ye
    assert ye.apply_together(s.edits())[str(p.model.path.resolve())] == t
    assert [x["why"] for x in s.done] == [e["why"] for e in CHAIN]


def test_an_edit_that_cannot_be_made_leaves_the_copy_as_it_was_and_says_why(tmp_path):
    p = project(tmp_path / "m")
    s = cs.Scratch(p)
    s.apply(CHAIN[0])
    before = dict(s.texts)
    with pytest.raises(cs.ChangeSetError, match="not a part"):
        s.apply({"remove": "stock.nothing-here"})
    with pytest.raises(cs.ChangeSetError, match="found 0 times"):
        s.apply({"file": "ergostat.yaml", "replace": "  no such line:", "with": "  x:"})
    assert s.texts == before


def test_an_error_mid_way_does_not_stop_edits_to_other_parts(tmp_path):
    p = project(tmp_path / "m")
    s = cs.Scratch(p)
    s.apply({"part": "flow.closed", "set": {"unit": "alerts/h"}})      # an error until a later edit puts it right
    assert s.errors()
    s.apply({"part": "stock.investigate", "set": {"description": "alerts being looked at"}})
    s.apply({"part": "flow.closed", "set": {"unit": "alerts"}})
    assert not s.errors()


def test_a_file_written_whole_keeps_the_history_of_the_parts_it_renames(tmp_path):
    p = project(tmp_path / "m")
    s = cs.Scratch(p)
    text = p.model.path.read_text().replace("  triage:\n", "  new-alerts:\n").replace("to: triage", "to: new-alerts") \
        .replace("from: triage", "from: new-alerts").replace("stock: triage", "stock: new-alerts")
    s.apply({"file": "ergostat.yaml", "write": text, "why": "rewritten"})
    assert s.keep_names() == ["stock.triage → stock.new-alerts"]
    after, _ = s.compiled()
    assert cs.parts_changed(p.model.spec, after)["renamed"] == ["stock.triage → stock.new-alerts"]


def test_the_scorecard_counts_what_a_modeller_cares_about(tmp_path):
    p = project(tmp_path / "m")
    s = cs.Scratch(p)
    for e in CHAIN:
        s.apply(e)
    _, before = read(p.model.path)
    after, problems = s.compiled()
    card = sc.score(p, p.model.spec, before, after, problems)
    assert card["pieces"]["before"] == 1 and card["pieces"]["after"] == 0
    assert "outflow-not-chained@flow.triaged" in card["findings"]["resolved"]
    assert not card["findings"]["introduced"]
    assert "no-unit@stock.new-alerts" in card["findings"]["resolved"]         # a finding, not a note (no request)
    assert "no-description@stock.new-alerts" in card["craft"]["closed"]
    assert card["craft"]["opened"] == ["no-equation@flow.triaged"]      # a flow between stocks now: it wants an equation
    assert card["parts"]["renamed"] == ["stock.triage → stock.new-alerts"]
    assert card["verdict"] == "better", card["why"]
    assert any(x.startswith("verdict") for x in sc.lines(card))


def test_the_verdict_is_mixed_when_a_measure_gets_worse_and_lost_behaviour_counts_against():
    base = {"findings": {"before": 3, "after": 1, "resolved": ["a@x", "b@y"], "introduced": []},
            "pieces": {"before": 1, "after": 0, "by_kind": {}},
            "coherence": {"kinds": {}, "mismatches_before": 0, "mismatches_after": 0, "resolved": [], "introduced": []},
            "craft": {"before": 0, "after": 0, "closed": [], "opened": []},
            "fit": {"worse": False, "says": "0.1 → 0.1, the same"}, "lost": [], "parts": {}}
    assert sc.verdict(base)[0] == "better"
    worse = json.loads(json.dumps(base))
    worse["fit"] = {"worse": True, "says": "0.1 → 0.5, 5× worse"}
    v, why, _ = sc.verdict(worse)
    assert v == "mixed" and "fit worse" in why
    lost = json.loads(json.dumps(base))
    lost["lost"] = ["stock.x: its replay followed the record"]
    assert sc.verdict(lost)[0] == "mixed"
    assert sc.verdict(lost)[2] < sc.verdict(base)[2]
    nothing = json.loads(json.dumps(base))
    nothing["findings"] = {"before": 0, "after": 0, "resolved": [], "introduced": []}
    nothing["pieces"] = {"before": 0, "after": 0, "by_kind": {}}
    assert sc.verdict(nothing)[0] == "no better"


def test_the_thirteen_disconnected_stocks_are_chained_by_one_change_set(tmp_path):
    chained = thirteen(tmp_path / "thirteen")
    p = Project(mdl.load(tmp_path / "thirteen"))
    states = [f"s{i:02d}" for i in range(1, 14)]
    edits = [{"part": f"flow.{s}-worked", "set": {"to": f"{states[i + 1]}-waiting"}, "why": f"items move on from {s}"}
             for i, s in enumerate(states[:-1])]
    got = rd.submit(p, "redesigner", {"title": "one chain", "summary": "the 13 states chained", "edits": edits})
    assert got["status"] == "proposed", got["why"]
    card = got["scorecard"]
    assert card["pieces"]["before"] == 12 and card["pieces"]["after"] == 0
    assert card["findings"]["after"] == 0 and card["verdict"] == "better", sc.lines(card)
    assert "12 craft notes more" in card["why"]                        # said: each new flow between stocks wants an equation
    x = pr.stored(p)[got["id"]]
    assert x["kind"] == "redesign" and len(x["redesign"]["edits"]) == 12
    after = mdl.load(tmp_path / "thirteen")                      # nothing written yet
    assert after.spec.flows["s01-worked"].target is None
    pr.accept(p, got["id"], {"at": 0, "window": 600}, by="owner")
    p.model = mdl.load(tmp_path / "thirteen")
    assert chained(p.model.spec)
    _, problems = read(p.model.path)
    assert not sc.findings(problems)


def test_a_redesign_is_judged_by_its_scorecard_and_waits_for_the_owner_unless_promoted_by_name(tmp_path):
    for accept, written in (("auto", False), ("owner", False), ("{redesign: auto}", True)):
        p = busy(tmp_path / accept.strip("{}").replace(": ", "-"), accept)
        assert p.model.spec.improve.accept["redesign"] == ("auto" if written else "owner")
        got = rd.submit(p, "redesigner", {"title": "busy read", "edits": READ})
        assert got["status"] == "proposed", got["why"]
        out = jd.run(p, "judge")
        assert out["passed"] == 1
        x = pr.stored(p)[got["id"]]
        assert x["state"] == ("accepted" if written else "passed")
        assert x["verdict"]["verdict"] == "passed" and x["scorecard"]["verdict"] == "better"


def test_at_most_one_redesign_waits_for_each_system(tmp_path):
    p = project(tmp_path / "m")
    assert rd.submit(p, "redesigner", {"title": "one", "edits": CHAIN})["status"] == "proposed"
    again = rd.submit(p, "redesigner", {"title": "two", "edits": CHAIN[:2]})
    assert again["status"] == "not-proposed" and "waiting already" in again["why"]
    rd.ask(p, None)
    assert rd.plan(p, "ask")["system"] is None                   # asked, but one waits: said, and nothing made


def test_the_owners_ask_comes_first_and_is_taken_up_once(tmp_path):
    p = project(tmp_path / "m")
    assert rd.plan(p, "ask")["system"] is None                   # ask: only what the owner asked
    rd.ask(p, None)
    got = rd.plan(p, "ask")
    assert got == {"system": "model", "why": ["the owner asked"], "asked": True}
    rd.ran(p, "model", {"result": "started"})
    assert rd.plan(p, "ask")["system"] is None
    with pytest.raises(ValueError):
        rd.ask(p, "no-such-system")


def _answers(*rounds):
    it = iter(rounds)

    def call(text, model, timeout=None):
        call.prompts.append(text)
        return {"result": json.dumps({"redesign": next(it)}), "usd": 0.01, "tokens_in": 1000, "tokens_out": 200, "seconds": 0.1}
    call.prompts = []
    return call


def test_the_redesigner_works_its_scratch_copy_over_rounds_then_proposes_the_best(tmp_path):
    p = project(tmp_path / "m")
    call = _answers({"title": "chained", "summary": "one chain", "edits": [CHAIN[0], {"remove": "stock.nope"}]},
                    {"title": "later", "edits": CHAIN[1:]})
    out = rdr.run(p, "model", ["asked"], budget=1.0, rounds=3, call=call)
    assert out["result"] == "proposed", out
    assert len(out["rounds"]) == 2                                # done once check and coherence were clean
    assert "edit 2 (remove stock.nope) was not made" in call.prompts[1]   # what went wrong, given back
    assert "Your edits so far" in call.prompts[1]
    assert out["cost"]["usd"] == pytest.approx(0.02) and out["cost"]["calls"] == 2
    x = pr.stored(p)[out["id"]]
    assert x["title"] == "chained"                               # the first round's: the change set as a whole
    assert x["redesign"]["cost"]["usd"] == pytest.approx(0.02)
    line = rdr.result_line(out["cost"])
    from ergostat.costs import ai
    assert ai.is_result(line) and line["total_cost_usd"] == pytest.approx(0.02)


def test_the_redesigner_stops_at_its_budget(tmp_path):
    p = project(tmp_path / "m")
    call = _answers({"edits": CHAIN[:1]}, {"edits": CHAIN[1:]})
    out = rdr.run(p, "model", [], budget=0.02, rounds=3, call=call)     # room for one call at its dearest, not two
    assert out["cost"]["calls"] == 1 and any("budget" in json.dumps(r) for r in out["rounds"])


def test_a_report_in_the_redesigners_answer_is_passed_on_for_the_block_to_print(tmp_path):
    p = project(tmp_path / "m")

    def call(text, model, timeout=None):
        return {"result": json.dumps({"redesign": None, "why": "the format cannot say it"}) + "\n"
                + json.dumps({"report": "a flow's rate cannot read another flow's delayed value"}), "usd": 0.01}
    out = rdr.run(p, "model", [], budget=1.0, rounds=1, call=call)
    assert out["reports"] == ["a flow's rate cannot read another flow's delayed value"]
    assert '{"report": "<what ergostat could not express' in rdr.guides()      # the guide says so


def test_the_prompt_carries_the_model_check_coherence_the_record_and_the_guides(tmp_path):
    p = project(tmp_path / "m")
    text = rdr.prompt(p, cs.Scratch(p), "model", ["the owner asked"])
    for want in ("one change set", "outflow-not-chained@flow.triaged", "## Coherence", "## The record", "Review checklists",
                 "name: t"):
        assert want in text, want


def test_a_proposal_is_drawn_as_it_would_leave_the_model(tmp_path):
    from ergostat.web.server import Live, api
    p = project(tmp_path / "m")
    got = rd.submit(p, "redesigner", {"title": "chained", "edits": CHAIN})
    live = Live(p)
    for view in ("dynamics", "blocks"):
        g = api(live, "graph", {"view": [view], "open": ["*"], "proposal": [got["id"]]})
        assert g["proposed"]["renamed"] == ["stock.triage → stock.new-alerts"]
        assert "stock.new-alerts" in g["proposed"]["changed"] and "stock.new-alerts" in g["corr"]["parts"]
        assert "_model" not in g
        plain = api(live, "graph", {"view": [view], "open": ["*"]})
        assert "proposed" not in plain and "stock.triage" in plain["corr"]["parts"]   # the model as it is, untouched
    q = api(live, "fit", {})
    e = next(x for x in q["queue"] if x["id"] == got["id"])
    assert e["kind"] == "redesign" and e["redesign"]["scorecard"]["verdict"] == "better"
    assert [x["why"] for x in e["redesign"]["edits"]] == [c["why"] for c in CHAIN]
    assert q["redesigns"]["systems"] == ["model"]


def test_while_a_redesign_is_being_made_the_judge_writes_nothing_on_its_own(tmp_path):
    p = busy(tmp_path / "m", "{redesign: auto}")
    got = rd.submit(p, "redesigner", {"title": "busy read", "edits": READ})
    rd.ran(p, "model", {"result": "started"})
    assert rd.running(p)
    out = jd.run(p, "judge")
    assert out["passed"] == 1 and out["accepted"] == 0 and pr.stored(p)[got["id"]]["state"] == "passed"
    rd.ran(p, "model", {"result": "proposed"})
    assert not rd.running(p)
    assert jd.run(p, "judge")["accepted"] == 1


def test_the_record_holds_no_runs_of_a_block_the_change_set_adds(tmp_path):
    p = project(tmp_path / "m")
    got = sc.coherence(p, p.model.spec, [], 0, 1e12, {"block.new-step"})
    assert got.get("unseen") == []                               # nothing on this record; the rule is only for new blocks
    assert "declared-not-seen-acting" in sc.UNSEEN


def test_a_promoted_redesign_is_written_first_and_alone(tmp_path):
    from ergostat.numbers import improve as im
    p = busy(tmp_path / "m", "{description: auto, redesign: auto}")
    words = im.submit(p, "modeller", {"kind": "description", "parts": ["stock.triage"], "title": "described",
                                       "edit": {"part": "stock.triage", "set": {"description": "alerts not yet triaged"}},
                                       "reasons": [{"says": "it had none", "evidence": "finding:no-description@stock.triage"}]})
    assert words["status"] == "proposed", words["why"]
    got = rd.submit(p, "redesigner", {"title": "busy read", "edits": READ})
    out = jd.run(p, "judge")
    assert out["accepted"] == 1 and pr.stored(p)[got["id"]]["state"] == "accepted"
    assert pr.changes(p)[words["id"]][0] in ("passed", "checked")   # not written in the same pass; carried, not lost


def test_a_renamed_part_says_formerly_and_not_inferred(tmp_path):
    p = project(tmp_path / "m")
    got = rd.submit(p, "redesigner", {"title": "chained", "edits": CHAIN + [
        {"add": "parameters", "name": "time-to-triage", "set": {"value": "5m", "estimate": True, "description": "a guess"}}]})
    diff = pr.stored(p)[got["id"]]["edit"]["diff"]
    lines = diff.split("\n")
    at = next(i for i, x in enumerate(lines) if x.strip() == "+   new-alerts:")
    assert "inferred" not in lines[at + 1] and "formerly" in diff
    assert f"inferred: ergostat.model-change/{got['id']}" in diff          # the parameter it adds says so


def lab_model(subsystems: bool = False) -> str:
    """System ``lab``: two chains with no link between them (``system-splits``), read across its boundary by ``other``'s
    watcher at ten points (``interface`` on both); with ``subsystems``, ``lab`` holds ``left`` (no description:
    ``purpose``) and ``right``."""
    from .test_architecture import _chain, _model
    sys_ = {"lab": "the lab's two queues", "other": "watches the lab"}
    a, b = _chain("a", 3, "left" if subsystems else "lab"), _chain("b", 3, "right" if subsystems else "lab")
    reads = ", ".join([f"+stock.a{i}" for i in (1, 2, 3)] + [f"+stock.b{i}" for i in (1, 2, 3)]
                      + ["+flow.a1-out", "+flow.a2-out", "+flow.b1-out", "+flow.b2-out"])
    text = _model(sys_, a, b) + ("  watch: {type: program, run: 'echo 1', in: [" + reads + "], out: flow.o-in, system: other}\n")
    text = text.replace("flows:\n", "flows:\n  o-in: {to: o1, system: other}\n").replace(
        "stocks:\n", "stocks:\n  o1: {unit: items, system: other, sensor: {manual: true}}\n")
    if subsystems:
        text = text.replace("systems:\n", "systems:\n  left: {within: lab}\n  right: {description: the right queue, within: lab}\n")
    return text


def test_a_systems_own_architecture_notes_are_in_its_redesign_prompt(tmp_path):
    p = project(tmp_path / "m", lab_model())
    notes = {f"{x.code}@{x.about}" for x in p.model.problems}
    assert {"system-splits@system.lab", "interface@system.lab", "interface@system.other"} <= notes, notes
    text = rdr.prompt(p, cs.Scratch(p), "lab", ["asked"])
    check = text.split("## What check finds", 1)[1].split("\n## ", 1)[0]
    assert "system-splits@system.lab" in check and "interface@system.lab" in check
    assert "interface@system.other" not in text                        # another system's note: not this redesign's
    from ergostat.numbers import redesign_due as due
    spec = p.model.spec
    assert all(due._in(spec, "model", r) for r in ("system.lab", "system.nope", "stock.a1", "goal.b1-short"))
    assert not due._in(spec, "lab", "system.other") and due._in(spec, "lab", "system.lab")


def test_a_subsystems_note_is_in_its_parents_redesign_prompt(tmp_path):
    p = project(tmp_path / "m", lab_model(subsystems=True))
    assert "purpose@system.left" in {f"{x.code}@{x.about}" for x in p.model.problems}
    assert "purpose@system.left" in rdr.prompt(p, cs.Scratch(p), "lab", ["asked"])
    assert "purpose@system.left" not in rdr.prompt(p, cs.Scratch(p), "right", ["asked"])


def test_the_prompt_says_the_units_size_interface_and_subsystems(tmp_path):
    from ergostat.spec import architecture as ar
    p = project(tmp_path / "m", lab_model(subsystems=True))
    spec = p.model.spec
    text = rdr.prompt(p, cs.Scratch(p), "lab", ["asked"])
    arch = text.split("## Its architecture\n", 1)[1].split("\n## ", 1)[0]
    assert f"size: {ar.size_said(ar.size(spec, 'lab'))}" in arch
    assert "- out, signal: stock.a1 (peers: block.watch)" in arch, arch     # lab's ports, not other's
    assert "- in, signal: block.watch" not in arch
    assert "its subsystems: left, right" in arch and "nearly decomposable" in arch
    whole = rdr.prompt(p, cs.Scratch(p), "model", ["asked"]).split("## Its architecture\n", 1)[1].split("\n## ", 1)[0]
    for s in ("lab", "other"):
        assert f"- system {s}: {ar.size_said(ar.size(spec, s))}" in whole
    assert len([x for x in rdr.architecture(spec, "lab") if x.startswith(("- out", "- in"))]) <= rdr.PORTS
