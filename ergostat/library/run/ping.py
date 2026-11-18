"""Asking again until answered: a block's program.

    ping --kind K --state S [--state S2] --every 1d --limit 3 [--run CMD] [--pinged-flow flow.x]
         [--gave-up-flow flow.y] [--max N]

Each unanswered item (kind K, in one of the states) whose last ping is older than ``--every`` (or that was never
pinged) is pinged: the command is run with the item on standard input and in ``$ITEM_ID``, ``$ITEM_FIELDS`` and
``$PING_N`` (this ping's number), and ``K.pinged`` is recorded (``pings: 1``, summed, and ``last_ping``). An item
pinged ``--limit`` times and still unanswered a period after its last is given up on (``K.gave-up``), for a person
to take over. With no command, the stand-in: nothing is sent, and the ping says so. It moves two flows: the pings
sent, and the items given up on."""

from __future__ import annotations

import argparse

from .common import items, now, project, say
from .each import run_one


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="ping")
    ap.add_argument("--kind", required=True)
    ap.add_argument("--state", required=True, action="append")
    ap.add_argument("--every", type=float, required=True, help="seconds between pings")
    ap.add_argument("--limit", type=int, default=3)
    ap.add_argument("--run", default="")
    ap.add_argument("--pinged-flow")
    ap.add_argument("--gave-up-flow")
    ap.add_argument("--max", type=int, default=20)
    ap.add_argument("--timeout", type=float, default=120.0)
    a = ap.parse_args(argv)
    p = project()
    t = now()
    pinged = gave_up = 0
    for it in items(p, a.kind, a.state):
        if pinged >= a.max:
            break
        n = int(it.fields.get("pings") or 0)
        last = float(it.fields.get("last_ping") or it.entered or it.first)
        if n and t - last < a.every:
            continue
        if not n and t - (it.entered or it.first) < a.every:
            continue
        if n >= a.limit:
            say({"event": f"{a.kind}.gave-up", "item": it.id, "data": {"gave_up_after": n}})
            gave_up += 1
            continue
        if a.run.strip():
            import os
            os.environ["PING_N"] = str(n + 1)
            ok, data, why = run_one(a.run, it, a.timeout)
        else:
            ok, data, why = True, {"sent_by": "stand-in"}, ""
        if not ok:
            say({"event": f"{a.kind}.ping-failed", "item": it.id, "data": {"error": why}})
            continue
        say({"event": f"{a.kind}.pinged", "item": it.id, "data": {**data, "pings": 1, "last_ping": round(t, 3)}})
        pinged += 1
    if a.pinged_flow:
        say({"out": a.pinged_flow, "moved": pinged})
    if a.gave_up_flow:
        say({"out": a.gave_up_flow, "moved": gave_up})
    return 0
