"""Gated actions (SPEC §12k): an outward act a session may ask for only through ergostat's tools, each run as its gate
says (auto, approve, deny), every answer recorded as events, the output returned to the session or to a later run; the
MCP server that serves them; the flags the session is started with; the page, the CLI and the measures."""

import io
import json
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat import state as st
from ergostat.actions import gate, record, sandbox, server
from ergostat.cli import main as cli
from ergostat.numbers import measures
from ergostat.spec.engine import Engine
from ergostat.store import Project
from ergostat.web import actions_api

PY = sys.executable

MODEL = """
name: t
projections:
  ticket:
    match:
      key: ticket/*
    states: [open, done]
    events:
      ticket.done:
        state: set('done')
    otherwise: rest
stocks:
  open-tickets:
    sensor: {projection: ticket, state: open, every: 5s}
flows:
  closed:
    from: open-tickets
    sensor: {projection: ticket, entering: done, over: 10m}
actions:
  note:
    run: "echo noted {text} for {item} > note.txt; cat note.txt"
    gate: auto
    args: {text: what to note}
    description: Write a note
  push:
    run: "echo pushed {branch} >> pushed.txt; echo done"
    gate: approve
    class: outward
    wait: 5s
  nuke:
    run: "touch nuked.txt"
    gate: deny
blocks:
  dev:
    type: ai
    prompt: "Work."
    tools: [Read, Edit]
    actions: [note, push, nuke]
    every: 1h
"""


def project(tmp_path) -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL))
    m = mdl.load(tmp_path)
    assert not [x for x in m.problems if x.level == "error"]
    return Project(m)


def ctx(tmp_path, **kw):
    return {"block": "dev", "run": "run1", "session": "session/dev-1", "item": "ticket/1", "workdir": str(tmp_path),
            "branch": "ticket/1-x", **kw}


def test_the_template_is_filled_and_quoted(tmp_path):
    p = project(tmp_path)
    a = p.model.spec.actions["note"]
    assert gate.render(a, {"text": "a; rm -rf /"}, ctx(tmp_path)) == "echo noted 'a; rm -rf /' for ticket/1 > note.txt; cat note.txt"


def test_auto_runs_at_once_and_deny_never_runs(tmp_path):
    p = project(tmp_path)
    spec = p.model.spec
    a = gate.request(p, spec, "note", {"text": "hello"}, ctx(tmp_path))
    assert a["state"] == "ran" and a["approved_by"] == "gate" and a["exit"] == 0
    assert a["output"] == "noted hello for ticket/1" and (tmp_path / "note.txt").exists()
    d = gate.request(p, spec, "nuke", {}, ctx(tmp_path))
    assert d["state"] == "denied" and d["denied_by"] == "gate" and not (tmp_path / "nuked.txt").exists()
    with pytest.raises(gate.GateError, match="needs text"):
        gate.request(p, spec, "note", {}, ctx(tmp_path))
    types = [e["type"] for e in p.events.query(n=None, item=a["id"])]
    assert types == ["ergostat.action.requested", "ergostat.action.approved", "ergostat.action.ran"]


def test_approve_is_held_until_the_owner_approves_and_the_approval_is_recorded(tmp_path):
    p = project(tmp_path)
    spec = p.model.spec
    a = gate.request(p, spec, "push", {}, ctx(tmp_path))
    assert a["state"] == "requested" and not (tmp_path / "pushed.txt").exists()
    assert any(x["what"] == f"action/{record.short(a['id'])}" and x["link"] == f"/item/{a['id']}"   # the inbox (§12o)
               and x["answer"] == ["approve", "deny"] for x in st.attention(st.snapshot(p), False, p.model))
    assert measures.measure(p, "ergostat.actions.held@outward") == 1.0
    got = gate.approve(p, spec, a["id"], note="looks right")          # no session waits: it runs here
    assert got["state"] == "ran" and got["output"] == "done" and got["approved_by"] == "owner"
    assert (tmp_path / "pushed.txt").read_text() == "pushed ticket/1-x\n"
    ev = p.events.query(n=None, item=a["id"], type="ergostat.action.approved")[0]
    assert ev["source"] == "owner" and ev["data"]["note"] == "looks right"
    assert gate.run_once(p, spec, a["id"]) is None                   # never twice
    with pytest.raises(gate.GateError, match="ran already"):
        gate.approve(p, spec, a["id"])
    b = gate.request(p, spec, "push", {}, ctx(tmp_path))
    assert gate.deny(p, b["id"], note="not now")["state"] == "denied"
    n = record.counts(p, cls="outward")
    assert (n["approved"], n["denied"], n["held"], n["ran"]) == (1, 1, 0, 1)
    assert measures.measure(p, "actions.auto") == 0.0


