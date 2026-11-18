"""One step of the ticket workflow, run by its block for one ticket: the block takes the tickets in its state
(`takes:`), a run per ticket under a lease, ERGOSTAT_ITEM naming it. This runs the step's script
(steps/<name>.py) for that ticket, and says how it went:

    step.py NAME

The script's run(ticket) returns:

    Move(fields)     done: the event ticket.<NAME> is recorded with these fields, and the kind's `on:` moves
                     the ticket to the step's next state (ticket.yaml); the block reports it moved along
                     flow.<NAME>. Move(fields, event="ticket.x", out="flow.y") for another way out (a review
                     that asks for changes, a CI run that failed)
    Wait(why)        not yet (an approval, a reviewer, CI): the ticket is given back, put off for POLL_EVERY and
                     not counted as a failure ({"nack": {..., "count": false}}); its next run asks again
    Stop(why)        it cannot go on: the ticket moves to `stopped`, for the owner

A step with no script moves its ticket on at once (Move()): a step that is only a state, for a person or a
program outside to act on. A gated action held for the owner (gated.Pending) is a Wait; one denied
(gated.Denied) or failed (gated.Failed) is a Stop unless the script catches it. A step that crashes exits 1:
ergostat counts the attempt, and after the kind's attempts the ticket is a dead letter (`ergostat lease`).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import traceback
from dataclasses import dataclass, field

import gated
from tf import ROOT, conf, item, log, say


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
    except gated.Pending as e:
        return Wait(str(e))
    except (gated.Denied, gated.Failed) as e:
        return Stop(str(e))
    except Exception as e:                                 # noqa: BLE001: a step's bug stops its ticket, said why
        log(traceback.format_exc())
        return Stop(f"{type(e).__name__}: {e}")


def main() -> int:
    sys.modules.setdefault("step", sys.modules[__name__])   # the scripts' `from step import Move` is this module
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    a = ap.parse_args()
    try:
        given = json.loads(sys.stdin.read() or "{}")       # its input: the ticket and its lease (SPEC 9.5)
    except json.JSONDecodeError:
        given = {}
    tid = os.environ.get("ERGOSTAT_ITEM")
    ticket = item(tid) if tid else None
    if ticket is None:
        log(f"{a.name}: no ticket (ERGOSTAT_ITEM: {tid!r}): a step runs for the ticket its block takes")
        return 1
    got = attempt(load(a.name), ticket)
    if isinstance(got, Move):
        say({"event": got.event or f"ticket.{a.name}", "item": tid, "data": got.fields})
        say({"out": got.out or f"flow.{a.name}", "moved": 1})
        log(f"{tid}: {a.name} done" + (f" ({got.note})" if got.note else ""))
    elif isinstance(got, Stop):
        say({"event": "ticket.stopped", "item": tid, "data": {"stopped_why": got.why, "stopped_at": a.name,
                                                              "stopped_from": (given.get("lease") or {}).get("back")}})
        say({"out": f"flow.{a.name}", "moved": 0})
        log(f"{tid}: stopped at {a.name}: {got.why}")
    else:
        if got.fields:
            say({"event": "ticket.noted", "item": tid, "data": got.fields})
        say({"nack": {"why": got.why, "after": conf("POLL_EVERY", "15s"), "count": False}})
        say({"out": f"flow.{a.name}", "moved": 0})
        log(f"{tid}: waits at {a.name}: {got.why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
