"""The improvement loop as the bench needs it, on main's code, until the improver's own modules land
(``ergostat/numbers/improve.py`` and ``judge.py``, branch ``improver``): the same contract, kept small. When those
modules can be imported the adapter uses them and this file is not used (delete it then).

What it keeps of the contract (SPEC §12e): a proposal is checked the same way whoever made it: every reason needs
evidence ergostat can check, its edit is applied to a scratch copy, compiled, replayed on the record and, where it
brings a parameter to estimate, refitted; one with no evidenced reason, that does not compile or that clearly worsens
the fit is refused. A proposal kept is a candidate in the review queue (``proposals.json``), recorded as
``ergostat.model-change.made`` and ``.checked``. The judge replays each candidate beside the model on the record
after it was made, in windows (the whole, halves, quarters), passes it only when it is better by the threshold in
every one (or no worse and answering findings), fails it otherwise, and writes one passed change a run where the
policy says ``auto``."""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

from .. import series
from ..numbers import estimate as es
from ..numbers import fit as ft
from ..numbers import observe as ob
from ..numbers import proposals as pr
from ..numbers import simulate as sim
from ..numbers import trial as tr
from ..numbers import version as ver
from ..numbers import yamledit as ye
from ..spec.ir import Spec

ITEM = "ergostat.model-change"
KINDS = ("parameter", "equation", "structure")
WORSE, TRIFLE = 0.10, 1e-4
SPLITS, MIN_WINDOW, MIN_JUDGED, GIVE_UP, MOST = (1, 2, 4), 60.0, 3, 3.0, 3
RULES = ("rate-driven-by-rate", "stock-without-outflow", "outflow-ignores-stock", "perceived-value", "units-mismatch",
         "missing-delay", "boundary", "stock-without-flows", "unsigned-link", "extreme-conditions",
         "dimensional-consistency", "structure-assessment", "parameter-assessment", "behaviour-reproduction",
         "partial-model-test", "simplest-structure", "first-order-drain", "moving-average-lag")
URL = re.compile(r"^https?://\S+$")
PATH_LINE = re.compile(r"^(?P<path>[^:\s][^:]*):(?P<a>\d+)(?:-(?P<b>\d+))?$")


class ProposeError(Exception):
    pass


def _id(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, default=str).encode()).hexdigest()[:8]


def event(p, pid: str, state: str, data: dict | None = None, source: str = "ergostat", at: float | None = None) -> None:
    p.events.add(f"{ITEM}.{state}", item=f"{ITEM}/{pid}", source=source, data=data or {}, at=at)


# ---- the edit

def _model_file(spec: Spec, name: str) -> Path:
    f = Path(name)
    f = (f if f.is_absolute() else spec.root / f).resolve()
    if f not in {Path(x).resolve() for x in spec.files}:
        raise ProposeError(f"{name}: not one of the model's files; a proposal edits the model only")
    return f


def edits(spec: Spec, raw) -> list[ye.Edit]:
    if isinstance(raw, dict) and "files" in raw:
        raw = raw["files"]
    raw = [raw] if isinstance(raw, dict) else raw
    if not isinstance(raw, list) or not raw:
        raise ProposeError("edit: {files: [{file, hunks}]}, or {file, replace, with}")
    out = []
    for one in raw:
        if not isinstance(one, dict) or not one.get("file"):
            raise ProposeError("each edit names its file (from the model's folder)")
        f = _model_file(spec, str(one["file"]))
        if "replace" in one:
            old = str(one.get("replace") or "").rstrip("\n").split("\n")
            new = str(one.get("with") or "").rstrip("\n").split("\n") if one.get("with") else []
            ls = ye.lines_of(f)
            at = [i for i in range(len(ls) - len(old) + 1) if ls[i:i + len(old)] == old]
            if not any(x.strip() for x in old) or len(at) != 1:
                raise ProposeError(f"{f.name}: the lines to replace are found {len(at)} times (they must be found once)")
            out.append(ye.Edit(str(f), [ye.Hunk(at[0] + 1, old, new)]))
            continue
        try:
            hunks = [ye.Hunk(int(h["line"]), [str(x) for x in h.get("old") or []], [str(x) for x in h.get("new") or []])
                     for h in one.get("hunks") or []]
        except (KeyError, TypeError, ValueError):
            raise ProposeError("a hunk is {line, old, new}") from None
        if not hunks:
            raise ProposeError(f"{f.name}: no hunks")
        out.append(ye.Edit(str(f), hunks))
    return out


