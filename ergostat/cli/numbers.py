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
    from ..numbers import review as rv
    p = open_project(args)
    spec = _spec(p)
    if args.dismiss:
        try:
            x = pr.dismiss(p, args.dismiss, getattr(args, "reason", None))
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
    if not args.stored and not getattr(args, "show", None):
        pr.make(p, light_snap(p, args), which=which)
    entries = _queue(p, spec)
    if getattr(args, "show", None):
        hit = [e for e in entries if e["id"].startswith(args.show)]
        if len(hit) != 1:
            print(f"no proposal {args.show} waiting" if not hit else f"{args.show} is the start of {len(hit)} proposals: give more of it",
                  file=sys.stderr)
            return 2
        if args.json:
            return out_json(hit[0])
        print("\n".join(_coloured(x) for x in rv.show(hit[0])))
        return 0
    if args.json:
        return out_json(entries)
    if not entries:
        from ..numbers import estimate as es
        why = {es.label(n, e): e.get("refused") or e.get("why") for n, e in es.load(p, spec, which).items()
               if e.get("refused") or e.get("why")}
        print("no proposals: every parameter to estimate fits as written, the record does not support a change "
              "(estimate: true marks a parameter to fit), and check finds nothing ergostat can propose a fix for")
        for n, w in sorted(why.items()):
            print(c(f"  {n}: {w}", "dim"))
        return 0
    for i, e in enumerate(entries):
        if i:
            print()
        _brief(e)
    print(c("\nergostat proposals --show ID prints one in full, with the diff; ergostat accept ID applies it (ergostat check "
            "must still pass); ergostat proposals --dismiss ID [--reason TEXT] lets one go", "dim"))
    return 0


def _queue(p, spec) -> list[dict]:
    """The review queue, as the Model page lists it: the structural proposals looked for, each loop analysed."""
    from ..control import loop as lp
    from ..control import proposals as cp
    from ..numbers import review as rv
    rv.refresh(p, spec)
    control = []
    for g in spec.goals:
        try:
            a = lp.analyse(p, g)
        except Exception:                                   # a loop that cannot be analysed offers nothing
            continue
        if a is not None:
            control += [x for x in cp.offered(p, a) if x["kind"] in ("process", "tuning")]
    return rv.entries(p, spec, control)


def _coloured(line: str) -> str:
    t = line.lstrip()
    if t.startswith(("---", "+++", "@@")):
        return c(line, "dim")
    return line


def _brief(e: dict) -> None:
    """One entry, as the queue lists it: what, the change, where, why, how found, benefit."""
    h = e["how"]
    print(f"{c(e['id'], 'accent')}  {c(e['what'], 'bold')}")
    print(f"  {e['title']}")
    print(f"  {c('where', 'dim')}    {', '.join(e['where']['words']) or '–'}" +
          (f"; new: {', '.join(e['where']['new'])}" if e["where"]["new"] else ""))
    print(f"  {c('why', 'dim')}      {e['why']}")
    print(f"  {c('how', 'dim')}      {h.get('method') or '–'}" + (f", over {human(h['span'])} of record" if h.get("span") else "") +
          (f", {h['n']} points" if h.get("n") else "") + (f"; {h['confidence']}" if h.get("confidence") else ""))
    b = e["benefit"]
    if b.get("nmse_before") is not None or b.get("nmse_after") is not None:
        print(f"  {c('benefit', 'dim')}  scaled error {sig(b['nmse_before'])} → {sig(b['nmse_after'])} (lower is better)")
    elif b.get("margins"):
        print(f"  {c('benefit', 'dim')}  {b['margins']}")
    for x in e["conflicts"]:
        print(c(f"  conflicts with {x['id']}: {x['why']}", "warn"))


def cmd_accept(args) -> int:
    from ..numbers import proposals as pr
    p = open_project(args)
    _spec(p)
    if not args.name:
        print("ergostat accept ID: which proposal (ergostat proposals lists them)", file=sys.stderr)
        return 2
    spec = p.model.spec
    if not any(k.startswith(args.name) for k, x in pr.stored(p).items() if x["status"] == "pending"):
        loop = [e for e in _queue(p, spec) if e["source"] == "control" and e["id"].startswith(args.name)]
        if len(loop) == 1:                                  # a loop's process or gain, offered again just now
            from ..control import proposals as cp
            try:
                x = cp.accept(p, loop[0]["id"], by="owner")
            except cp.ProposalError as e:
                print(e, file=sys.stderr)
                return 2
            print(f"accepted {x['id']}: {x['title']}\n{x['edit']['diff']}")
            return 0
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


