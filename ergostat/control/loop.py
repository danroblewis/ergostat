"""Everything a control engineer works out for one loop, from the model and the record: what its
controller moves (u) and what it holds (y), the process between them identified, the controller's
law as its block writes it, what the two make together (step responses, Bode, margins), how the
loop is doing (performance monitoring), and what could be changed (proposals.py): the process
written into the model, a tuning by SIMC, a step test to identify it deliberately."""

from __future__ import annotations

import hashlib
import json
import math

from ..spec.ir import Spec
from . import ident, lti, monitor, record, tuning

DECIMATE = 240              # points of a series sent to the page


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
    if ti:                                               # velocity form: Δu = Kc (Δe + T/τI e)
        return {"form": "PI", "Kc": float(g), "Ti": float(ti), "T": T}, f"PI, run every {T:g}s", b.name
    return {"form": "I", "g": float(g), "T": T}, f"integral action, run every {T:g}s", b.name


def key(spec: Spec, goal: str) -> str:
    """What this loop's analysis depends on in the model: its structure, its goal's process and the
    gains its blocks write. A decision (dismissed, accepted) holds until it changes."""
    from ..numbers import version as ver
    sig = record.signals(spec, goal)
    blocks = {n: {k: spec.blocks[n].params.get(k) for k in ("gain", "integral-time")}
              for n in ([*sig.blocks, *sig.controllers] if sig else []) if n in spec.blocks}
    pr = spec.goals[goal].process
    data = [ver.structure(spec), goal, {k: v for k, v in (pr or {}).items() if k != "where"}, blocks]
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()[:10]


def _thin(xs: list, k: int) -> list:
    return [None if x is None else (round(x, 6) if isinstance(x, float) else x) for x in xs[::k]]


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
        elif e["type"] == "steptest.stepped":
            t["up" if e["data"].get("phase") == "up" else "back"] = e["time"]
        elif e["type"] == "steptest.finished":
            t["finished"], t["how"] = e["time"], e["data"].get("how")
    return [t for t in out.values() if t.get("started")]


def identify(p, sig: record.Signals, at: float | None = None) -> tuple[dict, dict]:
    """The process identified from the record, and the record it read: from the last step test that
    finished well (open loop), and from the loop working (closed loop); the one the record supports
    best is kept (proposable first, then with its numbers told apart, then following the record held
    out better), and the other is said beside it."""
    since, until, n = record.grid(p, sig, at)
    d = record.read(p, sig, since, until, n)
    tests = [t for t in tests_in(p, sig.goal, since, until) if t.get("back") and t.get("finished")
             and str(t.get("how", "")).startswith("done")]
    found = [ident.identify(d["h"], d["t"], d["u"], d["y"], d["others"])]
    if tests:
        t = tests[-1]
        h = d["h"]
        i0 = max(0, int((t["started"] - since) / h) - 3)
        ib = int((t["back"] - since) / h)
        i1 = min(n, int((t["finished"] - since) / h) + 1)
        r = ident.identify(h, d["t"], d["u"], d["y"], d["others"], list(range(i0, ib)), list(range(ib, i1)), closed_loop=False)
        r["test"] = t
        found.insert(0, r)
    best = max(found, key=lambda r: (bool(r.get("proposable")), bool(r.get("told_apart")), r.get("fit_val") or -1e9))
    other = next((r for r in found if r is not best), None)
    if other is not None and other.get("found"):
        best["instead_of"] = {"from": "a step test" if other.get("test") else "the loop working",
                              **{k: other.get(k) for k in ("K", "tau", "theta", "fit_val", "why")}}
    return best, d


