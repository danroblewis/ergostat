"""What holds the work up (SPEC §5a, *What holds the work up*): every unfinished item's roots, as ``why`` finds them,
grouped by root and ranked by what each holds (how many items, how many hours they have waited, and the items it holds
that its block would take first), with the goals off only because of a root folded under it.

A root is a **stall** when something that should be moving is not (a dead or stale lease, the budget refusing every run,
a block failing or not running, a cycle, a missing or parked item that others wait on, a dead letter, a state nothing
takes), **held** when it is held on purpose (a gate, a closed goal or intake, a person to answer, an item paused by
hand that nothing waits on), and **queue** when it is ordinary queueing (work going on, a full pool of live runs, a
give-back's wait). A root the record cannot tell is **unknown**: "nothing is stuck" is said only when no root is a stall
or unknown. The model's own item kinds only (``ergostat.*`` kinds are ergostat's own upkeep)."""

from __future__ import annotations

import threading
import time

from ..durations import human
from ..leases.ready import take_key
from ..precedence import status
from ..spec import items as its
from ..spec.ir import DEAD, LEASED
from ..spec.item_sets import _stock_set
from . import Ctx, here, item_link, root

STALL = {"lease", "block", "parked", "cycle", "missing", "nothing"}
HELD = {"gate", "closed", "person"}
CLASSES = ("stall", "unknown", "held", "queue")   # the ranking's first key, in this order
SHOWN = 5          # items named under each root
KEPT = 20          # roots listed (the rest counted)
FRESH = 30.0       # the page's line is worked out again after this, or when the record moves


def klass(r: dict, others: int) -> str:
    """stall, held, queue or unknown, for a root that holds ``others`` items besides its own."""
    k = r["kind"]
    if k == "unknown":
        return "unknown"
    if k == "gate" and r.get("gate") == "budget":
        return "stall"
    if k == "lease" and r.get("backoff"):
        return "queue"
    if k == "parked" and not others and not r.get("dead"):
        return "held"
    return "stall" if k in STALL else "held" if k in HELD else "queue"


def key(r: dict) -> tuple:
    """What makes two items' roots the same root: the item it is about, or what it says (a block's, a gate's)."""
    k = r["kind"]
    if k == "cycle":
        return k, r["members"]
    if k in ("work", "lease", "parked", "missing") or (k == "person" and not r.get("gate")) or \
            (k == "unknown" and r.get("missing")):
        return k, r["item"]
    return k, r["says"]


def unfinished(ctx: Ctx) -> list:
    """Every unfinished item of the model's own kinds (not in a finished state, nor of a kind that lives on)."""
    out = []
    for kind, k in sorted((ctx.spec.items or {}).items()):
        info = ctx.info(kind)
        if kind.startswith("ergostat.") or info is None or info["lives_on"]:
            continue
        states = [s for s in dict.fromkeys([*k.states, LEASED, DEAD]) if s not in info["finished"]]
        with ctx.ix.lock:
            out += ctx.ix.items(kind, states, moves=False)
    return out


def _read(ctx: Ctx, items: list) -> None:
    """Every item, its links and what they name, read up front (three reads of the index, not one per item)."""
    ctx.cache, ctx.links, ctx.memo = {i.id: i for i in items}, {}, {}
    with ctx.ix.lock:
        got = ctx.ix.links_from(list(ctx.cache))
    for a, r, d in got:
        ctx.links.setdefault(a, []).append((r, d))
    ctx.items([d for _, _, d in got])


def resolve(ctx: Ctx, ids: list[str]) -> tuple[dict, dict]:
    """(each item's root keys, each key's root): a depth-first walk, each item's roots worked out once."""
    memo: dict[str, set] = {}
    roots: dict[tuple, dict] = {}
    deps_of: dict[str, list[str]] = {}
    chain: list[str] = []                  # the items whose roots are being worked out, outermost first
    inside: set[str] = set()               # (the same, to look up)

    def add(r: dict) -> tuple:
        k = key(r)
        if k not in roots or (r.get("via") and not roots[k].get("via")):   # (a pool's dead lease says through what)
            roots[k] = r
        return k

    for s in ids:
        stack = [s]
        while stack:
            cur = stack[-1]
            if cur in memo:
                stack.pop()
                continue
            if cur not in deps_of:
                try:
                    deps, r = here(ctx, ctx.items([cur]).get(cur), cur)
                except Exception as e:     # an unreadable field: said, never raised
                    deps, r = [], root("unknown", cur, f"{cur} could not be read: {type(e).__name__}: {e}",
                                       "the owner", "look at its fields and its events")
                if r is not None:
                    memo[cur] = {add(r)}
                    stack.pop()
                    continue
                deps_of[cur] = [(rel, d) for rel, d, _ in deps]
                chain.append(cur)
                inside.add(cur)
                stack += [d for _, d in reversed(deps_of[cur]) if d not in memo and d not in inside]
                continue
            got = set()
            for rel, d in deps_of[cur]:
                if d in memo:
                    got |= memo[d]
                elif d in inside:          # a link back to an item still being worked out: a cycle
                    loop = chain[chain.index(d):] + [d]
                    got.add(add(root("cycle", d, "these wait on one another, so none can ever be ready: "
                                     + " → ".join(loop), "the owner", "remove one link of the cycle",
                                     f"ergostat event --add ITEM.changed --item {cur} --data "
                                     f"'{{\"{rel}\": {{\"remove\": \"{d}\"}}}}'",
                                     evidence=[{"says": a, "link": item_link(a)} for a in loop[:-1]],
                                     members=tuple(sorted(set(loop))))))
            memo[cur] = got
            chain.pop()                    # (it is the innermost: what it waits on was worked out first)
            inside.discard(cur)
            stack.pop()
    return memo, roots


