"""Why an item is not done (SPEC §5a, *Why it is not done*): its state now and for how long against its kind's stays,
the cause followed to its root through what it waits on, who or what must act and how, and the evidence for each
claim. Read from the item index and the model only: what holds an item is whatever the model declares (its kinds'
relations and states, the blocks that take them, their pools, gates and budget), never anything named here.

A root is one of ``ROOTS``. What the record cannot tell is said (``missing``, or a root of kind ``unknown``), never
guessed; a cycle, a link to an id never recorded and a field that cannot be read are answers, not errors."""

from __future__ import annotations

import time

from ..precedence import _prec, starts, status
from ..precedence import held as _held  # (the name ``held`` is this package's module, held.py)
from ..spec.finished import finish_of
from ..spec.ir import DEAD

ROOTS = ("work", "person", "pool-full", "gate", "lease", "block", "closed", "parked", "nothing", "cycle", "missing",
         "unknown")
DEPTH = 64               # links followed down from the item asked
MOST = 200               # items looked at in one answer
BRANCHES = 8             # roots kept (the first is the answer's)
USUAL = 0.9              # a stay longer than this share of its kind's is unusual
FEWEST = 5               # stays needed before a stay is called usual or not


def ev(says: str, link: str | None = None, event: str | None = None, at: float | None = None) -> dict:
    """One piece of evidence: what it shows, and where to read it."""
    return {"says": says, "link": link, "event": event, "at": at}


def item_link(i: str) -> str:
    return f"/item/{i}"


def root(kind: str, item: str | None, says: str, owner: str, action: str, command: str | None = None,
         evidence: list | None = None, since: float | None = None, **more) -> dict:
    return {"kind": kind, "item": item, "says": says, "owner": owner, "action": action, "command": command,
            "since": since, "evidence": list(evidence or []), **more}


class Ctx:
    """What one answer reads, each thing once: the index, the model, the kinds' states, the engine."""

    def __init__(self, p, spec, ix, now: float, engine: dict | None):
        self.p, self.spec, self.ix, self.now = p, spec, ix, now
        self.kinds: dict = {}
        self._engine = engine
        self.seen = 0
        self.cache: dict | None = None      # (held-up, held.py) every item read once, its links read up front,
        self.links: dict | None = None      # and each block's answer worked out once for all its items
        self.memo: dict | None = None

    def info(self, kind: str | None) -> dict:
        if kind not in self.kinds:
            k = (self.spec.items or {}).get(kind or "")
            if k is None or not k.states:
                self.kinds[kind] = None
            else:
                fin = finish_of(self.spec, kind, self.ix.left(kind))
                working = [s for s in k.states[1:] if s not in fin["finished"] and s != DEAD and s not in fin["paused"]]
                self.kinds[kind] = {**fin, "working": working, "states": list(k.states)}
        return self.kinds[kind]

    def items(self, ids) -> dict:
        ids = [i for i in ids if isinstance(i, str)]
        self.seen += len(ids)
        if self.cache is not None:
            want = [i for i in dict.fromkeys(ids) if i not in self.cache]
            if want:
                with self.ix.lock:
                    got = {i.id: i for i in self.ix.items(None, ids=want, moves=False)}
                self.cache.update({i: got.get(i) for i in want})
            return {i: self.cache[i] for i in ids if self.cache[i] is not None}
        with self.ix.lock:
            return {i.id: i for i in self.ix.items(None, ids=ids, moves=False)} if ids else {}

    @property
    def engine(self) -> dict:
        if self._engine is None:
            from .blocks import engine_now
            self._engine = engine_now(self.p, self.now)
        return self._engine


