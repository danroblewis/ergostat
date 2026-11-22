"""What a kind of item, and one item, touch in the model (SPEC §5a, *What a kind touches*): the parts whose sensors
count it, the blocks that take it, the goals and feedback loops through those, and an item's moves as steps through
them. Read from the spec alone (an item's path from that item alone), never from the record; worked out once per
model version (``spec.lookups().kept``), each caller given its own copy."""

from __future__ import annotations

import copy

from .ir import DEAD, LEASED, Ref


def _hold(g) -> str:
    return f"{g.hold.op} {g.hold.value:g}"


def _finished(spec, k) -> tuple[list[str], str]:
    """The states it is finished in, and why: ``messages: {done:}`` when it says, else its last state."""
    if k.name in spec.messages.done:
        return list(spec.messages.done[k.name]), "messages: done:"
    return k.states[-1:], "its last state"


def _counted_in(spec, kind: str) -> list[dict]:
    out = []
    for s in spec.sensors():
        q = s.items or {}
        if q.get("kind") != kind:
            continue
        row = {"part": str(s.of), "kind": s.of.kind, "name": s.of.name, "sensor": s.name, "system": spec.owner(s.of)}
        if s.of.kind == "flow":
            row.update({"entering": q["entering"]} if q.get("entering") else {"leaving": q.get("leaving")})
        else:
            row["states"] = list(q.get("state") or [])          # none: every state
        out.append({**row, **({"where": q["where"]} if q.get("where") else {}),
                    **({"measure": q["measure"]} if q.get("measure") else {})})
    return out


def _taken_by(spec, kind: str) -> list[dict]:
    from ..leases.terms import terms
    out = []
    for b in spec.blocks.values():
        t = b.takes
        if t is None or t.kind != kind:
            continue
        lt = terms(spec, b)
        some = [f"whose {f} is {' or '.join(map(str, v)) if isinstance(v, list) else v}" for f, v in t.where.items()]
        some += ["unblocked"] if t.unblocked else []
        out.append({"block": b.name, "type": b.type, "agent": b.agent, "rung": lt["tier"], "at": list(t.at),
                    "to": list(t.to), "where": dict(t.where), "unblocked": t.unblocked, "order": list(t.order),
                    "pool": b.pool, **({"pool_now": str(b.pool_now)} if b.pool_now else {}),
                    "attempts": lt["attempts"], "ttl": lt["ttl"], "goal": b.goal, "system": b.system,
                    "out": [str(r) for r in b.targets() if r.kind == "flow"],
                    "only_some": bool(some), "says": f"takes only the items {' and '.join(some)}" if some
                    else f"takes every {kind} in {' or '.join(t.at)}"})
    return out


def _build(spec, kind: str) -> dict:
    from .item_systems import TITLES, kind_systems
    k = spec.items[kind]
    counted, taken = _counted_in(spec, kind), _taken_by(spec, kind)
    done, done_why = _finished(spec, k)
    states = list(dict.fromkeys([*k.states, *([LEASED, DEAD] if taken else [])]))   # (a taken kind has them already)
    rel_in = [{"kind": o.name, "relation": r, "inverse": x.inverse or None}
              for o in spec.items.values() for r, x in o.relations.items() if kind in x.kinds]
    where = kind_systems(spec).get(kind) or {}
    definition = {
        "name": kind, "title": TITLES.get(kind) or kind, "description": k.description, "id": k.id,
        "states": [{"state": s, "first": i == 0, "finished": s in done, "final": s in k.final,
                    "ergostat": s in (LEASED, DEAD)} for i, s in enumerate(states)],
        "finished_by": done_why, "on": dict(k.on), "show": list(k.show), "fold": dict(k.fold),
        "relations": {r: {"kinds": x.kinds, "precedence": x.precedence, "inverse": x.inverse or None, "group": x.group}
                      for r, x in k.relations.items()}, "named_by": rel_in,
        "join": [{"children": j.children, "states": j.states, "to": j.to, "all": j.all} for j in k.join],
        "lease": {"ttl": k.lease.ttl, "attempts": k.lease.attempts}, "about": k.about,
        "system": where.get("system"), "system_why": where.get("why")}
    parts = {c["part"] for c in counted} | {f"block.{t['block']}" for t in taken} | {f for t in taken for f in t["out"]}
    goals = {}
    for t in taken:
        if t["goal"] in spec.goals:
            goals[t["goal"]] = f"served by block {t['block']}"
    for name, g in spec.goals.items():
        if str(g.of) in parts and name not in goals:
            goals[name] = f"on {g.of.kind} {g.of.name}"
    goal_rows = [{"goal": n, "of": str(spec.goals[n].of), "hold": _hold(spec.goals[n]), "why": why,
                  "description": spec.goals[n].description, "system": spec.owner(Ref("goal", n))} for n, why in goals.items()]
    from .causal import loops as causal_loops
    touch = parts | {f"goal.{n}" for n in goals}
    loops = [{"name": lp.name, "polarity": lp.polarity, "parts": lp.parts, "through": [x for x in lp.parts if x in touch]}
             for lp in causal_loops(spec) if touch & set(lp.parts)]
    counts = {s for c in counted if c["kind"] != "flow" for s in (c["states"] or states)}
    moves = {c.get("entering") or c.get("leaving") for c in counted if c["kind"] == "flow"}
    out = {"kind": kind, "definition": definition, "counted_in": counted, "taken_by": taken, "goals": goal_rows,
           "loops": loops, "uncounted": [s for s in states if s not in counts and s not in moves]}
    if not counted and not taken:
        out["why"] = f"no sensor counts items of kind {kind}, and no block takes them: it touches nothing in the model"
    return out


