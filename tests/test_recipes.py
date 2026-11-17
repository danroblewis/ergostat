"""Projection recipes (SPEC §12i): named, versioned recipes for a session's starting context (``contexts:``), each part
rendered within its budget from the record; ``ergostat context RECIPE``; an ``ai`` block started from one, the use
recorded with its recipe, version and the hash of the text; the outcome of the work it started found in the record
and folded onto the use and its session; the measures that compare recipes; and review depth set by trust.

Every transcript, message and project here is synthetic: made up in this file."""

import json
import subprocess
import sys
import textwrap
import uuid

import pytest

from ergostat import model as mdl
from ergostat.decisions import acts
from ergostat.decisions.kinds import CORRECTION, DECISION
from ergostat.recipes import render as rd
from ergostat.recipes import review as rv
from ergostat.recipes import uses
from ergostat.spec import items as its
from ergostat.spec.engine import Engine
from ergostat.store import Project

BASE = """
name: t
systems:
  shop:
    description: the shop
items:
  ticket:
    id: ticket/*
    states: [open, building, done, dropped]
    on:
      ticket.started: building
      ticket.done: done
      ticket.dropped: dropped
      ticket.reopened: open
    system: shop
  session:
    id: session/*
    states: [open, done, failed]
    on: {session.ran: done, session.failed: failed}
    show: [role, recipe, outcome]
    formats: {transcript: claude-session}
    fold: {messages: append, tool_calls: append}
stocks:
  todo:
    system: shop
    description: tickets waiting
    sensor: {manual: true}
flows:
  done:
    system: shop
    from: todo
goals:
  short:
    stock: todo
    hold: "<= 5"
"""


def project(tmp_path, extra: str = "", ok: bool = True) -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(BASE) + textwrap.dedent(extra))
    m = mdl.load(tmp_path)
    errors = [x for x in m.problems if x.level == "error"]
    if ok:
        assert not errors, errors
    return Project(m)


def problems(tmp_path, extra: str) -> list[str]:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(BASE) + textwrap.dedent(extra))
    from ergostat.spec import read
    return [f"{x.code}: {x.message}" for x in read(tmp_path / "ergostat.yaml")[1] if x.level == "error"]


def line(kind, content, at="2026-11-15T10:00:00Z", **extra):
    return {"type": kind, "uuid": str(uuid.uuid4()), "parentUuid": None, "timestamp": at, "sessionId": "s-synthetic",
            "message": {"role": kind, "content": content}, **extra}


def write_transcript(path, rows) -> None:
    path.write_text("".join(json.dumps(x) + "\n" for x in rows))


def synthetic(path) -> None:
    write_transcript(path, [
        line("user", "Let's make the checkout faster."),
        line("assistant", [{"type": "text", "text": "I cached the basket."}]),
        line("user", "The receipts page should stay plain: no charts on receipts.", at="2026-11-15T11:00:00Z"),
        line("assistant", [{"type": "text", "text": "Understood."}]),
        line("user", "Context from the harness", isMeta=True),
        line("user", "Checkout must never ask for the postcode twice.", at="2026-11-15T12:00:00Z"),
        line("assistant", [{"type": "text", "text": "Fixed the second ask."},
                           {"type": "tool_use", "id": "t1", "name": "Edit", "input": {}}]),
        line("user", "Next, the dark mode for the menu.", at="2026-11-15T13:00:00Z"),
        line("assistant", [{"type": "text", "text": "Dark mode added to the menu."}]),
    ])


RECIPES = """
contexts:
  worker:
    version: 3
    description: a worker on the shop
    outcome: {success: [done], failure: [dropped]}
    parts:
      - decisions: {scope: checkout, budget: 1500t}
      - corrections: {kind: ui}
      - owner-words: {topic: checkout, from: talk.jsonl, budget: 2000}
      - item-history
      - state: {findings: true}
      - model
  fork:
    parts:
      - session: {of: talk.jsonl, last: 2}
      - docs: {files: [notes.md]}
"""


