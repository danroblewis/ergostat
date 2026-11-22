"""modelling-core's acceptance tests (docs/roadmap/overnight/modelling-core.md): what the gate review of selfimprove and
redesign asked for. Who decides what is written is the owner's; a redesign that removes, rewires or changes control
waits for the owner; a rename is only a rename; a promoted redesign never blocks the queue; the owner's ask is taken
up by the redesigner block; runs say what they cost; carried redesigns are scored again; Accept writes all or
nothing; the daily cap; the requests goal reachable; the boundary rule scoped to a template's own parts."""

from __future__ import annotations

import io
import json
import threading
import time
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat.library.run import modelling as ml
from ergostat.numbers import improve as im
from ergostat.numbers import judge as jd
from ergostat.numbers import proposals as pr
from ergostat.numbers import redesign as rd
from ergostat.numbers import redesigner as rdr
from ergostat.numbers import scorecard as sc
from ergostat.numbers import structural as stc
from ergostat.numbers import version as ver
from ergostat.spec import chains, read
from ergostat.store import Project

from .test_redesign import CHAIN, JUDGE, PIECES, READ, busy
from .test_redesign import project as redesign_project
from .test_self_improve import POOR
from .test_self_improve import project as poor_project

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"



MODELLING = "uses:\n  modelling:\n    use: modelling\n    with:\n      fit: 0.05\n      ai: true\n"


def _replace(p, old: str, new: str, title: str = "x", kind: str = "structure", evidence: str = "finding:no-unit@stock.new-alerts"):
    text = p.model.path.read_text()
    assert old in text
    return {"kind": kind, "parts": [], "title": title,
            "edit": {"file": "ergostat.yaml", "replace": text.rstrip("\n"), "with": text.replace(old, new).rstrip("\n")},
            "reasons": [{"says": "x", "evidence": evidence}]}


def test_a_change_set_that_changes_the_policy_is_refused(tmp_path):
    p = busy(tmp_path / "m", "{redesign: auto}")
    disk = p.model.path.read_text()
    got = rd.submit(p, "redesigner", {"title": "and the policy", "edits": READ + [
        {"part": "block.judge", "set": {"accept": "auto"}, "why": "let the judge write what passes"}]})
    assert got["status"] == "not-proposed" and "the judge's policy" in got["why"] and "owner's" in got["why"]
    assert p.model.path.read_text() == disk


def test_a_proposal_that_changes_a_blocks_accept_or_a_templates_with_is_refused(tmp_path):
    (tmp_path / "a").mkdir()
    p = poor_project(tmp_path / "a", POOR + JUDGE.replace("ACCEPT", "owner").replace("\n  judge:", "  judge:"))
    got = im.trial(p, _replace(p, "accept: owner", "accept: auto"))
    assert got["would"] == "not be proposed" and "judge's policy" in got["why"]
    (tmp_path / "b").mkdir()
    p = poor_project(tmp_path / "b", POOR + MODELLING)
    got = im.trial(p, _replace(p, "fit: 0.05", "fit: 0.5"))
    assert got["would"] == "not be proposed" and "use modelling's with:" in got["why"]


def test_a_redesign_that_removes_rewires_or_changes_control_waits_for_the_owner(tmp_path):
    cases = {"rewires": (lambda d: redesign_project(d, PIECES + JUDGE.replace("ACCEPT", "{redesign: auto}")), CHAIN),
             "control": (lambda d: busy(d, "{redesign: auto}"),
                         READ + [{"part": "goal.triage-ok", "set": {"hold": "<= 1"}, "why": "a little slack"}]),
             "removes": (lambda d: busy(d, "{redesign: auto}"), [{"remove": "auxiliary.busy", "why": "it says nothing"}])}
    for name, (make, edits) in cases.items():
        p = make(tmp_path / name)
        got = rd.submit(p, "redesigner", {"title": name, "edits": edits})
        assert got["status"] == "proposed", (name, got["why"])
        x = pr.stored(p)[got["id"]]
        assert jd.owners(x), name
        out = jd.run(p, "judge")
        x = pr.stored(p)[got["id"]]
        assert out["accepted"] == 0 and x["state"] == "passed", (name, x["state"], out["verdicts"])
        pr.accept(p, got["id"], {"at": time.time(), "window": 600})   # the owner writes it
        assert pr.stored(p)[got["id"]]["state"] == "accepted"


