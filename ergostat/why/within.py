"""Where an unfinished item is held by others of the model's items (SPEC §5a, *Why it is not done*): the unfinished items
that name it in a relation of theirs (a batch naming the gaps it tests), each with its state and its kind's first
shown fields; when none names it, how many unfinished items of those kinds there are, ahead of it. The relations are
the model's own: those that declare an inverse and name its kind, never a precedence, a group or a remote's. Nothing
of any model is named here."""

from __future__ import annotations

from ..precedence import status
from ..process import LEASED

SHOWN = 3            # a holder's shown fields said, at most
NAMED = 5            # holders named, at most


def relating(spec, kind: str | None) -> list[tuple[str, str]]:
    """(the kind, its relation) of each relation that may name items of ``kind``."""
    return [(kn, r.name) for kn, k in (spec.items or {}).items() for r in k.relations.values()
            if r.inverse and not r.precedence and not r.group and not r.remote and kind in r.kinds]


def said(spec, h) -> dict:
    """One holder: its id, kind, state, and the first SHOWN of its kind's `show:` fields that hold a value."""
    shown = {}
    for f in spec.items[h.kind].show:
        v = h.fields.get(f)
        if len(shown) < SHOWN and isinstance(v, str | int | float) and not isinstance(v, bool) and v != "":
            shown[f] = v if not isinstance(v, str) else v[:60]
    return {"item": h.id, "kind": h.kind, "state": h.state, "shown": shown}


def unfinished(ctx, kind: str) -> list:
    info = ctx.info(kind)
    if info is None:
        return []
    with ctx.ix.lock:
        return ctx.ix.items(kind, [s for s in info["states"] if s not in info["finished"]], moves=False)


def waits_in(ctx, its: list) -> tuple[dict, dict]:
    """({id: its state as its work has it}, {id: the states it has left}). The first is SPEC §9.5's: its own, but for
    one held by a run (``leased``), which waits in the state it was taken from, read from its last move into the lease
    (that state unread: ``leased`` itself). The second is every ``from`` of its moves: an item the work has taken on
    (approved, leased, then queued) has left the state the one behind it waits in. Moves unread: none left."""
    ids = [i.id for i in its]
    with ctx.ix.lock:
        moved = {i.id: i.moves or [] for i in ctx.ix.items(None, ids=ids)} if ids else {}
    out = {i.id: i.state for i in its}
    for i in its:
        if i.state == LEASED:
            took = [m["from"] for m in moved.get(i.id, []) if m["to"] == LEASED and m["from"] not in (LEASED, None)]
            out[i.id] = took[-1] if took else LEASED
    left = {iid: {m["from"] for m in moves if m.get("from")} for iid, moves in moved.items()}
    return out, left


def place(ctx, it) -> dict | None:
    """{"in": the unfinished items naming it, "ahead": {kind: {n, latest}}}, or None when no relation of the model may
    name its kind. Ahead of it: the unfinished items of a relating kind that name an item of its kind waiting in its
    state (a leased one counted in the state it was taken from), or one that has left its state (an approved gap
    behind the batch testing a gap the queue took from approved and moved on to queued), the latest first."""
    rels = relating(ctx.spec, it.kind)
    if not rels:
        return None
    with ctx.ix.lock:
        naming = [(a, r) for a, r, _ in ctx.ix.links_to([it.id])]
    got = ctx.items([a for a, _ in naming])
    held = []
    for a, r in naming:
        h = got.get(a)
        info = ctx.info(h.kind) if h is not None else None
        if h is None or (h.kind, r) not in rels or info is None or status(h, info, []) == "done":
            continue
        held.append(said(ctx.spec, h))
    if held:
        return {"in": held[:NAMED], "ahead": {}}
    ahead = {}
    for kind in dict.fromkeys(k for k, _ in rels):
        open_ = unfinished(ctx, kind)
        mine = {r for k, r in rels if k == kind}
        with ctx.ix.lock:
            links = [(a, d) for a, r, d in ctx.ix.links_from([h.id for h in open_]) if r in mine]
        named = ctx.items([d for _, d in links])
        at, left = waits_in(ctx, [it, *named.values()])
        like = {a for a, d in links if d in named and named[d].kind == it.kind
                and (at[d] == at[it.id] or at[it.id] in left.get(d, ()))}
        alike = [h for h in open_ if h.id in like]
        if alike:
            ahead[kind] = {"n": len(alike), "latest": said(ctx.spec, alike[0])}
    return {"in": [], "ahead": ahead}


def words(p: dict | None) -> str:
    """The sentence the summary carries: what holds it, or how many are ahead of it."""
    if not p:
        return ""
    one = lambda h: f"{h['item']} ({h['state']}" + "".join(f"; {k} {v}" for k, v in h["shown"].items()) + ")"  # noqa: E731
    if p["in"]:
        return " It is in " + ", ".join(one(h) for h in p["in"]) + "."
    if not p["ahead"]:
        return ""
    return " It is in none yet; ahead of it: " + "; ".join(
        f"{a['n']} unfinished {k} item{'s' if a['n'] != 1 else ''}, the latest {one(a['latest'])}"
        for k, a in p["ahead"].items()) + "."