def with_recipes(tmp_path, extra: str = "") -> Project:
    synthetic(tmp_path / "talk.jsonl")
    (tmp_path / "notes.md").write_text("# Notes\n\nThe shop sells bread.\n")
    return project(tmp_path, RECIPES + extra)


# ---- the format


def test_recipes_compile_with_their_versions_parts_and_budgets(tmp_path):
    p = with_recipes(tmp_path)
    r = p.model.spec.contexts["worker"]
    assert r.version == 3 and r.tag == "worker@3"
    assert [x.kind for x in r.parts] == ["decisions", "corrections", "owner-words", "item-history", "state", "model"]
    assert r.parts[0].budget == 6000 and r.parts[0].params == {"scope": "checkout"}
    assert r.parts[2].budget == 2000
    assert p.model.spec.contexts["fork"].version == 1
    before = r.digest
    p2 = project(tmp_path, RECIPES.replace("scope: checkout", "scope: receipts"))
    assert p2.model.spec.contexts["worker"].digest != before      # a change without a new version is told apart


@pytest.mark.parametrize("bad, code", [
    ("contexts:\n  x:\n    parts: [gossip]\n", "bad-part"),
    ("contexts:\n  x:\n    parts:\n      - decisions: {scope: a, colour: red}\n", "unknown-key"),
    ("contexts:\n  decisions:\n    parts: [docs]\n", "reserved-name"),
    ("contexts:\n  x:\n    version: 0\n    parts: [model]\n", "bad-number"),
    ("contexts:\n  x:\n    parts: []\n", "missing-key"),
    ("contexts:\n  x:\n    parts:\n      - docs: {files: [nowhere.md]}\n", "docs-missing"),
    ("contexts:\n  x:\n    parts:\n      - session: {last: 0}\n", "bad-part"),
    ("contexts:\n  x:\n    parts:\n      - session: {match: '('}\n", "bad-part"),
    ("contexts:\n  x:\n    parts: [model]\n    outcome: {great: [done]}\n", "bad-outcome"),
    ("blocks:\n  w:\n    type: ai\n    prompt: do it\n    context: nobody\n    out: flow.done\n", "unknown-ref"),
    ("blocks:\n  w:\n    type: program\n    run: 'true'\n    context: x\n    out: flow.done\n", "unknown-key"),
    ("blocks:\n  w:\n    type: program\n    run: 'true'\n    out: flow.done\n    review: {when: 'trust is bad', by: w}\n",
     "bad-review"),
    ("blocks:\n  w:\n    type: program\n    run: 'true'\n    out: flow.done\n    review: {when: 'contradicted > 0.2', by: ghost}\n",
     "unknown-ref"),
    ("blocks:\n  w:\n    type: program\n    run: 'true'\n    out: flow.done\n    review: {when: 'ergostat.nothing > 1', by: none}\n",
     "bad-measure"),
])
def test_a_mistake_in_a_recipe_or_a_blocks_context_or_review_is_said_with_its_code(tmp_path, bad, code):
    got = problems(tmp_path, bad)
    assert any(g.startswith(code + ":") for g in got), got


def test_the_schema_knows_contexts_and_a_blocks_context_and_review():
    schema = json.loads(open("schema/ergostat.schema.json").read())
    assert "contexts" in schema["properties"]
    blk = json.dumps(schema)
    assert '"context"' in blk and '"review"' in blk


# ---- the parts


def confirm_some(p):
    d = acts.propose(p, DECISION, {"decision": "Checkout asks for the postcode once.", "scope": ["checkout"],
                                   "reasons": ["it annoyed customers"]}, "owner")
    acts.confirm(p, DECISION, d["item"], "yes")
    o = acts.propose(p, DECISION, {"decision": "Receipts are plain.", "scope": ["receipts"]}, "owner")
    acts.confirm(p, DECISION, o["item"], None)
    c = acts.propose(p, CORRECTION, {"correction": "Never put charts on receipts.", "kind_of_work": ["ui"]}, "owner")
    acts.confirm(p, CORRECTION, c["item"], None)