def test_a_rename_that_changes_a_sensor_or_control_is_not_a_rename(tmp_path):
    base = POOR.replace("flows:\n", "parameters:\n  slow:\n    value: 3\n    unit: alerts\nflows:\n")
    rename = [("  new-alerts:\n", "  alerts-waiting:\n    formerly: new-alerts\n"), ("to: new-alerts", "to: alerts-waiting"),
              ("from: new-alerts", "from: alerts-waiting"), ("+stock.new-alerts", "+stock.alerts-waiting"),
              ("stock: new-alerts", "stock: alerts-waiting")]

    def spec_of(name: str, more: list[tuple[str, str]], text: str = base):
        for a, b in rename + more:
            text = text.replace(a, b)
        d = tmp_path / name
        d.mkdir()
        (d / "ergostat.yaml").write_text(text)
        got, problems = read(d / "ergostat.yaml")
        assert not [x for x in problems if x.level == "error"], (name, [str(x) for x in problems if x.level == "error"])
        return got
    (tmp_path / "base").mkdir()
    (tmp_path / "base" / "ergostat.yaml").write_text(base)
    before = read(tmp_path / "base" / "ergostat.yaml")[0]
    assert ver.renamed_parts(before, spec_of("plain", [])) == {"stock.new-alerts": "stock.alerts-waiting"}
    cases = {"sensor": [("sensor: {items: alert, state: new, every: 2s}", "sensor: {items: alert, state: closed, every: 2s}")],
             "control": [('hold: "<= 3"', 'hold: "<= 50"')],
             "a value": [("value: 3", "value: 300")],                       # the dynamics, past the fit test
             "a rate": [("    description: closed\n", "    description: closed\n    rate: 5\n")],
             "an item kind": [("triage.finished: triaged", "triage.done: triaged")]}
    for name, more in cases.items():
        after = spec_of(name, more)
        assert ver.renamed_parts(before, after) is None, name
        assert im.kind_of(before, after, "rename") != "rename", name


def test_every_change_that_rewires_a_chain_says_so(tmp_path):
    p = redesign_project(tmp_path / "m", PIECES + JUDGE.replace("ACCEPT", "auto"))
    raw = {"kind": "equation", "parts": ["flow.triaged"], "title": "chained",
           "edit": {"part": "flow.triaged", "set": {"to": "investigate"}},
           "reasons": [{"says": "a move between states", "evidence": "finding:outflow-not-chained@flow.triaged"}]}
    got = im.submit(p, "modeller", raw)                  # an AI tier's change, which never said rewires itself
    assert got["status"] == "proposed", got["why"]
    assert pr.stored(p)[got["id"]].get("rewires") is True
    jd.run(p, "judge")
    assert pr.stored(p)[got["id"]]["state"] != "accepted"   # accept: auto, and still the owner's
    renamed = redesign_project(tmp_path / "r", PIECES)
    from ergostat.numbers import changeset as cs
    s = cs.Scratch(renamed)
    s.apply(CHAIN[0])                                    # a rename alone rewires nothing
    assert not stc.rewired(renamed.model.spec, s.compiled()[0])


