"""``ergostat actions``: the gated actions sessions asked for, and the owner's answer to one held for approval;
``ergostat act``: a program block's run asking for one (``$ERGOSTAT_CMD act NAME --arg K=V``);
``ergostat workspaces``: the workspace pools, and freeing a quarantined workspace (SPEC §12k)."""

from __future__ import annotations

import time

from ..show import c, table
from .common import open_project, out_json

PROMOTE = 5                  # approvals in a row, none denied, after which a class is said to be ready for gate: auto


def register(sub, common) -> None:
    ac = sub.add_parser("actions", parents=[common], help="The gated actions sessions asked for (ID: one; --approve or "
                        "--deny: the owner's answer to one held), counted per class",
                        description="Gated actions (SPEC §12k). ergostat actions [ID] [--approve | --deny] [--note TEXT]")
    ac.add_argument("name", nargs="?", metavar="ID", help="one action (its id, or the start of it)")
    ac.add_argument("--approve", action="store_true", help="approve a held action: it runs (or the session waiting runs it)")
    ac.add_argument("--deny", action="store_true", help="deny a held action: it never runs")
    ac.add_argument("--note", help="with --approve or --deny: why")
    ac.add_argument("--as", dest="by", metavar="WHO", help="who answers (default: owner)")
    ac.add_argument("-n", type=int, default=30, help="how many to list (default 30)")
    ac.set_defaults(fn=cmd_actions)
    at = sub.add_parser("act", parents=[common], help="From a block's run: ask for one of its gated actions "
                        "($ERGOSTAT_CMD act NAME --arg K=V); exits 0 ran, 1 failed, 3 held, 4 denied",
                        description="A gated action asked for by a block's run (SPEC §12k). Its output, once it ran, "
                        "is printed; how the gate took it is said on stderr. Exit: 0 ran, 1 failed, 3 held for the "
                        "owner (or approved and not run yet), 4 denied, 2 refused (no such action for this block).")
    at.add_argument("name", metavar="NAME", help="the action, one of the block's actions:")
    at.add_argument("--arg", action="append", default=[], metavar="K=V", help="one of its args: (repeat)")
    at.add_argument("--key", help="what tells this act from the same one asked before (default: its arguments)")
    at.add_argument("--wait", metavar="DUR", help="how long to wait for the owner when it is held "
                    "(default: not at all; the same request again finds it, answered or not)")
    at.set_defaults(fn=cmd_act)
    ws = sub.add_parser("workspaces", parents=[common], help="The workspace pools: each workspace, whose it is, free, "
                        "in use, held or quarantined (POOL --free N frees a quarantined one)",
                        description="Workspace pools (SPEC §12k). ergostat workspaces [POOL] [--free N]")
    ws.add_argument("name", nargs="?", metavar="POOL", help="one pool")
    ws.add_argument("--free", type=int, metavar="N", help="with POOL: free its quarantined workspace N (its worktree removed)")
    ws.set_defaults(fn=cmd_workspaces)
    from ..actions.operating import STATES
    op = sub.add_parser("operating", parents=[common], help="The operating state (normal, maintenance, freeze, incident) "
                        "and the owner's presence; STATE: the owner enters it (normal ends the one in force)",
                        description="The operating state (SPEC §12k). ergostat operating [freeze | incident --note TEXT "
                        "| maintenance --for DUR [--actions A,B] [--note TEXT] | normal]")
    op.add_argument("state", nargs="?", choices=STATES, metavar="STATE", help=", ".join(STATES))
    op.add_argument("--for", dest="lease", metavar="DUR", help="maintenance: how long its lease runs (at most 24h)")
    op.add_argument("--actions", metavar="A,B", help="maintenance: the actions it is for")
    op.add_argument("--note", help="why")
    op.set_defaults(fn=cmd_operating)


