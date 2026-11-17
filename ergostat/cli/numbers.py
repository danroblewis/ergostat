"""The model's numbers: ``ergostat fit`` (how well the replay fits the record), ``ergostat
proposals`` (estimate, and list the changes the record supports) and ``ergostat accept ID`` (apply
one, as the smallest edit to the YAML)."""

from __future__ import annotations

import sys
import time

from ..durations import human
from ..show import c, table
from .common import at_of, open_project, out_json, window


def light_snap(p, args) -> dict:
    """The window and the moment, without the whole state: what the replay needs."""
    oldest = min((t for t in (p.events.first_time(), p.measurements.first_time()) if t), default=None)
    return {"at": at_of(args) or time.time(), "window": window(args), "starts": oldest}


def _spec(p):
    spec = getattr(p.model, "spec", None)
    if spec is None:
        print("the model is an ergostat.toml: equations and parameters are written in ergostat.yaml "
              "(ergostat convert writes it)", file=sys.stderr)
        raise SystemExit(2)
    return spec


def pct(x) -> str:
    return "" if x is None else f"{x * 100:.0f}%"


def two(x) -> str:
    return "" if x is None else f"{x:.2f}"


def sig(x) -> str:
    return "–" if x is None else f"{x:.3g}"


def cmd_fit(args) -> int:
    from ..numbers import fit as ft
    from ..numbers import proposals as pr
    from ..numbers import version as ver
    p = open_project(args)
    spec = _spec(p)
    snap = light_snap(p, args)
    _, run, got = ft.compute(p, snap)
    ft.record(p, got)
    if args.json:
        return out_json({"version": ver.version(spec), "structure": ver.structure(spec), **got, "notes": run.notes,
                         "words": ft.WORDS, "history": ft.versions(p), "accepted": pr.accepted(p),
                         "proposals": pr.pending(p, spec)})

    def cells(s):
        if not s:
            return ["", "", "", "", "", "too few points"]
        if s.get("too_little"):
            return [str(s["n"]), "", "", "", "", f"too little record: {s['too_little']}"]
        if s.get("exact"):
            return [str(s["n"]), "", "", "", "", "no error"]
        err = pct(s["mape"]) if s["mape"] is not None else \
            (f"{pct(s['error_share'])} of {s['error_of']}" if s.get("error_share") is not None else "")
        return [str(s["n"]), two(s["r2"]), err, two(s["um"]), two(s["us"]), two(s["uc"]) + (f"  {s['says']}" if s.get("says") else "")]
    for part, head, empty in (("stocks", "MODEL FIT", "no stock is moved by an equation"),
                              ("partial", "EQUATION, INPUTS AS MEASURED", "no equation's part is measured"),
                              ("equations", "EQUATION, REPLAYED", ""),
                              ("accounting", "ACCOUNTING", "")):
        rows = [[ref.split(".", 1)[1], *cells(s)] for ref, s in sorted(got[part].items())]
        if part == "stocks" and got["total"]:
            t = got["total"]
            rows.append([c("total", "bold"), str(t["n"]), "", "", two(t["um"]), two(t["us"]),
                         two(t["uc"]) + (f"  scaled error {t['nmse']:.3g}" if t.get("nmse") is not None else "")])
        if rows or empty:
            print(table([head, "N", "R²", "MAPE", "U_M", "U_S", "U_C"], rows, empty))
    for ref, stock in sorted(got["judged_by_stock"].items()):
        print(c(f"  {ref}: measured from its stock's changes, so judged by {stock}'s replay", "dim"))
    for n in got["invalid"]:
        print(c(f"  not valid: {n}", "warn"))
    for n in run.notes:
        print(c(f"  {n}", "dim"))
    print(c(f"\nversion {ver.version(spec)}, over the last {human(got['span'])} of record. The total: {ft.WORDS['nmse']}. "
            f"R² {ft.WORDS['r2']}; MAPE {ft.WORDS['mape']}; "
            f"Theil's U_M {ft.WORDS['um']}, U_S {ft.WORDS['us']}, U_C {ft.WORDS['uc']}. Accounting: {ft.WORDS['accounting']}.", "dim"))
    waiting = pr.pending(p, spec)
    if waiting:
        print(f"\n{len(waiting)} proposal{'s' if len(waiting) > 1 else ''} waiting: ergostat proposals")
    return 0


