"""A Claude Code session, as an item ergostat shows (Items: session/developer-1a2b3c4d), from the
moment it starts: open while it runs, then done or failed, with its cost, turns and time, what it
said, and its transcript, kept as run/sessions/<item>.jsonl and copied there as it grows, so the
page can show the conversation while it happens.

    session.py run ROLE MODEL     the whole session: the prompt (stdin) to `claude -p`

ergostat's session helper runs it (`ergostat session`, ergostat's SPEC §12h): the session takes the
owner's messages while it works (`ergostat message "try a lossless path for logos" --about developer`),
written into it live as its next turn; its claims are marked with the session and its model. What is
this lab's own is which tools each role may use."""

import os
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def ergostat() -> list[str]:
    cmd = os.environ.get("ERGOSTAT_CMD")
    return shlex.split(cmd) if cmd else ["ergostat", "-C", str(ROOT)]


ALLOWED = ["Bash(bin/py:*)", "Bash(python3:*)", "Bash(git:*)", "Bash(ls:*)", "Bash(cat:*)", "Read", "Edit", "Write", "Glob", "Grep"]


def tools(role: str) -> list[str]:
    """What the session may use. The improver reads and proposes, and changes nothing: ergostat's tools over MCP
    (check, fit, residuals, explain, try_change, ...), and reading the files."""
    if role != "improver":
        return ["--permission-mode", "acceptEdits", "--allowedTools", *ALLOWED]
    import json
    py = ergostat()[0]
    mcp = {"mcpServers": {"ergostat": {"command": py, "args": [*ergostat()[1:], "mcp"]}}}
    return ["--mcp-config", json.dumps(mcp), "--strict-mcp-config", "--allowedTools", "mcp__ergostat", "Read", "Glob", "Grep",
            "Bash(ls:*)", "Bash(cat:*)", "--disallowedTools", "Edit", "Write", "NotebookEdit"]


def run(role: str, model: str) -> int:
    os.execvp(ergostat()[0], [*ergostat(), "session", role, "--model", model, "--keep", str(ROOT / "run" / "sessions"),
                              "--", *tools(role)])


if __name__ == "__main__":
    sys.exit(run(sys.argv[2], sys.argv[3]))
