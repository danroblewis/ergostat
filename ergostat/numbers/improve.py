"""A change to the model proposed by a block (SPEC §12e): any block, whatever its type, may print a line

    {"propose": {"kind": "structure", "parts": ["stock.x"], "edit": {...}, "title": "...",
                 "reasons": [{"says": "...", "evidence": "finding:stock-without-outflow@stock.x"}],
                 "confidence": 0.7}}

and ergostat validates it the same way whoever made it: the edit applied to a scratch copy of the files (in
memory, never on disk), compiled, checked, replayed on the reference window and, where it names parameters
to estimate, refitted; the measured effect is attached. Every reason must carry evidence ergostat can check:
a finding ``check`` reports now (``finding:CODE@PART``), a statistic of the fit (``fit:total.nmse``,
``fit:stock.quality.um``), a residual (``residual:stock.x``), a line of a document or of the code
(``docs/MODELLING.md:120``, ``bin/lab.py:40-52``, or a URL), or a modelling rule (``rule:NAME``, ``RULES``). A
reason without evidence is refused; a proposal left with none, one whose edit cannot be made or does not
compile, or one that clearly worsens the fit is not proposed, and is listed under "found, and not proposed"
with why. One that is proposed joins the review queue (``review.py``), attributed to the block that made it,
and is a **candidate** the judge (``judge.py``) tests on the record that comes after it.

The edit is in the form the review queue's proposals use (``{"files": [{"file", "hunks": [{"line", "old",
"new"}]}]}``, a file named from the model's folder), or, written by hand, ``{"file", "replace", "with"}``:
the lines ``replace`` names, found once in the file, become ``with``. Only the model's own files may be edited."""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

from ..spec.ir import Spec
from . import observe as ob
from . import proposals as pr
from . import trial as tr
from . import version as ver
from . import yamledit as ye

KINDS = ("parameter", "equation", "structure")
WORSE = 0.10                # a proposal whose scaled error rises past this share (and not by a trifle) clearly worsens the fit
TRIFLE = 1e-4
RULES = {                   # the modelling rules a reason may cite, each with where it is written
    "rate-driven-by-rate": "docs/MODELLING.md §1: a rate driven by a rate needs the stock between (Sterman ch. 6, 11; Forrester 1961)",
    "stock-without-outflow": "docs/MODELLING.md §2: what fills a stock leaves it somehow (Sterman ch. 6, 21)",
    "outflow-ignores-stock": "docs/MODELLING.md §3: an outflow falls to zero with its stock (Sterman ch. 8, 21)",
    "perceived-value": "docs/MODELLING.md §4: a decision sees a perceived value, a stock (Sterman ch. 11, 13: the Baker criterion)",
    "units-mismatch": "docs/MODELLING.md §5: a link between units needs the converting auxiliary (Sterman ch. 12, 21)",
    "missing-delay": "docs/MODELLING.md §6: a cause far from its effect goes through a delay (Sterman ch. 11, 12)",
    "boundary": "docs/MODELLING.md §7: an auxiliary is explained or declared exogenous (Sterman ch. 21, boundary adequacy)",
    "stock-without-flows": "docs/MODELLING.md §8: a quantity with no memory is an auxiliary",
    "unsigned-link": "docs/MODELLING.md §8: every link carries its polarity (Sterman ch. 5)",
    "extreme-conditions": "Sterman ch. 21, extreme conditions: the model does nothing the world cannot",
    "dimensional-consistency": "Sterman ch. 21, dimensional consistency: every equation balances its units",
    "structure-assessment": "Sterman ch. 21, structure assessment: the model conserves what it moves, and its structure is the system's",
    "parameter-assessment": "Sterman ch. 21, parameter assessment: every parameter means something real, and is measurable",
    "behaviour-reproduction": "Sterman ch. 21, behaviour reproduction: the replay follows the record (R², MAPE, Theil)",
    "partial-model-test": "Homer 2012: each equation against its own inputs as measured",
    "simplest-structure": "SD Lab's simplify rules (structural.py): what explains nothing goes",
    "first-order-drain": "Sterman ch. 8: an outflow is its stock over the time things stay",
    "moving-average-lag": "Sterman ch. 11.5: a moving average over L lags by L/2",
}
URL = re.compile(r"^https?://\S+$")
PATH_LINE = re.compile(r"^(?P<path>[^:\s][^:]*):(?P<a>\d+)(?:-(?P<b>\d+))?$")


