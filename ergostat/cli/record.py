"""The record: ``ergostat event``, ``ergostat item`` and ``ergostat residual``."""

from __future__ import annotations

import json
import os
import sys
import time

from ..durations import human, parse_duration
from ..show import ago, c, table
from ..state import fmt
from .common import at_of, open_project, out_json, parts_of, snap_of


def event_line(e: dict) -> str:
    t = time.strftime("%H:%M:%S", time.localtime(e["time"]))
    said = {"patch": e["patch"]} if e.get("patch") is not None else {"set": e["set"]} if e.get("set") is not None else e["data"]
    data = json.dumps(said, separators=(",", ":")) if said else ""
    src = e.get("source") or "-"
    return f"{c(t, 'dim')}  {e['type']:<20} {e.get('item') or '-':<20} {c(src, 'accent')}{' ' * max(1, 14 - len(src))}{data[:100]}"

RUNS = ("agent.started", "agent.ran")    # the bookkeeping of each run: --runs shows it


def cmd_event(args) -> int:
    if args.add:
        return add_event(None, args)
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
    if not args.type and not args.item:                    # a transcript's lines: asked for by type or by item
        skip = (*skip, "claude.*")
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
    from ..spec.item_sets import BadSet
    search = getattr(args, "search", None)
    if search is not None and (args.name or getattr(args, "at", None)):
        print("ergostat item --search lists the items as they are now: leave out NAME and --at", file=sys.stderr)
        return 2
    if args.near is not None or args.path_to is not None or args.about_item:
        return _item_graph(args)
    if args.name and args.json and not getattr(args, "at", None) and getattr(args, "history", None) is None:
        from ..calls.client import Refused
        from . import fast
        try:                                             # the running engine reads it, when one listens (calls/)
            got = fast.call(args, "item", id=args.name)
        except Refused as e:
            print(str(e), file=sys.stderr)
            return 2
        if got is not None:
            return out_json(got["item"])
    p = open_project(args)
    spec = getattr(p.model, "spec", None)
    if not args.name:
        args.n = max(1, min(args.n, its.LISTED))
        try:
            got = its.listing(p.events, spec, kind=args.kind, state=args.state, search=search)
        except BadSet as e:
            print(str(e), file=sys.stderr)
            return 2
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
                    f"no item's fields contain every word of {search!r}" if search is not None else
                    "no items yet: an item is what events with an id like ticket/12 are about "
                    "(a block prints {\"event\": \"ticket.opened\", \"item\": \"ticket/12\"})"))
        if got["total"] > args.n:
            print(c(f"{got['total'] - args.n} more (-n)", "dim"))
        return 0
    at = at_of(args) if getattr(args, "at", None) else None     # as it stood then: its fields, its history to then
    hist = getattr(args, "history", None)
    d = its.detail(p.events, spec, args.name, until=at, history=None if hist is not None else its.HISTORY_SHOWN)
    if d is None:
        print(f"no item {args.name!r}" + (" then" if at else ""), file=sys.stderr)
        return 2
    if hist is not None:
        if args.json:
            return out_json({"id": d["id"], "fields": d["fields"], "history": {f: cs for f, cs in d["history"].items()
                                                                               if not hist or f == hist},
                             "refused": d["refused"]})
        if hist and hist not in d["history"]:
            print(f"{args.name}: no changes to {hist!r} (its fields: {', '.join(sorted(d['fields'])) or 'none'})", file=sys.stderr)
            return 2
        print("\n".join(history_lines(d, hist or None)) or "no changes: its events carry nothing")
        return 0
    if args.json:
        return out_json(d)
    kind = f" · {d['kind']}" if d["kind"] else " · no kind (no items: entry matches it)"
    state = f" · {c(d['state'], 'accent')} since {ago(d['entered'])}" if d["state"] else ""
    print(f"{c('item', 'dim')} {args.name}{kind}{state} · {d['events']} events, first {ago(d['first'])}")
    for k, v in sorted(d["fields"].items()):
        n = d["changes"].get(k, 0)
        print(f"  {k:<14} {_short(v, 200)}" + (c(f"  {n} changes (--history {k})", "dim") if n > 1 else ""))
    for r in d["refused"]:
        print(c(f"  refused {time.strftime('%H:%M:%S', time.localtime(r['time']))} {r['type']}: {r['why']}", "warn"))
    if d["moves"]:
        print()
        for mv in d["moves"]:
            print(f"  {c(time.strftime('%H:%M:%S', time.localtime(mv['time'])), 'dim')}  {mv['from'] or '-'} → {mv['to']}"
                  f"  {c(mv['type'], 'dim')}")
    print()
    for e in d["record"][-args.n:]:
        print(event_line(e))
    return 0


