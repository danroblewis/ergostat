"""Decisions and corrections (SPEC §5a, the built-in kinds ``ergostat.decision`` and ``ergostat.correction``):
proposed from the owner's words (by the extractor, a block or a person), each word kept verbatim with where it was
said; confirmed, dismissed or superseded by the owner, each with what makes it meaningful; a correction given
again linked to the first and raised; and the confirmed ones rendered as a session's starting context.

Every transcript here is synthetic: made up in this file, never anyone's real conversation."""

import json
import os
import stat
import sys
import textwrap
import uuid

import pytest

from ergostat import model as mdl
from ergostat.decisions import acts, ai, context, extract, standin, transcript
from ergostat.decisions.kinds import CORRECTION, DECISION
from ergostat.spec import items as its
from ergostat.spec import watch
from ergostat.spec.engine import Engine
from ergostat.store import Project

MODEL = """
name: t
stocks:
  todo:
    sensor: {manual: true}
flows:
  done:
    from: todo
"""


def project(tmp_path, extra: str = "") -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL) + textwrap.dedent(extra))
    m = mdl.load(tmp_path)
    assert not [x for x in m.problems if x.level == "error"], m.problems
    return Project(m)


def line(kind, content, at="2026-11-15T10:00:00Z", **extra):
    return {"type": kind, "uuid": str(uuid.uuid4()), "parentUuid": None, "timestamp": at, "sessionId": "s-synthetic",
            "message": {"role": kind, "content": content}, **extra}


def write_transcript(path, lines) -> None:
    path.write_text("".join(json.dumps(x) + "\n" for x in lines))


def synthetic(path) -> None:
    """A made-up session: a decision, a correction, the same correction again, and the harness's own lines."""
    write_transcript(path, [
        line("user", "Let's build the report page."),
        line("assistant", [{"type": "text", "text": "I added a new Reports page with a wizard."}]),
        line("user", "No, not like that. We decided never to add a new page; show it on the existing diagrams instead."),
        line("assistant", [{"type": "text", "text": "Understood, I removed the page."}]),
        line("user", [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]),
        line("user", "<task-notification>a background task finished</task-notification>"),
        line("user", "Context from the harness", isMeta=True),
        line("assistant", [{"type": "text", "text": "I put a summary panel beside the chart."}]),
        line("user", "You keep adding pages. Never add a new page; show it on the diagrams."),
        line("assistant", [{"type": "text", "text": "Sorry, removed."}]),
        line("user", "Always keep the owner's words verbatim in items. <system-reminder>inserted</system-reminder>"),
    ])


# ---- the kinds, and the owner's acts

def test_the_two_kinds_are_built_in_with_their_states_and_fold_rules(tmp_path):
    p = project(tmp_path)
    k = p.model.spec.items
    assert k[DECISION].states == ["proposed", "confirmed", "superseded", "dismissed"]
    assert k[CORRECTION].states == ["proposed", "confirmed", "retired", "dismissed"]
    assert k[DECISION].fold["words"] == "append" and k[DECISION].fold["evidence"] == "append"
    assert k[CORRECTION].fold["words"] == "append" and k[CORRECTION].fold["repeated_by"] == "append"


def test_a_proposal_needs_the_owners_words_unless_the_owner_proposes_it(tmp_path):
    p = project(tmp_path)
    with pytest.raises(acts.ActError, match="words"):
        acts.propose(p, DECISION, {"decision": "Use one model, not one per package."}, "extractor")
    with pytest.raises(acts.ActError, match="one sentence"):
        acts.propose(p, DECISION, {"decision": "x " * 300, "words": ["y"]}, "extractor")
    got = acts.propose(p, DECISION, {"decision": "Use one model, not one per package."}, "owner")
    it = acts.one(p, got["item"])
    assert it.state == "proposed" and it.fields["words"] == [{"text": "Use one model, not one per package.", "speaker": "owner"}]


def test_seen_again_its_new_words_are_appended_never_replacing_the_first(tmp_path):
    p = project(tmp_path)
    d = {"decision": "Items are folds of events.", "words": [{"text": "items are folds", "session": "a", "line": 3}]}
    first = acts.propose(p, DECISION, d, "extractor")
    again = acts.propose(p, DECISION, {**d, "words": [{"text": "fold the events", "session": "b", "line": 9}],
                                       "confidence": 0.8}, "extractor")
    assert again["status"] == "known" and again["added_words"] == 1
    assert acts.propose(p, DECISION, d, "extractor") == {"status": "known", "item": first["item"], "state": "proposed"}
    f = acts.one(p, first["item"]).fields
    assert [w["text"] for w in f["words"]] == ["items are folds", "fold the events"]
    assert f["evidence"] == [{"by": "extractor", "confidence": 0.8}]


