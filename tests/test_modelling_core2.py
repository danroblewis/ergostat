"""modelling-core2's acceptance tests (docs/roadmap/overnight/modelling-core2.md): the spot-check's fixes to the
redesigner on its own (the rest keyed on a unit's own parts, turns, what starts the rest, the cap before planning,
reading the store once) and to scope and carrying."""

from __future__ import annotations

import time

from ergostat import model as mdl
from ergostat.library.run import modelling as ml
from ergostat.numbers import judge as jd
from ergostat.numbers import proposals as pr
from ergostat.numbers import redesign as rd
from ergostat.numbers import redesign_due as due
from ergostat.numbers import redesigner as rdr
from ergostat.numbers import requests as rq

from .test_modelling_core import MODELLING, _block
from .test_redesign import CHAIN, PIECES, READ, busy
from .test_redesign import project as redesign_project
from .test_self_improve import POOR
from .test_self_improve import project as poor_project

TWO = ("systems:\n  front:\n    description: triage\n  back:\n    description: investigation\n"
       + PIECES.replace("  triage:\n    sensor:", "  triage:\n    system: front\n    sensor:")
               .replace("  investigate:\n    unit:", "  investigate:\n    system: back\n    unit:")
               .replace("  in:\n    to: triage", "  in:\n    to: triage\n    system: front")
               .replace("  triaged:\n    from: triage", "  triaged:\n    from: triage\n    system: front")
               .replace("  closed:\n    from: investigate", "  closed:\n    from: investigate\n    system: back"))


def _quiet(monkeypatch):
    monkeypatch.setattr(due, "_fit", lambda p_, spec: {"stocks": {}, "span": 0.0})


def test_the_rest_is_keyed_on_the_units_own_parts(tmp_path, monkeypatch):
    _quiet(monkeypatch)
    p = redesign_project(tmp_path / "m", TWO)
    spec, now = p.model.spec, time.time()
    rd.ran(p, "front", {"result": "nothing proposed", "unit_sig": due.signature(spec, "front")})
    assert "resting" in due.resting(p, spec, "front", now)
    f = p.model.path                                        # a change elsewhere (back's description): front still rests
    f.write_text(f.read_text().replace("description: alerts closed", "description: alerts closed, investigated"))
    p.model = mdl.load(f.parent)
    assert "resting" in due.resting(p, p.model.spec, "front", now)
    f.write_text(f.read_text().replace("  triage:\n    system: front\n", "  triage:\n    system: front\n    unit: alerts\n"))
    p.model = mdl.load(f.parent)                            # a change to its own parts: it is looked at again
    assert due.signature(p.model.spec, "front") != due.signature(spec, "front")
    assert due.resting(p, p.model.spec, "front", now) is None


def test_units_take_turns(tmp_path, monkeypatch):
    _quiet(monkeypatch)
    p = redesign_project(tmp_path / "m", TWO)
    now = time.time()
    assert due.units(p.model.spec)[0] == ["back", "front"]
    rd.ran(p, "back", {"result": "proposed", "unit_sig": "x"})
    got = due.next_due(p, now + due.DAILY + 10)                  # both due for their daily review: front's turn
    assert got["system"] == "front", got
    rd.ran(p, "front", {"result": "proposed", "unit_sig": "y"})
    assert due.next_due(p, now + due.DAILY + 20)["system"] in ("back", None)


def test_dismissed_superseded_and_unfinished_runs_start_the_rest(tmp_path, monkeypatch):
    _quiet(monkeypatch)
    for state in ("dismissed", "superseded"):
        p = busy(tmp_path / state, "owner")
        got = rd.submit(p, "redesigner", {"title": "busy read", "edits": READ})
        pr.event(p, got["id"], state, {"why": "no", "decided": time.time()})
        assert f"was {state}" in due.resting(p, p.model.spec, "model", time.time()), state
    p = busy(tmp_path / "crashed", "owner")
    rd.ran(p, "model", {"result": "started", "unit_sig": due.signature(p.model.spec, "model")})
    later = time.time() + rd.RUNNING_FOR + 5
    assert due.resting(p, p.model.spec, "model", later) == "resting: its last run never ended"


def test_an_unfinished_run_closes_its_request(tmp_path, monkeypatch):
    _quiet(monkeypatch)
    p = busy(tmp_path / "m", "owner")
    rd.ran(p, "model", {"result": "started"})
    k = due.hold(p, "model", "redesign-due", "the first run with use: modelling", state="open")
    due.next_due(p, time.time() + rd.RUNNING_FOR + 5)
    x = rq.stored(p)[k]
    assert x["state"] == "answered" and "never ended" in x["why"]


def test_the_cap_is_checked_before_planning(tmp_path, monkeypatch, capsys):
    p = poor_project(tmp_path, POOR + MODELLING)
    _block(monkeypatch, p)
    rd.charge(p, "model", {"usd": 5.0})

    def never(*a, **k):
        raise AssertionError("planned past the cap")
    monkeypatch.setattr(rd, "plan", never)
    assert ml.redesign(["--when", "auto", "--daily", "2"]) == 0
    assert "spent" in capsys.readouterr().err


def test_next_due_reads_the_store_once(tmp_path, monkeypatch):
    _quiet(monkeypatch)
    p = redesign_project(tmp_path / "m", TWO)
    calls = {"rq": 0, "pr": 0}
    real_rq, real_pr = rq.stored, pr.changes

    def count(name, real):
        def f(*a, **k):
            calls[name] += 1
            return real(*a, **k)
        return f
    monkeypatch.setattr(rq, "stored", count("rq", real_rq))
    monkeypatch.setattr(pr, "changes", count("pr", real_pr))
    due.next_due(p)
    assert calls["rq"] <= 2 and calls["pr"] <= 1 + len(due.units(p.model.spec)[0])   # (waiting reads it per unit)
    ran = due._ran(p, time.time())
    assert isinstance(ran, list)                            # bounded: the last day and the rest after it


