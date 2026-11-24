"""gap/sessions-know-the-shell-rule (dev/records/sessions-know-the-shell-rule.md): the implementor's and the reviewer's
rendered briefs say how the shell works (one allowed command per Bash call, what to use instead, a refusal no reason to
stop), every command the briefs tell a session to run is one its role is allowed, and refused commands per session is
a measure on the factory's model."""

from __future__ import annotations

import re
import subprocess
import sys

import yaml

from tests.test_agents import may, permits
from tests.test_factory import BIN, ROOT, Factory, module

DEFINITION = "# alpha-thing: a thing\n\nDefinition of done.\n1. It is done.\n"
GAP = {"id": "gap/alpha-thing", "fields": {"title": "Alpha thing", "branch": "alpha-thing"}}
CFG = {"git": {"base": "main"}, "ai": {"implementor_model": "opus", "reviewer_model": "opus"}}
# the first word of a backticked span that makes it a command (a program, or a script by its path)
PROGRAMS = {"uv", "git", "python", "python3", "pytest", "ls", "wc", "mkdir", "rm", "cd", "cat", "head", "tail", "timeout",
            "sh", "bash", "docker", "ps", "grep", "sed", "awk", "echo", "curl", "wget", "find", "make", "pip", "npm",
            "node", "ssh", "gh", "ergostat"}
RULE = ["# How the shell works here", "Each Bash call must be one allowed command by itself",
        "`&&`, `;`, `|`, `cd`, `cat`, `head`, `timeout`, `python3` and `git -C` are refused, even when each part is allowed",
        "Read files with Read, search with Grep and Glob", "run each command you need as a separate call",
        "A refusal means the form of the command was wrong, not that the shell is unavailable: use the allowed form and "
        "carry on", "Never stop, park or report the environment as broken because of one"]


def briefs(monkeypatch) -> tuple[object, dict[str, str]]:
    """(agents, each role's brief as its session is given it): assembled from the real templates by brief.py, the
    knowledge block and GAPS.md entry stood in (they are the factory's record, not the templates); the implementor's
    with the page paragraph agents.session adds."""
    fac = module("fac")
    monkeypatch.setitem(sys.modules, "fac", fac)
    agents, knowledge = module("agents"), module("knowledge")
    monkeypatch.setitem(sys.modules, "agents", agents)
    monkeypatch.setitem(sys.modules, "knowledge", knowledge)
    monkeypatch.setattr(knowledge, "block", lambda cfg, role, gap, text: ("(the factory's knowledge)", {}))
    brief = module("brief")
    monkeypatch.setattr(brief, "gaps_entry", lambda cfg, title: "")
    implementor, _ = brief.assemble(CFG, "implementor", GAP, ROOT, definition=DEFINITION)
    reviewer, _ = brief.assemble(CFG, "reviewer", GAP, ROOT, definition=DEFINITION, diff="```diff\n```", net_lines=3,
                                 unlisted="(none)", gates="all passed")
    return agents, {"implementor": implementor + agents.LOOK, "reviewer": reviewer}


def commands(text: str) -> list[tuple[str, str]]:
    """(each backticked span that is a command, its line)."""
    return [(span, line) for line in text.splitlines() for span in re.findall(r"`([^`\n]+)`", line)
            if span.split()[0] in PROGRAMS]


def test_both_briefs_state_the_shell_rule_and_tell_only_allowed_commands(monkeypatch):
    agents, got = briefs(monkeypatch)
    for role, text in got.items():
        flat = " ".join(text.split())
        assert not [r for r in RULE if r not in flat], role                     # the rule, in its whole
        assert "{shell}" not in text and flat.count("# How the shell works here") == 1, role
        told = commands(text)
        for span, line in told:
            if span in agents.REFUSED:                                          # a form named as refused
                assert "are refused" in line, (role, span)
            elif permits(agents.DENY, span):                                    # a command named as never to run
                assert re.search(r"\bnever\b", line, re.I), (role, span, line)
            else:
                assert may(span, role), (role, span)                            # told to run: allowed to this role
        # the rule names, as what to use instead, exactly the role's own Bash commands
        rule = text[text.index("# How the shell works here"):]
        rule = rule[:rule.index("\n", rule.index("Never stop"))]
        listed = {s for s, _ in commands(rule) if s not in agents.REFUSED}
        assert listed == {t.removeprefix("Bash(").removesuffix(":*)") for t in agents.TOOLS[role]
                          if t.startswith("Bash(")}, role
    run = {s for s, _ in commands(got["implementor"])}
    assert {"git add", "git commit",                    # (no ruff: lint is the pre-commit hook's, never a gate)
            "uv run python scripts/named_tests.py tests/test_x.py",
            "uv run python scripts/suite_watch.py -- uv run --with playwright==1.63.0 python scripts/named_tests.py "
            "tests/test_x.py", "uv run python scripts/demo_up.py start DEMO",
            "uv run --with playwright==1.63.0 python scripts/walk.py STEPS --shots /shots"} <= run   # (the check sees them)
    assert "Edit and Write" in got["implementor"] and "Edit and Write" not in got["reviewer"]   # (the reviewer writes none)
    assert not [s for s, _ in commands(got["reviewer"]) if "pytest" in s]      # no test run the reviewer is refused


def test_the_allowlist_is_not_widened(monkeypatch):
    agents, _ = briefs(monkeypatch)
    assert agents.TOOLS["reviewer"] == ["Read", "Glob", "Grep", "Bash(git diff:*)", "Bash(git log:*)", "Bash(git show:*)"]
    for role in ("implementor", "reviewer"):                   # the forms the rule names as refused stay refused
        assert not [c for c in ("cd tests", "cat x", "head x", "timeout 5 git log", "python3 x.py", "git -C /work log")
                    if may(c, role)], role
        assert not [t for t in agents.TOOLS[role] if t.startswith("Bash(") and ("*" in t[:-3] or "&" in t or "|" in t)]


def session(i: int, **data) -> list[dict]:
    sid = f"session/alpha-thing-implementor-{i}"
    return [{"event": "session.started", "item": sid, "data": {"role": "implementor", "started": 1e10, "round": 1}},
            {"event": "session.ended", "item": sid, "data": {"cost": 0.1, **data}}]


def test_refused_commands_per_session_is_a_measure_on_the_model(tmp_path):
    f = Factory(tmp_path / "f")
    measure = lambda: subprocess.run([sys.executable, str(BIN / "measure.py"), "refused-commands-per-session"],  # noqa: E731
                                     cwd=f.model, env=f.env, capture_output=True, text=True)
    f.fold(session(1, tool_denials_unknown=1), None)                         # only a session whose refusals are unknown
    r = measure()
    assert r.returncode != 0 and "no value" in r.stderr and not r.stdout.strip()   # unknown, never 0
    f.fold(session(2, tool_denials=3, denied=["Bash: git status && git log", "Bash: cat x", "Edit: x.py"])
           + session(3, tool_denials=0, denied=[]), None)
    r = measure()
    assert r.returncode == 0 and float(r.stdout) == 1.0, r.stderr             # 2 Bash refusals over the 2 that said
    assert "1 session(s) whose refusals are unknown" in r.stderr              # left out, said, not counted as 0
    model = yaml.safe_load((BIN.parent / "model" / "measures.yaml").read_text())
    aux = model["auxiliaries"]["refused-commands-per-session"]
    assert aux["sensor"]["run"] == "python3 dev/bin/measure.py refused-commands-per-session"
    assert aux["unit"] == "calls/session"
