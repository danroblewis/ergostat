"""Built-in starting contexts for the parity benchmark (``parity.py``): plain text a fresh session starts from.

Each is a function returning text; any other projection (``ergostat context decisions``, a file written by hand)
is a file, and the benchmark takes files. The built-ins:

- ``none``: nothing;
- ``docs``: the repository's documents (SPEC, DESIGN, MODELLING, the proposals), concatenated;
- ``owner``: the owner's messages in a Claude Code transcript, verbatim, most recent first, to a budget;
- ``fork``: the last turns of a transcript (the owner's messages and the assistant's text, the tools it called
  named), as many as fit the budget, in order: what a session forked at the end would hold, less the tool output;
- ``memory``: a directory of memory files (Claude Code's ``memory/``), its index first.

A transcript is read here, not through the record (``transcripts.py``), because a context wants whole messages:
the record keeps the head of a long one."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

DOCS = ("docs/SPEC.md", "docs/DESIGN.md", "docs/MODELLING.md", "docs/proposals/*.md")
BUDGET = 100_000                 # characters, for the owner's words and a fork (about 25k tokens)
NOT_OWNER = ("<command-", "<local-command", "Caveat:", "[Request interrupted")


@dataclass
class Turn:
    """One message of the owner's and what the assistant said and did until the next."""
    line: int
    at: str
    owner: str
    replies: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)


def _text(content, kind: str = "text") -> str:
    if isinstance(content, str):
        return content if kind == "text" else ""
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == kind)
    return ""


def owner_text(line: dict) -> str | None:
    """What the owner typed on this line, or None when the line is not the owner's: the assistant, a tool's
    result, a subagent's, a summary of compacted context, a command's wrapper, a notification."""
    if line.get("type") != "user" or line.get("isSidechain") or line.get("isMeta") or line.get("isCompactSummary"):
        return None
    content = (line.get("message") or {}).get("content")
    if isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
        return None
    text = _text(content).strip()
    if not text or text.startswith(NOT_OWNER) or "<task-notification>" in text[:300]:
        return None
    return text


def turns(path: Path) -> list[Turn]:
    """The transcript's turns, in order. A message the owner sent again at once, longer (an edit), keeps only the
    later one."""
    out: list[Turn] = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for n, raw in enumerate(fh, 1):
            try:
                line = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(line, dict):
                continue
            said = owner_text(line)
            if said is not None:
                if out and not out[-1].replies and said.startswith(out[-1].owner[:200].rstrip()):
                    out.pop()
                out.append(Turn(n, str(line.get("timestamp") or ""), said))
                continue
            if line.get("type") != "assistant" or line.get("isSidechain") or not out:
                continue
            content = (line.get("message") or {}).get("content")
            text = _text(content).strip()
            if text:
                out[-1].replies.append(text)
            if isinstance(content, list):
                out[-1].tools += [str(b.get("name")) for b in content if isinstance(b, dict) and b.get("type") == "tool_use"]
    return out


def _cut(parts: list[str], budget: int) -> list[str]:
    kept, used = [], 0
    for p in parts:
        if used + len(p) > budget:
            break
        kept.append(p)
        used += len(p)
    return kept


def none() -> str:
    return ""


def docs(repo: Path, patterns: tuple[str, ...] = DOCS) -> str:
    out = []
    for pat in patterns:
        for f in sorted(repo.glob(pat)):
            out.append(f"=== {f.relative_to(repo)} ===\n{f.read_text(encoding='utf-8').rstrip()}\n")
    return "\n".join(out)


def owner(transcript: Path, budget: int = BUDGET) -> str:
    ts = turns(transcript)
    parts = [f"--- the owner, line {t.line}, {t.at[:16]} ---\n{t.owner}\n" for t in reversed(ts)]
    kept = _cut(parts, budget)
    head = (f"The owner's messages in the session, most recent first ({len(kept)} of {len(ts)}, "
            f"to {budget} characters).\n\n")
    return head + "\n".join(kept)


def _turn(t: Turn) -> str:
    tools = ""
    if t.tools:
        counts: dict[str, int] = {}
        for x in t.tools:
            counts[x] = counts.get(x, 0) + 1
        tools = "[tools: " + ", ".join(f"{k}×{v}" if v > 1 else k for k, v in counts.items()) + "]\n"
    said = "\n\n".join(t.replies)
    return f"--- the owner, line {t.line}, {t.at[:16]} ---\n{t.owner}\n--- the assistant ---\n{tools}{said}\n"


def fork(transcript: Path, budget: int = BUDGET, last: int | None = None) -> str:
    ts = turns(transcript)
    if last:
        ts = ts[-last:]
    parts = _cut([_turn(t) for t in reversed(ts)], budget)
    head = f"The last {len(parts)} turns of the session, in order (the tools' output left out).\n\n"
    return head + "\n".join(reversed(parts))


def memory(directory: Path) -> str:
    files = sorted(directory.glob("*.md"), key=lambda f: (f.name != "MEMORY.md", f.name))
    return "\n".join(f"=== {f.name} ===\n{f.read_text(encoding='utf-8').rstrip()}\n" for f in files)


KINDS = ("none", "docs", "owner", "fork", "memory")