def cmd_measure(args) -> int:
    """``ergostat measure [NAME]``: the model's own measures (SPEC §12e), as a ``model:`` sensor reads them."""
    from ..numbers import measures as ms
    p = open_project(args)
    _spec(p)
    if args.name:
        try:
            v = ms.measure(p, args.name)
        except ms.MeasureError as e:
            print(e, file=sys.stderr)
            return 2
        if v is None:
            print(f"{args.name}: no value yet (too little record to say)", file=sys.stderr)
            return 1
        print(f"{v:.6g}")
        return 0
    got = ms.all_of(p)
    if args.json:
        return out_json(got)
    from ..spec.ir import MESSAGE_MEASURES, MODEL_MEASURES, TRUST_MEASURES
    said = {**MODEL_MEASURES, **TRUST_MEASURES, **MESSAGE_MEASURES}
    print(table(["MEASURE", "VALUE", ""], [[n, sig(got.get(n)), said[n]] for n in said], ""))
    return 0


def cmd_judge(args) -> int:
    """``ergostat judge``: one pass of the judge over the changes to the model waiting (SPEC §12e), at once, as the
    model's judge block would make it (its policy; the owner's, with nothing automatic, when it has none)."""
    from ..numbers import judge as jd
    p = open_project(args)
    spec = _spec(p)
    got = jd.run(p, by=spec.improve.block or "owner")
    if args.json:
        return out_json(got)
    for v in got["verdicts"]:
        print(f"{c(v['id'], 'accent')}  {c(v['verdict'], 'ok' if v['verdict'] == 'passed' else 'warn')}: {v['why']}")
    for w in got["waiting"]:
        print(c(f"{w['id']}  testing: {human(w['held'])} of {human(w['needs'])} held out", "dim"))
    if not got["verdicts"] and not got["waiting"]:
        print("no changes to the model waiting to be judged")
    if got["accepted"]:
        print(f"written: {got['accepted']} (the judge's accept: says auto); commit it")
    return 0


def cmd_improve(args) -> int:
    """``ergostat improve``: what blocks proposed for the model and ergostat did not take, with why; ``--try
    FILE`` (or - for standard input) checks a proposal, as a propose line would be checked, and lands nowhere."""
    import json

    from ..numbers import improve as im
    p = open_project(args)
    _spec(p)
    if args.edit_value:
        from ..numbers import proposals as pr
        from ..numbers import yamledit as ye
        spec = p.model.spec
        name, _, value = args.edit_value.partition("=")
        prm = spec.parameters.get(name.strip())
        try:
            if prm is None or prm.table:
                raise pr.ProposalError(f"no parameter {name.strip()} with a value")
            v = float(value) if not prm.duration else pr.parse_value(prm, value)
            return out_json(im.joined([pr._value_edit(prm, v)]))
        except (pr.ProposalError, ye.EditError, ValueError) as e:
            print(e, file=sys.stderr)
            return 2
    if args.try_:
        raw = sys.stdin.read() if args.try_ == "-" else open(args.try_, encoding="utf-8").read()
        try:
            obj = json.loads(raw)
        except ValueError as e:
            print(f"not JSON: {e}", file=sys.stderr)
            return 2
        got = im.trial(p, obj.get("propose", obj) if isinstance(obj, dict) else obj)
        if args.json:
            return out_json(got)
        print(f"it would {got['would']}" + (f": {got['why']}" if got.get("why") else ""))
        if got.get("diff"):
            print(f"  {got['kind']}: {got['title']}\n  scaled error {sig(got['scaled_error_before'])} → "
                  f"{sig(got['scaled_error_after'])}; answers {len(got['findings']['answered'])} findings, makes "
                  f"{len(got['findings']['new'])}")
            for r in got["refused_reasons"]:
                print(c(f"  reason refused: {r['says'][:80]}: {r['why']}", "warn"))
            print("\n".join("  " + x for x in got["diff"].split("\n")))
        return 0 if got["would"] == "be proposed" else 1
    xs = im.not_proposed(p)
    if args.json:
        return out_json(xs)
    if not xs:
        print("nothing proposed by a block has been turned away")
    for x in xs:
        print(f"{c(x['by'], 'accent')}  {x['title']}\n  {c('not proposed:', 'warn')} {x['why']}")
    return 0
