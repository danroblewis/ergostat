"""ergostat's stand-in for a Claude Code session (``ERGOSTAT_CLAUDE=echo``, SPEC §12h): free, quick, and it echoes
what it receives, so the delivery of the owner's messages can be seen and tested without a model.

It takes the ``claude -p`` flags ``ergostat session`` gives (``--session-id`` or ``--resume``, ``--input-format
stream-json``, ``--output-format json|stream-json``) and keeps a transcript where Claude Code would
(``$CLAUDE_CONFIG_DIR/projects/<folder>/<id>.jsonl``), in its format. A turn "works" for ``$ERGOSTAT_ECHO_WORK``
seconds (default 1), after running ``$ERGOSTAT_ECHO_RUN`` (``{role}`` in it: the session's role) with the prompt's JSON
input, when it is set: a stand-in program that does the block's work, its lines the turn's result. Messages that
arrive while a turn works are folded into it, as Claude Code does ("The user sent a new message while you were
working"); each is echoed in the result, and a message that names an ergostat message id is answered with an
``answer`` line."""

from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import uuid
from datetime import UTC, datetime

from .session import transcript_of

MID = re.compile(r"\((?P<short>[0-9a-f]{6,12})\)|(?P<full>ergostat\.message/[0-9a-f]{6,12})")


def flag(args: list[str], name: str) -> str | None:
    return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else None


class Echo:
    def __init__(self, args: list[str]):
        self.sid = flag(args, "--resume") or flag(args, "--session-id") or str(uuid.uuid4())
        self.resumed = "--resume" in args
        self.stream_in = flag(args, "--input-format") == "stream-json"
        self.out_format = flag(args, "--output-format") or "text"
        self.model = flag(args, "--model") or "echo"
        self.path = transcript_of(self.sid)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.parent = None
        self.turns = 0
        self.before = 0
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if d.get("type") == "user":
                    self.before += 1
                self.parent = d.get("uuid") or self.parent

    def line(self, kind: str, content) -> None:
        u = str(uuid.uuid4())
        rec = {"type": kind, "uuid": u, "parentUuid": self.parent, "sessionId": self.sid,
               "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
               "message": {"role": kind, "content": content, **({"model": self.model} if kind == "assistant" else {})}}
        with open(self.path, "a") as f:
            f.write(json.dumps(rec) + "\n")
        self.parent = u

    def emit(self, obj: dict) -> None:
        if self.out_format == "stream-json":
            print(json.dumps(obj), flush=True)

    def work(self, prompt: str, more: queue.Queue | None) -> tuple[str, list[str]]:
        """One turn on the prompt; the messages that came while it worked, folded in."""
        took: list[str] = []
        out = ""
        run = (os.environ.get("ERGOSTAT_ECHO_RUN") or "").replace("{role}", os.environ.get("ERGOSTAT_SESSION_ROLE", ""))
        if run and self.turns == 0 and not self.resumed:
            start = prompt.rfind("\n{")                       # the block's JSON input, after its prompt
            given = prompt[start + 1:] if start >= 0 else prompt
            out = subprocess.run(run, shell=True, input=given, capture_output=True, text=True).stdout
        deadline = time.monotonic() + float(os.environ.get("ERGOSTAT_ECHO_WORK", "1"))
        while more is not None and time.monotonic() < deadline:
            try:
                took.append(more.get(timeout=max(0.01, deadline - time.monotonic())))
            except queue.Empty:
                break
        if more is None:
            time.sleep(max(0.0, deadline - time.monotonic()))
        return out, took

    def reply(self, prompt: str, out: str, took: list[str]) -> str:
        first = prompt.strip().splitlines()[0][:200] if prompt.strip() else ""
        lines = [out.rstrip()] if out.strip() else []
        lines.append(f"echo: received {first!r}" + (f" (resumed: {self.before} messages before)" if self.resumed else ""))
        for t in ([prompt] if self.turns or self.resumed else []) + took:
            body = t.strip().split("\n\n")
            said = body[1] if len(body) > 1 else body[0]
            lines.append(f"echo: the owner said {said.strip()[:300]!r}")
            m = MID.search(t)
            if m:
                mid = m.group("full") or f"ergostat.message/{m.group('short')}"
                lines.append(json.dumps({"answer": {"message": mid, "says": f"echo: received {said.strip()[:200]!r}"}}))
        return "\n".join(lines)

    def turn(self, prompt: str, more: queue.Queue | None) -> dict:
        t0 = time.monotonic()
        self.line("user", prompt)
        out, took = self.work(prompt, more)
        for t in took:                                        # as Claude Code records a message it took mid-turn
            self.line("user", f"The user sent a new message while you were working:\n{t}")
        text = self.reply(prompt, out, took)
        self.line("assistant", [{"type": "text", "text": text}])
        self.emit({"type": "assistant", "session_id": self.sid, "message": {"content": [{"type": "text", "text": text}]}})
        self.turns += 1
        return {"type": "result", "subtype": "success", "is_error": False, "result": text, "session_id": self.sid,
                "num_turns": self.turns, "duration_ms": int((time.monotonic() - t0) * 1000), "total_cost_usd": 0.0}

    def stream(self) -> int:
        inbox: queue.Queue = queue.Queue()

        def read():
            for raw in sys.stdin:
                try:
                    d = json.loads(raw)
                except ValueError:
                    continue
                c = (d.get("message") or {}).get("content")
                inbox.put(c if isinstance(c, str) else json.dumps(c))
            inbox.put(None)
        threading.Thread(target=read, daemon=True).start()
        self.emit({"type": "system", "subtype": "init", "session_id": self.sid, "model": self.model})
        while True:
            prompt = inbox.get()
            if prompt is None:
                return 0
            res = self.turn(prompt, _Until(inbox))
            self.emit(res)

    def once(self) -> int:
        res = self.turn(sys.stdin.read(), None)
        if self.out_format == "json":
            print(json.dumps(res))
        elif self.out_format == "stream-json":
            self.emit(res)
        else:
            print(res["result"])
        return 0


class _Until(queue.Queue):
    """The session's inbox, read while a turn works; the end of input is put back for the loop to see."""

    def __init__(self, q: queue.Queue):
        super().__init__()
        self.q = q

    def get(self, block=True, timeout=None):
        x = self.q.get(block, timeout)
        if x is None:
            self.q.put(None)
            raise queue.Empty
        return x


def main() -> int:
    e = Echo(sys.argv[1:])
    return e.stream() if e.stream_in else e.once()


if __name__ == "__main__":
    sys.exit(main())