def test_a_promoted_redesign_whose_edit_fails_is_superseded(tmp_path, monkeypatch):
    p = busy(tmp_path / "m", "{description: auto, redesign: auto}")
    got = rd.submit(p, "redesigner", {"title": "busy read", "edits": READ})
    words = im.submit(p, "modeller", {"kind": "description", "parts": ["stock.triage"], "title": "described",
                                       "edit": {"part": "stock.triage", "set": {"description": "alerts not yet triaged"}},
                                       "reasons": [{"says": "none", "evidence": "finding:no-description@stock.triage"}]})
    assert words["status"] == "proposed", words["why"]
    real = pr._accept                                         # (a promoted redesign is written by _accept, under the
    # lock the judge holds for its check-and-write: redesign-rescored-as-the-record-moves)

    def accept(p_, pid, *a, **k):
        if pid == got["id"]:
            raise pr.ProposalError("the files have changed under it")
        return real(p_, pid, *a, **k)
    monkeypatch.setattr(pr, "_accept", accept)
    out = jd.run(p, "judge")
    assert pr.changes(p)[got["id"]][0] == "superseded"
    assert pr.changes(p)[words["id"]][0] == "accepted" and out["accepted"] == 1   # the queue went on


def test_an_owner_asked_redesign_is_an_ask_the_block_takes_up(tmp_path):
    from ergostat.web import numbers_api as na
    p = poor_project(tmp_path, POOR + MODELLING)
    assert "redesigner" in p.model.spec.blocks
    model, threads = p.model, threading.active_count()
    code, got = na.redesign_asked(None, p, "model")
    assert code == 200 and got["asked"] == "model"
    assert threading.active_count() == threads and p.model is model         # nothing run in the page server
    assert rd.asked(p) == ["model"]
    assert rd.plan(p, "ask") == {"system": "model", "why": ["the owner asked"], "asked": True}
    (tmp_path / "bare").mkdir()
    bare = poor_project(tmp_path / "bare")
    assert na.redesign_asked(None, bare, "model")[0] == 409                  # no redesigner: said, nothing asked


def _block(monkeypatch, p) -> None:
    monkeypatch.setattr(ml, "project", lambda: p)
    monkeypatch.setattr("sys.stdin", io.StringIO(""))


def _results(out: str) -> list[dict]:
    return [x for x in (json.loads(line) for line in out.splitlines() if line.startswith("{")) if x.get("type") == "result"]


def test_the_redesigner_and_the_ai_tier_print_result_lines(tmp_path, monkeypatch, capsys):
    p = poor_project(tmp_path, POOR + MODELLING)
    _block(monkeypatch, p)
    one = {"usd": 0.012, "tokens_in": 900, "tokens_out": 100, "seconds": 1.0}
    cost = {**one, "calls": 1, "model": "haiku"}
    rd.ask(p, None)

    def run(*a, on_call=None, **k):
        on_call(one)                                 # each call said as it is spent
        on_call(one)
        return {"system": "model", "rounds": [{}, {}], "cost": cost, "version": "v", "result": "nothing proposed",
                "reports": []}
    monkeypatch.setattr(rdr, "run", run)
    assert ml.redesign(["--when", "ask"]) == 0
    got = _results(capsys.readouterr().out)
    assert [x["total_cost_usd"] for x in got] == [pytest.approx(0.012)] * 2
    assert rd.spent(p) == pytest.approx(0.024)        # charged as spent, not only when the run ends
    from ergostat.numbers import modeller as md
    from ergostat.numbers import requests as rq
    rq.sync(p)

    def answer(*a, on_call=None, **k):
        on_call(one)
        return {"proposals": [], "cannot": [], "cost": cost, "tried": []}
    monkeypatch.setattr(md, "answer", answer)
    assert ml.ai(["--model", "haiku", "--daily", "1"]) == 0
    got = _results(capsys.readouterr().out)
    assert len(got) == 1 and got[0]["total_cost_usd"] == pytest.approx(0.012)


def test_a_call_that_never_says_its_cost_is_charged_the_most_it_could_and_calls_fit_the_timeout(monkeypatch):
    import subprocess

    from ergostat.numbers import modeller as md

    def slow(*a, **k):
        raise subprocess.TimeoutExpired("claude", k.get("timeout"))
    monkeypatch.setattr(subprocess, "run", slow)
    got = md.call("x" * 30000, "haiku", 5)
    assert got["error"] and got["estimated"] and got["usd"] > 0.0          # dear, not free: the cap fails closed
    assert md.per_call(900, 3) * 3 <= 900 and md.per_call(None, 3) == 600.0