def joined(es_: list[ye.Edit]) -> dict:
    by: dict[str, list] = {}
    for e in es_:
        by.setdefault(e.file, []).append(e)
    files = [ye.merge(x) for x in by.values()]
    return {"files": [f.as_dict() for f in files], "diff": "\n".join(f.diff() for f in files)}


# ---- the evidence

def check_evidence(p, spec: Spec, fit: dict, ev) -> str:
    if isinstance(ev, dict) and len(ev) == 1:
        (k, v), = ev.items()
        ev = f"{k}:{v}"
    if not isinstance(ev, str) or not ev.strip():
        raise ProposeError("no evidence")
    ev = ev.strip()
    kind, _, what = ev.partition(":")
    if kind == "finding":
        from ..spec import read
        _, problems = read(p.model.path)
        got = {f"{x.code}@{x.about}" if x.about else x.code: x.message for x in problems if x.level != "error"}
        if what not in got:
            raise ProposeError(f"{ev}: check does not find it now")
        return got[what]
    if kind == "fit":
        ref, _, stat = what.rpartition(".")
        s = fit.get("total") if ref == "total" else (fit.get("stocks") or {}).get(ref) or (fit.get("equations") or {}).get(ref)
        if not s or s.get(stat) is None:
            raise ProposeError(f"{ev}: the fit has no {stat} for {ref} now")
        return f"{ref} {stat} = {s[stat]:.3g}"
    if kind == "residual":
        name = what.removeprefix("stock.")
        if name not in spec.stocks:
            raise ProposeError(f"{ev}: no stock {name}")
        return f"the residual of stock {name}"
    if kind == "rule":
        if what not in RULES:
            raise ProposeError(f"{ev}: no such modelling rule")
        return f"rule {what}"
    if URL.match(ev):
        return f"a reference: {ev}"
    m = PATH_LINE.match(ev)
    if m:
        from .. import helpdocs
        for r in (spec.root, helpdocs.HERE.parent):
            f = (r / m.group("path")).resolve()
            if f.is_file() and (f.is_relative_to(spec.root.resolve()) or f.is_relative_to(helpdocs.HERE.parent.resolve())):
                n = len(f.read_text(encoding="utf-8", errors="replace").split("\n"))
                a, b = int(m.group("a")), int(m.group("b") or m.group("a"))
                if not 1 <= a <= b <= n:
                    raise ProposeError(f"{m.group('path')}:{a}: it has {n} lines")
                return ev
        raise ProposeError(f"{m.group('path')}: no such file in the project or in ergostat")
    raise ProposeError(f"{ev}: not evidence ergostat can check")


# ---- checking

def _nmse(f: dict | None) -> float | None:
    return ((f or {}).get("total") or {}).get("nmse")


def _fit_with(spec: Spec, data: ob.Data, params: dict[str, float]) -> dict:
    run = sim.replay(spec, data, sim.plan(spec, params))
    partial = sim.replay(spec, data, sim.plan(spec, params, integrate=set()))
    got = ft.compare(spec, data, run, partial)
    return {"total": ft._slim(got["total"]) if run.valid else None, "stocks": {r: ft._slim(s) for r, s in got["stocks"].items()}}


