"""Entering and leaving an operating state (SPEC §9.5) from outside the engine: the owner's typed act, or a run
entering one (toward the safe state, recorded as caused by the run). A run never leaves one: refused here when
``ERGOSTAT_RUN`` is in the environment, and by the fold when the ``left`` is caused by a run. That covers a run that
carries its environment or records through ergostat; a process that writes the record by other means is the
sandbox's to stop."""

from __future__ import annotations

import os

from . import ENTERED, KIND, LEFT, item_of


class OperatingError(ValueError):
    pass


def _state(p, spec, name: str):
    from ..spec import items as its
    return its.one(p.events, spec, item_of(name))


def enter(p, spec, name: str, why: str, env: dict | None = None) -> dict:
    env = os.environ if env is None else env
    if name not in spec.operating:
        raise OperatingError(f"{name}: not an operating state of the model ({', '.join(sorted(spec.operating)) or 'none'})")
    run = env.get("ERGOSTAT_RUN") or None
    return p.events.add(ENTERED, item=item_of(name), source="run" if run else "owner", causedby=run,
                        data={"by": "run" if run else "owner", "why": why})


def leave(p, spec, name: str, why: str, env: dict | None = None) -> dict:
    env = os.environ if env is None else env
    if env.get("ERGOSTAT_RUN"):
        raise OperatingError("only the owner leaves an operating state: refused from a run (ERGOSTAT_RUN is set)")
    if KIND not in spec.items:
        raise OperatingError("the model declares no operating states")
    it = _state(p, spec, name)
    if it is None or it.state != "entered":
        raise OperatingError(f"{name}: not entered")
    return p.events.add(LEFT, item=item_of(name), source="owner", data={"by": "owner", "why": why})


def listing(p, spec) -> list[dict]:
    """Every state declared, and every state entered the model no longer declares: rank, pool, entered or left, by,
    since, and the trips that entered it."""
    from ..spec import items as its
    got = {it.id.split("/", 1)[1]: it for it in its.project(p.events, spec, KIND, transcript=False)}
    out = []
    for name in sorted(set(spec.operating) | {n for n, it in got.items() if it.state == "entered"},
                       key=lambda n: -(spec.operating[n].rank if n in spec.operating else float("inf"))):
        st, it = spec.operating.get(name), got.get(name)
        f = it.fields if it else {}
        out.append({"state": name, "rank": st.rank if st else None, "pool": (st.pool if st else 0), "declared": bool(st),
                    "now": it.state if it else "left", "by": f.get("by"), "why": f.get("why"), "since": f.get("since"),
                    "trips": f.get("trips") or []})
    return out
