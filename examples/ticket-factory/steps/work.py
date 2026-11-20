"""work: the AI agent (AI=claude, on AI_MODEL) or the stand-in does what the ticket asks, in its workspace
(ERGOSTAT_WORKSPACE: a git worktree from the pool `code`, on the ticket's branch, ERGOSTAT_BRANCH), with
prompts/work.md. What it changed is committed here; it cannot push. Its cost is recorded on the ticket."""

from pathlib import Path

import agent
from step import Move, Stop
from tf import env, key_of, once


def run(ticket):
    f = ticket["fields"]
    ws, branch = Path(env("ERGOSTAT_WORKSPACE")), env("ERGOSTAT_BRANCH")
    def work():
        got = agent.run("work", ticket, ws)
        return {**got, "head": agent.commit(ws, f"{key_of(ticket)}: {f.get('title', 'the work')}")}
    got = once(f"{key_of(ticket)}.work", work)
    head = got["head"]
    if not head:
        return Stop(f"the agent changed nothing: {got['said'][:200]}")
    return Move({**agent.spent(got), "head": head, "work_said": got["said"], "branch": branch, "workspace": str(ws)})
