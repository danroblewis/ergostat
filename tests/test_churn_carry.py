"""Proposals carried by any edit that leaves their subject as it was (docs/roadmap/overnight/proposals-superseded-by-any-edit.md):
a block's change, and one under test or passed, carried to a new version; a structural change whose lines moved carried
with the edit its finder finds again; every carry and every judging done under the proposals' lock, on the model as its
files are now."""

from __future__ import annotations

import threading

import pytest

from ergostat.numbers import estimate as es
from ergostat.numbers import improve as im
from ergostat.numbers import judge as jd
from ergostat.numbers import proposals as pr
from ergostat.numbers import review as rv
from ergostat.numbers import structural as stc
from ergostat.numbers import trial as tr
from ergostat.numbers import version as ver

from .test_churn import factory, history, snap
from .test_improve import KIND, LEAKS, judge_block, long_queue, made_ago, raw
from .test_numbers import QUEUE
from .test_review import project, reload, structural

ABOVE = ("parameters:\n", "parameters:\n  other:\n    value: 5\n")        # a part added above k: k's line moves
LEAKS_AT_ONCE = {"kind": "structure", "parts": ["flow.leaks"], "title": "leaks at once",
                 "edit": {"file": "ergostat.yaml", "replace": "    driven-by: +flow.arrivals",
                          "with": "    driven-by:\n      - {cause: +flow.arrivals, instant: true}\n      - +stock.queue"},
                 "reasons": [{"says": "a rate on a rate", "evidence": "finding:rate-driven-by-rate@flow.leaks"}]}


def edit(p, old, new):
    f = p.model.path
    text = f.read_text()
    assert old in text
    f.write_text(text.replace(old, new, 1))


def events(p, pid=None):
    return p.events.query(n=None, type=f"{KIND}.*", **({"item": pr.item_of(pid)} if pid else {}))


def k_after(p, x):
    return tr.spec_after(p, tr.edits_of(x)).parameters["k"].value


# ---- a block's change, carried when its subject is unchanged

def test_a_blocks_value_change_is_carried_when_its_subject_is_unchanged(tmp_path):
    p, _ = long_queue(tmp_path)
    got = im.submit(p, "x", raw(3))
    assert pr.stored(p)[got["id"]]["subject"]["refs"] == ["parameter.k"]
    edit(p, *ABOVE)
    reload(p)
    assert pr.supersede(p, p.model.spec) == []
    x = pr.stored(p)[got["id"]]
    assert x["state"] == "checked" and x["version"] == ver.version(p.model.spec) and x["made_by"] == "x"
    assert history(p, got["id"]) == ["made", "checked", "revised"]
    assert k_after(p, x) == 3


def test_a_blocks_change_is_superseded_when_its_subject_is_edited(tmp_path):
    p, _ = long_queue(tmp_path)
    got = im.submit(p, "x", raw(3))
    edit(p, "value: 2 ", "value: 2.5 ")
    reload(p)
    assert pr.supersede(p, p.model.spec) == [got["id"]]
    st, f = pr.changes(p)[got["id"]]
    assert st == "superseded" and "parameter.k" in f["why"] and "edited" in f["why"]


def test_a_change_recorded_without_a_subject_is_superseded(tmp_path):
    p, _ = long_queue(tmp_path)
    got = im.submit(p, "x", raw(3))
    x = pr.stored(p)[got["id"]]
    pid = "nosubject"
    pr.event(p, pid, "made", {k: v for k, v in x.items() if k not in (*pr.LOCAL, "subject")}, source="x")
    pr.event(p, pid, "checked", {})
    assert "subject" not in pr.stored(p)[pid]
    edit(p, *ABOVE)
    reload(p)
    assert pid in pr.supersede(p, p.model.spec)
    st, f = pr.changes(p)[pid]
    assert st == "superseded" and "recorded without what it is about" in f["why"]
    assert pr.changes(p)[got["id"]][0] == "checked"                       # the one with its subject: carried


def test_a_carried_change_that_would_change_who_decides_is_superseded(tmp_path, monkeypatch):
    p, _ = long_queue(tmp_path)
    got = im.submit(p, "x", raw(3))
    edit(p, *ABOVE)
    reload(p)
    seen = []
    monkeypatch.setattr(im, "governs", lambda a, b: seen.append((a, b)) or ["the judge's policy"])
    assert pr.supersede(p, p.model.spec) == [got["id"]]
    st, f = pr.changes(p)[got["id"]]
    assert st == "superseded" and "who decides" in f["why"] and "the judge's policy" in f["why"]
    (now, after), = seen
    assert ver.version(now) == ver.version(pr.files_now(p)) and after.parameters["k"].value == 3


