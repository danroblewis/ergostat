"""Everything a control engineer works out for one loop, from the model and the record: what its
controller moves (u) and what it holds (y), the process between them identified, the controller's
law as its block writes it, what the two make together (step responses, Bode, margins), how the
loop is doing (performance monitoring), and what could be changed (proposals.py): the process
written into the model, a tuning by SIMC, a step test to identify it deliberately."""

from __future__ import annotations

import bisect
import hashlib
import json
import math
import time

from ..durations import human as dur
from ..spec.ir import Spec
from . import experiments, ident, lti, monitor, record, tuning

DECIMATE = 240              # points of a series sent to the page
LAW = ("gain", "integral-time", "deadband", "resolution", "limits")
STARTUP = 10                # controller periods after ergostat starts that are its start, not its working


def model_process(spec: Spec, goal: str) -> dict | None:
    """The loop's process as the model writes it (the goal's ``process:``), in lti's terms (seconds)."""
    pr = spec.goals[goal].process
    if not pr:
        return None
    if pr["form"] == "integrating":
        return {"form": "integrating", "K": pr["gain"] / 3600.0, "theta": pr["theta"] or 0.0}
    return {"form": "fopdt", "K": pr["gain"], "tau": pr["tau"], "theta": pr["theta"] or 0.0}


def found_process(r: dict) -> dict | None:
    if not r.get("found"):
        return None
    if r["form"] == "integrating":
        return {"form": "integrating", "K": r["K"], "theta": r["theta"]}
    return {"form": "fopdt", "K": r["K"], "tau": r["tau"], "theta": r["theta"]}


def controller(spec: Spec, sig: record.Signals) -> tuple[dict | None, str, str | None]:
    """The controller's law, when its block writes it: (law, what it is, the block whose law it is)."""
    if sig.how != "setting" or not sig.blocks:
        kinds = sorted({spec.blocks[b].type for b in [*sig.controllers, *sig.blocks] if b in spec.blocks})
        return None, f"its controller is {', '.join(kinds) or 'not known'}: not a linear law written in the model", None
    b = spec.blocks[sig.blocks[0]]
    reads = [r for r in b.reads()]
    only_error = len(reads) == 1 and reads[0].kind == "goal" and reads[0].port == "error"
    if b.type == "onoff" or not only_error:
        return None, (f"{b.name} reads more than its goal's error: its own map, not a linear law" if not only_error
                      else f"{b.name} is on/off"), b.name
    g = b.params.get("gain")
    T = float(b.every) if b.every else None
    if g is None:
        return None, f"{b.name} steps its setting by its error (integral action), but its gain is not written (gain:)", b.name
    if not T:
        return None, f"{b.name} runs when commanded, not every T: its sampling is not known", b.name
    ti = b.params.get("integral-time")
    extra = {k: b.params[k] for k in ("deadband", "resolution", "limits") if b.params.get(k) is not None}
    if ti:                                               # velocity form: Δu = Kc (Δe + T/τI e)
        return {"form": "PI", "Kc": float(g), "Ti": float(ti), "T": T, **extra}, f"PI, run every {T:g}s", b.name
    return {"form": "I", "g": float(g), "T": T, **extra}, f"integral action, run every {T:g}s", b.name


def key(spec: Spec, goal: str) -> str:
    """What this loop's analysis depends on in the model: its structure, its goal's process and the
    gains its blocks write. A decision (dismissed, accepted) holds until it changes."""
    from ..numbers import version as ver
    sig = record.signals(spec, goal)
    blocks = {n: {k: spec.blocks[n].params.get(k) for k in LAW}
              for n in ([*sig.blocks, *sig.controllers] if sig else []) if n in spec.blocks}
    pr = spec.goals[goal].process
    data = [ver.structure(spec), goal, {k: v for k, v in (pr or {}).items() if k != "where"}, blocks]
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()[:10]


def _thin(xs: list, k: int) -> list:
    """Every k-th value, each the last reading in its k (a bucket with none does not hide its neighbours')."""
    out = []
    for i in range(0, len(xs), k):
        x = next((v for v in reversed(xs[i:i + k]) if v is not None), None)
        out.append(None if x is None else round(x, 6) if isinstance(x, float) else x)
    return out