def _eq(spec: Spec, ref: str) -> str | None:
    kind, _, name = ref.partition(".")
    x = (spec.flows if kind == "flow" else spec.auxiliaries).get(name)
    return x.equation.text if x is not None and x.equation else None


def refit(before: Spec, after: Spec, data: ob.Data) -> dict | None:
    changed = [n for n, x in after.parameters.items() if x.estimate and not x.table and
               (n not in before.parameters or sorted(pr.users_of(before, n)) != sorted(pr.users_of(after, n)) or
                any(_eq(before, r) != _eq(after, r) for r in pr.users_of(after, n)))]
    if not changed:
        return None
    cut = max(1, int(round(data.grid.n * (1 - es.HOLD_OUT))))
    best: dict[str, float] = {}
    for sc in es.scopes(after, changed, "parts"):
        prob = es.Problem(after, data, sc.names, cut=cut, scope=sc)
        if prob.n() < 10:
            continue
        start = {n: (after.parameters[n].value if after.parameters[n].value is not None else 1.0) for n in sc.names}
        got, _, _, _ = es.solve(prob, start)
        best.update({n: float(ye.number(v)) for n, v in got.items() if n in changed})
    return {"values": best, "fit": _fit_with(after, data, best)} if best else None


def validate(p, spec: Spec, by: str, raw, data: ob.Data) -> dict:
    if not isinstance(raw, dict):
        raise ProposeError("propose: an object with kind, parts, edit, reasons and confidence")
    said = str(raw.get("kind") or "structure")
    if said not in KINDS:
        raise ProposeError(f"kind: one of {', '.join(KINDS)}")
    conf = raw.get("confidence")
    if isinstance(conf, str):
        conf = {"low": 0.25, "medium": 0.5, "high": 0.8}.get(conf.strip().lower(), conf)
    if conf is not None and (isinstance(conf, bool) or not isinstance(conf, int | float) or not 0 <= conf <= 1):
        raise ProposeError("confidence: a number from 0 to 1")
    run_b, fit_b = tr.fit_of(spec, data)
    reasons = raw.get("reasons") or []
    reasons = [reasons] if isinstance(reasons, dict) else reasons
    kept = []
    for r in reasons if isinstance(reasons, list) else []:
        says = str((r or {}).get("says") or "").strip() if isinstance(r, dict) else str(r)
        evs = (r or {}).get("evidence") if isinstance(r, dict) else None
        checked = []
        for e in evs if isinstance(evs, list) else [evs]:
            try:
                checked.append((e, check_evidence(p, spec, fit_b, e)))
            except ProposeError:
                pass
        if says and checked:
            kept.append({"says": says, "evidence": [c[0] for c in checked], "verified": [c[1] for c in checked]})
    if not kept:
        raise ProposeError("no reason with evidence ergostat can check")
    es_ = edits(spec, raw.get("edit"))
    try:
        texts = ye.apply_together(es_)
    except ye.EditError as e:
        raise ProposeError(f"its edit cannot be made: {e}") from None
    after, problems = tr.compiled(p.model.path, texts, findings=True)
    errors = [x for x in problems if x.level == "error"]
    if errors:
        raise ProposeError("the model it leaves does not compile: " + "; ".join(str(x) for x in errors[:3]))
    from ..spec import read
    _, now_problems = read(p.model.path)
    before_f = {f"{x.code}@{x.about}" for x in now_problems if x.level != "error"}
    after_f = {f"{x.code}@{x.about}" for x in problems if x.level != "error"}
    data_a = ob.measured(p, data.grid, after)
    run_a, fit_a = tr.fit_of(after, data_a)
    again = refit(spec, after, data_a)
    b, a = _nmse(fit_b), _nmse(fit_a)
    best = min((x for x in (a, _nmse((again or {}).get("fit"))) if x is not None), default=None)
    if run_b.valid and not run_a.valid and not (again and again["fit"].get("total")):
        raise ProposeError("with it the replay is not valid: " + "; ".join(run_a.invalid[:2]))
    if b is not None and best is not None and best > b * (1 + WORSE) and best - b > TRIFLE:
        raise ProposeError(f"it clearly worsens the fit: the scaled error goes from {b:.3g} to {best:.3g}")
    kind = "parameter" if ver.structure(spec) == ver.structure(after) else (said if said != "parameter" else "structure")
    parts = [x for x in raw.get("parts") or [] if isinstance(x, str)]
    x = {"kind": kind, "said_kind": said, "proposed_by": by, "parts": parts, "title": str(raw.get("title") or kept[0]["says"])[:200],
         "reasons": kept, "reason": "; ".join(r["says"] for r in kept), "confidence": conf, "edit": joined(es_),
         "findings": {"answered": sorted(before_f - after_f), "new": sorted(after_f - before_f)},
         "fit_before": fit_b, "fit_after": fit_a, "refit": again, "target": parts[0] if parts else ""}
    if kind == "parameter":
        moved = {n: q.value for n, q in after.parameters.items() if n in spec.parameters and q.value != spec.parameters[n].value}
        x["parameters"], x["previous"] = moved, {n: spec.parameters[n].value for n in moved}
        x["target"] = ", ".join(f"parameter.{n}" for n in moved) or x["target"]
    return x


