"""A Claude Code session as a block's run (SPEC §12h): ``ergostat session ROLE --model M`` (or ``$ERGOSTAT_CMD
session ...`` from a block's ``run:``), the prompt on standard input. It starts ``claude -p`` with a session id chosen
here, records the session as an item (``session/ROLE-RUN``: ``session.started``, caused by the run, with its id, its
model and its transcript, copied as it grows so the page shows the conversation while it happens), and gives it the
owner's messages while it works:

- **live** (the default): the session runs with ``--input-format stream-json``, its standard input kept open. A
  message routed to this run, its session, its block or an item it works on is written into it as a user message;
  Claude Code takes it at its next step (after the tool call it is in), within the same turn. ``delivered``, how
  ``live``.
- **resume** (``--no-live``, or after a live session's last turn): a message that arrives while the session cannot
  take one is ``queued``, and after the turn ergostat resumes the session, ``claude -p --resume ID``, the message as
  its input: the session's next turn. ``delivered``, how ``resume``; its reply is the message's answer.

It prints what the block's run reports: ``session.ran`` (or ``.failed``) about the session item, with its cost, turns
and time, then the JSON lines of every turn's result (claims marked with the session and its model). ``$ERGOSTAT_CLAUDE``
names the program to run in place of ``claude`` (``echo``: ergostat's stand-in session, ``session_echo.py``, which
echoes what it receives). Arguments after ``--`` are passed to it (the tools the session may use)."""

from __future__ import annotations

import argparse
import json
import os
import queue
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

GRACE = 3.0          # seconds after a turn's result with nothing more said and no message to give: the session ends
POLL = 1.0           # seconds between looks for messages
FOLLOW_UPS = 5       # the most turns one run resumes for messages after its own