def test_a_recipe_renders_its_parts_in_order_each_within_its_budget(tmp_path):
    p = with_recipes(tmp_path)
    confirm_some(p)
    p.events.add("ticket.opened", item="ticket/7", source="owner", data={"title": "postcode asked twice at checkout"})
    p.events.add("ticket.started", item="ticket/7", source="w", data={"by": "w"})
    p.measurements.add(next(iter(p.model.spec.stocks["todo"].sensors.values())).series, 3)
    r = rd.render(p, p.model.spec, "worker", "ticket/7")
    t = r.text
    heads = [x for x in t.splitlines() if x.startswith("## ")]
    assert [h.split()[1] for h in heads[:4]] == ["Decisions", "Corrections", "The", "The"]
    assert t.index("Decisions in force") < t.index("Corrections to keep") < t.index("The owner's words") \
        < t.index("The item: ticket/7") < t.index("The state now") < t.index("## The model")
    assert t.index("Checkout asks for the postcode once.") < t.index("Receipts are plain.")
    assert "Never put charts on receipts." in t
    # the owner's words on the topic and the item, most relevant first, verbatim; the harness's line left out
    words = t[t.index("The owner's words"):t.index("The item: ticket/7")]
    assert words.index("Checkout must never ask for the postcode twice.") < words.index("Let's make the checkout faster.")
    assert "Context from the harness" not in words and "dark mode" not in words
    assert "- title: postcode asked twice at checkout" in t and "building" in t
    assert "stock.todo: 3" in t and "goal short: stock.todo <= 5, not judged yet" in t
    assert r.version == 3 and r.item == "ticket/7" and len(r.hash) == 16
    assert all(x["chars"] <= x["budget"] for x in r.parts)
    small = rd.render(p, p.model.spec, "worker", "ticket/7", budget=3000)
    assert len(small.text) < 3600 and all(x["budget"] < 1000 for x in small.parts)


def test_a_fork_of_the_last_turns_and_named_documents(tmp_path):
    p = with_recipes(tmp_path)
    t = rd.render(p, p.model.spec, "fork").text
    assert "Its turns, the last 2: 2 of 4" in t
    assert "Checkout must never ask for the postcode twice." in t and "Next, the dark mode" in t
    assert "Let's make the checkout faster." not in t
    assert "[tools: Edit]" in t
    assert "=== notes.md ===" in t and "The shop sells bread." in t


def test_a_session_part_matching_a_pattern(tmp_path):
    p = with_recipes(tmp_path, "  receipts:\n    parts:\n      - session: {of: talk.jsonl, match: receipt}\n")
    t = rd.render(p, p.model.spec, "receipts").text
    assert "no charts on receipts" in t and "postcode" not in t


def test_the_owners_words_from_the_record_leave_out_a_blocks_session(tmp_path):
    """The record holds the owner's own session (read from its transcript) and a block's session, whose user turns
    are ergostat's prompts, not the owner's words."""
    from ergostat.transcripts import Ingester
    p = with_recipes(tmp_path, "  words:\n    parts:\n      - owner-words: {topic: receipts}\n"
                     "blocks:\n  w:\n    type: ai\n    prompt: do it\n    run: 'true'\n    out: flow.done\n")
    (tmp_path / "run").mkdir()
    synthetic(tmp_path / "run" / "owner.jsonl")
    write_transcript(tmp_path / "run" / "block.jsonl", [line("user", "You are a block. The receipts are yours.")])
    p.events.add("session.started", item="session/mine", source="owner", data={"transcript": "file:run/owner.jsonl"})
    p.events.add("session.started", item="session/w-1", source="w", data={"role": "w", "transcript": "file:run/block.jsonl"})
    Ingester(p, p.model.spec).once()
    t = rd.render(p, p.model.spec, "words").text
    assert "no charts on receipts" in t and "session/mine, line 3" in t
    assert "You are a block" not in t


