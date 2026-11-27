"""What is done to a lease from outside the engine (SPEC §9.5): a run renewing its own lease or giving its item back
(``$ERGOSTAT_ITEM``, ``$ERGOSTAT_LEASE`` and ``$ERGOSTAT_RUN`` name it), and the owner redriving a dead letter. Each
is an event about the item, folded like any other: one that does not apply is refused, and says why."""

from __future__ import annotations

import os

from ..spec import items as its
from ..spec.ir import DEAD
from . import ENDED, REDRIVEN, RENEWED
from .fold import held


class LeaseError(ValueError):
    pass


def _refused(p, spec, item: str, ev: dict) -> str | None:
    it = its.one(p.events, spec, item, (ev.get("data") or {}).get("projection"))
    return next((r["why"] for r in (it.refused if it else []) if r["event"] == ev["id"]), None)


def again(p, ev: dict) -> dict:
    """The event as recorded: the stored one when its id was recorded before (a call asked again)."""
    return ev if ev.get("seq") is not None else p.events.get(ev["id"]) or ev


def mine(env: dict | None = None) -> tuple[str, int, str]:
    """The lease this process's run holds: its item, fencing number and run, from its environment."""
    env = os.environ if env is None else env
    item, fence, run = env.get("ERGOSTAT_ITEM"), env.get("ERGOSTAT_LEASE"), env.get("ERGOSTAT_RUN")
    if not (item and fence and run):
        raise LeaseError("no lease here: a run that holds one has ERGOSTAT_ITEM, ERGOSTAT_LEASE and ERGOSTAT_RUN set")
    return item, int(fence), run


def projection_of(env: dict | None = None) -> dict:
    """The projection whose item the run's lease is on (``ERGOSTAT_PROJECTION``), as a lease event names it."""
    got = (os.environ if env is None else env).get("ERGOSTAT_PROJECTION")
    return {"projection": got} if got else {}


def renew(p, spec, by: str = "ergostat", env: dict | None = None, id: str | None = None) -> dict:
    item, fence, run = mine(env)
    ev = again(p, p.events.add(RENEWED, item=item, source=by, causedby=run, id=id,      # id: a call's (calls/)
                               data={**projection_of(env), "run": run, "fence": fence, "seen": "asked"}))
    why = _refused(p, spec, item, ev)
    if why:
        raise LeaseError(why)
    return ev


def nack(p, spec, why: str, after: float | None = None, count: bool = True, by: str = "ergostat",
         env: dict | None = None, id: str | None = None) -> dict:
    item, fence, run = mine(env)
    it = its.one(p.events, spec, item, projection_of(env).get("projection"))
    lease = held(it.fields) if it else None
    end = {}
    if lease is not None and lease.get("fence") == fence:      # what it leaves the item as (SPEC §9.5)
        from .dispatch import terminal
        n = int(lease.get("attempts") or 0) + (1 if count else 0)
        state = DEAD if count and n >= int(lease.get("max") or 1) else lease.get("back")
        end = {"item": item, "state": state, "terminal": terminal(spec, it.kind, state)}
    ev = again(p, p.events.add(ENDED, item=item, source=by, causedby=run, id=id,
                               data={**projection_of(env), "run": run, "fence": fence, "how": "nack", "why": why, **({"after": after} if after else {}),
                                     **({} if count else {"count": False}), **end}))
    refused = _refused(p, spec, item, ev)
    if refused:
        raise LeaseError(refused)
    return ev


def redrive(p, spec, item: str, why: str = "", to: str | None = None, by: str = "owner") -> dict:
    it = its.one(p.events, spec, item)
    if it is None:
        raise LeaseError(f"nothing is recorded about {item}")
    if it.state != DEAD:
        raise LeaseError(f"{item} is {it.state or 'in no state'}: only a dead letter is redriven")
    ev = p.events.add(REDRIVEN, item=item, source=by, data={"why": why, **({"to": to} if to else {})})
    refused = _refused(p, spec, item, ev)
    if refused:
        raise LeaseError(refused)
    return ev


def listing(p, spec) -> list[dict]:
    """Every item with a lease, held or dead first: its lease as the fold has it."""
    out = []
    for kind in (k for k in spec.items if not k.startswith("ergostat.")):
        for it in its.project(p.events, spec, kind, transcript=False):
            lease = it.fields.get("lease")
            if isinstance(lease, dict):
                out.append({"item": it.id, "projection": it.kind, "state": it.state, "held": bool(held(it.fields)),
                            **{k: v for k, v in lease.items() if k != "history"}, "tries": len(lease.get("history") or [])})
    return sorted(out, key=lambda x: (not x["held"], x["state"] != DEAD, -(x.get("taken") or 0)))
