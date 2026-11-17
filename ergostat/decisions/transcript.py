"""A Claude Code transcript (a session's JSONL, one line per message, tool call or note), read as turns: who
spoke (the owner, or the assistant), what they said, and where (the session, the file's line, the time).

Two ways in: a file read directly (``turns``), or a session already in the record as ``claude.message`` events
(``turns_of_item``: an item whose transcript ``transcripts.py`` ingested), each message's text whole (a head cut
at 4 KB is read from the line its ``full`` names).

Only what was said counts. Tool results, the harness's own notes (task notifications, command output,
interruptions, a compacted summary, a subagent's side chain) and the reminders it inserts into a message are
left out, so an owner's turn is what the owner typed."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

HARNESS = ("<task-notification>", "<command-name>", "<command-message>", "<local-command-stdout>", "<local-command-",
           "[Request interrupted", "Caveat: The messages below", "<bash-input>", "<bash-stdout>", "<user-prompt-submit-hook>")
INSERTED = re.compile(r"<(system-reminder|artifact-content-authored-by-others)[^>]*>.*?</\1>|<artifact-content-authored-by-others/>",
                      re.S)


@dataclass
class Turn:
    role: str            # owner | assistant
    text: str
    line: int            # the line in the file, from 1
    time: float | None
    session: str

    def where(self) -> dict:
        return {"session": self.session, "line": self.line, **({"time": iso(self.time)} if self.time else {})}


def iso(t: float | None) -> str | None:
    return None if t is None else datetime.fromtimestamp(t).astimezone().isoformat(timespec="seconds")


def _time(ts) -> float | None:
    if isinstance(ts, str):
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def owner_text(raw: str) -> str:
    """What the owner typed: the harness's insertions taken out; empty when the whole message is the harness's."""
    s = raw.strip()
    if not s or s.startswith(HARNESS):
        return ""
    return INSERTED.sub("", s).strip()


def turns(path: Path, since_line: int = 0, since_time: float | None = None) -> list[Turn]:
    """Every turn after ``since_line`` (and from ``since_time``), in order. A line that is not JSON is passed by."""
    out: list[Turn] = []
    session = path.stem
    with open(path, encoding="utf-8", errors="replace") as f:
        for n, raw in enumerate(f, 1):
            if n <= since_line:
                continue
            try:
                d = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(d, dict) or d.get("type") not in ("user", "assistant"):
                continue
            if d.get("isSidechain") or d.get("isMeta") or d.get("isCompactSummary") or d.get("isVisibleInTranscriptOnly"):
                continue
            msg = d.get("message") or {}
            if not isinstance(msg, dict):
                continue
            t = _time(d.get("timestamp"))
            if since_time is not None and (t is None or t < since_time):
                continue
            session = str(d.get("sessionId") or session)
            if d["type"] == "user":
                text = owner_text(_text(msg.get("content")))
                role = "owner"
            else:
                text = _text(msg.get("content")).strip()
                role = "assistant"
            if not text:
                continue
            if out and out[-1].role == role == "assistant":      # one reply, split over lines by its tool calls
                out[-1].text += "\n\n" + text
                continue
            out.append(Turn(role, text, n, t, session))
    return out


def lines_in(path: Path) -> int:
    with open(path, "rb") as f:
        return sum(1 for _ in f)


def exchanges(ts: list[Turn], before: int = 1500, after: int = 800):
    """Each owner turn with the assistant's turns around it: the end of the one before it (what the owner was
    answering) and the start of the one after (what was done with it)."""
    for i, t in enumerate(ts):
        if t.role != "owner":
            continue
        prev = next((x for x in reversed(ts[:i]) if x.role == "assistant"), None)
        nxt = next((x for x in ts[i + 1:] if x.role == "assistant"), None)
        yield t, (prev.text[-before:] if prev else ""), (nxt.text[:after] if nxt else "")


def _full_text(p, m: dict) -> str:
    """A message's text, whole: a head cut in its event is read again from the transcript's line."""
    if not m.get("truncated") or not isinstance(m.get("full"), dict):
        return str(m.get("text") or "")
    f = m["full"]
    path = (p.repo / str(f.get("file") or "")).resolve()
    if not (path.is_relative_to(p.repo.resolve()) or path.is_relative_to(p.dir.resolve())) or not path.is_file():
        return str(m.get("text") or "")
    with open(path, encoding="utf-8", errors="replace") as fh:
        for n, raw in enumerate(fh, 1):
            if n == int(f.get("line") or 0):
                try:
                    d = json.loads(raw)
                except ValueError:
                    break
                return _text((d.get("message") or {}).get("content")) or str(m.get("text") or "")
    return str(m.get("text") or "")


def turns_of_item(p, item: str, since_line: int = 0, since_time: float | None = None) -> list[Turn]:
    """The turns of a session in the record (its ``claude.message`` events, ``transcripts.py``), in order."""
    out: list[Turn] = []
    session = item
    for e in p.events.query(n=None, item=item, type="claude.message"):
        if since_time is not None and e["time"] < since_time:
            continue
        for m in (e.get("data") or {}).get("messages") or []:
            n = int(m.get("line") or 0)
            if n <= since_line or m.get("meta"):
                continue
            raw = _full_text(p, m)
            role = "owner" if m.get("role") == "user" else "assistant"
            text = owner_text(raw) if role == "owner" else raw.strip()
            if not text:
                continue
            if out and out[-1].role == role == "assistant":
                out[-1].text += "\n\n" + text
                continue
            out.append(Turn(role, text, n, e["time"], session))
    return out