def transcript_of(sid: str, cwd: str | None = None, env: dict | None = None) -> Path:
    """Where Claude Code writes the transcript of a session run in this folder (``$CLAUDE_CONFIG_DIR``, else
    ``~/.claude``)."""
    base = Path((env or os.environ).get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    return base / "projects" / re.sub(r"[^A-Za-z0-9-]", "-", os.path.realpath(cwd or os.getcwd())) / f"{sid}.jsonl"


def claude_command(state_dir: Path | None) -> tuple[list[str], dict]:
    """The program a session runs, and its environment: ``$ERGOSTAT_CLAUDE`` or ``claude``; ``echo`` is ergostat's
    stand-in, which keeps its transcripts in the state directory."""
    raw = os.environ.get("ERGOSTAT_CLAUDE") or "claude"
    env = dict(os.environ)
    if raw == "echo":
        if state_dir is not None:
            env["CLAUDE_CONFIG_DIR"] = str(state_dir / "echo-claude")
        return [sys.executable, "-m", "ergostat.session_echo"], env
    return shlex.split(raw), env


def open_project():
    from . import model as mdl
    from .store import Project
    m = mdl.load(Path.cwd())
    d = os.environ.get("ERGOSTAT_STATE_DIR")
    return Project(m, Path(d) if d else None)


def tagged(said: str, item: str, model: str) -> list[str]:
    """A turn's lines, its claims marked as this session's and this model's (SPEC §12g: trust by model); answers
    marked with the session."""
    out = []
    for line in said.splitlines():
        try:
            obj = json.loads(line) if line.strip().startswith("{") else None
        except ValueError:
            obj = None
        if isinstance(obj, dict) and isinstance(obj.get("claim"), dict):
            obj["claim"] = {**obj["claim"], "session": item, "model": model}
            line = json.dumps(obj)
        elif isinstance(obj, dict) and isinstance(obj.get("answer"), dict):
            obj["answer"] = {**obj["answer"], "session": item}
            line = json.dumps(obj)
        out.append(line)
    return out


class Session:
    def __init__(self, role: str, model: str, live: bool, keep: str | None, prefix: str, extra: list[str]):
        self.p = open_project()
        self.spec = getattr(self.p.model, "spec", None)
        self.role, self.model, self.live, self.extra = role, model, live, extra
        self.run = os.environ.get("ERGOSTAT_RUN") or None
        self.sid = str(uuid.uuid4())
        tag = (self.run or f"{time.time_ns():x}")[:8]
        self.item = f"{prefix}/{role}-{tag}"
        keep_dir = Path(keep) if keep else self.p.dir / "sessions"
        self.keep = keep_dir / f"{self.item.split('/', 1)[1]}.jsonl"
        self.keep.parent.mkdir(parents=True, exist_ok=True)
        self.cmd, self.env = claude_command(self.p.dir)
        self.env["ERGOSTAT_SESSION_ROLE"] = role
        self.env["ERGOSTAT_SESSION"] = self.item
        self.src = transcript_of(self.sid, env=self.env)
        self.given: set[str] = set()              # messages given to it (live or by resume)
        self.queued: set[str] = set()
        self.results: list[dict] = []

    # ---- the record

    def add(self, type: str, data: dict) -> None:
        self.p.events.add(type, item=self.item, source=self.role, causedby=self.run, data=data)

    def lost(self) -> None:
        """Sessions of this role that never said how they ended: killed (a timeout?) or crashed."""
        prefix = self.item.rsplit("/", 1)[0] + "/"
        for e in self.p.events.query(n=50, type="session.started", source=self.role):
            if not e["item"].startswith(prefix) or e["item"] == self.item:
                continue
            ends = self.p.events.query(n=1, item=e["item"], type="session.ran,session.failed,session.lost")
            if not ends:
                self.p.events.add("session.lost", item=e["item"], source=self.role, causedby=self.run,
                                  data={"why": "it never finished: killed (a timeout?) or crashed"})

    def pending(self) -> list[dict]:
        if self.spec is None:
            return []
        from .messages import deliver
        try:
            return [m for m in deliver.for_session(self.p, self.spec, self.run, self.item) if m["id"] not in self.given]
        except Exception:                          # the record busy, or broken: the session goes on
            return []

    def copy(self) -> None:
        if self.src.exists():
            try:
                shutil.copyfile(self.src, self.keep)
            except OSError:
                pass

    # ---- running it

    def args(self, resume: bool) -> list[str]:
        base = [*self.cmd, "-p", "--model", self.model]
        base += ["--resume", self.sid] if resume else ["--session-id", self.sid]
        if self.live and not resume:
            base += ["--input-format", "stream-json", "--output-format", "stream-json", "--verbose"]
        else:
            base += ["--output-format", "json"]
        return [*base, *self.extra]

    def start(self, prompt: str) -> int:
        self.lost()
        self.add("session.started", {"role": self.role, "model": self.model, "started": time.time(), "session_id": self.sid,
                                     "transcript": "file:" + display_path(self.keep, self.p), "run": self.run,
                                     "block": os.environ.get("ERGOSTAT_BLOCK"), "live": self.live})
        stop = threading.Event()
        copier = threading.Thread(target=self._copying, args=(stop,), daemon=True)
        copier.start()
        try:
            ok = self._live(prompt) if self.live else self._once(prompt)
            for _ in range(FOLLOW_UPS):                   # what arrived after its turn: resumed with it
                msgs = self.pending()
                if not msgs or not ok:
                    break
                ok = self._resume(msgs)
        finally:
            stop.set()
            copier.join(5)
            self.copy()
        return self.finish()

    def _copying(self, stop: threading.Event) -> None:
        while not stop.wait(2):
            self.copy()

    def _deliver(self, m: dict, how: str) -> None:
        from .messages import deliver
        self.given.add(m["id"])
        deliver.delivered(self.p, m, how, run=self.run, session=self.item, block=os.environ.get("ERGOSTAT_BLOCK"),
                          session_id=self.sid)

    def _live(self, prompt: str) -> bool:
        """One process, its standard input open: the prompt, then each message as it arrives."""
        from .messages import deliver
        proc = subprocess.Popen(self.args(False), stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, env=self.env)
        out: queue.Queue = queue.Queue()

        def read():
            for line in proc.stdout:
                out.put(line)
            out.put(None)
        threading.Thread(target=read, daemon=True).start()

        def say(text: str) -> bool:
            try:
                proc.stdin.write(json.dumps({"type": "user", "message": {"role": "user", "content": text}}) + "\n")
                proc.stdin.flush()
                return True
            except (BrokenPipeError, ValueError, OSError):
                return False
        say(prompt)
        idle_since, last_poll, closed = None, 0.0, False
        while True:
            try:
                line = out.get(timeout=0.25)
            except queue.Empty:
                line = ""
            if line is None:                              # it ended
                break
            if line:
                try:
                    d = json.loads(line)
                except ValueError:
                    d = {}
                if d.get("type") == "result":
                    self.results.append(d)
                    idle_since = time.monotonic()
                elif d:
                    idle_since = None                     # a turn under way (a message it took after its result)
            now = time.monotonic()
            if not closed and now - last_poll >= POLL:
                last_poll = now
                for m in self.pending():
                    if say(deliver.note(m)):
                        self._deliver(m, "live")
                        idle_since = None
            if not closed and idle_since is not None and now - idle_since >= GRACE:
                closed = True                             # nothing more to say to it: it ends
                try:
                    proc.stdin.close()
                except OSError:
                    pass
        proc.wait()
        for r in self.results[:-1]:                       # one process: its last result counts its cost and turns
            r["_cumulative"] = True
        return bool(self.results) and not self.results[-1].get("is_error")

    def _once(self, prompt: str) -> bool:
        """One turn, its input given whole: what arrives meanwhile is queued for after it."""
        from .messages import deliver
        proc = subprocess.Popen(self.args(False), stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, env=self.env)
        got: list[str] = []
        reader = threading.Thread(target=lambda: got.append(proc.communicate(prompt)[0]), daemon=True)
        reader.start()
        while reader.is_alive():
            reader.join(POLL)
            for m in self.pending():
                if m["id"] not in self.queued:
                    self.queued.add(m["id"])
                    deliver.queued(self.p, m, session=self.item, run=self.run,
                                   why="it runs with its input given whole (not live): it takes the message after its turn")
        return self._result(got[0] if got else "")

    def _resume(self, msgs: list[dict]) -> bool:
        """The session's next turn: resumed, the messages its input."""
        from .messages import deliver
        text = "\n\n---\n\n".join(deliver.note(m) for m in msgs)
        for m in msgs:
            self._deliver(m, "resume")
        proc = subprocess.run(self.args(True), input=text, capture_output=True, text=True, env=self.env)
        ok = self._result(proc.stdout)
        self.results[-1]["_resumed"] = True
        reply = (self.results[-1].get("result") or "") if self.results else ""
        if ok and reply.strip():
            plain = "\n".join(x for x in reply.splitlines() if not x.strip().startswith("{")).strip() or reply.strip()
            for m in msgs:
                if not re.search(re.escape(m["id"]) + r".{0,40}says", reply):   # it answered it itself, in a line
                    deliver.answered(self.p, m["id"], plain[:2000], by=self.role, run=self.run, session=self.item)
        return ok

    def _result(self, raw: str) -> bool:
        try:
            d = json.loads(raw)
        except ValueError:
            self.results.append({"is_error": True, "result": raw[-1500:], "unreadable": True})
            return False
        self.results.append(d)
        return not d.get("is_error")

    def finish(self) -> int:
        if not self.results or (len(self.results) == 1 and self.results[0].get("unreadable")):
            said = self.results[0].get("result", "") if self.results else ""
            print(json.dumps({"event": "session.failed", "item": self.item, "data": {"said": said, "error": True}}))
            return 1
        last = self.results[-1]
        counted = [r for r in self.results if not r.get("_cumulative")]
        cost = sum(float(r.get("total_cost_usd") or 0) for r in counted)
        rec = {"cost_usd": round(cost, 4), "turns": sum(int(r.get("num_turns") or 0) for r in counted),
               "seconds": round(sum(float(r.get("duration_ms") or 0) for r in counted) / 1000, 1),
               "error": bool(last.get("is_error")), "said": (last.get("result") or "")[-1500:],
               "messages": sorted(self.given), **({"queued": sorted(self.queued)} if self.queued else {}),
               "resumed": sum(1 for r in self.results[1:] if r.get("_resumed"))}
        print(json.dumps({"event": "session.failed" if rec["error"] else "session.ran", "item": self.item, "data": rec}))
        for r in self.results:
            for line in tagged(r.get("result") or "", self.item, self.model):
                print(line)
        return 1 if rec["error"] else 0


def display_path(path: Path, p) -> str:
    """A transcript's path as an item's field names it: from the project's folder when inside it, else whole."""
    try:
        return str(path.resolve().relative_to(p.repo.resolve()))
    except ValueError:
        return str(path.resolve())


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    extra: list[str] = []
    if "--" in argv:
        i = argv.index("--")
        argv, extra = argv[:i], argv[i + 1:]
    ap = argparse.ArgumentParser(prog="ergostat session", description=__doc__.split("\n\n")[0])
    ap.add_argument("role", help="what the session is (developer, researcher): its item is session/ROLE-RUN")
    ap.add_argument("--model", default=os.environ.get("ERGOSTAT_MODEL") or "sonnet", help="the model (claude --model)")
    ap.add_argument("--no-live", action="store_true", help="give the prompt whole; messages wait for the turn's end, "
                                                           "then resume the session with them")
    ap.add_argument("--keep", help="the folder its transcript is copied into (default: sessions/ in the state directory)")
    ap.add_argument("--prefix", default="session", help="its item's id before the / (default: session)")
    a = ap.parse_args(argv)
    s = Session(a.role, a.model, not a.no_live, a.keep, a.prefix, extra)
    return s.start(sys.stdin.read())


if __name__ == "__main__":
    sys.exit(main())
