"""Working on items: a block's program.

    each --projection K --state S --done EVENT [--run CMD] [--max N] [--failed EVENT] [--tries N] [--stuck EVENT]
         [--flow flow.x] [--timeout 5m]

**Given an item** (a block that takes items, SPEC §9.5: ergostat leased this run one item, in its input), it works
on that one: the command is run in the project's folder with the item on standard input (``{id, projection, state,
fields}``) and in ``$ITEM_ID``, ``$ITEM_PROJECTION``, ``$ITEM_STATE`` and ``$ITEM_FIELDS`` (JSON). The last JSON object it
prints is folded into the item, and the item moves on (``K.<done>``): the lease's ack. A command that fails says so
on the item (``K.<failed>``, with ``error`` and ``failed_at``) and gives it back (``{"nack": why}``): the lease
counts the attempt, and after its attempts the item is a dead letter. Retries, and when to give up, are the lease's.

**Given none** (run by hand, or by a block that does not take items), it works on the items of projection K in state S,
the longest waiting first, at most N a run (or the amount the block was commanded, when that is less), one after
another; it counts the tries itself (``tries-<state>``: 1 each failure, summed by its projection's fold) and after
``--tries`` failures in one state sets the item aside (``K.<stuck>``, with ``stuck_at``).

With no command, the stand-in: it does nothing outside, and says so. What it moved is the count of items moved on,
along ``--flow``."""

from __future__ import annotations

import argparse
import json
import os
import subprocess

from .common import block_input, items, note, project, say


def run_one(cmd: str, it, timeout: float) -> tuple[bool, dict, str]:
    payload = {"id": it.id, "projection": it.kind, "state": it.state, "fields": it.fields}
    env = {**os.environ, "ITEM_ID": it.id, "ITEM_PROJECTION": it.kind or "", "ITEM_STATE": it.state or "",
           "ITEM_FIELDS": json.dumps(it.fields, default=str)}
    try:
        p = subprocess.run(cmd, shell=True, input=json.dumps(payload, default=str), capture_output=True, text=True,
                           timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return False, {}, f"no answer within {timeout:g}s"
    data: dict = {}
    for line in p.stdout.splitlines():
        s = line.strip()
        if s.startswith("{"):
            try:
                obj = json.loads(s)
            except ValueError:
                note(line)
                continue
            if isinstance(obj, dict):
                data = obj
        elif s:
            note(line)
    if p.stderr.strip():
        note(p.stderr.strip()[-2000:])
    if p.returncode != 0:
        return False, data, (p.stderr or p.stdout).strip()[-300:] or f"exited {p.returncode}"
    return True, data, ""


class Leased:
    def __init__(self, d: dict):
        self.id, self.kind, self.state = str(d.get("id")), d.get("projection"), d.get("state")
        self.fields = d.get("fields") if isinstance(d.get("fields"), dict) else {}


def leased(a, item: dict) -> int:
    """The one item this run holds a lease on: done and moved on, or failed and given back."""
    it = Leased(item)
    if not a.run.strip():
        ok, data, why = True, {"done_by": "stand-in"}, ""
    else:
        ok, data, why = run_one(a.run, it, a.timeout)
    if ok:
        say({"event": f"{a.kind}.{a.done}", "item": it.id, "data": data})
    else:
        say({"event": f"{a.kind}.{a.failed}", "item": it.id, "data": {**data, "error": why, "failed_at": it.state}})
        say({"nack": why})
    say({"out": a.flow, "moved": 1 if ok else 0} if a.flow else {"moved": 1 if ok else 0})
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="each")
    ap.add_argument("--projection", dest="kind", required=True)
    ap.add_argument("--state", required=True, action="append")
    ap.add_argument("--done", required=True)
    ap.add_argument("--run", default="")
    ap.add_argument("--max", type=int, default=5)
    ap.add_argument("--failed", default="failed")
    ap.add_argument("--tries", type=int, default=3)
    ap.add_argument("--stuck", default="stuck")
    ap.add_argument("--flow")
    ap.add_argument("--timeout", type=float, default=300.0)
    a = ap.parse_args(argv)
    given = block_input()
    amount = (given.get("command") or {}).get("amount")
    n = a.max if not amount or amount <= 1 else min(a.max, int(amount))
    if isinstance(given.get("item"), dict):                    # leased to this run: that one item (SPEC §9.5)
        return leased(a, given["item"])
    p = project()
    todo = items(p, a.kind, a.state)[:n]
    moved = 0
    for it in todo:
        if not a.run.strip():
            ok, data, why = True, {"done_by": "stand-in"}, ""
        else:
            ok, data, why = run_one(a.run, it, a.timeout)
        if ok:
            say({"event": f"{a.kind}.{a.done}", "item": it.id, "data": data})
            moved += 1
            continue
        field = f"tries-{it.state}"                          # (a fold: sum in its projection, so tries add up per step)
        tries = int(it.fields.get(field) or 0) + 1
        say({"event": f"{a.kind}.{a.failed}", "item": it.id, "data": {"error": why, "attempts": 1, field: 1}})
        if tries >= a.tries:
            say({"event": f"{a.kind}.{a.stuck}", "item": it.id, "data": {"stuck_after": tries, "stuck_at": it.state}})
    say({"out": a.flow, "moved": moved} if a.flow else {"moved": moved})
    if not todo:
        note(f"no {a.kind} in {', '.join(a.state)}")
    return 0
