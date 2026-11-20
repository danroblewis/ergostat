"""The inbox (SPEC §12o): everything waiting on a person in one answerable list, from the CLI, the API and the MCP;
`notify:` sending what newly waits through a gated action per channel, grouped, rate limited, quiet at night,
escalated once; the approval budget and each class's record pointing up the ladder. No test sends anything: the
channels are `command` ones writing to a file, and the others' commands are only built (or their run patched)."""

from __future__ import annotations

import io
import json
import subprocess
import textwrap
import time

import pytest

from ergostat import model as mdl
from ergostat import state as st
from ergostat.actions import gate, record
from ergostat.cli import main as cli
from ergostat.control import loop as lp
from ergostat.inbox import answer, deliver, entries, stats
from ergostat.numbers import measures
from ergostat.numbers import proposals as pr
from ergostat.spec import read, watch
from ergostat.store import Project
from ergostat.web import actions_api

from .test_numbers import QUEUE, queue_project

EXTRA = """\
  reviewed:
    from: queue
  pushed:
    from: queue
goals:
  queue-short:
    stock: queue
    hold: "<= 20"
actions:
  push:
    run: "echo pushed >> pushed.txt"
    gate: approve
    class: outward
blocks:
  reviewer:
    type: person
    ask: review the queue
    goal: queue-short
    out: flow.reviewed
  pusher:
    type: program
    mode: advise
    run: "true"
    goal: queue-short
    out: flow.pushed
    actions: [push]
notify:
  base-url: http://ergostat.test:8791
  group: 2m
  per-hour: 2
  channels:
    log:
      type: command
      run: "cat >> sent.txt"
"""
MODEL = QUEUE + EXTRA


def project(tmp_path, text: str = MODEL) -> tuple[Project, dict]:
    p, snap = queue_project(tmp_path, text=text)
    assert not [x for x in p.model.problems if x.level == "error"], p.model.problems
    return p, snap


def seed(p, snap, at: float | None = None) -> dict:
    """One of each kind waiting: an action held, a person asked, a command advised, a step test offered, a change."""
    spec = p.model.spec
    a = gate.request(p, spec, "push", {}, {"block": "pusher", "item": None})
    for e in p.events.query(n=None, type="ergostat.action.requested"):
        e["time"] = at or e["time"]
    p.events.add("person.asked", item="reviewer", source="ergostat", data={"command": 3, "ask": "review the queue"}, at=at)
    p.events.add("block.advised", item="pusher", source="ergostat", data={"command": 2}, at=at)
    x = {"id": "st123456", "kind": "step-test", "goal": "queue-short", "title": "queue-short: a step test", "reason": "r",
         "plan": {"id": "st123456", "amount": 1}, "key": lp.key(spec, "queue-short")}
    p.events.add("steptest.offered", item="queue-short", source="ergostat", data=x, at=at)
    c = pr.propose_values(p, {"k": "3"}, snap)
    return {"action": a, "change": c}


def kinds(p) -> list[str]:
    return [e["kind"] for e in entries.entries(p)]


def test_the_inbox_aggregates_every_kind(tmp_path):
    p, snap = project(tmp_path)
    got = seed(p, snap)
    es = {e["kind"]: e for e in entries.entries(p)}
    assert set(es) == {"action", "person", "advise", "steptest", "change"}
    assert es["action"]["id"] == f"action/{record.short(got['action']['id'])}" and es["action"]["class"] == "outward"
    assert es["action"]["link"] == f"/item/{got['action']['id']}" and es["action"]["verbs"] == ["approve", "deny"]
    assert es["person"]["verbs"] == ["done"] and "review the queue" in es["person"]["summary"]
    assert es["person"]["link"] == "/diagram?view=blocks&around=block/reviewer"
    assert es["change"]["id"] == f"change/{got['change']['id']}" and es["change"]["class"] == "change:parameter"
    assert all(e["age"] >= 0 and e["summary"] for e in es.values())
    att = st.attention(st.snapshot(p), False, p.model)
    assert [a["what"] for a in att[:5]] == [e["id"] for e in entries.entries(p)]       # first, and answerable
    assert measures.measure(p, "ergostat.inbox.waiting") == 5.0 and measures.measure(p, "inbox.asked") == 5.0


