"""``ergostat inbox``: everything waiting on a person, and the answer to any of it (SPEC §12o)."""

from __future__ import annotations

import os
import sys

from ..durations import human
from ..show import c, table
from .common import open_project, out_json


def register(sub, common) -> None:
    ib = sub.add_parser("inbox", parents=[common], help="Everything waiting on a person: held actions, requests, advised "
                        "commands, step tests, model changes (ID --approve | --deny | --done N answers one)",
                        description="The inbox (SPEC §12o). ergostat inbox [ID] [--approve | --deny | --done N] [--note "
                        "TEXT]; --stats: each class's record over the last week")
    ib.add_argument("name", nargs="?", metavar="ID", help="one entry (its id, or the start of its key)")
    ib.add_argument("--approve", action="store_true", help="approve it (an action, an advised command, a step test, a "
                    "change to the model; a held modelling request: back to the modelling loop)")
    ib.add_argument("--deny", action="store_true", help="deny it (a change or a step test: dismissed; a held modelling "
                    "request, with --note WHY: dismissed until its part changes)")
    ib.add_argument("--done", type=float, metavar="N", help="a person's request: how much they moved")
    ib.add_argument("--note", help="why")
    ib.add_argument("--as", dest="by", metavar="WHO", help="who answers (default: owner)")
    ib.add_argument("--stats", action="store_true", help="each class asked over the last week: asked, approved, denied, "
                    "median time to answer, and what could move up the ladder")
    ib.add_argument("--requests", action="store_true", help="the modelling requests waiting, held ones first, each with "
                    "why (--since: those raised or reopened in it); with --made, or in a block's run, the interventions "
                    "loop's controller instead: record suppression, make a modelling request for each recurring class, "
                    "resolve those remedied (prints how many were made)")
    ib.add_argument("--made", action="store_true", help="with --requests: run the interventions loop's controller pass")
    ib.add_argument("--invest", metavar="CLASS", help="mark a class's modelling request as being worked on: the rise its "
                    "fix needs is weighted down in the trend")
    ib.set_defaults(fn=cmd_inbox)


def cmd_inbox(args) -> int:
    from ..inbox import answer, entries, stats
    p = open_project(args)
    spec = getattr(p.model, "spec", None)
    if spec is None:
        print("the inbox is an ergostat.yaml's (ergostat convert writes it)", file=sys.stderr)
        return 2
    if args.requests or args.invest:
        return _loop(p, spec, args)
    verbs = [v for v, on in (("approve", args.approve), ("deny", args.deny), ("done", args.done is not None)) if on]
    if len(verbs) > 1 or (verbs and not args.name):
        print("one of --approve, --deny or --done N, with the entry's ID", file=sys.stderr)
        return 2
    if verbs:
        from ..inbox import entries
        from ..spec.triggers import own
        e = entries.find(p, spec, args.name)
        if e and e.get("block") and e["kind"] in ("advise", "breaker") and own(p.events, e["block"]):
            print(f"a run of {e['block']} answers for it to no one: its approvals and its breaker are the owner's",
                  file=sys.stderr)
            return 2
        try:
            got = answer.answer(p, spec, args.name, verbs[0], args.done, args.note, by=args.by or "owner")
        except answer.AnswerError as e:
            print(e, file=sys.stderr)
            return 2
        if args.json:
            return out_json(got)
        print(f"{got['id']}: {got['said']}")
        return 0
    if args.stats:
        rec = stats.by_class(p, spec)
        from ..inbox import interventions as iv
        n, m, reqs = getattr(spec, "notify", None), iv.measures(p, spec), iv.requests_now(p)
        today = len(stats.asked_today(p, spec))
        if args.json:
            return out_json({"classes": rec, "asked_today": today, "budget": n and n.asks_per_day, "interventions": m,
                             "requests": reqs})
        print(table(["CLASS", "ASKED", "APPROVED", "DENIED", "BY AN AGENT", "WAITING", "MEDIAN ANSWER"],
                    [[k, r["asked"], r["approved"], r["denied"], r["by_agent"], r["waiting"],
                      human(r["median"]) if r["median"] is not None else "-"] for k, r in rec.items()],
                    "nothing asked of a person this week"))
        print(c(f"\n{today} asked over the last day" + (f", budget {n.asks_per_day}" if n and n.asks_per_day else ""), "dim"))
        print(c(f"interventions (ISA-18.2): {m['per-day']:g} over the last day, trend {m['trend']:+.3g}/day per week over "
                f"{m['days']}d, standing {m['standing']}, chattering {m['chattering']}, blocked {m['blocked-hours']:.1f}h", "dim"))
        for o in m["top"][:5]:
            r = reqs.get(o["class"])
            print(c(f"  {o['class']}: {o['count']} ({o['share']:.0%}), {o['hours']:.1f}h blocked, {o['cause']}"
                    + (f"; request {r['id']} {r['state']}" if r else ""), "dim"))
        for r in rec.values():
            if r["suggest"]:
                print(c(r["suggest"], "dim"))
        return 0
    es = stats.listing(p, spec)
    if args.name:
        one = entries.find(p, spec, args.name)
        es = [e for e in es if one and e["id"] == one["id"]]
    if args.json:
        return out_json(es)
    if not es:
        print(c("nothing waits on you", "ok") if not args.name else f"nothing waiting is {args.name!r}")
        return 0 if not args.name else 2
    for e in es:
        print(f"{c(e['id'], 'accent')}  {e['summary']}  " + c(f"waiting {human(e['age'])}", "dim"))
        for line in (e["why"] and f"why: {e['why']}", e.get("run") and f"runs: {e['run']}", e["link"], e.get("record"), e.get("suggest")):
            if line:
                print(c(f"    {line}", "dim"))
        for w in e.get("workbench") or []:               # a drafted projection: opened in the workbench, to edit first
            print(c(f"    open {w['projection']} in the workbench: {w['link']}", "dim"))
        if e["verbs"]:                                   # a kind with none is not shown as answerable
            print(c(f"    {entries.command(e)}", "dim"))
    return 0


