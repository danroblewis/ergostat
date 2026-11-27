"""The forecast (SPEC §5a, *The forecast*): the completion estimates as one stable, versioned answer, ``forecast/v1``,
per item, per group and per stage, made from the one Monte Carlo (``eta.simulate`` over ``etamodel.read``'s inputs;
no estimator of its own). The Timeline, an item's page, the Items tab, a dashboard's SQL views (``forecast_*``,
datasources/_itemviews.py), ``GET /api/forecast`` and the remote API (``/remote/v1/forecast``) all read this answer.

Every answer (the whole, each item, kind, group and stage) says its **basis** (what it is drawn from), its **sample
size** (``runs``: the simulation's runs; ``basis.sample``: the record's stays or runs its curve is drawn from) and
when it was **computed** (wall time; ``at`` is the moment it is of). When it has no estimate it says so and why, in
``none``: the whole, when no run finished within the budget or the simulation failed (then ``items`` is empty, never
read as no items); an item, group, stage or kind, when it is not scheduled or does not finish within the horizon in
the median run. A missing p90 (too few runs) is said in ``p90_none``.

Stable: under one ``schema`` a key may be added, and a key's meaning never changes. ``version`` counts the answers
worked out for one model and what-if since the server started (one more each time the simulation runs again; an
answer reused because nothing it reads changed keeps its version); ``seq`` is the record's last event it read."""

from __future__ import annotations

import hashlib

from . import yields
from .eta import FEW, HORIZON, RUNS
from .etamodel import HISTORY

SCHEMA = "forecast/v1"
MOST_GROUPS = 200           # groups said in one forecast (the rest counted in ``groups_left``)
MOST_COUNTED = 500_000      # members times runs kept for the group counts in one forecast (4 MB of times)


def sets(inp) -> tuple[dict[str, list[str]], int]:
    """The sets the simulation says a last finish for: each group (``group:PARENT``, at most ``MOST_GROUPS``, by
    parent id) and each stage, a kind's state with open items in it now (``stage:KIND/STATE``); and the groups left."""
    out: dict[str, list[str]] = {}
    for x in sorted(inp.items.values(), key=lambda x: x.id):
        out.setdefault(f"stage:{x.kind}/{x.state}", []).append(x.id)
    groups = sorted(inp.groups)
    for g in groups[:MOST_GROUPS]:
        out[f"group:{g}"] = list(inp.groups[g])
    return out, max(0, len(groups) - MOST_GROUPS)


def counted(inp, runs: int = RUNS) -> dict[str, list[str]]:
    """The groups whose runs are kept for their counts (numbers/yields.py): each said group's members, its parent not
    counted, by parent id while their members times ``runs`` stay within ``MOST_COUNTED`` (the rest say why not)."""
    out, room = {}, MOST_COUNTED
    for g in sorted(inp.groups)[:MOST_GROUPS]:
        ids = [i for i in dict.fromkeys(inp.groups[g]) if i != g]
        if len(ids) * runs > room:
            break
        out[g], room = ids, room - len(ids) * runs
    return out


