"""What the control analysis of a loop offers the owner, and nothing is done until the owner says so:

- **process**: the process identified, written into the goal's ``process:`` (SPEC §8), when the
  record supports it (``ident.judge``);
- **tuning**: the controller's gain (and integral time) set by SIMC for the process the model
  holds, when its block writes its law and the suggestion is checked to settle the loop with
  margins (``tuning``);
- **step test**: a step of u, held, then back, to identify the process deliberately, when the
  record cannot (``steptest.py`` runs it, only once approved).

A proposal is worked out afresh from the record when the loop is looked at; what the page was last
shown is what an Accept applies. An accepted edit is checked like any other (the model must still
compile, else the file is put back) and recorded as ``model.accepted``; a dismissed proposal is not
offered again until what it depends on in the model changes (``loop.key``). Decisions are kept in
``<state>/control/decisions.json``."""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from pathlib import Path

from ..durations import human as dur
from ..numbers import yamledit as ye
from . import ident

OFFERED: dict[str, dict] = {}       # proposal id → what the page was last shown (what an Accept applies)
FILE = "control/decisions.json"
HOLD_LEAST, HOLD_MOST = 120.0, 1800.0


class ProposalError(Exception):
    pass


def _path(p) -> Path:
    return p.dir / FILE


def decisions(p) -> dict:
    try:
        return json.loads(_path(p).read_text())
    except (OSError, ValueError):
        return {}


def _save(p, d: dict) -> None:
    f = _path(p)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=1))
    tmp.replace(f)


def _id(kind: str, goal: str, key: str) -> str:
    return hashlib.sha256(json.dumps([kind, goal, key]).encode()).hexdigest()[:8]


def _sec(x: float) -> str:
    return ye.number(round(x, 1)) + "s" if x < 600 else ye.duration(x / 3600.0)


# ---- the YAML: a goal's process:, a block's gain:

def _name_line(path: Path, line: int, name: str) -> int:
    """The line naming a map (``quality-held:``) at or above the line of its first key."""
    ls = ye.lines_of(path)
    for i in range(min(line, len(ls)) - 1, -1, -1):
        if re.match(rf"^\s*{re.escape(name)}\s*:\s*(#.*)?$", ls[i]):
            return i + 1
    raise ye.EditError(f"{path.name}: {name}: not found above line {line}")


def _children(ls: list[str], name_line: int) -> tuple[int, int | None]:
    """The last line of a map's children, and their indentation."""
    base = ye.indent(ls[name_line - 1])
    end, child = name_line, None
    for i in range(name_line, len(ls)):
        s = ls[i]
        if not s.strip() or s.strip().startswith("#"):
            continue
        if ye.indent(s) <= base:
            break
        child = ye.indent(s) if child is None else child
        end = i + 1
    return end, child


def _key_line(path: Path, name_line: int, key: str) -> int | None:
    ls = ye.lines_of(path)
    end, child = _children(ls, name_line)
    for i in range(name_line, end):
        if ye.indent(ls[i]) == child and re.match(rf"^\s*{re.escape(key)}\s*:", ls[i]):
            return i + 1
    return None


def process_edit(spec, goal: str, lines: list[str]) -> ye.Edit:
    """The goal's ``process:`` written (or written again), its keys ``lines``."""
    g = spec.goals[goal]
    if g.where is None:
        raise ye.EditError(f"goal {goal}: where it is written is not known")
    ye.own(g.where, f"goal {goal}")
    path = Path(g.where.file)
    nl = _name_line(path, g.where.line, goal)
    ls = ye.lines_of(path)
    end, child = _children(ls, nl)
    pad = " " * (child if child is not None else ye.indent(ls[nl - 1]) + 2)
    body = [f"{pad}process:                     # the loop's process, from what its controller moves to what the goal holds"]
    body += [f"{pad}  {x}" for x in lines]
    at = _key_line(path, nl, "process")
    if at is None:
        return ye.Edit(str(path), [ye.Hunk(end + 1, [], body)])
    pend, _ = _children(ls, at)
    return ye.Edit(str(path), [ye.Hunk(at, ls[at - 1:pend], body)])