def test_the_why_of_an_action_is_its_items_impact_and_tests(tmp_path):
    p, _ = project(tmp_path, MODEL.replace("blocks:", "items:\n  failure:\n    id: failure/*\n    states: [open]\n"
                                                   "    on: {failure.seen: open}\nblocks:", 1))
    p.events.add("failure.seen", item="failure/1", data={"impact": {"said": "restores 12 an hour"}, "tests": "passed"})
    gate.request(p, p.model.spec, "push", {}, {"block": "pusher", "item": "failure/1"})
    e = entries.entries(p)[0]
    assert e["why"] == "restores 12 an hour; tests passed" and "for failure/1" in e["summary"]


def test_each_kind_is_answered_from_the_cli(tmp_path, capsys):
    p, snap = project(tmp_path)
    got = seed(p, snap)
    run = ["-C", str(tmp_path)]
    assert cli([*run, "inbox"]) == 0 and "action/" in capsys.readouterr().out
    assert cli([*run, "inbox", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert len(listed) == 5 and all("verbs" in e for e in listed)
    short = record.short(got["action"]["id"])
    assert cli([*run, "inbox", short[:4], "--approve", "--note", "fine"]) == 0      # the start of its key will do
    assert record.get(p, got["action"]["id"])["state"] == "ran" and (tmp_path / "pushed.txt").exists()
    assert cli([*run, "inbox", "person/reviewer", "--approve"]) == 2               # a person reports, not approves
    assert "--done N" in capsys.readouterr().err
    assert cli([*run, "inbox", "person/reviewer", "--done", "4"]) == 0
    assert p.events.query(n=1, type="valve.opened")[-1]["data"]["amount"] == 4.0
    assert cli([*run, "inbox", "advise/pusher", "--deny", "--note", "not now"]) == 0
    assert p.events.query(n=1, type="block.denied")[-1]["source"] == "owner"
    assert cli([*run, "inbox", "steptest/st12", "--deny"]) == 0
    assert cli([*run, "inbox", f"change/{got['change']['id']}", "--approve"]) == 0
    assert pr.stored(Project(mdl.load(tmp_path)))[got["change"]["id"]]["status"] == "accepted"
    assert "value: 3" in (tmp_path / "ergostat.yaml").read_text()
    assert cli([*run, "inbox"]) == 0 and "nothing waits on you" in capsys.readouterr().out


def test_each_kind_is_answered_from_the_api(tmp_path):
    from ergostat.web.server import Live
    p, snap = project(tmp_path)
    got = seed(p, snap)
    live = Live(p)
    assert len(actions_api.inbox(p)["entries"]) == 5
    short = record.short(got["action"]["id"])
    code, x = actions_api.answer(live, f"inbox/action%2F{short}/deny", {"note": ["no"]})
    assert code == 200 and (x["id"], x["kind"], x["said"]) == (f"action/{short}", "action", "denied")
    code, x = actions_api.answer(live, "inbox/person%2Freviewer/done", {"n": ["2"]})
    assert code == 200 and "moved 2" in x["said"]
    assert actions_api.answer(live, "inbox/advise%2Fpusher/approve", {})[0] == 200
    assert p.events.query(n=1, type="block.approved")[-1]["source"] == "owner"
    code, x = actions_api.answer(live, f"inbox/change%2F{got['change']['id']}/deny", {"note": ["later"]})
    assert code == 200 and x["said"] == "dismissed"
    assert actions_api.answer(live, "inbox/steptest%2Fst123456/approve", {})[0] == 400   # nothing runs a test: refused
    assert actions_api.answer(live, "inbox/nothing/approve", {})[0] == 400
    assert kinds(p) == ["steptest"]


def test_the_mcp_lists_and_answers(tmp_path):
    from ergostat.mcp import Server
    p, snap = project(tmp_path)
    seed(p, snap)
    s = Server(tmp_path)
    listed = json.loads(s.call("inbox", {})["content"][0]["text"])
    assert {e["kind"] for e in listed} == {"action", "person", "advise", "steptest", "change"}
    out = s.call("answer", {"id": "advise/pusher", "verb": "approve", "note": "the owner said so"})
    assert "approved" in out["content"][0]["text"]
    assert s.call("answer", {"id": "person/reviewer", "verb": "deny"})["isError"]
    assert "advise" not in kinds(p)


# ---- notify

def sent(tmp_path) -> str:
    f = tmp_path / "sent.txt"
    return f.read_text() if f.exists() else ""


def test_new_entries_within_the_window_are_one_message(tmp_path):
    p, snap = project(tmp_path)
    spec, now = p.model.spec, time.time()
    p.events.add("person.asked", item="reviewer", source="ergostat", data={"command": 3}, at=now - 60)
    assert deliver.sweep(p, spec, now) == 0 and not sent(tmp_path)               # the window is not over yet
    p.events.add("block.advised", item="pusher", source="ergostat", data={"command": 2}, at=now - 30)
    assert deliver.sweep(p, spec, now + 61) == 1
    text = sent(tmp_path)
    assert text.startswith("ergostat: 1 request, 1 advised command waiting\n")
    assert "http://ergostat.test:8791/diagram?view=blocks&around=block/reviewer" in text
    assert "ergostat inbox person/reviewer@1 --done N" in text and "ergostat inbox advise/pusher@2 --approve | --deny" in text
    assert deliver.sweep(p, spec, now + 200) == 0                                 # told once
    told = p.events.query(n=None, type=deliver.SENT)
    assert len(told) == 1 and told[0]["data"]["entries"] == ["person/reviewer@1", "advise/pusher@2"]
    a = record.get(p, told[0]["data"]["action"])
    assert a["action"] == "notify.log" and a["state"] == "ran" and a["approved_by"] == record.GATE


def test_at_most_per_hour_per_channel_and_quiet_hours(tmp_path):
    p, snap = project(tmp_path)
    spec, now = p.model.spec, time.time()
    for i in range(4):                                       # four held actions, each found after the last was sent
        gate.request(p, spec, "push", {}, {"block": "pusher"})
        deliver.sweep(p, spec, now + 200 * (i + 1))
    assert len(p.events.query(n=None, type=deliver.SENT)) == 2                    # per-hour: 2
    later = now + 2 * 3600
    deliver.sweep(p, spec, later)
    told = p.events.query(n=None, type=deliver.SENT)
    assert len(told) == 3 and len(told[-1]["data"]["entries"]) == 2               # the two held back, together
    n = spec.notify
    n.quiet = (0, 24 * 60 - 1)
    gate.request(p, spec, "push", {}, {"block": "pusher"})
    assert deliver.sweep(p, spec, later + 3 * 3600) == 0                          # nothing in the quiet hours
    n.quiet = (22 * 60, 7 * 60)
    t = time.mktime(time.strptime("2026-11-19 23:30", "%Y-%m-%d %H:%M"))
    assert deliver.quiet(n, t) and not deliver.quiet(n, t + 9 * 3600)


DENIED = MODEL.replace("""    log:
      type: command
      run: "cat >> sent.txt"
""", """    log:
      type: command
      run: "cat >> sent.txt"
    team:
      type: slack
      url-env: TEAM_HOOK
      gate: deny
    desk:
      type: macos
      gate: approve
""")


def test_a_delivery_passes_through_its_gate_and_a_denied_channel_sends_nothing(tmp_path, monkeypatch):
    p, snap = project(tmp_path, DENIED)
    spec, now = p.model.spec, time.time()
    ran = []
    real = subprocess.run
    monkeypatch.setattr(gate.subprocess, "run", lambda cmd, **kw: ran.append(cmd) or real(
        cmd if "cat >>" in cmd else "true", **kw))                                # nothing leaves the machine
    p.events.add("person.asked", item="reviewer", source="ergostat", data={"command": 3}, at=now - 300)
    assert deliver.sweep(p, spec, now) == 3
    by = {e["data"]["channel"]: e["data"] for e in p.events.query(n=None, type=deliver.SENT)}
    assert by["log"]["state"] == "ran" and by["team"]["state"] == "denied" and by["desk"]["state"] == "requested"
    assert len(ran) == 1 and "cat >> sent.txt" in ran[0]                          # the denied and the held never ran
    assert record.get(p, by["team"]["action"])["denied_by"] == record.GATE
    deliver.sweep(p, spec, now + 600)
    assert len(p.events.query(n=None, type=deliver.SENT)) == 3                    # a denied channel is not asked again
    held = record.get(p, by["desk"]["action"])
    assert held["class"] == "notify" and "osascript" in held["command"] or "terminal-notifier" in held["command"]
    answer.answer(p, spec, f"action/{record.short(held['id'])}", "approve")
    assert len(ran) == 2 and record.get(p, held["id"])["state"] == "ran"


def test_a_notify_action_held_is_never_notified_about(tmp_path):
    p, snap = project(tmp_path, DENIED.replace("type: command\n      run", "type: command\n      gate: approve\n      run"))
    spec, now = p.model.spec, time.time()
    p.events.add("person.asked", item="reviewer", source="ergostat", data={"command": 3}, at=now - 300)
    deliver.sweep(p, spec, now)
    assert {e["kind"] for e in entries.entries(p)} == {"person", "action"}          # the held notifications wait too
    for i in range(1, 4):
        deliver.sweep(p, spec, now + 3600 * i)
    told = [i for e in p.events.query(n=None, type=deliver.SENT) for i in e["data"]["entries"]]
    assert told == ["person/reviewer@1"] * 3                                        # never about its own notify.* actions


def test_channel_commands_are_built_without_the_url_in_the_yaml(tmp_path):
    from ergostat.inbox import config
    assert config.command("slack", {"url-env": "TEAM_HOOK"}).endswith('--data-binary {body} "$TEAM_HOOK"')
    assert config.command("discord", {"url-file": "~/hook"}).endswith('"$(cat ' + str(__import__("pathlib").Path.home())
                                                                        + '/hook)"')
    assert config.command("email", {"command": "msmtp -t"}) == "printf '%s' {body} | msmtp -t"
    assert config.command("command", {"run": "tee x.txt"}) == "printf '%s\\n' {body} | tee x.txt"
    assert json.loads(deliver.body("slack", "", "s", "t")) == {"text": "*s*\nt"}
    assert deliver.body("email", "me@example.com", "s", "t") == "To: me@example.com\nSubject: s\n\nt\n"
    p, _ = project(tmp_path, DENIED)
    a = p.model.spec.actions["notify.team"]
    rendered = gate.render(a, {"subject": "s", "text": "t", "body": '{"text": "x; rm -rf /"}'}, {})
    assert rendered.endswith("""--data-binary '{"text": "x; rm -rf /"}' "$TEAM_HOOK\"""")


def test_notify_is_checked(tmp_path):
    bad = MODEL.replace('run: "cat >> sent.txt"', 'run: "cat >> sent.txt"\n    hook:\n      type: slack\n'
                        '      url: https://hooks.example.com/x\n    mail:\n      type: email\n    page:\n      type: pager')
    bad = bad.replace("  per-hour: 2", "  per-hour: 2\n  quiet: 25:00-07:00\n  escalate-to: phone")
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(bad))
    _, problems = read(tmp_path / "ergostat.yaml")
    said = " | ".join(x.message for x in problems if x.level == "error")
    for want in ("notify.channels.hook: unknown key 'url'", "never written in the model", "email needs to:",
                 "notify.channels.page.type: one of", "notify.quiet:", "notify.escalate-to: 'phone'"):
        assert want in said, said
    inc = tmp_path / "more.yaml"
    inc.write_text("notify:\n  channels: {}\n")
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL) + "include: [more.yaml]\n")
    _, problems = read(tmp_path / "ergostat.yaml")
    assert any(x.code == "notify-in-include" for x in problems)


