"""The declared operating states' half of ``ergostat operating`` (SPEC §9.5; the topic is ``gated.py``'s, with the
operating state of SPEC §12k): each one's rank and pool, entered or left, by whom, since when, and the trips that entered
it; ``enter NAME --why TEXT`` and ``leave NAME --why TEXT``, the owner's acts. From a run (``ERGOSTAT_RUN`` set)
``leave`` is refused and ``enter`` is recorded as the run's."""

from __future__ import annotations

import sys
import time

from ..show import table
from .common import open_project, out_json


def act(args) -> int:
    from ..operating import acts
    p = open_project(args)
    spec = getattr(p.model, "spec", None)
    if spec is None:
        print("the model is an ergostat.toml: operating states are an ergostat.yaml's", file=sys.stderr)
        return 2
    if not args.name or not args.why or args.lease or args.actions or args.note:
        print(f"ergostat operating {args.state} NAME --why TEXT: name the state and say why", file=sys.stderr)
        return 2
    try:
        ev = (acts.enter if args.state == "enter" else acts.leave)(p, spec, args.name, args.why)
    except acts.OperatingError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    if args.json:
        return out_json(ev)
    print(f"{args.name} {'entered' if args.state == 'enter' else 'left'} (by {ev['data']['by']})")
    return 0


def listing(p) -> list[dict]:
    """The declared states (none when the model declares none: nothing is read, invariant 12)."""
    from ..operating import KIND, acts
    spec = getattr(p.model, "spec", None)
    return acts.listing(p, spec) if spec is not None and KIND in spec.items else []


def show(p) -> None:
    got = listing(p)
    if not got:
        return
    rows = [[x["state"] + ("" if x["declared"] else " (not declared)"), str(x["rank"] or ""),
             "none" if x["pool"] is None else str(x["pool"]), x["now"], x["by"] or "",
             time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(x["since"])) if x["since"] else "",
             ", ".join(f"{t['goal']} ({t['spell']})" for t in x["trips"])] for x in got]
    print("\nthe states the model declares (SPEC §9.5)")
    print(table(["state", "rank", "pool", "now", "by", "since", "trips"], rows))