def gain_edit(spec, block: str, values: dict[str, str]) -> ye.Edit:
    b = spec.blocks[block]
    if b.where is None:
        raise ye.EditError(f"block {block}: where it is written is not known")
    ye.own(b.where, f"block {block}")
    path = Path(b.where.file)
    nl = _name_line(path, b.where.line, block)
    hunks = []
    for k, v in values.items():
        at = _key_line(path, nl, k)
        hunks += (ye.set_value(path, at, k, v) if at else ye.add_key(path, nl, k, v)).hunks
    return ye.Edit(str(path), hunks)


# ---- what is offered

def _unit(spec, ref: str) -> str:
    kind, _, name = ref.partition(".")
    t = spec.measured(kind).get(name)
    return getattr(t, "unit", "") or ""


def _process_lines(spec, a: dict, r: dict) -> list[str]:
    yu, uu = _unit(spec, a["y"]), _unit(spec, a["u"]) + ("/h" if a["how"] == "valve" else "")
    how = ("from a step test, open loop" if r.get("test") else _around(r) or "from the loop working, closed loop")
    when = time.strftime("%Y-%m-%d", time.localtime())
    unit = f"{yu} per {uu}" if yu and uu else ""
    if r["form"] == "integrating":
        gain = r["K"] * 3600.0
        out = ["integrating: true", f"gain: {ye.number(gain)}" + (f"                 # {yu}/h per {uu}" if unit else "")]
    else:
        out = [f"gain: {ye.number(r['K'])}" + (f"                 # {unit}" if unit else ""),
               f"time-constant: {_sec(r['tau'])}"]
    out.append(f"dead-time: {_sec(r['theta'])}" if r["theta"] >= 0.05 else "dead-time: 0")
    out.append(f'identified: "{when}, {how}, {dur(r["span"])} of record"')
    return out


def _around(r: dict) -> str | None:
    """Every outside step it was identified around, and how their windows were chosen (``experiments``)."""
    o = r.get("outside_step")
    if not o:
        return None
    steps = o.get("steps") or [{"at": o["at"], "inputs": [o["input"]]}]
    at = ", ".join(time.strftime("%H:%M", time.localtime(s["at"])) for s in steps)
    ins = ", ".join(dict.fromkeys(x for s in steps for x in s["inputs"]))
    head, each = (f"identified around outside steps at {at} ({ins})", "each window") if len(steps) > 1 else \
        (f"identified around an outside step at {at} ({ins})", "its window")
    if o.get("window") == "process":
        how = f"{each} from the process (θ + 4τ = {dur(r['theta'] + 4 * r['tau'])})"
    else:
        stop = next((x for x in (o.get("passes") or [])[1:] if x != "kept"), None)
        how = f"{each} from y's excursion" + (f" ({stop})" if stop else "")
    return "; ".join([f"{head}, {how}", *(o.get("dropped") or [])])


def _pm(x) -> str:
    return "–" if x is None else f"{x:.3g}"


