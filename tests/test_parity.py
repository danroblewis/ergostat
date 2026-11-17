"""The parity benchmark (ergostat/bench/parity.py, contexts.py, parity_draft.py) on made-up data: cases, exact
checks, verdicts, the run with stand-in sessions (in Python and as a ``claude`` stand-in command), resuming, the
cost cap, the scorecard, the built-in contexts read from a made-up transcript, and drafting with its quote check."""

from __future__ import annotations

import json
import os
import stat
import sys

import pytest

from ergostat.bench import contexts as cx
from ergostat.bench import parity as pb
from ergostat.bench import parity_draft as pd
from ergostat.cli import main

CASES = [
    {"id": "colour", "kind": "preference", "question": "What colour does the owner want the buttons?",
     "truth": "make them green, never red", "source": "line 3", "checks": {"all": ["green"], "none": ["red"]}},
    {"id": "why-yaml", "kind": "decision", "question": "Why was the config kept in one file?",
     "truth": "one small file I can read", "source": "line 5"},
    {"id": "brief", "kind": "task", "question": "Write a brief for an agent to add a page.",
     "truth": "no new pages, ever", "source": "line 7"},
]


class Fake:
    """A stand-in session: answers by what the context holds; judges by whether the answer has the truth's word."""

    def __init__(self, usd=0.01):
        self.calls, self.usd = [], usd

    def ask(self, system, prompt, tools=()):
        self.calls.append((system, prompt))
        if system == pb.JUDGE:
            truth = prompt.split(":\n", 2)[2].split("\n\n")[0]
            answer = prompt.rsplit("Answer to judge:\n", 1)[1]
            word = truth.split()[2].strip(",.")
            v = "correct" if word in answer.lower() else "contradicts" if "red" in answer.lower() else "wrong"
            return pb.Reply(json.dumps({"verdict": v, "reason": f"looked for {word}"}), self.usd, 100, 10)
        if "green" in system and "colour" in prompt:
            return pb.Reply("Green, never red? Green.", self.usd, 1000, 20)
        if "colour" in prompt:
            return pb.Reply("Red, probably.", self.usd, 10, 5)
        return pb.Reply("I do not know.", self.usd, 10, 5)


def write_cases(tmp_path, rows=CASES):
    f = tmp_path / "cases.jsonl"
    f.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return f


def test_cases_load_and_refuse_what_is_wrong(tmp_path):
    cs = pb.load_cases(write_cases(tmp_path))
    assert [c.id for c in cs] == ["colour", "why-yaml", "brief"]
    with pytest.raises(ValueError, match="kind"):
        pb.load_cases(write_cases(tmp_path, [{**CASES[0], "kind": "gossip"}]))
    with pytest.raises(ValueError, match="read-only"):
        pb.load_cases(write_cases(tmp_path, [{**CASES[0], "tools": ["Bash"]}]))
    with pytest.raises(ValueError, match="twice"):
        pb.load_cases(write_cases(tmp_path, [CASES[0], CASES[0]]))
    f = tmp_path / "c.json"
    f.write_text(json.dumps(CASES))
    assert len(pb.load_cases(f)) == 3


def test_exact_checks():
    c = pb.Case.of(CASES[0])
    assert pb.check(c, "Green.") is True
    assert pb.check(c, "green or red") is False
    assert pb.check(c, "blue") is False
    assert pb.check(pb.Case.of(CASES[1]), "anything") is None
    assert pb.check(pb.Case.of({**CASES[1], "checks": {"any": ["one", "single"]}}), "a single file") is True


def test_verdicts_are_read_from_the_judges_reply():
    assert pb.parse_verdict('thinking...\n{"verdict": "Partly", "reason": "half"}') == ("partly", "half")
    assert pb.parse_verdict("```\n{\"verdict\": \"contradicts\", \"reason\": \"x\"}\n```")[0] == "contradicts"
    assert pb.parse_verdict("I'd say wrong.")[0] == "wrong"
    assert pb.parse_verdict("no idea")[0] is None


