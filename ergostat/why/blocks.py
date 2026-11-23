"""What the model's blocks say about an item no relation holds (SPEC §5a, *Why it is not done*): the lease on it, or
the blocks that take it from its state, each looked at in the dispatcher's order (its ``where``, a give-back's wait,
the engine, the budget, the gate that commands it, its pool, its runs failing). Readings are the record's, as the
engine left them: a gate's output (``block/NAME``), a goal's last crossing, a stock's newest reading."""

from __future__ import annotations

import ast

from ..costs import budget
from ..leases import TAKEN, poolnow
from ..spec import items as its
from ..spec.ir import LEASED, Ref
from . import ev, item_link, root

REFUSED_FRESH = 300.0    # a budget refusal this recent, with no run started since, is still refusing
FAILS = 3                # a block whose last this many runs failed is failing


def engine_now(p, now: float) -> dict:
    """Whether an engine is running here: the runner's lock held, and its heartbeat fresh."""
    from .. import runner, watcher
    pid = runner.running_pid(p, wait=False)
    hb = watcher.beat(p.dir) or {}
    written = hb.get("written") if isinstance(hb.get("written"), int | float) else None
    stale = written is None or now - written > watcher.limit(p.dir, hb)
    return {"running": bool(pid) and not stale, "pid": pid, "beat": written,
            "said": "no engine holds the run lock" if not pid else
                    f"the engine (pid {pid}) has not passed since {_ago(now, written)}" if stale else f"pid {pid}"}


def _ago(now, t) -> str:
    from ..durations import human
    return "never" if t is None else f"{human(max(0.0, now - t))} ago"


def _blink(name: str) -> str:
    return f"/diagram?view=blocks&around=block/{name}"


def holder(ctx, it) -> dict:
    """The root for an item held under a lease: a person asked, the owner asked for an action, a lease whose process
    is gone or that is past its expiry, or the work itself, going on."""
    lease = it.fields["lease"]
    b = ctx.spec.blocks.get(lease.get("block") or "")
    run, name = str(lease.get("holder"))[:8], lease.get("block") or "a block no longer in the model"
    taken, now = lease.get("taken"), ctx.now
    proof = [ev(f"leased to run {run} of {name} {_ago(now, taken)}", item_link(it.id), at=taken)]
    asked = _actions(ctx, it.id)
    if asked:
        a = asked[0]
        return root("person", it.id, f"its run waits for the owner to answer the gated action {a['id']} "
                    f"({a['fields'].get('action') or 'an action'}), asked {_ago(now, a['first'])}", "the owner",
                    "approve or deny it", f"ergostat inbox action/{a['id'].split('/', 1)[1]} --approve | --deny",
                    proof + [ev("the action asked", item_link(a["id"]), at=a["first"])], since=a["first"], who="the owner")
    pid = _taken_pid(ctx, it)
    eng = ctx.engine
    gone = pid is not None and not budget.alive(pid)
    if gone or not eng["running"]:
        why = f"the process that took it (pid {pid}) is gone" if gone else f"no engine is running ({eng['said']})"
        return root("lease", it.id, f"held by run {run} of {name}, but {why}: nothing renews or ends its lease",
                    "the owner", "start the engine: its watchdog expires the lease and the item is taken again",
                    "ergostat run", proof + [ev(f"engine: {eng['said']}", None, at=eng.get("beat"))], since=taken)
    exp = lease.get("expires")
    if isinstance(exp, int | float) and exp < now:
        return root("lease", it.id, f"held by run {run} of {name}, whose lease expired {_ago(now, exp)} and has not been "
                    "ended", f"the engine's watchdog (pid {eng.get('pid')})",
                    "it expires the lease at its next look; if it does not, see the engine's log", "ergostat lease " + it.id,
                    proof, since=exp)
    agent = ctx.spec.agents.get(b.agent or "") if b else None
    who = f"{name}" + (f" ({agent.kind} {agent.name})" if agent else "")
    return root("work", it.id, f"being worked by {who}, run {run}, since {_ago(now, taken)}"
                + (f"; its lease runs to {_ago(now, exp).replace(' ago', '')} from now" if isinstance(exp, int | float) else ""),
                who, "let the run finish", f"ergostat lease {it.id}", proof, since=taken)