def _process(p, spec, a: dict, done: dict) -> dict | None:
    r = a.get("identified") or {}
    if not r.get("found") or not r.get("proposable"):
        return None
    pid = _id("process", a["goal"], a["key"])
    if pid in done:
        return None
    se = r.get("se") or {}
    from ..blockdiagram import process_text
    num, den = process_text({"form": r["form"], "gain": r["K"] * (3600.0 if r["form"] == "integrating" else 1),
                             "tau": r.get("tau"), "theta": r["theta"]})
    w = r.get("whiteness") or {}
    ind = r.get("independence") or {}
    parts = [f"{'identified from the step test' if r.get('test') else _around(r) or 'identified from the loop working (closed loop)'} on "
             f"{dur(r['span'])} of record, {r['n_est']} readings fitted and {r['n_val']} held out",
             f"it follows {r['fit_val']:.0f}% of the record held out ({r['fit_est']:.0f}% of what it was fitted to)",
             f"K = {r['K']:.3g} ± {_pm(se.get('K'))}" + (f", τ = {r['tau']:.3g}s ± {_pm(se.get('tau'))}" if r.get("tau") else "")
             + f", θ = {r['theta']:.3g}s ± {_pm(se.get('theta'))} (standard errors)"]
    if w:
        parts.append(f"its errors held out are {'white' if w['white'] else 'not white'} (Ljung–Box Q = {w['q']:.3g} against "
                     f"{w['limit']:.3g} at {w['lags']} lags)")
    if ind:
        parts.append("and independent of u" if ind["ok"] else f"and not independent of u (cross-correlation {ind['max']:.2f} "
                     f"past ±{ind['bound']:.2f}): a model of this order misses some of what u does")
    if r.get("closed_loop") and not r.get("outside_step"):
        parts.append("identified in closed loop: where disturbances are not measured, the estimate leans toward the "
                     "controller's inverse (Ljung ch. 13); a step test identifies it open loop")
    edit = process_edit(spec, a["goal"], _process_lines(spec, a, r))
    return {"id": pid, "kind": "process", "goal": a["goal"], "title": f"{a['goal']}: its process P(s) = {num}/({den})",
            "reason": "; ".join(parts) + ".", "edit": {"files": [edit.as_dict()], "diff": edit.diff()},
            "values": {"form": r["form"], "K": r["K"], "tau": r.get("tau"), "theta": r["theta"]},
            "block": (a.get("blocks") or [None])[0],
            "identified": {k: r.get(k) for k in ("form", "moves", "test", "span", "n_est", "n_val", "fit_val", "fit_est")}}


def _said(m: dict, st: dict) -> str:
    bits = [f"gain margin {_pm(m.get('gain_margin'))}", f"phase margin {_pm(m.get('phase_margin'))}°",
            f"Ms {_pm(m.get('ms'))}"]
    if st.get("overshoot") is not None:
        bits.append(f"overshoot {st['overshoot'] * 100:.0f}%")
    if st.get("settling") is not None:
        bits.append(f"settles in {dur(st['settling'])}")
    if not m.get("stable", True):
        bits.append("does not settle")
    return ", ".join(bits)


def _law_values(s: dict, law: dict) -> tuple[dict, str]:
    """A law's new constants as the block writes them, and the change in words."""
    three = ye.number
    if s["form"] == "I":
        return {"gain": three(s["g"])}, f"gain {ye.number(law['g'])} → {three(s['g'])} a step"
    return ({"gain": three(s["Kc"]), "integral-time": _sec(s["Ti"])},
            f"gain {ye.number(law['Kc'])} → {three(s['Kc'])}, integral time {_sec(law['Ti'])} → {_sec(s['Ti'])}")


def _tuning(p, spec, a: dict, done: dict) -> dict | None:
    t = a.get("tuning") or {}
    law = (a.get("controller") or {}).get("law")
    if not law:
        return None
    if t.get("simc") and not t.get("why"):
        s = t["simc"]
        pid = _id("tuning", a["goal"], a["key"])
        if pid in done:
            return None
        values, change = _law_values(s, law)
        edit = gain_edit(spec, t["block"], values)
        reason = (f"{s['rule']}, for the process the model holds. As it is: {_said(a.get('margins') or {}, a.get('closed_step') or {})}. "
                  f"Tuned: {_said(t['margins'], t['step'])}.")
        return {"id": pid, "kind": "tuning", "goal": a["goal"], "block": t["block"], "title": f"{t['block']}: {change} (SIMC)",
                "reason": reason,
                "edit": {"files": [edit.as_dict()], "diff": edit.diff()}, "values": s}
    dt = t.get("detune")
    if not dt:
        return None
    pid = _id("detune", a["goal"], a["key"])
    if pid in done:
        return None
    c, rob, rb = dt["controller"], a.get("robust") or {}, dt.get("robust") or {}
    values, change = _law_values(c, law)
    edit = gain_edit(spec, t["block"], values)
    se = rob.get("se") or {}
    reason = (f"How sure the process is: K ± {_pm(se.get('K'))}, θ ± {_pm(se.get('theta'))}s (standard errors). At the worst "
              f"it could be (K + 2σ, θ + 2σ), the loop as it is has a gain margin of {_pm(rob.get('gain_margin'))}"
              + ("" if rob.get("stable") else " and may not settle") + f"; {c['rule']}. At the worst then: gain margin "
              f"{_pm(rb.get('gain_margin'))}, phase margin {_pm(rb.get('phase_margin'))}°, Ms {_pm(rb.get('ms'))}. "
              f"As it is, with the process as found: {_said(a.get('margins') or {}, a.get('closed_step') or {})}. Detuned: "
              f"{_said(dt['margins'], dt['step'])}. Slower, and stable over all the process could be.")
    return {"id": pid, "kind": "tuning", "goal": a["goal"], "block": t["block"],
            "title": f"{t['block']}: {change} (detuned for robustness)",
            "reason": reason, "edit": {"files": [edit.as_dict()], "diff": edit.diff()}, "values": c}