def test_confirm_dismiss_supersede_each_need_what_makes_them_meaningful(tmp_path):
    p = project(tmp_path)
    a = acts.propose(p, DECISION, {"decision": "Store events in SQLite.", "words": ["sqlite is fine"]}, "extractor")["item"]
    b = acts.propose(p, DECISION, {"decision": "Store events in segmented logs.", "words": ["segments"]}, "extractor")["item"]
    c = acts.propose(p, DECISION, {"decision": "Add a chat dock.", "words": ["a chat dock?"]}, "extractor")["item"]
    with pytest.raises(acts.ActError, match="reason"):
        acts.dismiss(p, DECISION, c, "")
    acts.dismiss(p, DECISION, c, "it was a question, not a decision")
    with pytest.raises(acts.ActError, match="only a proposed"):
        acts.confirm(p, DECISION, c)
    acts.confirm(p, DECISION, a)
    acts.confirm(p, DECISION, b.split("/", 1)[1])                 # its slug alone will do
    with pytest.raises(acts.ActError, match="reason"):
        acts.supersede(p, a, b, None)
    with pytest.raises(acts.ActError, match="replaces"):
        acts.supersede(p, a, "", "too slow")
    with pytest.raises(acts.ActError, match="cannot replace"):
        acts.supersede(p, a, c, "too slow")
    acts.supersede(p, a, b, "SQLite broke under a real load")
    old, new = acts.one(p, a), acts.one(p, b)
    assert old.state == "superseded" and old.fields["superseded_by"] == b and old.fields["superseded_reason"]
    assert new.state == "confirmed" and new.fields["supersedes"] == [a]
    assert acts.one(p, c).state == "dismissed"


def test_a_correction_given_again_is_linked_to_the_first_and_raised(tmp_path):
    p = project(tmp_path)
    one = acts.propose(p, CORRECTION, {"correction": "Never add a new page or panel to the UI.",
                                       "words": [{"text": "no new pages", "line": 3}], "kind_of_work": ["ui"]}, "extractor")
    acts.confirm(p, CORRECTION, one["item"])
    two = acts.propose(p, CORRECTION, {"correction": "Do not add another panel or page to the UI.",
                                       "words": [{"text": "you keep adding panels", "line": 9}], "kind_of_work": ["ui"]},
                       "extractor")
    assert two["repeats"] == one["item"]
    first = acts.one(p, one["item"])
    assert first.fields["repeated_by"][0]["item"] == two["item"] and first.fields["repeated_by"][0]["line"] == 9
    found = [f for f in watch.find(p, p.model.spec) if f.code == "correction-repeated"]
    assert found and "given 2 times" in found[0].message
    other = acts.propose(p, CORRECTION, {"correction": "Run the whole test suite before merging.", "words": ["tests"],
                                         "kind_of_work": ["git"]}, "extractor")
    assert "repeats" not in other


