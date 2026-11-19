"""The steps' stand-ins: what an AI agent or a program would do at each step, made up in a second or two, and the
event lines that say what happened. Each run holds a lease on one item (ERGOSTAT_ITEM) and prints its events as it
goes; ergostat records each as caused by this run (``causedby``), and the run as caused by the lease on its item, so
an event this run prints about another item (a facet it opens, the alert a facet finishes) is drawn in the Process
view as a line from this item's kind to that one's.

    step.py triage | fan-out | investigate | summarise
"""

from __future__ import annotations

import fcntl
import json
import os
import random
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

FACETS = ["logs", "deploys", "metrics"]
RUN = Path(__file__).resolve().parent.parent / "run"


def say(event: str, item: str, data: dict | None = None) -> None:
    print(json.dumps({"event": event, "item": item, "data": data or {}}), flush=True)


def record(event: str, item: str, data: dict) -> None:
    """Record an event now, through ergostat's command line: written before this returns, so the next run to read
    the items sees it (a printed line is recorded by the running ergostat, and another process may read the record
    a moment later). Caused by this run all the same: the command reads ERGOSTAT_RUN."""
    subprocess.run([*ergostat(), "event", "--add", event, "--item", item, "--data", json.dumps(data), "--as",
                    os.environ.get("ERGOSTAT_BLOCK") or os.environ.get("ERGOSTAT_AGENT") or "investigate"], check=True, capture_output=True)


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


def items(kind: str) -> list[dict]:
    got = subprocess.run([*ergostat(), "item", "--kind", kind, "-n", "10000", "--json"], capture_output=True, text=True)
    try:
        return json.loads(got.stdout or "{}").get("items") or []
    except ValueError:
        return []


def read_input(raw: str) -> dict:
    """The run's input: the item it holds (``item``: its id, state and fields), its lease, the goals. A program block
    is given the JSON alone; an ``ai`` block's ``run:`` wrapper is given its prompt first, the JSON last."""
    for text in (raw, *reversed(raw.strip().splitlines())):
        try:
            got = json.loads(text)
        except ValueError:
            continue
        if isinstance(got, dict):
            return got
    return {}


def fields(it: dict) -> dict:
    return it.get("fields") or {}


def main() -> int:
    step = sys.argv[1]
    item = os.environ["ERGOSTAT_ITEM"]
    given = read_input(sys.stdin.read())
    time.sleep(random.uniform(0.5, 2.0))                    # the work itself
    if step == "triage":                                    # an AI agent's judgement: noise, or worth a look
        if random.random() < 0.2:
            say("alert.dismissed", item, {"why": "a known flapping check"})
        else:
            say("alert.triaged", item, {"via": "triage", "severity": random.choice(["low", "high"])})
    elif step == "fan-out":                                 # one facet item per line of inquiry: the fan-out
        n = int(fields(given.get("item") or {}).get("rounds") or 0) + 1   # this alert's rounds so far
        for f in FACETS:
            say("facet.opened", f"facet/{item.split('/', 1)[1]}-{n}-{f}", {"alert": item, "facet": f, "round": n})
        say("alert.facets-opened", item, {"rounds": 1, "facets": len(FACETS)})
    elif step == "investigate":                             # one facet looked into; the last one done joins
        alert, rnd = fields(given.get("item") or {}).get("alert"), fields(given.get("item") or {}).get("round")
        RUN.mkdir(exist_ok=True)
        with open(RUN / "join.lock", "w") as lock:          # one run at a time decides the join: the last to finish moves the alert
            fcntl.flock(lock, fcntl.LOCK_EX)
            record("facet.done", item, {"finding": random.choice(["nothing unusual", "a deploy 4 minutes before",
                                                                  "a spike in 5xx from one pod"])})
            mine = [i for i in items("facet") if fields(i).get("alert") == alert and fields(i).get("round") == rnd]
            if mine and all("finding" in fields(i) for i in mine):   # every facet of this round has its finding
                say("alert.investigated", alert, {"facets_done": len(mine)})
    elif step == "summarise":                               # an AI agent's summary: closed, or the on-call's call
        if random.random() < 0.4:
            say("alert.escalated", item, {"summary": "a deploy coincides with the errors: needs the on-call"})
        else:
            say("alert.summarised", item, {"via": "summary", "summary": "transient; recovered on its own"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