def _round_to(x: float, res: float | None) -> float:
    return round(x / res) * res if res else float(f"{x:.2g}")


def plan(a: dict) -> dict | None:
    """A step of u: its size and sign, how long it is held, and when it stops early (Seborg et al. §7:
    in the linear range, inside the setting's limits, back to where it was). Sized from the process
    identified only when the record tells its numbers apart; otherwise from the tolerance and the
    noise against the most the record shows y moving per unit of u, never less than ten of the
    setting's least steps (Ljung §13.2: a poor prior, a conservative design). ``refused`` says why
    no step fits."""
    if a.get("how") != "setting" or not a.get("blocks") or a.get("known") or not (a.get("controller") or {}).get("integral"):
        return None                     # only a setting its own controller steps by this loop's error alone
    us = [x for x in a["record"]["u"] if x is not None]
    if not us:
        return None
    r = a.get("identified") or {}
    g = a["goal"]
    tol = a.get("tolerance") or 0.0
    noise = a.get("noise") or 0.0
    want = max(2 * tol, 4 * noise)
    res = a.get("resolution") or 0.0
    lo, hi = (a.get("limits") or [None, None])[:2]
    u_now = a["u_now"] if a.get("u_now") is not None else us[-1]       # now, not the end of a test's chart
    ur = a.get("u_range") or [min(us), max(us)]
    rng = ur[1] - ur[0]
    modest = max(0.15 * abs(u_now), 0.25 * rng) or 1.0         # never far past what the setting is used to moving
    floor = 10 * res
    sure = bool(r.get("found") and r.get("told_apart"))
    K = r.get("K") if r.get("found") else None
    done = [t for t in a.get("tests") or [] if t.get("finished") and t.get("amount")]
    T = a.get("period") or 10.0
    every = a.get("sensor_every") or 0.0                     # enough readings each way to fit and to test on
    least = max(HOLD_LEAST, 10 * T, ident.POINTS_MIN * every * 1.1)
    if sure:
        amount = want / abs(K) if want > 0 else modest
        amount = min(amount, modest)
        lag = (r.get("tau") or 0) + (r.get("theta") or 0)
        hold = max(least, 5 * lag)
        how = (f"sized from the process identified (K {K:.3g}): enough to move y by {want:.3g}, twice its tolerance or "
               f"four times its noise; held five of τ + θ")
    else:
        sens = a.get("sensitivity")
        amount = max(want / sens if sens and want > 0 else 0.0, modest)
        amount *= 1 + 0.5 * len(done)                         # each test that did not tell it apart: half again
        hold = max(least, 600.0) * (1 + 0.5 * len(done))
        how = ("the record does not tell the process's numbers apart, so they are not used: sized to move y by "
               f"{want:.3g} (twice its tolerance or four times its noise) even at the most y moved per unit of u in the record, "
               "and no less than the setting is used to moving" + (f", half again for each of the {len(done)} tests before"
                                                                    if done else "") + f"; held {dur(hold)}")
    amount = max(amount, floor)
    hold = min(HOLD_MOST, hold)
    op = a.get("op", "==")
    sign = 1.0
    if K and sure:
        down = op in ("<=", "<") or (op == "==" and (a.get("error") or 0) < 0)
        sign = -1.0 if (K > 0) == down else 1.0
    room = {1.0: (hi - u_now) if hi is not None else math.inf, -1.0: (u_now - lo) if lo is not None else math.inf}
    if room[sign] < amount and room[-sign] >= amount:
        sign = -sign                                          # the other way has room for it
    if room[sign] < amount:
        best = max(room.values())
        if best - res < max(floor, 1e-9):
            return {"refused": f"no step of at least {floor:g} fits between {lo:g} and {hi:g} from {u_now:g}", "goal": g}
        sign = 1.0 if room[1.0] >= room[-1.0] else -1.0
        amount = best - res
        how += f"; cut to {amount:.3g} to stay within {lo:g} to {hi:g}"
    amount = sign * _round_to(amount, res)
    if res and abs(amount) < floor - 1e-9:
        return {"refused": f"the step would be under ten of the setting's least steps ({res:g})", "goal": g}
    dy = abs(K * amount) if K and sure else (want or tol or noise)
    abort = max(3 * dy, 3 * tol, 6 * noise)
    abort = abort + abs(a.get("error") or 0) if abort > 0 else None
    hold_blocks = sorted(set(a["blocks"]) | set(a.get("controllers") or []) | set(a.get("quiet") or []))
    return {"goal": g, "block": a["blocks"][0], "amount": amount, "hold": round(hold), "abort": abort,
            "hold_blocks": hold_blocks, "u": a["u"], "u_now": u_now, "limits": [lo, hi], "resolution": res or None,
            "flow": a.get("flow"), "sized": how}


