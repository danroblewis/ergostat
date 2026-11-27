"""Claude Code transcripts as events (SPEC §5a): each line of a session's transcript recorded once,
as it grows, about the session's item, caused by its parent line; a long text kept as its head
with a pointer to the file; and the session folded by its kind's rules into its conversation.
Folds, counts and sensors that do not ask for the transcript are as fast as before it."""

import json
import textwrap
import time
import uuid
from datetime import UTC, datetime

from ergostat import model as mdl
from ergostat import transcripts as tr
from ergostat.spec import items as its
from ergostat.store import Project

MODEL = """
projections:
  session:
    query: key.startswith('session/')
    fields:
      state:
        values: [open, done]
      messages: {fold: append}
      tool_calls: {fold: append}
      tool_results: {fold: append}
      thinking: {fold: append}
      tokens_in: {fold: add}
      tokens_out: {fold: add}
    events:
      session-ran:
        when: type == 'session.ran'
        '...': data
        state: set('done')
      other:
        when: true
        '...': data
    show: [role, cost_usd]
    formats:
      transcript: claude-session
stocks:
  sessions-open:
    sensor:
      projection: session
      state: open
"""


def line(kind, content, parent=None, uid=None, usage=None, mid=None, at="2026-11-15T10:00:00Z"):
    msg = {"role": kind, "content": content}
    if usage:
        msg.update(usage=usage, id=mid)
    return {"type": kind, "uuid": uid or str(uuid.uuid4()), "parentUuid": parent, "timestamp": at, "message": msg}


def conversation():
    a = line("user", "Make the images smaller.", uid="u1")
    b = line("assistant", [{"type": "thinking", "thinking": "Look at the encoder first."}], "u1", "a1",
             {"input_tokens": 10, "cache_read_input_tokens": 90, "output_tokens": 5}, "m1")
    c = line("assistant", [{"type": "text", "text": "I'll run the tests."},
                           {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "bin/py test.py"}}],
             "a1", "a2", {"input_tokens": 10, "cache_read_input_tokens": 90, "output_tokens": 5}, "m1")     # the same message
    d = line("user", [{"type": "tool_result", "tool_use_id": "t1", "content": "x" * 10000}], "a2", "r1")
    e = {"type": "summary", "summary": "images"}                                                     # no uuid
    f = line("assistant", [{"type": "text", "text": "Done."}], "r1", "a3",
             {"input_tokens": 20, "output_tokens": 7}, "m2")
    return [a, b, c, d, e, f]


def setup(tmp_path):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL))
    (tmp_path / "run").mkdir()
    p = Project(mdl.load(tmp_path))
    p.events.add("session.started", item="session/dev-1", source="developer",
                 data={"role": "developer", "transcript": "file:run/s.jsonl"})
    return p