def _loop(p, spec, args) -> int:
    """``--requests``: one pass of the interventions loop's controller; ``--invest CLASS``: its request worked on."""
    from ..inbox import interventions as iv
    if args.invest:
        r = iv.requests_now(p).get(args.invest)
        if r is None or r["state"] not in iv.OPEN:
            print(f"no open modelling request for {args.invest!r} (ergostat inbox --stats lists them)", file=sys.stderr)
            return 2
        p.events.add(f"{iv.MODEL_REQUEST}.investing", item=r["id"], source=args.by or "owner", data={"note": args.note or ""})
        print(f"{r['id']}: investing (its class's rise is weighted down in the trend while it is worked on)")
        return 0
    if not (args.made or os.environ.get("ERGOSTAT_RUN")):     # a person asking: what waits, and why
        return _listed(p, spec, args)
    got = iv.requests(p, spec)
    if args.json:
        return out_json({k: v for k, v in got.items() if k != "measures"})
    for line in got["said"]:
        print(line, file=sys.stderr)
    print(got["made"])                                   # the block's one output: requests made
    return 0


def _listed(p, spec, args) -> int:
    """``--requests`` asked by a person: the modelling subsystem's requests waiting (held first, then open, then those
    a change answers), each with why, and the interventions loop's open ones."""
    import time

    from ..durations import parse_duration
    from ..inbox import interventions as iv
    from ..numbers import requests as rq
    now = time.time()
    cut = now - parse_duration(args.since, "--since") if getattr(args, "since", None) else None
    order = {"held": 0, "open": 1, "proposed": 2}
    mine = [r for r in rq.current(p, tuple(order)) if cut is None or float(r.get("since") or r.get("raised") or 0) >= cut]
    mine.sort(key=lambda r: (order[r["state"]], -float(r.get("since") or r.get("raised") or 0)))
    ivs = [r for r in iv.requests_now(p).values() if r["state"] in iv.OPEN
           and (cut is None or float((r.get("moves") or [{}])[-1].get("time") or 0) >= cut)]
    if args.json:
        return out_json({"modelling": mine, "interventions": ivs})
    if not mine and not ivs:
        print(c("no modelling request waits" + (f" from the last {args.since}" if cut else ""), "ok"))
        return 0
    for r in mine:
        g = r.get("group") or {}
        what = (f"{(r.get('unexplained') or {}).get('count', '?')} events of {g.get('type') or '?'}"
                + (f" from {g['source']}" if g.get("source") else "")) if r.get("source") == "events" \
            else f"{r.get('code')} on {r.get('about')}"
        tried = int((r.get("tried") or {}).get("ai") or 0)
        print(f"{c(r['id'], 'accent')}  {r['state']}  {r.get('source')}: {what}  "
              + c(f"since {human(now - float(r.get('since') or r.get('raised') or now))}"
                  + (f", tried {tried}" if tried else "") + (", the owner's" if r.get("owner") else ""), "dim"))
        why = r.get("why") or (f"its change {r['change']} waits" if r["state"] == "proposed" and r.get("change")
                               else r.get("error") and f"its last call failed: {r['error']}")
        if why:
            print(c(f"    why: {str(why)[:400]}", "dim"))
        if r["state"] == "held":
            print(c(f"    ergostat inbox request/{r['id']} --approve | --deny --note WHY", "dim"))
    for r in ivs:
        print(f"{c(r['id'], 'accent')}  {r['state']}  interventions: {r.get('class')}"
              + (f"  {c('why: ' + str(r['why']), 'dim')}" if r.get("why") else ""))
    held = sum(1 for r in mine if r["state"] == "held")
    print(c(f"\n{len(mine)} modelling requests waiting, {held} held" + (f"; {len(ivs)} of the interventions loop" if ivs
                                                                         else ""), "dim"))
    return 0