def test_an_entry_past_wait_at_most_is_a_finding_and_escalated_once(tmp_path):
    text = DENIED.replace("  per-hour: 2", "  per-hour: 9\n  wait-at-most: 1h\n  escalate-to: [log]").replace(
        "      gate: approve\n", "")                                             # team: denied, desk: a file
    p, snap = project(tmp_path, text.replace("type: macos", "type: command\n      run: \"cat >> desk.txt\""))
    spec, now = p.model.spec, time.time()
    p.events.add("person.asked", item="reviewer", source="ergostat", data={"command": 3}, at=now - 300)
    deliver.sweep(p, spec, now)
    assert "ergostat: 1 request waiting" in (tmp_path / "desk.txt").read_text() and not sent(tmp_path)
    assert not [f for f in watch.find(p, spec) if f.code == "waiting-on-owner"]
    p.events.add("block.advised", item="pusher", source="ergostat", data={"command": 2}, at=now - 7200)
    found = [f for f in watch.find(p, spec) if f.code == "waiting-on-owner"]
    assert [f.about.split("@")[0] for f in found] == ["advise/pusher"] and "longer than notify's wait-at-most of 1h" in found[0].message
    deliver.sweep(p, spec, now + 10)
    assert "waiting longer than 1h" in sent(tmp_path) and "advise/pusher@" in sent(tmp_path)
    deliver.sweep(p, spec, now + 4000)
    assert sent(tmp_path).count("waiting longer than") == 2                    # each late entry once: then reviewer
    deliver.sweep(p, spec, now + 8000)
    assert sent(tmp_path).count("waiting longer than") == 2