def submit(p, by: str, raw, data: ob.Data | None = None, at: float | None = None) -> dict:
    spec: Spec = p.model.spec
    now = at or time.time()
    data = data or ob.measured(p, ob.reference(p, now))
    title = str((raw or {}).get("title") or "a change")[:200] if isinstance(raw, dict) else "a change"
    pid = _id("made", by, now, json.dumps(raw, sort_keys=True, default=str))
    event(p, pid, "made", {"title": title, "made_by": by}, source=by)
    try:
        x = validate(p, spec, by, raw, data)
        same = next((y for y in pr.stored(p).values() if y.get("version") == ver.version(spec) and y["status"] == "pending"
                     and (y.get("edit") or {}).get("diff") == x["edit"]["diff"]), None)
        if same is not None:
            raise ProposeError(f"the same change is waiting already: {ITEM}/{same['id']}")
    except (ProposeError, tr.TrialError) as e:
        event(p, pid, "refused", {"why": str(e)})
        return {"status": "refused", "id": pid, "title": title, "why": str(e)}
    x.update({"id": pid, "status": "pending", "state": "checked", "created": now, "proposed": now,
              "structure": ver.structure(spec), "version": ver.version(spec), "span": data.grid.until - data.grid.since,
              "method": f"proposed by {by}; checked on a scratch copy"})
    props = pr.stored(p)
    props[pid] = x
    pr.save(p, props)
    event(p, pid, "checked", {"kind": x["kind"], "scaled_error_before": _nmse(x["fit_before"]),
                              "scaled_error_after": _nmse(x["fit_after"])})
    return {"status": "proposed", "id": pid, "title": x["title"], "why": None}


def trial(p, raw, data: ob.Data | None = None) -> dict:
    data = data or ob.measured(p, ob.reference(p))
    try:
        x = validate(p, p.model.spec, "trial", raw, data)
    except (ProposeError, tr.TrialError) as e:
        return {"would": "not be proposed", "why": str(e)}
    return {"would": "be proposed", "kind": x["kind"], "scaled_error_before": _nmse(x["fit_before"]),
            "scaled_error_after": _nmse(x["fit_after"]), "refit": (x["refit"] or {}).get("values"),
            "diff": x["edit"]["diff"], "findings": x["findings"]}


# ---- the judge

LIKE_FOR_LIKE = False     # True: the judge compares the two models over the same stocks (see like_nmse); False: each
#                           model's own total, as the improver's judge does today