def _rank_of(ctx: Ctx, it) -> tuple:
    """Where an item stands: in the take order of the block that takes it from its state, else after, oldest first."""
    for b in ctx.spec.blocks.values():
        if b.takes and b.takes.kind == it.kind and it.state in b.takes.at:
            return b.name, take_key(b.takes.order, b.takes.at, it.state, it.fields), -(ctx.now - (it.entered or ctx.now))
    return "~", ((), 0, 0.0), -(ctx.now - (it.entered or ctx.now))


def goals_off(ctx: Ctx) -> list[str]:
    """The goals off, by their last recorded crossing (``loop.off``, as the engine wrote it)."""
    out = []
    for g in sorted(ctx.spec.goals):
        last = ctx.p.events.query(n=1, item=g, type="loop.*", unvoided=True)
        if last and last[0]["type"] == "loop.off":
            out.append(g)
    return out


def fold(ctx: Ctx, off: list[str], items: list, memo: dict) -> tuple[dict, list]:
    """(goal → the root key holding most of the items its stock counts, the goals no unfinished item is counted in)."""
    folded, untraced = {}, []
    for g in off:
        ref = ctx.spec.goals[g].of
        got = _stock_set(ctx.spec, ref.name) if ref.kind in ("stock", "auxiliary") else None
        counts: dict = {}
        if got is not None:
            _, kind, states, where = got
            for it in items:
                if it.kind == kind and it.state in states and its.matches(it, where):
                    for k in memo.get(it.id, ()):
                        counts[k] = counts.get(k, 0) + 1
        if counts:
            folded[g] = max(counts, key=lambda k: (counts[k], str(k)))
        else:
            untraced.append(g)
    return folded, untraced


def answer(p, now: float | None = None, engine: dict | None = None) -> dict:
    """``ergostat held-up --json``, ``/api/held-up``, MCP's ``held_up``."""
    from ..spec.itemindex import index_for
    now = time.time() if now is None else now
    spec = getattr(p.model, "spec", None)
    out = {"at": now, "stall": None, "nothing_stuck": False, "unfinished": 0, "roots": [], "more": 0,
           "goals": {"off": [], "untraced": []}, "missing": []}
    ix = index_for(p.events, spec, False) if spec is not None else None
    if ix is None:
        out["missing"].append("this record keeps no item index, so its items' states cannot be read")
        out["line"] = "What holds the work up cannot be worked out: " + out["missing"][0] + "."
        return out
    ctx = Ctx(p, spec, ix, now, engine)
    items = [i for i in unfinished(ctx) if (ctx.info(i.kind) is None or status(i, ctx.info(i.kind), []) != "done")]
    _read(ctx, items)
    memo, roots = resolve(ctx, [i.id for i in items])
    held: dict[tuple, list] = {k: [] for k in roots}
    for it in items:
        for k in memo.get(it.id, ()):
            held[k].append(it)
    off = goals_off(ctx)
    folded, untraced = fold(ctx, off, items, memo)
    ranked = []
    for k, r in roots.items():
        hs = sorted(held[k], key=lambda i: _rank_of(ctx, i))
        own = r["item"] if k[1] == r.get("item") else None    # (a block's or a gate's root is about no one item)
        others = [i for i in hs if i.id != own]
        by: dict = {}
        for i in others:
            by[f"{i.kind} in {i.state}"] = by.get(f"{i.kind} in {i.state}", 0) + 1
        ranked.append({"class": klass(r, len(others)), "kind": r["kind"], "item": own, "via": r.get("via"),
                       "says": r["says"], "owner": r["owner"], "action": r["action"], "command": r.get("command"),
                       "since": r.get("since"), "evidence": r.get("evidence", [])[:SHOWN],
                       "holds": len(hs), "waiting": len(others),
                       "hours": round(sum(now - i.entered for i in hs if i.entered) / 3600, 2),
                       "by": dict(sorted(by.items(), key=lambda x: -x[1])), "first": [i.id for i in others[:SHOWN]],
                       "goals": sorted(g for g, gk in folded.items() if gk == k)})
    ranked.sort(key=lambda x: (CLASSES.index(x["class"]), -x["waiting"], -x["holds"], -x["hours"], x["says"]))
    stalls = [x for x in ranked if x["class"] == "stall"]
    out.update(stall=bool(stalls), unfinished=len(items), roots=ranked[:KEPT], more=max(0, len(ranked) - KEPT),
               nothing_stuck=not stalls and not any(x["class"] == "unknown" for x in ranked),
               goals={"off": off, "untraced": untraced})
    out["line"] = line(out)
    return out


