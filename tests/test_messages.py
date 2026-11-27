"""The owner's messages (SPEC §12h): routed to the work in flight they concern, and delivered to it. Routing by what
the sender named, by the ids and names in the words, and by the classifier (the stand-in, and a block); delivery to a
running session (live, into its open input), to a session that cannot take one mid-run (queued, then resumed), and
to a block that is no session (its next run's context); finished work followed up or reopened; a message that reached
no work raised; and the measures."""

import json
import os
import sys
import textwrap
import threading
import time

import pytest

from ergostat import model as mdl
from ergostat import state as st
from ergostat.messages import deliver, measures, record, route
from ergostat.spec.engine import Engine, observations
from ergostat.store import Project

PY = sys.executable

BASE = """
name: t
projections:
  review:
    match:
      key: review/*
    states: [requested, briefed, answered]
    events:
      review.briefed:
        state: set('briefed')
      review.answered:
        state: set('answered')
    otherwise: rest
    show: [title, author]
  ramp:
    match:
      key: ramp/*
    states: [pending, briefed, approved]
    events:
      ramp.briefed:
        state: set('briefed')
      ramp.approved:
        state: set('approved')
    otherwise: rest
    show: [flag, team]
  session:
    match:
      key: session/*
    states: [open, done, failed, lost]
    events:
      session.ran:
        state: set('done')
      session.failed:
        state: set('failed')
      session.lost:
        state: set('lost')
    otherwise: rest
stocks:
  to-brief:
    sensor: {projection: review, state: requested, every: 5s}
  ramps-pending:
    sensor: {projection: ramp, state: pending, every: 5s}
flows:
  briefing:
    from: to-brief
    sensor: {projection: review, entering: briefed, over: 10m}
  researching:
    from: ramps-pending
    sensor: {projection: ramp, entering: briefed, over: 10m}
"""


def project(tmp_path, blocks: str = "", extra: str = "") -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(BASE) + textwrap.dedent(extra) +
                                            ("blocks:\n" + textwrap.indent(textwrap.dedent(blocks), "  ") if blocks else ""))
    m = mdl.load(tmp_path)
    errors = [x for x in m.problems if x.level == "error"]
    assert not errors, errors
    return Project(m)


BRIEFER = f"""
briefer:
  type: program
  run: {PY} -c "import sys; open('given.json', 'w').write(sys.stdin.read())"
  every: 1h
  out: flow.briefing
"""


def items(p):
    ev = p.events
    ev.add("review.requested", item="review/2041", source="watch", data={"title": "Migrate the billing schema", "author": "ana"})
    ev.add("review.requested", item="review/2042", source="watch", data={"title": "Faster image decoding", "author": "bo"})
    ev.add("ramp.requested", item="ramp/7", source="watch", data={"flag": "new-checkout", "team": "payments"})


def send(p, text, **kw):
    return route.send(p, p.model.spec, text, **kw)


# ---- routing

def test_explicit_about_routes_to_the_item_or_part_named(tmp_path):
    p = project(tmp_path, BRIEFER)
    items(p)
    m = send(p, "hold that one", about="review/2042")
    assert m["state"] == "routed" and m["matched"] == "explicit"
    assert m["routed_to"] == [{"item": "review/2042"}]
    m = send(p, "go slower", about=["block.briefer"])
    assert m["routed_to"] == [{"part": "block.briefer", "block": "briefer"}]
    m = send(p, "and this", about="briefer")                      # a part's bare name
    assert m["routed_to"][0]["block"] == "briefer"
    assert m["text"] == "and this" and m["by"] == "owner" and m["via"] == "cli"


def test_mentions_of_item_ids_and_block_names_route_it(tmp_path):
    p = project(tmp_path, BRIEFER)
    items(p)
    m = send(p, "ramp/7 is urgent, do it before review/2041")
    assert m["matched"] == "mention"
    assert {t["item"] for t in m["routed_to"]} == {"ramp/7", "review/2041"}
    m = send(p, "the briefer should keep briefs short")
    assert m["matched"] == "mention" and m["routed_to"][0]["block"] == "briefer"


def test_the_stand_in_classifier_matches_kind_words_fields_and_numbers(tmp_path):
    p = project(tmp_path, BRIEFER)
    items(p)
    m = send(p, "check the flag ramp first")
    assert m["matched"] == "classifier:standin" and [t["item"] for t in m["routed_to"]] == ["ramp/7"]
    m = send(p, "that billing review can wait")                  # its kind's name and a word of its title
    assert [t["item"] for t in m["routed_to"]] == ["review/2041"]
    m = send(p, "the review of 2042 is fine to skip")            # its number
    assert [t["item"] for t in m["routed_to"]] == ["review/2042"]
    assert "its number" in m["why"]


