"""Outside steps as experiments (Ljung, *System Identification*, §14.3, ``merge``, as ``loop._test_windows`` does for
step tests): every large step of an input from outside the loop (a burst of arrivals, a jump of a measured input beside
the path) is found, its window around it read, and the windows fitted together as one data set of several experiments,
the same K, τ and θ, each its own start and level, the last held out whole.

The windows are sized in passes. Pass 0 is y's own excursion (``ident.around``: fitted to where y comes half way back).
Each later pass sizes them from the process the kept pass found, its settling S = max(θ + 4τ, SPAN_MIN (τ + θ) − P h):
fitted from P buckets before the step to S after it. A later pass is kept only when it is not worse by ``rank`` (the
order ``loop.identify`` keeps); otherwise the kept one stays and ``passes`` says why. A step whose window runs past the
record, or whose window has an input with no readings, is dropped and said, never clipped or filled from elsewhere."""

from __future__ import annotations

import math
import time

from ..durations import human as dur
from . import ident

P = ident.POINTS_MIN
STEPS_MAX = 6            # steps fitted together, at most (each multiplies the record searched)
PASSES_MAX = 3           # fits in one call, at most, pass 0 included


def rank(r: dict) -> tuple:
    """``loop.identify``'s order: proposable, then told apart, then the more precise."""
    return bool(r.get("proposable")), bool(r.get("told_apart")), -ident.precision(r)


def _hm(t: float) -> str:
    return time.strftime("%H:%M", time.localtime(t))


def steps_of(ins: dict[str, list]) -> list[dict]:
    """The outside steps of every input, in bucket order. Steps on different inputs within P buckets of each other are
    one, at the earlier bucket, naming each input; two on one input within P are one already (``outside_steps`` keeps the
    larger: a burst's rise and fall). The STEPS_MAX largest by |jump| are kept, the earlier first among equals."""
    out: list[dict] = []
    for k, j, name in sorted((k, j, nm) for nm, xs in ins.items() for k, j in ident.outside_steps(xs)):
        if out and k - out[-1]["k"] < P:
            s = out[-1]
            s["inputs"] += [] if name in s["inputs"] else [name]
            s["jump"] = max(s["jump"], abs(j))
        else:
            out.append({"k": k, "jump": abs(j), "inputs": [name]})
    big = sorted(range(len(out)), key=lambda i: (-out[i]["jump"], out[i]["k"]))[:STEPS_MAX]
    return [out[i] for i in sorted(big)]


def settling(r: dict, h: float) -> float:
    tau, th = r["tau"], r["theta"]
    return max(th + 4 * tau, ident.SPAN_MIN * (tau + th) - P * h)


def _merge(steps: list[dict], ends) -> list[dict]:
    """Each step's window [k − P, f), those that overlap one experiment over their union, held out to its last step's b."""
    exps: list[dict] = []
    for s in steps:
        f, b = ends(s)
        if exps and s["k"] - P < exps[-1]["f"]:
            e = exps[-1]
            e["steps"].append(s)
            e["f"] = max(e["f"], f)
            e["b"] = max(b, e["f"])
        else:
            exps.append({"a": s["k"] - P, "f": f, "b": b, "steps": [s]})
    return exps


def _plan(t: list, u: list, ins: dict, steps: list[dict], ends, sized: bool, h: float) -> tuple[list[dict], list]:
    """The experiments, and (bucket, line) for each step dropped: an input with no readings in its window, or
    (``sized``, a pass from the process) a window past the record's end: b with one experiment, f with several."""
    n, live, dropped = len(t), list(steps), []
    while live:
        exps = _merge(live, ends)
        one = len(exps) == 1
        bad = []
        for e in exps:
            end = e["b"] if one else e["f"]
            empty = next((nm for nm, xs in (("u", u), *ins.items()) if all(x is None for x in xs[e["a"]:end])), None)
            if empty:
                bad += [(s, f"the step at {_hm(t[s['k']])}: {empty} has no readings in its window") for s in e["steps"]]
        if not bad and sized:
            for s in ([exps[0]["steps"][-1]] if one and exps[0]["b"] > n else [] if one else
                      [s for s in live if ends(s)[0] > n]):
                need = (exps[0]["b"] if one else ends(s)[0]) - s["k"]
                bad.append((s, f"the step at {_hm(t[s['k']])} ({', '.join(s['inputs'])}): the record after it covers "
                               f"{dur((n - s['k']) * h)} of the {dur(need * h)} its process needs to settle"))
        if not bad:
            return exps, dropped
        for s, line in bad:
            if s in live:
                live.remove(s)
                dropped.append((s["k"], line))
    return [], dropped