def waits(ctx: Ctx, it) -> list[tuple[str, str, object]]:
    """(relation, id, the item or None) of each precedence target not finished (nor in a ``starts_at`` state)."""
    prec = _prec(ctx.spec, it.kind)
    if not prec:
        return []
    if ctx.links is not None:
        links = sorted((r, d) for r, d in ctx.links.get(it.id, ()) if r in prec)
    else:
        with ctx.ix.lock:
            links = sorted((r, d) for _, r, d in ctx.ix.links_from([it.id]) if r in prec)
    got = ctx.items([d for _, d in links])
    out = []
    for r, d in links:
        t = got.get(d)
        if t is not None:
            info = ctx.info(t.kind)
            if info is not None and (status(t, info, []) == "done" or starts(t, prec[r])):
                continue
        out.append((r, d, t))
    return out


def now_of(ctx: Ctx, it, info: dict | None) -> dict:
    """Its state, for how long, and whether that is unusual against its projection's stays in that state."""
    secs = max(0.0, ctx.now - it.entered) if it.entered else None
    out = {"state": it.state, "since": it.entered or None, "for": secs, "usual": None, "unusual": None}
    if info is None or it.state is None or secs is None:
        out["said"] = "its projection has no states, so it is never finished" if info is None else "it has no state"
        return out
    with ctx.ix.lock:
        stays = sorted(ctx.ix.stays(it.kind, 2000, info["finished"])[0].get(it.state) or [])
    if len(stays) < FEWEST:
        out["said"] = (f"{len(stays)} stay{'s' if len(stays) != 1 else ''} in {it.state} recorded for its projection: too few "
                       f"to say whether this is unusual")
        return out
    shorter = sum(1 for s in stays if s < secs)
    top = stays[min(len(stays) - 1, int(USUAL * len(stays)))]
    out["usual"] = {"median": stays[len(stays) // 2], "p90": top, "stays": len(stays), "longer_than": shorter / len(stays)}
    out["unusual"] = secs > top
    out["said"] = (f"longer than {round(100 * shorter / len(stays))}% of the {len(stays)} stays its projection made in "
                   f"{it.state} (median {_dur(stays[len(stays) // 2])})" + (": unusual" if out["unusual"] else ""))
    return out


def _dur(s: float | None) -> str:
    from ..durations import human
    return "unknown" if s is None else human(s)


def here(ctx: Ctx, it, iid: str) -> tuple[list, dict | None]:
    """What holds this item: (the targets it waits on, None), or ([], its root)."""
    if it is None:
        return [], root("missing", iid, f"{iid} is named as what it waits on, but nothing is recorded about it, so it is "
                        "not known to be finished", "the owner", f"record {iid}, or remove the link to it",
                        evidence=[ev("no event about this id in the item index", item_link(iid))])
    info = ctx.info(it.kind)
    if info is None:
        return [], root("unknown", iid, f"{iid} has no projection with states ({it.kind or 'no projection matches its id'}), so it "
                        "is never finished", "the owner", "declare its projection's states in the model, or remove the link",
                        evidence=[ev("its projection in the model", item_link(iid))])
    if it.state == DEAD:
        return [], _parked(it, "a dead letter: its attempts ran out", f"ergostat lease {iid} --redrive")
    if it.state in info["paused"]:
        return [], _parked(it, f"paused in {it.state}: continued by hand", None)
    if _held(it.fields):
        from .blocks import holder
        return [], holder(ctx, it)
    if not isinstance(it.fields.get("lease", {}), dict):
        return [], root("unknown", iid, "its lease field cannot be read (not an object)", "the owner",
                        "look at its lease field's history", evidence=[ev("its fields", item_link(iid))])
    w = waits(ctx, it)
    if w:
        return w, None
    from .blocks import taken
    return [], taken(ctx, it, info)


def _parked(it, says: str, command: str | None) -> dict:
    last = it.latest or "its latest event"
    return root("parked", it.id, f"{it.id} is {says}", "the owner",
                "continue it, or remove what waits on it" if command is None else "redrive it, or remove what waits on it",
                command, since=it.entered, dead=it.state == DEAD,
                evidence=[ev(f"moved to {it.state} by {last}", item_link(it.id), at=it.entered)])


def walk(ctx: Ctx, first, iid: str) -> tuple[list[dict], list[str]]:
    """The roots, each with its path from the item asked (depth first, in each item's links' order), and what was cut."""
    roots, cut = [], []
    stack = [(iid, first, [iid])]
    while stack and len(roots) < BRANCHES:
        cur, it, path = stack.pop()
        if ctx.seen > MOST:
            cut.append(f"stopped after {MOST} items: what lies past them is not followed")
            break
        try:
            deps, r = here(ctx, it, cur)
        except Exception as e:                       # an unreadable field: said, never raised
            deps, r = [], root("unknown", cur, f"{cur} could not be read: {type(e).__name__}: {e}", "the owner",
                               "look at its fields and its events", evidence=[ev("its record", item_link(cur))])
        if r is not None:
            roots.append({**r, "path": path})
            continue
        if len(path) > DEPTH:
            cut.append(f"stopped {DEPTH} links down, at {cur}")
            continue
        for rel, d, t in reversed(deps):
            if d in path:
                loop = path[path.index(d):] + [d]
                roots.append({**root("cycle", d, "these wait on one another, so none can ever be ready: "
                                     + " → ".join(loop), "the owner", "remove one link of the cycle",
                                     f"ergostat event --add ITEM.changed --item {cur} --data '{{\"{rel}\": {{\"remove\": \"{d}\"}}}}'",
                                     evidence=[ev(f"{a} {rel} …", item_link(a)) for a in loop[:-1]]), "path": path + [d]})
                continue
            stack.append((d, t, path + [d]))
    return roots, cut


def answer(p, iid: str, now: float | None = None, engine: dict | None = None) -> dict:
    """The answer for one item (``--json``, ``/api/why``, MCP's ``why``)."""
    from ..spec.itemindex import index_for
    from .words import summary
    now = time.time() if now is None else now
    spec = getattr(p.model, "spec", None)
    out = {"item": iid, "known": False, "done": False, "now": None, "chain": [], "root": None, "roots": [],
           "next": None, "evidence": [], "missing": [], "at": now}
    ix = index_for(p.events, spec, False) if spec is not None else None
    if ix is None:
        out["missing"].append("this record keeps no item index, so its items' states cannot be read")
        out["summary"] = summary(out)
        return out
    ctx = Ctx(p, spec, ix, now, engine)
    it = ctx.items([iid]).get(iid)
    if it is None:
        out["missing"].append(f"nothing is recorded about {iid}")
        out["summary"] = summary(out)
        return out
    info = ctx.info(it.kind)
    out.update(known=True, kind=it.kind, now=now_of(ctx, it, info))
    if info is not None and status(it, info, []) == "done":
        out["done"] = True
        out["summary"] = summary(out)
        return out
    if info is not None and info["lives_on"]:            # (a pool is held, never done: nothing to follow)
        out["missing"].append(f"its projection, {it.kind}, has no finished state (it lives on), so it is never done")
        out["summary"] = summary(out)
        return out
    roots, cut = walk(ctx, it, iid)
    out["missing"] += cut
    from .within import place
    try:                                             # (what holds it as one of many: a batch of the gaps it tests)
        out["place"] = place(ctx, it)
    except Exception as e:                           # an unreadable holder: said, never raised
        out["place"] = None
        out["missing"].append(f"which items hold it could not be read: {type(e).__name__}: {e}")
    out["roots"] = roots
    if roots:
        r = out["root"] = roots[0]
        got = ctx.items(r["path"])
        out["chain"] = [{"item": x, "state": getattr(got.get(x), "state", None),
                         "projection": getattr(got.get(x), "kind", None)} for x in r["path"]]
        out["next"] = {"owner": r["owner"], "action": r["action"], "command": r["command"]}
        out["evidence"] = [e for x in roots for e in x["evidence"]]
        if r["kind"] == "unknown":
            out["missing"].append(r["says"])
        elif r.get("missing"):                       # (a root known, with a part of it the record cannot tell)
            out["missing"].append(r["missing"])
    out["summary"] = summary(out)
    return out