class ProposeError(Exception):
    pass


def _id(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, default=str).encode()).hexdigest()[:8]


def finding_id(code: str, about: str | None) -> str:
    """How a reason names a finding ``check`` reports: its code, and the part it is about."""
    return f"{code}@{about}" if about else code


# ---- the edit

def _model_file(spec: Spec, name: str) -> Path:
    f = Path(name)
    f = (f if f.is_absolute() else spec.root / f).resolve()
    files = {Path(x).resolve() for x in spec.files}
    if f not in files:
        raise ProposeError(f"{name}: not one of the model's files ({', '.join(sorted(_rel(spec, x) for x in files))}); "
                           f"a proposal edits the model only")
    return f


def _rel(spec: Spec, f) -> str:
    try:
        return str(Path(f).resolve().relative_to(spec.root.resolve()))
    except ValueError:
        return Path(f).name


def _replace(spec: Spec, one: dict) -> ye.Edit:
    f = _model_file(spec, str(one.get("file") or ""))
    old = str(one.get("replace") or "").rstrip("\n").split("\n")
    new = str(one.get("with") or "").rstrip("\n").split("\n") if one.get("with") else []
    if not any(x.strip() for x in old):
        raise ProposeError("replace: the lines to change, as they are written now")
    ls = ye.lines_of(f)
    at = [i for i in range(len(ls) - len(old) + 1) if ls[i:i + len(old)] == old]
    if len(at) != 1:
        raise ProposeError(f"{_rel(spec, f)}: the lines to replace are found {len(at)} times (they must be found once, "
                           f"exactly as written, with their indentation)")
    return ye.Edit(str(f), [ye.Hunk(at[0] + 1, old, new)])


def edits(spec: Spec, raw) -> list[ye.Edit]:
    """A proposal's edit, as ``ye.Edit``s on the model's files: the review queue's form, or ``replace``."""
    if isinstance(raw, dict) and "files" in raw:
        raw = raw["files"]
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list) or not raw:
        raise ProposeError("edit: {files: [{file, hunks: [{line, old, new}]}]}, or {file, replace, with}")
    out = []
    for one in raw:
        if not isinstance(one, dict) or not one.get("file"):
            raise ProposeError("each edit names its file (from the model's folder)")
        if "replace" in one:
            out.append(_replace(spec, one))
            continue
        f = _model_file(spec, str(one["file"]))
        hunks = []
        for h in one.get("hunks") or []:
            try:
                hunks.append(ye.Hunk(int(h["line"]), [str(x) for x in h.get("old") or []], [str(x) for x in h.get("new") or []]))
            except (KeyError, TypeError, ValueError):
                raise ProposeError("a hunk is {line: N, old: [lines], new: [lines]}") from None
        if not hunks:
            raise ProposeError(f"{_rel(spec, f)}: no hunks")
        out.append(ye.Edit(str(f), hunks))
    return out


def joined(es: list[ye.Edit]) -> dict:
    by: dict[str, list] = {}
    for e in es:
        by.setdefault(e.file, []).append(e)
    files = [ye.merge(x) for x in by.values()]
    return {"files": [f.as_dict() for f in files], "diff": "\n".join(f.diff() for f in files)}


# ---- the evidence