def test_the_redesigners_guides_come_through_the_help_documents(monkeypatch):
    from ergostat import helpdocs
    monkeypatch.setattr(helpdocs, "read", lambda name: "## 5. Review checklists\n\nXYZZY the installed copy\n"
                        if name == "modelling-well" else None)
    assert "XYZZY the installed copy" in rdr.guides()


def test_a_carried_redesign_is_checked_again(tmp_path):
    p = busy(tmp_path / "m", "owner")
    got = rd.submit(p, "redesigner", {"title": "busy read", "edits": READ})
    jd.run(p, "judge")
    assert pr.stored(p)[got["id"]]["state"] == "passed"
    f = p.model.path                                                      # the owner edits the model: a new version
    f.write_text(f.read_text() + "parameters:\n  slack:\n    value: 2\n    unit: alerts\n    description: a margin\n")
    p.model = mdl.load(f.parent)
    assert pr.supersede(p, p.model.spec) == []                            # carried, not let go
    x = pr.stored(p)[got["id"]]
    assert x["state"] == "checked" and x.get("carried")                   # carried, and to be scored again
    jd.run(p, "judge")
    assert pr.stored(p)[got["id"]]["state"] == "passed"


def test_a_write_of_several_files_rolls_back_whole(tmp_path, monkeypatch):
    p = busy(tmp_path / "m", "owner")
    disk = p.model.path.read_text()
    words = im.submit(p, "modeller", {"kind": "description", "parts": ["stock.triage"], "title": "described",
                                       "edit": {"part": "stock.triage", "set": {"description": "alerts not yet triaged"}},
                                       "reasons": [{"says": "none", "evidence": "finding:no-description@stock.triage"}]})

    def broken(*a, **k):
        raise RuntimeError("the disk went away")
    monkeypatch.setattr(mdl, "load", broken)
    with pytest.raises(RuntimeError):
        pr.accept(p, words["id"], {"at": time.time(), "window": 600})
    assert p.model.path.read_text() == disk                               # put back, as it was


def test_keep_history_says_what_it_did(tmp_path):
    p = poor_project(tmp_path)
    t0 = 1_700_000_000.0
    for i in range(3):
        p.measurements.add("sensor/new-alerts.main", float(i), at=t0 + i)
    raw = _replace(p, "  new-alerts:\n", "  alerts-waiting:\n    formerly: new-alerts\n", kind="rename")
    text = p.model.path.read_text()
    new = text
    for a, b in (("  new-alerts:\n", "  alerts-waiting:\n    formerly: new-alerts\n"), ("to: new-alerts", "to: alerts-waiting"),
                 ("from: new-alerts", "from: alerts-waiting"), ("+stock.new-alerts", "+stock.alerts-waiting"),
                 ("stock: new-alerts", "stock: alerts-waiting")):
        new = new.replace(a, b)
    raw["edit"]["with"] = new.rstrip("\n")
    got = im.submit(p, "modeller", raw)
    assert got["status"] == "proposed", got["why"]
    pr.accept(p, got["id"], {"at": t0 + 10, "window": 600})
    history = pr.stored(p)[got["id"]]["applied"]["history"]
    assert history == {"sensor/alerts-waiting.main": {"from": "sensor/new-alerts.main", "readings": 3}}


def test_the_scorecard_says_behaviour_lost(tmp_path, monkeypatch):
    p = busy(tmp_path / "m", "owner")
    before, problems = read(p.model.path)
    followed = {"stocks": {"stock.investigate": {"nmse": 0.05}}, "equations": {}}
    monkeypatch.setattr(sc, "fit", lambda p_, spec: {"stocks": {}, "equations": {}})   # after: it is not replayed
    card = sc.score(p, before, problems, before, problems, fit_before=followed)
    assert card["lost"] and "stock.investigate" in card["lost"][0]
    assert card["verdict"] != "better"


