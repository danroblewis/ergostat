"""``ergostat intent``: finished work held to what the owner meant (SPEC §12i): the verdicts and the rates, one verdict
with its evidence, a pass of the judge by hand, and the owner's acts (overrule a verdict, reopen work)."""

from __future__ import annotations

import sys

from ..durations import human
from ..show import c, table
from .common import open_project, out_json

USAGE = ("ergostat intent [ID] | intent judge [ITEM] [--model M] [--again] | intent overrule ID --reason R | "
         "intent reopen ITEM --reason R")


def register(sub, common) -> None:
    sp = sub.add_parser("intent", parents=[common], help="Finished work held to what the owner meant: verdicts, the "
                        "false-done rates, one verdict (ID), judge, overrule, reopen",
                        description="The intent judge (SPEC §12i). " + USAGE)
    sp.add_argument("words", nargs="*", metavar="ID | judge [ITEM] | overrule ID | reopen ITEM")
    sp.add_argument("--model", help="judge: an AI judge on this model (haiku) in place of the block's")
    sp.add_argument("--max-cost", type=float, metavar="USD", help="judge, with --model: dollars a verdict, at most")
    sp.add_argument("--again", action="store_true", help="judge: also what has a verdict already")
    sp.add_argument("--reason", help="overrule, reopen: why (required)")
    sp.add_argument("--block", help="the intent judge to use, when the model has more than one name for it")
    sp.set_defaults(fn=cmd_intent)


def _pct(x) -> str:
    return "–" if x is None else f"{round(x * 100)}%"


def _judge_block(spec, name: str | None) -> str | None:
    names = [b.name for b in spec.blocks.values() if b.judge_mode == "intent"]
    if name:
        return name if name in names else None
    return names[0] if names else None


def cmd_intent(args) -> int:
    from ..intent import judge, measures, record
    p = open_project(args)
    spec = getattr(p.model, "spec", None)
    if spec is None:
        print("the model is an ergostat.toml: the intent judge is a block of an ergostat.yaml")
        return 2
    w = list(args.words or [])
    if getattr(args, "name", None):
        w.insert(0, args.name)
    act = w[0] if w else None
    if act in ("judge", "overrule", "reopen"):
        rest = w[1:]
        try:
            if act == "overrule":
                if not rest:
                    print(USAGE, file=sys.stderr)
                    return 2
                got = record.overrule(p, rest[0], args.reason)
                print(f"{got['id']}: overruled ({got.get('verdict')} on {got['work']}): {args.reason}")
                return 0
            if act == "reopen":
                if not rest:
                    print(USAGE, file=sys.stderr)
                    return 2
                ev = record.reopen(p, spec, rest[0], args.reason)
                r = ev["data"]["reopened"]
                print(f"{rest[0]}: reopened, {r['from']} → {r['to']}: {args.reason}")
                return 0
        except record.VerdictError as e:
            print(e, file=sys.stderr)
            return 2
        b = _judge_block(spec, args.block)
        if b is None:
            print("no intent judge in this model: a block with type: judge, judge: intent (ergostat help spec, §12i)",
                  file=sys.stderr)
            return 2
        if args.max_cost is not None:
            spec.blocks[b].params["intent"].max_cost = args.max_cost
        got = judge.run(p, spec, b, model=args.model, only=rest[0] if rest else None, again=args.again)
        if args.json:
            return out_json(got)
        if got.get("refused"):
            print(f"refused: {got['refused']}", file=sys.stderr)
        elif not got["verdicts"]:
            print("nothing waiting to be judged" + (f" ({rest[0]} has not entered its judged state)" if rest else ""))
        for v in got["verdicts"]:
            print(f"{v['work']}: {c(v['verdict'], 'bold')}: {v['why']}  ({v['id']})")
        if got["cost_usd"]:
            print(c(f"spent ${got['cost_usd']:.4f}", "dim"))
        return 1 if got.get("refused") else 0
    if act:
        got = record.get(p, act)
        if got is None:
            print(f"no verdict {act!r} ({USAGE})", file=sys.stderr)
            return 2
        if args.json:
            return out_json(got)
        print(f"{got['id']}  {c(got['state'], 'bold')}\n  work      {got['work']} ({got.get('kind')}, judged at "
              f"{got.get('at')})\n  by        {got.get('block')} ({got.get('rung')}, {got.get('mode')}"
              f"{', ' + got['model'] if got.get('model') else ''})\n  held to   {', '.join(got.get('against') or []) or 'nothing'}")
        if got.get("done_when"):
            print(f"  done when {got['done_when']}")
        print(f"  why       {got.get('why') or '(not judged yet)'}")
        for e in got.get("evidence") or []:
            print(f"  - {e.get('against') or ''}: {e.get('says') or ''}" + (f"\n      {e['at']}: {e['quote']}" if e.get("at")
                                                                            else f"\n      {e['quote']}" if e.get("quote") else ""))
        if got.get("overruled"):
            print(f"  overruled {got['overruled'].get('reason')} ({got['overruled'].get('by')})")
        if got.get("missed"):
            print(f"  missed    accepted, then {got['missed'].get('how')}")
        if got.get("cost_usd"):
            print(f"  cost      ${got['cost_usd']:.4f} ({got.get('tokens_in', 0)} tokens in, {got.get('tokens_out', 0)} out)")
        return 0
    t = measures.table(p, spec)
    if args.json:
        return out_json(t)
    print(c(f"Work held to what the owner meant, over the last {human(t['until'] - t['since'])}", "bold"))
    rows = [[k, str(r["reached"]), str(r["met"]), str(r["unmet"]), str(r["contradicted"]), str(r["unjudged"]),
             str(r["overruled"]), str(r["accepted"]), str(r["reopened"]), _pct(r["false_done"]), _pct(r["false_done_tests"]),
             f"${r['cost']:.2f}"] for k, r in t["kinds"].items()]
    print(table(["KIND", "REACHED", "MET", "UNMET", "CONTRADICTED", "UNJUDGED", "OVERRULED", "ACCEPTED", "REOPENED",
                 "FALSE-DONE", "FALSE-DONE (TESTS ALONE)", "COST"], rows, "no intent judge, or nothing judged yet"))
    if t["latest"]:
        print(c("\nLatest verdicts", "bold"))
        print(table(["VERDICT", "WORK", "STATE", "WHY"], [[x["id"].split("/", 1)[1], x["work"], x["state"], (x.get("why") or "")[:90]]
                                                     for x in t["latest"][:12]], ""))
    print(c("\nergostat intent ID: one, with its evidence · intent judge: a pass now · intent overrule ID --reason · "
            "intent reopen ITEM --reason", "dim"))
    return 0