def _family(a: dict) -> str:
    return f"{a['key']}/{len(a.get('tests') or [])}"


def _step_test(p, spec, a: dict, done: dict) -> dict | None:
    r = a.get("identified") or {}
    if a.get("declared") or r.get("proposable"):
        return None
    tests = a.get("tests") or []
    if any(not t.get("finished") for t in tests):
        return None                                        # one under way: its answer first
    if a.get("steady"):
        a["step_test_waiting"] = a["steady"]              # waiting for steady operation: not offered yet
        return None
    pl = plan(a)
    if pl is None:
        return None
    if pl.get("refused"):
        a["step_test_refused"] = pl["refused"]
        return None
    fam = _family(a)                                      # each test done may be followed by another
    if any(v.get("family") == fam and v.get("status") == "dismissed" for v in done.values()):
        return None
    pid = _id("step-test", a["goal"], f"{fam}/{pl['amount']:.6g}/{pl['hold']}/{pl['abort'] or 0:.6g}")   # binds to this plan
    if pid in done:
        return None
    pl["id"] = pid
    why = "; ".join(r.get("why") or []) or "the record does not identify it"
    u = a["u"].split(".", 1)[1]
    held = ", ".join(pl["hold_blocks"])
    step = ye.number(pl["amount"]).replace("-", "−")
    held_for = dur(pl["hold"])
    verb = "takes" if len(pl["hold_blocks"]) == 1 else "take"
    lim = pl["limits"]
    reason = (f"The record does not identify this loop's process ({why}). The test: {held} held still; "
              f"{pl['block']} moves {u} by {step} at once (from about {ye.number(round(pl['u_now'], 3))}"
              + (f", within {ye.number(lim[0])} to {ye.number(lim[1])}" if lim[0] is not None and lim[1] is not None else "")
              + f"), the loop is left to answer for {held_for}, then {u} is put back to the value it had when the test "
              f"started and the loop answers for {held_for} again; then {held} {verb} over. "
              f"How it is sized: {pl['sized']}. "
              + (f"It stops early, putting {u} back at once, if the error passes {pl['abort']:.3g}, or if {pl['block']} "
                 "moves anything but the step. " if pl["abort"] else "")
              + "The step up is fitted, the step back held out (with tests before, all fitted together), with no feedback "
              'to bias it. ergostat must be running; its program is given "trigger": "step-test" and must move exactly '
              'the step, or put the setting to the value given ("to"), and say what it moved.')
    return {"id": pid, "kind": "step-test", "goal": a["goal"], "family": fam,
            "title": f"{a['goal']}: a step test, {u} {'+' if pl['amount'] > 0 else '−'}{ye.number(abs(pl['amount']))} for "
                     f"{dur(pl['hold'])}, then back", "reason": reason, "plan": pl}


