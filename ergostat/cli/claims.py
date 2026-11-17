"""``ergostat claims``: what blocks said they did, and how far it held (SPEC §12g)."""

from __future__ import annotations

import time

from ..durations import human
from ..show import c, table
from .common import open_project, out_json


def _pct(x) -> str:
    return "" if x is None else f"{round(x * 100)}%"


def cmd_claims(args) -> int:
    """The trust table (by block, rung and model, over the last week, or ``--since``), then the latest claims, each
    with its verdict and why; ``NAME``: one claim, with its evidence; ``--check``: check the claims left unchecked
    (made just before ergostat stopped)."""
    from ..claims import checks, record, trust
    from ..durations import parse_duration
    p = open_project(args)
    spec = getattr(p.model, "spec", None)
    if spec is None:
        print("the model is an ergostat.toml: claims are made by the blocks of an ergostat.yaml")
        return 2
    if getattr(args, "check", False):
        done = checks.check_all(p, spec, checks.pending(p, spec))
        if args.json:
            return out_json(done)
        print(f"checked {len(done)} claim{'s' if len(done) != 1 else ''}" +
              "".join(f"\n  {x['id']}: {x['state']}: {x['why']}" for x in done))
        return 0
    since = time.time() - parse_duration(args.since, "--since") if args.since else None
    if args.name:
        got = record.stored(p).get(record.item_of(args.name))
        if got is None:
            print(f"no claim {args.name!r} (ergostat claims lists them)")
            return 2
        if args.json:
            return out_json(got)
        print(f"{got['id']}  {c(got['state'], 'bold')}\n  says   {got['says']}\n  about  {got.get('about') or '-'}\n"
              f"  by     {got.get('block')} ({got.get('rung') or '?'}{', ' + got['model'] if got.get('model') else ''})"
              f"{', session ' + got['session'] if got.get('session') else ''}, run {str(got.get('run') or '')[:8]}\n"
              f"  check  {got.get('kind') or 'none'}\n  why    {got.get('why') or '(not checked yet)'}\n  evidence")
        for k, v in (got.get("evidence") or {}).items():
            text = str(v)
            print(f"    {k:<8} {text if len(text) < 200 and chr(10) not in text else chr(10) + text}")
        return 0
    t = trust.table(p, since)
    if args.json:
        return out_json(t)
    print(c(f"Trust, over the last {human(t['until'] - t['since'])}", "bold"))
    rows = [[r["by"], r["name"], str(r["claims"]), str(r["verified"]), str(r["contradicted"]), str(r["unchecked"]),
             _pct(r["contradicted_share"])] for r in t["rows"]]
    print(table(["BY", "WHO", "CLAIMS", "VERIFIED", "CONTRADICTED", "UNCHECKED", "CONTRADICTED %"], rows, "no claims yet"))
    if t["contradicted"]:
        print(c("\nContradicted", "bold"))
        print(table(["CLAIM", "BLOCK", "SAYS", "WHY"], [[x["id"].split("/", 1)[1], x["block"] or "", x["says"][:50],
                                                       (x["why"] or "")[:90]] for x in t["contradicted"][:10]], ""))
    print(c("\nergostat claims ID: one, with its evidence · ergostat item --kind ergostat.claim: all of them", "dim"))
    return 0