def _taken_pid(ctx, it):
    got = ctx.p.events.query(n=1, item=it.id, type=TAKEN)
    pid = (got[0].get("data") or {}).get("pid") if got else None
    return pid if isinstance(pid, int) and not isinstance(pid, bool) else None


def _actions(ctx, iid: str) -> list:
    from ..actions.record import ACTION
    if not getattr(ctx.spec, "actions", None):
        return []
    with ctx.ix.lock:
        got = ctx.ix.items(ACTION, ["requested"], moves=False)
    return [{"id": a.id, "fields": a.fields, "first": a.first} for a in got if a.fields.get("item") == iid]


def taken(ctx, it, info) -> dict:
    """The root for an item in its state, nothing it waits on unfinished and no lease on it."""
    bs = [b for b in ctx.spec.blocks.values() if b.takes and b.takes.kind == it.kind and it.state in b.takes.at]
    kind = ctx.spec.items[it.kind]
    onward = sorted(e for e, s in (kind.on or {}).items() if s != it.state)
    moved = f"moved to {it.state} by {it.latest or 'an event'}"
    if not bs:
        if it.state in info["working"] and it.state not in info["queue"]:
            return root("work", it.id, f"in progress in {it.state}, outside ergostat: no block takes it from there, and "
                        f"it moves on when one of these is recorded: {', '.join(onward) or 'none declared'}",
                        "whoever records " + (onward[0] if onward else "its next event"), "finish the work and record it",
                        None, [ev(moved, item_link(it.id), at=it.entered)], since=it.entered)
        return root("nothing", it.id, f"nothing takes {it.kind} items from {it.state}: no block's takes: names it, and "
                    "nothing it waits on is unfinished", "the owner",
                    f"add a block that takes: {{kind: {it.kind}, at: [{it.state}]}}, or record the event that moves it",
                    None, [ev(moved, item_link(it.id), at=it.entered)], since=it.entered)
    got = [r for r in (_block(ctx, b, it) for b in bs) if r is not None]
    if got:
        return got[0]
    names = ", ".join(b.name for b in bs)
    return root("unknown", it.id, f"nothing in the record holds it: {names} may take it from {it.state}, and no closed "
                "gate, full pool, refusal or failing run is recorded for it", "the engine",
                "look at the engine's log if it is not taken within a minute", "ergostat lease",
                [ev(f"{b.name}: takes it, room now", _blink(b.name)) for b in bs], since=it.entered)


