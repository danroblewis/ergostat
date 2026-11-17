"""The Model page as a review queue (numbers/review.py, structural.py, trial.py): each proposal an entry with
what, where, why, how found, effect, benefit and the exact diff; Show on diagram's parts; every pending
change simulated together; Accept writing exactly what was shown; Dismiss remembered with its reason;
each kind of structural proposal from a crafted model; the command line's same fields."""

from __future__ import annotations

import json
import math
import textwrap
import time

import pytest

from ergostat import model as mdl
from ergostat.correspond import universe
from ergostat.numbers import estimate as es
from ergostat.numbers import proposals as pr
from ergostat.numbers import review as rv
from ergostat.numbers import structural as stc
from ergostat.numbers import trial as tr
from ergostat.numbers import version as ver
from ergostat.numbers import yamledit as ye
from ergostat.spec import read
from ergostat.store import Project

from .test_numbers import QUEUE, queue_project

FIELDS = ("id", "what", "title", "where", "why", "how", "benefit", "diff", "conflicts", "simulable")


def project(tmp_path, text: str, record=None, minutes: int = 120):
    """A model, and a record every 30 s made by ``record(i, t) -> {series: value}``."""
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    p = Project(mdl.load(tmp_path))
    now = time.time()
    for i in range(minutes * 2 + 1):
        t = now - minutes * 60 + i * 30
        for k, v in (record(i, t) if record else {}).items():
            p.measurements.add(f"sensor/{k}.main", v, at=t)
    return p, {"at": now, "window": minutes * 60.0, "starts": now - minutes * 60}


def reload(p):
    p.model = mdl.load(p.model.path.parent)
    return p


def structural(p) -> list[dict]:
    rv.refresh(p, p.model.spec, force=True)
    return [x for x in pr.pending(p) if x["kind"] == "structure"]


def check_entry(e: dict, spec) -> None:
    for k in FIELDS:
        assert k in e, k
    assert e["what"] and e["title"] and e["why"] and e["how"]["method"], e
    assert e["where"]["parts"] and set(e["where"]["select"]) <= set(universe(spec))
    assert "unified" in e["diff"] and e["diff"]["hash"] and e["diff"]["files"], e["diff"]


# ---- the fields, for each kind of proposal

def test_a_parameter_proposal_is_an_entry_with_every_field(tmp_path):
    p, snap = queue_project(tmp_path, k_true=3.0)
    pr.make(p, snap)
    es_ = rv.entries(p, p.model.spec)
    e = next(x for x in es_ if x["kind"] == "parameter")
    check_entry(e, p.model.spec)
    assert e["what"] == "A parameter's value"
    assert "weighted least squares" in e["how"]["method"] and e["how"]["span"] and e["how"]["n"]
    assert "standard error" in (e["how"]["confidence"] or "")
    assert e["where"]["select"] == ["flow.served", "stock.queue"] or set(e["where"]["select"]) == {"flow.served", "stock.queue"}
    assert e["benefit"]["nmse_after"] < e["benefit"]["nmse_before"]
    assert "-    value: 2 " in e["diff"]["unified"] and "+    value: 2.99" in e["diff"]["unified"]
    assert e["simulable"]