def test_a_carried_change_that_is_no_longer_its_kind_is_superseded(tmp_path, monkeypatch):
    p, _ = long_queue(tmp_path)
    got = im.submit(p, "x", raw(3))
    edit(p, *ABOVE)
    reload(p)
    monkeypatch.setattr(im, "kind_of", lambda a, b, said: "control")
    assert pr.supersede(p, p.model.spec) == [got["id"]]
    st, f = pr.changes(p)[got["id"]]
    assert st == "superseded" and "no longer a parameter change" in f["why"]


# ---- judged on the old version: judged again

def test_a_passed_change_carried_goes_back_to_testing_and_is_judged_again(tmp_path):
    p, _ = long_queue(tmp_path, text=QUEUE + judge_block(accept="owner"))
    got = made_ago(p, "x", raw(3))
    jd.run(p, "judge")
    assert pr.stored(p)[got["id"]]["state"] == "passed"
    edit(p, *ABOVE)
    reload(p)
    assert pr.supersede(p, p.model.spec) == []
    st, f = pr.changes(p)[got["id"]]
    assert st == "testing" and f["verdict"] is None and f["looked"] is None and f["undecided"] is None
    carry = events(p, got["id"])[-1]
    assert carry["data"]["rebased"]["to"] == ver.version(p.model.spec)
    jd.run(p, "judge")
    later = [e for e in events(p, got["id"]) if e["seq"] > carry["seq"] and (e["data"] or {}).get("verdict")]
    assert later, "judged again"
    assert pr.stored(p)[got["id"]]["version"] == ver.version(p.model.spec)


def test_a_testing_change_carried_stays_testing_cleared_and_its_rewires_worked_out_again(tmp_path):
    p, _ = long_queue(tmp_path)
    got = im.submit(p, "x", raw(3))
    pr.event(p, got["id"], "testing", {"looked": 60.0, "undecided": "not yet", "more": 3600.0, "rewires": True,
                                       "verdict": {"verdict": "kept", "why": "old"}})
    edit(p, *ABOVE)
    reload(p)
    assert pr.supersede(p, p.model.spec) == []
    st, f = pr.changes(p)[got["id"]]
    assert st == "testing" and f["rewires"] is False and not jd.owners({**f, "id": got["id"]})
    assert all(f[k] is None for k in ("verdict", "looked", "undecided", "more", "not_exercised"))


def test_the_judge_never_moves_a_change_made_on_another_version(tmp_path, monkeypatch):
    p, _ = long_queue(tmp_path, text=LEAKS + judge_block(accept="{parameter: auto}"))
    a = im.submit(p, "x", raw(3))
    b = im.submit(p, "x", LEAKS_AT_ONCE)
    pr.event(p, a["id"], "testing", {})
    pr.event(p, a["id"], "passed", {"verdict": {"verdict": "passed", "why": "set by the test"}})
    before = p.model.path.read_text()
    p.model.path.write_text(before + "auxiliaries:\n  extra:\n    unit: points\n")   # at the end: a's hunk applies
    assert k_after(p, pr.stored(p)[a["id"]]) == 3
    monkeypatch.setattr(pr, "supersede", lambda *a_, **k_: [])            # the edit lands after supersede
    out = jd.run(p, "judge")
    assert out["accepted"] == 0 and out["deferred"]
    assert pr.stored(p)[a["id"]]["state"] == "passed" and pr.stored(p)[b["id"]]["state"] == "checked"
    text = p.model.path.read_text()
    assert "extra:" in text and "value: 2 " in text and "value: 3 " not in text


def test_accept_refuses_when_the_files_moved_on_from_the_loaded_model(tmp_path):
    p, snap_ = long_queue(tmp_path)
    a = im.submit(p, "x", raw(3))
    p.model.path.write_text(p.model.path.read_text() + "auxiliaries:\n  extra:\n    unit: points\n")
    before = p.model.path.read_text()
    with pytest.raises(pr.ProposalError, match="the model has changed"):
        pr.accept(p, a["id"], snap_)
    assert p.model.path.read_text() == before


def test_files_that_do_not_compile_defer_every_pass(tmp_path):
    p, snap_ = long_queue(tmp_path, text=QUEUE + judge_block())
    a = made_ago(p, "x", raw(3))
    p.model.path.write_text(p.model.path.read_text().replace("    unit: 1/h\n", "    unit: [1/h\n"))   # a syntax error
    assert pr.files_now(p) is None
    n = len(events(p))
    assert pr.supersede(p, p.model.spec) == []
    state = p.dir / rv.STATE
    state.unlink(missing_ok=True)
    rv.refresh(p, p.model.spec, force=True)
    assert not state.exists()
    pr.make(p, {"at": snap_["at"], "window": snap_["window"]})
    out = jd.run(p, "judge")
    assert out["deferred"] and len(events(p)) == n and pr.stored(p)[a["id"]]["state"] == "checked"


