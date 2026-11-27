"""A change found for a remote's part, written as text for that remote's owner (SPEC §4c, "Proposals for its owner";
docs/roadmap/overnight/remote-proposals-text.md): in the remote's names, against the version read, never applied
here, never sent."""

from __future__ import annotations

import json
import os
import re
import threading
import time

import pytest

from ergostat import model as mdl
from ergostat.cli import main
from ergostat.numbers import proposals as pr
from ergostat.numbers import remote_text as rt
from ergostat.remote import cache
from ergostat.store import Project
from tests.test_remote import served_into, write

REM = """\
name: incidents
parameters:
  review-time:
    value: 120s
    estimate: true
stocks:
  review-asked:
    unit: tickets
    sensor:
      manual: true
flows:
  asked:
    to: review-asked
    sensor:
      manual: true
  review:
    from: review-asked
    driven-by: +stock.review-asked
    equation: stock.review-asked / review-time
"""
EQ = """\
name: incidents
parameters:
  time-in-queue: {value: 1}
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
    driven-by: +stock.queue
    sensor:
      manual: true
"""
LOCAL = """\
name: support
systems:
  incidents:
    remote:
      url: http://127.0.0.1:1
      token-file: incidents.token
parameters:
  k:
    value: 2
stocks:
  tickets:
    sensor: {manual: true}
flows:
  filed:
    to: tickets
    equation: k
"""
FIT_KEYS = ("fit_before", "fit_after", "gate", "neighbourhood", "objective", "estimate", "predicted", "fit_gained",
            "held_before", "held_after", "edit", "previous", "parameters", "version")
DECIDED = ("by", "decided", "applied", "edit", "dismissed_because", "dismissed_by", "revisions", "verdict", "why")


def _project(tmp_path, text=REM, local=LOCAL):
    d = tmp_path / "support"
    write(d, local)
    body = served_into(d, tmp_path, text=text)
    return Project(mdl.load(d)), body