def test_a_waiting_session_runs_it_once_approved_and_gets_its_output(tmp_path):
    p = project(tmp_path)
    spec = p.model.spec
    a = gate.request(p, spec, "push", {}, ctx(tmp_path))
    got = {}
    t = threading.Thread(target=lambda: got.update(gate.wait(p, spec, a["id"], 10)), daemon=True)
    t.start()
    for _ in range(100):
        if gate.waiting(p, a["id"]):
            break
        time.sleep(0.05)
    assert gate.waiting(p, a["id"])
    gate.approve(p, spec, a["id"])                                   # the waiting session runs it, not the approver
    t.join(10)
    assert got["state"] == "ran" and got["output"] == "done"
    assert (tmp_path / "pushed.txt").read_text().count("pushed") == 1
    assert not gate.waiting(p, a["id"])


def test_a_result_the_session_never_got_goes_to_the_blocks_next_run(tmp_path, monkeypatch):
    import ergostat.spec.engine as eng
    p = project(tmp_path)
    spec = p.model.spec
    a = gate.request(p, spec, "push", {}, ctx(tmp_path))
    out = gate.wait(p, spec, a["id"], 0.2)                           # the session waited, and went on without it
    assert out["state"] == "requested"
    gate.approve(p, spec, a["id"])                                   # later: runs at once, nobody waiting
    f = tmp_path / "given.txt"
    monkeypatch.setattr(eng, "AI_COMMAND", f"{PY} -c \"import sys; open({str(f)!r}, 'w').write(sys.stdin.read())\"")
    Engine(p, say=lambda s: None).run_block(spec.blocks["dev"], "schedule")
    given = json.loads(f.read_text().split("\n---\n", 1)[1].split("\n", 1)[1].split("\n", 12)[-1])
    assert given["actions"][0]["id"] == a["id"] and given["actions"][0]["output"] == "done"
    d = record.get(p, a["id"])["deliveries"]
    assert d[0]["how"] == "context" and d[0]["block"] == "dev"


def mcp(cfg, *msgs):
    out = io.StringIO()
    server.serve(cfg, "session/dev-1", io.StringIO("".join(json.dumps(m) + "\n" for m in msgs)), out)
    return {r["id"]: r for r in map(json.loads, out.getvalue().splitlines())}


def test_the_mcp_server_serves_the_blocks_actions_as_tools(tmp_path):
    p = project(tmp_path)
    cfg = {"block": "dev", "run": "run1", "item": "ticket/1", "workdir": str(tmp_path), "branch": "b",
           "root": str(tmp_path), "state": str(p.dir), "actions": ["note", "push"]}
    got = mcp(cfg, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
              {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
              {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "note", "arguments": {"text": "hi"}}},
              {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "nuke", "arguments": {}}})
    tools = {t["name"]: t for t in got[2]["result"]["tools"]}
    assert set(tools) == {"note", "push", "action_status"}
    assert tools["note"]["inputSchema"]["required"] == ["text"] and "at once" in tools["note"]["description"]
    ran = json.loads(got[3]["result"]["content"][0]["text"])
    assert ran["state"] == "ran" and ran["output"] == "noted hi for ticket/1"
    a = record.get(p, ran["id"])
    assert a["session"] == "session/dev-1" and a["deliveries"][0]["how"] == "session"
    assert got[4]["result"]["isError"]                               # not one of this block's
    # a held one: the call says so when its wait runs out, and action_status tells it later
    spec_wait = p.model.spec.actions["push"].wait
    p.model.spec.actions["push"].wait = 0.3
    s = server.Server(cfg, "session/dev-1")
    s._p = p
    held = json.loads(s.call("push", {})["content"][0]["text"])
    assert held["state"] == "requested" and "held for the owner's approval" in held["note"]
    gate.deny(p, held["id"], note="no")
    later = s.call("action_status", {"id": held["id"]})
    assert later["isError"] and json.loads(later["content"][0]["text"])["state"] == "denied"
    p.model.spec.actions["push"].wait = spec_wait