def tests_in(p, goal: str, since: float, until: float) -> list[dict]:
    """The step tests the record holds for this loop: when each started, stepped back and finished."""
    out = {}
    for e in p.events.query(n=None, item=goal, type="steptest.*", since=since, until=until):
        tid = e["data"].get("test")
        if tid is None:
            continue
        t = out.setdefault(tid, {"id": tid})
        if e["type"] == "steptest.started":
            t["started"], t["amount"], t["hold"] = e["time"], e["data"].get("amount"), e["data"].get("hold")
            t["from"], t["plant"], t["seq"] = e["data"].get("from"), e["data"].get("plant"), e.get("seq")
        elif e["type"] == "steptest.stepped":
            t["up" if e["data"].get("phase") == "up" else "back"] = e["time"]
            if e["data"].get("phase") == "up" and e["data"].get("moved") is not None:
                t["moved"] = e["data"]["moved"]
        elif e["type"] == "steptest.finished":
            t["finished"], t["how"], t["plant_after"] = e["time"], e["data"].get("how"), e["data"].get("plant")
    return [t for t in out.values() if t.get("started")]


def own_delay(p, sig: record.Signals, block: str | None, until: float) -> dict:
    """The controller's own delay, from its last runs: how old the reading of y it acted on was (the
    time since y's sensor last read, when it started) and how long a run took before its move was
    made (Åström & Wittenmark §8.3). It adds to the process's dead time in the loop."""
    if block is None:
        return {"delay": 0.0}
    since = until - 3 * 3600.0
    starts = [e["time"] for e in p.events.query(n=200, type="agent.started", item=block, since=since, until=until)]
    runs = [float(e["data"].get("seconds") or 0) for e in p.events.query(n=200, type="agent.ran", item=block, since=since,
                                                                         until=until)]
    if not starts:
        return {"delay": 0.0}
    kind, _, name = sig.y.partition(".")
    reads = sorted(t for s in series_sensors(p, name) for t, _ in p.measurements.range(f"sensor/{s}", since, until))
    ages = []
    for t in starts:
        i = bisect.bisect_right(reads, t)
        if i:
            ages.append(t - reads[i - 1])
    med = lambda xs: sorted(xs)[len(xs) // 2] if xs else 0.0     # noqa: E731
    age, run = med(ages), med(runs)
    return {"delay": age + run, "age": age, "run": run, "runs": len(starts)}


def series_sensors(p, name: str) -> list[str]:
    from .. import series
    return series._sensors(p.model, name)


def _test_windows(p, sig: record.Signals, tests: list[dict]) -> tuple[dict, list[tuple[int, int]], list[int], list[int]] | None:
    """The finished step tests, each read on its own span at the sensor's resolution, as one data set
    of several experiments: (the record, the experiments, fitted, held out). One test: its step up
    fitted, its step back held out; several: all but the last fitted, the last held out whole."""
    parts = []
    for t in tests:
        since, until, n = record.fine(p, sig, t["started"] - 20.0, t["finished"])
        parts.append((t, record.read(p, sig, since, until, n)))
    if not parts:
        return None
    d = {"t": [], "u": [], "y": [], "e": [], "others": {o: [] for o in sig.others}, "h": parts[0][1]["h"],
         "since": parts[-1][1]["since"], "until": parts[-1][1]["until"], "r": parts[0][1]["r"]}
    segs, est, val = [], [], []
    for i, (t, x) in enumerate(parts):
        a = len(d["t"])
        for k in ("t", "u", "y", "e"):
            d[k] += x[k]
        for o in sig.others:
            d["others"][o] += x["others"][o]
        b = len(d["t"])
        segs.append((a, b))
        ib = a + int((t["back"] - x["since"]) / x["h"])
        if len(parts) == 1:
            est += list(range(a, ib))
            val += list(range(ib, b))
        elif i < len(parts) - 1:
            est += list(range(a, b))
        else:
            val += list(range(a, b))
    d["last"] = segs[-1]
    return d, segs, est, val


def identify(p, sig: record.Signals, at: float | None = None) -> tuple[dict, dict]:
    """The process identified from the record, and the record it read: from the step tests that
    finished well (open loop, all of them together), and from the loop working (closed loop, the
    recent record at the sensor's resolution); the one the record supports best is kept (proposable
    first, then with its numbers told apart, then the more precise, by the standard errors: the two
    are held out on different records, so their fits are not compared), and the other is said beside
    it."""
    since, until, n = record.grid(p, sig, at, fine=True)
    d = record.read(p, sig, since, until, n)
    noise = _noise(d["y"])
    ref_since = record.grid(p, sig, at)[0]
    tests = [t for t in tests_in(p, sig.goal, ref_since, until) if t.get("back") and t.get("finished")
             and str(t.get("how", "")).startswith("done")]
    found = [ident.identify(d["h"], d["t"], d["u"], d["y"], d["others"], noise=noise)]
    found[0]["record"] = d
    if tests:
        got = _test_windows(p, sig, tests)
        if got is not None:
            dt, segs, est, val = got
            r = ident.identify(dt["h"], dt["t"], dt["u"], dt["y"], dt["others"], est, val, closed_loop=False,
                               segments=segs, noise=_noise(dt["y"]) or noise)
            r["test"] = tests[-1]
            r["tests_used"] = [t["id"] for t in tests]
            r["record"] = dt
            found.insert(0, r)
    got = around_step(p, sig, d, noise)
    if got is not None:
        found.append(got)
    best = max(found, key=experiments.rank)
    other = next((r for r in found if r is not best), None)
    if other is not None and other.get("found"):
        o = other.get("outside_step")
        best["instead_of"] = {"from": "the step tests" if other.get("test") else
                              ("outside steps" if len(o.get("steps") or []) > 1 else "an outside step") if o
                              else "the loop working",
                              **{k: other.get(k) for k in ("K", "tau", "theta", "fit_val", "why", "se")}}
    return best, best.pop("record")


def around_step(p, sig: record.Signals, d: dict, noise: float | None) -> dict | None:
    """The process identified from the record around the outside steps (bursts of arrivals at the goal's stock, jumps of
    a measured input beside the path), fitted together as experiments (``experiments``), those inputs fitted beside u: a
    step excites the loop from outside, so the estimate leans less toward the controller's inverse than one from the loop
    working (Ljung §13.4)."""
    spec = p.model.spec
    kind, _, name = sig.y.partition(".")
    from .. import series
    ins = {f"flow.{f.name}": series.rate(p, f.name, d["since"], d["until"], len(d["t"]), changes=False)
           for f in (spec.flows_of(name) if kind == "stock" else []) if f.target == name and f.sensors
           and f"flow.{f.name}" not in (sig.u, *sig.path)}
    ins = {**{r: (v or [None])[0] for r, v in ins.items() if v and any(x is not None for x in v[0])}, **d["others"]}
    r = experiments.identify_around(d["h"], d["t"], d["u"], d["y"], ins, noise)
    if r is None:
        return None
    o = r["outside_step"]
    ws = [e["buckets"] for e in o["experiments"]] or [[0, len(d["t"])]]

    def cut(xs):                                   # the experiments one after another, as _test_windows reads them
        return [x for a, b in ws for x in xs[a:b]]
    r["record"] = {**d, **{x: cut(d[x]) for x in ("t", "u", "y", "e")}, "others": {k: cut(xs) for k, xs in d["others"].items()},
                   "since": o["since"], "until": o["until"],     # drawn: the held-out experiment, as for step tests
                   "last": (sum(b - a for a, b in ws[:-1]), sum(b - a for a, b in ws))}
    return r


def windows_left_out(p, sig: record.Signals, d: dict, tests: list[dict], lag: float) -> list[tuple[float, float]]:
    """What monitoring leaves out (Jelali ch. 2-3): each step test (a deliberate excursion with the
    loop held), and each start (ergostat started, or the record's own start), for ten controller
    periods or three of τ + θ, whichever is longer."""
    T = sig.period or d["h"]
    start = max(STARTUP * T, 3 * lag, 120.0)
    out = [(t["started"], t.get("finished") or d["until"]) for t in tests]
    starts = [e["time"] for e in p.events.query(n=50, type="ergostat.started", since=d["since"] - start, until=d["until"])]
    oldest = min((x for x in (p.events.first_time(), p.measurements.first_time()) if x), default=None)
    if oldest is not None and oldest >= d["since"] - 1:
        starts.append(oldest)
    out += [(t, t + start) for t in starts]
    return sorted(out)


def steady(d: dict, sig: record.Signals, op: str, tol: float, lag: float, left_out: list[tuple[float, float]],
           res: float | None) -> str | None:
    """Why the loop is not yet in steady operation, for a step test (Seborg et al. §7.2: a bump test
    starts from steady state), or None: the record past its start covers ten controller periods and
    three of τ + θ (ten minutes at least), and over the last five periods (three minutes at least)
    the error has been within its tolerance on average and not drifting (its two halves' means within
    it of each other: the noise alone does not keep a test waiting), and u away from its limits."""
    T = sig.period or d["h"]
    need = max(10 * T, 3 * lag, 600.0)
    last = max((b for _, b in left_out if b <= d["until"]), default=d["since"])
    have = d["until"] - max(d["since"], last)
    if have < need:
        return (f"waiting for steady operation: {dur(max(have, 0))} of record since "
                f"{'its start' if left_out else 'the record began'}, of the {dur(need)} a test starts from")
    quiet_for = max(5 * T, 180.0)
    idx = [i for i, t in enumerate(d["t"]) if t >= d["until"] - quiet_for]
    es = [d["e"][i] for i in idx if d["e"][i] is not None]
    band = max(tol, 1e-12)

    def off(e):
        return e < -band if op in ("<=", "<") else e > band if op in (">=", ">") else abs(e) > band
    half = len(es) // 2
    mean = sum(es) / len(es) if es else None
    drift = abs(sum(es[half:]) / max(1, len(es) - half) - sum(es[:half]) / max(1, half)) if half else None
    if not es or off(mean) or (drift is not None and drift > band):       # level and not drifting; noise is not a reason
        return f"waiting for steady operation: the error has not settled within its tolerance over {dur(quiet_for)}"
    lo, hi = sig.limits[:2] if sig.how == "setting" else (None, None)
    us = [d["u"][i] for i in idx if d["u"][i] is not None]
    near = (res or 0.0) + 1e-9
    if us and ((lo is not None and min(us) <= lo + near) or (hi is not None and max(us) >= hi - near)):
        return f"waiting for steady operation: u has been at its limit ({lo:g} to {hi:g}) in the last {dur(quiet_for)}"
    return None


def resolution(law: dict | None, us: list) -> float | None:
    """The least step the setting takes: its block's ``resolution:``, else the least change between
    two of the values it was read at."""
    if law and law.get("resolution"):
        return float(law["resolution"])
    vals = sorted({round(x, 9) for x in us if x is not None})
    diffs = [b - a for a, b in zip(vals, vals[1:], strict=False) if b - a > 1e-9]
    return min(diffs) if diffs else None


def analyse(p, goal: str, at: float | None = None) -> dict | None:
    """The loop's control analysis, for the page (``/api/loop-control``)."""
    spec: Spec = getattr(p.model, "spec", None)
    if spec is None or goal not in spec.goals:
        return None
    sig = record.signals(spec, goal)
    g = spec.goals[goal]
    out: dict = {"goal": goal, "y": f"{g.of.kind}.{g.of.name}", "key": key(spec, goal), "op": g.hold.op,
                 "setpoint": g.hold.value, "tolerance": g.tolerance,         # (and the systems its goal and stock are in)
                 "systems": sorted({s for x in (g.system, spec.owner(g.of)) for s in spec.chain(x)})}
    if sig is None:
        out["why"] = ("nothing its controller moves is one setting or one valve: it closes the long way, through queues "
                      "and the blocks that work them off, so it has no one process to identify")
        return out
    out.update(u=sig.u, how=sig.how, blocks=sig.blocks, controllers=sig.controllers, period=sig.period, path=sig.path,
               others=sig.others, known=sig.known, limits=sig.limits)
    declared = model_process(spec, goal)
    out["declared"] = {**{k: v for k, v in g.process.items() if k != "where"},
                       "where": str(g.process["where"]) if g.process.get("where") else None} if g.process else None
    law, law_says, law_block = controller(spec, sig)
    integral = law is not None or "integral action" in law_says
    until = at if at is not None else time.time()
    if law is not None:
        law = {**law, **{k: v for k, v in own_delay(p, sig, law_block, until).items() if k != "runs"}}
    out["controller"] = {"law": law, "says": law_says, "block": law_block, "integral": integral}
    r, d = identify(p, sig, at) if not sig.known else ({"found": False, "why": [sig.known]}, None)
    if d is None:
        since, until_, n = record.grid(p, sig, at, fine=True)
        d = record.read(p, sig, since, until_, n)
    lo, hi = d["since"], d["until"]
    idx = list(range(*d["last"])) if d.get("last") else list(range(len(d["t"])))
    idx = [i for i in idx if lo <= d["t"][i] <= hi + 60]
    k = max(1, len(idx) // DECIMATE)
    sub = lambda xs: [xs[i] for i in idx]       # noqa: E731
    out["record"] = {"t": [round(x, 3) for x in sub(d["t"])[::k]], "u": _thin(sub(d["u"]), k), "y": _thin(sub(d["y"]), k),
                     "since": d["t"][idx[0]] - d["h"] / 2 if idx else lo, "until": d["t"][idx[-1]] + d["h"] / 2 if idx else hi,
                     "h": d["h"]}
    pred = r.pop("pred", None)
    upart = r.pop("u_part", None)
    if pred is not None:
        out["record"]["yhat"] = _thin(sub(pred), k)
        if r.get("gains") and upart is not None:
            out["record"]["yhat_u"] = _thin(sub(upart), k)
        out["record"]["held_from"] = r["outside_step"]["held"] if r.get("outside_step") else \
            r["test"]["back"] if r.get("test") and len(r.get("tests_used") or []) == 1 else \
            r["test"]["started"] if r.get("test") else d["t"][int(len(d["t"]) * (1 - ident.HOLD_OUT))]
    out["identified"] = r
    mon_since, mon_until, mon_n = record.grid(p, sig, at)
    dm = record.read(p, sig, mon_since, mon_until, mon_n)
    out["tests"] = tests_in(p, goal, dm["since"], dm["until"])
    guess = found_process(r)
    proc = declared or (guess if r.get("told_apart") else None)   # a guess too unsure is not worked with
    if proc is guess and guess and guess["form"] == "integrating" and (law or {}).get("form") == "I":
        proc = None            # integral action never settles an integrator: the guess, not the loop, is what fails
    out["process_from"] = "model" if declared else "identified" if proc else None
    if proc:
        out["process"] = proc
        out["process_step"] = lti.process_step(proc)
        out["bode"] = lti.bode(proc, law)
        if law:
            m = lti.margins(proc, law)
            out["margins"] = {k2: tuning.finite(v) for k2, v in m.items()}
            out["closed_step"] = lti.closed_step(proc, law)
            out["nonlinear"] = lti.nonlinear(proc, law, m)
    if law and (proc or guess):
        out["robust"] = robustness(proc or guess, r, declared is not None, law)
    theta = (proc or {}).get("theta")
    lag = ((proc or {}).get("tau") or 0.0) + ((proc or {}).get("theta") or 0.0)     # only a process told apart
    left = windows_left_out(p, sig, dm, out["tests"], lag)
    out["left_out"] = left
    out["performance"] = monitor.performance(dm, g.hold.op, g.tolerance, sig.period, theta, sig.limits, sig.how,
                                             left_out=left, delay=(law or {}).get("delay") or 0.0)
    if proc and law and out.get("margins"):
        out["predicted"] = {"overshoot": out["closed_step"].get("overshoot"), "settling": out["closed_step"].get("settling"),
                            "nonlinear": out.get("nonlinear") or []}
    out["tuning"] = suggest(spec, sig, law, law_block, proc, declared is not None, out.get("robust")) if integral else \
        {"why": f"no linear controller to tune: {law_says}"}
    out["noise"] = _noise(d["y"])
    out["sensor_every"] = record._every(spec, sig.y)
    out["quiet"] = quiet(spec, sig)
    out["error"] = next((x for x in reversed(dm["e"]) if x is not None), None)
    out["resolution"] = resolution(law, dm["u"])
    out["u_range"] = _range(dm["u"], left)
    out["flow"] = sig.flow
    out["u_now"] = next((x for x in reversed(dm["u"]) if x is not None), None)
    out["sensitivity"] = _sensitivity(dm, left)
    out["steady"] = steady(dm, sig, g.hold.op, g.tolerance, lag, left, out["resolution"]) if sig.how == "setting" else None
    return out


def _kept(d: dict, xs: list, left: list) -> list:
    return [x for t, x in zip(d["t"], xs, strict=True) if x is not None and not any(a <= t <= b for a, b in left)]


def _range(us: list, left: list) -> list | None:
    got = [x for x in us if x is not None]
    return [min(got), max(got)] if got else None


def _sensitivity(d: dict, left: list) -> float | None:
    """The most y moved per unit of u in the record (its working, not its start or a test): the
    spread of y over the spread of u. An upper bound on |K| when nothing else moved y."""
    us, ys = _kept(d, d["u"], left), _kept(d, d["y"], left)
    if len(us) < 10 or len(ys) < 10 or max(us) <= min(us):
        return None
    return (max(ys) - min(ys)) / (max(us) - min(us))


def robustness(proc: dict, r: dict, declared: bool, law: dict) -> dict:
    """The loop's margins at the worst the process could be, by the identification's standard errors
    (K ± 2σ, θ + 2σ, τ ± 2σ); for a process the model holds, its own numbers with the identification's
    relative errors. Said even when the process is not proposable."""
    se = {k: v for k, v in (r.get("se") or {}).items() if k in ("K", "tau", "theta")}
    if proc["form"] == "integrating" and law["form"] == "I":
        return {"known": False, "why": ("the record's best guess is an integrator, and integral action alone never settles "
                                        "one; the record does not yet tell a long lag from an integrator")}
    if not r.get("found") or not se:
        return {"known": False, "why": "the record does not say how sure the process is (no standard errors)"}
    if declared:
        rel = {k: (se.get(k) / abs(r[k])) if se.get(k) is not None and r.get(k) else None for k in ("K", "tau")}
        se = {"K": rel["K"] * abs(proc["K"]) if rel["K"] is not None else None,
              "tau": rel["tau"] * proc["tau"] if rel.get("tau") is not None and proc.get("tau") else None,
              "theta": se.get("theta")}
    if se.get("K") is None or se.get("theta") is None:
        return {"known": False, "why": "the record does not say how sure its gain or dead time is"}
    out = lti.robust(proc, law, se)
    out["se"] = {k: v for k, v in se.items() if v is not None}
    if out.get("known"):
        out["words"] = ("may be unstable" if not out["stable"] else "stable, with little to spare"
                        if out.get("gain_margin") is not None and out["gain_margin"] < 2 else "robustly stable")
    return out


def quiet(spec: Spec, sig: record.Signals) -> list[str]:
    """The blocks that move the measured inputs beside the path (what else changes y): held still in a
    step test too, so the step is all that moves it. Not the world (a block that reads nothing), which
    cannot be held."""
    out = set()
    for ref in sig.others:
        kind, _, name = ref.partition(".")
        movers = [spec.setter_of(name)] if kind == "auxiliary" else \
            [spec.actuator_of(f.name) for f in spec.flows_of(name)] if kind == "stock" else []
        for b in movers:
            if b is not None and b.machine and b.reads() and b.name not in sig.blocks:
                out.add(b.name)
    return sorted(out)


def _noise(y: list) -> float | None:
    """The size of y's own jitter: the spread of its changes from one bucket to the next, over √2."""
    got = [v for v in y if v is not None]
    if len(got) < 10:
        return None
    dd = sorted(abs(b - a) for a, b in zip(got, got[1:], strict=False))
    med = dd[len(dd) // 2]
    return 1.4826 * med / math.sqrt(2)


def suggest(spec: Spec, sig: record.Signals, law: dict | None, block: str | None, proc: dict | None, accepted: bool,
            rob: dict | None = None) -> dict:
    """A tuning by SIMC for the controller's form, checked: its margins and its closed-loop step,
    beside the controller as it is; and, when the worst the process could be leaves a gain margin
    under 2, a detuning that brings it to 2 (Åström & Hägglund §4.8)."""
    if not proc:
        return {"why": "the process is not identified yet"}
    if block is None or sig.how != "setting":
        return {"why": "no linear controller to tune: " + (sig.known or "its controller is not a written law")}
    b = spec.blocks[block]
    T = float(b.every) if b.every else None
    form = law["form"] if law else ("PI" if b.params.get("integral-time") else "I")
    own = {k: v for k, v in (law or {}).items() if k in ("delay", "age", "run", "deadband", "resolution", "limits")}
    s = tuning.simc(lti.effective(proc, own), form, T)
    if s is None:
        return {"why": f"SIMC has no {form} rule for this process"}
    s = {**s, **own}
    new = tuning.judged(proc, s)
    out = {"form": form, "simc": s, "margins": {k: tuning.finite(v) for k, v in new["margins"].items()},
           "step": new["step"], "block": block, "accepted_process": accepted}
    if law is not None and rob and rob.get("known") and rob.get("gain_margin") is not None and \
            (rob["gain_margin"] < 2 or not rob["stable"]):
        dt = tuning.detuned(law, rob["gain_margin"])
        dj = tuning.judged(proc, dt)
        out["detune"] = {"controller": dt, "margins": {k: tuning.finite(v) for k, v in dj["margins"].items()},
                         "step": dj["step"], "robust": lti.robust(proc, dt, rob["se"])}
    if law is None:
        out["why"] = f"{block}'s gain is not written (gain: on the block), so it cannot be changed in the model"
    elif not accepted:
        out["why"] = "the process it is tuned for is not in the model yet: accept it first"
    elif not tuning.worth(law, s, "g" if form == "I" else "Kc"):
        out["why"] = "the controller is already within a fifth of it"
    elif not new["margins"]["stable"]:
        out["why"] = "the suggestion does not settle the loop as worked out: not offered"
    return out