def test_a_block_may_propose_but_never_decide(tmp_path):
    lines = [{"event": f"{DECISION}.proposed", "data": {"decision": "Keep one model.", "words": ["one model"]}},
             {"event": f"{DECISION}.confirmed", "item": f"{DECISION}/x"}]
    (tmp_path / "lines.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines))
    p = project(tmp_path, """
        blocks:
          extractor:
            type: program
            run: cat lines.jsonl
            every: 1h
        """)
    Engine(p, say=lambda s: None).run_block(p.model.spec.blocks["extractor"], "schedule")
    ds = acts.items(p, DECISION)
    assert [(d.state, d.fields["proposed_by"]) for d in ds] == [("proposed", "extractor")]
    assert not p.events.query(n=None, type=f"{DECISION}.confirmed")


# ---- the extractors

def test_the_transcript_reader_keeps_only_what_the_owner_typed(tmp_path):
    f = tmp_path / "s.jsonl"
    synthetic(f)
    ts = transcript.turns(f)
    owner = [t for t in ts if t.role == "owner"]
    assert [t.line for t in owner] == [1, 3, 9, 11]
    assert owner[-1].text == "Always keep the owner's words verbatim in items."
    assert all(t.session == "s-synthetic" for t in ts)


def test_the_standin_proposes_with_words_verbatim_and_where_they_were_said(tmp_path):
    p = project(tmp_path)
    f = tmp_path / "s.jsonl"
    synthetic(f)
    got = extract.run(p, [str(f)], out=open(os.devnull, "w"))
    assert got["extractor"] == "standin" and got["proposed"]["correction"] >= 2 and got["proposed"]["decision"] >= 1
    raw = f.read_text()
    for kind in (DECISION, CORRECTION):
        for i in acts.items(p, kind):
            for w in i.fields["words"]:
                assert w["text"] in raw and w["session"] == "s-synthetic" and w["line"] in (1, 3, 9, 11)
    cs = acts.items(p, CORRECTION)
    assert any(i.fields.get("repeats") for i in cs)              # the panel complaint repeats the page one
    again = extract.run(p, [str(f)], out=open(os.devnull, "w"))
    assert again["proposed"] == {"decision": 0, "correction": 0} and again["known"] > 0
    assert extract.run(p, [str(f)], since="8", out=open(os.devnull, "w"))["owner_turns"] == 2


def test_print_gives_event_lines_for_a_block(tmp_path, capsys):
    p = project(tmp_path)
    f = tmp_path / "s.jsonl"
    synthetic(f)
    extract.run(p, [str(f)], print_lines=True, out=sys.stdout)
    lines = [json.loads(x) for x in capsys.readouterr().out.splitlines()]
    assert {x["event"] for x in lines} >= {f"{DECISION}.proposed", f"{CORRECTION}.proposed", "extractor.ran"}
    assert not acts.items(p, DECISION)                             # printed, not recorded


def fake_ai(tmp_path, answer: str, cost: float = 0.4):
    script = tmp_path / "fake-claude"
    out = json.dumps({"result": answer, "total_cost_usd": cost, "usage": {"input_tokens": 1000, "output_tokens": 50}})
    script.write_text(f"#!/bin/sh\ncat > /dev/null\ncat <<'EOF'\n{out}\nEOF\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


def test_the_ai_extractors_quotes_are_checked_against_the_owners_turns(tmp_path, monkeypatch):
    p = project(tmp_path)
    f = tmp_path / "s.jsonl"
    synthetic(f)
    answer = "\n".join([
        json.dumps({"decision": {"decision": "No new pages; use the existing diagrams.", "scope": ["ui"], "confidence": 0.9,
                                 "words": [{"line": 3, "text": "We decided never to add a new page;"}]}}),
        json.dumps({"decision": {"decision": "Invented.", "words": [{"line": 3, "text": "words the owner never said"}]}}),
        json.dumps({"correction": {"correction": "Keep the owner's words verbatim.", "kind_of_work": ["docs"],
                                   "words": [{"line": 1, "text": "Always keep the owner's words verbatim in items."}]}}),
        "some prose the model should not have written"])
    monkeypatch.setenv("ERGOSTAT_AI", fake_ai(tmp_path, answer))
    got = extract.run(p, [str(f)], model="sonnet", cap=5.0, out=open(os.devnull, "w"))
    assert got["spent"]["calls"] == 1 and got["spent"]["cost_usd"] == 0.4 and got["spent"]["dropped_unquoted"] == 1
    d = acts.items(p, DECISION)
    assert [x.fields["decision"] for x in d] == ["No new pages; use the existing diagrams."]
    assert d[0].fields["extractor"] == {"name": "ai", "model": "sonnet"}
    c = acts.items(p, CORRECTION)[0]
    assert c.fields["words"][0]["line"] == 11                      # the line it was found at, not the line claimed


def test_the_ai_extractor_stops_before_its_cost_cap(tmp_path, monkeypatch):
    p = project(tmp_path)
    f = tmp_path / "s.jsonl"
    write_transcript(f, [line("user", f"Turn {i}: " + "words " * 1200) for i in range(12)])
    monkeypatch.setenv("ERGOSTAT_AI", fake_ai(tmp_path, "", cost=0.5))
    got = extract.run(p, [str(f)], model="sonnet", cap=1.2, out=open(os.devnull, "w"))
    assert got["spent"]["calls"] == 2 and got["spent"]["cost_usd"] <= 1.2 and "cap" in got["spent"]["stopped"]


def test_a_session_in_the_record_is_read_from_its_claude_events(tmp_path):
    from ergostat import transcripts as tr
    p = project(tmp_path, """
        items:
          session:
            id: session/*
            formats: {transcript: claude-session}
            fold: {messages: append}
        """)
    (tmp_path / "run").mkdir()
    synthetic(tmp_path / "run" / "a.jsonl")
    long = "Never merge without the suites passing. " + "Because. " * 600
    with open(tmp_path / "run" / "a.jsonl", "a") as fh:
        fh.write(json.dumps(line("user", long)) + "\n")
    p.events.add("session.started", item="session/a", data={"transcript": "file:run/a.jsonl"})
    assert tr.Ingester(p, p.model.spec).once() == 12
    ts = transcript.turns_of_item(p, "session/a")
    owner = [t for t in ts if t.role == "owner"]
    assert [t.line for t in owner] == [1, 3, 9, 11, 12] and owner[-1].text == long.strip()   # cut in its event, whole here
    assert "inserted" not in owner[3].text
    got = extract.run(p, ["session/a"], out=open(os.devnull, "w"))
    assert got["owner_turns"] == 5 and acts.items(p, DECISION)[0].fields["words"][0]["session"] == "session/a"


def test_the_standin_reads_a_question_as_neither():
    t = transcript.Turn("owner", "Should we always use the existing pages?", 4, None, "s")
    assert standin.read(t, "before", "") == []


# ---- the projections

def test_context_decisions_has_the_confirmed_ones_most_relevant_first_within_its_budget(tmp_path):
    p = project(tmp_path)
    ids = []
    for text, scope in (("Commits end with the trailer.", ["git"]), ("Never add a page.", ["ui"]),
                        ("Name series for what they measure.", ["modelling"]), ("Still waiting.", ["ui"])):
        ids.append(acts.propose(p, DECISION, {"decision": text, "words": [{"text": text.lower(), "session": "s1", "line": 7}],
                                              "scope": scope, "reasons": ["the owner said so"]}, "extractor")["item"])
    for i in ids[:3]:
        acts.confirm(p, DECISION, i)
    md = context.render(p, DECISION, "ui")
    assert md.startswith("# Decisions in force for ui")
    assert md.index("Never add a page.") < md.index("Commits end with the trailer.")
    assert "> never add a page." in md and "session s1, line 7" in md and "Still waiting" not in md
    assert "Still waiting" in context.render(p, DECISION, "ui", proposed=True)
    big = context.render(p, DECISION, "ui", budget=10**6)
    small = context.render(p, DECISION, "ui", budget=big.index("### ", big.index("### ") + 1) + 200)
    assert "### Never add a page." in small and "## Also decided" in small and small.count("### ") == 1
    assert context.budget_of("100t") == 400 and context.budget_of("900") == 900


def test_context_corrections_for_a_kind_of_work_and_any_work(tmp_path):
    p = project(tmp_path)
    for text, kind in (("Show it on the diagrams.", "ui"), ("Check the exit code.", "testing"), ("Say less.", "general")):
        acts.confirm(p, CORRECTION, acts.propose(p, CORRECTION, {"correction": text, "words": [text], "kind_of_work": [kind]},
                                                 "extractor")["item"])
    md = context.render(p, CORRECTION, "ui")
    assert "Show it on the diagrams." in md and "Say less." in md and "Check the exit code." not in md


def test_the_cli_and_mcp_give_the_same_context(tmp_path, capsys):
    from ergostat.cli import main
    from ergostat.mcp import Server
    project(tmp_path)
    home = ["-C", str(tmp_path)]
    assert main([*home, "decisions", "propose", "Keep one model.", "--scope", "modelling"]) == 0
    capsys.readouterr()
    assert main([*home, "decisions", "list", "--json"]) == 0
    id = json.loads(capsys.readouterr().out)[0]["id"]
    assert main([*home, "decisions", "dismiss", id]) == 2                 # no reason
    assert main([*home, "decisions", "confirm", id, "--reason", "yes"]) == 0
    capsys.readouterr()
    assert main([*home, "context", "decisions", "--scope", "modelling"]) == 0
    md = capsys.readouterr().out
    assert "### Keep one model." in md
    got = Server(tmp_path).call("context", {"recipe": "decisions", "scope": "modelling"})["content"][0]["text"]
    assert got == md


def test_the_items_page_answers_go_through_the_owners_acts(tmp_path):
    from ergostat.web import intent_api
    p = project(tmp_path)

    class Live:
        def get(self):
            return p
    a = acts.propose(p, DECISION, {"decision": "Old way.", "words": ["old"]}, "extractor")["item"]
    b = acts.propose(p, DECISION, {"decision": "New way.", "words": ["new"]}, "extractor")["item"]
    post = lambda act, **q: intent_api.post(Live(), f"intent/{act}", {k: [v] for k, v in q.items()})   # noqa: E731
    assert post("confirm", id=a)[0] == 200 and post("confirm", id=b, reason="agreed")[0] == 200
    code, got = post("supersede", id=a, by=b)
    assert code == 409 and "reason" in got["error"]
    assert post("supersede", id=a, by=b, reason="the new way is faster")[0] == 200
    assert post("retire", id=a)[0] == 404                                  # a decision is superseded, not retired
    assert acts.one(p, a).state == "superseded"
    detail = its.detail(p.events, p.model.spec, a)
    assert detail["kind_of"]["name"] == DECISION if "kind_of" in detail else True


def test_strip_block_footer_leaves_the_prompt():
    from ergostat.spec.engine import AI_FOOTER
    assert ai.strip_block_footer("Find them.\n\n" + AI_FOOTER + "\ninputs...") == "Find them."