def test_the_judges_hold_while_a_redesign_is_made_is_bounded(tmp_path):
    p = busy(tmp_path / "m", "{redesign: auto}")
    got = rd.submit(p, "redesigner", {"title": "busy read", "edits": READ})
    rd.ran(p, "model", {"result": "started"})                            # a run that never ends
    assert jd.run(p, "judge")["accepted"] == 0
    later = time.time() + rd.HOLD_FOR + 5
    assert rd.running(p) and not rd.running(p, later, rd.HOLD_FOR)
    jd.run(p, "judge", at=later)
    assert pr.stored(p)[got["id"]]["state"] == "accepted"                 # held for HOLD_FOR at most


def test_redesigns_stop_at_the_daily_cap(tmp_path, monkeypatch, capsys):
    p = poor_project(tmp_path, POOR + MODELLING)
    _block(monkeypatch, p)
    rd.charge(p, "model", {"usd": 2.5})
    assert rd.spent(p) == pytest.approx(2.5)
    rd.ask(p, None)

    def never(*a, **k):
        raise AssertionError("ran past the cap")
    monkeypatch.setattr(rdr, "run", never)
    assert ml.redesign(["--when", "ask", "--daily", "2"]) == 0
    assert "spent" in capsys.readouterr().err and rd.asked(p) == ["model"]   # the ask waits for tomorrow


def test_held_requests_leave_the_count_the_goal_holds(tmp_path):
    p = poor_project(tmp_path, POOR + MODELLING)
    st = p.model.spec.stocks["unanswered-requests"]
    states = {tuple(s.items.get("state") or ()) for s in st.sensors.values() if s.items}
    assert states == {("open", "proposed")}
    assert str(p.model.spec.goals["requests-handled"].of) == "stock.unanswered-requests"


def test_the_boundary_leaves_out_only_a_templates_parts(tmp_path):
    ops = read(EXAMPLES / "ops" / "ergostat.yaml")[0]
    assert chains.boundary(ops, {}) is None                               # the modelling template's inflows are its own
    own = "name: c\nstocks:\n" + "".join(f"  s{i}:\n    unit: things\n" for i in range(6)) + "flows:\n" + \
          "".join(f"  in{i}:\n    to: s{i}\n" for i in range(6))
    (tmp_path / "ergostat.yaml").write_text(own)
    mine = read(tmp_path / "ergostat.yaml")[0]
    assert chains.boundary(mine, {}).code == "many-cloud-inflows"         # the model's own still found
    (tmp_path / "with").mkdir()
    (tmp_path / "with" / "ergostat.yaml").write_text(own + MODELLING.replace("      ai: true\n", ""))
    assert chains.boundary(read(tmp_path / "with" / "ergostat.yaml")[0], {}).code == "many-cloud-inflows"


def test_a_held_modelling_request_is_in_the_inbox(tmp_path):
    from ergostat.inbox import entries as en
    from ergostat.numbers import requests as rq
    p = poor_project(tmp_path, POOR + MODELLING)
    rq.sync(p)
    held = {r["id"] for r in rq.current(p, ("held",))}            # control, held for the owner at once
    r = next(r for r in rq.current(p, ("open",)))
    rq.mark(p, r, "held", "no tier has a change for it")
    got = [e for e in en.entries(p) if e["kind"] == "request"]
    assert {e["id"] for e in got} == {f"request/{x}" for x in held | {r["id"]}}
    assert {e["id"]: e["verbs"] for e in got} == {f"request/{x}": ["deny"] for x in held} | {f"request/{r['id']}": ["approve", "deny"]}
    assert f"/item/ergostat.modelling-request/{r['id']}" in {e["link"] for e in got}


# ---- the redesigner on its own (when: auto, the owner's decision): per system, bounded, never written without the owner