def like_nmse(spec: Spec, data: ob.Data, run) -> dict[str, float]:
    """Each stock's scaled error (its mean squared error over its own mean square), whether or not the fit's total
    would count it: the fit leaves out a stock whose replay is slower than the record is long, so a change that makes
    a stock slow enough takes it out of the total, and looks better."""
    got = ft.compare(spec, data, run)
    out = {}
    for ref, st in {**got["stocks"], **got["accounting"]}.items():
        if st and st.get("mse") is not None:
            out[ref] = st["mse"] / (st.get("scale") or 1.0)
    return out


WARM = False              # True: each window is scored on a replay started WARM_HOURS before it (its delays and stocks
WARM_HOURS = 6.0          # as the record left them), not started cold at the window's first reading


def warm_nmse(p, spec: Spec, since: float, until: float) -> dict[str, float] | None:
    """Each stock's scaled error over [since, until], on a replay started ``WARM_HOURS`` earlier."""
    start = since - WARM_HOURS * 3600.0
    width = max(ob.MIN_BUCKET, (until - since) / 30.0)
    grid = ob.Grid(start, until, max(2, int((until - start) // width)))
    data = ob.measured(p, grid, spec)
    run = sim.replay(spec, data)
    if not run.valid:
        return None
    first = int((since - start) // grid.width)
    out = {}
    for ref in run.how:
        if not ref.startswith("stock."):
            continue
        got = [(m, a) for i, m, a in ft.pairs(spec, data, run, ref) or [] if i >= first]
        if len(got) < 5:
            continue
        mse = sum((m - a) ** 2 for m, a in got) / len(got)
        scale = sum(a * a for _, a in got) / len(got)
        out[ref] = mse / (scale or 1.0)
    return out


def like_for_like(a: dict[str, float], b: dict[str, float]) -> tuple[float | None, float | None]:
    common = sorted(set(a) & set(b))
    if not common:
        return None, None
    return sum(a[r] for r in common) / len(common), sum(b[r] for r in common) / len(common)


def windows(since: float, until: float) -> list[tuple[float, float]]:
    out = []
    for k in SPLITS:
        w = (until - since) / k
        if w >= MIN_WINDOW:
            out += [(since + i * w, since + (i + 1) * w) for i in range(k)]
    return out


def compare(p, spec: Spec, after: Spec, since: float, until: float) -> dict:
    grid = ob.Grid(since, until, max(2, min(series.POINTS, int((until - since) // ob.MIN_BUCKET))))
    if WARM:
        wb, wa = warm_nmse(p, spec, since, until), warm_nmse(p, after, since, until)
        if LIKE_FOR_LIKE and wb is not None and wa is not None:
            b, a = like_for_like(wb, wa)
        else:
            b = sum(wb.values()) / len(wb) if wb else None
            a = sum(wa.values()) / len(wa) if wa else None
    elif LIKE_FOR_LIKE:
        db, da = ob.measured(p, grid, spec), ob.measured(p, grid, after)
        rb, ra = sim.replay(spec, db), sim.replay(after, da)
        b, a = like_for_like(like_nmse(spec, db, rb), like_nmse(after, da, ra))
        if not rb.valid:
            b = None
        if not ra.valid:
            a = None
    else:
        _, fb = tr.fit_of(spec, ob.measured(p, grid, spec))
        _, fa = tr.fit_of(after, ob.measured(p, grid, after))
        b, a = _nmse(fb), _nmse(fa)
    change = (b - a) / b if b and a is not None else (0.0 if b == 0 and a == 0 else None)
    return {"since": since, "until": until, "before": b, "after": a, "change": change}


def decide(results: list[dict], threshold: float, answers: int, new: int, held: float, hold_out: float):
    judged = [r for r in results if r["change"] is not None]
    n = len(judged)
    if n < MIN_JUDGED:
        if held < GIVE_UP * hold_out:
            return None
        if answers and not new and not judged:
            return "passed", "nothing it changes is fitted; it answers findings and makes none"
        return "failed", f"too little record to judge it: {n} windows with a fit"
    worse = [r for r in judged if r["change"] <= -threshold]
    better = [r for r in judged if r["change"] >= threshold]
    if worse:
        w = min(worse, key=lambda r: r["change"])
        return "failed", f"worse in {len(worse)} of {n} windows held out (by up to {-w['change']:.0%})"
    if len(better) == n:
        return "passed", f"better in every one of {n} windows held out (by {min(r['change'] for r in judged):.0%} or more)"
    if not better and answers and not new:
        return "passed", f"no worse in any of {n} windows held out, and it answers {answers} findings"
    return "failed", f"not consistently better: by {threshold:.0%} or more in {len(better)} of {n} windows held out"


def judge(p, policy: dict, by: str = "judge", at: float | None = None) -> dict:
    spec: Spec = p.model.spec
    now = at or time.time()
    out = {"verdicts": [], "waiting": [], "accepted": []}
    props = pr.stored(p)
    v = ver.version(spec)
    judged = 0
    for x in sorted((x for x in props.values() if x["status"] == "pending" and x.get("proposed_by")), key=lambda x: x["created"]):
        try:
            stale = x.get("version") != v or not pr.current(x, spec)
            after = None if stale else tr.spec_after(p, tr.edits_of(x))
        except tr.TrialError:
            stale = True
        if stale:
            x["status"] = x["state"] = "superseded"
            event(p, x["id"], "superseded", {"why": "the model changed since it was made"})
            out["verdicts"].append({"id": x["id"], "verdict": "superseded", "why": "the model changed since it was made"})
            continue
        if x.get("state") == "passed":
            continue
        if x.get("state") == "checked":
            x["state"] = "testing"
            event(p, x["id"], "testing", {"hold_out": policy["hold_out"]})
        held = now - x["proposed"]
        if held < policy["hold_out"] or judged >= MOST:
            out["waiting"].append({"id": x["id"], "held": held})
            continue
        judged += 1
        results = [compare(p, spec, after, a, b) for a, b in windows(x["proposed"], now)]
        f = x.get("findings") or {}
        got = decide(results, policy["threshold"], len(f.get("answered") or []), len(f.get("new") or []), held, policy["hold_out"])
        if got is None:
            out["waiting"].append({"id": x["id"], "held": held})
            continue
        state, why = got
        x["state"] = state
        x["verdict"] = {"verdict": state, "why": why, "at": now, "windows": results}
        if state == "failed":
            x["status"] = "failed"
        event(p, x["id"], state, {"why": why, "windows": len(results)})
        out["verdicts"].append({"id": x["id"], "verdict": state, "why": why})
    pr.save(p, props)
    for x in sorted((x for x in props.values() if x["status"] == "pending" and x.get("state") == "passed"),
                    key=lambda x: x["created"]):
        if policy["accept"].get(x["kind"]) != "auto":
            continue
        g = ob.reference(p, now)
        try:
            accept(p, x["id"], {"at": now, "window": g.until - g.since}, by=by)
        except pr.ProposalError as e:
            out["verdicts"].append({"id": x["id"], "verdict": "passed", "why": f"not written: {e}"})
            continue
        out["accepted"].append(x["id"])
        break
    return out


def accept(p, pid: str, snap: dict, by: str = "owner", expect: str | None = None) -> dict:
    x = pr.stored(p).get(pid) or pr.find(p, pid)
    if x.get("version") and x["version"] != ver.version(p.model.spec):      # main's Accept checks the structure only
        raise pr.ProposalError("the model has changed since it was proposed (another change was written)")
    x = pr.accept(p, x["id"], snap, by=by, expect=expect)
    props = pr.stored(p)
    props[pid]["state"] = "accepted"
    pr.save(p, props)
    event(p, pid, "accepted", {"kind": x["kind"], "title": x["title"], "diff": x["edit"]["diff"], "by": by,
                               "made_by": x.get("proposed_by"), **x.get("applied", {})}, source=by)
    return x
