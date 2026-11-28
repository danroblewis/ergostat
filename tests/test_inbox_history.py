"""The inbox's history (SPEC §12o): each thing asked of a person an item of the built-in projection ergostat.inbox,
asked once, answered by whoever answered it (with by and note), or superseded; listed by the Events query."""

from __future__ import annotations

from ergostat.actions import gate, record
from ergostat.cli import main as cli
from ergostat.eventquery import as_query, events_matching
from ergostat.inbox import entries, history
from ergostat.numbers import proposals as pr
from ergostat.spec import items as its
from ergostat.spec.ir import INBOX
from ergostat.web import actions_api

from .test_inbox import project, seed


def decisions(p) -> dict:
    _, _, got = its.in_states(p.events, p.model.spec, INBOX, None, items=True)
    return {i.id.split("/", 1)[1]: i for i in got}


def asked(p) -> list[dict]:
    return p.events.query(n=None, type=f"{INBOX}.asked")


def test_an_entry_is_asked_once_however_often_it_is_listed(tmp_path):
    p, snap = project(tmp_path)
    seed(p, snap)
    es = entries.entries(p)
    for _ in range(3):
        entries.entries(p)
        actions_api.inbox(p)
    assert sorted(e["item"] for e in asked(p)) == sorted(f"{INBOX}/{e['id']}" for e in es)
    ds = decisions(p)
    assert {k for k, d in ds.items() if d.state == "waiting"} == {e["id"] for e in es}   # never disagree
    one = ds[next(e["id"] for e in es if e["kind"] == "change")]
    assert one.fields["summary"].startswith("model change") and one.fields["class"] == "change:parameter"
    assert one.fields["link"].startswith("/") and one.fields["asked"] > 0
    history.sync(p, p.model.spec, entries.entries(p))                 # a second writer: the same event, not another
    assert len(asked(p)) == len(es)


def test_answers_from_the_cli_and_the_page_say_by_and_note(tmp_path, capsys):
    from ergostat.web.server import Live
    p, snap = project(tmp_path)
    got = seed(p, snap)
    entries.entries(p)
    short = record.short(got["action"]["id"])
    assert cli(["-C", str(tmp_path), "inbox", short[:4], "--approve", "--note", "fine"]) == 0
    assert cli(["-C", str(tmp_path), "inbox", "person/reviewer", "--done", "4", "--note", "did four"]) == 0
    code, _ = actions_api.answer(Live(p), "inbox/advise%2Fpusher/deny", {"note": ["not now"]})
    assert code == 200
    entries.entries(p)
    ds = decisions(p)
    a = ds[f"action/{short}"]
    assert (a.state, a.fields["by"], a.fields["note"]) == ("approved", "owner", "fine") and a.fields["answered"]
    person = next(d for k, d in ds.items() if k.startswith("person/"))
    assert (person.state, person.fields["n"], person.fields["note"]) == ("done", 4.0, "did four")
    adv = next(d for k, d in ds.items() if k.startswith("advise/"))
    assert (adv.state, adv.fields["by"], adv.fields["note"]) == ("denied", "owner", "not now")
    assert len(p.events.query(n=None, type=f"{INBOX}.approved")) == 1             # answered once, not again by sync


def test_an_answer_given_elsewhere_is_read_from_its_kind(tmp_path):
    p, snap = project(tmp_path)
    got = seed(p, snap)
    entries.entries(p)
    gate.deny(p, got["action"]["id"], by="someone@example.com", note="no")       # the Actions page, not the inbox
    entries.entries(p)
    d = decisions(p)[f"action/{record.short(got['action']['id'])}"]
    assert (d.state, d.fields["by"], d.fields["note"]) == ("denied", "someone@example.com", "no")


def test_a_superseded_change_is_superseded(tmp_path):
    p, snap = project(tmp_path)
    got = seed(p, snap)
    entries.entries(p)
    pr.event(p, got["change"]["id"], "superseded")
    entries.entries(p)
    d = decisions(p)[f"change/{got['change']['id']}"]
    assert d.state == "superseded" and not d.fields.get("by")


def test_the_events_query_lists_them(tmp_path):
    p, snap = project(tmp_path)
    seed(p, snap)
    entries.entries(p)
    hit, _ = events_matching(p.events, as_query("type.startswith('ergostat.inbox.')"))
    assert len(hit) == 5 and {e["type"] for e in hit} == {f"{INBOX}.asked"}
