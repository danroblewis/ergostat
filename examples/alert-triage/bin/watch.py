"""The collector, a sensor on the arrivals flow: reads the pager for alerts it has not seen and records each as an
alert (alert.fired), then prints the arrivals per hour over the last ten minutes. It reads, and never acts.

Offline (always, in this example) the pager is simulated here: an alert fires every few seconds, and the on-call
engineer's answers to the alerts escalated to them (handled, or sent back for more investigation) are read from
the pager as they are made, after a person's delay. The on-call is a person outside ergostat; this script only
reports what the pager says they did."""

from __future__ import annotations

import json
import os
import random
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

RUN = Path(__file__).resolve().parent.parent / "run"
WINDOW = 600.0
SERVICES = ["checkout", "search", "payments", "login", "images"]


def say(event: str, item: str, data: dict | None = None) -> None:
    print(json.dumps({"event": event, "item": item, "data": data or {}}), flush=True)


def ergostat() -> list[str]:
    """The command that runs ergostat on this project: what ergostat gives a block's run (ERGOSTAT_CMD), else
    `ergostat` on the PATH (a sensor's command is not given ERGOSTAT_CMD; under `uv run`, the PATH has it), else the
    checkout this example sits in."""
    root = Path(__file__).resolve().parent.parent
    if os.environ.get("ERGOSTAT_CMD"):
        return shlex.split(os.environ["ERGOSTAT_CMD"])
    if shutil.which("ergostat"):
        return ["ergostat", "-C", str(Path.cwd())]
    for up in root.parents:
        if (up / "ergostat" / "__init__.py").exists():
            return ["uv", "run", "-q", "--project", str(up), "python", "-m", "ergostat", "-C", str(Path.cwd())]
    sys.exit("ergostat is not installed (uv tool install ergostat, or run from its checkout)")


def alerts(state: str) -> list[dict]:
    got = subprocess.run([*ergostat(), "item", "--kind", "alert", "--state", state, "-n", "1000", "--json"],
                         capture_output=True, text=True)
    try:
        return json.loads(got.stdout or "{}").get("items") or []
    except ValueError:
        return []


def main() -> int:
    RUN.mkdir(exist_ok=True)
    mem_path = RUN / "pager.json"
    mem = json.loads(mem_path.read_text()) if mem_path.exists() else {"n": 0, "next": 0, "arrivals": [], "answer": {}}
    now = time.time()
    if now >= mem["next"]:                                  # the pager: a new alert every few seconds
        mem["n"] += 1
        aid = f"alert/{mem['n']}"
        say("alert.fired", aid, {"service": random.choice(SERVICES), "summary": "error rate over 2% for 5 minutes",
                                 "fired_at": now})
        mem["arrivals"].append(now)
        mem["next"] = now + random.expovariate(1 / 6)
    for a in alerts("escalated"):                          # the on-call answers what was escalated to them
        due = mem["answer"].setdefault(a["id"], now + random.uniform(4, 12))
        if now >= due:
            mem["answer"].pop(a["id"])
            if random.random() < 0.3:
                say("alert.reopened", a["id"], {"via": "reopened", "why": "look at the database too"})
            else:
                say("alert.handled", a["id"], {"via": "on-call"})
    mem["arrivals"] = [t for t in mem["arrivals"] if t > now - WINDOW]
    mem_path.write_text(json.dumps(mem))
    print(round(len(mem["arrivals"]) * 3600 / WINDOW, 2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
