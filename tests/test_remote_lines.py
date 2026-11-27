"""Lines in the process map between our items and a remote's (SPEC §4c, §5a): a relation names a remote's projection,
the remote says where each named item was last (``at=``), and the line is drawn from our item's last step to that
step; never gating, never dropped (each link drawn or counted ``unlinked`` by its reason), never ordered by time."""

from __future__ import annotations

import json
import random
import time
from urllib.parse import parse_qs, urlencode

import pytest

from ergostat import model as mdl
from ergostat import precedence as pr
from ergostat import process as pm
from ergostat import spec as sp
from ergostat.remote import compose, tokens
from ergostat.remote import process as rp
from ergostat.spec import items as its
from ergostat.store import Project
from ergostat.web import remote_api
from ergostat.web.server import Live
from tests.test_remote import LOCAL, REMOTE, served_into, write

REMOTE_ITEMS = REMOTE + """
projections:
  incident:
    id: incident/*
    states: [open, fixing, closed]
    on: {incident.opened: open, incident.fixing: fixing, incident.closed: closed}
"""

TICKET = """
projections:
  ticket:
    id: ticket/*
    states: [todo, doing, done]
    on: {ticket.planned: todo, ticket.started: doing, ticket.done: done}
    relations: {RELS}
"""


def local_text(rels="{blocked_by: incidents-incident}", more=""):
    return LOCAL + TICKET.replace("{RELS}", rels) + more


class World:
    """A remote project ``incidents`` (served in process through ``remote_api.answer``) and a local ``support`` whose
    ``ticket`` names its incidents; each GET's params recorded."""

    def __init__(self, tmp_path, monkeypatch, remote=REMOTE_ITEMS, cached=None, local=None, local_kind=False):
        self.tmp, self.mp = tmp_path, monkeypatch
        write(tmp_path / "incidents", remote)
        self.rp = Project(mdl.load(tmp_path / "incidents"))
        self.live = Live(self.rp)
        self.dir = tmp_path / "support"
        write(self.dir, local or local_text())
        served_into(self.dir, tmp_path, text=cached or remote)
        (self.dir / "incidents.token").write_text("tok")
        self.lp = Project(mdl.load(self.dir))
        self.spec = self.lp.model.spec
        assert self.spec is not None
        if not local_kind:
            assert "incidents-incident" not in self.spec.items
        self.asked: list[dict] = []
        self.reply = None                   # a scripted reply: f(real body) -> body, or None for the real one
        self.unreachable = False
        self.remote_most = None             # MOST_NODES while the remote draws its map
        monkeypatch.setattr(rp.client, "get", self.get)
        rp._kept.clear()

    def get(self, url, path, token, params=None, etag=None, timeout=5.0, tls=None):
        self.asked.append(dict(params or {}))
        if self.unreachable:
            return 0, None, None, "unreachable (refused)"
        q = parse_qs(urlencode({k: v for k, v in (params or {}).items() if v is not None}, doseq=True))
        most = pm.MOST_NODES
        if self.remote_most is not None:
            pm.MOST_NODES = self.remote_most
        try:
            code, body = remote_api.answer(self.live, f"v1/{path}", q)
        finally:
            pm.MOST_NODES = most
        body = json.loads(json.dumps(body))
        if self.reply is not None and code == 200:
            body = self.reply(body)
        return code, body, None, ""

    def draw(self, since, until=None):
        until = until or time.time()
        got = pm.process(self.lp.events, self.spec, pm.kinds_of(self.spec, None), since, until)
        return rp.merge(self.spec, got, None, since, None)

    def ats(self):
        return [p["at"] for p in self.asked if p.get("at")]


def remote_edges(out):
    return [e for e in out["edges"] if e.get("remote") and e["kind"] == "related" and e["id"].startswith("x:")]


def conserved(out, name="incidents"):
    r = out["remotes"][name]
    assert r["linked"] + sum(r["unlinked"].values()) == sum(1 for x in out["remote_links"] if x["remote"] == name)
    return r


def a_ticket_at_doing_naming(w, now, target="incident/7", item="ticket/1", rel="blocked_by"):
    w.lp.events.add("ticket.planned", item=item, data={rel: target}, at=now - 600)
    w.lp.events.add("ticket.started", item=item, at=now - 500)