def cmd_operating(args) -> int:
    from ..actions import operating as ops
    from ..durations import DurationError, human, parse_duration
    p = open_project(args)                               # (a broken model: refused, as every act is)
    if args.state:
        try:
            lease = parse_duration(args.lease, "--for") if args.lease else None
            acts = [a.strip() for a in (args.actions or "").split(",") if a.strip()]
            known = getattr(getattr(p.model, "spec", None), "actions", {})
            if unknown := [a for a in acts if a not in known]:
                raise ops.OperatingError(f"--actions: {', '.join(unknown)}: not one of the actions: in the model")
            ops.enter(p, args.state, args.note, lease, acts)
        except (ops.OperatingError, DurationError, OverflowError) as e:
            print(f"refused: {e}")
            return 2
    o = ops.read(p)
    if args.json:
        return out_json(o._asdict())
    print(f"{c(o.state, 'bold')}  ·  owner {o.presence}" + (f"  ·  {o.note}" if o.note else ""))
    if o.until is not None:
        print(f"  lapses in {human(max(o.until - time.time(), 0))}" + (f", for {', '.join(o.actions)}" if o.actions else ""))
    print(c(f"  {o.reason}", "dim"))
    return 0


def _spec(p):
    spec = getattr(p.model, "spec", None)
    if spec is None:
        print("the model is an ergostat.toml: actions and workspaces are an ergostat.yaml's")
    return spec


def show_one(a: dict) -> None:
    print(f"{a['id']}  {c(a['state'], 'bold')}  ({a.get('action')}, class {a.get('class')}, gate {a.get('gate')})")
    print(f"  command  {a.get('command')}\n  in       {a.get('in')}")
    for k in ("item", "branch", "block", "session"):
        if a.get(k):
            print(f"  {k:<8} {a[k]}")
    print(f"  asked    {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(a['time']))}")
    if a.get("approved_by"):
        print(f"  approved by {a['approved_by']}" + (f": {a['note']}" if a.get("note") else ""))
    if a.get("denied_by"):
        print(f"  denied by {a['denied_by']}" + (f": {a['note']}" if a.get("note") else ""))
    if a["state"] in ("ran", "failed"):
        print(f"  exit     {a.get('exit')}\n  output\n" + "\n".join("    " + x for x in (a.get("output") or "").splitlines()))
    for d in a.get("deliveries") or []:
        print(f"  given to {d.get('session') or d.get('block')} ({d.get('how')})")
    if a["state"] == "requested":
        print(c(f"\nheld for approval: ergostat actions {a['id'].split('/', 1)[1]} --approve (or --deny)", "dim"))


def cmd_actions(args) -> int:
    from ..actions import gate, record
    p = open_project(args)
    spec = _spec(p)
    if spec is None:
        return 2
    if args.name:
        a = record.get(p, args.name)
        if a is None:
            print(f"no action {args.name!r} (ergostat actions lists them)")
            return 2
        if args.approve and args.deny:
            print("--approve or --deny, not both")
            return 2
        try:
            if args.approve:
                a = gate.approve(p, spec, a["id"], by=args.by or "owner", note=args.note)
            elif args.deny:
                a = gate.deny(p, a["id"], by=args.by or "owner", note=args.note)
        except gate.GateError as e:
            print(e)
            return 2
        if args.json:
            return out_json(a)
        show_one(a)
        return 0
    got = sorted(record.stored(p).values(), key=lambda a: -a["time"])[:args.n]
    classes = record.by_class(p)
    if args.json:
        return out_json({"actions": got, "classes": classes, "measures": record.counts(p)})
    rows = [[record.short(a["id"]), a["state"], time.strftime("%m-%d %H:%M", time.localtime(a["time"])),
             a.get("action") or "", a.get("item") or "", (a.get("command") or "")[:60]] for a in got]
    print(table(["ACTION", "STATE", "ASKED", "NAME", "ITEM", "COMMAND"], rows, "no actions asked for yet"))
    if classes:
        print()
        print(table(["CLASS", "GATE", "HELD", "APPROVED", "AUTO", "DENIED", "RAN", "FAILED"],
                    [[k, _gate(spec, k), *(f"{v[x]:g}" for x in ("held", "approved", "auto", "denied", "ran", "failed"))]
                     for k, v in classes.items()], ""))
        for k, v in classes.items():
            if _gate(spec, k) == "approve" and v["approved"] >= PROMOTE and not v["denied"]:
                print(c(f"class {k}: approved {v['approved']:g} times this week, none denied: the owner may promote it "
                        f"(gate: auto under actions: in the model)", "dim"))
    held = [a for a in got if a["state"] == "requested"]
    if held:
        print(c(f"\n{len(held)} held for approval: ergostat actions ID --approve (or --deny)", "dim"))
    return 0