class Evidence:
    """What ergostat can check a reason against, worked out once and only when a reason needs it."""

    def __init__(self, p, spec: Spec, data: ob.Data | None = None, fit: dict | None = None):
        self.p, self.spec, self.data, self._fit = p, spec, data, fit
        self._findings = None
        self._residuals = None

    def findings(self) -> dict[str, str]:
        if self._findings is None:
            from ..spec import read
            _, problems = read(self.p.model.path)
            self._findings = {finding_id(x.code, x.about): x.message for x in problems if x.level != "error"}
        return self._findings

    def fit(self) -> dict:
        if self._fit is None:
            data = self.data or ob.measured(self.p, ob.reference(self.p))
            _, self._fit = tr.fit_of(self.spec, data)
        return self._fit

    def residuals(self) -> dict:
        if self._residuals is None:
            from .. import state
            self._residuals = state.snapshot(self.p, state.WINDOW, None).get("residuals") or {}
        return self._residuals

    def check(self, ev) -> str:
        """What the evidence says, checked; or ``ProposeError`` with why it is not evidence."""
        if isinstance(ev, dict) and len(ev) == 1:
            (k, v), = ev.items()
            ev = f"{k}:{v}" if k in ("finding", "fit", "residual", "rule") else str(v)
        if not isinstance(ev, str) or not ev.strip():
            raise ProposeError("no evidence")
        ev = ev.strip()
        kind, _, what = ev.partition(":")
        if kind == "finding":
            got = self.findings()
            if what not in got:
                near = [k for k in got if k.split("@")[0] == what.split("@")[0]]
                raise ProposeError(f"{ev}: check does not find it now" + (f" (it finds {', '.join(near[:3])})" if near else ""))
            return got[what]
        if kind == "fit":
            ref, _, stat = what.rpartition(".")
            f = self.fit()
            if ref == "total":
                s = f.get("total")
            else:
                s = (f.get("stocks") or {}).get(ref) or (f.get("equations") or {}).get(ref)
            if not s or s.get(stat) is None:
                raise ProposeError(f"{ev}: the fit has no {stat} for {ref} now (fit:total.nmse, fit:stock.NAME.r2|mape|um|us|uc)")
            return f"{ref} {stat} = {s[stat]:.3g}" + (f" ({s['says']})" if s.get("says") else "")
        if kind == "residual":
            name = what.removeprefix("stock.")
            r = self.residuals().get(name)
            if r is None:
                raise ProposeError(f"{ev}: no residual for stock {name} over the last hour")
            return (f"stock {name}: changed {r['change']:.3g}, its flows explain {r['explained']:.3g}, unexplained "
                    f"{r['unexplained']:.3g}" + (" (significant)" if r.get("significant") else " (not significant)"))
        if kind == "rule":
            if what not in RULES:
                raise ProposeError(f"{ev}: no such modelling rule (rule:{', rule:'.join(sorted(RULES))})")
            return RULES[what]
        if URL.match(ev):
            return f"a reference: {ev}"
        m = PATH_LINE.match(ev)
        if m:
            return self._lines(m.group("path"), int(m.group("a")), int(m.group("b") or m.group("a")))
        raise ProposeError(f"{ev}: not evidence ergostat can check: a finding (finding:CODE@PART), a fit statistic "
                           f"(fit:total.nmse), a residual (residual:stock.NAME), a document or code line (path:LINE), a URL, "
                           f"or a modelling rule (rule:NAME)")

    def _lines(self, name: str, a: int, b: int) -> str:
        from .. import helpdocs
        roots = [self.spec.root, helpdocs.HERE.parent]          # the project, and ergostat's own (its docs, its code)
        for r in roots:
            f = (r / name).resolve()
            if not any(f.is_relative_to(x.resolve()) for x in roots) or not f.is_file():
                continue
            n = len(f.read_text(encoding="utf-8", errors="replace").split("\n"))
            if not 1 <= a <= b <= n:
                raise ProposeError(f"{name}:{a}: it has {n} lines")
            text = f.read_text(encoding="utf-8", errors="replace").split("\n")[a - 1:b]
            return f"{name}:{a}{'-' + str(b) if b != a else ''}: " + " ".join(x.strip() for x in text)[:200]
        raise ProposeError(f"{name}: no such file in the project or in ergostat")


# ---- validating, and the effect