def test_item_history_shows_its_linked_sessions_key_turns(tmp_path):
    from ergostat.transcripts import Ingester
    p = with_recipes(tmp_path)
    (tmp_path / "run").mkdir()
    write_transcript(tmp_path / "run" / "s.jsonl", [
        line("user", "Fix ticket/7."), line("assistant", [{"type": "text", "text": "Looking."}]),
        line("assistant", [{"type": "text", "text": "Fixed: the form remembers the postcode."}])])
    p.events.add("ticket.opened", item="ticket/7", source="owner", data={"title": "postcode"})
    p.events.add("session.started", item="session/w-1", source="w", data={"item": "ticket/7", "transcript": "file:run/s.jsonl"})
    Ingester(p, p.model.spec).once()
    t = rd.render(p, p.model.spec, "worker", "ticket/7").text
    assert "### session/w-1" in t and "Fix ticket/7." in t and "Fixed: the form remembers the postcode." in t
    assert "Looking." not in t                       # a key turn: what it was asked, and what it said last


def test_state_says_what_moved_on_main_and_what_is_running(tmp_path):
    p = with_recipes(tmp_path)
    git = ["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
    subprocess.run([*git, "add", "notes.md"], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "Notes on the shop"], check=True)
    p.events.add("agent.started", item="builder", source="ergostat", data={"trigger": "schedule"})
    t = rd.render(p, p.model.spec, "worker").text
    st = t[t.index("The state now"):]
    assert "What moved on main" in st and "Notes on the shop" in st
    assert "block builder: running since" in st
    assert "Uncommitted there" in st                   # ergostat.yaml and talk.jsonl are not committed


def test_an_unknown_recipe_or_item_is_said(tmp_path):
    p = with_recipes(tmp_path)
    with pytest.raises(rd.RecipeError, match="worker, fork|fork, worker"):
        rd.render(p, p.model.spec, "nobody")
    with pytest.raises(rd.RecipeError, match="no item"):
        rd.render(p, p.model.spec, "worker", "ticket/404")


def test_the_item_a_run_works_on_from_its_command_or_a_selector(tmp_path):
    p = with_recipes(tmp_path)
    spec = p.model.spec
    for n in (1, 2, 3):
        p.events.add("ticket.opened", item=f"ticket/{n}", source="owner", data={"title": f"t{n}"})
    p.events.add("ticket.started", item="ticket/3", source="w", data={})
    assert rd.item_for(p, spec, {"kind": "ticket", "state": ["building", "open"]}).id == "ticket/3"
    assert rd.item_for(p, spec, {"kind": "ticket", "state": ["open"]}).id == "ticket/1"
    assert rd.item_for(p, spec, {"kind": "ticket", "state": ["open"], "pick": "newest"}).id == "ticket/2"
    assert rd.item_for(p, spec, {"kind": "ticket"}, command_item="ticket/2").id == "ticket/2"
    assert rd.item_for(p, spec, "ticket/{block}", block="1").id == "ticket/1"
    assert rd.item_for(p, spec, None) is None


# ---- the command line and MCP


def cli(tmp_path, *args):
    return subprocess.run([sys.executable, "-m", "ergostat", "-C", str(tmp_path), *args], capture_output=True, text=True)


