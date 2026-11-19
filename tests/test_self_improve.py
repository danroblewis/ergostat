"""The modelling subsystem improves the model (SPEC §12e): what check finds (its findings, the chain's, the craft notes of
spec/craft.py, the coherence mismatches) becomes requests (numbers/requests.py); the rule tier answers what a
mechanical change answers (numbers/rules.py); the AI tier the rest (numbers/modeller.py); the judge decides by class,
and a description, a unit and a rename are judged by check, not by the record."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

from ergostat import model as mdl
from ergostat.numbers import improve as im
from ergostat.numbers import judge as jd
from ergostat.numbers import modeller as md
from ergostat.numbers import proposals as pr
from ergostat.numbers import requests as rq
from ergostat.numbers import rules as ru
from ergostat.spec import read
from ergostat.store import Project

POOR = """\
name: t
items:
  alert:
    id: alert/*
    description: an alert from the pager
    states: [new, triaged, closed]
    on:
      alert.fired: new
      triage.finished: triaged
      alert.closed: closed
stocks:
  new-alerts:
    description: alerts not yet triaged
    sensor: {items: alert, state: new, every: 2s}
  triaged-alerts:
    unit: alerts
    description: alerts triaged, not yet closed
    sensor: {items: alert, state: triaged, every: 2s}
flows:
  alerts-fired:
    to: new-alerts
    description: alerts from the pager
    sensor: {run: python3 bin/watch.py, every: 2s}
  alerts-triaged:
    from: new-alerts
    to: triaged-alerts
    description: triaged as worth a look
    driven-by: +stock.new-alerts
    sensor: {items: alert, entering: triaged}
  alerts-closed:
    from: triaged-alerts
    description: closed
    driven-by: +stock.triaged-alerts
    sensor: {items: alert, entering: closed}
goals:
  triaged-fast:
    stock: new-alerts
    hold: "<= 3"
    description: alerts triaged as they come
    process: {gain: 1, time-constant: 10s}
blocks:
  triage:
    type: program
    description: triages each alert
    run: python3 bin/step.py
    goal: triaged-fast
    takes: {kind: alert, at: new, to: [triaged]}
    out: flow.alerts-triaged
"""


def project(tmp_path: Path, text: str = POOR, bin_text: str | None = None) -> Project:
    (tmp_path / "bin").mkdir(exist_ok=True)
    (tmp_path / "bin" / "watch.py").write_text("print(0)\n")
    (tmp_path / "bin" / "step.py").write_text(bin_text or 'print(\'{"event": "triage.finished"}\')\n')
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    m = mdl.load(tmp_path)
    assert not [x for x in m.problems if x.level == "error"], [str(x) for x in m.problems]
    return Project(m)


def codes(path: Path) -> dict[str, set[str]]:
    _, ps = read(path)
    out: dict[str, set[str]] = {}
    for x in ps:
        if x.level == "note":
            out.setdefault(x.code, set()).add(x.about)
    return out


def test_check_notes_the_craft_and_never_the_parts_a_template_made(tmp_path):
    p = project(tmp_path, POOR + "uses:\n  modelling: {use: modelling}\n")
    got = codes(p.model.path)
    assert got["no-unit"] == {"stock.new-alerts"}
    assert got["no-equation"] == {"flow.alerts-triaged"}            # between two stocks; the outflow to a cloud is not
    assert got["collector-undescribed"] == {"flow.alerts-fired"}
    assert got["event-names-mixed"] == {"items.alert"}
    assert got["queue-goal-tolerance"] == {"goal.triaged-fast"}      # a takes queue held at 3
    assert got["process-not-identified"] == {"goal.triaged-fast"}
    assert "no-description" not in got                                # every part of ours is described, theirs skipped
    _, ps = read(p.model.path)
    assert not [x for x in ps if x.level == "note" and x.about.split(".", 1)[-1] in p.model.spec.stocks
                and getattr(p.model.spec.stocks[x.about.split(".", 1)[-1]].where, "template", None)]


def test_every_finding_becomes_a_request_answered_when_check_no_longer_finds_it(tmp_path):
    p = project(tmp_path)
    got = rq.sync(p)
    have = {(r["code"], r["about"]): r for r in rq.current(p)}
    assert got["raised"] == len(have) and ("no-unit", "stock.new-alerts") in have
    assert have[("no-unit", "stock.new-alerts")]["tier"] == "rule" and have[("no-unit", "stock.new-alerts")]["says"]
    assert ("no-modelling-loop", "model") not in have                   # not a change to the model: the owner's
    text = p.model.path.read_text().replace("    description: alerts not yet triaged\n",
                                             "    description: alerts not yet triaged\n    unit: alerts\n")
    p.model.path.write_text(text)
    p.model = mdl.load(tmp_path)
    got = rq.sync(p)
    assert got["answered"] == 1 and rq.stored(p)[have[("no-unit", "stock.new-alerts")]["id"]]["state"] == "answered"


def test_the_rule_tier_carries_units_writes_a_first_order_outflow_and_renames_events(tmp_path):
    p = project(tmp_path)
    rq.sync(p)
    mine = [r for r in rq.current(p) if r["tier"] == "rule"]
    made, none = ru.propose(p, mine, most=20)
    by = {r["code"]: raw for r, raw in made}
    assert by["no-unit"]["edit"] and "unit: alerts" in json.dumps(by["no-unit"])             # from the stock it flows to
    assert "stock.new-alerts / time-in-new-alerts" in json.dumps(by["no-equation"])
    assert "alert.triaged" in json.dumps(by["event-names-mixed"]) and "step.py" in json.dumps(by["event-names-mixed"])
    assert by["queue-goal-tolerance"]["kind"] == "control"
    for r, raw in made:
        got = im.submit(p, "fixer", raw)
        assert got["status"] == "proposed", (r["code"], got["why"])
    xs = {x["kind"]: x for x in pr.stored(p).values()}
    assert {"unit", "equation", "rename", "control"} <= set(xs)
    assert xs["rename"]["renamed_events"] == {"alert": {"triage.finished": "alert.triaged"}}
    rq.sync(p)
    assert {r["code"] for r in rq.current(p, ("proposed",))} >= {"no-unit", "no-equation", "event-names-mixed"}
    assert none == [] or all(r["tier"] == "rule" for r, _ in none)


def test_the_judge_passes_words_by_check_and_writes_them_as_the_policy_allows_moving_the_rest(tmp_path):
    p = project(tmp_path)
    rq.sync(p)
    made, _ = ru.propose(p, [r for r in rq.current(p) if r["code"] in ("no-unit", "event-names-mixed")], most=20)
    for _, raw in made:
        assert im.submit(p, "fixer", raw)["status"] == "proposed"
    desc = {"kind": "description", "parts": ["goal.triaged-fast"], "title": "goal described",
            "edit": {"part": "flow.alerts-fired", "sensor": "main", "set": {"description": "the pager collector"}},
            "reasons": [{"says": "the collector had none", "evidence": "finding:collector-undescribed@flow.alerts-fired"}]}
    assert im.submit(p, "modeller", desc)["status"] == "proposed"
    spec = p.model.spec
    spec.improve.accept.update({"unit": "auto", "description": "auto"})
    got = jd.run(p)
    assert got["passed"] == 3 and got["accepted"] == 2                # the rename waits: the policy leaves it to the owner
    text = p.model.path.read_text()
    assert "unit: alerts" in text and "description: the pager collector" in text
    p.model = mdl.load(tmp_path)
    left = [x for x in pr.stored(p).values() if x["state"] == "passed"]
    assert [x["kind"] for x in left] == ["rename"]
    pr.accept(p, left[0]["id"], {"at": 0, "window": 600})            # its lines moved with the two written above it
    assert "alert.triaged: triaged" in p.model.path.read_text()
    assert '"alert.triaged"' in (tmp_path / "bin" / "step.py").read_text()
    assert "triage.finished: alert.triaged" in p.model.path.read_text()   # the record's old events still fold


def test_a_rename_of_a_part_updates_every_reference_and_keeps_its_history(tmp_path):
    p = project(tmp_path)
    t0 = 1_700_000_000.0
    for i in range(5):
        p.measurements.add("sensor/new-alerts.main", float(i), at=t0 + i)
    text = p.model.path.read_text()
    new = text.replace("  new-alerts:\n", "  alerts-waiting:\n    formerly: new-alerts\n").replace("to: new-alerts", "to: alerts-waiting") \
        .replace("from: new-alerts", "from: alerts-waiting").replace("+stock.new-alerts", "+stock.alerts-waiting") \
        .replace("stock: new-alerts", "stock: alerts-waiting")
    raw = {"kind": "rename", "parts": ["stock.new-alerts"], "title": "new-alerts renamed",
           "edit": {"file": "ergostat.yaml", "replace": text.rstrip("\n"), "with": new.rstrip("\n")},
           "reasons": [{"says": "a reader looks for the waiting alerts", "evidence": "finding:no-unit@stock.new-alerts"}]}
    got = im.submit(p, "modeller", raw)
    assert got["status"] == "proposed", got["why"]
    x = pr.stored(p)[got["id"]]
    assert x["kind"] == "rename" and x["renames"] == {"stock.new-alerts": "stock.alerts-waiting"}
    jd.run(p)
    pr.accept(p, got["id"], {"at": t0 + 10, "window": 600})
    assert [v for _, v in p.measurements.range("sensor/alerts-waiting.main", 0)] == [0.0, 1.0, 2.0, 3.0, 4.0]
    assert len(p.measurements.range("sensor/new-alerts.main", 0)) == 5          # the old series is left as it was


def test_a_change_that_also_edits_a_program_is_refused_unless_it_only_renames_event_types(tmp_path):
    p = project(tmp_path)
    raw = {"kind": "description", "parts": ["stock.new-alerts"], "title": "x",
           "edit": [{"part": "stock.new-alerts", "set": {"unit": "alerts"}},
                    {"file": "bin/watch.py", "replace": "print(0)", "with": "print(1)"}],
           "reasons": [{"says": "no unit", "evidence": "finding:no-unit@stock.new-alerts"}]}
    got = im.trial(p, raw)
    assert got["would"] == "not be proposed" and "only a rename of event types" in got["why"]


def test_the_ai_tier_gives_each_request_its_neighbourhood_and_proposes_only_what_would_be_proposed(tmp_path):
    p = project(tmp_path)
    rq.sync(p)
    reqs = [r for r in rq.current(p) if r["code"] in ("collector-undescribed", "no-unit")]
    text = md.prompt(p, p.model.spec, reqs)
    assert "finding:collector-undescribed@flow.alerts-fired" in text and "alerts-fired:" in text and "bin/watch.py" in text
    answer = [json.dumps({"propose": {"kind": "description", "parts": ["flow.alerts-fired"], "title": "named",
                                      "edit": {"part": "flow.alerts-fired", "sensor": "main", "set": {"description": "the pager"}},
                                      "reasons": [{"says": "none", "evidence": "finding:collector-undescribed@flow.alerts-fired"}]}}),
              json.dumps({"propose": {"kind": "unit", "parts": ["stock.new-alerts"], "title": "bad",
                                      "edit": {"part": "stock.new-alerts", "set": {"unit": "alerts"}},
                                      "reasons": [{"says": "made up", "evidence": "finding:no-such@stock.x"}]}}),
              json.dumps({"cannot": "no-such-request", "why": "the owner's"})]
    fake = tmp_path / "fake_claude.py"
    fake.write_text("import json, sys\nsys.stdin.read()\nprint(json.dumps({'result': " + repr("\n".join(answer)) +
                    ", 'total_cost_usd': 0.001, 'usage': {'input_tokens': 10, 'output_tokens': 5}}))\n")
    os.environ["ERGOSTAT_AI"] = f"{sys.executable} {fake}"
    try:
        os.chmod(fake, 0o755)
        (tmp_path / "claude").write_text(f"#!/bin/sh\nexec {sys.executable} {fake}\n")
        os.chmod(tmp_path / "claude", 0o755)
        os.environ["ERGOSTAT_AI"] = str(tmp_path / "claude")
        got = md.answer(p, reqs, "haiku")
    finally:
        os.environ.pop("ERGOSTAT_AI", None)
    assert [x["title"] for x in got["proposals"]] == ["named"]
    assert got["cost"]["usd"] > 0 and got["cost"]["calls"] == 2         # the turned-away one was given back once
    assert got["cannot"] and got["cannot"][0]["why"] == "the owner's"


def test_the_template_has_the_tiers_the_ai_tier_only_when_asked(tmp_path):
    (tmp_path / "ergostat.yaml").write_text("name: t\nuses:\n  modelling: {use: modelling}\n")
    spec, ps = read(tmp_path / "ergostat.yaml")
    assert not [x for x in ps if x.level == "error"], [str(x) for x in ps if x.level == "error"]
    assert spec.blocks["fixer"].type == "program" and "modeller" not in spec.blocks
    assert spec.goals["requests-handled"].of.name == "unanswered-requests"
    assert set(spec.improve.accept) >= {"description", "unit", "rename"}
    (tmp_path / "ergostat.yaml").write_text("name: t\nuses:\n  modelling:\n    use: modelling\n    with: {ai: true}\n")
    spec, ps = read(tmp_path / "ergostat.yaml")
    assert not [x for x in ps if x.level == "error"], [str(x) for x in ps if x.level == "error"]
    b = spec.blocks["modeller"]
    assert b.type == "ai" and "modelling ai --model haiku" in b.params["run"] and Path(b.params["prompt"]).is_file()
    assert not [x for x in ps if x.code == "missing-feedback"]


def test_the_requests_collector_prints_arrivals_an_hour(tmp_path):
    project(tmp_path)
    got = subprocess.run([sys.executable, "-m", "ergostat.library.run", "modelling", "requests", "--no-coherence"],
                         cwd=tmp_path, capture_output=True, text=True, timeout=120,
                         env={**os.environ, "ERGOSTAT_STATE_DIR": str(tmp_path / "state")})
    assert got.returncode == 0, got.stderr
    assert float(got.stdout.strip()) > 0 and "not answered" in got.stderr


NO_EQUATIONS = """\
name: bare
items:
  ticket:
    id: ticket/*
    states: [new, worked, done]
    on: {ticket.opened: new, ticket.worked: worked, ticket.done: done}
stocks:
  new-tickets:
    sensor: {items: ticket, state: new, every: 5s}
  worked-tickets:
    sensor: {items: ticket, state: worked, every: 5s}
flows:
  working:
    from: new-tickets
    to: worked-tickets
  finishing:
    from: worked-tickets
blocks:
  worker:
    type: program
    run: python3 -c pass
    takes: {kind: ticket, at: new, to: [worked]}
    out: flow.working
uses:
  modelling: {use: modelling}
"""


def test_a_model_with_no_equations_wakes_modelling_whatever_the_fit_says_and_it_says_why(tmp_path):
    from ergostat.numbers import modelling_status as mst
    (tmp_path / "ergostat.yaml").write_text(NO_EQUATIONS)
    p = Project(mdl.load(tmp_path))
    got = rq.sync(p)
    have = {(r["code"], r["about"]): r for r in rq.current(p)}
    fit = have[("fit-unknown", "model")]                                # the fit cannot be read: that is work, said why
    assert "equation" in fit["says"] and fit["tier"] == "rule"
    assert ("no-equation", "flow.working") in have and got["open"] >= 5
    made, _ = ru.propose(p, [r for r in rq.current(p) if r["tier"] == "rule"], most=20)
    kinds = {raw["kind"] for _, raw in made}
    assert "equation" in kinds and "unit" in kinds                     # proposals, though model-fits says nothing
    for _, raw in made:
        assert im.submit(p, "fixer", raw)["status"] == "proposed"
    said = mst.of(p)["says"]
    assert "fit unknown" in said and "request" in said                 # never silent: what it waits for
    spec, ps = read(tmp_path / "ergostat.yaml")
    assert "requests-handled" in spec.goals and spec.blocks["fixer"].goal == "requests-handled"   # its own goal, not the fit's
