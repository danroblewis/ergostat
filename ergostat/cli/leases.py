"""``ergostat lease``: the leases on items (SPEC §9.5): who holds what, until when; the dead letters; one item's
attempts; a run renewing its lease or giving its item back; the owner redriving a dead letter."""

from __future__ import annotations

import sys
import time

from ..durations import human
from ..show import c, table
from .common import open_project, out_json


def cmd_lease(args) -> int:
    from ..leases import acts
    from ..spec import items as its
    if args.renew or args.nack is not None:              # a run's own lease: the running engine, when one listens (calls/)
        from ..calls.client import Refused
        from . import fast
        try:
            if args.renew:
                got = fast.call(args, "lease", how="renew", env=fast.env())
                if got is not None:
                    print(json_or(args, got["event"], f"renewed the lease on {got['event']['item']}"))
                    return 0
            else:
                from ..durations import parse_duration
                after = parse_duration(args.after, "--after") if args.after else None
                got = fast.call(args, "lease", how="nack", why=args.nack or "given back", after=after,
                                count=not args.no_count, env=fast.env())
                if got is not None:
                    print(json_or(args, got["event"], f"gave {got['event']['item']} back"))
                    return 0
        except Refused as e:
            print(str(e), file=sys.stderr)
            return e.code
    p = open_project(args)
    spec = getattr(p.model, "spec", None)
    if spec is None:
        print("the model is an ergostat.toml: leases are taken by the blocks of an ergostat.yaml", file=sys.stderr)
        return 2
    try:
        if args.renew:
            ev = acts.renew(p, spec)
            print(json_or(args, ev, f"renewed the lease on {ev['item']}"))
            return 0
        if args.nack is not None:
            from ..durations import parse_duration
            after = parse_duration(args.after, "--after") if args.after else None
            ev = acts.nack(p, spec, args.nack or "given back", after=after, count=not args.no_count)
            print(json_or(args, ev, f"gave {ev['item']} back"))
            return 0
        if args.redrive:
            if not args.name:
                print("--redrive: name the dead letter (ergostat lease ITEM --redrive)", file=sys.stderr)
                return 2
            ev = acts.redrive(p, spec, args.name, why=args.why or "", to=args.to)
            print(json_or(args, ev, f"redrove {args.name}: it can be taken again"))
            return 0
    except acts.LeaseError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    now = time.time()
    if args.name:
        it = its.one(p.events, spec, args.name)
        lease = (it.fields.get("lease") if it else None) or None
        if not isinstance(lease, dict):
            print(f"no lease was ever taken on {args.name}")
            return 2
        if args.json:
            return out_json({"item": it.id, "state": it.state, "lease": lease})
        print(f"{c(it.id, 'bold')}  {it.state}  " + (f"held by {lease.get('block')} (run {str(lease['holder'])[:8]}), "
              f"expires in {human(float(lease['expires']) - now)}" if lease.get("holder") else "not held")
              + f"; attempts {lease.get('attempts', 0)} of {lease.get('max', '?')}")
        rows = [[str(h.get("fence")), h.get("block") or "", str(h.get("run") or "")[:8],
                 time.strftime("%H:%M:%S", time.localtime(h["taken"])), h.get("how") or "holding",
                 human(float(h.get("ended") or now) - float(h["taken"])), str(h.get("exit") if h.get("exit") is not None else ""),
                 str(h.get("why") or "")[:80]] for h in lease.get("history") or []]
        print(table(["fence", "block", "run", "taken", "how", "for", "exit", "why"], rows))
        return 0
    got = acts.listing(p, spec)
    if args.json:
        return out_json(got)
    shown = [x for x in got if x["held"] or x["state"] == "dead"]
    rows = [[x["item"], x["state"] or "", f"{x.get('block')} ({str(x.get('holder') or '')[:8]})" if x["held"] else "",
             human(float(x.get("expires") or now) - now) if x["held"] else "", f"{x.get('attempts', 0)}/{x.get('max', '?')}"]
            for x in shown]
    print(table(["item", "state", "held by", "expires in", "attempts"], rows, empty="no lease held, and no dead letter"))
    return 0


def json_or(args, ev: dict, text: str) -> str:
    import json
    return json.dumps(ev, default=str) if args.json else text