def test_the_session_is_started_with_claudes_permission_flags_and_sandbox(tmp_path):
    cfg = {"file": "/s/f.json", "read": ["/docs"], "writes": ["/r/.git/objects"], "tools": ["Read", "Bash(python3:*)"],
           "actions": ["push"], "waits": [300, 120]}
    f = sandbox.flags(cfg, "session/dev-1")
    assert f[:2] == ["--add-dir", "/docs"] and "--restricted" in f
    assert f[f.index("--tools") + 1] == "Bash,Read"
    assert f[f.index("--allowedTools") + 1] == "Read,Bash(python3:*),mcp__actions"
    assert f[f.index("--permission-mode") + 1] == "dontAsk"
    deny = f[f.index("--disallowedTools") + 1].split(",")
    assert {"Bash(git push:*)", "Bash(gh:*)", "Bash(curl:*)", "Bash(ssh:*)", "WebFetch", "WebSearch"} <= set(deny)
    s = json.loads(f[f.index("--settings") + 1])
    assert s["sandbox"] == {"enabled": True, "failIfUnavailable": True, "allowUnsandboxedCommands": False,
                            "network": {"allowedDomains": [], "strictAllowlist": True},
                            "filesystem": {"allowWrite": ["/r/.git/objects"], "denyWrite": ["/docs"]}}
    assert "Edit(//docs/**)" in s["permissions"]["deny"]
    m = json.loads(f[f.index("--mcp-config") + 1])["mcpServers"]["actions"]
    assert m["env"] == {"ERGOSTAT_SANDBOX": "/s/f.json", "ERGOSTAT_SESSION": "session/dev-1"}
    assert sandbox.env(cfg) == {"MCP_TOOL_TIMEOUT": str((300 + 60) * 1000)}
    # a block that only says where it works is not gated: its folder and reads, nothing more
    assert sandbox.flags({"read": ["/docs"], "tools": None, "actions": []}) == ["--add-dir", "/docs"]


def test_each_class_says_asked_approved_denied_waiting_and_its_gate(tmp_path):
    """record.asked: each action asked this week counted once, by where it ended, so asked is the sum; an approval
    later denied at the act counts as denied; the gate is the model's for the class."""
    p = project(tmp_path)
    spec = p.model.spec
    gate.request(p, spec, "note", {"text": "a"}, ctx(tmp_path))
    gate.request(p, spec, "nuke", {}, ctx(tmp_path))
    held = gate.request(p, spec, "push", {}, ctx(tmp_path))
    gone = gate.request(p, spec, "push", {}, ctx(tmp_path))
    gate.approve(p, spec, gone["id"])
    gate.request(p, spec, "push", {}, ctx(tmp_path))
    gate.deny(p, held["id"])
    got = actions_api.listing(p, classes=True)["asked"]
    assert got["note"] == {"asked": 1, "approved": 1, "by_gate": 1, "denied": 0, "waiting": 0, "gate": "auto", "actions": ["note"]}
    assert got["nuke"] == {"asked": 1, "approved": 0, "by_gate": 0, "denied": 1, "waiting": 0, "gate": "deny", "actions": ["nuke"]}
    assert got["outward"] == {"asked": 3, "approved": 1, "by_gate": 0, "denied": 1, "waiting": 1, "gate": "approve",
                              "actions": ["push"]}
    assert all(c["asked"] == c["approved"] + c["denied"] + c["waiting"] for c in got.values())
    assert record.asked(p, spec, now=time.time() + 8 * 86400) == {}          # a week on: none asked this week


MIXED = """\
  ask:
    run: "echo asked"
    gate: approve
    class: mixed
  tell:
    run: "echo told"
    gate: auto
    class: mixed
blocks:"""


def test_a_class_mixing_gates_is_said_by_its_strictest(tmp_path):
    """record.asked: a class whose actions have different gates takes the strictest, from the model and, with no
    model, from the actions asked, whichever was declared or asked last."""
    text = textwrap.dedent(MODEL).replace("blocks:", MIXED, 1).replace("[note, push, nuke]", "[note, push, nuke, ask, tell]")
    (tmp_path / "ergostat.yaml").write_text(text)
    m = mdl.load(tmp_path)
    assert not [x for x in m.problems if x.level == "error"]
    p, spec = Project(m), m.spec
    gate.request(p, spec, "ask", {}, ctx(tmp_path))
    gate.request(p, spec, "tell", {}, ctx(tmp_path))            # the auto one declared and asked last
    got = record.asked(p, spec)["mixed"]
    assert (got["gate"], got["waiting"], got["approved"]) == ("approve", 1, 1)
    assert record.asked(p, None)["mixed"]["gate"] == "approve"   # no model: the strictest asked


