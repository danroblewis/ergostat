"""The record: ``ergostat event``, ``ergostat item`` and ``ergostat residual``."""

from __future__ import annotations

import json
import sys
import time

from ..durations import human, parse_duration
from ..show import ago, c, table
from ..state import fmt
from .common import open_project, out_json, parts_of, snap_of


def event_line(e: dict) -> str:
    t = time.strftime("%H:%M:%S", time.localtime(e["time"]))
    data = json.dumps(e["data"], separators=(",", ":")) if e["data"] else ""
    src = e.get("source") or "-"
    return f"{c(t, 'dim')}  {e['type']:<20} {e.get('item') or '-':<20} {c(src, 'accent')}{' ' * max(1, 14 - len(src))}{data[:100]}"

RUNS = ("agent.started", "agent.ran")    # the bookkeeping of each run: --runs shows it


def cmd_event(args) -> int:
    p = open_project(args)
    if args.name:
        e = p.events.get(args.name)
        if e is None:
            print(f"no event {args.name!r}", file=sys.stderr)
            return 2
        caused = p.events.caused_by(e["id"])
        if args.json:
            return out_json({**e, "caused": caused})
        print(json.dumps(e, indent=2, default=str))
        if e.get("causedby") and (up := p.events.get(e["causedby"])):
            print(c("caused by", "dim"))
            print("  " + event_line(up))
        if caused:
            print(c("caused", "dim"))
            for x in caused:
                print("  " + event_line(x))
        return 0
    if args.follow:
        sys.stdout.reconfigure(line_buffering=True)        # each line as it comes, into a pipe too
    since = time.time() - parse_duration(args.since, "--since") if args.since else None
    skip = () if args.runs or args.type else RUNS
    evs = p.events.query(n=args.n, type=args.type, item=args.item, source=args.source, since=since, skip=skip)
    if args.json and not args.follow:
        return out_json(evs)
    for e in evs:
        print(json.dumps(e, default=str) if args.json else event_line(e))
    if not args.follow:
        return 0
    seq = evs[-1]["seq"] if evs else p.events.last_seq()
    try:
        while True:
            for e in p.events.query(n=None, type=args.type, item=args.item, source=args.source, after_seq=seq, skip=skip):
                seq = e["seq"]
                print(json.dumps(e, default=str) if args.json else event_line(e), flush=True)
            time.sleep(0.5)
    except KeyboardInterrupt:
        return 0

def cmd_item(args) -> int:
    p = open_project(args)
    if not args.name:
        since = time.time() - parse_duration(args.since, "--since") if args.since else None
        its = p.events.items(since, own=args.all)
        if args.json:
            return out_json(its)
        print(table(["ITEM", "EVENTS", "LATEST", "LAST", "FIRST"],
                    [[i["item"], str(i["n"]), i["latest"], ago(i["last"]), ago(i["first"])] for i in its[:args.n]],
                    "no items yet: an item is what your agents' events are about (\"item\": ...)"
                    + ("" if args.all else "; --all also lists the parts and agents")))
        return 0
    evs = p.events.query(n=None, item=args.name)
    if not evs:
        print(f"no item {args.name!r}", file=sys.stderr)
        return 2
    fields: dict = {}
    for e in evs:
        fields.update(e["data"])
    if args.json:
        return out_json({"item": args.name, "fields": fields, "events": evs})
    print(f"{c('item', 'dim')} {args.name} · {len(evs)} events · latest {evs[-1]['type']} {ago(evs[-1]['time'])}")
    for k, v in sorted(fields.items()):
        print(f"  {k:<14} {json.dumps(v, default=str)[:90]}")
    print()
    for e in evs[-args.n:]:
        print(event_line(e))
    return 0

def cmd_residual(args) -> int:
    p = open_project(args)
    snap = snap_of(p, args)
    parts = parts_of(args, p.model)
    res = {k: v for k, v in snap["residuals"].items() if k in parts and (not args.name or k == args.name)}
    if args.json:
        return out_json(res)
    rows = []
    for k, r in res.items():
        verdict = (c("unexplained", "warn") if r["significant"] else
                   (f"estimated as {', '.join(r['absorbed_by'])}" if r["absorbed_by"] else c("explained", "ok")))
        rows.append([k, fmt(r["change"]), fmt(r["explained"]), fmt(r["unexplained"]), verdict])
    print(table(["STOCK", "CHANGED", "EXPLAINED", "UNEXPLAINED", ""], rows,
                "no stock has two readings in this window yet"))
    span = min(snap["window"], snap["recorded"]) if snap.get("recorded") else snap["window"]
    covered = (f"the {human(span)} recorded" if snap.get("recorded") and snap["recorded"] < snap["window"] - 1 else human(snap["window"]))
    print(c(f"\nover {covered}: what each stock's readings did, against what its known flows explain", "dim"))
    return 0