def _queue_readings(p, now):
    """The review queue as the remote's sensors read it, mirrored here (a reviewer takes five minutes; it says two)."""
    q = 3.0
    for i in range(int(8 * 3600 / 30)):
        t = now - 5 * 3600 + i * 30
        a = 20 + 8 * ((i // 40) % 2)
        if abs(t - (now - 40 * 60)) < 15:
            q += 130
            a += 130 * 3600 / 30
        p.measurements.add("sensor/incidents-review-asked.main", q, at=t)
        p.measurements.add("sensor/incidents-asked.main", a, at=t)
        for _ in range(30):
            q += (a / 3600 if a < 1000 else 0) - q / 300.0


def _snap(now):
    return {"at": now, "window": 4 * 3600, "starts": now - 5 * 3600}


def _made(tmp_path, **kw):
    p, body = _project(tmp_path, **kw)
    now = time.time()
    _queue_readings(p, now)
    pr.make(p, _snap(now))
    return p, body, now


def _texts(p):
    return {k: x for k, x in pr.stored(p).items() if x.get("for_remote")}


def _evs(p, pid):
    return p.events.query(n=None, type="ergostat.model-change.*", item=pr.item_of(pid))


def _states(p, pid):
    return [e["type"].rsplit(".", 1)[1] for e in _evs(p, pid)]


def _dir(p):
    return p.dir / "remotes" / "incidents"


def _set_version(p, v):
    f = _dir(p) / cache.MODEL
    got = json.loads(f.read_text())
    if v is None:
        got.pop("version", None)
    else:
        got["version"] = v
    f.write_text(json.dumps(got))


def _blocked(start, timeout=0.5):
    """A thread started now, and whether it is still waiting after ``timeout`` (it runs nothing slow of its own)."""
    t = threading.Thread(target=start, daemon=True)
    t.start()
    t.join(timeout)
    return t, t.is_alive()


def test_an_estimate_of_a_remote_parameter_is_written_as_text_for_its_owner(tmp_path):
    from ergostat.inbox import entries as en
    p, body, _ = _made(tmp_path)
    [(pid, x)] = _texts(p).items()
    assert x["for_remote"]["remote"] == "incidents" and x["for_remote"]["version"] == body["version"]
    assert x["for_remote"]["parts"]["parameter.incidents-review-time"] == "parameter.review-time"
    assert set(x["for_remote"]["parts"].values()) == {"parameter.review-time", "flow.review", "stock.review-asked"}
    assert "parameter.review-time" in x["text"] and "incidents-" not in x["text"]
    assert re.search(r"from 2m to \S+ ± \S+", x["text"]) and x["state"] == "checked"
    assert pid not in {y["id"] for y in pr.pending(p)} and not pr.pending(p)
    assert not [e for e in en.entries(p, p.model.spec) if pid in e["id"]]


def test_an_equation_for_a_remote_flow_is_written_in_the_remotes_names(tmp_path):
    p, body = _project(tmp_path, text=EQ)
    now = time.time()
    q = 0.0
    for i in range(121):
        t = now - 3600 + i * 30
        a = 10 + 5 * ((i // 20) % 2)
        for name, v in (("queue.main", q), ("arrivals.main", a), ("served.main", 3 * q)):
            p.measurements.add(f"sensor/incidents-{name}", v, at=t)
        for _ in range(30):
            q += (a - 3 * q) / 3600
    pr.make(p, {"at": now, "window": 3600.0, "starts": now - 3600})
    [x] = _texts(p).values()
    assert x["kind"] == "equation" and "incidents-" not in x["text"] and "incidents-" not in x["title"]
    secs = body["sections"]
    for kind, name in re.findall(r"\b(stock|flow|auxiliary|parameter)\.([a-z0-9-]+)", x["text"]):
        assert name in secs[{"stock": "stocks", "flow": "flows", "auxiliary": "auxiliaries",
                             "parameter": "parameters"}[kind]], (kind, name)
    # time-in-queue is the remote's own parameter already: the new one is made free against its names
    assert "flow.served the equation stock.queue / time-in-queue-2" in x["text"] and "time-in-queue-2 = " in x["text"]
    assert x["evidence"]["read"] == ["flow.served", "stock.queue"] and x["evidence"]["points"] > 100


def test_an_equations_new_parameter_names_are_built_from_the_remote_names(tmp_path):
    p, _ = _project(tmp_path, text=EQ.replace("+stock.queue", "[+stock.queue, +flow.arrivals]"))
    spec = p.model.spec
    x = {"id": "e1", "kind": "equation", "target": "flow.incidents-served", "parts": ["flow.incidents-served"],
         "equation": "MAX(0, stock.incidents-queue * (1 / time-in-incidents-queue + incidents-served-per-incidents-arrivals"
                     " * flow.incidents-arrivals))",
         "parameters": {"time-in-incidents-queue": {"value": 0.5, "unit": "h"},
                        "incidents-served-per-incidents-arrivals": {"value": 0.01, "unit": "1/job"}},
         "for_text": {"roles": {"time-in-incidents-queue": ["time-in", "stock.incidents-queue"],
                                "incidents-served-per-incidents-arrivals": ["per", "flow.incidents-arrivals"]},
                      "points": 50}}
    got = rt.text_of(spec, x, 3600.0)
    assert "MAX(0, stock.queue * (1 / time-in-queue-2 + served-per-arrivals * flow.arrivals))" in got["text"]
    assert "incidents-" not in got["text"]


def test_new_names_are_free_against_every_parameter_served_even_those_left_out_by_systems(tmp_path):
    """systems: [ops] brings in none of the remote's model-level parameters, but time-in-queue is still its name."""
    two = EQ.replace("name: incidents\n", "name: incidents\nsystems:\n  ops: {}\n").replace(
        "    unit: jobs\n", "    unit: jobs\n    system: ops\n").replace(
        "    to: queue\n", "    to: queue\n    system: ops\n").replace(
        "    from: queue\n", "    from: queue\n    system: ops\n")
    local = LOCAL.replace("      token-file: incidents.token\n", "      token-file: incidents.token\n      systems: [ops]\n")
    p, _ = _project(tmp_path, text=two, local=local)
    spec = p.model.spec
    assert "parameter.incidents-time-in-queue" not in spec.remotes["incidents"]["names"]   # narrowed away here
    x = {"id": "e1", "kind": "equation", "target": "flow.incidents-served", "parts": ["flow.incidents-served"],
         "equation": "stock.incidents-queue / time-in-incidents-queue",
         "parameters": {"time-in-incidents-queue": {"value": 0.5, "unit": "h"}},
         "for_text": {"roles": {"time-in-incidents-queue": ["time-in", "stock.incidents-queue"]}, "points": 50}}
    got = rt.text_of(spec, x, 3600.0)
    assert "stock.queue / time-in-queue-2" in got["text"] and "time-in-queue = " not in got["text"]
    spec.remotes["incidents"].pop("served_parameters")                 # not known: nothing is written
    assert isinstance(rt.text_of(spec, x, 3600.0), str)


def test_a_for_remote_record_stores_no_fit_field(tmp_path):
    p, _, _ = _made(tmp_path)
    [(pid, x)] = _texts(p).items()
    [made] = [e for e in _evs(p, pid) if e["type"].endswith(".made")]
    assert set(made["data"]) <= set(rt.FIELDS)
    assert not [k for k in FIT_KEYS if x.get(k) is not None]
    no_se = x["text"].replace("standard error", "")
    for word in ("R²", "%", "fit", "error", "variation", "gate"):
        assert word not in no_se, word


def test_a_proposal_of_local_and_remote_parts_or_two_remotes_is_not_written_for_remote(tmp_path):
    d = tmp_path / "support"
    write(d, LOCAL.replace("systems:\n", "systems:\n  other:\n    remote:\n      url: http://127.0.0.1:2\n", 1))
    served_into(d, tmp_path, text=REM)
    served_into(d, tmp_path / "o", remote="other", text=REM.replace("name: incidents", "name: other"))
    p = Project(mdl.load(d))
    spec = p.model.spec
    mixed = {"id": "aaaa0001", "kind": "parameter", "parameters": {"incidents-review-time": 0.1, "k": 3.0},
             "edit": {"error": "parameter incidents-review-time belongs to remote incidents"}, "title": "t"}
    two = {**mixed, "id": "aaaa0002", "parameters": {"incidents-review-time": 0.1, "other-review-time": 0.1}}
    assert rt.owner_of(spec, rt.edited(mixed)) is None and rt.owner_of(spec, rt.edited(two)) is None
    local, texts = rt.split(spec, [dict(mixed), dict(two)], 3600.0)
    assert [x["id"] for x in local] == ["aaaa0001", "aaaa0002"] and texts == {}
    from ergostat.numbers import version as ver
    pr.save(p, {x["id"]: {**x, "status": "pending", "version": ver.version(spec), "structure": ver.structure(spec)}
                for x in local})
    for pid in ("aaaa0001", "aaaa0002"):
        x = pr.stored(p)[pid]
        assert x["edit"].get("error") and not x.get("for_remote")
        with pytest.raises(pr.ProposalError, match="its edit cannot be made by ergostat"):
            pr.accept(p, pid, _snap(time.time()))


@pytest.mark.parametrize("case", ["never-read", "file-removed", "no-version", "differs"])
def test_recording_refuses_when_the_remotes_version_cannot_be_read(tmp_path, monkeypatch, case):
    p, _ = _project(tmp_path)
    now = time.time()
    _queue_readings(p, now)
    if case == "never-read":
        p.model.spec.remotes["incidents"]["version"] = None
    real, real_folder, seen = rt.split, rt.folder, {}

    def split(spec, found, window):
        got = real(spec, found, window)
        assert got[1], "the finder found a text to write"
        seen["found"] = True
        return got

    def folder(p_, spec, remote):                         # the step just before the record's lock: after the find
        if seen.pop("found", None):
            f = _dir(p) / cache.MODEL
            if case == "file-removed":
                f.unlink()
            elif case == "no-version":
                _set_version(p, None)
            elif case == "differs":
                _set_version(p, "another")
            seen["changed"] = True
        return real_folder(p_, spec, remote)
    monkeypatch.setattr(rt, "split", split)
    monkeypatch.setattr(rt, "folder", folder)
    pr.make(p, _snap(now))
    assert seen.get("changed") and not p.events.query(n=None, type="ergostat.model-change.*")


def test_a_name_lookup_miss_refuses_and_never_uses_the_local_name(tmp_path, monkeypatch):
    p, _ = _project(tmp_path)
    now = time.time()
    _queue_readings(p, now)
    real = rt.split
    monkeypatch.setattr(rt, "split", lambda spec, found, w: ([{k: v for k, v in x.items() if k != "for_text"}
                                                             for x in found], {}))
    pr.make(p, _snap(now))                                # as before: a local record whose edit is an error
    [(pid, was)] = pr.stored(p).items()
    assert was["edit"].get("error") and not was.get("for_remote")
    n = len(p.events.query(n=None))
    monkeypatch.setattr(rt, "split", real)
    del p.model.spec.remotes["incidents"]["names"]["stock.incidents-review-asked"]
    pr.make(p, _snap(now))
    assert not _texts(p) and pr.stored(p)[pid]["edit"] == was["edit"]      # left exactly as it was
    assert len(_evs(p, pid)) == 2 and len(p.events.query(n=None)) >= n
    for e in p.events.query(n=None, type="ergostat.model-change.*"):
        assert "incidents-" not in str((e.get("data") or {}).get("text") or "")
    x = {"id": "s1", "kind": "parameter", "parameters": {"incidents-review-time": 0.1}, "uncertainty": {},
         "parts": [], "touched": ["stock.incidents-gone"], "estimate": {}}
    assert isinstance(rt.text_of(p.model.spec, x, 3600.0), str)                 # a stand-in is never served


def test_current_needs_both_versions_read_and_equal():
    class S:
        remotes = {"incidents": {"version": "A"}, "blank": {"version": None}}

    def x(remote, v):
        return {"for_remote": {"remote": remote, "version": v}}
    assert rt.current(x("incidents", "A"), S)
    assert not rt.current(x("incidents", None), S)          # record None
    assert not rt.current(x("blank", "A"), S)               # spec None
    assert not rt.current(x("blank", None), S)              # both None
    assert not rt.current(x("gone", None), S) and not rt.current(x("gone", "A"), S)   # remote absent
    assert not rt.current(x("incidents", "B"), S)
    assert not rt.current(x("blank", ""), S) and not rt.current({}, S)


def test_a_moved_remote_version_supersedes_and_an_unreadable_one_only_marks_not_current(tmp_path):
    p, body, _ = _made(tmp_path / "a")
    [pid] = _texts(p)
    _set_version(p, "moved-on")
    assert pid in pr.supersede(p, p.model.spec)
    st, f = pr.changes(p)[pid]
    assert st == "superseded" and body["version"] in f["why"] and "moved-on" in f["why"] and f["version_now"] == "moved-on"
    p, body, _ = _made(tmp_path / "b")
    [pid] = _texts(p)
    (_dir(p) / cache.MODEL).unlink()
    assert pid not in pr.supersede(p, p.model.spec)
    assert pr.changes(p)[pid][0] == "checked"
    rows, unread = rt.listing(p, p.model.spec)
    assert [r["id"] for r in rows] == [pid] and not rows[0]["current"] and "can't be read" in rows[0]["not_current_because"]
    assert unread == ["incidents"]


def _fake_refresh(p, monkeypatch, body, v):
    (p.model.path.parent / "incidents.token").write_text("tok")
    monkeypatch.setattr(cache.client, "get", lambda *a, **k: (200, {**body, "version": v}, None, ""))
    info = p.model.spec.remotes["incidents"]
    return lambda: cache.refresh(_dir(p), info["url"], info["token_file"], p.model.path.parent, 60.0, force=True)


def test_recording_holds_both_locks_across_read_compare_write(tmp_path, monkeypatch):
    p, body = _project(tmp_path)
    now = time.time()
    _queue_readings(p, now)
    refresh = _fake_refresh(p, monkeypatch, body, "B")
    seen, real_same, real_add = {}, rt._same, p.events.add

    def same(a, b):
        if "thread" not in seen and a is not None:
            seen["thread"], seen["blocked"] = _blocked(refresh)
        return real_same(a, b)

    def add(type, **kw):
        if type.endswith("model-change.made"):
            seen["file_at_append"] = cache.version(_dir(p))
            seen["alive_at_append"] = seen["thread"].is_alive()
        return real_add(type, **kw)
    monkeypatch.setattr(rt, "_same", same)
    monkeypatch.setattr(p.events, "add", add)
    pr.make(p, _snap(now))
    seen["thread"].join(5)
    assert seen["blocked"] and seen["alive_at_append"] and seen["file_at_append"] == body["version"]
    [x] = _texts(p).values()
    assert cache.version(_dir(p)) == "B"
    p.model = mdl.load(p.model.path.parent)
    assert not rt.current(x, p.model.spec)


def test_superseding_a_for_remote_record_holds_both_locks(tmp_path, monkeypatch):
    p, body, _ = _made(tmp_path)
    [pid] = _texts(p)
    _set_version(p, "B")
    refresh = _fake_refresh(p, monkeypatch, body, "C")
    seen, real_differ, real_add = {}, rt._differ, p.events.add

    def differ(a, b):
        seen["thread"], seen["blocked"] = _blocked(refresh)
        return real_differ(a, b)

    def add(type, **kw):
        if type.endswith("model-change.superseded"):
            seen["file"], seen["said"] = cache.version(_dir(p)), kw["data"]["version_now"]
        return real_add(type, **kw)
    monkeypatch.setattr(rt, "_differ", differ)
    monkeypatch.setattr(p.events, "add", add)
    assert pr.supersede(p, p.model.spec) == [pid]
    seen["thread"].join(5)
    assert seen["blocked"] and seen["said"] == seen["file"] == "B" and cache.version(_dir(p)) == "C"


def _local_pending(p):
    """A change of this model's own, waiting, with an edit (the owner's what-if on k)."""
    return pr.propose_values(p, {"k": "3"}, _snap(time.time()))


def _as_text(p, pid, text="set parameter.review-time from 2m to 5m."):
    spec = p.model.spec
    v = spec.remotes["incidents"]["version"]
    now = time.time()
    return {"id": pid, "kind": "parameter", "title": "incidents: parameter.review-time", "text": text,
            "evidence": {"points": 9, "window": 3600.0, "read": ["stock.review-asked"]},
            "for_remote": {"remote": "incidents", "version": v,
                           "parts": {"parameter.incidents-review-time": "parameter.review-time"}},
            "subject": pr.subject(spec, ["parameter.incidents-review-time"]), "made_by": "ergostat",
            "created": now, "made": now}


def _no_decision(x):
    assert x.get("for_remote") and x["state"] == "checked" and x["status"] == "pending"
    assert not [k for k in DECIDED if x.get(k) is not None], {k: x.get(k) for k in DECIDED}
    assert not [k for k, v in x.items() if v is not None and k not in (*rt.FIELDS, "id", "state", "status")]


def test_an_accept_racing_a_remake_as_for_remote_under_the_same_id(tmp_path, monkeypatch):
    from ergostat.numbers import fit as ft
    p, _ = _project(tmp_path)
    x = _local_pending(p)
    pid, spec = x["id"], p.model.spec
    order, seen, real_compute, real_add = [], {}, ft.compute, p.events.add

    def compute(*a, **k):
        if "thread" not in seen:
            seen["thread"], seen["blocked"] = _blocked(lambda: rt.record(p, spec, [_as_text(p, pid)]))
        return real_compute(*a, **k)

    def add(type, **kw):
        order.append((type, threading.current_thread() is not threading.main_thread()))
        return real_add(type, **kw)
    monkeypatch.setattr(ft, "compute", compute)
    monkeypatch.setattr(p.events, "add", add)
    pr.accept(p, pid, _snap(time.time()))
    seen["thread"].join(5)
    assert seen["blocked"]
    mine = [i for i, (_, other) in enumerate(order) if other]
    assert mine and min(mine) > max(i for i, (t, other) in enumerate(order) if not other and
                                    t in ("ergostat.model.changed", "ergostat.model-change.accepted"))
    _no_decision(pr.stored(p)[pid])
    assert [h["proposal"] for h in pr.accepted(p)] == [pid]


@pytest.mark.parametrize("how", ["accepted", "dismissed", "refused"])
def test_a_local_accepted_proposal_remade_as_for_remote_keeps_no_decision(tmp_path, how):
    p, _ = _project(tmp_path)
    x = _local_pending(p)
    pid = x["id"]
    if how == "accepted":
        pr.accept(p, pid, _snap(time.time()))
        p.model = mdl.load(p.model.path.parent)
    elif how == "dismissed":
        pr.dismiss(p, pid, "not now")
        assert pr.stored(p)[pid]["dismissed_because"] == "not now"
    else:
        props = pr.stored(p)
        props[pid] = {**props[pid], "status": "refused", "state": "refused", "why": "worse", "decided": time.time()}
        pr.save(p, props)
    assert pr.stored(p)[pid]["status"] == how
    assert rt.record(p, p.model.spec, [_as_text(p, pid)]) == [pid]
    _no_decision(pr.stored(p)[pid])
    assert _states(p, pid)[-3:] == ["superseded", "made", "checked"]


def test_a_for_remote_proposal_remade_as_local_loses_for_remote_and_its_version(tmp_path, monkeypatch):
    p, _, now = _made(tmp_path)
    [pid] = _texts(p)
    real_admit, seen, order, real_add = pr.admit, {}, [], p.events.add
    spec = p.model.spec

    def admit(*a, **k):
        seen["thread"], seen["blocked"] = _blocked(lambda: rt.record(p, spec, [_as_text(p, pid, "again")]))
        return real_admit(*a, **k)

    def add(type, **kw):
        order.append((type.rsplit(".", 1)[1], threading.current_thread() is not threading.main_thread()))
        return real_add(type, **kw)
    # its part made this model's own: the finder's proposal is kept as a local one
    monkeypatch.setattr(rt, "split", lambda spec, found, w: ([{k: v for k, v in x.items() if k != "for_text"}
                                                             for x in found], {}))
    monkeypatch.setattr(pr, "admit", admit)
    monkeypatch.setattr(p.events, "add", add)
    pr.make(p, _snap(now))
    assert seen["blocked"]
    # the remake, as one: superseded, made, checked; the racing record only after it
    assert order[:3] == [("superseded", False), ("made", False), ("checked", False)], order
    seen["thread"].join(5)
    assert [o for o in order if o[1]] == [("superseded", True), ("made", True), ("checked", True)]
    # as the remake left it (read from its own events): no for_remote, text or evidence; an edit and a version
    local = p.events.query(n=None, type="ergostat.model-change.made", item=pr.item_of(pid))[-2]
    assert local["data"]["for_remote"] is None and local["data"]["text"] is None and local["data"]["evidence"] is None
    assert local["data"]["version"] and local["data"]["edit"]


def test_the_remade_local_record_folds_with_no_for_remote(tmp_path, monkeypatch):
    p, _, now = _made(tmp_path)
    [pid] = _texts(p)
    monkeypatch.setattr(rt, "split", lambda spec, found, w: ([{k: v for k, v in x.items() if k != "for_text"}
                                                             for x in found], {}))
    pr.make(p, _snap(now))
    x = pr.stored(p)[pid]
    assert not [k for k in ("for_remote", "text", "evidence") if x.get(k) is not None]
    assert x["version"] and x["status"] == "pending" and x["edit"].get("error")


def test_cli_accept_refuses_a_for_remote_proposal(tmp_path, capsys):
    p, _, _ = _made(tmp_path)
    [pid] = _texts(p)
    f = p.model.path
    before = f.read_bytes()
    capsys.readouterr()
    assert main(["-C", str(f.parent), "accept", pid]) != 0
    err = capsys.readouterr().err
    assert "text for remote incidents's owner" in err and "never applied here" in err
    assert f.read_bytes() == before


def test_the_web_accept_endpoint_refuses_a_for_remote_proposal(tmp_path):
    from ergostat.web.numbers_api import post
    from ergostat.web.server import Live
    p, _, _ = _made(tmp_path)
    [pid] = _texts(p)
    f = p.model.path
    before = f.read_bytes()
    live = Live(p)
    code, got = post(live, f"proposals/{pid}/accept", 3600.0)
    assert code == 409 and "text for remote incidents's owner" in got["error"] and f.read_bytes() == before
    code, got = post(live, f"proposals/{pid}/dismiss", 3600.0, {"reason": ["no"]})
    assert code == 200 and pr.stored(p)[pid]["status"] == "dismissed"


def test_the_judges_auto_accept_never_applies_a_for_remote_proposal(tmp_path):
    from ergostat.numbers import judge as jd
    p, _, now = _made(tmp_path)
    [pid] = _texts(p)
    pr.event(p, pid, "passed", {})
    p.model.spec.improve.accept = {k: "auto" for k in p.model.spec.improve.accept}
    before = p.model.path.read_bytes()
    jd.run(p, by="judge")
    assert pr.stored(p)[pid]["status"] == "pending" and not pr.accepted(p)
    with pytest.raises(pr.ProposalError, match="text for remote incidents's owner"):
        pr.accept(p, pid, _snap(now), by="judge", policy="judge judge: accept parameter: auto")   # its accept step
    assert p.model.path.read_bytes() == before


def test_the_inbox_answer_refuses_a_for_remote_proposal(tmp_path, monkeypatch):
    from ergostat.inbox import answer as an
    from ergostat.inbox import entries as en
    p, _, _ = _made(tmp_path)
    [pid] = _texts(p)
    with pytest.raises(an.AnswerError, match="nothing waiting"):          # never offered
        an.answer(p, p.model.spec, f"change/{pid}", "approve")
    monkeypatch.setattr(en, "find", lambda p, spec, eid: {"id": f"change/{pid}", "kind": "change",
                                                          "verbs": ["approve", "deny"], "summary": ""})
    with pytest.raises(an.AnswerError, match="text for remote incidents's owner"):
        an.answer(p, p.model.spec, f"change/{pid}", "approve")


def test_the_bench_adapter_accept_refuses_a_for_remote_proposal(tmp_path):
    from ergostat.bench.adapter import Loop
    p, _, _ = _made(tmp_path)
    [pid] = _texts(p)
    before = p.model.path.read_bytes()
    with pytest.raises(pr.ProposalError, match="text for remote incidents's owner"):
        Loop(p).accept(pid)
    assert p.model.path.read_bytes() == before


def test_ergostat_sends_nothing_for_a_for_remote_proposal(tmp_path, monkeypatch, capsys):
    import urllib.parse
    import urllib.request
    p, body = _project(tmp_path)
    d = p.model.path.parent
    (d / "incidents.token").write_text("tok")
    asked = []

    class R:
        status = 200
        headers = {"ETag": body["version"]}

        def __init__(self, b):
            self.b = b

        def read(self, n=-1):                      # client.get reads at most BODY_MOST + 1
            return self.b if n < 0 else self.b[:n]

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    real, vm = urllib.request.urlopen, os.environ["ERGOSTAT_METRICS_URL"]

    def urlopen(req, timeout=None):
        if req.full_url.startswith(vm):                # (the readings' store: this test's own VictoriaMetrics)
            return real(req, timeout=timeout)
        asked.append(req)
        return R(json.dumps({**body} if req.full_url.split("?")[0].endswith("/model") else {}).encode())
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    st = json.loads((_dir(p) / cache.STATUS).read_text())
    (_dir(p) / cache.STATUS).write_text(json.dumps({**st, "next": 0}))          # the cache due
    p = Project(mdl.load(d))
    now = time.time()
    _queue_readings(p, now)
    pr.make(p, _snap(now))
    [x] = _texts(p).values()
    assert main(["-C", str(d), "remote", "proposals"]) == 0
    assert asked
    for r in asked:
        said = urllib.parse.unquote_plus(r.full_url) + json.dumps(dict(r.header_items()))
        assert r.get_method() == "GET" and r.data is None and "/api/remote/v1/" in r.full_url
        assert x["text"] not in said and "review-time from" not in said


def test_remote_proposals_lists_text_and_json(tmp_path, capsys):
    p, body, _ = _made(tmp_path)
    [pid] = _texts(p)
    d = p.model.path.parent
    for f in (_dir(p) / cache.LOCK, p.dir / "proposals.lock"):
        f.unlink(missing_ok=True)
    n = len(p.events.query(n=None))
    capsys.readouterr()
    assert main(["-C", str(d), "remote", "proposals"]) == 0
    out = capsys.readouterr().out
    assert pid in out and "incidents" in out and body["version"] in out and "current" in out
    assert pr.stored(p)[pid]["text"] in out
    assert main(["-C", str(d), "remote", "proposals", "incidents", "--json"]) == 0
    [row] = json.loads(capsys.readouterr().out)
    assert row["id"] == pid and row["current"] and row["for_remote"]["remote"] == "incidents"
    assert main(["-C", str(d), "remote", "proposals", "nothing"]) == 2
    assert "incidents" in capsys.readouterr().err
    assert len(p.events.query(n=None)) == n
    assert not (_dir(p) / cache.LOCK).exists() and not (p.dir / "proposals.lock").exists()
    assert main(["-C", str(d), "proposals", "--stored"]) == 0
    assert "1 written for remotes' owners: ergostat remote proposals" in capsys.readouterr().out
    for f in (_dir(p) / cache.LOCK, p.dir / "proposals.lock"):
        f.unlink(missing_ok=True)
    n = len(p.events.query(n=None))
    _set_version(p, None)
    capsys.readouterr()
    assert main(["-C", str(d), "remote", "proposals"]) == 0
    out = capsys.readouterr().out
    assert "remote incidents: its model's version can't be read, so nothing is written for it" in out
    assert "not current" in out and "can't be read" in out
    assert len(p.events.query(n=None)) == n
    assert not (_dir(p) / cache.LOCK).exists() and not (p.dir / "proposals.lock").exists()


def test_a_dismissed_for_remote_proposal_is_not_written_again_at_the_same_remote_version(tmp_path, monkeypatch):
    p, body, now = _made(tmp_path)
    [pid] = _texts(p)
    pr.dismiss(p, pid, "they know")
    n = len(_evs(p, pid))
    pr.make(p, _snap(now))
    assert len(_evs(p, pid)) == n and pr.stored(p)[pid]["status"] == "dismissed"
    # found again as it was (open, same version, same text): left alone; another text there: written again
    assert rt.record(p, p.model.spec, [_as_text(p, pid)]) == []
    # at a new version of the remote's model: written again, open, nothing of the dismissal kept
    served_into(p.model.path.parent, tmp_path / "v2", text=REM.replace("value: 120s", "value: 120s\n    description: x"))
    p.model = mdl.load(p.model.path.parent)
    assert p.model.spec.remotes["incidents"]["version"] != body["version"]
    pr.make(p, _snap(now))
    x = pr.stored(p)[pid]
    _no_decision(x)
    assert x["for_remote"]["version"] == p.model.spec.remotes["incidents"]["version"]


def test_a_for_remote_record_found_again_with_another_text_is_remade(tmp_path):
    p, _, _ = _made(tmp_path)
    [pid] = _texts(p)
    n = len(_evs(p, pid))
    assert rt.record(p, p.model.spec, [_as_text(p, pid)]) == [pid]     # same version, another text: every field again
    x = pr.stored(p)[pid]
    assert x["text"] == _as_text(p, pid)["text"] and _states(p, pid)[n:] == ["made", "checked"]
    _no_decision(x)


def test_a_bad_remote_name_never_builds_a_lock_path(tmp_path):
    p, _ = _project(tmp_path)
    for bad in ("../x", "", "A", "a/b", None, "-x"):
        assert rt.folder(p, p.model.spec, bad) is None
    assert rt.folder(p, p.model.spec, "incidents") == _dir(p).resolve()
