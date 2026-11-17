"""``ergostat context RECIPE [--item X] [--budget N]``: a projection recipe rendered (SPEC §12i); ``--list``, the
recipes; ``--outcomes``, how the work each recipe started turned out. ``decisions`` and ``corrections`` are the
one-part built-ins (``cli/decisions.py``)."""

from __future__ import annotations

import json
import sys

from .common import out_json


def _pct(x) -> str:
    return "–" if x is None else f"{x:.0%}"


def recipes(p, args, budget: int | None) -> int:
    spec = getattr(p.model, "spec", None)
    if spec is None:
        print("recipes are the YAML model's (contexts: in ergostat.yaml)", file=sys.stderr)
        return 2
    if args.list:
        rows = [{"recipe": n, "version": r.version, "description": r.description, "budget": r.budget,
                 "parts": [{"part": x.label(), "budget": x.budget} for x in r.parts], "definition": r.digest}
                for n, r in spec.contexts.items()]
        if args.json:
            return out_json({"recipes": rows, "builtin": ["decisions", "corrections"]})
        for r in rows:
            print(f"{r['recipe']}@{r['version']}  " + " + ".join(f"{x['part']} [{x['budget']}]" for x in r["parts"]) +
                  (f"\n    {r['description']}" if r["description"] else ""))
        print(("" if rows else "No recipes: write them under contexts: (ergostat help contexts).\n") +
              "Built in: decisions (--scope), corrections (--kind).")
        return 0
    if args.outcomes:
        from ..recipes import uses
        t = uses.table(p, spec)
        if args.json:
            return out_json(t)
        if not t["rows"]:
            print("No recipe used yet in the last week.")
            return 0
        print(f"{'recipe':24s} {'uses':>5s} {'ok':>4s} {'fail':>5s} {'open':>5s} {'outcome':>8s} {'cost':>8s} {'chars':>7s}")
        for r in t["rows"]:
            print(f"{r['recipe']:24s} {r['uses']:5d} {r['succeeded']:4d} {r['failed']:5d} {r['started']:5d} "
                  f"{_pct(r['outcome']):>8s} {f'${r["cost"]:.3f}' if r['cost'] is not None else '–':>8s} "
                  f"{r['chars'] or '–':>7}")
        return 0
    if not args.recipe:
        print("ergostat context RECIPE [--item X] [--budget N], or --list", file=sys.stderr)
        return 2
    from ..recipes import render as rd
    try:
        r = rd.render(p, spec, args.recipe, args.item, args.block, None, budget)
    except rd.RecipeError as e:
        print(e, file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({**r.record(), "markdown": r.text}))
    else:
        sys.stdout.write(r.text)
    return 0