def _due(p, monkeypatch=None, fit=None):
    from ergostat.numbers import redesign_due as due
    if monkeypatch is not None:
        monkeypatch.setattr(due, "_fit", lambda p_, spec: fit or {"stocks": {}, "span": 0.0})
    return due


def test_each_automatic_trigger_fires(tmp_path, monkeypatch):
    from ergostat.numbers import requests as rq
    p = busy(tmp_path / "m", "owner")
    spec, now = p.model.spec, time.time()
    due = _due(p, monkeypatch)
    assert due.units(spec) == (["model"], [])                              # no systems of its own: one unit
    assert due.triggers(p, spec, "model", now) == ["the first run with use: modelling"]
    rd.ran(p, "model", {"result": "no better", "version": "x"})
    assert due.triggers(p, spec, "model", now) == []                       # reviewed today: nothing due
    assert due.triggers(p, spec, "model", now + due.DAILY + 1) == ["its daily review"]
    worse = {"stocks": {"stock.triage": {"nmse": 1.8}}, "span": due.SUSTAINED}
    assert "its replay is worse than its mean" in due.triggers(p, spec, "model", now, fit=worse)[0]
    assert due.triggers(p, spec, "model", now, fit={**worse, "span": 60.0}) == []   # not sustained
    rq.event(p, "w1", "raised", {"source": "check", "code": "measured-not-caused", "about": "flow.closed", "raised": now})
    assert due.triggers(p, spec, "model", now) == ["measured-not-caused on flow.closed"]
    rq.event(p, "w1", "answered", {})
    rq.event(p, "c1", "raised", {"source": "check", "code": "outflow-not-chained", "about": "flow.closed", "raised": now})
    assert due.triggers(p, spec, "model", now) == []                       # a structural finding: only once it is stale
    assert "unresolved" in due.triggers(p, spec, "model", now + due.STALE + 1)[0]
    rq.event(p, "c1", "answered", {})
    for i in range(due.STALL):                                            # refinement stalled on its parts
        pr.event(p, f"r{i}", "made", {"made_by": "modeller", "parts": ["stock.triage"], "made": now - 100 + i, "kind": "equation"})
        pr.event(p, f"r{i}", "refused", {"why": "no better"})
    assert due.triggers(p, spec, "model", now) == [f"refinement stalled: its last {due.STALL} changes were all turned away"]


def test_one_pending_and_the_rest_after_one_no_better(tmp_path, monkeypatch):
    p = busy(tmp_path / "m", "owner")
    spec, now = p.model.spec, time.time()
    due = _due(p, monkeypatch)
    assert rd.plan(p, "auto")["system"] == "model"                        # the first run: due
    got = rd.submit(p, "redesigner", {"title": "busy read", "edits": READ})
    assert rd.plan(p, "auto")["system"] is None and "waiting already" in rd.plan(p, "auto")["why"][0]
    pr.event(p, got["id"], "failed", {"why": "no better", "decided": now})
    assert "resting" in due.resting(p, spec, "model", now)                 # judged no better: it rests
    assert due.resting(p, spec, "model", now + due.COOL + 1) is None       # for a while
    q = busy(tmp_path / "n", "owner")
    sig = due.signature(q.model.spec, "model")
    rd.ran(q, "model", {"result": "nothing proposed", "unit_sig": sig})  # made nothing: rests too
    assert "resting" in due.resting(q, q.model.spec, "model", now)
    rd.ran(q, "model", {"result": "nothing proposed", "unit_sig": "its parts as they were"})
    rd.ran(q, "model", {"result": "proposed", "unit_sig": sig})
    assert due.resting(q, q.model.spec, "model", time.time() + 1) is None