def test_variants_from_files(tmp_path):
    (tmp_path / "words.txt").write_text("the owner said green")
    vs = pb.load_variants(["none", f"owner={tmp_path / 'words.txt'}", str(tmp_path / "words.txt")])
    assert vs == {"none": "", "owner": "the owner said green", "words": "the owner said green"}
    assert "<context>" in pb.system_for("x") and "<context>" not in pb.system_for("")


def test_run_scores_each_variant_and_writes_the_scorecard(tmp_path):
    cases = pb.load_cases(write_cases(tmp_path))
    f = Fake()
    card = pb.run(cases, {"none": "", "words": "the owner wants green"}, f, f, tmp_path / "out", workers=2)
    v = card["variants"]
    assert v["none"]["contradicts"] == 1 and v["none"]["wrong"] == 2 and v["none"]["score"] == 0.0
    assert v["words"]["correct"] == 1 and v["words"]["score"] == round(1 / 3, 3)
    assert v["words"]["checks_passed"] == 0 and v["words"]["checks"] == 1     # "never red" names red: the check fails
    assert v["words"]["by_kind"] == {"decision": 0.0, "preference": 1.0, "task": 0.0}
    assert v["words"]["context_chars"] == len("the owner wants green")
    assert card["usd"] == pytest.approx(0.12)
    md = (tmp_path / "out" / "scorecard.md").read_text()
    assert "| words |" in md and "‼" in md and "### none (3)" in md
    assert json.loads((tmp_path / "out" / "scorecard.json").read_text())["variants"]["none"]["cases"] == 3
    assert len((tmp_path / "out" / "answers.jsonl").read_text().splitlines()) == 6
    # judged by a separate session, given the truth; the answering session never sees it
    answers = [p for s, p in f.calls if s != pb.JUDGE]
    assert not any("never red" in p for p in answers)


def test_a_run_again_runs_only_what_is_missing_and_a_new_context_runs_again(tmp_path):
    cases = pb.load_cases(write_cases(tmp_path))
    pb.run(cases, {"none": ""}, Fake(), Fake(), tmp_path / "out")
    f = Fake()
    card = pb.run(cases, {"none": "", "words": "green"}, f, f, tmp_path / "out")
    assert len([1 for s, _ in f.calls if s != pb.JUDGE]) == 3                 # only the new variant's
    assert card["variants"]["none"]["cases"] == 3
    f = Fake()
    pb.run(cases, {"none": "", "words": "green, changed"}, f, f, tmp_path / "out")
    assert len([1 for s, _ in f.calls if s != pb.JUDGE]) == 3                 # its context changed


def test_the_cost_cap_stops_starting_cases(tmp_path):
    cases = pb.load_cases(write_cases(tmp_path))
    card = pb.run(cases, {"none": "", "words": "green"}, Fake(usd=0.5), Fake(usd=0.5), tmp_path / "out",
                  workers=1, max_usd=2.5)
    ran = sum(v["cases"] for v in card["variants"].values())
    assert ran == 3 and card["stopped_at_cap"]
    assert "Stopped at the cost cap" in (tmp_path / "out" / "scorecard.md").read_text()


def test_an_answer_that_failed_is_not_judged_and_runs_again(tmp_path):
    class Broken(Fake):
        def ask(self, system, prompt, tools=()):
            return pb.Reply(error="timed out")
    cases = pb.load_cases(write_cases(tmp_path))
    j = Fake()
    card = pb.run(cases, {"none": ""}, Broken(), j, tmp_path / "out")
    assert card["variants"]["none"]["unjudged"] == 3 and not j.calls
    f = Fake()
    pb.run(cases, {"none": ""}, f, f, tmp_path / "out")
    assert len(f.calls) == 6