def test_the_budget_and_an_always_approved_class_are_suggested_up_the_ladder(tmp_path, capsys):
    p, snap = project(tmp_path, MODEL.replace("  per-hour: 2", "  per-hour: 2\n  asks-per-day: 5"))
    spec = p.model.spec
    for _ in range(6):
        a = gate.request(p, spec, "push", {}, {"block": "pusher"})
        answer.answer(p, spec, f"action/{record.short(a['id'])}", "approve")
    rec = stats.by_class(p, spec)["outward"]
    assert (rec["asked"], rec["approved"], rec["denied"], rec["waiting"]) == (6, 6, 0, 0) and rec["median"] >= 0
    assert rec["suggest"] == ("6 approvals of outward this week, all approved: consider gate: auto for the actions of "
                              "class outward, or an AI approver")
    found = [f for f in watch.find(p, spec) if f.code == "approvals-over-budget"]
    assert found and "6 asked of the owner over the last day, over the budget of 5; most of them outward" in found[0].message
    assert "consider gate: auto" in found[0].message
    assert cli(["-C", str(tmp_path), "inbox", "--stats"]) == 0
    out = capsys.readouterr().out
    assert "outward" in out and "6 asked over the last day, budget 5" in out and "consider gate: auto" in out
    a = gate.request(p, spec, "push", {}, {"block": "pusher"})
    assert st.inbox(p, time.time(), True)[0]["record"].startswith("7 asked this week, 6 approved, 0 denied")
    p.events.add("block.advised", item="pusher", source="ergostat", data={"command": 1})
    answer.answer(p, spec, "advise/pusher", "deny")
    assert stats.by_class(p, spec)["advise:pusher"]["denied"] == 1 and record.get(p, a["id"])["state"] == "requested"