def fingerprint(inp, pools: dict, failures: dict) -> str:
    """What the simulation reads of the record, without the clock: an answer is reused while this is unchanged. Every
    input is in it but those that move with the clock alone, taken by size or rounded instead: a curve's stays and a
    block's runs and refusals by how many (a stay or run still going grows), a kind's arrival rate to 0.1 an hour and
    its next-state and first-state shares to 0.001."""
    items = sorted((x.id, x.kind, x.state, x.entered, x.queued, x.lease, x.attempts, x.not_before, tuple(x.preds),
                    x.level, x.unscheduled, tuple(sorted(x.holds)), repr(sorted(x.fields.items())))
                   for x in inp.items.values())
    blocks = [(b.name, b.kind, tuple(b.at), b.pool, b.lanes, b.off, len(b.attempts), len(b.refusals), tuple(b.shared),
               b.unblocked, b.most, b.ttl, b.workspace, tuple(b.order), b.assumed, b.pool_said, b.measured)
              for b in inp.blocks]
    def shares(xs):
        return tuple((s, round(w, 3)) for s, w in xs)
    kinds = sorted((k.name, tuple(k.states), tuple(sorted(k.finished)), tuple(sorted(k.paused)), tuple(sorted(k.lost)),
                    tuple((s, km.n) for s, km in sorted(k.km.items())), round(k.arrivals, 1),
                    tuple((s, shares(v)) for s, v in sorted(k.next.items())), shares(k.arrive_at))
                   for k in inp.kinds.values())
    groups = sorted((g, tuple(m)) for g, m in inp.groups.items())
    text = repr((items, blocks, kinds, groups, sorted(inp.workspaces.items()), sorted(pools.items()),
                 sorted(failures.items())))
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _item_basis(inp, x) -> dict:
    """What an item's wait now is drawn from: the block running or taking it (its recorded runs), or its state's stays
    (its own, its kind's or every kind's)."""
    b = next((b for b in inp.blocks if x.lease and b.name == x.lease[0]), None) or \
        next((b for b in inp.blocks if b.kind == x.kind and x.state in b.at), None)
    if b is not None:
        return {"from": "block", "name": b.name, "sample": len(b.attempts), "of": "recorded runs",
                **({"assumed": b.assumed} if b.assumed else {})}
    k = inp.kinds[x.kind]
    km = k.km.get(x.state)
    return {"from": "state", "name": x.state, "sample": km.n if km else 0, "of": "recorded stays",
            "whose": k.said.get(x.state, "all")}


def _said(e: dict, runs: int, computed: float, none: str) -> dict:
    e["computed"] = computed
    e.setdefault("runs", runs)
    if e.get("p50") is None:
        e["none"] = none
    elif e.get("p90") is None and runs < FEW:
        e["p90_none"] = f"{runs} runs, fewer than the {FEW} a p90 is said from"
    return e


def build(inp, sim: dict, why: dict, computed: float, seq, whatif: list, sources: dict, left: int = 0,
          seed: int = 1) -> dict:
    """``forecast/v1`` from the simulation's answer ``sim`` (of ``inp``, with its ``sets``) and ``eta.reasons``'
    words ``why``; ``left``: the groups past ``MOST_GROUPS``; ``version`` is set by the worker that keeps it."""
    assumed = {b.name: b.assumed for b in inp.blocks if b.assumed}
    runs = sim.get("runs") or 0
    beyond = f"not finished within the {HORIZON / 86400:.0f} days ahead in the median run"
    items = {}
    for i, x in sim.get("items", {}).items():          # (reasons' words kept; one not scheduled says so first)
        e = dict(x)
        r = dict(why.get(i) or {})
        if e.get("unscheduled"):                       # (the bare reason kept for the Timeline row and item page)
            r["said"] = e["why"]
        if e.get("unscheduled") and not r.get("why", "").startswith(e["why"]):
            r["why"] = f"not scheduled: {e['why']}" + (f"; {r['why']}" if r.get("why") else "")
        elif e.get("out"):                             # (counted out in some runs: said after reasons' words)
            r["why"] = "; ".join(filter(None, [r.get("why"), e["why"]]))
        e.update(r)
        e["projection"], e["state"] = inp.items[i].kind, inp.items[i].state
        e["basis"] = _item_basis(inp, inp.items[i])
        items[i] = _said(e, runs, computed, f"not scheduled: {x['why']}" if x.get("unscheduled") else beyond)
    kinds = {k: _said({**v, "basis": {"open": v["open"], "visits": v["visits"]}}, runs, computed,
                      beyond if v["open"] else "no open item that can move")
             for k, v in sim.get("projections", {}).items()}
    groups, stages, draws = {}, {}, {}
    for name, v in sim.get("sets", {}).items():
        what, _, key = name.partition(":")
        e = _said(dict(v), v["runs"], computed, beyond if v["open"] else "none of its open items can move")
        e["basis"] = {"members": v["open"] + v["unscheduled"], "runs": runs}
        if what == "group":
            c = sim.get("counts", {}).get(key)
            if c and c["draws"]:                       # its counts (numbers/yields.py), the parent not a member
                e["count"] = yields.summary(c["members"], c["draws"])
                draws[key] = (c["members"], c["draws"])
            else:
                e["count"] = {"none": f"not counted: the forecast keeps the runs of {MOST_COUNTED:,} members' "
                              "finishes at most, by parent id" if runs else "no run"}
            groups[key] = e
        else:
            kind, _, state = key.partition("/")
            stages[key] = {"projection": kind, "state": state, **e}
    out = {"schema": SCHEMA, "version": None, "seq": seq, "at": inp.at, "computed": computed, "runs": runs,
           "basis": {"since": inp.at - HISTORY, "seed": seed, "horizon": HORIZON, "flags": sim.get("flags", {}),
                     "whatif": whatif, "assumed": assumed, "capacity": sim.get("capacity", {}),
                     "limit": sim.get("limit", {}), "sources": sources},
           "items": items if runs else {}, "projections": kinds, "groups": groups, "groups_left": left, "stages": stages,
           # (the Timeline's own, as eta_api.merge reads them)
           "schedule": sim.get("schedule", {}), "capacity": sim.get("capacity", {}), "limit": sim.get("limit", {}),
           "sources": sources, "assumed": assumed, "whatif": whatif, "flags": sim.get("flags", {}),
           "draws": draws}                             # (each counted group's runs, for asks: never served)
    if not runs:
        out["none"] = "no run of the simulation finished within its budget: no estimate yet"
    return out


