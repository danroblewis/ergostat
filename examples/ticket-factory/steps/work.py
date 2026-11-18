"""work: the AI agent (AI=claude, on AI_MODEL) or the stand-in does what the ticket asks, in its workspace
(prompts/work.md). What it changed is committed here; it cannot push. Its cost is recorded on the ticket."""

from pathlib import Path

import agent
from step import Move, Stop
from tf import key_of


def run(ticket):
    f = ticket["fields"]
    ws = Path(f["workspace"])
    got = agent.run("work", ticket, ws)
    head = agent.commit(ws, f"{key_of(ticket)}: {f.get('title', 'the work')}")
    spent = agent.spent(got)
    if not head:
        return Stop(f"the agent changed nothing: {got['said'][:200]}")
    return Move({**spent, "head": head, "work_said": got["said"]})