def kind_footprint(spec, kind: str) -> dict | None:
    """What ``kind`` touches (None: no such kind): its definition, the parts that count it, the blocks that take it,
    their goals and loops, and the states nothing counts."""
    if spec is None or kind not in spec.items:
        return None
    kept = spec.lookups().kept
    key = ("footprint", kind)
    if key not in kept:
        kept[key] = _build(spec, kind)
    return copy.deepcopy(kept[key])


def _attempts(history: list[dict]) -> list[int]:
    """Each lease's attempt number: counted ends add one, an ack (or a dead letter redriven) starts again."""
    out, n = [], 0
    for h in history:
        out.append(n + 1)
        n = 0 if h.get("how") == "ack" or h.get("dead") else n + (1 if h.get("counted") else 0)
    return out


def item_path(spec, it) -> list[dict]:
    """An item's moves as ordered steps through the model: each state it was in (``leased`` is not a step: the lease
    is the step's ``block``), the stock that counts it there and the flow that counted it in, the block that took it
    from there (or had taken it while it was there), that run's attempt, the goal, when it entered and left. A nack or rework is
    a repeated step; a state nothing counts says so."""
    fp = kind_footprint(spec, it.kind or "") or {"counted_in": [], "taken_by": [], "goals": []}
    stocks, flows = {}, {}
    for c in fp["counted_in"]:
        if c["kind"] == "flow" and c.get("entering"):
            flows.setdefault(c["entering"], c["name"])
        elif c["kind"] != "flow":
            for s in c["states"] or [m["to"] for m in it.moves]:
                stocks.setdefault(s, (c["name"], c["part"]))
    on_part = {g["of"]: g["goal"] for g in reversed(fp["goals"])}
    goal_of = {t["block"]: t["goal"] for t in fp["taken_by"]}
    lease = it.fields.get("lease") if isinstance(it.fields.get("lease"), dict) else {}
    hist = list(lease.get("history") or [])
    tries = _attempts(hist)
    taken = [i for i, m in enumerate(it.moves) if m["to"] == LEASED]
    skip = len(hist) - len(taken)                    # the k-th move into leased is the k-th lease (a rollup kept the tail)
    lease_at = {i: k + skip for k, i in enumerate(taken) if 0 <= k + skip < len(hist)}
    steps, open_ = [], None
    for i, m in enumerate(it.moves):
        if m["to"] == LEASED:
            open_ = lease_at.get(i)
            continue
        if m["type"].startswith("ergostat.lease."):  # given back, expired or redriven: no run has it taken now
            open_ = None
        nxt = it.moves[i + 1] if i + 1 < len(it.moves) else None
        k, how = (lease_at.get(i + 1), "taken from here") if nxt and nxt["to"] == LEASED else (None, None)
        if k is None and open_ is not None and (hist[open_].get("ended") is None or m["time"] <= hist[open_]["ended"]):
            k, how = open_, "taken while here"
        h = hist[k] if k is not None else {}
        st = m["to"]
        stock, part = stocks.get(st, (None, None))
        step = {"state": st, "stock": stock, "flow": flows.get(st), "block": h.get("block"),
                "run": h.get("run"), "attempts": tries[k] if k is not None else None, "how": how,
                "ended": h.get("how") if how == "taken from here" else None,
                "goal": on_part.get(part) or goal_of.get(h.get("block")),
                "entered": m["time"], "left": nxt["time"] if nxt else None}
        if st not in stocks and st not in flows:
            step["says"] = f"nothing in the model counts {it.kind or 'its'} items in {st}"
        steps.append(step)
    return steps