def test_a_message_naming_no_work_is_unrouted_and_needs_attention(tmp_path):
    p = project(tmp_path, BRIEFER)
    items(p)
    m = send(p, "hold that one")
    assert m["state"] == "unrouted" and m["routed_to"] == []
    snap = st.snapshot(p)
    att = [a for a in st.attention(snap, False, p.model) if a["what"].startswith("message ")]
    assert att and "hold that one" in att[0]["says"] and "--about" in att[0]["says"]
    route.route(p, p.model.spec, m["id"], about="review/2041", by="owner")   # routed by hand
    assert record.get(p, m["id"])["state"] == "routed"
    assert not [a for a in st.attention(st.snapshot(p), False, p.model) if a["what"].startswith("message ")]


def test_a_classifier_block_routes_what_nothing_names(tmp_path):
    script = tmp_path / "classify.py"
    script.write_text(textwrap.dedent("""
        import json, sys
        raw = sys.stdin.read()
        ctx = json.loads(raw[raw.rfind(chr(10) + "{") + 1:])   # its input, after its prompt
        m = ctx["message"]
        pick = [c["id"] for c in ctx["candidates"] if c["projection"] == "ramp"]
        print(json.dumps({"route": {"message": m["id"], "to": pick, "why": "it is about rollouts"}}))
    """))
    p = project(tmp_path, BRIEFER + f"""
router:
  type: ai
  model: haiku
  prompt: "Which work does this message concern?"
  run: {PY} classify.py
  out: flow.researching
""", extra="messages:\n  classifier: router\n")
    items(p)
    m = send(p, "hold off on the rollout")
    assert m["matched"] == "classifier:router" and [t["item"] for t in m["routed_to"]] == ["ramp/7"]
    assert m["why"] == "it is about rollouts"
    ran = p.events.query(n=1, item="router", type="agent.ran")[-1]
    assert ran["data"]["routes"] == 1 and ran["data"]["why"] == "message"
    send(p, "ramp/7 now")                                         # a mention needs no classifier
    assert len(p.events.query(n=None, item="router", type="agent.ran")) == 1


# ---- delivery

def test_a_block_that_is_no_session_gets_the_message_in_its_next_runs_context(tmp_path):
    p = project(tmp_path, BRIEFER)
    items(p)
    m = send(p, "that billing review can wait")
    assert m["state"] == "routed"
    Engine(p, say=lambda s: None).run_block(p.model.spec.blocks["briefer"], "schedule")
    given = json.loads((tmp_path / "given.json").read_text())
    assert [x["id"] for x in given["messages"]] == [m["id"]]
    assert given["messages"][0]["text"] == "that billing review can wait" and given["messages"][0]["items"] == ["review/2041"]
    got = record.get(p, m["id"])
    assert got["state"] == "delivered" and got["deliveries"][0]["how"] == "context"
    assert got["deliveries"][0]["block"] == "briefer"
    Engine(p, say=lambda s: None).run_block(p.model.spec.blocks["briefer"], "schedule")
    assert "messages" not in json.loads((tmp_path / "given.json").read_text())   # once


def session_project(tmp_path, live: bool = True):
    return project(tmp_path, f"""
dev:
  type: ai
  prompt: "Brief the oldest review."
  run: $ERGOSTAT_CMD session dev --model haiku{'' if live else ' --no-live'}
  timeout: 1m
  out: flow.briefing
""")


def run_in_background(p, name):
    e = Engine(p, say=lambda s: None)
    t = threading.Thread(target=e.run_block, args=(p.model.spec.blocks[name], "schedule"), daemon=True)
    t.start()
    for _ in range(200):                                          # until its session has started
        if p.events.query(n=1, type="session.started"):
            break
        time.sleep(0.05)
    assert p.events.query(n=1, type="session.started"), "the session never started"
    return t


@pytest.fixture
def echo(monkeypatch):
    monkeypatch.setenv("ERGOSTAT_CLAUDE", "echo")
    monkeypatch.setenv("ERGOSTAT_ECHO_WORK", "3")