def _fit_with(spec: Spec, data: ob.Data, params: dict[str, float]) -> dict:
    from . import fit as ft
    from . import simulate as sim
    run = sim.replay(spec, data, sim.plan(spec, params))
    partial = sim.replay(spec, data, sim.plan(spec, params, integrate=set()))
    got = ft.compare(spec, data, run, partial)
    return {"total": ft._slim(got["total"]) if run.valid else None,
            "stocks": {r: ft._slim(s) for r, s in got["stocks"].items()},
            "equations": {r: ft._slim(s) for r, s in got["partial"].items()}, "invalid": list(run.invalid)}


def refit(before: Spec, after: Spec, data: ob.Data) -> dict | None:
    """The parameters to estimate that the change brings or changes the use of, fitted to the record in the model
    it leaves (each part alone, the last fifth held out, as calibration does): their values and the fit with them."""
    from . import estimate as es
    changed = []
    for n, x in after.parameters.items():
        if not x.estimate or x.table:
            continue
        if n not in before.parameters or sorted(pr.users_of(before, n)) != sorted(pr.users_of(after, n)) or \
                any(_eq(before, r) != _eq(after, r) for r in pr.users_of(after, n)):
            changed.append(n)
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
    if not best:
        return None
    return {"values": best, "fit": _fit_with(after, data, best)}


def _eq(spec: Spec, ref: str) -> str | None:
    kind, _, name = ref.partition(".")
    x = (spec.flows if kind == "flow" else spec.auxiliaries).get(name)
    return x.equation.text if x is not None and x.equation else None


def _nmse(f: dict | None) -> float | None:
    return ((f or {}).get("total") or {}).get("nmse")


def kind_of(before: Spec, after: Spec, said: str) -> str:
    """What the change is, by what it does: values only is a parameter change, whatever it was called."""
    if ver.structure(before) == ver.structure(after):
        return "parameter"
    return said if said in ("equation", "structure") else "structure"


