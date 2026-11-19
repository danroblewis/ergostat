"""Claude Code transcripts as events (SPEC §5a): each line of a session's JSONL, recorded as an event
about the session's item while the session runs, so the item folds into its conversation.

Any item whose kind shows a field as ``claude-session`` (``formats:``), and whose field names a
file (``file:run/sessions/x.jsonl``), is read: each new complete line becomes one event, its id
made from the item and the line's ``uuid`` (so reading a line again records nothing new), caused
by its ``parentUuid``'s event. The types:

- ``claude.message``: what the user or the assistant said (``messages``; ``meta`` on a line the harness
  wrote in the user's name, a side chain's or a compacted summary);
- ``claude.tool-use``: a tool called (``tool_calls``: id, name, input);
- ``claude.tool-result``: what came back (``tool_results``);
- ``claude.thinking``: the assistant's thinking (``thinking``);
- ``claude.other``: any other line (``other``: its type, and its head).

An assistant message's first line also carries its tokens (``tokens_in``, ``tokens_out``; a
message split over several lines repeats its usage, counted once). A text over ``LIMIT`` bytes
keeps its head in the event, with ``full``: the file and line where all of it is. The file stays
the full record of what was said and the conversation the page shows. A kind folds these with its
rules (``fold: {messages: append, tokens_out: sum, ...}``); without them each is replaced."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path

LIMIT = 4096                     # bytes of one text kept in its event; the rest is in the file
FIELDS = ("messages", "tool_calls", "tool_results", "thinking", "other", "tokens_in", "tokens_out")
EVERY = 2.0                      # seconds between looks at the files
FORMAT = "claude-session"
META = ("isMeta", "isSidechain", "isCompactSummary", "isVisibleInTranscriptOnly")   # the harness's, not said: ``meta``


def archived_ids(p, item: str) -> set[str]:
    """The ids of an item's events rolled up into its snapshot (``rollup.py``), from the archive: a
    transcript read again from its start records none of them again."""
    snap = p.events.query(n=1, item=item, type="ergostat.item.snapshot")
    if not snap:
        return set()
    from .rollup import Archive
    segs = (snap[0]["data"].get("rollup") or {}).get("archived", {}).get("segments") or []
    return {e["id"] for e in Archive(p.dir).read(item, segs)}


def event_id(item: str, key: str) -> str:
    return hashlib.sha1(f"{item}\n{key}".encode()).hexdigest()[:32]


def _head(text: str, where: dict) -> dict:
    """``{"text": ...}``, or its head with a pointer to all of it."""
    raw = text.encode()
    if len(raw) <= LIMIT:
        return {"text": text}
    return {"text": raw[:LIMIT].decode(errors="ignore"), "truncated": True, "bytes": len(raw), "full": where}


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(_text_of(b.get("text") if isinstance(b, dict) and "text" in b else b) for b in content)
    if isinstance(content, dict):
        return _text_of(content.get("text", "")) if "text" in content else json.dumps(content)
    return "" if content is None else str(content)


def _time(line: dict, before: float) -> float:
    ts = line.get("timestamp")
    if isinstance(ts, str):
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
    return before


def line_event(item: str, raw: str, n: int, file: str, seen: set, before: float) -> dict:
    """One line of a transcript (``n``, from 1), as the event it is recorded as."""
    where = {"file": file, "line": n}
    try:
        line = json.loads(raw)
    except ValueError:
        line = None
    if not isinstance(line, dict):
        return {"id": event_id(item, f"line {n} {hashlib.sha1(raw.encode()).hexdigest()[:16]}"), "type": "claude.other",
                "item": item, "at": before, "data": {"other": {"type": "unreadable", "line": n, **_head(raw, where)}}}
    at = _time(line, before)
    uid = line.get("uuid")
    key = f"uuid {uid}" if isinstance(uid, str) and uid else f"line {n} {hashlib.sha1(raw.encode()).hexdigest()[:16]}"
    parent = line.get("parentUuid")
    ev = {"id": event_id(item, key), "item": item, "at": at,
          "causedby": event_id(item, f"uuid {parent}") if isinstance(parent, str) and parent else None}
    kind, msg = line.get("type"), line.get("message")
    if kind not in ("user", "assistant") or not isinstance(msg, dict):
        return {**ev, "type": "claude.other", "data": {"other": {"type": str(kind), "line": n, **_head(raw, where)}}}
    role = msg.get("role") or kind
    content = msg.get("content")
    blocks = content if isinstance(content, list) else [{"type": "text", "text": _text_of(content)}]
    data: dict = {}
    for b in blocks:
        if not isinstance(b, dict):
            continue
        t = b.get("type")
        if t == "text" and (b.get("text") or "").strip():
            data.setdefault("messages", []).append({"role": role, "line": n, "uuid": uid, **_head(b["text"], where),
                                                    **({"meta": True} if any(line.get(k) for k in META) else {})})
        elif t == "thinking" and (b.get("thinking") or "").strip():
            data.setdefault("thinking", []).append({"line": n, **_head(b["thinking"], where)})
        elif t == "tool_use":
            inp = json.dumps(b.get("input"), default=str)
            call = {"id": b.get("id"), "name": b.get("name"), "line": n}
            if len(inp.encode()) <= LIMIT:
                call["input"] = b.get("input")
            else:
                h = _head(inp, where)
                call.update({"input_head": h["text"], "truncated": True, "bytes": h["bytes"], "full": where})
            data.setdefault("tool_calls", []).append(call)
        elif t == "tool_result":
            data.setdefault("tool_results", []).append({"tool_use_id": b.get("tool_use_id"), "error": bool(b.get("is_error")),
                                                        "line": n, **_head(_text_of(b.get("content")), where)})
    usage, mid = msg.get("usage"), msg.get("id")
    if role == "assistant" and isinstance(usage, dict) and mid not in seen:
        seen.add(mid)
        data["tokens_in"] = sum(int(usage.get(k) or 0) for k in
                                ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
        data["tokens_out"] = int(usage.get("output_tokens") or 0)
    if "tool_calls" in data:
        t = "claude.tool-use"
    elif "tool_results" in data:
        t = "claude.tool-result"
    elif "messages" in data:
        t = "claude.message"
    elif "thinking" in data:
        t = "claude.thinking"
    else:
        t, data = "claude.other", {**data, "other": {"type": str(kind), "line": n, **_head(raw, where)}}
    return {**ev, "type": t, "data": data}


class _File:
    def __init__(self):
        self.offset, self.lines, self.stat, self.seen, self.time = 0, 0, None, set(), 0.0


class Ingester:
    """Reads the transcripts the items name, as they grow, into the record. One per project, kept
    by whatever runs it (the engine, every ``EVERY`` seconds; or a test, once)."""

    def __init__(self, project, spec):
        self.p, self.spec = project, spec
        self.files: dict[tuple[str, str], _File] = {}
        self.lock = threading.Lock()
        self.note = project.dir / "transcripts.json"       # files read to their end, as they were then: not read again
        try:
            self.done = json.loads(self.note.read_text())
        except (OSError, ValueError):
            self.done = {}

    def kinds(self) -> list[tuple[str, list[str]]]:
        return [(k.name, [f for f, fmt in k.formats.items() if fmt == FORMAT]) for k in (self.spec.items or {}).values()
                if FORMAT in k.formats.values()]

    def path_of(self, value) -> Path | None:
        if not isinstance(value, str) or not value.startswith("file:"):
            return None
        root = self.p.repo.resolve()
        path = (root / value[5:]).resolve()
        if not (path.is_relative_to(root) or path.is_relative_to(self.p.dir.resolve())):
            return None                                     # only files inside the project, as the page serves them
        return path

    def once(self) -> int:
        """Look at every transcript once: how many lines were recorded."""
        from .spec import items as its
        new = 0
        with self.lock:
            for kind, fields in self.kinds():
                for it in its.project(self.p.events, self.spec, kind, transcript=False):
                    for f in fields:
                        path = self.path_of(it.fields.get(f))
                        if path is not None:
                            source = self._source(it.id)
                            new += self.read(it.id, str(it.fields[f])[5:], path, source)
            self._save()
        return new

    def _source(self, item: str) -> str:
        first = self.p.events.query(n=None, item=item, skip=("claude.*",))[:1]   # who started it: few events, these
        return (first[0].get("source") if first else None) or "claude"

    def read(self, item: str, name: str, path: Path, source: str = "claude") -> int:
        """The lines of ``path`` not read yet, recorded about ``item``."""
        try:
            st = path.stat()
        except OSError:
            return 0
        stamp = [st.st_size, st.st_mtime_ns]
        key = (item, str(path))
        f = self.files.get(key)
        if f is None:
            if self.done.get(f"{item}\n{path}") == stamp:        # read to its end before, and unchanged since
                return 0
            if time.time() - st.st_mtime > self.p.storage.logs["transcripts"] and \
                    self.p.events.query(n=1, item=item, type="claude.*"):   # read before, then forgotten: left as read
                self.files[key] = f = _File()
                f.stat = stamp
                return 0
            f = self.files[key] = _File()
        if f.stat == stamp:
            return 0
        if st.st_size < f.offset:                                # written again from the start: read it again
            self.files[key] = f = _File()
        start = f.offset
        with open(path, "rb") as fh:
            fh.seek(f.offset)
            chunk = fh.read()
        end = chunk.rfind(b"\n")
        if end < 0:
            f.stat = None if chunk else stamp
            return 0
        evs = []
        for raw in chunk[:end].split(b"\n"):
            f.lines += 1
            text = raw.decode(errors="replace").strip()
            if not text:
                continue
            e = line_event(item, text, f.lines, name, f.seen, f.time or st.st_mtime)
            f.time = e["at"]
            evs.append({**e, "source": source})
        f.offset += end + 1
        f.stat = stamp if f.offset == st.st_size else None
        if f.stat:
            self.done[f"{item}\n{path}"] = stamp
        if evs and start == 0:                                  # read from the start:
            gone = archived_ids(self.p, item)                  # lines rolled up into its snapshot are not new
            evs = [e for e in evs if e["id"] not in gone]
        return self.p.events.add_many(evs) if evs else 0

    def _save(self) -> None:
        old = time.time() - self.p.storage.logs["transcripts"]          # unchanged since: forgotten, never read again
        self.done = {k: v for k, v in self.done.items() if v[1] / 1e9 > old}
        try:
            tmp = self.note.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.done))
            os.replace(tmp, self.note)
        except OSError:
            pass

    def run(self, stop: threading.Event, say=None) -> None:
        while not stop.is_set():
            try:
                self.once()
            except Exception as e:                               # noqa: BLE001 - the next look tries again
                if say:
                    say(f"transcripts: {type(e).__name__}: {e}")
            stop.wait(EVERY)