def test_a_running_session_receives_the_message_live_as_its_next_turn(tmp_path, echo):
    p = session_project(tmp_path)
    items(p)
    t = run_in_background(p, "dev")
    started = p.events.query(n=1, type="session.started")[-1]
    m = send(p, "the dev should look at the indexes too")
    assert m["routed_to"][0]["run"] == started["causedby"] and m["routed_to"][0]["session"] == started["item"]
    t.join(60)
    got = record.get(p, m["id"])
    d = got["deliveries"][0]
    assert d["how"] == "live" and d["session"] == started["item"] and d["run"] == started["causedby"]
    assert got["state"] == "answered" and "indexes" in got["answers"][0]["says"]
    # it reached the session within its turn: the stand-in folded it in, as Claude Code does
    lines = [json.loads(x) for x in (p.dir / "sessions" / f"{started['item'].split('/')[1]}.jsonl").read_text().splitlines()]
    users = [x["message"]["content"] for x in lines if x["type"] == "user"]
    assert any("while you were working" in u and "indexes" in u for u in users)
    ran = p.events.query(n=1, item=started["item"], type="session.ran")[-1]
    assert ran["data"]["owner_messages"] == [m["id"]]


def test_a_session_that_cannot_take_it_mid_run_gets_it_queued_then_resumed(tmp_path, echo):
    p = session_project(tmp_path, live=False)
    items(p)
    t = run_in_background(p, "dev")
    started = p.events.query(n=1, type="session.started")[-1]
    m = send(p, "dev: skip the drafts folder")
    t.join(60)
    got = record.get(p, m["id"])
    assert got["queued"]["session"] == started["item"]
    assert got["deliveries"][0]["how"] == "resume" and got["deliveries"][0]["session"] == started["item"]
    assert got["state"] == "answered"
    lines = [json.loads(x) for x in (p.dir / "sessions" / f"{started['item'].split('/')[1]}.jsonl").read_text().splitlines()]
    replies = [x["message"]["content"][0]["text"] for x in lines if x["type"] == "assistant"]
    assert len(replies) == 2 and "resumed" in replies[1] and "drafts folder" in replies[1]


def test_a_message_about_finished_work_becomes_a_follow_up(tmp_path):
    p = project(tmp_path, BRIEFER)
    items(p)
    p.events.add("review.answered", item="review/2041", source="me")
    m = send(p, "on review 2041: also check the indexes")
    assert m["state"] == "delivered" and m["deliveries"][0]["how"] == "follow-up"
    new = m["deliveries"][0]["follow_up"]
    assert new == "review/2041.1"
    from ergostat.spec import items as its
    it = its.one(p.events, p.model.spec, new)
    assert it.state == "requested" and it.fields["follows"] == "review/2041" and it.fields["title"] == "Migrate the billing schema"
    assert not m.get("missed")                                    # it came after the work finished: nothing was missed


def test_reopen_policy_and_attention_policy(tmp_path):
    p = project(tmp_path, BRIEFER, extra="messages:\n  finished: reopen\n  reopen-to: {review: requested}\n")
    items(p)
    p.events.add("review.briefed", item="review/2041", source="briefer")
    p.events.add("review.answered", item="review/2041", source="me")
    m = send(p, "redo review/2041, the schema changed")
    assert m["deliveries"][0]["how"] == "reopen"
    from ergostat.spec import items as its
    assert its.one(p.events, p.model.spec, "review/2041").state == "requested"
    (tmp_path / "b").mkdir()
    q = project(tmp_path / "b", BRIEFER, extra="messages:\n  finished: attention\n")
    items(q)
    q.events.add("review.answered", item="review/2041", source="me")
    m = route.send(q, q.model.spec, "review/2041 again?")
    assert m["state"] == "unrouted" and "finished" in m["why"]


def test_work_that_finished_before_the_message_reached_it_is_missed_and_redone(tmp_path):
    p = project(tmp_path, BRIEFER, extra="messages:\n  finished: reopen\n")
    items(p)
    p.events.add("review.briefed", item="review/2041", source="briefer")
    m = send(p, "wait: review/2041 needs the migration checked")   # briefed, waiting for me: no block works on it
    assert m["state"] == "routed"
    p.events.add("review.answered", item="review/2041", source="me")  # ... and I answered it without the message
    assert deliver.sweep(p, p.model.spec) == 1
    got = record.get(p, m["id"])
    assert got["missed"]["item"] == "review/2041" and got["deliveries"][0]["how"] == "reopen"
    from ergostat.spec import items as its
    it = its.one(p.events, p.model.spec, "review/2041")
    assert it.state == "requested" and it.fields["reopened"]["message"] == m["id"] and it.fields["reopened"]["missed"]
    assert measures.counts(p)["missed"] == 1


