"""``ergostat message TEXT``: the owner's words to the work in flight; ``ergostat messages``: what became of them
(SPEC §12h)."""

from __future__ import annotations

import time

from ..show import c, table
from .common import open_project, out_json


def _spec(p):
    spec = getattr(p.model, "spec", None)
    if spec is None:
        print("the model is an ergostat.toml: messages are routed to the work of an ergostat.yaml")
    return spec


def _to(m: dict) -> str:
    to = m.get("routed_to") or []
    names = list(dict.fromkeys((t.get("item") or t.get("part") or t.get("block") or "") +
                               (f" (run {str(t['run'])[:8]})" if t.get("run") else "") for t in to))
    return ", ".join(names)


def show_one(m: dict) -> None:
    print(f"{m['id']}  {c(m['state'], 'bold')}\n  text     {m.get('text')}\n  by       {m.get('by')}, "
          f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(m.get('sent') or m['time']))} (via {m.get('via')})")
    if m.get("about"):
        print(f"  about    {', '.join(m['about'])}")
    print(f"  matched  {m.get('matched') or '-'}{(': ' + m['why']) if m.get('why') else ''}")
    if m.get("routed_to"):
        print("  routed to")
        for t in m["routed_to"]:
            print("    " + ", ".join(f"{k} {v}" for k, v in t.items() if k != "session_id"))
    for d in m.get("deliveries") or []:
        print(f"  delivered {d.get('how')}: " + ", ".join(f"{k} {v}" for k, v in d.items() if k not in ("how", "at",
                                                                                                         "session_id")))
    if m.get("queued"):
        print(f"  queued   for {m['queued'].get('session')}: {m['queued'].get('why')}")
    if m.get("missed"):
        print(f"  missed   {m['missed'].get('item')} finished ({m['missed'].get('state')}) before it was delivered")
    for a in m.get("answers") or []:
        print(f"  answered by {a.get('session') or a.get('by')}: {a.get('says')}")
    print(f"  outcome  {m.get('outcome')}")


def cmd_message(args) -> int:
    """The owner's words, verbatim, routed at once to the work they concern (``--about``, the ids and names in them,
    or the classifier), and delivered to it: a running session's next turn, a run's context, a follow-up."""
    from ..messages import record, route
    p = open_project(args)
    spec = _spec(p)
    if spec is None:
        return 2
    text = " ".join(args.text or [])
    try:
        m = route.send(p, spec, text, by=args.by or "owner", about=args.about, via="cli", reopen=args.reopen)
    except record.MessageError as e:
        print(str(e))
        return 2
    if args.json:
        return out_json(m)
    print(f"{m['id']}: {m.get('outcome')}")
    if m["state"] == "unrouted":
        print(c(f"  route it: ergostat messages {record.short(m['id'])} --about ITEM|PART", "dim"))
    return 0


def cmd_messages(args) -> int:
    """The latest messages and what became of each; ``NAME``: one, with its routing and deliveries; ``NAME --about X``:
    route it by hand (an unrouted one, or again)."""
    from ..messages import measures, record, route
    p = open_project(args)
    spec = _spec(p)
    if spec is None:
        return 2
    if args.name:
        m = record.get(p, args.name)
        if m is None:
            print(f"no message {args.name!r} (ergostat messages lists them)")
            return 2
        if args.about or args.reopen:
            m = route.route(p, spec, m["id"], about=args.about or m.get("about") or [], by=args.by or "owner",
                            finished_policy="reopen" if args.reopen else None)
        if args.json:
            return out_json(m)
        show_one(m)
        return 0
    ms = sorted(record.stored(p).values(), key=lambda m: -m["time"])[:args.n]
    if args.json:
        return out_json({"messages": ms, "measures": measures.counts(p)})
    rows = [[record.short(m["id"]), m["state"], time.strftime("%m-%d %H:%M", time.localtime(m["time"])), m.get("by") or "",
             (m.get("text") or "")[:50], m.get("matched") or "", _to(m)[:50]] for m in ms]
    print(table(["MESSAGE", "STATE", "SENT", "BY", "TEXT", "MATCHED", "ROUTED TO"], rows, "no messages yet"))
    n = measures.counts(p)
    print(c(f"\nunrouted {n['unrouted']:g} · awaiting delivery {n['awaiting']:g} · over the last week: received "
            f"{n['received']:g}, delivered {n['delivered']:g}, answered {n['answered']:g}, missed {n['missed']:g}", "dim"))
    print(c("ergostat message \"TEXT\" [--about ITEM|PART]: send one · ergostat messages ID: one · "
            "ergostat messages ID --about X: route it by hand", "dim"))
    return 0


def cmd_session(args) -> int:
    import os

    from .. import session
    if getattr(args, "C", None):
        os.chdir(args.C)
    return session.main(args.rest)
