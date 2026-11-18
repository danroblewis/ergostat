"""Working on items one at a time: a block's program.

    each --kind K --state S --done EVENT [--run CMD] [--max N] [--failed EVENT] [--tries N] [--stuck EVENT]
         [--flow flow.x] [--timeout 5m]

The items of kind K in state S, the longest waiting first, at most N a run (or the amount the block was commanded,
when that is less): for each, the command is run in the project's folder with the item on standard input (``{id,
kind, state, fields}``) and in ``$ITEM_ID``, ``$ITEM_KIND``, ``$ITEM_STATE`` and ``$ITEM_FIELDS`` (JSON). The last
JSON object it prints is folded into the item, and the item moves on (``K.<done>``). A command that fails says so
on the item (``K.<failed>``, with ``error``, ``attempts`` and ``tries-<state>``: 1, summed by its kind's fold); after
``--tries`` failures in one state the item is set aside (``K.<stuck>``, with ``stuck_at``). With no command, the
stand-in: it does nothing outside, and says so. What it moved is the count of items moved on, along ``--flow``.

*Timer-driven, for now:* the block runs on its goal's clock and takes the items in turn; one run works on them
one after another, and nothing leases an item to it. Item-driven dispatch, with leases, belongs to the engine."""

from __future__ import annotations

import argparse
import json
import os
import subprocess

from .common import block_input, items, note, project, say


def run_one(cmd: str, it, timeout: float) -> tuple[bool, dict, str]:
    payload = {"id": it.id, "kind": it.kind, "state": it.state, "fields": it.fields}
    env = {**os.environ, "ITEM_ID": it.id, "ITEM_KIND": it.kind or "", "ITEM_STATE": it.state or "",
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


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="each")
    ap.add_argument("--kind", required=True)
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
        field = f"tries-{it.state}"                          # (a fold: sum in its kind, so tries add up per step)
        tries = int(it.fields.get(field) or 0) + 1
        say({"event": f"{a.kind}.{a.failed}", "item": it.id, "data": {"error": why, "attempts": 1, field: 1}})
        if tries >= a.tries:
            say({"event": f"{a.kind}.{a.stuck}", "item": it.id, "data": {"stuck_after": tries, "stuck_at": it.state}})
    say({"out": a.flow, "moved": moved} if a.flow else {"moved": moved})
    if not todo:
        note(f"no {a.kind} in {', '.join(a.state)}")
    return 0