@pytest.fixture(autouse=True)
def _no_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(""))


def test_each_ask_is_its_own_entry_and_the_answer_is_to_the_ask_shown(tmp_path):
    p, snap = project(tmp_path)
    spec, now = p.model.spec, time.time()
    first = p.events.add("block.advised", item="pusher", source="ergostat", data={"command": 2}, at=now - 600)
    deliver.sweep(p, spec, now)
    assert sent(tmp_path).count("- advise/pusher@") == 1
    p.events.add("block.approved", item="pusher", source="owner", data={}, at=now - 500)
    second = p.events.add("block.advised", item="pusher", source="ergostat", data={"command": 5}, at=now - 400)
    deliver.sweep(p, spec, now + 200)                                             # a second ask is told too
    assert f"advise/pusher@{second['seq']}" in sent(tmp_path)
    third = p.events.add("block.advised", item="pusher", source="ergostat", data={"command": 7}, at=now - 100)
    with pytest.raises(answer.AnswerError):                                      # the ask shown is no longer waiting
        answer.answer(p, spec, f"advise/pusher@{second['seq']}", "approve")
    got = answer.answer(p, spec, "advise/pusher", "approve")                      # the block's name: its ask now
    assert got["id"] == f"advise/pusher@{third['seq']}"
    assert p.events.query(n=1, type="block.approved")[-1]["data"]["ask"] == third["seq"] != first["seq"]


