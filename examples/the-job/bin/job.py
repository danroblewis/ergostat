"""What the watchers and preparers share: ergostat's record of the items, the outbox, the lines they print.

Nothing here writes anywhere but ergostat's record (through the lines a block or sensor prints) and
the local outbox/ folder. No work system is ever written to."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))                    # the simulated world (world/), a folder of this example
from world.world import DAY, GH  # noqa: E402  (after the line above)

OUTBOX = ROOT / "outbox"
STATE = ROOT / "run" / "world" / "state.json"


def ergostat() -> list[str]:
    cmd = os.environ.get("ERGOSTAT_CMD")
    return shlex.split(cmd) if cmd else ["ergostat", "-C", str(ROOT)]


def items(kind: str, state: str | None = None) -> list[dict]:
    """The items of a kind (in a state), oldest first, as ergostat has folded them from the record."""
    args = [*ergostat(), "item", "--projection", kind, "-n", "2000", "--json"] + (["--state", state] if state else [])
    got = json.loads(subprocess.run(args, check=True, capture_output=True, text=True).stdout)["items"]
    return sorted(got, key=lambda i: i["first"])


def every_item() -> list[dict]:
    """Every item of every kind, oldest first."""
    got = json.loads(subprocess.run([*ergostat(), "item", "-n", "100000", "--json"], check=True, capture_output=True,
                                    text=True).stdout)["items"]
    return sorted(got, key=lambda i: i["first"])


def loops() -> dict:
    """Each goal: holding or off, its value and setpoint."""
    return json.loads(subprocess.run([*ergostat(), "loop", "--json"], check=True, capture_output=True, text=True).stdout)


def status() -> dict:
    return json.loads(subprocess.run([*ergostat(), "--json"], check=True, capture_output=True, text=True).stdout)


def world() -> dict:
    """The world as the work systems' read APIs would show it (read only: the preparers' research)."""
    return json.loads(STATE.read_text()) if STATE.exists() else {"things": {}, "log": []}


def draft_path(item: str) -> Path:
    return OUTBOX / (item.replace("/", "-") + ".md")


def write_draft(item: str, text: str, path: Path | None = None) -> str:
    """Leave a draft in the outbox; the item's field names it (file:outbox/review-2041.md)."""
    path = path or draft_path(item)
    OUTBOX.mkdir(exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text.rstrip() + "\n")
    tmp.replace(path)
    return "file:" + str(path.relative_to(ROOT))


def event(type: str, item: str, **data) -> None:
    print(json.dumps({"event": type, "item": item, "data": data}), flush=True)


def moved(n: float, flow: str | None = None) -> None:
    print(json.dumps({"moved": n} if flow is None else {"out": f"flow.{flow}", "moved": n}), flush=True)


def clock_of(w: dict, t: float) -> str:
    from world.world import World
    return World({**w, "now": t}).clock(t)