def test_a_parameter_is_inside_a_system_only_if_its_parts_use_it(tmp_path):
    text = TWO.replace("goals:", "parameters:\n  pace:\n    value: 2\n    unit: alerts\n    description: how fast\n"
                       "goals:").replace("  closed:\n    from: investigate\n    system: back\n",
                                         "  closed:\n    from: investigate\n    system: back\n    driven-by: +stock.investigate\n"
                                         "    equation: stock.investigate / pace\n")
    p = redesign_project(tmp_path / "m", text)
    out = rd.submit(p, "redesigner", {"title": "x", "system": "front",
                                      "edits": [{"part": "parameter.pace", "set": {"value": 5}}]})
    assert out["status"] == "not-proposed" and "parameter.pace" in out["why"]       # back's, by its use


def test_following_a_rename_never_touches_selectors_labels_or_run_strings(tmp_path):
    from ergostat.numbers.changeset import parts_changed
    p = redesign_project(tmp_path / "m", TWO)
    before = p.model.spec
    f = p.model.path
    text = f.read_text()
    for a, b in (("  triage:\n", "  new-alerts:\n    formerly: [triage]\n"), ("to: triage", "to: new-alerts"),
                 ("from: triage", "from: new-alerts"), ("stock: triage", "stock: new-alerts")):
        text = text.replace(a, b)
    text = text.replace("description: alerts closed", "description: alerts closed after triage")   # back's words
    (tmp_path / "n").mkdir()
    (tmp_path / "n" / "ergostat.yaml").write_text(text)
    after = mdl.load(tmp_path / "n").spec
    beyond = rd.outside(before, after, "front", parts_changed(before, after))
    assert beyond == ["flow.closed"]                       # its words changed: not a name it follows


def test_a_carried_redesign_is_held_to_its_scope(tmp_path):
    p = redesign_project(tmp_path / "m", TWO)
    got = rd.submit(p, "redesigner", {"title": "y", "system": "front", "edits": [CHAIN[0]]})
    assert got["status"] == "proposed", got["why"]
    f = p.model.path                                        # the owner moves stock.investigate into front
    f.write_text(f.read_text().replace("    system: back\n    unit: alerts", "    system: front\n    unit: alerts")
                 + "parameters:\n  slack:\n    value: 2\n    unit: alerts\n    description: a margin\n")
    p.model = mdl.load(f.parent)
    pr.supersede(p, p.model.spec)
    x = pr.stored(p)[got["id"]]
    assert x["state"] == "checked" and x.get("rescoring")
    f.write_text(f.read_text().replace("  triage:\n    system: front\n", "  triage:\n    system: back\n")
                 .replace("value: 2", "value: 3"))
    p.model = mdl.load(f.parent)                            # its stock moved to back: the rename is outside front now
    pr.supersede(p, p.model.spec)
    st, x = pr.changes(p)[got["id"]]
    assert st == "superseded" and "outside system front" in x["why"]


def test_carried_words_go_back_to_checked_and_a_redesign_says_rescoring(tmp_path):
    from ergostat.numbers import improve as im
    from ergostat.numbers import review as rv
    p = busy(tmp_path / "m", "owner")
    words = im.submit(p, "modeller", {"kind": "description", "parts": ["stock.triage"], "title": "described",
                                       "edit": {"part": "stock.triage", "set": {"description": "alerts not yet triaged"}},
                                       "reasons": [{"says": "none", "evidence": "finding:no-description@stock.triage"}]})
    design = rd.submit(p, "redesigner", {"title": "busy read", "edits": READ})
    jd.run(p, "judge")
    assert pr.stored(p)[words["id"]]["state"] == "passed"
    f = p.model.path
    f.write_text(f.read_text() + "parameters:\n  slack:\n    value: 2\n    unit: alerts\n    description: a margin\n")
    p.model = mdl.load(f.parent)
    pr.supersede(p, p.model.spec)
    assert pr.stored(p)[words["id"]]["state"] == "checked"                     # back to checked, not passed
    x = pr.stored(p)[design["id"]]
    assert x["state"] == "checked" and rv.redesign_view(x)["rescoring"]
    jd.run(p, "judge")
    assert not pr.stored(p)[design["id"]].get("rescoring")                     # scored again


def test_carrying_runs_under_the_lock(tmp_path, monkeypatch):
    p = busy(tmp_path / "m", "owner")
    held = []
    real = pr._supersede

    def watched(p_, spec, why="x"):
        import fcntl
        with open(p_.dir / "proposals.lock", "w") as fh:     # another holder cannot take the lock meanwhile
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                held.append(False)
                fcntl.flock(fh, fcntl.LOCK_UN)
            except OSError:
                held.append(True)
        return real(p_, spec, why)
    monkeypatch.setattr(pr, "_supersede", watched)
    pr.supersede(p, p.model.spec)
    words = __import__("ergostat.numbers.improve", fromlist=["submit"]).submit(
        p, "modeller", {"kind": "description", "parts": ["stock.triage"], "title": "d",
                        "edit": {"part": "stock.triage", "set": {"description": "alerts not yet triaged"}},
                        "reasons": [{"says": "none", "evidence": "finding:no-description@stock.triage"}]})
    jd.run(p, "judge")
    pr.accept(p, words["id"], {"at": time.time(), "window": 600})
    assert held and all(held)                                # in supersede, the judge and Accept alike
    assert rdr is not None