def _fit(h: float, t: list, u: list, y: list, ins: dict, exps: list[dict], noise: float | None) -> dict:
    """One ``ident.identify`` over the experiments, each read on its own window and filled only within it."""
    one = len(exps) == 1
    tt, uu, yy, oo = [], [], [], {o: [] for o in ins}
    segs, est, val, spans = [], [], [], []
    for i, e in enumerate(exps):
        a, end = e["a"], (e["b"] if one else e["f"])
        s0 = len(tt)
        tt += t[a:end]
        uu += ident._ffill(u[a:end])
        yy += y[a:end]
        for o, xs in ins.items():
            oo[o] += ident._ffill(xs[a:end])
        segs.append((s0, len(tt)))
        spans.append((a, end))
        if one:
            est, val = list(range(e["f"] - a)), list(range(e["f"] - a, len(tt)))
        else:
            (est if i < len(exps) - 1 else val).extend(range(s0, len(tt)))
    r = ident.identify(h, tt, uu, yy, oo, est, val, segments=None if one else segs, noise=noise)
    first = exps[0]["steps"][0]
    r["outside_step"] = {"at": t[first["k"]], "input": first["inputs"][0], "since": tt[0], "until": tt[-1],
                         "held": tt[val[0]] if val else tt[-1],
                         "steps": [{"at": t[s["k"]], "inputs": s["inputs"], "jump": s["jump"]} for e in exps for s in e["steps"]],
                         "experiments": [{"since": t[a], "until": t[b - 1], "buckets": [a, b], "steps": [t[s["k"]] for s in e["steps"]]}
                                         for (a, b), e in zip(spans, exps, strict=True)]}
    return r


def _worse(new: dict, old: dict) -> str | None:
    for name, a, b in zip(("proposable", "told apart", "precision"), rank(new), rank(old), strict=True):
        if a != b:
            return name if a < b else None
    return None


def _nothing(t: list, lines: list[str]) -> dict:
    return {"found": False, "proposable": False, "told_apart": False, "why": list(lines),
            "outside_step": {"at": t[0], "input": None, "since": t[0], "until": t[-1], "held": t[-1], "steps": [],
                             "experiments": [], "window": "excursion", "passes": [], "dropped": list(lines)}}


def around_steps(h: float, t: list, u: list, y: list, ins: dict[str, list], noise: float | None = None,
                 steps: list[dict] | None = None) -> dict | None:
    """The process identified around the outside steps (``steps_of`` when not given), in at most PASSES_MAX fits."""
    steps = steps_of(ins) if steps is None else steps
    if not steps:
        return None
    every = sorted({s["k"] for s in steps} | {s["k"] for s in steps_of(ins)})
    exc = {s["k"]: ident.excursion(y[:next((j for j in every if j > s["k"]), len(t))], s["k"])[1:] for s in steps}
    #      each step's excursion read up to the next outside step, not into its
    exps, drop = _plan(t, u, ins, steps, lambda s: exc[s["k"]], False, h)
    if not exps:
        return _nothing(t, [x for _, x in drop])
    drops = [drop]                                       # each pass's (bucket, line), the kept pass's said first
    kept, kept_i, used = _fit(h, t, u, y, ins, exps, noise), 0, {s["k"] for e in exps for s in e["steps"]}
    passes = ["kept" if kept.get("found") else f"not found: {'; '.join(kept['why'])}"]
    tried = [[(e["a"], e["f"], e["b"]) for e in exps]]
    for i in range(1, PASSES_MAX):
        if not kept.get("found"):
            passes.append(f"not run: pass {kept_i} found no process")
            break
        if kept.get("tau") is None:
            passes.append("not run: integrating, no settling time to size a window from")
            break
        c = math.ceil(settling(kept, h) / h)
        exps, drop = _plan(t, u, ins, steps, lambda s, c=c: (s["k"] + c, s["k"] + c + max(c, P // 2)), True, h)
        drops.append(drop)
        if not exps and any("has no readings" in x for _, x in drop):
            return _nothing(t, [x for _, x in drop])
        short = [x for k, x in drop if k in used and "covers" in x and x not in kept["why"]]
        if short:              # the kept pass fitted a step its process says is too short: not trusted from there either
            kept = {**kept, "why": kept["why"] + short, "proposable": False}
        if not exps:
            passes.append("not run: no step left whose record covers what its process needs to settle")
            break
        bounds = [(e["a"], e["f"], e["b"]) for e in exps]
        if bounds in tried:
            passes.append(f"not run: its windows are pass {tried.index(bounds)}'s")
            break
        tried.append(bounds)
        r = _fit(h, t, u, y, ins, exps, noise)
        if not r.get("found"):
            passes.append(f"not found: {'; '.join(r['why'])}")
        elif worse := _worse(r, kept):
            passes.append(f"not kept: pass {kept_i} was better ({worse})")
        else:
            kept, kept_i, used = r, i, {s["k"] for e in exps for s in e["steps"]}
            passes.append("kept")
    said: dict[int, str] = {}       # the kept pass's drops, and a later pass's "covers" lines that rule 5 put in its why;
    for k, x in drops[kept_i] + [(k, x) for d in drops[kept_i + 1:] for k, x in d if "covers" in x and x in kept["why"]]:
        said.setdefault(k, x)       # never a line of a pass not kept (its window is not the one the result was fitted on)
    kept["outside_step"].update(window="process" if kept_i else "excursion", passes=passes, dropped=list(said.values()))
    return kept


def identify_around(h: float, t: list, u: list, y: list, ins: dict[str, list], noise: float | None = None) -> dict | None:
    """The process identified around every outside step of ``ins`` (None when there is none)."""
    return around_steps(h, t, u, y, ins, noise)