def test_ergostat_context_lists_and_renders_recipes(tmp_path):
    p = with_recipes(tmp_path)
    p.events.add("ticket.opened", item="ticket/7", source="owner", data={"title": "postcode"})
    got = cli(tmp_path, "context", "--list")
    assert got.returncode == 0 and "worker@3  decisions (scope: checkout) [6000]" in got.stdout
    assert "Built in: decisions" in got.stdout
    got = cli(tmp_path, "context", "worker", "--item", "ticket/7", "--budget", "1000t")
    assert got.returncode == 0 and got.stdout.startswith("# Starting context: worker (version 3)")
    assert "The work is on ticket/7." in got.stdout
    got = cli(tmp_path, "context", "worker", "--json")
    d = json.loads(got.stdout)
    assert d["tag"] == "worker@3" and d["markdown"].startswith("# Starting context")
    got = cli(tmp_path, "context", "nobody")
    assert got.returncode == 2 and "no recipe 'nobody'" in got.stderr
    assert cli(tmp_path, "context", "decisions").stdout.startswith("# Decisions in force")


def test_mcp_context_renders_a_recipe(tmp_path):
    from ergostat import mcp
    with_recipes(tmp_path)
    srv = mcp.Server(tmp_path)
    got = srv.call("context", {"recipe": "fork"})
    assert not got.get("isError") and "Session talk" in got["content"][0]["text"]
    assert srv.call("context", {"recipe": "nobody"}).get("isError")
    assert "worker" in json.loads(srv.call("context", {"list": True})["content"][0]["text"])
    tools = {t["name"]: t for t in mcp.TOOLS}
    assert "item" in tools["context"]["inputSchema"]["properties"]


# ---- a block started from a recipe, and the outcome of its work


WORKER = """
blocks:
  w:
    type: ai
    prompt: do the oldest ticket
    run: sh w.sh
    context: {recipe: worker, item: {kind: ticket, state: [building, open]}}
    out: flow.done
"""

SCRIPT = """
echo "context=$ERGOSTAT_CONTEXT recipe=$ERGOSTAT_CONTEXT_RECIPE hash=$ERGOSTAT_CONTEXT_HASH item=$ERGOSTAT_CONTEXT_ITEM" >> seen.txt
cat > stdin.txt
echo '{"event": "ticket.started", "item": "ticket/7"}'
echo '{"claim": {"says": "%s", "about": "ticket/7", "check": {"state": "%s"}}}'
"""


def run_once(p, name="w"):
    e = Engine(p, say=lambda s: None)
    e.run_block(p.model.spec.blocks[name], "schedule")
    return p.events.query(n=1, type="agent.started", item=name)[-1]["id"]


def test_a_block_with_a_context_starts_from_its_recipe_and_records_the_use(tmp_path):
    (tmp_path / "w.sh").write_text(SCRIPT % ("ticket/7 is building", "building"))
    p = with_recipes(tmp_path, WORKER)
    p.events.add("ticket.opened", item="ticket/7", source="owner", data={"title": "postcode at checkout"})
    run = run_once(p)
    seen = (tmp_path / "seen.txt").read_text()
    assert "recipe=worker@3" in seen and "item=ticket/7" in seen
    path = seen.split("context=")[1].split()[0]
    text = open(path).read()
    assert text.startswith("# Starting context: worker (version 3)") and "The work is on ticket/7." in text
    stdin = json.loads([x for x in (tmp_path / "stdin.txt").read_text().splitlines() if x.startswith('{"block"')][-1])
    assert stdin["context"]["tag"] == "worker@3" and stdin["context"]["file"] == path
    u = uses.stored(p, p.model.spec)[0]
    assert u["id"] == f"ergostat.context/w-{run[:8]}" and u["recipe"] == "worker@3" and u["run"] == run
    assert u["hash"] in seen and u["definition"] == p.model.spec.contexts["worker"].digest
    assert u["state"] == "succeeded"                  # its claim verified (the ticket is building), at once
    assert any("claim verified" in x["says"] for x in u["evidence"])


SESSION_WORKER = """
blocks:
  w:
    type: ai
    prompt: do the oldest ticket
    run: $ERGOSTAT_CMD session w --model haiku --no-live
    context: {recipe: worker, item: {kind: ticket, state: [building, open]}}
    timeout: 1m
    out: flow.done
"""


