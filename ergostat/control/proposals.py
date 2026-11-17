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
    how = ("from a step test, open loop" if r.get("test") else "from the loop working, closed loop")
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
    parts = [f"identified {'from the step test' if r.get('test') else 'from the loop working (closed loop)'} on "
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
    if r.get("closed_loop"):
        parts.append("identified in closed loop: where disturbances are not measured, the estimate leans toward the "
                     "controller's inverse (Ljung ch. 13); a step test identifies it open loop")
    edit = process_edit(spec, a["goal"], _process_lines(spec, a, r))
    return {"id": pid, "kind": "process", "goal": a["goal"], "title": f"{a['goal']}: its process P(s) = {num}/({den})",
            "reason": "; ".join(parts) + ".", "edit": {"files": [edit.as_dict()], "diff": edit.diff()},
            "values": {"form": r["form"], "K": r["K"], "tau": r.get("tau"), "theta": r["theta"]}}


def _tuning(p, spec, a: dict, done: dict) -> dict | None:
    t = a.get("tuning") or {}
    if t.get("why") or not t.get("simc"):
        return None
    pid = _id("tuning", a["goal"], a["key"])
    if pid in done:
        return None
    s, law = t["simc"], a["controller"]["law"]
    now, new = a.get("margins") or {}, t["margins"]
    st_now, st_new = a.get("closed_step") or {}, t["step"]

    def said(m, st):
        bits = [f"gain margin {_pm(m.get('gain_margin'))}", f"phase margin {_pm(m.get('phase_margin'))}°",
                f"Ms {_pm(m.get('ms'))}"]
        if st.get("overshoot") is not None:
            bits.append(f"overshoot {st['overshoot'] * 100:.0f}%")
        if st.get("settling") is not None:
            bits.append(f"settles in {dur(st['settling'])}")
        if not m.get("stable", True):
            bits.append("does not settle")
        return ", ".join(bits)
    if s["form"] == "I":
        values = {"gain": ye.number(s["g"])}
        change = f"gain {ye.number(law['g'])} → {ye.number(s['g'])} a step"
    else:
        values = {"gain": ye.number(s["Kc"]), "integral-time": _sec(s["Ti"])}
        change = f"gain {ye.number(law['Kc'])} → {ye.number(s['Kc'])}, integral time {_sec(law['Ti'])} → {_sec(s['Ti'])}"
    edit = gain_edit(spec, t["block"], values)
    reason = (f"{s['rule']}, τc = {s['tc']:.3g}s, for the process the model holds. As it is: {said(now, st_now)}. "
              f"Tuned: {said(new, st_new)}.")
    return {"id": pid, "kind": "tuning", "goal": a["goal"], "title": f"{t['block']}: {change} (SIMC)", "reason": reason,
            "edit": {"files": [edit.as_dict()], "diff": edit.diff()}, "values": s}


def plan(a: dict) -> dict | None:
    """A step of u, its size, how long it is held, and when it stops early."""
    if a.get("how") != "setting" or not a.get("blocks") or a.get("known") or not (a.get("controller") or {}).get("integral"):
        return None                     # only a setting its own controller steps by this loop's error alone
    rec = a["record"]
    us = [x for x in rec["u"] if x is not None]
    if not us:
        return None
    r = a.get("identified") or {}
    g = a["goal"]
    tol = a.get("tolerance") or 0.0
    noise = a.get("noise") or 0.0
    want = max(2 * tol, 4 * noise)
    K = r.get("K") if r.get("found") else None
    u_now = us[-1]
    rng = max(us) - min(us)
    modest = max(0.15 * abs(u_now), 0.25 * rng) or 1.0         # never far past what the setting is used to moving
    amount = min(want / abs(K), modest) if K and want > 0 else max(0.05 * abs(u_now), 0.1 * rng) or 1.0
    op = a.get("op", "==")
    sign = 1.0
    if K:
        down = op in ("<=", "<") or (op == "==" and (a.get("error") or 0) < 0)
        sign = -1.0 if (K > 0) == down else 1.0
    done = [t for t in a.get("tests") or [] if t.get("finished") and t.get("amount")]
    if done:                               # the last test did not tell it apart: twice the step, held twice as long
        amount = min(2 * abs(done[-1]["amount"]), max(0.3 * abs(u_now), 0.5 * rng) or 2 * abs(done[-1]["amount"]))
    amount = float(f"{sign * amount:.2g}")
    lag = (r.get("tau") or 0) + (r.get("theta") or 0) if r.get("found") else 0
    T = a.get("period") or 10.0
    every = a.get("sensor_every") or 0.0                     # enough readings each way to fit and to test on
    hold = min(HOLD_MOST, max(HOLD_LEAST, 5 * lag, 10 * T, ident.POINTS_MIN * every * 1.1))
    if done:
        hold = min(HOLD_MOST, max(hold, 2 * (done[-1].get("hold") or 0)))
    dy = abs(K * amount) if K else (want or tol or noise)
    abort = max(3 * dy, 3 * tol, 6 * noise)
    abort = abort + abs(a.get("error") or 0) if abort > 0 else None
    hold_blocks = sorted(set(a["blocks"]) | set(a.get("controllers") or []) | set(a.get("quiet") or []))
    return {"goal": g, "block": a["blocks"][0], "amount": amount, "hold": round(hold), "abort": abort,
            "hold_blocks": hold_blocks, "u": a["u"], "u_now": u_now}


def _step_test(p, spec, a: dict, done: dict) -> dict | None:
    r = a.get("identified") or {}
    if a.get("declared") or r.get("proposable"):
        return None
    tests = a.get("tests") or []
    if any(not t.get("finished") for t in tests):
        return None                                        # one under way: its answer first
    pl = plan(a)
    if pl is None:
        return None
    pid = _id("step-test", a["goal"], f"{a['key']}/{len(tests)}")      # each test done may be followed by another
    if pid in done:
        return None
    pl["id"] = pid
    why = "; ".join(r.get("why") or []) or "the record does not identify it"
    u = a["u"].split(".", 1)[1]
    held = ", ".join(pl["hold_blocks"])
    step = ye.number(pl["amount"]).replace("-", "−")
    held_for = dur(pl["hold"])
    verb = "takes" if len(pl["hold_blocks"]) == 1 else "take"
    reason = (f"The record does not identify this loop's process ({why}). The test: {held} held still; "
              f"{pl['block']} moves {u} by {step} at once, the loop is left to answer for {held_for}, "
              f"then {u} goes back by the same and the loop answers for {held_for} again; then {held} {verb} over. "
              + (f"It stops early, stepping back at once, if the error passes {pl['abort']:.3g}. " if pl["abort"] else "")
              + "The step up is fitted, the step back "
              "held out, with no feedback to bias it. ergostat must be running; its program is given "
              '"trigger": "step-test" and must move exactly the step.')
    return {"id": pid, "kind": "step-test", "goal": a["goal"],
            "title": f"{a['goal']}: a step test, {u} {'+' if pl['amount'] > 0 else '−'}{ye.number(abs(pl['amount']))} for "
                     f"{dur(pl['hold'])}, then back", "reason": reason, "plan": pl}


def offered(p, a: dict) -> list[dict]:
    """The proposals for one loop's analysis (``loop.analyse``), and remembered as shown."""
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
    return out


def dismiss(p, pid: str) -> dict:
    x = OFFERED.get(pid)
    if x is None:
        raise ProposalError(f"no proposal {pid} on offer: open the loop again")
    d = decisions(p)
    d[pid] = {"status": "dismissed", "decided": time.time(), "kind": x["kind"], "goal": x["goal"], "title": x["title"]}
    _save(p, d)
    p.events.add("model.dismissed", item=p.model.name, source="owner", data={"proposal": pid, "title": x["title"]})
    OFFERED.pop(pid, None)
    return {**x, "status": "dismissed"}


def accept(p, pid: str, by: str = "owner") -> dict:
    """Apply what the page was shown: an edit (checked, else put back), or a step test's approval."""
    from .. import model as mdl
    from ..spec import read
    from . import loop as lp
    x = OFFERED.get(pid)
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
    p.events.add("model.accepted", item=p.model.name, source=by,
                 data={"proposal": pid, "kind": x["kind"], "title": x["title"], "target": f"goal.{x['goal']}",
                       "diff": x["edit"]["diff"], "loop_before": before, "loop_after": after, "values": x.get("values")})
    OFFERED.pop(pid, None)
    return {**x, "status": "accepted"}
