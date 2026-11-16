"""The record: ``ergostat event``, ``ergostat item`` and ``ergostat residual``."""

from __future__ import annotations

import json
import os
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
    if args.add:
        return add_event(p, args)
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
    from ..spec import items as its
    p = open_project(args)
    spec = getattr(p.model, "spec", None)
    if not args.name:
        got = its.listing(p.events, spec, kind=args.kind, state=args.state)
        if args.json:
            return out_json(got)
        for k in got["kinds"]:
            counts = " · ".join(f"{s} {k['counts'].get(s, 0)}" for s in k["states"]) or f"{sum(k['counts'].values())} items"
            print(f"{c(k['name'], 'accent')} {c(k['id'], 'dim')}  {counts}")
        if got["kinds"]:
            print()
        show = sorted({f for k in got["kinds"] for f in k["show"] if args.kind in (None, k["name"])})
        rows = [[i["id"], i["kind"] or "-", i["state"] or "-", *[str(i["fields"].get(f, ""))[:30] for f in show],
                 str(i["events"]), i["latest"], ago(i["entered"] or i["first"]), ago(i["last"])] for i in got["items"][:args.n]]
        print(table(["ITEM", "KIND", "STATE", *[f.upper() for f in show], "EVENTS", "LATEST", "IN STATE SINCE", "LAST"], rows,
                    "no items yet: an item is what events with an id like ticket/12 are about "
                    "(a block prints {\"event\": \"ticket.opened\", \"item\": \"ticket/12\"})"))
        if got["total"] > args.n:
            print(c(f"{got['total'] - args.n} more (-n)", "dim"))
        return 0
    d = its.detail(p.events, spec, args.name)
    if d is None:
        print(f"no item {args.name!r}", file=sys.stderr)
        return 2
    if args.json:
        return out_json(d)
    kind = f" · {d['kind']}" if d["kind"] else " · no kind (no items: entry matches it)"
    state = f" · {c(d['state'], 'accent')} since {ago(d['entered'])}" if d["state"] else ""
    print(f"{c('item', 'dim')} {args.name}{kind}{state} · {d['events']} events, first {ago(d['first'])}")
    for k, v in sorted(d["fields"].items()):
        print(f"  {k:<14} {json.dumps(v, default=str)}")
    if d["moves"]:
        print()
        for mv in d["moves"]:
            print(f"  {c(time.strftime('%H:%M:%S', time.localtime(mv['time'])), 'dim')}  {mv['from'] or '-'} → {mv['to']}"
                  f"  {c(mv['type'], 'dim')}")
    print()
    for e in d["record"][-args.n:]:
        print(event_line(e))
    return 0


def add_event(p, args) -> int:
    from ..runner import OWN_TYPES, TYPE_NAME
    t = args.add
    if not TYPE_NAME.match(t) or t.startswith((*OWN_TYPES, "block.", "person.")):
        print(f"{t!r}: an event type is lowercase words joined by dots (ticket.opened), and not ergostat's own",
              file=sys.stderr)
        return 2
    try:
        data = json.loads(args.data) if args.data else {}
    except ValueError as e:
        print(f"--data: not JSON ({e})", file=sys.stderr)
        return 2
    if not isinstance(data, dict):
        print("--data: a JSON object ({\"title\": \"...\"})", file=sys.stderr)
        return 2
    run = os.environ.get("ERGOSTAT_RUN") or None         # recorded during a run: caused by it
    ev = p.events.add(t, item=args.item, source=args.by or "user", data=data, causedby=run)
    print(json.dumps(ev, default=str) if args.json else event_line(ev))
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


RECORD = ("events.db", "events.db-shm", "events.db-wal", "measurements.db", "measurements.db-shm", "measurements.db-wal",
          "run.log")


def cmd_reset(args) -> int:
    """``ergostat reset``: forget this project's record (every event, item and measurement, and the
    agents' logs) and start from nothing. Only what ergostat wrote there is deleted, by name; the
    project's own files (and anything its programs keep, like an example's run/) are not touched."""
    import shutil

    from ..runner import running_pid
    p = open_project(args)
    if running_pid(p):
        print("it is running: stop it first (ergostat run --stop, or Ctrl-C), then reset", file=sys.stderr)
        return 2
    gone = [p.dir / n for n in RECORD if (p.dir / n).exists()]
    logs = p.dir / "logs"
    if not args.yes:
        what = ", ".join(x.name for x in gone) + (", logs/" if logs.is_dir() else "")
        print(f"this forgets {p.model.name}'s record in {p.dir}: {what or 'nothing is there'}.\n"
              f"ergostat reset --yes to do it")
        return 0
    for f in gone:
        f.unlink()
    if logs.is_dir():
        shutil.rmtree(logs)
    print(f"forgot {p.model.name}'s record ({p.dir}); the next run starts from nothing")
    return 0

