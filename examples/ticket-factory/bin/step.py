"""One step of the ticket workflow, run by its block: take a ticket waiting in the step's state, do the step's
script (steps/<name>.py) for it, and move it on.

    step.py NAME --from STATE

The tickets in STATE are tried oldest first. The script's run(ticket) returns:

    Move(fields)     done: the event ticket.<NAME> is recorded with these fields, and the kind's `on:` moves
                     the ticket to the step's next state (ticket.yaml); the block reports it moved along
                     flow.<NAME>. Move(fields, event="ticket.x", out="flow.y") for another way out (a review
                     that asks for changes, a CI run that failed)
    Wait(why)        not yet (an approval, a reviewer, CI): the next ticket is tried, and this one next run
    Stop(why)        it cannot go on: the ticket moves to `stopped`, for the owner

A step with no script moves every ticket on at once (Move()): a step that is only a state, for a person or a
program outside to act on. At most one ticket moves per run (the block's max: 1); the block reports it as
the amount moved along its flow. A gated action that waits (act.Pending) is a Wait; one denied (act.Denied)
or failed (act.Failed) is a Stop unless the script catches it.

PLUG POINT (branch `leases`): with item-driven dispatch, ergostat runs the block once per ticket with a
lease, ERGOSTAT_ITEM naming it and ERGOSTAT_LEASE the lease, and a pool size instead of max: 1. This runner
then takes that one ticket (below) and the oldest-first loop goes.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import traceback
from dataclasses import dataclass, field

import act
from tf import ROOT, items, log, say


@dataclass
class Move:
    fields: dict = field(default_factory=dict)
    event: str | None = None
    out: str | None = None                              # the flow it moved along: flow.<NAME> unless said
    note: str = ""


@dataclass
class Wait:
    why: str
    fields: dict = field(default_factory=dict)          # recorded (ticket.noted) when there are any


@dataclass
class Stop:
    why: str


def load(name: str):
    path = ROOT / "steps" / f"{name}.py"
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location(f"step_{name.replace('-', '_')}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def attempt(mod, ticket: dict):
    if mod is None:
        return Move()
    try:
        return mod.run(ticket)
    except act.Pending as e:
        return Wait(str(e))
    except (act.Denied, act.Failed) as e:
        return Stop(str(e))
    except Exception as e:                                 # noqa: BLE001: a step's bug stops its ticket, said why
        log(traceback.format_exc())
        return Stop(f"{type(e).__name__}: {e}")


def main() -> int:
    sys.modules.setdefault("step", sys.modules[__name__])   # the scripts' `from step import Move` is this module
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--from", dest="state", required=True)
    a = ap.parse_args()
    mod = load(a.name)
    waiting = sorted(items("ticket", a.state), key=lambda t: t.get("entered") or 0)
    leased = os.environ.get("ERGOSTAT_ITEM")              # PLUG POINT (leases): the one ticket this run is for
    if leased:
        waiting = [t for t in waiting if t["id"] == leased]
    for ticket in waiting:
        got = attempt(mod, ticket)
        if isinstance(got, Move):
            say({"event": got.event or f"ticket.{a.name}", "item": ticket["id"], "data": got.fields})
            log(f"{ticket['id']}: {a.name} done" + (f" ({got.note})" if got.note else ""))
            say({"out": got.out or f"flow.{a.name}", "moved": 1})
            return 0
        if isinstance(got, Stop):
            say({"event": "ticket.stopped", "item": ticket["id"], "data": {"stopped_why": got.why, "stopped_at": a.name,
                                                                          "stopped_from": a.state}})
            log(f"{ticket['id']}: stopped at {a.name}: {got.why}")
            continue
        if got.fields:
            say({"event": "ticket.noted", "item": ticket["id"], "data": got.fields})
        log(f"{ticket['id']}: waits at {a.name}: {got.why}")
    say({"out": f"flow.{a.name}", "moved": 0})
    return 0


if __name__ == "__main__":
    sys.exit(main())