def _item_graph(args) -> int:
    """``item ID --near [N]``, ``item A --path B``, ``item ID --about`` (``spec/itemgraph.py``), as the record is now."""
    from ..spec import itemgraph as ig
    asked = sum(x not in (None, False) for x in (args.near, args.path_to, args.about_item))
    if getattr(args, "at", None) or getattr(args, "history", None) is not None or not args.name or asked > 1:
        print("--near, --path, --about: one, of an item, as the record is now (never with --at or --history)", file=sys.stderr)
        return 2
    p = open_project(args)
    ev, spec, n = p.events, getattr(p.model, "spec", None), args.name
    try:
        got = ig.near(ev, spec, n, args.near) if args.near is not None else \
            ig.path(ev, spec, n, args.path_to) if args.path_to is not None else ig.about(ev, spec, n)
    except (ig.Unknown, ig.Bad) as e:
        print(f"{n}: {e.args[0]}", file=sys.stderr)
        return 2
    if args.json:
        return out_json(got)
    for x in got.get("steps") or got.get("items") or []:     # from relation to, or id distance (via) / how relation-or-field
        print("  " + "  ".join(" ".join(map(str, v.values())) if isinstance(v, dict) else str(v) for v in x.values()))
    print(c(got.get("says") or f"{len(got['items'])} items" + (f", capped at {got['cap']}" if got["capped"] else ""),
            "warn" if got["capped"] else "dim"))
    return 0


def add_event(p, args) -> int:
    from ..runner import OWN_TYPES, TYPE_NAME
    t = args.add
    if not TYPE_NAME.match(t) or t.startswith((*OWN_TYPES, "block.", "person.")):
        print(f"{t!r}: an event type is lowercase words joined by dots (ticket.opened), and not ergostat's own",
              file=sys.stderr)
        return 2
    got = {}
    for flag, raw in (("--data", args.data), ("--patch", getattr(args, "patch", None)), ("--set", getattr(args, "set_", None))):
        if raw:
            try:
                got[flag] = json.loads(raw)
            except ValueError as e:
                print(f"{flag}: not JSON ({e})", file=sys.stderr)
                return 2
    data = got.get("--data", {})
    if not isinstance(data, dict):
        print("--data: a JSON object ({\"title\": \"...\"})", file=sys.stderr)
        return 2
    from ..store import ChangesetError
    run = os.environ.get("ERGOSTAT_RUN") or None         # recorded during a run: caused by it
    one = {"event": t, "item": args.item, "data": data, **{k: got[f] for k, f in (("patch", "--patch"), ("set", "--set"))
                                                             if f in got}}
    from ..calls.client import Refused
    from . import fast
    try:                                                 # the running engine records it, when one listens (calls/)
        sent = fast.call(args, "event", events=[one], source=args.by or "user", causedby=run)
    except Refused as e:
        print(str(e), file=sys.stderr)
        return e.code
    if sent is not None:
        ev = (sent.get("events") or [{}])[0]
        print(json.dumps(ev, default=str) if args.json else event_line(ev))
        why = (sent.get("unchanged") or {}).get(ev.get("id"))
        if why:
            print(f"recorded, but it changed nothing: {why}", file=sys.stderr)
            return 1
        return 0
    p = p or open_project(args)
    from ..spec.triggers import block_of, undeclared
    why = run and undeclared(getattr(p.model, "spec", None), block_of(p.events, run), [t])
    if why:                                              # a run started by events says only what it declares (SPEC §9.3)
        print(f"not recorded: {why}", file=sys.stderr)
        return 2
    try:
        ev = p.events.add(t, item=args.item, source=args.by or "user", data=data, causedby=run, patch=got.get("--patch"),
                          set=got.get("--set"))
    except ChangesetError as e:
        print(f"not recorded: {e}", file=sys.stderr)
        return 2
    print(json.dumps(ev, default=str) if args.json else event_line(ev))
    spec = getattr(p.model, "spec", None)
    if ev["item"] and "/" in ev["item"] and spec is not None and (ev.get("patch") is not None or ev.get("set") is not None
                                                                   or getattr(its_kind(spec, ev["item"]), "fold", None)):
        from ..spec import items as its
        it = its.one(p.events, spec, ev["item"])
        why = next((r["why"] for r in (it.refused if it else []) if r["event"] == ev["id"]), None)
        if why:                                          # recorded, as it happened; its item is as it was
            print(f"recorded, but it changed nothing: {why}", file=sys.stderr)
            return 1
    return 0