# ---- a structural change whose lines moved: carried with the edit found again

AUX = """\
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
    """
INSERTED = ("auxiliaries:\n", "parameters:\n  other:\n    value: 5\nauxiliaries:\n")   # above every hunk; no subject's


def aux_project(tmp_path):
    p, _ = project(tmp_path, AUX, lambda i, t: {"s": 5.0, "in": 3.0, "out": 3.0})
    s = next(x for x in structural(p) if x["code"] == "auxiliary-without-causes")
    return p, s


def test_a_structural_change_whose_lines_moved_is_carried_with_the_edit_found_again(tmp_path):
    p, s = aux_project(tmp_path)
    edit(p, *INSERTED)
    with pytest.raises(tr.TrialError):
        tr.spec_after(p, tr.edits_of(s))                                    # its lines moved: as it stands it no longer applies
    reload(p)
    assert s["id"] in {x["id"] for x in structural(p)}
    assert history(p, s["id"]) == ["made", "checked", "revised"]
    x = pr.stored(p)[s["id"]]
    assert x["state"] == "checked" and x["rebased"]["to"] == ver.version(p.model.spec)
    tr.spec_after(p, tr.edits_of(x))                                        # it applies to the files now


def test_an_edit_between_the_finder_and_the_lock_defers_the_carry(tmp_path, monkeypatch):
    p, s = aux_project(tmp_path)
    real = stc.find

    def find(*a, **k):
        got = real(*a, **k)
        edit(p, *INSERTED)                                                  # lands after the finder read the files
        return got
    monkeypatch.setattr(stc, "find", find)
    state = p.dir / rv.STATE
    state.unlink()
    began = p.events.last_seq()
    rv.refresh(p, p.model.spec, force=True)
    assert not [e for e in events(p, s["id"]) if e["seq"] > began] and not state.exists()
    monkeypatch.setattr(stc, "find", real)
    reload(p)
    structural(p)
    x = pr.stored(p)[s["id"]]
    assert x["state"] == "checked" and x["version"] == ver.version(p.model.spec)
    tr.spec_after(p, tr.edits_of(x))


def _dismiss_inside(monkeypatch, p, pid):
    real, threads = pr.admit, []

    def admit(*a, **k):
        t = threading.Thread(target=pr.dismiss, args=(p, pid, "not now"))
        t.start()
        t.join(1.0)                                                         # the dismissal lands in the pass, if it can
        threads.append(t)
        return real(*a, **k)
    monkeypatch.setattr(pr, "admit", admit)
    return threads


def test_a_dismissal_during_the_structural_pass_is_kept(tmp_path, monkeypatch):
    p, s = aux_project(tmp_path)
    threads = _dismiss_inside(monkeypatch, p, s["id"])
    rv.refresh(p, p.model.spec, force=True)
    for t in threads:
        t.join(10)
    assert threads and pr.changes(p)[s["id"]][0] == "dismissed"


def test_a_dismissal_during_the_estimators_pass_is_kept(tmp_path, monkeypatch):
    p, now = factory(tmp_path)
    [a] = pr.make(p, snap(now, now))
    threads = _dismiss_inside(monkeypatch, p, a["id"])
    pr.make(p, snap(now, now))
    for t in threads:
        t.join(10)
    assert threads and pr.changes(p)[a["id"]][0] == "dismissed"


def test_an_edit_during_the_estimators_pass_defers_it(tmp_path, monkeypatch):
    p, now = factory(tmp_path)
    real = es.estimate

    def estimate(*a, **k):
        got = real(*a, **k)
        edit(p, "parameters:\n", "parameters:\n  other:\n    value: 5\n")
        return got
    monkeypatch.setattr(es, "estimate", estimate)
    pr.make(p, snap(now, now))
    assert events(p) == []


# ---- made again on its id: clean

def test_a_change_made_again_on_its_id_starts_clean(tmp_path):
    p, _ = long_queue(tmp_path)
    pid = "remade01"
    pr.event(p, pid, "made", {"kind": "parameter", "title": "k is 3", "made_by": "ergostat", "version": "v0", "revisions": 2})
    pr.event(p, pid, "checked", {})
    pr.event(p, pid, "testing", {"looked": 60.0})
    pr.event(p, pid, "passed", {"verdict": {"verdict": "passed", "why": "old"}})
    pr.event(p, pid, "superseded", {"why": "what it is about changed", "version_now": "v1"})
    pr.save(p, {pid: {"id": pid, "kind": "parameter", "title": "k is 3 again", "status": "pending",
                      "version": ver.version(p.model.spec)}})
    x = pr.stored(p)[pid]
    assert x["state"] == "checked" and x["title"] == "k is 3 again"
    for k in ("why", "version_now", "verdict", "looked", "revisions"):
        assert x.get(k) is None, k