def _block(ctx, b, it) -> dict | None:
    now, p = ctx.now, ctx.p
    where = b.takes.where or {}
    off = {k: v for k, v in where.items() if not its.matches(it, {k: v})}
    if off:
        have = ", ".join(f"{k} is {its.field_at(it.fields, k)!r} (it takes {v!r})" for k, v in off.items())
        return root("nothing", it.id, f"{b.name} takes from {it.state} only items whose fields match its where:, and "
                    f"here {have}", "whatever sets " + ", ".join(off), f"change {', '.join(off)}, or {b.name}'s where:",
                    None, [ev(f"{b.name}'s takes: where", _blink(b.name)), ev("its fields", item_link(it.id))])
    lease = it.fields.get("lease") or {}
    nb = lease.get("not_before")
    if isinstance(nb, int | float) and nb > now:
        last = (lease.get("history") or [{}])[-1]
        return root("lease", it.id, f"given back by its last run ({last.get('how') or 'ended'}"
                    + (f": {last['why']}" if last.get("why") else "") + f"), not taken again for {_ago(nb, now)[:-4]}"
                    + (" or until news of it" if lease.get("news") else ""), b.name, "wait, or redrive it by hand",
                    None, [ev("its lease's history", item_link(it.id), at=last.get("ended"))], since=last.get("ended"))
    eng = ctx.engine
    if not eng["running"]:
        return root("block", it.id, f"{b.name} takes it from {it.state}, but no engine is running ({eng['said']})",
                    "the owner", "start the engine", "ergostat run", [ev(f"engine: {eng['said']}", None, at=eng.get("beat"))])
    late = p.events.query(n=1, item=b.name, type=f"{budget.REFUSED},{budget.STARTED}")
    if late and late[0]["type"] == budget.REFUSED and now - late[0]["time"] <= REFUSED_FRESH:
        d = late[0].get("data") or {}
        return root("gate", it.id, f"the day's AI budget refuses {b.name}'s runs: {d.get('why') or 'refused'}",
                    "the owner", "raise budget: daily: in the model, or wait for the day's spending to fall",
                    "ergostat explain block." + b.name,
                    [ev(f"budget.refused {_ago(now, late[0]['time'])}: {d.get('why')}", f"/api/events/{late[0]['id']}",
                        late[0]["id"], late[0]["time"])], since=late[0]["time"], gate="budget")
    gate = _gates(ctx, b, it)
    if gate is not None:
        return gate
    pool = poolnow.now(b, poolnow.read_at(p, ctx.spec, b, now)) if b.pool_now else b.pool
    with ctx.ix.lock:
        mine = [i.id for i in ctx.ix.items(it.kind, [LEASED], moves=False)
                if isinstance(i.fields.get("lease"), dict) and i.fields["lease"].get("block") == b.name]
    if len(mine) >= pool:
        said = f" (from {b.pool_now}, " + ("which has no reading)" if pool == 0 else "now)") if b.pool_now else ""
        for x, h in ctx.items(mine[:20]).items():          # a holder whose lease is dead holds the pool for nothing
            r = holder(ctx, h)
            if r["kind"] == "lease":
                return {**r, "says": f"{b.name}'s pool is full ({len(mine)} of {pool}), and {x} holds a place in it: "
                        + r["says"], "item": x, "via": b.name}
        return root("pool-full", it.id, f"{b.name}'s pool is full: {len(mine)} of {pool} runs at once{said}"
                    + (f", holding {', '.join(mine[:5])}" + (f" and {len(mine) - 5} more" if len(mine) > 5 else "")
                       if mine else ""), b.name, "finish a run, or raise its pool", "ergostat lease",
                    [ev(f"held by {b.name}", item_link(x)) for x in mine[:5]] + [ev(f"{b.name}'s pool", _blink(b.name))])
    ends = p.events.query(n=FAILS, item=b.name, type="agent.ran,agent.failed")
    if len(ends) == FAILS and all(e["type"] == "agent.failed" for e in ends):
        note = (ends[-1].get("data") or {}).get("note") or "failed"
        return root("block", it.id, f"{b.name}'s last {FAILS} runs failed, the latest {_ago(now, ends[-1]['time'])}: "
                    f"{note}", b.agent or b.name, f"fix {b.name}", f"ergostat agent {b.agent or b.name}",
                    [ev(f"agent.failed: {(e.get('data') or {}).get('note')}", f"/api/events/{e['id']}", e["id"], e["time"])
                     for e in ends], since=ends[0]["time"])
    return None


def reading(ctx, r) -> tuple[float | None, float | None, str]:
    """A signal's value as the record left it: (value, when, where it was read); None when it has none."""
    p, spec = ctx.p, ctx.spec
    if r.kind == "goal" and r.name in spec.goals and r.port == "off":
        last = p.events.query(n=1, item=r.name, type="loop.*", unvoided=True)
        return ((1.0 if last[0]["type"] == "loop.off" else 0.0), last[0]["time"], f"goal {r.name}: {last[0]['type']}") \
            if last else (None, None, f"goal {r.name}: no crossing recorded")
    if r.kind == "block":
        got = p.measurements.latest(f"block/{r.name}")
        return (got[1], got[0], f"block/{r.name}") if got else (None, None, f"block/{r.name}: no reading")
    part = {"stock": spec.stocks, "flow": spec.flows, "auxiliary": spec.auxiliaries}.get(r.kind, {}).get(r.name)
    series = [s.series for s in (part.sensors.values() if part else ())] + ([f"sensor/{r.name}.set"] if r.kind == "auxiliary" else [])
    best = max((x for x in (p.measurements.latest(s) for s in series) if x), default=None)
    return (best[1], best[0], f"{r} (its newest reading)") if best else (None, None, f"{r}: no reading")


