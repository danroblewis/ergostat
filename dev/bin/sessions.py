"""Each AI session's conversation, kept: Claude Code's own session file, as an item of kind `session`.

A session runs with `--session-id` chosen here and a folder of its own mounted as Claude Code's projects folder in its
container (`/home/dev/.claude/projects`: that one folder, nothing else of the host's home), under the session's
scratch folder in `<live>/sessions/` (never served, never read by ergostat). While it runs, the complete lines Claude
Code writes there are copied, the session token scrubbed from each (and asserted gone), into
`run/sessions/<item>-<role>-<n>.jsonl`, at most CAP bytes (then one line says the rest was cut). The item
`session/<item>-<role>-<n>` names that file as its `transcript` (format `claude-session`, ergostat.yaml), so the page
shows the conversation as it grows and ergostat records each line as a `claude.*` event about it (SPEC §5a).
`session.started` says it began (its role, model, round, the gap, research or review it worked for); `session.ended`
(or `session.errored`) its cost, turns, tools and time.

`python3 dev/bin/status.py session GAP [ROLE] [N]` prints one from the same file."""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from collections import Counter
from pathlib import Path

import fac

CAP = 20 * 1024 * 1024 - 4096         # bytes of one transcript (the page serves a file up to 20 MB)
HOME = "/home/dev/.claude/projects"   # Claude Code's projects folder in the agent image (its user's home)
SLUG = "-work"                        # Claude Code's folder for a session run in /work
PARENTS = ("gap", "research", "review", "situation")   # the kinds a session is related to (its field of that name)


class Session:
    """One session's names: its item, its transcript (``dest``), Claude Code's folder for it (``raw``)."""

    HOME = HOME

    def __init__(self, cfg: dict, role: str, item: str | None):
        self.role, self.cfg = role, cfg
        self.parent = item or os.environ.get("ERGOSTAT_ITEM") or ""
        name = fac.slug(self.parent.split("/", 1)[-1], 64) or "session"
        d = fac.run_dir(cfg, "sessions")
        self.n = 1
        while True:                                            # the next free number, taken by creating its file
            self.dest = d / f"{name}-{role}-{self.n}.jsonl"
            try:
                os.close(os.open(self.dest, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644))
                break
            except FileExistsError:
                self.n += 1
        self.stem = self.dest.stem
        self.id = f"session/{self.stem}"
        self.sid = str(uuid.uuid4())
        self.raw = fac.path(cfg, "live") / "sessions" / f"{self.stem}-claude-{self.sid[:8]}"   # (never under run/)
        (self.raw / SLUG).mkdir(parents=True, exist_ok=True)
        self.copy = Copy(self.raw / SLUG / f"{self.sid}.jsonl", self.dest)
        self.began = time.time()

    def started(self, model: str) -> None:
        kind = self.parent.split("/", 1)[0]
        fac.say("session.started", self.id, role=self.role, model=model, round=self.n, worked_for=self.parent,
                transcript="file:" + fac.rel(self.dest), session_id=self.sid, started=self.began,
                **({kind: self.parent} if kind in PARENTS and "/" in self.parent else {}))

    def ended(self, out: dict | None, error: str | None = None) -> dict:
        """``session.ended`` (or ``session.errored``) with what it cost and did; the record said."""
        self.copy.step()
        rec = {"cost": None if not out or out.get("total_cost_usd") is None else round(float(out["total_cost_usd"]), 4),
               "turns": int((out or {}).get("num_turns") or self.copy.turns), "tools_used": dict(self.copy.tools),
               "seconds": round(time.time() - self.began), "lines": self.copy.lines,
               "truncated": self.copy.cut, "subtype": (out or {}).get("subtype"),
               **({"resources": out["resources"]} if (out or {}).get("resources") else {})}   # (its container's CPU, memory)
        bad = error or not out or out.get("is_error")
        if bad:
            rec["error"] = scrub(error or str((out or {}).get("result") or "no result"), self.copy.tok)[-600:]
        fac.say("session.errored" if bad else "session.ended", self.id, **rec)
        return rec