def test_a_session_started_by_the_helper_is_given_the_context_and_records_it(tmp_path, monkeypatch):
    """ergostat session (the shared helper) starts claude -p with the rendered context as its appended system prompt,
    and its session item says which recipe, version and text it started from; the use names the session."""
    monkeypatch.setenv("ERGOSTAT_CLAUDE", "echo")
    monkeypatch.setenv("ERGOSTAT_ECHO_WORK", "0")
    p = with_recipes(tmp_path, SESSION_WORKER)
    p.events.add("ticket.opened", item="ticket/7", source="owner", data={"title": "postcode at checkout"})
    run = run_once(p)
    started = p.events.query(n=1, type="session.started")[-1]
    c = started["data"]["context"]
    u = uses.stored(p, p.model.spec)[0]
    assert c["recipe"] == "worker@3" and c["name"] == "worker" and c["version"] == 3
    assert c["hash"] == u["hash"] and c["item"] == "ticket/7" and c["run"] == run and c["chars"] == u["chars"]
    ran = p.events.query(n=1, item=started["item"], type="session.ran")[-1]
    assert "echo: started from '# Starting context: worker (version 3)'" in ran["data"]["said"]
    s = its.one(p.events, p.model.spec, started["item"])
    assert s.fields["recipe"] == "worker@3"            # shown on the session's row (show: [role, recipe, outcome])
    assert u["session"] == started["item"]


def test_a_contradicted_claim_or_a_dropped_item_fails_the_use_and_the_session_shows_it(tmp_path):
    (tmp_path / "w.sh").write_text(SCRIPT % ("ticket/7 is done", "done") +
                                   'echo \'{"event": "session.started", "item": "session/w-1", '
                                   '"data": {"role": "w", "run": "\'$ERGOSTAT_RUN\'"}}\'\n')
    p = with_recipes(tmp_path, WORKER)
    p.events.add("ticket.opened", item="ticket/7", source="owner", data={"title": "postcode"})
    run_once(p)
    u = uses.stored(p, p.model.spec)[0]
    assert u["state"] == "failed" and u["session"] == "session/w-1"
    assert any("claim contradicted" in x["says"] for x in u["evidence"])
    s = its.one(p.events, p.model.spec, "session/w-1")
    assert s.fields["outcome"] == "failed" and s.fields["recipe"] == "worker@3"
    assert uses.measure(p, p.model.spec, "ergostat.context.worker.outcome") == 0.0
    assert uses.measure(p, p.model.spec, "ergostat.context.worker.failed") == 1.0
    assert uses.measure(p, p.model.spec, "ergostat.context.worker.uses") == 1.0


def test_an_outcome_found_later_is_folded_on_the_next_pass(tmp_path):
    (tmp_path / "w.sh").write_text("cat > /dev/null\necho '{\"event\": \"ticket.started\", \"item\": \"ticket/7\"}'\n")
    p = with_recipes(tmp_path, WORKER)
    p.events.add("ticket.opened", item="ticket/7", source="owner", data={"title": "postcode"})
    run_once(p)
    assert uses.stored(p, p.model.spec)[0]["state"] == "started"     # nothing known of the work yet
    p.events.add("ticket.done", item="ticket/7", source="owner", data={})
    assert uses.refresh(p, p.model.spec) == 1
    assert uses.stored(p, p.model.spec)[0]["state"] == "succeeded"
    assert uses.refresh(p, p.model.spec) == 0                        # nothing new: nothing recorded
    p.events.add("ticket.reopened", item="ticket/7", source="owner", data={"reason": "the postcode is asked again"})
    uses.refresh(p, p.model.spec)
    u = uses.stored(p, p.model.spec)[0]
    assert u["state"] == "failed" and any("reopened: the postcode is asked again" in x["says"] for x in u["evidence"])
    t = uses.table(p, p.model.spec)
    assert t["rows"][0]["recipe"] == "worker@3" and t["rows"][0]["failed"] == 1
    from ergostat.numbers.measures import measure
    assert measure(p, "ergostat.context.worker.outcome") == 0.0
    got = cli(tmp_path, "context", "--outcomes")
    assert "worker@3" in got.stdout and got.returncode == 0