def validate(p, spec: Spec, by: str, raw: dict, data: ob.Data | None = None) -> dict:
    """The proposal checked and measured: its record to keep, or ``ProposeError`` with why it is not proposed."""
    if not isinstance(raw, dict):
        raise ProposeError("propose: an object with kind, parts, edit, reasons and confidence")
    said_kind = str(raw.get("kind") or "structure")
    if said_kind not in KINDS:
        raise ProposeError(f"kind: one of {', '.join(KINDS)}")
    parts = raw.get("parts") or []
    if not isinstance(parts, list) or not all(isinstance(x, str) for x in parts):
        raise ProposeError("parts: a list of references (stock.x, flow.y, parameter.z)")
    conf = raw.get("confidence")
    if isinstance(conf, str):
        conf = {"low": 0.25, "medium": 0.5, "high": 0.8}.get(conf.strip().lower(), conf)
    if conf is not None and (isinstance(conf, bool) or not isinstance(conf, int | float) or not 0 <= conf <= 1):
        raise ProposeError("confidence: a number from 0 to 1 (or low, medium, high)")
    reasons = raw.get("reasons") or []
    if isinstance(reasons, dict):
        reasons = [reasons]
    if not isinstance(reasons, list):
        raise ProposeError("reasons: a list of {says, evidence}")
    data = data or ob.measured(p, ob.reference(p))
    run_b, fit_b = tr.fit_of(spec, data)
    ev = Evidence(p, spec, data, fit_b)
    kept, refused = [], []
    for r in reasons:
        says = str((r or {}).get("says") or "").strip() if isinstance(r, dict) else str(r)
        evs = (r or {}).get("evidence") if isinstance(r, dict) else None
        evs = evs if isinstance(evs, list) else [evs]
        checked, why = [], []
        for e in evs:
            try:
                checked.append({"evidence": e, "verified": ev.check(e)})
            except ProposeError as err:
                why.append(str(err))
        if says and checked:
            kept.append({"says": says, "evidence": [c["evidence"] for c in checked], "verified": [c["verified"] for c in checked]})
        else:
            refused.append({"says": says, "why": "; ".join(why) or ("no evidence" if says else "it says nothing")})
    if not kept:
        raise ProposeError("no reason with evidence ergostat can check" +
                           (f" ({'; '.join(x['says'][:60] + ': ' + x['why'] for x in refused[:3])})" if refused else ""))
    es_ = edits(spec, raw.get("edit"))
    try:
        texts = ye.apply_together(es_)
    except ye.EditError as e:
        raise ProposeError(f"its edit cannot be made: {e}") from None
    after, problems = tr.compiled(p.model.path, texts, findings=True)
    errors = [x for x in problems if x.level == "error"]
    if errors:
        raise ProposeError("the model it leaves does not compile: " + "; ".join(str(x) for x in errors[:3]))
    before_f = set(ev.findings())
    after_f = {finding_id(x.code, x.about) for x in problems if x.level != "error"}
    data_a = ob.measured(p, data.grid, after)
    run_a, fit_a = tr.fit_of(after, data_a)
    again = refit(spec, after, data_a)
    b, a = _nmse(fit_b), _nmse(fit_a)
    ar = _nmse(again["fit"]) if again else None
    best = min((x for x in (a, ar) if x is not None), default=None)
    if run_b.valid and not run_a.valid and not (again and again["fit"].get("total")):
        raise ProposeError("with it the replay is not valid: " + "; ".join(run_a.invalid[:2]))
    if b is not None and best is not None and best > b * (1 + WORSE) and best - b > TRIFLE:
        raise ProposeError(f"it clearly worsens the fit: the scaled error goes from {b:.3g} to {best:.3g}"
                           + (" even refitted" if ar is not None else ""))
    kind = kind_of(spec, after, said_kind)
    j = joined(es_)
    x = {"kind": kind, "said_kind": said_kind, "made_by": by, "parts": parts,
         "touched": [r for r in parts if r.split(".")[0] in ("stock", "flow", "auxiliary")] or
                    [r for r in sorted(_moved(spec, after)) if r.split(".")[0] in ("stock", "flow", "auxiliary")],
         "title": str(raw.get("title") or kept[0]["says"])[:200], "reasons": kept, "refused_reasons": refused,
         "reason": "; ".join(r["says"] for r in kept), "confidence": conf, "edit": j,
         "findings": {"answered": sorted(before_f - after_f), "new": sorted(after_f - before_f)},
         "fit_before": fit_b, "fit_after": fit_a, "refit": again, "new_parts": sorted(_parts(after) - _parts(spec)),
         "gone_parts": sorted(_parts(spec) - _parts(after))}
    if kind == "parameter":
        moved = {n: q.value for n, q in after.parameters.items() if n in spec.parameters and q.value != spec.parameters[n].value}
        x["parameters"], x["previous"] = moved, {n: spec.parameters[n].value for n in moved}
        x["target"] = ", ".join(f"parameter.{n}" for n in moved) or (parts[0] if parts else "")
        x["parts"] = parts or sorted({r for n in moved for r in pr.users_of(spec, n)})
    else:
        x["target"] = parts[0] if parts else (x["new_parts"] or x["gone_parts"] or [""])[0]
        x["change"] = {"equation": "an equation changed", "structure": "a change to the structure"}[kind]
    return x


def _parts(spec: Spec) -> set[str]:
    return {f"stock.{n}" for n in spec.stocks} | {f"flow.{n}" for n in spec.flows} | {f"auxiliary.{n}" for n in spec.auxiliaries}


def _moved(before: Spec, after: Spec) -> set[str]:
    """The parts whose definition the change touches (added, removed, or its equation or causes changed)."""
    out = _parts(before) ^ _parts(after)
    for k, a, b in (("flow", before.flows, after.flows), ("auxiliary", before.auxiliaries, after.auxiliaries)):
        for n in set(a) & set(b):
            if _eq(before, f"{k}.{n}") != _eq(after, f"{k}.{n}") or sorted(map(str, a[n].driven_by)) != sorted(map(str, b[n].driven_by)):
                out.add(f"{k}.{n}")
    return out


# ---- recorded, as an ergostat.model-change item

