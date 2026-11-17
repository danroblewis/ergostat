"""The recovery benchmark's scorecard, per case and overall, as JSON and markdown."""

from __future__ import annotations


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def overall(results) -> dict:
    sc = [r.scores for r in results]
    every = [d for s in sc for d in s["defects"]]
    defects = [d for d in every if d.get("visible", True)]
    by_kind: dict[str, list] = {}
    for d in defects:
        by_kind.setdefault(d["kind"], []).append(d["fixed"])
    props = sum(s["proposals"] for s in sc)
    real = sum(s["real_fixes"] for s in sc)
    acc = sum(s["accepted"] for s in sc)
    usd = sum(float(r.cost.get("usd") or 0.0) for r in results)
    accepted_real = sum(s["accepted_real"] for s in sc)
    kinds: dict[str, dict] = {}
    for s_ in sc:
        for k, row in (s_.get("by_kind") or {}).items():
            got = kinds.setdefault(k, dict.fromkeys(row, 0))
            for f, v in row.items():
                got[f] += v
    return {
        "by_kind": kinds,
        "cases": len(results), "defects": len(defects), "not_visible": len(every) - len(defects),
        "fixed": sum(d["fixed"] for d in defects),
        "recall": sum(d["fixed"] for d in defects) / len(defects) if defects else None,
        "recall_by_kind": {k: f"{sum(v)}/{len(v)}" for k, v in sorted(by_kind.items())},
        "proposals": props, "real_fixes": real, "precision": real / props if props else None,
        "accepted": acc, "accepted_real": accepted_real, "damage": sum(s["damage"] for s in sc),
        "fit_ratio_final_to_truth": _mean([_ratio(s["fit"]["final"], s["fit"]["truth"]) for s in sc]),
        "fit_ratio_damaged_to_truth": _mean([_ratio(s["fit"]["damaged"], s["fit"]["truth"]) for s in sc]),
        "forecast_better_than_damaged": sum(1 for s in sc if _lt(s["forecast"]["final"], s["forecast"]["damaged"])),
        "forecast_within_2x_truth": sum(1 for s in sc if _ratio(s["forecast"]["final"], s["forecast"]["truth"]) is not None
                                        and _ratio(s["forecast"]["final"], s["forecast"]["truth"]) <= 2.0),
        "rounds": sum(r.cost.get("rounds") or 0 for r in results),
        "seconds": round(sum(float(r.cost.get("seconds") or 0.0) for r in results), 1),
        "tokens": sum(int(r.cost.get("tokens") or 0) for r in results), "usd": round(usd, 4),
        "usd_per_accepted_fix": round(usd / accepted_real, 4) if accepted_real else None,
    }


def _ratio(a, b):
    if a is None or b is None or b <= 0:
        return None
    return a / b


def _lt(a, b):
    if a is None:
        return False
    return b is None or a < b


def _g(x) -> str:
    if x is None:
        return "–"
    if isinstance(x, float):
        return f"{x:.3g}"
    return str(x)


def markdown(data: dict) -> str:
    o = data["overall"]
    cases = data["cases"]
    imp = cases[0]["improver"] if cases else "?"
    be = cases[0]["judge"] if cases else "?"
    out = [f"# Recovery benchmark: {imp} ({be})", "",
           f"{o['cases']} cases, {o['defects']} defects planted and visible in the record"
           + (f" ({o['not_visible']} more planted that the record cannot tell from the truth)" if o.get("not_visible") else "")
           + f", {o['fixed']} fixed (recall {_g(o['recall'])}); "
           f"{o['proposals']} proposals, {o['real_fixes']} real fixes (precision {_g(o['precision'])}); "
           f"{o['accepted']} accepted, {o['accepted_real']} of them real fixes, {o['damage']} damaging.", "",
           f"Fit over the record, as a multiple of the truth's: damaged {_g(o['fit_ratio_damaged_to_truth'])}, final "
           f"{_g(o['fit_ratio_final_to_truth'])}. Forecast on later record: better than the damaged model in "
           f"{o['forecast_better_than_damaged']} of {o['cases']} cases, within twice the truth's error in "
           f"{o['forecast_within_2x_truth']}.", "",
           f"Cost: {o['rounds']} rounds, {o['seconds']} s, {o['tokens']} tokens, ${o['usd']}"
           + (f" (${o['usd_per_accepted_fix']} an accepted fix)" if o.get("usd_per_accepted_fix") else "") + ".", "",
           "Recall by defect: " + ", ".join(f"{k} {v}" for k, v in o["recall_by_kind"].items()) + ".", "",
           "Proposals by kind (proposed, checked by ergostat, passed by the judge, failed by it, real fixes): "
           + "; ".join(f"{k} {r['proposed']}, {r['checked']}, {r['passed']}, {r['failed']}, {r['real_fixes']}"
                       for k, r in sorted(o.get("by_kind", {}).items())) + ".", "",
           "| Case | Defects | Fixed | Proposals (real) | Accepted (real, damage) | Fit damaged / final / truth | "
           "Forecast damaged / final / truth | Rounds | s |",
           "|---|---|---|---|---|---|---|---|---|"]
    for c in cases:
        s = c["scores"]
        out.append(f"| {c['case']} | {', '.join(d['kind'] for d in s['defects'])} | "
                   f"{sum(d['fixed'] for d in s['defects'])}/{sum(d.get('visible', True) for d in s['defects'])} | "
                   f"{s['proposals']} ({s['real_fixes']}) | "
                   f"{s['accepted']} ({s['accepted_real']}, {s['damage']}) | "
                   f"{_g(s['fit']['damaged'])} / {_g(s['fit']['final'])} / {_g(s['fit']['truth'])} | "
                   f"{_g(s['forecast']['damaged'])} / {_g(s['forecast']['final'])} / {_g(s['forecast']['truth'])} | "
                   f"{c['cost'].get('rounds')} | {c['cost'].get('seconds')} |")
    out += ["", "## Cases", ""]
    for c in cases:
        s = c["scores"]
        out.append(f"### {c['case']}")
        for d in s["defects"]:
            out.append(f"- planted: {d['says']} (locus {', '.join(d['locus'])}): locus error {_g(d['locus_error_damaged'])} → "
                       f"{_g(d['locus_error_final'])}, " + ("not visible in the record" if not d.get("visible", True) else
                                                            "fixed" if d["fixed"] else "halved" if d["halved"] else "not fixed"))
        for a in c["accepted"]:
            out.append(f"- accepted (round {a['round']}): {a['title']}: distance from the truth {_g(a['distance_before'])} → "
                       f"{_g(a['distance_after'])}" + (" (damage)" if a["damage"] else ""))
        failed = [x for x in c["proposals"] if x.get("verdict") == "failed" or x["status"] == "refused"]
        if failed:
            out.append(f"- not taken: {len(failed)} (" + "; ".join(f"{x['title']}: {(x.get('verdict_why') or x.get('why') or '')[:80]}"
                                                         for x in failed[:4]) + ")")
        out.append("")
    return "\n".join(out) + "\n"