def an_incident_fixing(w, at, item="incident/7"):
    w.rp.events.add("incident.opened", item=item, source="pager", data={}, at=at)
    w.rp.events.add("incident.fixing", item=item, source="pager", data={}, at=at + 10)


# ---- compile


def test_a_relation_may_name_a_remotes_kind(tmp_path, monkeypatch):
    w = World(tmp_path, monkeypatch)
    _, problems = sp.read(w.dir / "ergostat.yaml", extremes=False)
    assert not [p for p in problems if p.level == "error"], problems
    assert not [p for p in problems if p.code == "remote-reference-unresolved"], problems
    r = w.spec.items["ticket"].relations["blocked_by"]
    assert (r.remote, r.there, r.precedence, r.group, r.kinds) == ("incidents", "incident", False, False,
                                                                  ["incidents-incident"])


def test_a_remote_relation_never_gates_but_the_same_relation_does_on_a_local_kind(tmp_path, monkeypatch):
    w = World(tmp_path, monkeypatch)
    now = time.time()
    an_incident_fixing(w, now - 400)                                   # unfinished at the remote
    ev, spec = w.lp.events, w.spec
    ev.add("ticket.planned", item="ticket/1", data={"blocked_by": "incident/7"}, at=now - 100)
    ev.add("ticket.planned", item="ticket/2", at=now - 100)
    st = {x["id"]: x["status"] for x in pr.build(ev, spec, ["ticket"], now, now - 1000)["items"]}
    assert st["ticket/1"] == st["ticket/2"] == "unblocked", st
    todo = [i for i in sorted(its.project(ev, spec, "ticket"), key=lambda i: i.id) if i.state == "todo"]
    assert "ticket/1" in [i.id for i in pr.order_ready(ev, spec, "ticket", todo, now)]
    # the same relation on a local kind whose item is unfinished: blocked, and not taken
    d = tmp_path / "plain"
    write(d, local_text("{blocked_by: epic}", "  epic:\n    id: epic/*\n    states: [planned, shipped]\n"))
    served_into(d, tmp_path, text=REMOTE_ITEMS)
    p = Project(mdl.load(d))
    p.events.add("epic.planned", item="epic/1", at=now - 200)
    p.events.add("ticket.planned", item="ticket/1", data={"blocked_by": "epic/1"}, at=now - 100)
    st = {x["id"]: x["status"] for x in pr.build(p.events, p.model.spec, ["ticket"], now, now - 1000)["items"]}
    assert st["ticket/1"] == "blocked", st
    todo = [i for i in its.project(p.events, p.model.spec, "ticket") if i.state == "todo"]
    assert "ticket/1" not in [i.id for i in pr.order_ready(p.events, p.model.spec, "ticket", todo, now)]


def test_precedence_true_on_a_remote_relation_is_an_error(tmp_path, monkeypatch):
    def errors(rels, more=""):
        write(tmp_path / "support", local_text(rels, more))
        served_into(tmp_path / "support", tmp_path, text=REMOTE_ITEMS)
        _, got = sp.read(tmp_path / "support" / "ergostat.yaml", extremes=False)
        return [p for p in got if p.level == "error"]
    got = errors("{blocked_by: {projection: incidents-incident, precedence: true}}")
    assert [p.code for p in got] == ["remote-relation-precedence"], got
    assert "cannot gate on it" in got[0].message
    got = errors("{blocked_by: [epic, incidents-incident]}", "  epic:\n    id: epic/*\n")
    assert [p.code for p in got] == ["bad-relation"] and "names only that projection" in got[0].message, got
    got = errors("{parent: {projection: incidents-incident, group: true}}")
    assert [p.code for p in got] == ["bad-relation"], got
    assert not errors("{parent: incidents-incident}")                   # parent's default group: not asked for here


