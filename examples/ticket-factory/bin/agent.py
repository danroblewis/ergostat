"""The work itself, in a ticket's workspace: done by Claude Code (AI=claude, on AI_MODEL, haiku by default) or
by the stand-in (AI=standin: free, a scripted change). Three jobs, each with its prompt in prompts/:

    work      do what the ticket asks
    review    answer the reviewers' comments with a change
    ci        read the failing CI log, and fix what it says

The agent edits files in the ticket's workspace (a git worktree ergostat's pool gave the step). It is told
not to push, call gh, or reach Jira, and its tools here are the file tools and read-only git (Claude Code's
--allowedTools and --disallowedTools, below; not ergostat's OS sandbox, which only a session ergostat starts
gets). The step commits what it changed, and pushing is a gated action (factory/actions.yaml). Every session's cost is recorded on its ticket (ai_cost_usd, ai_runs, ai_seconds), and its
whole answer kept in run/sessions/.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

from tf import ROOT, SESSIONS, conf, yes

TOOLS = ["Read", "Edit", "Write", "Glob", "Grep", "Bash(ls:*)", "Bash(cat:*)", "Bash(git status:*)",
         "Bash(git diff:*)", "Bash(git log:*)"]
NEVER = ["Bash(git push:*)", "Bash(git commit:*)", "Bash(gh:*)", "Bash(curl:*)", "WebFetch", "WebSearch"]


def prompt(job: str, **values) -> str:
    text = (ROOT / "prompts" / f"{job}.md").read_text()
    return re.sub(r"\{(\w+)\}", lambda m: str(values.get(m.group(1), m.group(0))), text)


def run(job: str, ticket: dict, workspace: Path, **context) -> dict:
    """Do the job; returns what it cost and said: {ai, cost_usd, seconds, said, session}."""
    f = ticket["fields"]
    key = ticket["id"].split("/", 1)[1]
    values = {"key": key, "title": f.get("title", ""), "description": f.get("description", ""), **context}
    SESSIONS.mkdir(parents=True, exist_ok=True)
    n = len(list(SESSIONS.glob(f"{key}-{job}-*.json"))) + 1
    session = SESSIONS / f"{key}-{job}-{n}.json"
    began = time.time()
    if conf("AI") == "claude":
        out = _claude(prompt(job, **values), workspace)
    else:
        out = _standin(job, key, f, workspace, context)
    out["seconds"] = round(time.time() - began, 1)
    session.write_text(json.dumps(out, indent=1))
    return {"ai": conf("AI"), "model": conf("AI_MODEL") if conf("AI") == "claude" else "standin",
            "cost_usd": float(out.get("total_cost_usd") or 0), "seconds": out["seconds"],
            "said": str(out.get("result", ""))[:2000], "session": f"file:{session.relative_to(ROOT)}"}


def _claude(text: str, workspace: Path) -> dict:
    cmd = ["claude", "-p", "--model", conf("AI_MODEL", "haiku"), "--output-format", "json",
           "--max-budget-usd", conf("AI_BUDGET_USD", "0.50"), "--permission-mode", "acceptEdits",
           "--allowedTools", *TOOLS, "--disallowedTools", *NEVER]
    r = subprocess.run(cmd, input=text, cwd=workspace, capture_output=True, text=True, timeout=900)
    try:
        out = json.loads(r.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"claude answered no JSON (exit {r.returncode}): {(r.stderr or r.stdout)[:300]}") from None
    if out.get("is_error"):
        raise RuntimeError(f"claude: {out.get('subtype')}: {str(out.get('result'))[:300]}")
    return out


def _standin(job: str, key: str, f: dict, ws: Path, context: dict) -> dict:
    """A scripted change, free: what an engineer in a hurry would do."""
    work = ws / "work"
    work.mkdir(exist_ok=True)
    mine = work / f"{key}.txt"
    if job == "work":
        mine.write_text(f"{key}: {f.get('title', 'the work')}\n\nDone by the stand-in for an AI agent.\n")
        if yes("STANDIN_PLACEHOLDER"):
            (work / f"{key}-notes.txt").write_text("")           # left empty: CI catches it
        said = f"wrote {mine.name}"
    elif job == "review":
        with mine.open("a") as fh:
            for c in context.get("comments_list", []):
                fh.write(f"\nAnswering the review: {c.strip().splitlines()[0][:120]}\n")
        said = f"answered {len(context.get('comments_list', []))} comment(s) in {mine.name}"
    elif job == "ci":
        named = set(re.findall(r"test -s \"?([\w./-]+\.txt)", context.get("log", "")))
        empty = sorted(f for f in named if (ws / f).exists() and (ws / f).stat().st_size == 0)
        if not empty and "test -s" in context.get("log", "") + _workflows(ws):   # none it names is empty: check all
            empty = sorted(str(p.relative_to(ws)) for p in work.glob("*.txt") if p.stat().st_size == 0)
        for rel in empty:
            (ws / rel).write_text(f"Notes for {key}: filled in after CI said this file was empty.\n")
        said = "filled " + (", ".join(empty) or "nothing: the log named no empty file")
    else:
        raise ValueError(job)
    return {"result": said, "total_cost_usd": 0}


def _workflows(ws: Path) -> str:
    return "".join(p.read_text() for p in (ws / ".github" / "workflows").glob("*.y*ml"))


def commit(ws: Path, message: str) -> str | None:
    """Commit everything the agent changed; the new head, or None when it changed nothing."""
    from tf import git
    git("add", "-A", cwd=ws)
    if not git("status", "--porcelain", cwd=ws):
        return None
    git("commit", "-q", "-m", message, cwd=ws)
    return git("rev-parse", "HEAD", cwd=ws)


def spent(got: dict) -> dict:
    """What a session adds to its ticket's fields (folded: the costs summed, the sessions listed)."""
    return {"ai_cost_usd": round(got["cost_usd"], 6), "ai_runs": 1, "ai_seconds": got["seconds"],
            "sessions": [got["session"]], "last_session": got["session"], "ai_model": got["model"]}
