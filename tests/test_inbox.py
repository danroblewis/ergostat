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
    objects = {a["what"].split("/")[0]: a["object"] for a in att[:5]}                 # what each answer is about
    assert objects["action"] == "push" and objects["person"] == "reviewer" and objects["advise"] == "pusher"
    assert measures.measure(p, "ergostat.inbox.waiting") == 5.0 and measures.measure(p, "inbox.asked") == 5.0


def test_a_persons_entry_says_what_its_number_moves_and_whether_it_is_yes_or_no(tmp_path, tmp_path_factory):
    p, snap = project(tmp_path)
    seed(p, snap)
    e = next(e for e in entries.entries(p) if e["kind"] == "person")
    assert (e["flow"], e["unit"], e["yes_no"]) == ("reviewed", "jobs", False)      # the stock's unit, from: queue
    att = next(a for a in st.attention(st.snapshot(p), False, p.model) if a["what"] == e["id"])
    assert (att["flow"], att["unit"], att["yes_no"]) == ("reviewed", "jobs", False)   # passed on to the side list
    two = (MODEL.replace("    out: flow.reviewed\n", "    out:\n      kept: flow.reviewed\n      dropped: flow.dropped\n", 1)
           .replace("  pushed:\n", "  dropped:\n    from: queue\n  pushed:\n", 1))
    p2, _ = project(tmp_path_factory.mktemp("two"), two)
    p2.events.add("person.asked", item="reviewer", source="ergostat", data={"command": 3, "ask": "review the queue"})
    assert next(e for e in entries.entries(p2) if e["kind"] == "person")["yes_no"] is True   # two ends: a decision


def test_the_why_of_an_action_is_its_items_impact_and_tests(tmp_path):
    p, _ = project(tmp_path, MODEL.replace("blocks:", "items:\n  failure:\n    id: failure/*\n    states: [open]\n"
                                                   "    on: {failure.seen: open}\nblocks:", 1))
    p.events.add("failure.seen", item="failure/1", data={"impact": {"said": "restores 12 an hour"}, "tests": "passed"})
    gate.request(p, p.model.spec, "push", {}, {"block": "pusher", "item": "failure/1"})
    e = entries.entries(p)[0]
    assert e["why"] == "restores 12 an hour; tests passed" and "for failure/1" in e["summary"]


def test_an_action_says_its_command_and_its_reason_once_in_the_cli_the_message_and_the_status(tmp_path, capsys):
    p, _ = project(tmp_path, MODEL.replace("blocks:", "items:\n  failure:\n    id: failure/*\n    states: [open]\n"
                                                   "    on: {failure.seen: open}\nblocks:", 1)
                   .replace('run: "cat >> sent.txt"', 'run: "cat >> sent.txt"\n      detail: full'))
    p.events.add("failure.seen", item="failure/1", data={"impact": {"said": "restores 12 an hour"}, "tests": "passed"})
    gate.request(p, p.model.spec, "push", {}, {"block": "pusher", "item": "failure/1"})
    assert cli(["-C", str(tmp_path), "inbox"]) == 0
    out = capsys.readouterr().out
    deliver.sweep(p, p.model.spec, time.time() + 300)
    msg = sent(tmp_path)
    ask = next(a for a in st.attention(st.snapshot(p), False, p.model) if a["what"].startswith("action/"))
    for said in (out, msg, ask["says"]):                       # the reason said once wherever it can be approved
        assert said.count("restores 12 an hour") == 1, said
    assert "runs: echo pushed >> pushed.txt" in out and "runs: echo pushed >> pushed.txt" in ask["says"]
    assert "runs: echo flow-1 >> flow-1.txt" in msg            # what will run (a message's: model names scrubbed)
    assert ask["first"].endswith("because restores 12 an hour; tests passed") and ask["more"] is None


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