def test_a_kind_the_remote_no_longer_serves_is_a_finding_and_draws_no_line(tmp_path, monkeypatch):
    w = World(tmp_path, monkeypatch, remote=REMOTE)                    # served, and as cached: no projection incident
    _, problems = sp.read(w.dir / "ergostat.yaml", extremes=False)
    assert not [p for p in problems if p.level == "error"], problems
    found = [p for p in problems if p.code == "remote-reference-unresolved"]
    assert len(found) == 1 and "has no projection incident" in found[0].message and "(version " in found[0].message
    assert w.spec.items["ticket"].relations["blocked_by"].remote == "incidents"
    now = time.time()
    a_ticket_at_doing_naming(w, now)
    out = w.draw(now - 4000)
    assert not remote_edges(out)
    assert conserved(out)["unlinked"] == {"not-answered": 1}


def test_compile_with_the_remote_never_read_is_a_finding_not_an_error(tmp_path, monkeypatch):
    local = tmp_path / "support"
    write(local, local_text())
    monkeypatch.setattr(compose, "EVERY", 60.0)
    spec, problems = sp.read(local / "ergostat.yaml", extremes=False)      # 127.0.0.1:1 answers nothing, no cache
    assert not [p for p in problems if p.level == "error"], problems
    found = [p for p in problems if p.code == "remote-reference-unresolved" and "incidents-incident" in p.message]
    assert found and "has not been read" in found[0].message
    assert spec.items["ticket"].relations["blocked_by"].remote == "incidents"


# ---- drawn


def test_a_line_is_drawn_from_our_step_to_the_step_their_item_was_last_at(tmp_path, monkeypatch):
    w = World(tmp_path, monkeypatch)
    now = time.time()
    a_ticket_at_doing_naming(w, now)
    an_incident_fixing(w, now - 400)
    out = w.draw(now - 4000)
    got = remote_edges(out)
    assert len(got) == 1, out["edges"]
    e = got[0]
    assert (e["remote"], e["source"], e["target"], e["count"], e["relation"]) == (
        "incidents", "p:ticket:doing", "p:incidents-incident:fixing", 1, "blocked_by")
    r = conserved(out)
    assert r["linked"] == 1 and r["unlinked"] == {}
    assert w.ats() == [["incident/7"]]
    # our own node capped: not drawn here, still counted
    monkeypatch.setattr(pm, "MOST_NODES", 1)
    rp._kept.clear()
    w.remote_most = 60
    out = w.draw(now - 4000)
    assert not remote_edges(out) and conserved(out)["unlinked"] == {"not-drawn-here": 1}


def test_a_local_kind_of_the_same_name_is_not_taken_for_a_remote_line(tmp_path, monkeypatch):
    more = ("  incidents-incident:\n    id: incident/*\n    states: [open, fixing, closed]\n"
            "    on: {incident.opened: open, incident.fixing: fixing}\n")
    w = World(tmp_path, monkeypatch, local=local_text(more=more), local_kind=True)   # the remote serves incident too
    assert "incident" in w.spec.remotes["incidents"]["projections"]
    assert w.spec.items["ticket"].relations["blocked_by"].remote == ""
    now = time.time()
    a_ticket_at_doing_naming(w, now)
    an_incident_fixing(w, now - 400)                                   # at the remote
    w.lp.events.add("incident.opened", item="incident/7", at=now - 300)   # and here, the local kind's
    out = w.draw(now - 4000)
    assert w.asked and not w.ats()
    rel = [e for e in out["edges"] if e["kind"] == "related"]
    assert len(rel) == 1 and "remote" not in rel[0] and rel[0]["target"] == "p:incidents-incident:open", rel
    assert out["remotes"]["incidents"]["linked"] == 0 and out["remotes"]["incidents"]["unlinked"] == {}


def test_an_activity_not_in_the_remotes_drawn_map_is_unlinked(tmp_path, monkeypatch):
    w = World(tmp_path, monkeypatch)
    now = time.time()
    a_ticket_at_doing_naming(w, now)
    an_incident_fixing(w, now - 400)
    w.remote_most = 2                                                  # the remote's start and end only: fixing dropped
    out = w.draw(now - 4000)
    assert "p:incidents-incident:fixing" not in {n["id"] for n in out["nodes"]}
    assert "p:incidents-incident:^" in {n["id"] for n in out["nodes"]}         # its map is drawn, capped
    assert not remote_edges(out)
    assert conserved(out)["unlinked"] == {"not-drawn": 1}


