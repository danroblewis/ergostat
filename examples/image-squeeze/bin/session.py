"""A Claude Code session, as an item ergostat shows (Items: session/developer-1a2b3c4d), from the
moment it starts: open while it runs, then done or failed, with its cost, turns and time, what it
said, and its transcript, kept as run/sessions/<item>.jsonl and copied there as it grows, so the
page can show the conversation while it happens.

    session.py run ROLE MODEL     the whole session: the prompt (stdin) to `claude -p`, which runs with
                                  a session id chosen here (so its transcript is known from the start)"""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def ergostat() -> list[str]:
    cmd = os.environ.get("ERGOSTAT_CMD")
    return shlex.split(cmd) if cmd else ["ergostat", "-C", str(ROOT)]


def add(type: str, item: str, data: dict, by: str) -> None:
    subprocess.run([*ergostat(), "event", "--add", type, "--item", item, "--data", json.dumps(data), "--as", by],
                   capture_output=True, text=True)


ALLOWED = ["Bash(bin/py:*)", "Bash(python3:*)", "Bash(git:*)", "Bash(ls:*)", "Bash(cat:*)", "Read", "Edit", "Write", "Glob", "Grep"]


def transcript_of(sid: str) -> Path:
    """Where Claude Code writes the transcript of a session run in this folder."""
    return Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9-]", "-", os.path.realpath(os.getcwd())) / f"{sid}.jsonl"


def run(role: str, model: str) -> int:
    sid = str(uuid.uuid4())
    item = start(role, model, sid)
    keep = ROOT / "run" / "sessions" / f"{item.split('/')[1]}.jsonl"
    keep.parent.mkdir(parents=True, exist_ok=True)
    src = transcript_of(sid)
    proc = subprocess.Popen(["claude", "-p", "--model", model, "--session-id", sid, "--output-format", "json",
                             "--permission-mode", "acceptEdits", "--allowedTools", *ALLOWED],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    proc.stdin.write(sys.stdin.read())
    proc.stdin.close()
    out = []
    import threading
    reader = threading.Thread(target=lambda: out.append(proc.stdout.read()), daemon=True)
    reader.start()
    while proc.poll() is None:                               # the transcript, copied as it grows
        if src.exists():
            shutil.copyfile(src, keep)
        time.sleep(2)
    reader.join(10)
    if src.exists():
        shutil.copyfile(src, keep)
    return finish(item, out[0] if out else "")


def start(role: str, model: str, sid: str = "") -> str:
    try:
        out = subprocess.run([*ergostat(), "item", "--kind", "session", "--state", "open", "-n", "100", "--json"],
                             capture_output=True, text=True).stdout
        left = [i["id"] for i in json.loads(out)["items"] if i["fields"].get("role") == role]
    except (ValueError, KeyError):
        left = []
    for item in left:                                        # one block never runs twice at once: these are dead
        add("session.lost", item, {"why": "it never finished: killed (a timeout?) or crashed"}, role)
    run = (os.environ.get("ERGOSTAT_RUN") or f"{time.time_ns():x}")[:8]
    item = f"session/{role}-{run}"
    add("session.started", item, {"role": role, "model": model, "started": time.time(), "session_id": sid,
                                  "transcript": f"file:run/sessions/{item.split('/')[1]}.jsonl"}, role)
    return item


def finish(item: str, raw: str) -> int:
    role = item.split("/")[1].rsplit("-", 1)[0]
    try:
        d = json.loads(raw)
    except ValueError:
        print(json.dumps({"event": "session.failed", "item": item, "data": {"said": raw[-1500:], "error": True}}))
        print(raw)
        return 1
    rec = {"cost_usd": round(d.get("total_cost_usd") or 0, 4), "turns": d.get("num_turns"),
           "seconds": round((d.get("duration_ms") or 0) / 1000, 1), "error": bool(d.get("is_error")),
           "said": (d.get("result") or "")[-1500:]}
    (ROOT / "run").mkdir(exist_ok=True)
    with open(ROOT / "run" / "costs.jsonl", "a") as f:
        f.write(json.dumps({"at": time.time(), "role": role, "item": item, **rec}) + "\n")
    print(json.dumps({"event": "session.failed" if rec["error"] else "session.ran", "item": item, "data": rec}))
    print(d.get("result") or "")
    return 1 if rec["error"] else 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[2], sys.argv[3]))