def test_a_request_answered_leaves_the_attention_list_the_side_list_keys_by_what(tmp_path):
    """The side list (diagram.js) keys each request's row by its ``what`` and, while the reader is in it, marks a row
    "no longer waiting" when that ``what`` drops out of the graph answer's attention: so each request must be there
    under its own ``what`` with its verbs, and an answered one gone while the others stay, in their order (the browser
    half of this check is tests/test_inbox_page.py)."""
    from ergostat.web.server import Live
    p, _ = project(tmp_path)
    shorts = [record.short(gate.request(p, p.model.spec, "push", {}, {"block": "pusher", "item": None})["id"])
              for _ in range(3)]

    def waiting() -> list[str]:
        return [a["what"] for a in st.attention(st.snapshot(p), False, p.model) if a.get("answer")]
    before = waiting()
    assert sorted(w for w in before if w.startswith("action/")) == sorted(f"action/{s}" for s in shorts), before
    code, x = actions_api.answer(Live(p), f"inbox/action%2F{shorts[1]}/deny", {"note": ["not now"]})
    assert code == 200 and x["id"] == f"action/{shorts[1]}"
    assert waiting() == [w for w in before if w != f"action/{shorts[1]}"]


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
    real = subprocess.Popen                                                        # (run_once's: SPEC §12k)
    monkeypatch.setattr(gate.subprocess, "Popen", lambda cmd, **kw: ran.append(cmd) or real(
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
    assert "secret-host.corp.internal" not in full and "for host-1, " in full      # its summary, scrubbed
    assert "\n  runs: echo " in full                                                     # and what will run
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

def held_request(tmp_path, code: str = "collector-undescribed", ai: bool = True):
    """A modelling project whose finding ``code`` (on flow.alerts-fired) the ai tier held after using its tries (the
    usual way a request reaches the inbox): an inbox entry."""
    from ergostat.numbers import requests as rq

    from .test_modelling_core import MODELLING
    from .test_self_improve import POOR
    from .test_self_improve import project as poor_project
    p = poor_project(tmp_path, POOR + (MODELLING if ai else MODELLING.replace("      ai: true\n", "")))
    rq.sync(p)
    r = next(r for r in rq.current(p, ("open",)) if r["code"] == code)
    rq.mark(p, r, "held", "acting on its own: a decision for the owner", tier="ai", tried={"ai": 2})
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
    said = [x for x in stats.asked(p, spec, 0, time.time()) if x["class"] == f"request:{r['code']}"]
    assert [(x["verdict"], x["by"], x["note"]) for x in said] == [("denied", "sam", "the pager is the collector: nothing to say")]


def test_a_dismissed_finding_returns_when_its_part_changes(tmp_path):
    from ergostat.numbers import requests as rq
    p, r, eid = held_request(tmp_path)
    answer.answer(p, p.model.spec, eid, "deny", note="not now")
    text = p.model.path.read_text()
    assert "sensor: {items: alert, state: triaged, every: 2s}" in text
    p.model.path.write_text(text.replace("sensor: {items: alert, state: triaged, every: 2s}",
                                         "sensor: {items: alert, state: triaged, every: 3s}"))
    q = Project(mdl.load(tmp_path))                                       # another part changed: still dismissed
    assert rq.sync(q)["reopened"] == 0 and rq.stored(q)[r["id"]]["state"] == "dismissed"
    text = p.model.path.read_text()
    p.model.path.write_text(text.replace("sensor: {run: python3 bin/watch.py, every: 2s}",
                                         "sensor: {run: python3 bin/watch.py, every: 5s}"))
    q = Project(mdl.load(tmp_path))                                       # its own part changed: raised again
    assert rq.sync(q)["reopened"] >= 1
    x = rq.stored(q)[r["id"]]                                             # a new finding: untried, the tier's again
    assert x["state"] == "open" and r["id"] in {w["id"] for w in rq.for_ai(q, 2)}
    assert not x["owner"] and x["tried"] == {} and x["tier"] == "ai"
    assert all(x.get(k) is None for k in rq.DISMISSAL)                   # no dismissal shown on an open request
    rq.mark(q, x, "held", "the ai tier: nothing", tried={"ai": 2})       # the tier holds it again: in the inbox
    assert eid in {e["id"] for e in entries.entries(q)}


def test_a_dismissal_made_while_the_ai_tier_works_stands(tmp_path):
    from ergostat.numbers import requests as rq
    p, r, eid = held_request(tmp_path)
    rq.mark(p, rq.stored(p)[r["id"]], "held", "tries left", tried={"ai": 1})
    read = next(w for w in rq.for_ai(p, 2) if w["id"] == r["id"])        # the ai tier reads it, then calls the model
    answer.answer(p, p.model.spec, eid, "deny", note="not a modelling matter")
    assert rq.mark(p, read, "held", "the ai tier: nothing", tried={"ai": 2}) is False
    assert rq.mark(p, read, "held", tried={"ai": 2}, cost_usd=0.01) is False
    assert rq.stored(p)[r["id"]]["state"] == "dismissed" and eid not in {e["id"] for e in entries.entries(p)}


def test_an_approval_made_while_the_ai_tier_works_stands_though_the_state_is_as_it_read(tmp_path):
    """review/inbox-dismiss-4: the tier reads R open; meanwhile R is held (a change citing it turned away) and the
    owner approves it, so R is open again, as the tier read it. The tier's word is refused all the same."""
    from ergostat.numbers import requests as rq
    p, r, eid = held_request(tmp_path)
    answer.answer(p, p.model.spec, eid, "approve")
    read = next(w for w in rq.for_ai(p, 2) if w["id"] == r["id"])        # the ai tier reads it open, calls the model
    assert rq.move(p, r["id"], "held", {"why": "its change was dismissed", "tier": "ai", "owner": False}, ("open",))
    answer.answer(p, p.model.spec, eid, "approve")                        # the owner hands it back: open, untried
    assert rq.stored(p)[r["id"]]["state"] == read["state"] == "open"
    assert rq.mark(p, read, "held", "the ai tier: nothing", tried={"ai": 1}) is False
    assert rq.mark(p, read, "open", tried={"ai": 1}, cost_usd=0.01) is False
    x = rq.stored(p)[r["id"]]
    assert x["state"] == "open" and x["tried"]["ai"] == 0 and eid not in {e["id"] for e in entries.entries(p)}
    again = rq.stored(p)[r["id"]]                                         # a tier that reads it now is heard
    assert rq.mark(p, again, "open", tried={"ai": 1}) and rq.mark(p, rq.stored(p)[r["id"]], "held", "nothing")


def test_a_request_is_answered_under_the_lock(tmp_path, monkeypatch):
    import threading

    from ergostat.numbers import requests as rq
    from ergostat.numbers import version as ver
    p, r, eid = held_request(tmp_path)
    read, real, seen = rq.stored(p)[r["id"]], ver.part, {}

    def gap(spec, about):                                 # between the answer's read and its write: a tier marks it
        t = threading.Thread(target=lambda: seen.update(wrote=rq.mark(p, read, "held", "the ai tier: nothing")))
        t.start()
        t.join(0.5)
        seen["waited"] = t.is_alive()
        seen["thread"] = t
        return real(spec, about)
    monkeypatch.setattr(ver, "part", gap)
    answer.answer(p, p.model.spec, eid, "deny", note="mine to decide")
    seen["thread"].join(10)
    assert seen["waited"] and seen["wrote"] is False                      # it waited for the answer, then stood down
    assert rq.stored(p)[r["id"]]["state"] == "dismissed"


def test_the_collector_moves_requests_under_the_lock(tmp_path, monkeypatch):
    import threading

    from ergostat.numbers import requests as rq
    p, r, eid = held_request(tmp_path)
    real, seen = rq._citing, {}

    def gap(changes):                                     # between sync's read of the requests and its moves: the owner
        t = threading.Thread(target=lambda: answer.answer(p, p.model.spec, eid, "deny", note="no"))
        t.start()
        t.join(0.5)
        seen.update(waited=t.is_alive(), thread=t)
        return real(changes)
    monkeypatch.setattr(rq, "_citing", gap)
    rq.sync(p)
    seen["thread"].join(10)
    assert seen["waited"] and rq.stored(p)[r["id"]]["state"] == "dismissed"


def test_a_held_modelling_request_approved_goes_back_to_the_loop(tmp_path):
    from ergostat.numbers import requests as rq
    p, r, eid = held_request(tmp_path)                                    # held with the ai tier's tries used
    assert r["id"] not in {w["id"] for w in rq.for_ai(p, 2)}
    got = answer.answer(p, p.model.spec, eid, "approve", by="sam")
    assert "ai tier" in got["said"]
    x = rq.stored(p)[r["id"]]
    assert x["state"] == "open" and x["approved_by"] == "sam" and x["tier"] == "ai" and x["tried"]["ai"] == 0
    assert r["id"] in {w["id"] for w in rq.for_ai(p, 2)}                  # what the ai tier takes up next
    rq.sync(p)
    assert rq.stored(p)[r["id"]]["state"] == "open" and eid not in {e["id"] for e in entries.entries(p)}
    assert stats.by_class(p, p.model.spec)[f"request:{r['code']}"]["approved"] == 1
    rq.mark(p, rq.stored(p)[r["id"]], "held", "the ai tier: nothing", tried={"ai": 2})   # its tries used again
    assert eid in {e["id"] for e in entries.entries(p)}                   # back in the inbox


def test_a_held_request_no_tier_takes_up_is_only_dismissed(tmp_path):
    from ergostat.numbers import requests as rq
    (tmp_path / "a").mkdir()
    p, _, _ = held_request(tmp_path / "a")
    mine = [r for r in rq.current(p, ("held",)) if r["code"] in rq.OWNER]   # control: held for the owner at once
    assert mine
    for r in mine:
        e = entries.find(p, p.model.spec, f"request/{r['id']}")
        assert e["verbs"] == ["deny"] and "--deny --note WHY" in entries.command(e)
        with pytest.raises(rq.RequestError, match="no tier"):
            rq.answer(p, p.model.spec, r["id"], True)
        assert rq.stored(p)[r["id"]]["state"] == "held"
    (tmp_path / "b").mkdir()
    q, r, eid = held_request(tmp_path / "b", ai=False)                    # a model without the ai tier
    assert entries.find(q, q.model.spec, eid)["verbs"] == ["deny"]
    with pytest.raises(answer.AnswerError, match="--deny"):
        answer.answer(q, q.model.spec, eid, "approve")
    assert rq.stored(q)[r["id"]]["state"] == "held"


def test_a_redesign_request_is_never_approved_to_the_ai_tier(tmp_path):
    from ergostat.numbers import redesign_due as due
    from ergostat.numbers import requests as rq
    p, r, _ = held_request(tmp_path)                                      # a model running the ai tier
    assert rq.approvable(p.model.spec, rq.stored(p)[r["id"]])
    k = due.hold(p, "model", "too-large", "too large to redesign in one pass", owner=True)
    assert entries.find(p, p.model.spec, f"request/{k}")["verbs"] == ["deny"]   # the allowlist: check's, not a redesign's
    with pytest.raises(rq.RequestError, match="no tier"):
        rq.answer(p, p.model.spec, k, True)
    assert rq.stored(p)[k]["state"] == "held" and k not in {w["id"] for w in rq.for_ai(p, 2)}


def test_a_dismissed_redesign_request_stays_dismissed_across_the_redesigners_passes(tmp_path, monkeypatch):
    from ergostat.numbers import redesign_due as due
    from ergostat.numbers import requests as rq

    def big(n: int) -> str:
        return "name: big\nstocks:\n" + "".join(f"  s{i}:\n    unit: things\n    description: stock {i}\n" for i in range(n))
    monkeypatch.setattr(due, "MOST_PARTS", 10)
    monkeypatch.setattr(due, "_fit", lambda p_, spec: {"stocks": {}, "span": 0.0})
    (tmp_path / "ergostat.yaml").write_text(big(14))
    p = Project(mdl.load(tmp_path))
    due.next_due(p)
    r = next(r for r in rq.stored(p).values() if r["code"] == "too-large")
    assert r["state"] == "held"
    rq.answer(p, p.model.spec, r["id"], False, note="one plant, kept whole", by="sam")
    due.next_due(p)                                                       # the redesigner's next pass: still dismissed
    x = rq.stored(p)[r["id"]]
    assert x["state"] == "dismissed" and x["note"] == "one plant, kept whole"
    (tmp_path / "ergostat.yaml").write_text(big(15))                      # the unit changed: said again, for the owner
    q = Project(mdl.load(tmp_path))
    due.next_due(q)
    x = rq.stored(q)[r["id"]]
    assert x["state"] == "held" and x["owner"] and all(x.get(k) is None for k in rq.DISMISSAL)


def test_the_redesigner_holds_under_the_lock(tmp_path, monkeypatch):
    import threading

    from ergostat.numbers import redesign_due as due
    from ergostat.numbers import requests as rq
    p, _, _ = held_request(tmp_path)
    k = due.hold(p, "model", "too-large", "too large", owner=True)
    real, seen = rq.stored, {}

    def gap(p_):                                          # between hold's read and its write: the owner dismisses it
        if not seen:
            seen["thread"] = t = threading.Thread(target=lambda: rq.answer(p, p.model.spec, k, False, note="kept whole"))
            t.start()
            t.join(0.5)
            seen["waited"] = t.is_alive()
        return real(p_)
    monkeypatch.setattr(rq, "stored", gap)
    due.hold(p, "model", "too-large", "too large still: 40 parts", owner=True)
    seen["thread"].join(10)
    assert seen["waited"] and real(p)[k]["state"] == "dismissed"          # it waited, then the owner's answer landed


def test_the_status_and_notifications_say_how_a_request_is_denied(tmp_path):
    p, _, eid = held_request(tmp_path)
    e = next(e for e in entries.entries(p) if e["id"] == eid)
    assert entries.command(e) == f"ergostat inbox {eid} --approve | --deny --note WHY"
    att = st.attention(st.snapshot(p), False, p.model)
    assert any(a["says"].endswith(entries.command(e)) for a in att if a["what"] == eid)
    n = type("N", (), {"wait_at_most": 3600.0})()
    assert entries.command(e) in deliver.message(n, [{**e, "age": 60.0}], False, "")[1]


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


GROUPED = """\
name: grouped
stocks:
  backlog:
    unit: tickets
    sensor:
      manual: true
flows:
  finishing:
    from: backlog
goals:
  short-backlog:
    stock: backlog
    hold: "<= 5"
blocks:
  reviewer:
    type: person
    ask: review the backlog
    goal: short-backlog
    out: flow.finishing
uses:
  modelling:
    use: modelling
"""


def test_each_loop_line_carries_its_state_and_whether_the_goal_is_modellings(tmp_path, monkeypatch):
    """What the side list groups by (design review Q42): each loop entry says its status, a goal of a `use: modelling`
    instance is marked modelling's, the system's own is not, and the reports-upstream line is marked waiting."""
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    d = tmp_path / "grouped"
    d.mkdir()
    (d / "ergostat.yaml").write_text(GROUPED)
    p = Project(mdl.load(d))
    now = time.time()
    p.measurements.add("sensor/backlog.main", 9, at=now - 30)                    # the system's goal: off
    p.measurements.add("sensor/unanswered-requests.main", 3, at=now - 30)        # modelling's goal: off
    snap = st.snapshot(p, now=now)
    loops = {a["what"]: a for a in st.attention(snap, False, p.model) if a["what"].startswith("loop ")}
    assert loops["loop short-backlog"]["state"] == "off" and "modelling" not in loops["loop short-backlog"], loops
    assert loops["loop requests-handled"]["state"] == "off" and loops["loop requests-handled"]["modelling"] is True
    assert all(a["state"] == snap["loops"][w.split(" ", 1)[1]]["status"] for w, a in loops.items()), loops
    snap["reports"] = [{"id": "report/1", "title": "a crash"}]
    said = [a for a in st.attention(snap, False, p.model) if a["what"] == "reports upstream"]
    assert said and said[0]["waiting"] is True, said
    from ergostat.numbers import requests as rq
    rq.event(p, "r1", "held", {"code": "flow-unmeasured", "about": "flow.x", "source": "check", "tier": "ai"})
    p.events.add("person.asked", item="reviewer", source="ergostat", data={"command": 2, "ask": "look"})
    asks = {a["what"]: a for a in st.attention(st.snapshot(p, now=time.time()), False, p.model) if "answer" in a}
    assert asks["request/r1"]["kind"] == "request", asks                     # the page puts these under housekeeping
    assert [a["kind"] for w, a in asks.items() if w != "request/r1"] and all(
        a["kind"] != "request" for w, a in asks.items() if w != "request/r1"), asks