def test_a_large_system_is_taken_a_subsystem_at_a_time_or_said_too_large(tmp_path, monkeypatch):
    from ergostat.numbers import redesign_due as due
    from ergostat.numbers import requests as rq

    def model(systems: bool, n: int) -> str:
        head = "name: big\n" + ("systems:\n  plant:\n    description: the whole plant\n  left:\n    within: plant\n"
                                "    description: one half\n  right:\n    within: plant\n    description: the other half\n"
                                if systems else "")
        stocks = "stocks:\n" + "".join(f"  s{i}:\n    unit: things\n    description: stock {i}\n"
                                       + (f"    system: {'left' if i % 2 else 'right'}\n" if systems else "")
                                       for i in range(n))
        return head + stocks
    monkeypatch.setattr(due, "MOST_PARTS", 10)
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "ergostat.yaml").write_text(model(False, 14))
    p = Project(mdl.load(tmp_path / "a"))
    assert due.units(p.model.spec) == ([], ["model"])                      # too large, nothing to split into
    monkeypatch.setattr(due, "_fit", lambda p_, spec: {"stocks": {}, "span": 0.0})
    assert due.next_due(p)["system"] is None
    held = [r for r in rq.stored(p).values() if r["code"] == "too-large"]
    assert held and held[0]["state"] == "held" and held[0]["owner"]        # said, for the owner: never attempted whole
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "ergostat.yaml").write_text(model(True, 14))
    spec = mdl.load(tmp_path / "b").spec
    assert due.units(spec) == (["left", "right"], [])                      # a subsystem at a time


def test_nothing_the_redesigner_makes_on_its_own_is_written_without_the_owner(tmp_path, monkeypatch, capsys):
    p = poor_project(tmp_path, POOR + MODELLING)
    assert rd.settings(p.model.spec)["when"] == "auto"                     # the default: it reviews on its own
    _block(monkeypatch, p)
    _due(p, monkeypatch)

    def run(p_, system, why, **k):
        got = rd.submit(p_, "redesigner", {"title": "units", "system": system,
                                           "edits": [{"part": "stock.new-alerts", "set": {"unit": "alerts"}}]})
        return {"system": system, "rounds": [{}], "cost": {"usd": 0.0, "calls": 0}, "version": "v",
                "result": got["status"], "id": got["id"], "reports": []}
    monkeypatch.setattr(rdr, "run", run)
    assert ml.redesign(["--when", "auto"]) == 0
    from ergostat.numbers import requests as rq
    trig = [r for r in rq.stored(p).values() if r.get("source") == "redesign"]
    assert trig and trig[0]["code"] == "redesign-due" and "first run" in trig[0]["says"]    # its trigger, said
    x = next(x for x in pr.stored(p).values() if x.get("kind") == "redesign")
    jd.run(p, "judge")
    assert pr.stored(p)[x["id"]]["state"] != "accepted"                    # the owner's to write (accept: owner)
    from ergostat.numbers import modelling_status as mst
    assert "the redesigner last reviewed model" in mst.of(p)["says"]


def test_a_redesign_of_a_system_changes_only_that_system(tmp_path):
    text = ("systems:\n  front:\n    description: triage\n  back:\n    description: investigation\n"
            + PIECES.replace("  triage:\n    sensor:", "  triage:\n    system: front\n    sensor:")
                    .replace("  investigate:\n    unit:", "  investigate:\n    system: back\n    unit:"))
    p = redesign_project(tmp_path / "m", text)
    out = rd.submit(p, "redesigner", {"title": "x", "system": "front",
                                      "edits": [{"part": "stock.investigate", "set": {"description": "elsewhere"}}]})
    assert out["status"] == "not-proposed" and "outside system front" in out["why"] and "stock.investigate" in out["why"]
    ok = rd.submit(p, "redesigner", {"title": "y", "system": "front", "edits": [CHAIN[0], {
        "add": "auxiliaries", "name": "triage-load", "why": "a new part, placed in no system: the redesign's to place",
        "set": {"unit": "alerts", "description": "what waits", "driven-by": ["+stock.new-alerts"],
                "equation": "stock.new-alerts"}}]})                      # a rename others follow, and a new part
    assert ok["status"] == "proposed", ok["why"]