UNIDENTIFIED = "control/unidentified.json"


def unidentified(p, spec=None) -> dict[str, dict]:
    """``loop-not-identifiable``: each goal whose loop's process the record so far does not identify, with what would,
    while the loop is as it was when it was said (``loop.key``)."""
    from . import loop as lp
    spec = spec or p.model.spec
    try:
        got = json.loads((p.dir / UNIDENTIFIED).read_text())
    except (OSError, ValueError):
        return {}
    return {g: x for g, x in got.items() if g in spec.goals and x.get("key") == lp.key(spec, g)}


def _unidentified(p, a: dict, step: bool) -> None:
    r = a.get("identified") or {}
    f = p.dir / UNIDENTIFIED
    try:
        got = json.loads(f.read_text())
    except (OSError, ValueError):
        got = {}
    if r.get("found") and r.get("poor") and not a.get("declared") and not r.get("proposable"):
        span = r.get("span") or 0.0
        got[a["goal"]] = {"key": a["key"], "poor": r["poor"], "said": (
            f"the record so far does not identify this loop's process ({'; '.join(r['poor'])}). What would: a step test"
            f"{' (offered)' if step else ''}, a large outside change in its input (a burst of arrivals), or "
            f"{dur(max(span, 3600.0))} more of record")}
    elif got.pop(a["goal"], None) is None:
        return
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(got, indent=1))


def offered(p, a: dict) -> list[dict]:
    """The proposals for one loop's analysis (``loop.analyse``), and remembered as shown; a loop the record does not
    identify, said (``unidentified``)."""
    spec = p.model.spec
    done = decisions(p)
    out = []
    for make in (_process, _tuning, _step_test):
        try:
            x = make(p, spec, a, done)
        except ye.EditError as e:
            x = None
            a.setdefault("edit_errors", []).append(str(e))
        if x:
            x["key"] = a["key"]
            OFFERED[x["id"]] = x
            out.append(x)
            if x["kind"] in ("process", "tuning"):
                _made(p, x)
            elif not any(e["data"].get("id") == x["id"] for e in p.events.query(n=50, type="steptest.offered")):
                p.events.add("steptest.offered", item=x["goal"], source="ergostat", data=x)   # it waits on the owner (SPEC §12o)
    _unidentified(p, a, any(x["kind"] == "step-test" for x in out))
    return out


def _made(p, x: dict) -> None:
    """A loop's process or gain offered for the first time: an ``ergostat.model-change`` item, made by ergostat and
    checked (its analysis is its check), like every change to the model."""
    from ..numbers import proposals as pr
    was = pr.changes(p).get(x["id"])
    body = {"kind": x["kind"], "title": x["title"], "goal": x.get("goal"), "block": x.get("block"), "reason": x.get("reason"),
            "target": f"goal.{x.get('goal')}", "made_by": "ergostat", "edit": x.get("edit")}
    if was is not None and was[0] in pr.OPEN:        # offered again: the same change, with the numbers found now
        if any(was[1].get(k) != body[k] for k in ("title", "reason", "edit")):
            pr.event(p, x["id"], "revised", {**body, "revisions": (was[1].get("revisions") or 0) + 1})
        return
    if was is not None and was[0] != "superseded":
        return
    pr.event(p, x["id"], "made", {**body, "created": time.time()})
    pr.event(p, x["id"], "checked", {})