def not_proposed(p) -> list[dict]:
    """What blocks made and ergostat refused, newest first, with why (the review queue's "found, and not proposed")."""
    xs = [x for x in pr.stored(p).values() if x["state"] == "refused" and x.get("made_by") not in (None, "ergostat", "owner")]
    return [{"id": x["id"], "title": x.get("title") or "a change", "why": x.get("why"), "by": x["made_by"],
             "at": x.get("made") or x.get("created")} for x in sorted(xs, key=lambda x: -(x.get("made") or 0))]


def _rung(spec: Spec, by: str) -> str | None:
    b = spec.blocks.get(by)
    if b is None:
        return None
    if b.agent in spec.agents and spec.agents[b.agent].kind:
        return spec.agents[b.agent].kind
    return {"ai": "ai", "program": "program", "person": "person", "external": "external", "judge": "program"}.get(b.type, "rule")


def submit(p, by: str, raw, run: str | None = None, data: ob.Data | None = None, at: float | None = None) -> dict:
    """A block's proposal: recorded as made (``ergostat.model-change.made``, from the block, caused by its run), then
    checked, or refused with why. Returns ``{"status": "proposed" | "not-proposed", "id", "title", "why"}``."""
    spec: Spec = p.model.spec
    now = at or time.time()
    title = str((raw or {}).get("title") or "a change")[:200] if isinstance(raw, dict) else "a change"
    pid = _id("made", by, run, now, json.dumps(raw, sort_keys=True, default=str))
    made = {"title": title, "made_by": by, "made_by_rung": _rung(spec, by), "made": now, "created": now,
            "version": ver.version(spec), "structure": ver.structure(spec), "run": run,
            **({k: raw.get(k) for k in ("kind", "parts", "edit", "reasons", "confidence") if k in raw} if isinstance(raw, dict) else {})}
    with pr.locked(p):
        pr.event(p, pid, "made", made, source=by, causedby=run)
        try:
            x = validate(p, spec, by, raw, data)
            same = next((y for y in pr.stored(p).values() if y["id"] != pid and y.get("version") == made["version"] and
                         (y.get("edit") or {}).get("diff") == x["edit"]["diff"] and y["state"] != "refused"), None)
            if same is not None:
                raise ProposeError(f"the same change is {'waiting' if same['status'] == 'pending' else same['status']} "
                                   f"already: {pr.item_of(same['id'])}, made by {same.get('made_by') or 'ergostat'}")
        except (ProposeError, tr.TrialError) as e:
            pr.event(p, pid, "refused", {"why": str(e)})
            return {"status": "not-proposed", "id": pid, "title": title, "why": str(e)}
        x.update({"made_by_rung": _rung(spec, by), "window": data.grid.until - data.grid.since if data else None,
                  "method": f"made by {by} ({_rung(spec, by) or 'a block'}); checked by ergostat on a scratch copy: "
                            f"compiled, checked, replayed and refitted on the reference window"})
        if x["window"] is None:
            g = ob.reference(p)
            x["window"] = g.until - g.since
        x["span"] = x["window"]
        pr.event(p, pid, "checked", x)
    return {"status": "proposed", "id": pid, "title": x["title"], "why": None}


def trial(p, raw: dict) -> dict:
    """A proposal checked and measured without landing anywhere (``ergostat improve --try``, the MCP tool
    ``try_change``): what ergostat would say of it."""
    spec: Spec = p.model.spec
    try:
        x = validate(p, spec, "trial", raw)
    except (ProposeError, tr.TrialError) as e:
        return {"would": "not be proposed", "why": str(e)}
    return {"would": "be proposed", "kind": x["kind"], "title": x["title"], "reasons": x["reasons"],
            "refused_reasons": x["refused_reasons"], "findings": x["findings"],
            "scaled_error_before": _nmse(x["fit_before"]), "scaled_error_after": _nmse(x["fit_after"]),
            "refit": (x["refit"] or {}).get("values"), "diff": x["edit"]["diff"], "new_parts": x["new_parts"],
            "gone_parts": x["gone_parts"]}