def test_a_sensor_reads_a_recipes_outcome(tmp_path):
    p = project(tmp_path, RECIPES.replace("talk.jsonl", "x.jsonl").replace("[notes.md]", "[ergostat.yaml]") + """
auxiliaries:
  worker-outcome:
    sensor: {builtin: ergostat.context.worker.outcome, every: 30s}
""")
    assert p.model.spec.auxiliaries["worker-outcome"].sensors


# ---- review depth set by trust


REVIEWED = """
blocks:
  dev:
    type: program
    run: sh dev.sh
    out: flow.done
    review:
      - when: "contradicted > 0.3"
        by: reviewer
        depth: deep
      - by: none
  reviewer:
    type: program
    run: sh reviewer.sh
    out: flow.done2
flows:
  done2:
    from: todo
"""


def test_a_reviewer_is_required_when_the_blocks_contradictions_pass_the_threshold(tmp_path):
    """A liar's work goes to the reviewer, with the depth and why; an honest block's is not reviewed."""
    (tmp_path / "dev.sh").write_text('echo \'{"claim": {"says": "ticket/7 is done", "about": "ticket/7", '
                                     '"check": {"state": "done"}}}\'\n')
    (tmp_path / "reviewer.sh").write_text("cat > review-input.json\n")
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(BASE).replace("flows:\n  done:", "flows:\n  done2:\n    from: todo\n  done:")
                                            + textwrap.dedent(REVIEWED).replace("flows:\n  done2:\n    from: todo\n", ""))
    m = mdl.load(tmp_path)
    assert not [x for x in m.problems if x.level == "error"], m.problems
    p = Project(m)
    spec = p.model.spec
    assert spec.blocks["dev"].outputs["review-reviewer"][0].name == "reviewer"     # drawn: dev commands its reviewer
    p.events.add("ticket.opened", item="ticket/7", source="owner", data={})
    e = Engine(p, say=lambda s: None)
    e.run_block(spec.blocks["dev"], "schedule")              # the claim is contradicted: trust 1.0 > 0.3
    req = p.events.query(n=1, type="review.required", item="dev")
    assert req and req[0]["data"]["by"] == "reviewer" and req[0]["data"]["depth"] == "deep"
    assert "ergostat.trust.contradicted@dev = 1" in req[0]["data"]["why"] and req[0]["data"]["item"] == "ticket/7"
    assert e.outputs["dev"]["review-reviewer"] == 1.0
    cmd, detail = e.command_of(spec.blocks["reviewer"])
    assert cmd == 1.0 and detail["review"]["depth"] == "deep" and detail["item"] == "ticket/7"
    e.run_block(spec.blocks["reviewer"], "command")
    given = json.loads((tmp_path / "review-input.json").read_text())
    assert given["command"]["review"]["of"] == req[0]["data"]["of"]
    assert e.outputs["dev"]["review-reviewer"] == 0.0         # the ask answered: not asked again


def test_an_honest_blocks_work_is_not_reviewed(tmp_path):
    class B:
        params = {"review": [{"when": ("ergostat.trust.contradicted@dev", ">", 0.3), "by": "reviewer", "depth": "deep",
                              "text": "contradicted > 0.3"}, {"when": None, "by": None, "depth": "none", "text": None}]}
    d = rv.decide(None, B, read=lambda p, n: 0.0)
    assert d["by"] is None and d["why"] == "otherwise"
    d = rv.decide(None, B, read=lambda p, n: 0.5)
    assert d["by"] == "reviewer" and d["value"] == 0.5
    B.params = {"review": [{"when": ("ergostat.trust.contradicted@dev", ">", 0.3), "by": "reviewer", "depth": "deep",
                            "text": None}]}
    assert rv.decide(None, B, read=lambda p, n: 0.1)["by"] is None
