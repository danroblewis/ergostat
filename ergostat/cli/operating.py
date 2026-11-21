"""``ergostat operating``: the operating states (SPEC §9.5): each one's rank and pool, entered or left, by whom, since
when, and the trips that entered it; ``enter NAME --why TEXT`` and ``leave NAME --why TEXT``, the owner's acts. From a
run (``ERGOSTAT_RUN`` set) ``leave`` is refused and ``enter`` is recorded as the run's."""

from __future__ import annotations

import sys
import time

from ..show import table
from .common import open_project, out_json


def register(sub, common) -> None:
    op = sub.add_parser("operating", parents=[common], help="The operating states: rank, pool, entered or left, by whom; "
                        "enter NAME --why TEXT, leave NAME --why TEXT",
                        description="Operating states (SPEC §9.5). ergostat operating [enter|leave NAME --why TEXT]")
    op.add_argument("act", nargs="?", choices=["enter", "leave"], help="enter or leave a state (leave it out: list them)")
    op.add_argument("name", nargs="?", metavar="NAME", help="the state")
    op.add_argument("--why", metavar="TEXT", help="with enter or leave: why (required)")
    op.set_defaults(fn=cmd_operating)


def cmd_operating(args) -> int:
    from ..operating import acts
    p = open_project(args)
    spec = getattr(p.model, "spec", None)
    if spec is None:
        print("the model is an ergostat.toml: operating states are an ergostat.yaml's", file=sys.stderr)
        return 2
    if args.act:
        if not args.name or not args.why:
            print(f"ergostat operating {args.act} NAME --why TEXT: name the state and say why", file=sys.stderr)
            return 2
        try:
            ev = (acts.enter if args.act == "enter" else acts.leave)(p, spec, args.name, args.why)
        except acts.OperatingError as e:
            print(f"refused: {e}", file=sys.stderr)
            return 1
        if args.json:
            return out_json(ev)
        print(f"{args.name} {'entered' if args.act == 'enter' else 'left'} (by {ev['data']['by']})")
        return 0
    got = acts.listing(p, spec)
    if args.json:
        return out_json(got)
    rows = [[x["state"] + ("" if x["declared"] else " (not declared)"), str(x["rank"] or ""),
             "none" if x["pool"] is None else str(x["pool"]), x["now"], x["by"] or "",
             time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(x["since"])) if x["since"] else "",
             ", ".join(f"{t['goal']} ({t['spell']})" for t in x["trips"])] for x in got]
    print(table(["state", "rank", "pool", "now", "by", "since", "trips"], rows, empty="no operating states declared"))
    return 0