@pytest.mark.parametrize("reply,reason", [
    (lambda b: {k: v for k, v in b.items() if k != "at"}, "not-answered"),
    (lambda b: {**b, "at": [["incident/7", "fixing"]]}, "not-answered"),
    (lambda b: {**b, "at": {}}, "not-answered"),
    (lambda b: {**b, "at": {"incident/7": {"projection": "incident", "activity": 5}}}, "not-answered"),
    (lambda b: {**b, "at": {"incident/7": {"projection": "other", "activity": "fixing"}}}, "other-projection"),
])
def test_a_reply_that_leaves_out_an_id_or_is_malformed_is_unlinked_not_dropped(tmp_path, monkeypatch, reply, reason):
    w = World(tmp_path, monkeypatch)
    now = time.time()
    a_ticket_at_doing_naming(w, now)
    a_ticket_at_doing_naming(w, now, item="ticket/2")
    an_incident_fixing(w, now - 400)
    w.reply = reply
    out = w.draw(now - 4000)
    assert not remote_edges(out)
    assert "p:incidents-incident:fixing" in {n["id"] for n in out["nodes"]}       # the remote's map is drawn
    assert conserved(out)["unlinked"] == {reason: 2}


def test_two_relations_sharing_an_id_ask_it_once_and_are_checked_each(tmp_path, monkeypatch):
    remote = REMOTE_ITEMS + "  page:\n    id: page/*\n"
    w = World(tmp_path, monkeypatch, remote=remote,
              local=local_text("{blocked_by: incidents-incident, relates_to: incidents-page}"))
    now = time.time()
    a_ticket_at_doing_naming(w, now)
    w.lp.events.add("ticket.linked", item="ticket/1", data={"relates_to": "incident/7"}, at=now - 550)
    an_incident_fixing(w, now - 400)
    out = w.draw(now - 4000)
    assert w.ats() == [["incident/7"]]                                 # asked once
    assert [e["relation"] for e in remote_edges(out)] == ["blocked_by"]
    r = conserved(out)
    assert r["linked"] == 1 and r["unlinked"] == {"other-projection": 1}     # the reply checked against each link's kind


def test_an_unreachable_remote_is_ok_false_with_no_lines(tmp_path, monkeypatch):
    w = World(tmp_path, monkeypatch)
    now = time.time()
    a_ticket_at_doing_naming(w, now)
    a_ticket_at_doing_naming(w, now, item="ticket/2", target="incident/8")
    a_ticket_at_doing_naming(w, now, item="ticket/3", target="bad id")
    w.unreachable = True
    out = w.draw(now - 4000)
    r = conserved(out)
    assert r["ok"] is False and "unreachable" in r["why"]
    assert not [x for x in out["nodes"] + out["edges"] if x.get("remote")]
    assert r["unlinked"] == {"unreachable": 2, "bad-id": 1}            # ids are checked first: bad-id wins


def test_an_unreachable_remote_with_a_changed_id_set_still_draws_its_map_as_cached(tmp_path, monkeypatch):
    w = World(tmp_path, monkeypatch)
    now = time.time()
    a_ticket_at_doing_naming(w, now)
    an_incident_fixing(w, now - 400)
    since = now - 4000
    assert len(remote_edges(w.draw(since))) == 1
    w.unreachable = True
    out = w.draw(since)                                                # the same ids: the answer kept
    assert len(remote_edges(out)) == 1
    a_ticket_at_doing_naming(w, now, item="ticket/2", target="incident/8")   # the ids sent change
    out = w.draw(since)
    r = conserved(out)
    assert r["ok"] is False and r.get("cached") is True
    assert "p:incidents-incident:fixing" in {n["id"] for n in out["nodes"]}  # its map as last read
    assert not remote_edges(out) and r["unlinked"] == {"not-answered": 2}  # its at was for other ids
    assert len(rp._kept) <= 32