def test_the_cli_and_the_page_answer_a_held_action(tmp_path, capsys):
    p = project(tmp_path)
    spec = p.model.spec
    a = gate.request(p, spec, "push", {}, ctx(tmp_path))
    assert cli(["-C", str(tmp_path), "actions"]) == 0
    out = capsys.readouterr().out
    assert record.short(a["id"]) in out and "outward" in out and "held for approval" in out
    assert cli(["-C", str(tmp_path), "actions", record.short(a["id"])[:6], "--approve", "--note", "ok"]) == 0
    assert record.get(p, a["id"])["state"] == "ran"
    b = gate.request(p, spec, "push", {}, ctx(tmp_path))

    class Live:
        def get(self):
            return p
    code, got = actions_api.post(Live(), f"action/{b['id']}/deny", {"note": ["not this one"]})
    assert code == 200 and got["state"] == "denied" and got["note"] == "not this one"
    assert actions_api.post(Live(), f"action/{b['id']}/approve", {})[0] == 400       # answered already
    listed = actions_api.listing(p, "ticket/1")
    assert [x["id"] for x in listed["actions"]] == [b["id"], a["id"]]
    assert listed["classes"]["outward"]["approved"] == 1 and listed["classes"]["outward"]["denied"] == 1


def test_actions_are_checked(tmp_path):
    from ergostat import spec
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent("""
        name: t
        actions:
          a: {run: "x {nope}", gate: maybe}
          b: {run: "x {item}", args: {item: the item}}
          c: {gate: auto}
          d: {run: "x {title}", args: {title: its title}, class: Bad_Class}
        blocks:
          dev: {type: ai, prompt: w, run: ./wrap.sh, tools: [Read], every: 1h}
    """))
    msgs = [x.message for x in spec.read(tmp_path / "ergostat.yaml")[1] if x.level == "error"]
    assert any("action a.gate" in m for m in msgs) and any("{nope} is neither" in m for m in msgs)
    assert any("action b.args.item" in m for m in msgs) and any("action c: run:" in m for m in msgs)
    assert any("action d.class" in m for m in msgs)
    assert any("ergostat session" in m for m in msgs)               # tools: given to a session ergostat starts


def test_the_owner_may_promote_a_class_to_auto(tmp_path, capsys):
    p = project(tmp_path)
    spec = p.model.spec
    for _ in range(5):
        gate.approve(p, spec, gate.request(p, spec, "push", {}, ctx(tmp_path))["id"])
    cli(["-C", str(tmp_path), "actions"])
    assert "the owner may promote it" in capsys.readouterr().out
    y = Path(tmp_path / "ergostat.yaml")
    y.write_text(y.read_text().replace("    gate: approve\n    class: outward", "    gate: auto\n    class: outward"))
    p = Project(mdl.load(tmp_path))
    assert gate.request(p, p.model.spec, "push", {}, ctx(tmp_path))["state"] == "ran"
    assert record.counts(p, cls="outward")["auto"] == 1


def test_each_action_names_who_asked_and_who_answered_in_the_list_and_the_items_page(tmp_path):
    from ergostat.web.server import _as_listed
    p = project(tmp_path)
    spec = p.model.spec
    auto = gate.request(p, spec, "note", {"text": "hi"}, ctx(tmp_path))
    held = gate.request(p, spec, "push", {}, ctx(tmp_path, block=None))       # a session with no block
    gate.approve(p, spec, held["id"], note="offline stand-in")
    no = gate.request(p, spec, "push", {}, ctx(tmp_path))
    gate.deny(p, no["id"], note="not now")
    waits = gate.request(p, spec, "push", {}, ctx(tmp_path))
    never = gate.request(p, spec, "nuke", {}, ctx(tmp_path))                  # its gate is deny: the gate's own denial
    late = gate.request(p, spec, "push", {}, ctx(tmp_path))                   # approved, then its gate is deny at the act
    y = tmp_path / "ergostat.yaml"
    y.write_text(y.read_text().replace("gate: approve\n    class: outward", "gate: deny\n    class: outward"))
    assert gate.approve(p, spec, late["id"], note="offline stand-in")["state"] == "denied"
    want = {auto["id"]: ("dev", "gate (auto)"), held["id"]: ("session/dev-1", "owner (offline stand-in)"),
            no["id"]: ("dev", "denied by owner (not now)"), waits["id"]: ("dev", "not yet answered"),
            never["id"]: ("dev", "denied by its gate: its gate is deny: never run"),
            late["id"]: ("dev", f"owner, then denied by its gate: {record.get(p, late['id'])['note']}")}
    assert "its gate at the act is deny" in want[late["id"]][1]
    assert {a["id"]: (a["by"], a["approved by"]) for a in actions_api.listing(p)["actions"]} == want
    got = {"projections": [{"name": "ergostat.action", "show": ["by", "approved by"]}],
           "items": [{"id": a["id"], "projection": "ergostat.action", "state": a["state"], "fields": a} for a in record.stored(p).values()]}
    listed = _as_listed(got, None, 0, True)["items"]
    assert {i["id"]: (i["fields"]["by"], i["fields"]["approved by"]) for i in listed} == want