class Copy:
    """Claude Code's file, copied as it grows: whole lines only, the token scrubbed, at most ``cap`` bytes."""

    def __init__(self, src: Path, dest: Path, cap: int = CAP):
        self.src, self.dest, self.cap = src, dest, cap
        self.offset = self.size = self.lines = self.turns = 0
        self.tok, self.cut, self.tools = "", False, Counter()

    def step(self) -> int:
        """The new complete lines copied; how many."""
        try:
            with open(self.src, "rb") as fh:
                fh.seek(self.offset)
                chunk = fh.read()
        except FileNotFoundError:
            return 0
        end = chunk.rfind(b"\n")
        if end < 0:
            return 0
        self.offset += end + 1
        n = 0
        with open(self.dest, "ab") as out:
            for raw in chunk[:end].split(b"\n"):
                text = scrub(raw.decode(errors="replace"), self.tok).strip()
                if not text:
                    continue
                self._count(text)
                data = (text + "\n").encode()
                if self.cut:
                    continue
                if self.size + len(data) > self.cap:
                    self.cut = True
                    data = (json.dumps({"type": "system", "subtype": "truncated",
                                        "note": f"the transcript passed {self.cap} bytes: the rest was not kept"}) + "\n").encode()
                assert not self.tok or self.tok.encode() not in data, "the session token in a transcript"
                out.write(data)
                self.size += len(data)
                self.lines += 1
                n += 1
        return n

    def _count(self, text: str) -> None:
        try:
            line = json.loads(text)
        except ValueError:
            return
        msg = line.get("message") if isinstance(line, dict) else None
        if not isinstance(msg, dict) or line.get("type") != "assistant" or not isinstance(msg.get("content"), list):
            return
        self.turns += 1
        self.tools.update(b.get("name") or "?" for b in msg["content"] if isinstance(b, dict) and b.get("type") == "tool_use")

    def follow(self, every: float = 2.0):
        """A thread copying every ``every`` seconds until the returned stop is called (which copies the last)."""
        done = threading.Event()

        def loop():
            while not done.wait(every):
                self.step()
        t = threading.Thread(target=loop, daemon=True)
        t.start()

        def stop():
            done.set()
            t.join(30)
            self.step()
        return stop


def scrub(text: str, tok: str) -> str:
    return text.replace(tok, "[token]") if tok else text


def standin(s: Session, brief: str, out: dict) -> None:
    """The stand-in's session file, as Claude Code writes one: the brief, its answer, one tool call."""
    def line(kind, content, uid, parent):
        return {"type": kind, "uuid": uid, "parentUuid": parent, "sessionId": s.sid, "cwd": "/work",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "message": {"role": kind, "content": content}}
    rows = [line("user", brief, "u1", None),
            line("assistant", [{"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": "/work/README.md"}}],
                 "a1", "u1"),
            line("user", [{"type": "tool_result", "tool_use_id": "t1", "content": "the stand-in read it"}], "r1", "a1"),
            line("assistant", [{"type": "text", "text": str(out.get("result", ""))}], "a2", "r1")]
    with open(s.copy.src, "a") as fh:
        fh.writelines(json.dumps(r) + "\n" for r in rows)


# ---- the terminal view (status.py session)

ROLE = re.compile(r"^(?P<name>.+)-(?P<role>[a-z_]+)-(?P<n>\d+)\.jsonl$")


def find(cfg: dict, item: str, role: str | None = None, n: int | None = None) -> list[Path]:
    """The transcripts of an item (``gap/NAME`` or ``NAME``), oldest first; of one role, or one session."""
    name = fac.slug(item.split("/", 1)[-1], 64)
    got = []
    for p in fac.run_dir(cfg, "sessions").glob(f"{name}-*.jsonl"):
        m = ROLE.match(p.name)
        if m and m["name"] == name and (role is None or m["role"] == role) and (n is None or int(m["n"]) == n):
            got.append(p)
    return sorted(got, key=lambda p: (p.stat().st_mtime, p.name))


def summary(inp) -> str:
    if not isinstance(inp, dict):
        return str(inp)[:160]
    head = next((inp[k] for k in ("command", "file_path", "pattern", "path", "url", "query", "description") if inp.get(k)),
                None)
    return " ".join(str(head if head is not None else json.dumps(inp, default=str)).split())[:160]


def readable(path: Path, most: int = 600) -> str:
    """A transcript as text: each message, each tool call with its input summarised, each result cut to ``most``."""
    out = [f"== {path.stem} ({fac.rel(path)})"]
    for raw in path.read_text(errors="replace").splitlines():
        try:
            line = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(line, dict):
            continue
        if line.get("type") == "system" and line.get("subtype") == "truncated":
            out.append(f"[cut] {line.get('note')}")
        msg = line.get("message")
        if line.get("type") not in ("user", "assistant") or not isinstance(msg, dict):
            continue
        blocks = msg.get("content")
        blocks = [{"type": "text", "text": blocks}] if isinstance(blocks, str) else blocks or []
        for b in blocks:
            if not isinstance(b, dict):
                continue
            t = b.get("type")
            if t == "text" and line["type"] == "user":
                text = b.get("text") or ""
                out.append(f"[prompt] {text[:most]}" + (f" ... ({len(text)} characters)" if len(text) > most else ""))
            elif t == "text":
                out.append(f"[claude] {b.get('text', '')}")
            elif t == "tool_use":
                out.append(f"  -> {b.get('name')}: {summary(b.get('input'))}")
            elif t == "tool_result":
                c = b.get("content")
                text = "\n".join(x.get("text", "") for x in c if isinstance(x, dict)) if isinstance(c, list) else str(c or "")
                cut = text[:most] + (f" ... ({len(text)} characters)" if len(text) > most else "")
                mark = "  <- failed: " if b.get("is_error") else "  <- "
                out.append(mark + cut.replace("\n", "\n     "))
    return "\n".join(out)