def analyse(p, goal: str, at: float | None = None) -> dict | None:
    """The loop's control analysis, for the page (``/api/loop-control``)."""
    spec: Spec = getattr(p.model, "spec", None)
    if spec is None or goal not in spec.goals:
        return None
    sig = record.signals(spec, goal)
    g = spec.goals[goal]
    out: dict = {"goal": goal, "y": f"{g.of.kind}.{g.of.name}", "key": key(spec, goal), "op": g.hold.op,
                 "setpoint": g.hold.value, "tolerance": g.tolerance}
    if sig is None:
        out["why"] = ("nothing its controller moves is one setting or one valve: it closes the long way, through queues "
                      "and the blocks that work them off, so it has no one process to identify")
        return out
    out.update(u=sig.u, how=sig.how, blocks=sig.blocks, controllers=sig.controllers, period=sig.period, path=sig.path,
               others=sig.others, known=sig.known)
    declared = model_process(spec, goal)
    out["declared"] = {**{k: v for k, v in g.process.items() if k != "where"},
                       "where": str(g.process["where"]) if g.process.get("where") else None} if g.process else None
    law, law_says, law_block = controller(spec, sig)
    integral = law is not None or "integral action" in law_says
    out["controller"] = {"law": law, "says": law_says, "block": law_block, "integral": integral}
    r, d = identify(p, sig, at) if not sig.known else ({"found": False, "why": [sig.known]}, None)
    if d is None:
        since, until, n = record.grid(p, sig, at)
        d = record.read(p, sig, since, until, n)
    k = max(1, len(d["t"]) // DECIMATE)
    out["record"] = {"t": _thin(d["t"], k), "u": _thin(d["u"], k), "y": _thin(d["y"], k), "since": d["since"],
                     "until": d["until"], "h": d["h"]}
    pred = r.pop("pred", None)
    if pred is not None:
        out["record"]["yhat"] = _thin(pred, k)
        out["record"]["held_from"] = r["test"]["back"] if r.get("test") else d["t"][int(len(d["t"]) * (1 - ident.HOLD_OUT))]
    out["identified"] = r
    out["tests"] = tests_in(p, goal, d["since"], d["until"])
    proc = declared or (found_process(r) if r.get("told_apart") else None)   # a guess too unsure is not worked with
    out["process_from"] = "model" if declared else "identified" if proc else None
    if proc:
        out["process"] = proc
        out["process_step"] = lti.process_step(proc)
        out["bode"] = lti.bode(proc, law)
        if law:
            m = lti.margins(proc, law)
            out["margins"] = {k2: tuning.finite(v) for k2, v in m.items()}
            st = lti.closed_step(proc, law)
            out["closed_step"] = st
    theta = (proc or {}).get("theta")
    out["performance"] = monitor.performance(d, g.hold.op, g.tolerance, sig.period, theta, sig.limits, sig.how)
    if proc and law and out.get("margins"):
        out["predicted"] = {"overshoot": out["closed_step"].get("overshoot"), "settling": out["closed_step"].get("settling")}
    out["tuning"] = suggest(spec, sig, law, law_block, proc, declared is not None) if integral else \
        {"why": f"no linear controller to tune: {law_says}"}
    out["noise"] = _noise(d["y"])
    out["sensor_every"] = record._every(spec, sig.y)
    out["quiet"] = quiet(spec, sig)
    out["error"] = next((x for x in reversed(d["e"]) if x is not None), None)
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


def suggest(spec: Spec, sig: record.Signals, law: dict | None, block: str | None, proc: dict | None, accepted: bool) -> dict:
    """A tuning by SIMC for the controller's form, checked: its margins and its closed-loop step,
    beside the controller as it is."""
    if not proc:
        return {"why": "the process is not identified yet"}
    if block is None or sig.how != "setting":
        return {"why": "no linear controller to tune: " + (sig.known or "its controller is not a written law")}
    b = spec.blocks[block]
    T = float(b.every) if b.every else None
    form = law["form"] if law else ("PI" if b.params.get("integral-time") else "I")
    s = tuning.simc(proc, form, T)
    if s is None:
        return {"why": f"SIMC has no {form} rule for this process"}
    new = tuning.judged(proc, s)
    out = {"form": form, "simc": s, "margins": {k: tuning.finite(v) for k, v in new["margins"].items()},
           "step": new["step"], "block": block, "accepted_process": accepted}
    if law is None:
        out["why"] = f"{block}'s gain is not written (gain: on the block), so it cannot be changed in the model"
    elif not accepted:
        out["why"] = "the process it is tuned for is not in the model yet: accept it first"
    elif not tuning.worth(law, s, "g" if form == "I" else "Kc"):
        out["why"] = "the controller is already within a fifth of it"
    elif not new["margins"]["stable"]:
        out["why"] = "the suggestion does not settle the loop as worked out: not offered"
    return out