def failed(words: str, computed: float, seq, error: bool = True) -> dict:
    """A forecast that could not be worked out (``error``, as the Timeline reads it), or of nothing: no estimate,
    and why."""
    return {"schema": SCHEMA, "version": None, "seq": seq, "computed": computed, "runs": 0, "items": {}, "projections": {},
            "groups": {}, "stages": {}, **({"error": words} if error else {}),
            "none": f"the simulation failed: {words}" if error else words}


def asked(fc: dict, ask: dict) -> dict:
    """A group's counts asked of the forecast (numbers/yields.py ``parse``: ``group``, ``by``, ``at_least``,
    ``confidence``), from its kept runs; ``none`` why, when it has none (not a group, not counted, no run)."""
    got = (fc.get("draws") or {}).get(ask["group"])
    if got is None:
        g = (fc.get("groups") or {}).get(ask["group"])
        why = (g or {}).get("count", {}).get("none") or fc.get("none") or "no such group in the forecast"
        return {**ask, "none": why}
    return {**yields.ask(got[0], got[1], ask), "computed": fc.get("computed"), "version": fc.get("version")}


def served(fc: dict, items: list[str] | None = None, kinds: list[str] | None = None, most: int = 500,
           ask: dict | None = None) -> dict:
    """The forecast as another reader is given it (``/api/forecast``, the remote API): without the levelled schedule
    (the Timeline's own) or the kept runs, only the ``items`` and ``projections`` asked for (all when not asked), at most
    ``most`` items, the rest counted in ``items_left``; with ``ask``, its answer (``asked``)."""
    got = {k: v for k, v in fc.items() if k not in ("schedule", "capacity", "limit", "sources", "assumed", "whatif",
                                                     "flags", "calibration", "draws")}
    if ask is not None:
        got["asked"] = asked(fc, ask)
    every = fc.get("items") or {}
    want = [i for i in (items if items is not None else sorted(every)) if i in every
            and (not kinds or every[i].get("projection") in kinds)]
    got["items"] = {i: every[i] for i in want[:most]}
    got["items_left"] = max(0, len(want) - most)
    if items is not None:
        got["items_missing"] = [i for i in items if i not in every]
    if kinds:
        got["projections"] = {k: v for k, v in (fc.get("projections") or {}).items() if k in kinds}
        got["stages"] = {k: v for k, v in (fc.get("stages") or {}).items() if v["projection"] in kinds}
    return got