STANDIN = r'''
import json, sys
a = sys.argv
system = open(a[a.index("--system-prompt-file") + 1]).read()
tools = a[a.index("--tools") + 1]
prompt = sys.stdin.read()
if system.startswith("You judge"):
    out = {"verdict": "correct" if "green" in prompt.split("Answer to judge:")[1] else "wrong", "reason": "r"}
    text = json.dumps(out)
else:
    text = ("green" if "green" in system else "no idea") + (" tools:" + tools if tools else "")
print(json.dumps({"result": text, "total_cost_usd": 0.002, "is_error": False,
                  "usage": {"input_tokens": 3, "cache_read_input_tokens": 500, "output_tokens": 7}}))
'''


@pytest.fixture
def standin(tmp_path, monkeypatch):
    f = tmp_path / "claude-standin"
    f.write_text(f"#!{sys.executable}\n{STANDIN}")
    f.chmod(f.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("ERGOSTAT_AI", str(f))
    return f


def test_the_command_line_runs_it_with_a_stand_in_claude(tmp_path, standin, capsys):
    cases = write_cases(tmp_path, [{**CASES[0], "checks": {}, "tools": ["Read"]}, CASES[1]])
    (tmp_path / "ctx.txt").write_text("green")
    rc = main(["bench", "parity", "run", "--cases", str(cases), "--variant", "none", "--variant", f"g={tmp_path / 'ctx.txt'}",
               "--out", str(tmp_path / "out"), "--repo", str(tmp_path)])
    assert rc == 0
    card = json.loads((tmp_path / "out" / "scorecard.json").read_text())
    assert card["variants"]["g"]["correct"] == 2 and card["variants"]["none"]["wrong"] == 2
    assert card["variants"]["g"]["tokens_in"] == 2 * 503 and card["usd"] == pytest.approx(0.016)
    rows = [json.loads(x) for x in (tmp_path / "out" / "answers.jsonl").read_text().splitlines()]
    assert any("tools:Read" in r["answer"] for r in rows if r["case"] == "colour")
    assert not any("tools:" in r["answer"] for r in rows if r["case"] == "why-yaml")
    assert "# Parity benchmark" in capsys.readouterr().out


def test_a_session_that_fails_is_an_error_not_an_answer(tmp_path, monkeypatch):
    f = tmp_path / "bad"
    f.write_text(f"#!{sys.executable}\nimport json; print(json.dumps({{'result': 'API Error: overloaded', 'is_error': True}}))")
    f.chmod(f.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("ERGOSTAT_AI", str(f))
    r = pb.Claude().ask("s", "q")
    assert r.error and "overloaded" in r.error
    monkeypatch.setenv("ERGOSTAT_AI", str(tmp_path / "missing"))
    assert pb.Claude().ask("s", "q").error.startswith("FileNotFoundError")


def transcript(tmp_path):
    def u(text, **more):
        return {"type": "user", "timestamp": "2026-01-01T10:00:00Z", "message": {"role": "user", "content": text}, **more}

    def a(text, tool=None):
        content = [{"type": "text", "text": text}] + ([{"type": "tool_use", "name": tool, "input": {}}] if tool else [])
        return {"type": "assistant", "message": {"role": "assistant", "content": content}}

    rows = [u("summary of earlier", isCompactSummary=True),
            u("Make the buttons green, never red."),                       # line 2
            a("Done: green.", "Edit"),
            u([{"type": "tool_result", "content": "ok", "tool_use_id": "x"}]),
            a("Also ran the tests.", "Bash"),
            u("Keep the config in one"),                                    # an edit sent again at once, longer
            u("Keep the config in one small file I can read."),            # line 7
            a("Agreed."),
            u("<command-name>/clear</command-name>"),
            u("sub", isSidechain=True),
            u("[Request interrupted by user]")]
    f = tmp_path / "t.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in rows) + "\nnot json\n")
    return f


def test_turns_keep_only_what_the_owner_typed(tmp_path):
    ts = cx.turns(transcript(tmp_path))
    assert [(t.line, t.owner) for t in ts] == [(2, "Make the buttons green, never red."),
                                               (7, "Keep the config in one small file I can read.")]
    assert ts[0].replies == ["Done: green.", "Also ran the tests."] and ts[0].tools == ["Edit", "Bash"]


def test_the_built_in_contexts(tmp_path):
    t = transcript(tmp_path)
    own = cx.owner(t)
    assert own.index("one small file") < own.index("buttons green")        # most recent first
    assert "summary of earlier" not in own and "2 of 2" in own
    assert "1 of 2" in cx.owner(t, budget=100)
    fk = cx.fork(t)
    assert fk.index("buttons green") < fk.index("one small file") and "[tools: Edit, Bash]" in fk
    assert "Agreed." in fk and "buttons" not in cx.fork(t, last=1)
    (tmp_path / "docs" / "proposals").mkdir(parents=True)
    (tmp_path / "docs" / "SPEC.md").write_text("spec")
    (tmp_path / "docs" / "proposals" / "p.md").write_text("proposal")
    d = cx.docs(tmp_path)
    assert "=== docs/SPEC.md ===\nspec" in d and "=== docs/proposals/p.md ===" in d
    m = tmp_path / "mem"
    m.mkdir()
    (m / "a.md").write_text("a rule")
    (m / "MEMORY.md").write_text("index")
    assert cx.memory(m).index("index") < cx.memory(m).index("a rule")
    assert cx.none() == ""


def test_the_context_command(tmp_path, capsys):
    t = transcript(tmp_path)
    assert main(["bench", "parity", "context", "owner", "--transcript", str(t)]) == 0
    assert "buttons green" in capsys.readouterr().out
    assert main(["bench", "parity", "context", "fork"]) == 2


def test_quotes_are_checked_against_the_owners_lines(tmp_path):
    at = {2: "Make the buttons  green, never red.", 7: "Keep the config in one small file I can read."}
    assert pd.verified("the buttons green … one small file", "line 2, line 7", at)
    assert pd.verified("Make the buttons green", "2", at)
    assert not pd.verified("make them blue", "line 2", at)
    assert not pd.verified("one small file", "line 2", at)                  # said, but not at the line given


def test_drafting_reads_the_owner_in_parts_and_checks_each_quote(tmp_path):
    t = transcript(tmp_path)

    class Drafter:
        def __init__(self):
            self.prompts = []

        def ask(self, system, prompt, tools=()):
            self.prompts.append(prompt)
            rows = [{"id": "buttons", "kind": "preference", "question": "q?", "truth": "buttons green, never red",
                     "source": "line 2"},
                    {"id": "buttons", "kind": "decision", "question": "q2?", "truth": "made up", "source": "line 7"},
                    {"kind": "gossip", "question": "x", "truth": "y"}]
            return pb.Reply("Here:\n" + "\n".join(json.dumps(r) for r in rows), usd=0.1)

    d = Drafter()
    rows, usd = pd.draft(t, d, n_parts=2)
    assert len(d.prompts) == 2 and usd == pytest.approx(0.2)
    assert "### line 2" in d.prompts[0] and "### line 7" in d.prompts[1] and "[...Done: green." in d.prompts[1]
    assert [r["id"] for r in rows] == ["buttons", "buttons-2", "buttons-2-2", "buttons-2-2-2"]
    assert [r["verified"] for r in rows] == [True, False, True, False]


def test_parts_are_about_equal(tmp_path):
    ts = [cx.Turn(i, "", "x" * 100) for i in range(10)]
    ps = pd.parts(ts, 3)
    assert len(ps) == 3 and all("### line" in p for p in ps)
    assert sum(p.count("### line") for p in ps) == 10


def test_no_case_file_is_an_error(tmp_path, capsys):
    assert main(["bench", "parity", "run", "--cases", str(tmp_path / "missing"), "--out", str(tmp_path / "o")]) == 2
    assert os.path.exists(tmp_path / "o") is False