def its_kind(spec, id: str):
    from ..spec import items as its
    return its.kind_of(spec, id)


def _short(v, n: int = 60) -> str:
    s = "–" if v is None else json.dumps(v, default=str)
    return s if len(s) <= n else s[:n - 1] + "…"


def history_lines(d: dict, only: str | None) -> list[str]:
    out = []
    fields = [only] if only else sorted(d["history"], key=lambda f: (f == "", f))
    for f in fields:
        cs = d["history"].get(f) or []
        out.append(f"{c(f or '(the whole item)', 'accent')}  now {_short(d['fields'].get(f)) if f else ''}"
                   f"  {c(f'{len(cs)} change' + ('s' if len(cs) != 1 else ''), 'dim')}")
        for ch in cs:
            t = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ch["time"]))
            how = ch["op"] + (f" ({ch['rule']})" if ch.get("rule") not in (None, "replace") else "") + \
                (f" by {ch['form']}" if ch["form"] != "data" else "")
            what = ch["why"] if ch["op"] == "refused" else f"{_short(ch['before'], 40)} → {_short(ch['after'], 60)}"
            out.append(f"  {c(t, 'dim')}  {how:<16} {ch['path'] or '/':<20} {what}  {c(ch['type'], 'dim')} {c(ch['event'][:12], 'dim')}")
    return out


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
          "events", "archive", "measurements.forgotten.json", "run.log", "transcripts.json",   # events/: segments.py
          "items")                                                                        # items/: the item index


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
        shutil.rmtree(f) if f.is_dir() else f.unlink()
    if logs.is_dir():
        shutil.rmtree(logs)
    print(f"forgot {p.model.name}'s record ({p.dir}); the next run starts from nothing")
    return 0



def cmd_compact(args) -> int:
    """``ergostat compact``: now, what the engine does every hour (SPEC §4b): items' events older than
    their horizon rolled up into snapshots and archived, what is older than ``keep`` forgotten, the
    measurements rolled into their tiers."""
    from ..rollup import Archive, compact, upkeep, vacuum
    if getattr(args, "projects", False):
        return _compact_projects(args)
    p = open_project(args)
    if getattr(args, "reindex", False):
        from ..spec.itemindex import reindex
        got = reindex(p.events, p.model.spec)
        if args.json:
            return out_json({"reindex": got})
        for what, r in got.items():
            print(f"{what}: {r['items']} items folded from the record into the index ({r['seconds']:.1f}s)")
        return 0
    if args.dry_run:
        got = {"rollup": compact(p, cap=p.model.keep, dry=True)}
    else:
        got = upkeep(p)                                 # (under the compaction lock: busy when another holds it)
        if got.get("busy"):
            if args.json:
                return out_json(got)
            print(f"busy: another process holds {p.dir / 'compact.lock'} (rolling up now); nothing done")
            return 0
        got["vacuumed"] = vacuum(p)
    got["archive_bytes"] = Archive(p.dir).size()
    if args.json:
        return out_json(got)
    ro = got["rollup"]
    verb = "would roll up" if args.dry_run else "rolled up"
    print(f"{verb} {ro['events']} events of {ro['items']} items into snapshots ({ro['seconds']:.1f}s)")
    if not args.dry_run:
        me = got.get("measurements") or {}
        print(f"forgot {got['pruned']} events older than {human(p.model.keep)}, {got['archive_forgot']} archive segments; "
              f"measurements: {me.get('rolled', 0)} buckets made, {me.get('forgot', 0)} rows forgotten; "
              f"{got['vacuumed'] / 1e6:.1f} MB given back")
    print(c(f"archive: {got['archive_bytes'] / 1e6:.1f} MB in {p.dir / 'archive'}", "dim"))
    return 0


def _compact_projects(args) -> int:
    """``ergostat compact --projects``: the record folders of repositories that are gone, listed; deleted with ``--yes``,
    after the list."""
    from ..projects import forget, orphans
    found = orphans()
    if not args.json:
        for x in found:
            print(f"{x['dir']}  {x['bytes'] / 1e6:.1f} MB  (its repository {x['repo']} is gone)", flush=True)
    gone = forget(found) if args.yes else []
    if args.json:
        return out_json({"orphans": found, "deleted": gone})
    total = sum(x["bytes"] for x in found) / 1e6
    print(c(f"{len(gone)} of {len(found)} deleted" if args.yes else
            f"{len(found)} folders, {total:.1f} MB, of repositories that are gone"
            + ("; ergostat compact --projects --yes deletes them" if found else ""), "dim"))
    return 0