def _show(x: dict) -> None:
    b, a = (x.get("fit_before") or {}).get("total") or {}, (x.get("fit_after") or {}).get("total") or {}
    print(f"{c(x['id'], 'accent')}  {x['title']}" + (c(f"  ({x['scope_words']})", "dim") if x.get("scope_words") else ""))
    print(f"  {x['reason']}")
    for r in x.get("touched", []):
        fb = (x.get("fit_before") or {}).get("stocks", {}).get(r) or (x.get("fit_before") or {}).get("equations", {}).get(r)
        fa = (x.get("fit_after") or {}).get("stocks", {}).get(r) or (x.get("fit_after") or {}).get("equations", {}).get(r)
        if fb or fa:
            print(f"  {r}: R² {two((fb or {}).get('r2')) or '–'} → {two((fa or {}).get('r2')) or '–'}, "
                  f"MAPE {pct((fb or {}).get('mape')) or '–'} → {pct((fa or {}).get('mape')) or '–'}")
    if b or a:
        print(f"  fit, in total: scaled error {sig(b.get('nmse'))} → {sig(a.get('nmse'))} (lower is better)")
    if "diff" in x["edit"]:
        for line in x["edit"]["diff"].split("\n"):
            print("  " + (c(line, "dim") if line.startswith("@@") else line))
    else:
        print(c(f"  (no edit: {x['edit'].get('error')})", "warn"))


def cmd_proposals(args) -> int:
    from ..numbers import proposals as pr
    p = open_project(args)
    spec = _spec(p)
    if args.dismiss:
        try:
            x = pr.dismiss(p, args.dismiss)
        except pr.ProposalError as e:
            print(e, file=sys.stderr)
            return 2
        print(f"dismissed {x['id']}: {x['title']}")
        return 0
    if getattr(args, "propose", None):
        values = {}
        for one in args.propose:
            for part in one.split(","):
                name, _, value = part.partition("=")
                if name.strip():
                    values[name.strip()] = value.strip()
        try:
            x = pr.propose_values(p, values, light_snap(p, args))
        except pr.ProposalError as e:
            print(e, file=sys.stderr)
            return 2
        if args.json:
            return out_json(x)
        _show(x)
        print(c(f"\nergostat accept {x['id']} applies it", "dim"))
        return 0
    which = getattr(args, "calibrate", None) or "parts"
    got = pr.pending(p, spec) if args.stored else pr.make(p, light_snap(p, args), which=which)
    if args.json:
        return out_json(got)
    if not got:
        from ..numbers import estimate as es
        why = {es.label(n, e): e.get("refused") or e.get("why") for n, e in es.load(p, spec, which).items()
               if e.get("refused") or e.get("why")}
        print("no proposals: every parameter to estimate fits as written, or the record does not support a change "
              "(estimate: true marks a parameter to fit)")
        for n, w in sorted(why.items()):
            print(c(f"  {n}: {w}", "dim"))
        return 0
    for i, x in enumerate(got):
        if i:
            print()
        _show(x)
    print(c("\nergostat accept ID applies one (the edit above; ergostat check must still pass); "
            "ergostat proposals --dismiss ID lets one go", "dim"))
    return 0


def cmd_accept(args) -> int:
    from ..numbers import proposals as pr
    p = open_project(args)
    _spec(p)
    if not args.name:
        print("ergostat accept ID: which proposal (ergostat proposals lists them)", file=sys.stderr)
        return 2
    try:
        x = pr.accept(p, args.name, light_snap(p, args), by="owner")
    except pr.ProposalError as e:
        print(e, file=sys.stderr)
        return 2
    if args.json:
        return out_json(x)
    ap = x["applied"]
    print(f"accepted {x['id']}: {x['title']}\n{x['edit']['diff']}")
    print(f"version {ap['version_before']} → {ap['version_after']}; fit in total: scaled error "
          f"{sig((ap['fit_before'] or {}).get('nmse'))} → {sig((ap['fit_after'] or {}).get('nmse'))}")
    return 0