def cmd_act(args) -> int:
    import sys

    from ..actions import gate, program
    from ..durations import parse_duration
    vals = {}
    for kv in args.arg:
        k, eq, v = kv.partition("=")
        if not eq or not k:
            print(f"--arg {kv!r}: write it NAME=VALUE", file=sys.stderr)
            return 2
        vals[k] = v
    wait = parse_duration(args.wait, "--wait") if args.wait else 0.0
    from ..calls.client import Refused
    from ..calls.ops import act_key
    from . import fast
    once = fast.key()                                    # the same in the fallback below: asked once
    try:                                                 # the running engine asks it, when one listens (calls/)
        sent = fast.call(args, "act", timeout=wait + 3600.0, name=args.name, args=vals, key=args.key, wait=wait,
                         env=fast.env(), call=once)
    except Refused as e:
        print(str(e), file=sys.stderr)
        return e.code
    if sent is not None:
        a, code = sent["full"], int(sent["exit"])
        if args.json:
            out_json(sent["action"])
            return code
        return said(args, a, code)
    p = open_project(args)
    spec = _spec(p)
    if spec is None:
        return 2
    try:
        cfg = program.given()
        a = program.ask(p, spec, cfg, args.name, vals, key=act_key(cfg, {"key": args.key, "call": once}), wait=wait)
    except program.AskError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    code = program.exit_code(a)
    if args.json:
        out_json(gate.result(a))
        return code
    return said(args, a, code)


def said(args, a: dict, code: int) -> int:
    """What ``act`` prints of an action's answer (without --json)."""
    import sys

    from ..actions import record
    if a["state"] == "ran":
        if a.get("output"):
            print(a["output"])
        print(f"{args.name}: ran ({a['id']}, approved by {a.get('approved_by')})", file=sys.stderr)
    elif a["state"] == "failed":
        print(f"{args.name}: failed ({a['id']}, exit {a.get('exit')})" + (f"\n{a.get('output')}" if a.get("output") else ""),
              file=sys.stderr)
    elif a["state"] == "denied":
        print(f"{args.name}: denied by {a.get('denied_by')}" + (f": {a['note']}" if a.get("note") else ""), file=sys.stderr)
    elif a["state"] == "requested":
        print(f"{args.name}: held for the owner's approval ({a['id']}): ergostat actions {record.short(a['id'])} --approve",
              file=sys.stderr)
    else:
        print(f"{args.name}: approved, not run yet ({a['id']})", file=sys.stderr)
    return code


def _gate(spec, cls: str) -> str:
    gates = {a.gate for a in spec.actions.values() if (a.cls or a.name) == cls}
    return ", ".join(sorted(gates)) or "?"


def cmd_workspaces(args) -> int:
    from ..workspaces import pool as pl
    p = open_project(args)
    spec = _spec(p)
    if spec is None:
        return 2
    if args.name and args.name not in spec.workspaces:
        print(f"no pool {args.name!r} (pools: {', '.join(spec.workspaces) or 'none'})")
        return 2
    if args.free is not None:
        if not args.name:
            print("--free N frees a quarantined workspace of a pool: ergostat workspaces POOL --free N")
            return 2
        try:
            pl.free(p, spec, args.name, args.free, by=getattr(args, "by", None) or "owner")
        except pl.PoolError as e:
            print(e)
            return 2
    pools = [spec.workspaces[args.name]] if args.name else list(spec.workspaces.values())
    got = {x.name: list(pl.slots(p, spec, x).values()) for x in pools}
    if args.json:
        return out_json({"pools": got, "measures": {x.name: pl.counts(p, spec, x.name) for x in pools}})
    if not pools:
        print("no workspace pools (workspaces: in the model)")
        return 0
    rows = [[f"{s['pool']}-{s['slot']}", s["state"], s.get("item") or "", s.get("branch") or "", s.get("dir") or "",
             s.get("why") or s.get("how") or ""] for ss in got.values() for s in ss]
    print(table(["WORKSPACE", "STATE", "ITEM", "BRANCH", "FOLDER", "WHY"], rows, ""))
    for name in got:
        n = pl.counts(p, spec, name)
        print(c(f"{name}: free {n['free']} · in use {n['in-use']} · held {n['held']} · quarantined {n['quarantined']}",
                "dim"))
    return 0