def test_an_equation_and_a_what_if_are_entries_with_every_field(tmp_path):
    text = QUEUE.replace("    equation: k * stock.queue\n", "    sensor:\n      manual: true\n").replace("    estimate: true\n", "")
    st = {"q": 0.0}

    def rec(i, t):
        a = 10 + 5 * ((i // 20) % 2)
        out = {"queue": st["q"], "arrivals": a, "served": 3 * st["q"]}
        for _ in range(30):
            st["q"] += (a - 3 * st["q"]) / 3600
        return out
    p, snap = project(tmp_path, text, rec)
    pr.make(p, snap)
    e = next(x for x in rv.entries(p, p.model.spec) if x["kind"] == "equation")
    check_entry(e, p.model.spec)
    assert e["what"] == "An equation for a flow that has none" and "least squares" in e["how"]["method"] and e["how"]["n"]
    (tmp_path / "w").mkdir()
    p2, snap2 = queue_project(tmp_path / "w", k_true=3.0)
    pr.propose_values(p2, {"k": "3"}, snap2)
    w = next(x for x in rv.entries(p2, p2.model.spec) if x["kind"] == "parameter")
    check_entry(w, p2.model.spec)
    assert w["what"].endswith("your what-if") and w["how"]["method"].startswith("not estimated")


def test_a_loops_process_and_gain_are_entries_with_every_field(tmp_path):
    """A loop's proposals (control/proposals.py) read the same way; their effect is the loop's, not a replay's."""
    p, _ = queue_project(tmp_path)
    spec = p.model.spec
    edit = ye.Edit(str(tmp_path / "ergostat.yaml"), [ye.Hunk(3, [], ["# a process would be written here"])])
    for kind, extra in (("process", {"identified": {"form": "fopdt", "moves": 4, "test": False, "span": 3600, "n_est": 120,
                                                    "fit_val": 81.0}}),
                        ("tuning", {"block": "x", "reason": "SIMC. As it is: gain margin 1.2. Tuned: gain margin 2.4."})):
        x = {"id": f"c{kind}", "kind": kind, "goal": "g", "title": "t", "reason": "r. s", "edit": {"files": [edit.as_dict()], "diff": ""},
             "values": {"form": "fopdt"}, **extra}
        e = rv.entry(x, spec)
        for k in FIELDS:
            assert k in e
        assert e["source"] == "control" and not e["simulable"] and "controller" in e["not_simulated"]
        assert e["diff"]["unified"].count("+# a process") == 1
    proc = rv.entry({**x, "kind": "process", "identified": {"moves": 4, "n_est": 120}, "id": "z"}, spec)
    assert "4 step changes" in proc["how"]["method"]


# ---- accept writes exactly what was shown; dismiss is remembered

def test_accept_writes_exactly_the_diff_shown_and_refuses_another(tmp_path):
    p, snap = queue_project(tmp_path, k_true=3.0)
    x = next(x for x in pr.make(p, snap) if x["kind"] == "parameter")
    shown = rv.diff_of(x, p.model.path.parent)
    before = (tmp_path / "ergostat.yaml").read_text()
    with pytest.raises(pr.ProposalError):
        pr.accept(p, x["id"], snap, expect="0" * 16)                       # not what was shown: nothing written
    assert (tmp_path / "ergostat.yaml").read_text() == before
    pr.accept(p, x["id"], snap, expect=shown["hash"])
    after = (tmp_path / "ergostat.yaml").read_text()
    assert ye.unified(before, after, "ergostat.yaml") == shown["unified"]


def test_a_dismissal_is_remembered_with_its_reason_and_not_proposed_again(tmp_path):
    p, snap = project(tmp_path, """\
        name: d
        auxiliaries:
          mood:
            unit: points
        stocks:
          s:
            unit: jobs
            sensor:
              manual: true
        flows:
          in:
            to: s
            sensor:
              manual: true
          out:
            from: s
            driven-by: +stock.s
            sensor:
              manual: true
        """, lambda i, t: {"s": 5.0, "in": 3.0, "out": 3.0})
    x = next(x for x in structural(p) if x["code"] == "auxiliary-without-causes")
    pr.dismiss(p, x["id"], "it is set by hand each morning")
    assert pr.stored(p)[x["id"]]["dismissed_because"] == "it is set by hand each morning"
    assert not [y for y in structural(p) if y["id"] == x["id"]]
    ev = p.events.query(n=None, type="ergostat.model-change.dismissed")
    assert ev[-1]["data"]["dismissed_because"] == "it is set by hand each morning" and ev[-1]["source"] == "owner"
    assert ev[-1]["item"] == f"ergostat.model-change/{x['id']}"


# ---- every pending change simulated together, conflicts left out

def test_simulate_all_pending_combines_the_changes_and_leaves_out_a_conflict(tmp_path):
    p, snap = project(tmp_path, """\
        name: two
        parameters:
          a:
            value: 1
            unit: 1/h
          b:
            value: 1
            unit: 1/h
        stocks:
          first:
            unit: jobs
            sensor:
              manual: true
          second:
            unit: jobs
            sensor:
              manual: true
        flows:
          arrivals:
            to: first
            sensor:
              manual: true
          handed-on:
            from: first
            to: second
            driven-by: +stock.first
            equation: a * stock.first
          done:
            from: second
            driven-by: +stock.second
            equation: b * stock.second
        """, None)
    x1 = pr.propose_values(p, {"a": "2"}, snap)
    x2 = pr.propose_values(p, {"b": "3"}, snap)
    x3 = pr.propose_values(p, {"a": "4"}, snap)
    pend = pr.pending(p)
    taken, left, edits = tr.combine(p, [x for i in (x1["id"], x2["id"], x3["id"]) for x in pend if x["id"] == i])
    assert [x["id"] for x in taken] == [x1["id"], x2["id"]] and left[0]["id"] == x3["id"] and "conflicts" in left[0]["why"]
    spec = tr.spec_after(p, edits)
    assert spec.parameters["a"].value == 2 and spec.parameters["b"].value == 3      # both, in memory
    assert "value: 1" in (tmp_path / "ergostat.yaml").read_text()                    # nothing written
    e = {y["id"]: y for y in rv.entries(p, p.model.spec)}
    assert any(c["id"] == x3["id"] for c in e[x1["id"]]["conflicts"])
    assert not e[x2["id"]]["conflicts"]


def test_the_effect_charts_the_parts_before_and_after_and_says_what_changes_ahead(tmp_path):
    p, snap = queue_project(tmp_path, k_true=3.0)
    x = next(x for x in pr.make(p, snap) if x["kind"] == "parameter")
    got = rv.effect(p, p.model.spec, [x], snap["at"])
    c = {c["ref"]: c for c in got["charts"]}
    assert "stock.queue" in c and c["stock.queue"]["after"] != c["stock.queue"]["before"]
    assert c["stock.queue"]["proj_after"] and c["stock.queue"]["proj_before"]
    assert got["fit_after"]["total"]["nmse"] < got["fit_before"]["total"]["nmse"]
    assert any(s.startswith("queue in") for s in got["operational"])
    together = rv.effect(p, p.model.spec, [x, x], snap["at"])
    assert together["taken"] == [x["id"]]


# ---- each structural proposal from a crafted model

BASE = """\
name: s
parameters:
  k:
    value: 2
    unit: 1/h
stocks:
  inbox:
    unit: items
    sensor:
      manual: true
  pile:
    unit: items
    sensor:
      manual: true
  sent:
    unit: messages
  still:
    unit: items
    sensor:
      manual: true
auxiliaries:
  mood:
    unit: points
flows:
  arrive:
    to: inbox
    sensor:
      manual: true
  finish:
    from: inbox
    to: pile
    driven-by: +stock.inbox
    equation: k * stock.inbox
    sensor:
      manual: true
  notify:
    to: sent
    driven-by: +flow.finish
  topup:
    to: still
    sensor:
      manual: true
"""


def base_record():
    st = {"q": 0.0, "pile": 0.0}

    def rec(i, t):
        a = 10 + 5 * ((i // 20) % 2)
        out = {"inbox": st["q"], "pile": st["pile"], "still": 5.0, "arrive": a, "finish": 3 * st["q"], "topup": 0.0}
        for _ in range(30):
            f = 3 * st["q"]
            st["q"] += (a - f) / 3600
            st["pile"] += (f - 0.5 * st["pile"]) / 3600
        return out
    return rec


def accepted_cleanly(p, x, snap, gone: str | None = None):
    """Accepted: the model still compiles, and the finding it answered is gone."""
    pr.accept(p, x["id"], snap, expect=rv.diff_of(x, p.model.path.parent)["hash"])
    reload(p)
    spec, probs = read(p.model.path)
    assert not [q for q in probs if q.level == "error"]
    if gone:
        assert not [q for q in probs if q.code == gone and q.about == x["target"]], [str(q) for q in probs if q.code == gone]
    return spec


def test_check_findings_become_structural_proposals_each_with_its_edit(tmp_path):
    p, snap = project(tmp_path, BASE, base_record())
    got = {(x["code"], x["change"]): x for x in structural(p)}
    assert ("rate-driven-by-rate", "a new stock with its two flows") in got
    assert ("units-mismatch", "a new converting auxiliary") in got
    assert ("stock-without-outflow", "a new outflow to a cloud") in got                     # pile: things leave it
    assert ("auxiliary-without-causes", "an auxiliary marked exogenous") in got
    assert ("simplify-dead-flow", "a flow removed") in got and got[("simplify-dead-flow", "a flow removed")]["target"] == "flow.topup"
    assert ("simplify-still", "a stock removed") in got
    out = got[("stock-without-outflow", "a new outflow to a cloud")]
    assert "Little's law" in out["method"] and "time-in-pile" in out["edit"]["diff"]
    for x in pr.pending(p):
        check_entry(rv.entry(x, p.model.spec), p.model.spec)
    spec = accepted_cleanly(p, got[("stock-without-outflow", "a new outflow to a cloud")], snap, "stock-without-outflow")
    assert "pile-leaving" in spec.flows and spec.flows["pile-leaving"].equation.text == "stock.pile / time-in-pile"


def test_a_rate_following_a_rate_gets_the_stock_between_it_and_the_rate_it_follows(tmp_path):
    p, snap = project(tmp_path, """\
        name: r
        stocks:
          a:
            unit: jobs
            sensor:
              manual: true
          b:
            unit: jobs
            sensor:
              manual: true
        flows:
          in:
            to: a
            sensor:
              manual: true
          done:
            from: a
            driven-by: +stock.a
            sensor:
              manual: true
          shipped:
            to: b
            driven-by: +flow.done
          out:
            from: b
            driven-by: +stock.b
        """, lambda i, t: {"a": 4.0, "b": 2.0, "in": 3.0, "done": 3.0})
    x = next(x for x in structural(p) if x["code"] == "rate-driven-by-rate")
    spec = accepted_cleanly(p, x, snap, "rate-driven-by-rate")
    s = "done-awaiting-shipped"
    assert spec.flows["done"].target == s and spec.flows["shipped"].source == s       # the two flows meet at it
    assert [str(r) for r in spec.flows["shipped"].driven_by] == [f"stock.{s}"]


SIGNS = QUEUE.replace("equation: k * stock.queue", "equation: k * (10 - stock.queue)")


def test_a_sign_its_equation_contradicts_is_flipped(tmp_path):
    p, snap = queue_project(tmp_path, text=SIGNS)
    x = next(x for x in structural(p) if x["code"] == "equation-sign")
    assert x["change"] == "a link's sign flipped" and "-stock.queue" in x["edit"]["diff"]
    spec = accepted_cleanly(p, x, snap)
    assert spec.flows["served"].polarity["stock.queue"] == -1


EXTREME = QUEUE + """\
  spill:
    from: queue
    driven-by: [+stock.queue, -stock.other]
    equation: stock.queue - stock.other / stock.queue
  fill:
    to: other
    sensor:
      manual: true
  leak:
    from: other
    driven-by: +stock.other
    equation: stock.other / two-hours
"""


def test_extreme_conditions_failures_get_guards(tmp_path):
    other = "stocks:\n  other:\n    unit: jobs\n    sensor:\n      manual: true\n"
    text = EXTREME.replace("parameters:\n", "parameters:\n  two-hours: 2h\n").replace("stocks:\n", other)
    p, snap = queue_project(tmp_path, text=text)
    got = [x for x in structural(p) if x["code"] == "extreme-conditions"]
    texts = " ".join(x["title"] for x in got)
    assert "MAX(0, " in texts and "ZIDZ(" in texts, texts
    for x in got:
        assert x["change"] == "a guard on an equation"


def test_an_estimate_indistinguishable_from_zero_with_a_narrow_interval_removes_its_term_and_link(tmp_path):
    text = """\
        name: z
        parameters:
          k:
            value: 3
            unit: 1/h
            estimate: true
          w:
            value: 0.001
            unit: 1/h
            estimate: true
        auxiliaries:
          noise:
            unit: jobs
            exogenous: true
            sensor:
              manual: true
        stocks:
          queue:
            unit: jobs
            sensor:
              manual: true
        flows:
          arrivals:
            to: queue
            sensor:
              manual: true
          served:
            from: queue
            driven-by: [+stock.queue, +auxiliary.noise]
            equation: k * stock.queue + w * auxiliary.noise
            sensor:
              manual: true
        """
    p, snap = project(tmp_path, text, lambda i, t: {"queue": 4 + math.sin(i / 7), "noise": 1 + (i % 3), "arrivals": 12.0,
                                                    "served": 3 * (4 + math.sin(i / 7))})
    f = es.path(p, ver.structure(p.model.spec), "parts")
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"k": {"parameter": "k", "value": 3.0, "se": 0.01, "n": 200},
                             "w": {"parameter": "w", "value": 0.0005, "se": 0.002, "n": 200}}))
    x = next(x for x in structural(p) if x["code"] == "no-effect")
    assert x["change"] == "a term and its link removed" and "indistinguishable from 0" in x["reason"]
    spec = accepted_cleanly(p, x, snap)
    assert spec.flows["served"].equation.text == "k * stock.queue" and "w" not in spec.parameters
    assert [str(r) for r in spec.flows["served"].driven_by] == ["stock.queue"]


def test_a_sign_the_record_contradicts_is_flipped(tmp_path):
    text = """\
        name: c
        auxiliaries:
          speed:
            unit: points
            exogenous: true
            sensor:
              manual: true
        stocks:
          queue:
            unit: jobs
            sensor:
              manual: true
        flows:
          arrivals:
            to: queue
            sensor:
              manual: true
          served:
            from: queue
            driven-by: [+stock.queue, +auxiliary.speed]
            sensor:
              manual: true
        """
    p, snap = project(tmp_path, text, lambda i, t: {"queue": 5 + 2 * math.sin(i / 9), "speed": (i % 10),
                                                    "arrivals": 10.0, "served": (5 + 2 * math.sin(i / 9)) * (3 - 0.2 * (i % 10))})
    x = next(x for x in structural(p) if x["code"] == "sign-contradicted")
    assert "-auxiliary.speed" in x["edit"]["diff"] and "least squares" in x["method"]
    spec = accepted_cleanly(p, x, snap)
    assert spec.flows["served"].polarity["auxiliary.speed"] == -1


SIMPLE = """\
name: simple
stocks:
  first:
    unit: jobs
    sensor:
      manual: true
  middle:
    unit: jobs
    sensor:
      manual: true
  last:
    unit: jobs
    sensor:
      manual: true
  copy:
    unit: jobs
    sensor:
      manual: true
  empty:
    unit: jobs
    sensor:
      manual: true
  lonely:
    unit: jobs
flows:
  arrive:
    to: first
    sensor:
      manual: true
  onward:
    from: first
    to: middle
    sensor:
      manual: true
  through:
    from: middle
    to: last
    sensor:
      manual: true
  also:
    from: first
    to: last
  again:
    from: first
    to: last
  gone:
    from: last
    sensor:
      manual: true
  copy-in:
    to: copy
    sensor:
      manual: true
  empty-in:
    to: empty
  empty-out:
    from: empty
"""


def simple_record(i, t):
    f = 20 + 10 * math.sin(i / 11) + i * 0.1
    return {"first": f, "middle": 0.0, "last": 3 + i * 0.05, "copy": f * 1.001, "empty": 0.0, "arrive": 5.0, "onward": 5.0,
            "through": 5.0, "gone": 5.0, "copy-in": 1.0}


def test_sd_labs_simplify_rules_propose_merges_pass_throughs_and_removals(tmp_path):
    p, snap = project(tmp_path, SIMPLE, simple_record)
    got = {(x["code"], x["target"]): x for x in structural(p)}
    assert ("simplify-merge", "flow.also") in got                                     # also and again: first to last
    assert ("simplify-pass-through", "stock.middle") in got                           # nearly always empty, one in, one out
    assert ("simplify-empty", "stock.empty") in got
    assert ("simplify-twin", "stock.copy") in got and "first" in got[("simplify-twin", "stock.copy")]["reason"]
    assert ("simplify-alone", "stock.lonely") in got
    for x in got.values():
        if x["code"].startswith("simplify") and x["code"] != "simplify-merge":
            assert "ergostat has no hide:" in x["reason"]
    spec = accepted_cleanly(p, got[("simplify-merge", "flow.also")], snap)
    assert "again" not in spec.flows and "also" in spec.flows
    x = next(x for x in structural(p) if x["code"] == "simplify-pass-through")
    spec = accepted_cleanly(p, x, snap)
    assert "middle" not in spec.stocks and spec.flows["onward"].target == "last" and "through" not in spec.flows


def test_a_stock_a_goal_holds_is_left_alone(tmp_path):
    text = SIMPLE + "goals:\n  few-lonely:\n    stock: lonely\n    hold: <= 3\n"
    p, _ = project(tmp_path, text, simple_record)
    assert not [x for x in structural(p) if x["target"] == "stock.lonely"]


def test_an_equation_only_flow_that_explains_nothing_is_removed(tmp_path):
    text = QUEUE.replace("parameters:\n", "parameters:\n  tiny:\n    value: 0.000001\n    unit: 1/h\n") + \
        "  seep:\n    from: queue\n    driven-by: +stock.queue\n    equation: tiny * stock.queue\n"
    p, snap = queue_project(tmp_path, k_true=2.0, text=text)
    x = next(x for x in structural(p) if x["code"] == "simplify-no-effect")
    assert x["target"] == "flow.seep" and "replay without it" in x["reason"]


def test_what_ergostat_can_and_cannot_propose_is_said_and_the_residual_finder_has_its_place():
    assert any("missing stock" in x for x in stc.CANNOT)
    assert stc.from_residuals(None) is None and "next piece of work" in stc.from_residuals.__doc__


# ---- the command line lists the same fields

def test_the_command_line_lists_the_queue_and_shows_one_with_its_diff(tmp_path, capsys, monkeypatch):
    from ergostat.cli import main
    p, snap = queue_project(tmp_path, k_true=3.0)
    monkeypatch.chdir(tmp_path)
    assert main(["proposals"]) == 0
    out = capsys.readouterr().out
    for word in ("where", "why", "how", "benefit"):
        assert word in out
    pid = next(x["id"] for x in pr.pending(reload(p)) if x["kind"] == "parameter")
    assert main(["proposals", "--show", pid[:6]]) == 0
    out = capsys.readouterr().out
    assert "WHERE" in out and "HOW" in out and "DIFF" in out and "+    value: " in out
    assert main(["proposals", "--stored", "--json"]) == 0
    got = json.loads(capsys.readouterr().out)
    assert all(k in got[0] for k in FIELDS)


def test_leverage_ranks_the_flows_by_how_far_a_tenth_faster_moves_the_goals(tmp_path):
    """SD Lab's leverage: each flow a tenth faster in turn, projected to the horizon; arrivals faster moves
    the queue away from a ceiling, the drain faster toward it."""
    from ergostat.numbers import leverage as lv
    from ergostat.numbers import observe as ob
    from ergostat.numbers import simulate as sim
    text = QUEUE + "goals:\n  short:\n    stock: queue\n    hold: <= 3\n"
    p, snap = queue_project(tmp_path, k_true=2.0, text=text)
    spec = p.model.spec
    data = ob.measured(p, ob.reference(p, snap["at"]))
    run = sim.replay(spec, data, sim.plan(spec))
    got = lv.rank(spec, data, run, 3600.0)
    rows = {r["flow"]: r for r in got["rows"]}
    assert rows["arrivals"]["effect"]["short"]["toward"] < 0 < rows["served"]["effect"]["short"]["toward"]
    assert sorted(r["rank"] for r in got["rows"]) == list(range(1, len(got["rows"]) + 1))
    assert "toward goal short" in lv.said(rows["served"], got["of"])


def test_the_page_api_lists_the_queue_simulates_and_accepts_only_what_was_shown(tmp_path):
    from ergostat.web.numbers_api import post
    from ergostat.web.server import Live, api
    p, snap = queue_project(tmp_path, k_true=3.0)
    pr.make(p, snap)
    live = Live(p)
    d = api(live, "fit", {})
    e = next(x for x in d["queue"] if x["kind"] == "parameter")
    assert d["can"] and d["cannot"] and all(k in e for k in FIELDS)
    eff = api(live, "proposal-effect", {"ids": [e["id"]]})
    assert eff["taken"] == [e["id"]] and eff["charts"]
    assert post(live, f"proposals/{e['id']}/accept", 3600.0, {"expect": ["nope"]})[0] == 409
    code, got = post(live, f"proposals/{e['id']}/accept", 3600.0, {"expect": [e["diff"]["hash"]]})
    assert code == 200 and got["status"] == "accepted"