def _gates(ctx, b, it) -> dict | None:
    """A gate that commands the block, reading 0 (the dispatcher takes nothing then): which of its factors is 0, and
    what each factor reads; or that its reading is not recorded."""
    try:
        cs = ctx.spec.commanders_of(b.name)
    except KeyError:
        return None
    vals = []
    for c in cs:
        v, t, where = reading(ctx, Ref("block", c.name)) if c.builtin else (None, None, "")
        vals.append((c, v, t, where))
    if not vals or any(v for _, v, _, _ in vals) or not all(c.builtin for c, *_ in vals):
        return None
    c, v, t, where = vals[0]
    if v is None:
        return root("unknown", it.id, f"{c.name} commands {b.name}, and its output has no reading: whether it lets "
                    f"{b.name} take items is not recorded", "the engine", "run the engine so the gate is worked out",
                    "ergostat explain block." + c.name, [ev(where, _blink(c.name))])
    blame, kind = _factors(ctx, c)
    said = lambda n, x: f"{n} = {x[0]:g} from {x[2]}" if x[0] is not None else f"{n}: {x[2]}"   # noqa: E731
    names = "; ".join(f"{t_} {'cannot be worked out' if kind == 'unknown' else 'is 0'} "
                      f"({', '.join(said(n, x) for n, x in rs.items())})" for t_, rs in blame) \
        if blame else f"its expression ({c.params.get('expr', c.type)})"
    proof = [ev(f"{where} = 0 since {_ago(ctx.now, t)}", _blink(c.name), at=t)]
    proof += [ev(x[2], None, at=x[1]) for _, rs in blame for x in rs.values()]
    refs = [x[3] for _, rs in blame for x in rs.values()]
    by_hand = [(r, s) for r in refs for s in _manual(ctx.spec, r)] if kind != "unknown" else []
    owner, cmd = ("a person, reading " + ", ".join(f"{r.name}.{s}" for r, s in by_hand) + " by hand",
                  f"ergostat sensor {by_hand[0][0].name}.{by_hand[0][1]} --read V") if by_hand else \
        ("whatever sets " + ", ".join(map(str, refs)) if refs else "the owner", f"ergostat explain block.{c.name}")
    return root("person" if by_hand else kind, it.id, f"{c.name}, which commands {b.name}, is 0, so {b.name} takes "
                f"nothing: {names}", owner, "change what the gate reads, or the gate", cmd, proof, since=t, gate=c.name,
                **({"who": owner} if by_hand else {}))


def _manual(spec, r) -> list[str]:
    """The manual sensors (read by a person) of the part a gate's input names."""
    part = {"stock": spec.stocks, "flow": spec.flows, "auxiliary": spec.auxiliaries}.get(r.kind, {}).get(r.name)
    return [n for n, s in (part.sensors.items() if part else ()) if getattr(s, "manual", False)]


def _factors(ctx, c) -> tuple[list, str]:
    """An expression gate's factors that read 0 (its top-level product), each with its inputs' readings; ``closed``
    when every input of those reads 0 (a goal holding, an intake shut), else ``gate`` (a limit reached)."""
    from ..spec.blocks import compile_expr, eval_expr, expr_names
    if c.type != "expr":
        return [], "gate"
    tree = compile_expr(str(c.params.get("expr")))
    terms, todo = [], [tree.body]
    while todo:
        n = todo.pop()
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Mult):
            todo += [n.right, n.left]
        else:
            terms.append(n)
    ports = {k.replace("-", "_"): r for k, r in c.inputs.items()}
    read = {k: (*reading(ctx, r), r) for k, r in ports.items()}
    env = {k: x[0] for k, x in read.items() if x[0] is not None}
    out, unread = [], []
    for t in terms:
        names = expr_names(ast.Expression(t))
        rs = {n: read[n] for n in names if n in read}
        if not names <= set(env):
            unread.append((ast.unparse(t), rs))
            continue
        try:
            if eval_expr(ast.Expression(t), env) == 0:
                out.append((ast.unparse(t), rs))
        except (ArithmeticError, ValueError, TypeError):
            unread.append((ast.unparse(t), rs))
    if not out:                                  # no factor known to be 0: which one is, the record does not say
        return unread, "unknown"
    zero = [x[0] for _, rs in out for x in rs.values()]
    return out, "closed" if zero and all(v == 0 for v in zero) else "gate"