def dismiss(p, pid: str, reason: str | None = None, offer: dict | None = None, by: str = "owner") -> dict:
    x = OFFERED.get(pid) or offer                    # offer: as it was recorded offered (steptest.offered), answered elsewhere
    if x is None:
        raise ProposalError(f"no proposal {pid} on offer: open the loop again")
    d = decisions(p)
    d[pid] = {"status": "dismissed", "decided": time.time(), "kind": x["kind"], "goal": x["goal"], "title": x["title"],
              **({"family": x["family"]} if x.get("family") else {}), **({"reason": reason.strip()[:500]} if reason else {})}
    _save(p, d)
    from ..numbers import proposals as pr
    _made(p, x)
    pr.event(p, pid, "dismissed", {"dismissed_because": reason.strip()[:500]} if reason else {}, source=by)
    OFFERED.pop(pid, None)
    return {**x, "status": "dismissed"}


def accept(p, pid: str, by: str = "owner", expect: str | None = None, offer: dict | None = None) -> dict:
    """Apply what the page was shown: an edit (checked, else put back), or a step test's approval. ``expect``
    is the hash of the diff shown (``numbers.review.diff_of``): refused unless that is what would be written."""
    from .. import model as mdl
    from ..spec import read
    from . import loop as lp
    x = OFFERED.get(pid) or offer
    if x is None:
        raise ProposalError(f"no proposal {pid} on offer: open the loop again")
    spec = p.model.spec
    if x["goal"] not in spec.goals or lp.key(spec, x["goal"]) != x["key"]:
        raise ProposalError("the model has changed since it was offered: open the loop again")
    d = decisions(p)
    if x["kind"] == "step-test":
        from ..runner import running_pid
        if not running_pid(p):
            raise ProposalError("ergostat is not running, so nothing would run the test: start it (ergostat run), then approve")
        pl = x["plan"]
        p.events.add("steptest.approved", item=x["goal"], source=by, data={**pl, "title": x["title"]})
        d[pid] = {"status": "approved", "decided": time.time(), "kind": x["kind"], "goal": x["goal"], "title": x["title"]}
        _save(p, d)
        OFFERED.pop(pid, None)
        return {**x, "status": "approved"}
    edits = [ye.Edit.from_dict(e) for e in x["edit"]["files"]]
    if expect is not None:
        from ..numbers.review import diff_of
        if diff_of(x, p.model.path.parent).get("hash") != expect:
            raise ProposalError("the files have changed since the diff was shown: look at it again before accepting")
    old = {e.file: Path(e.file).read_text(encoding="utf-8") for e in edits}
    try:
        new = {e.file: ye.apply(e) for e in edits}
    except ye.EditError as e:
        raise ProposalError(str(e)) from None
    for f, text in new.items():
        Path(f).write_text(text, encoding="utf-8")
    _, problems = read(p.model.path)
    errors = [str(e) for e in problems if e.level == "error"]
    if errors:
        for f, text in old.items():
            Path(f).write_text(text, encoding="utf-8")
        raise ProposalError("the edit would leave the model with errors, so it was not made:\n  " + "\n  ".join(errors))
    before = x["key"]
    p.model = mdl.load(p.model.path.parent)
    after = lp.key(p.model.spec, x["goal"])
    d[pid] = {"status": "accepted", "decided": time.time(), "kind": x["kind"], "goal": x["goal"], "title": x["title"], "by": by}
    _save(p, d)
    from ..numbers import proposals as pr
    _made(p, x)
    pr.event(p, pid, "accepted", {"decided": time.time(), "by": by}, source=by)
    p.events.add("ergostat.model.changed", item=p.model.name, source="ergostat",
                 data={"change": pid, "item": pr.item_of(pid), "kind": x["kind"], "title": x["title"],
                       "target": f"goal.{x['goal']}", "accepted_by": by, "diff": x["edit"]["diff"], "loop_before": before,
                       "loop_after": after, "values": x.get("values")})
    OFFERED.pop(pid, None)
    return {**x, "status": "accepted"}