def test_a_message_says_little_unless_the_channel_asks_for_detail_and_then_scrubbed(tmp_path):
    p, snap = project(tmp_path, MODEL.replace('run: "cat >> sent.txt"', 'run: "cat >> sent.txt"\n      detail: full'))
    gate.request(p, p.model.spec, "push", {}, {"block": "pusher", "item": "secret-host.corp.internal"})
    deliver.sweep(p, p.model.spec, time.time() + 300)
    full = sent(tmp_path)
    assert "secret-host.corp.internal" not in full and "for host-1: echo" in full      # its summary, scrubbed
    (tmp_path / "minimal").mkdir()
    p2, _ = project(tmp_path / "minimal")
    gate.request(p2, p2.model.spec, "push", {}, {"block": "pusher", "item": "ticket/7"})
    deliver.sweep(p2, p2.model.spec, time.time() + 300)
    text = sent(tmp_path / "minimal")
    assert "class outward" in text and "echo pushed" not in text and "ticket/7" not in text


def test_an_agents_answer_is_its_own_and_never_evidence(tmp_path):
    from ergostat.mcp import Server
    p, snap = project(tmp_path)
    for _ in range(6):
        gate.request(p, p.model.spec, "push", {}, {"block": "pusher"})
        e = entries.entries(p)[0]
        Server(tmp_path).call("answer", {"id": e["id"], "verb": "approve"})
    r = stats.by_class(p, p.model.spec)["outward"]
    assert (r["approved"], r["by_agent"], r["suggest"]) == (0, 6, None)
    assert record.stored(p).popitem()[1]["approved_by"] == "owner via mcp"


def test_a_failed_delivery_is_tried_again_and_said(tmp_path):
    p, snap = project(tmp_path, MODEL.replace('run: "cat >> sent.txt"', 'run: "exit 1"').replace("per-hour: 2",
                                                                                                "per-hour: 9"))
    spec, now = p.model.spec, time.time()
    p.events.add("person.asked", item="reviewer", source="ergostat", data={"command": 3}, at=now - 300)
    for i in range(3):
        deliver.sweep(p, spec, now + i * 10)
    states = [e["data"]["state"] for e in p.events.query(n=None, type=deliver.SENT)]
    assert states == ["failed"] * 3
    assert [f.about for f in watch.find(p, spec) if f.code == "notify-failing"] == ["notify.log"]


# ---- held modelling requests, answered from the inbox (docs/roadmap/overnight/inbox-dismiss.md)

def held_request(tmp_path, code: str = "collector-undescribed"):
    """A modelling project whose finding ``code`` (on flow.alerts-fired) the ai tier held: an inbox entry."""
    from ergostat.numbers import requests as rq

    from .test_modelling_core import MODELLING
    from .test_self_improve import POOR
    from .test_self_improve import project as poor_project
    p = poor_project(tmp_path, POOR + MODELLING)
    rq.sync(p)
    r = next(r for r in rq.current(p, ("open",)) if r["code"] == code)
    rq.mark(p, r, "held", "acting on its own: a decision for the owner")
    return p, r, f"request/{r['id']}"