def test_the_ids_sent_are_distinct_capped_at_200_and_chosen_by_id(tmp_path, monkeypatch):
    now = time.time()
    ids = [f"incident/{k:03d}" for k in range(230)]
    targets = ids + random.Random(1).sample(ids, 18) + ["bad id", "incident/" + "x" * 120]
    assert len(targets) == 250 and len(targets[-1]) == 129
    order = list(range(250))
    random.Random(2).shuffle(order)                                    # made in shuffled order
    for reverse in (True, False):                                      # stamped in reverse id order; then in id order
        w = World(tmp_path / str(reverse), monkeypatch)
        rank = {t: i for i, t in enumerate(sorted(set(targets), reverse=reverse))}
        for n in order:
            w.lp.events.add("ticket.planned", item=f"ticket/{n}", data={"blocked_by": targets[n]},
                            at=now - 3000 + rank[targets[n]])
        out = w.draw(now - 4000)
        sent = w.ats()
        assert sent == [sorted(ids)[:200]], (reverse, sent)            # by id, however they were stamped
        r = conserved(out)
        kept = set(sorted(ids)[200:])
        assert r["unlinked"]["capped"] == sum(1 for t in targets if t in kept)
        assert r["unlinked"]["bad-id"] == 2
    # an id with a comma is sent whole, and answered whole
    w2 = World(tmp_path / "comma", monkeypatch)
    a_ticket_at_doing_naming(w2, now, target="incident/a,b")
    an_incident_fixing(w2, now - 400, item="incident/a,b")
    out = w2.draw(now - 4000)
    assert w2.ats() == [["incident/a,b"]]
    assert len(remote_edges(out)) == 1 and out["remotes"]["incidents"]["linked"] == 1


def test_the_byte_cap_applies_before_the_count_and_the_remote_server_takes_such_a_query(tmp_path, monkeypatch):
    from ergostat.remote import client
    from ergostat.web import serve as web_serve
    from tests.ports import free_port
    ids = [f"incident/{k:04d}" + ":" * 115 for k in range(150)]       # 128 characters, each ":" sent as %3A
    taken, bad, capped = rp.chosen(ids)
    size = lambda xs: len(urlencode({"at": xs}, doseq=True))         # noqa: E731
    assert len(taken) < 150 and taken == sorted(ids)[:len(taken)] and not bad and capped == set(sorted(ids)[len(taken):])
    assert size(taken) <= rp.AT_BYTES < size(sorted(ids)[:len(taken) + 1])
    assert size(taken) > 31_000
    write(tmp_path / "incidents", REMOTE_ITEMS)
    p = Project(mdl.load(tmp_path / "incidents"))
    p.events.add("incident.opened", item=taken[0], at=time.time() - 400)
    p.events.add("incident.fixing", item=taken[0], at=time.time() - 390)
    tok = tokens.issue(p.dir, "support")
    server, url = web_serve(p, free_port())
    try:
        code, body, _, why = client.get(url, "process", tok, {"since": time.time() - 4000, "at": taken}, timeout=30)
    finally:
        server.shutdown()
        server.server_close()
    assert code == 200, why
    assert body["at"] == {taken[0]: {"projection": "incident", "activity": "fixing"}}


def test_the_remote_refuses_more_than_200_ids(tmp_path):
    write(tmp_path / "incidents", REMOTE_ITEMS)
    p = Project(mdl.load(tmp_path / "incidents"))
    now = time.time()
    p.events.add("incident.opened", item="incident/7", at=now - 100)
    live = Live(p)
    many = [f"incident/{k}" for k in range(201)]
    code, body = remote_api.answer(live, "v1/process", {"at": many})
    assert code == 400 and "200" in body["error"]
    code, body = remote_api.answer(live, "v1/process", {"at": many[:200] + many[:5], "since": [str(now - 1000)]})
    assert code == 200 and body["at"] == {"incident/7": {"projection": "incident", "activity": "open"}}
    assert "remote_links" not in body


def test_remote_times_before_or_after_ours_draw_the_same_lines(tmp_path, monkeypatch):
    def lines(d, shift):
        w = World(d, monkeypatch)
        now = time.time()
        for i in range(3):
            a_ticket_at_doing_naming(w, now, item=f"ticket/{i}", target=f"incident/{i}")
            an_incident_fixing(w, now - 500 + shift, item=f"incident/{i}")
        w.rp.events.add("incident.closed", item="incident/2", source="pager", data={}, at=now - 480 + shift)
        out = w.draw(now - 4000)
        return sorted((e["id"], e["source"], e["target"], e["count"]) for e in remote_edges(out))
    before, after = lines(tmp_path / "before", -3000), lines(tmp_path / "after", 100)
    assert before == after and len(before) == 2, (before, after)
