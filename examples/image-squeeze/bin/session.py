"""A Claude Code session, as an item ergostat shows (Items: session/developer-1a2b3c4d), from the
moment it starts: open while it runs, then done or failed, with its cost, turns, time, what it said,
and the path of its full transcript. bin/ai.sh calls it on both sides of `claude -p`.

    session.py start ROLE MODEL              record it open (and any of ROLE's left open, by a session
                                             that was killed, as lost); prints its item id
    claude ... | session.py finish ITEM      read claude's JSON: its cost to run/costs.jsonl, the item
                                             closed (as the block's output), its answer passed on"""

import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def ergostat() -> list[str]:
    cmd = os.environ.get("ERGOSTAT_CMD")
    return shlex.split(cmd) if cmd else ["ergostat", "-C", str(ROOT)]


def add(type: str, item: str, data: dict, by: str) -> None:
    subprocess.run([*ergostat(), "event", "--add", type, "--item", item, "--data", json.dumps(data), "--as", by],
                   capture_output=True, text=True)


def start(role: str, model: str) -> str:
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
    add("session.started", item, {"role": role, "model": model, "started": time.time()}, role)
    return item


def finish(item: str) -> int:
    raw = sys.stdin.read()
    role, model = item.split("/")[1].rsplit("-", 1)[0], ""
    try:
        d = json.loads(raw)
    except ValueError:
        print(json.dumps({"event": "session.failed", "item": item, "data": {"said": raw[-1500:], "error": True}}))
        print(raw)
        return 1
    sid = d.get("session_id") or ""
    transcript = Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9-]", "-", os.path.realpath(os.getcwd())) / f"{sid}.jsonl"
    rec = {"cost_usd": round(d.get("total_cost_usd") or 0, 4), "turns": d.get("num_turns"),
           "seconds": round((d.get("duration_ms") or 0) / 1000, 1), "error": bool(d.get("is_error")), "session_id": sid,
           "transcript": str(transcript) if transcript.exists() else None, "said": (d.get("result") or "")[-1500:]}
    (ROOT / "run").mkdir(exist_ok=True)
    with open(ROOT / "run" / "costs.jsonl", "a") as f:
        f.write(json.dumps({"at": time.time(), "role": role, "item": item, **rec}) + "\n")
    print(json.dumps({"event": "session.failed" if rec["error"] else "session.ran", "item": item, "data": rec}))
    print(d.get("result") or "")
    return 1 if rec["error"] else 0


if __name__ == "__main__":
    if sys.argv[1] == "start":
        print(start(sys.argv[2], sys.argv[3]))
    else:
        sys.exit(finish(sys.argv[2]))