def write(tmp_path, lines, tail=""):
    (tmp_path / "run" / "s.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines) + tail)


def test_each_line_is_an_event_once_caused_by_its_parent(tmp_path):
    p = setup(tmp_path)
    ing = tr.Ingester(p, p.model.spec)
    lines = conversation()
    write(tmp_path, lines[:3], tail='{"type": "user", "uuid": "half')          # a line still being written
    assert ing.once() == 3
    write(tmp_path, lines)
    assert ing.once() == 3
    assert ing.once() == 0
    assert tr.Ingester(p, p.model.spec).once() == 0, "read again from its start by another reader: nothing new"
    (p.dir / "transcripts.json").unlink()
    assert tr.Ingester(p, p.model.spec).once() == 0, "nor with no note of what was read: each line's id is its own"
    evs = p.events.query(n=None, item="session/dev-1", type="claude.*")
    assert [e["type"] for e in evs] == ["claude.message", "claude.thinking", "claude.tool-use", "claude.tool-result",
                                        "claude.other", "claude.message"]
    by = {e["id"]: e for e in evs}
    assert by[evs[1]["causedby"]] is evs[0] and by[evs[2]["causedby"]] is evs[1] and by[evs[3]["causedby"]] is evs[2]
    assert evs[0]["causedby"] is None and evs[4]["causedby"] is None
    assert all(e["source"] == "developer" for e in evs), "from whoever started the session"
    assert evs[0]["time"] == datetime(2026, 11, 15, 10, tzinfo=UTC).timestamp()
    assert evs[0]["id"] == tr.event_id("session/dev-1", "uuid u1")


def test_a_long_text_keeps_its_head_and_points_to_the_file(tmp_path):
    p = setup(tmp_path)
    write(tmp_path, conversation())
    tr.Ingester(p, p.model.spec).once()
    res = p.events.query(n=None, item="session/dev-1", type="claude.tool-result")[0]["data"]["tool_results"][0]
    assert res["truncated"] and res["bytes"] == 10000 and len(res["text"]) == tr.LIMIT
    assert res["full"] == {"file": "run/s.jsonl", "line": 4}
    assert (tmp_path / "run" / "s.jsonl").read_text().splitlines()[3].count("x") == 10000, "all of it is in the file"
    for e in p.events.query(n=None, item="session/dev-1", type="claude.*"):
        assert len(json.dumps(e["data"]).encode()) < tr.LIMIT + 1024


def test_the_session_folds_into_its_conversation(tmp_path):
    p = setup(tmp_path)
    write(tmp_path, conversation())
    tr.Ingester(p, p.model.spec).once()
    p.events.add("session.ran", item="session/dev-1", data={"cost_usd": 0.12})
    d = its.detail(p.events, p.model.spec, "session/dev-1")
    f = d["fields"]
    assert [(m["role"], m["text"]) for m in f["messages"]] == [("user", "Make the images smaller."),
                                                              ("assistant", "I'll run the tests."), ("assistant", "Done.")]
    assert [(c["name"], c["input"]) for c in f["tool_calls"]] == [("Bash", {"command": "bin/py test.py"})]
    assert f["tool_results"][0]["tool_use_id"] == "t1" and f["thinking"][0]["text"] == "Look at the encoder first."
    assert f["tokens_in"] == 120 and f["tokens_out"] == 12, "a message over two lines is counted once"
    assert f["cost_usd"] == 0.12 and d["state"] == "done"
    assert d["changes"]["messages"] == 3 and d["transcript_events"] == 6     # one change per event that changed it
    assert all(e["type"].startswith("session.") for e in d["record"]), "the record shown is the session's own events"
    # what lists and counts sessions leaves the transcript out, and says how many events there are
    listed = its.listing(p.events, p.model.spec, kind="session")["items"][0]
    assert listed["events"] == 8 and "messages" not in listed["fields"] and listed["fields"]["cost_usd"] == 0.12
    plain = its.project(p.events, p.model.spec, "session")[0]
    assert "messages" not in plain.fields and plain.state == "done"


def test_ingesting_and_querying_a_two_thousand_line_session(tmp_path):
    """The cost, measured: 2,000 lines read in well under a second; a fold, a count or a listing that
    does not ask for the transcript no slower than with no transcript at all."""
    p = setup(tmp_path)
    for i in range(30):                                              # other sessions, with no transcript
        p.events.add("session.started", item=f"session/other-{i}", data={"role": "x"})
    spec = p.model.spec
    sensor = next(iter(spec.stocks["sessions-open"].sensors.values()))

    def timed(f, n=5):
        best = 1e9
        for _ in range(n):
            t = time.perf_counter()
            f()
            best = min(best, time.perf_counter() - t)
        return best
    before = {"count": timed(lambda: its.measure(p.events, spec, sensor)),
              "listing": timed(lambda: its.listing(p.events, spec))}
    lines, parent = [], None
    for i in range(2000):
        kind = "assistant" if i % 2 else "user"
        content = ([{"type": "tool_use", "id": f"t{i}", "name": "Bash", "input": {"command": f"echo {i}"}}] if i % 4 == 1 else
                   [{"type": "tool_result", "tool_use_id": f"t{i - 1}", "content": "ok " * 200}] if i % 4 == 2 else
                   [{"type": "text", "text": f"turn {i} " + "words " * 100}])
        lines.append(line(kind, content, parent, f"l{i}", {"input_tokens": 5, "output_tokens": 3} if kind == "assistant" else None,
                          f"m{i}"))
        parent = f"l{i}"
    write(tmp_path, lines)
    t = time.perf_counter()
    assert tr.Ingester(p, spec).once() == 2000
    ingest = time.perf_counter() - t
    after = {"count": timed(lambda: its.measure(p.events, spec, sensor)),
             "listing": timed(lambda: its.listing(p.events, spec))}
    full = timed(lambda: its.detail(p.events, spec, "session/dev-1"), 2)
    print(f"\n2,000 lines: ingested in {ingest * 1000:.0f} ms; count {before['count'] * 1000:.1f} → {after['count'] * 1000:.1f} ms; "
          f"listing {before['listing'] * 1000:.1f} → {after['listing'] * 1000:.1f} ms; the session's own page {full * 1000:.0f} ms")
    assert ingest < 2.0
    assert after["count"] < before["count"] * 3 + 0.01 and after["listing"] < before["listing"] * 3 + 0.01
    assert full < 3.0
    if p.events.name != "sqlite":                       # the segmented log reads the lines' columns, never their payload
        return
    with p.events._c() as c:
        plan = " ".join(str(r[3]) for r in c.execute(
            "explain query plan select * from events where item like '%/%' and not (type >= 'claude.' and type < 'claude/') "
            "and (item glob 'session/*') order by seq"))
    assert "events_item" in plan, plan