# ---- measures, and the other ways in

def test_measures(tmp_path):
    p = project(tmp_path, BRIEFER, extra="""
auxiliaries:
  unrouted:
    sensor: {builtin: ergostat.messages.unrouted, every: 30s}
""")
    items(p)
    send(p, "hold that one")
    send(p, "that billing review can wait")
    n = measures.counts(p)
    assert n["unrouted"] == 1 and n["awaiting"] == 1 and n["received"] == 2 and n["routed"] == 1 and n["reached"] == 0
    Engine(p, say=lambda s: None).run_block(p.model.spec.blocks["briefer"], "schedule")
    n = measures.counts(p)
    assert n["awaiting"] == 0 and n["delivered"] == 1 and n["reached"] == 0.5
    from ergostat.numbers import measures as ms
    assert ms.measure(p, "messages.unrouted") == 1.0
    assert ms.all_of(p)["ergostat.messages.delivered"] == 1.0


def test_a_sensor_may_relay_the_owners_words(tmp_path):
    seen, refused = observations('{"message": {"text": "check the flag ramp first", "by": "me"}}\n'
                                 '{"message": {"text": ""}}\n3\n')
    assert seen == [{"message": {"text": "check the flag ramp first", "by": "me"}}] and len(refused) == 1


def test_the_mcp_tool_relays_a_message(tmp_path):
    from ergostat.mcp import Server
    p = project(tmp_path, BRIEFER)
    items(p)
    srv = Server(tmp_path)
    srv.project = lambda: p
    out = srv.call("message", {"text": "check the flag ramp first", "by": "owner, via the chat"})
    got = json.loads(out["content"][0]["text"])
    assert got["state"] == "routed" and got["routed_to"][0]["item"] == "ramp/7"
    listed = json.loads(srv.call("messages", {})["content"][0]["text"])
    assert listed["messages"][0]["by"] == "owner, via the chat" and listed["counts"]["routed"] == 1


def test_messages_policy_is_checked(tmp_path):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(BASE) + textwrap.dedent("""
        messages:
          classifier: nobody
          finished: forget
          reopen-to: {review: nowhere}
        """))
    with pytest.raises(mdl.ModelError) as got:
        mdl.load(tmp_path)
    errs = str(got.value)
    assert "messages.classifier" in errs and "messages.finished" in errs and "messages.reopen-to.review" in errs


def test_cli_send_and_list(tmp_path, capsys):
    from ergostat.cli import main
    project(tmp_path, BRIEFER)
    os.environ.pop("ERGOSTAT_RUN", None)
    assert main(["-C", str(tmp_path), "message", "hold", "that", "one"]) == 0
    assert "unrouted" in capsys.readouterr().out
    assert main(["-C", str(tmp_path), "messages"]) == 0
    assert "hold that one" in capsys.readouterr().out




def test_the_stand_in_reads_a_possessive_as_the_name(tmp_path):
    p = project(tmp_path, BRIEFER)
    items(p)
    p.events.add("review.requested", item="review/2043", source="watch", data={"title": "Migrate the search index", "author": "bo"})
    m = send(p, "that review of Bo's, the search one, can wait")
    assert [t["item"] for t in m["routed_to"]] == ["review/2043"]    # Bo's and search: 2042 is Bo's, not search


def test_a_note_about_a_running_session_goes_to_its_run(tmp_path, echo):
    p = session_project(tmp_path)
    items(p)
    t = run_in_background(p, "dev")
    started = p.events.query(n=1, type="session.started")[-1]
    m = send(p, "stop after this one", about=started["item"])
    assert m["routed_to"][0]["run"] == started["causedby"]
    t.join(60)
    assert record.get(p, m["id"])["deliveries"][0]["how"] == "live"
    from ergostat.web.messages_api import listing
    assert [x["id"] for x in listing(p, started["item"])["messages"]] == [m["id"]]


def test_a_message_that_corrects_is_found_by_the_corrections_scan(tmp_path):
    """The decisions' scan (SPEC §5a) reads the owner's messages as this kind records them."""
    from ergostat.decisions import fromrecord
    p = project(tmp_path, BRIEFER)
    items(p)
    send(p, "no, don't brief reviews in that much detail; keep the brief to five lines", about="review/2041",
         )
    got = fromrecord.found(p, p.model.spec)
    msgs = [x for x in got if x["data"]["source"]["type"] == "message"]
    assert msgs and msgs[0]["data"]["corrects"] == "review/2041"