def test_a_held_modelling_request_is_dismissed_with_its_note(tmp_path):
    from ergostat.numbers import requests as rq
    p, r, eid = held_request(tmp_path)
    spec = p.model.spec
    with pytest.raises(answer.AnswerError, match="--note"):
        answer.answer(p, spec, eid, "deny")                               # a dismissal says why
    assert cli(["-C", str(tmp_path), "inbox", eid, "--deny", "--note", "the pager is the collector: nothing to say",
                "--as", "sam"]) == 0
    x = rq.stored(p)[r["id"]]
    assert x["state"] == "dismissed" and x["note"] == "the pager is the collector: nothing to say"
    assert x["dismissed_by"] == "sam" and eid not in {e["id"] for e in entries.entries(p)}
    got = rq.sync(p)
    assert rq.stored(p)[r["id"]]["state"] == "dismissed" and got["raised"] == got["reopened"] == 0   # not raised again
    assert eid not in {e["id"] for e in entries.entries(p)}
    rec = stats.by_class(p, spec)[f"request:{r['code']}"]                 # an answered intervention, not a suppressed one
    assert (rec["asked"], rec["denied"], rec["waiting"]) == (1, 1, 0)


def test_a_dismissed_finding_returns_when_its_part_changes(tmp_path):
    from ergostat.numbers import requests as rq
    p, r, eid = held_request(tmp_path)
    answer.answer(p, p.model.spec, eid, "deny", note="not now")
    text = p.model.path.read_text()
    p.model.path.write_text(text.replace("sensor: {run: python3 bin/watch.py, every: 2s}",
                                         "sensor: {run: python3 bin/watch.py, every: 5s}"))
    q = Project(mdl.load(tmp_path))
    assert rq.sync(q)["reopened"] >= 1
    assert rq.stored(q)[r["id"]]["state"] in ("open", "held")              # raised again, for the tiers


def test_a_held_modelling_request_approved_goes_back_to_the_loop(tmp_path):
    from ergostat.numbers import requests as rq
    p, r, eid = held_request(tmp_path)
    got = answer.answer(p, p.model.spec, eid, "approve", by="sam")
    assert "modelling loop" in got["said"]
    x = rq.stored(p)[r["id"]]
    assert x["state"] == "open" and x["approved_by"] == "sam"
    assert r["id"] in {w["id"] for w in rq.waiting(p)}                    # what the ai tier takes up next
    rq.sync(p)
    assert rq.stored(p)[r["id"]]["state"] == "open" and eid not in {e["id"] for e in entries.entries(p)}
    assert stats.by_class(p, p.model.spec)[f"request:{r['code']}"]["approved"] == 1


def test_every_inbox_entry_kind_has_a_verb(tmp_path):
    (tmp_path / "a").mkdir()
    p, snap = project(tmp_path / "a", MODEL.replace("blocks:\n", "blocks:\n  poked:\n    type: program\n"
                                                    "    on: {event: queue.poked}\n    run: \"true\"\n", 1))
    seed(p, snap)
    p.events.add("trigger.tripped", item="poked", source="ergostat", data={"runs": 9, "most": 3})
    (tmp_path / "b").mkdir()
    q, _, _ = held_request(tmp_path / "b")
    es = entries.entries(p) + entries.entries(q)
    assert {e["kind"] for e in es} == set(entries.KINDS)                 # every kind the inbox can list
    for e in es:
        assert e["verbs"], e["id"]
        wrong = next(v for v in ("approve", "deny", "done") if v not in e["verbs"])
        with pytest.raises(answer.AnswerError) as no:
            answer.answer(q if e["kind"] == "request" else p, None, e["id"], wrong)
        assert "--" in str(no.value).split(" is answered with ", 1)[1], e["id"]