def _held_words(x: dict) -> str:
    n = x["waiting"]
    by = ", ".join(f"{c} {w}" for w, c in list(x["by"].items())[:3])
    wait = f" ({by}), {human(x['hours'] * 3600)} of waiting in all" if n else ""
    goals = f"; {len(x['goals'])} goal{'s' if len(x['goals']) != 1 else ''} off because of it" if x["goals"] else ""
    return (f"{n} item{' waits' if n == 1 else 's wait'} on it{wait}" if n else "it holds only itself") + goals


def line(a: dict) -> str:
    """The first line: the biggest constraint in words, with its next step; or that nothing is stuck, when true."""
    rs = a["roots"]
    if a["stall"]:
        x = rs[0]
        return (f"Stalled: {x['says']}. {_held_words(x)[0].upper()}{_held_words(x)[1:]}. Next: {x['owner']} to "
                f"{x['action']}" + (f": `{x['command']}`" if x.get("command") else "") + ".")
    untraced = a["goals"]["untraced"]
    goals = (f" {len(untraced)} goal{'s' if len(untraced) != 1 else ''} off, not traced to an unfinished item: "
             + ", ".join(untraced[:5]) + ("…" if len(untraced) > 5 else "") + ".") if untraced else ""
    if rs and rs[0]["class"] == "unknown":
        n = sum(x["holds"] for x in rs if x["class"] == "unknown")
        return (f"No stall found, but what holds {n} item{'s' if n != 1 else ''} is not known: {rs[0]['says']}."
                + goals)
    if not rs:
        return "Nothing is stuck: no item is unfinished." + goals
    x = max(rs, key=lambda r: (r["waiting"], r["holds"]))
    return (f"Nothing is stuck: {a['unfinished']} unfinished item{'s are' if a['unfinished'] != 1 else ' is'} being "
            f"worked, queueing or held on purpose. The most held: {x['says']} ({_held_words(x)})." + goals)


def lines(a: dict) -> list[str]:
    """``ergostat held-up``: the first line, then each root ranked, with what it holds and its next step."""
    out = [a["line"], ""]
    for n, x in enumerate(a["roots"], 1):
        out.append(f"  {n:>2}. {x['class']:<7} {x['kind']}: {x['says']}")
        out.append(f"      holds {x['holds']}: {_held_words(x)}" + (f"; first {', '.join(x['first'])}" if x["first"] else ""))
        if x["goals"]:
            out.append(f"      goals off because of it: {', '.join(x['goals'])}")
        out.append(f"      next: {x['owner']}: {x['action']}" + (f"  $ {x['command']}" if x.get("command") else ""))
    if a["more"]:
        out.append(f"  ({a['more']} more root{'s' if a['more'] != 1 else ''}, each holding less)")
    if a["goals"]["untraced"]:
        out.append(f"  goals off, not traced to an unfinished item: {', '.join(a['goals']['untraced'])}")
    out += [f"  missing   {m}" for m in a["missing"]]
    return out


_LOCK = threading.Lock()
_LAST: dict = {}


def headline(p) -> dict:
    """The page's line (``/api/status``'s ``held_up``): worked out again when the record moves or after ``FRESH`` s;
    a failure is said, kept like an answer, and never fails the status."""
    k, seq, now = str(p.dir), p.events.last_seq(), time.time()
    with _LOCK:
        got = _LAST.get(k)
    if got is not None and got[0] == seq and now - got[1] < FRESH:
        return got[2]
    try:
        a = answer(p, now)
        said = {"line": a["line"], "stall": a["stall"], "nothing_stuck": a["nothing_stuck"]}
    except Exception as e:
        said = {"line": f"What holds the work up could not be worked out: {type(e).__name__}: {e}", "stall": None,
                "nothing_stuck": False}
    with _LOCK:
        _LAST[k] = (seq, now, said)
    return said
