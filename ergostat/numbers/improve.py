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
import threading
import time
from pathlib import Path

from ..durations import human as dur
from ..spec.ir import Spec
from . import display as dp
from . import gate as gt
from . import memory as mem
from . import observe as ob
from . import proposals as pr
from . import requests as rq
from . import trial as tr
from . import version as ver
from . import yamledit as ye

KINDS = ("parameter", "equation", "structure", "measurement", "control", "description", "unit", "rename", "display")
WORDING = ("description", "unit", "rename", "display")   # what a reader is told or shown, not what moves: never replayed
WORSE = gt.WORSE            # a proposal whose scaled error rises past this share (and not by a trifle) clearly worsens the fit
TRIFLE = gt.TRIFLE
CITED = "cited, not checked"   # a rule, a line or a URL: it says where a reason comes from, not that it holds here
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
    "simplest-structure": "SD Lab's simplify rules (structural.py): structure with no declared reason that the record shows "
                          "redundant goes, and the owner decides; a declared part the record has not exercised stays",
    "not-exercised": "Sterman ch. 21: a record that has not exercised a part cannot identify its rate; quiet is not absent "
                     "(docs/MODELLING.md §9)",
    "first-order-drain": "Sterman ch. 8: an outflow is its stock over the time things stay",
    "moving-average-lag": "Sterman ch. 11.5: a moving average over L lags by L/2",
}
URL = re.compile(r"^https?://\S+$")
PATH_LINE = re.compile(r"^(?P<path>[^:\s][^:]*):(?P<a>\d+)(?:-(?P<b>\d+))?$")


class ProposeError(Exception):
    pass


class GateError(ProposeError):
    """Refused for what the record says of it (it worsens the fit), not for its form: remembered (``memory``)."""


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


SECTIONS = {"stock": "stocks", "flow": "flows", "auxiliary": "auxiliaries", "parameter": "parameters", "goal": "goals",
            "block": "blocks", "items": "items", "agent": "agents"}


def _value(v) -> str:
    if isinstance(v, list):
        return "[" + ", ".join(ye.scalar(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ", ".join(f"{k}: {_value(x)}" for k, x in v.items()) + "}"
    return ye.scalar(v)


def _part(spec: Spec, ref: str):
    kind, _, name = str(ref).partition(".")
    table = {"stock": spec.stocks, "flow": spec.flows, "auxiliary": spec.auxiliaries, "parameter": spec.parameters,
             "goal": spec.goals, "block": spec.blocks, "items": spec.items, "agent": spec.agents}.get(kind)
    x = (table or {}).get(name)
    if x is None:
        raise ProposeError(f"part: {ref} is not a part of the model (stock.x, flow.y, auxiliary.z, parameter.p, goal.g, "
                           f"block.b, items.k, agent.a)")
    ye.own(getattr(x, "where", None), str(ref))
    w = getattr(x, "defined", None) or getattr(x, "where", None)
    if w is None:
        raise ProposeError(f"{ref}: where it is written is not known")
    path = _model_file(spec, str(w.file))
    ls = ye.lines_of(path)
    for i in range(min(w.line, len(ls)) - 1, -1, -1):          # the line its name is on (its map, or inline)
        if re.match(rf"^\s*{re.escape(name)}\s*:", ls[i]):
            return x, path, i + 1
    raise ProposeError(f"{ref}: its name is not found above {path.name}:{w.line}")


def _set(spec: Spec, one: dict) -> list[ye.Edit]:
    """``{"part": "stock.x", "set": {"unit": "alerts", "description": "..."}}``: each key set on the part (replaced
    when it is there, else added), ``"sensor": NAME`` to set them on one of its sensors; or ``{"add": "parameters",
    "name": "time-in-x", "set": {...}}``: a new entry in a section (``file`` names the file, else the main one)."""
    keys = one.get("set")
    if not isinstance(keys, dict) or not keys:
        raise ProposeError("set: a map of key: value")
    if one.get("add"):
        sec = str(one["add"])
        name = str(one.get("name") or "")
        if sec not in SECTIONS.values() or not re.match(r"^[a-z][a-z0-9-]*$", name):
            raise ProposeError(f"add: a section ({', '.join(SECTIONS.values())}) and name: the new entry's name")
        path = _model_file(spec, str(one.get("file") or spec.files[0]))
        lines = [f"  {name}:"] + [f"    {k}: {_value(v)}" for k, v in keys.items()]
        return [ye.add_entries(path, sec, [lines])]
    x, path, at = _part(spec, str(one.get("part") or ""))
    ls = ye.lines_of(path)
    if one.get("sensor"):
        sname = str(one["sensor"])
        end, _ = ye.children(ls, at)
        hit = None
        for i in range(at, end):
            t = ls[i].strip()
            if (sname == "main" and re.match(r"^sensor\s*:", t)) or re.match(rf"^{re.escape(sname)}\s*:", t):
                hit = i + 1
                break
        if hit is None and re.search(r"sensor\s*:\s*\{", ls[at - 1]):
            raise ProposeError(f"{one['part']}: written on one line with its sensor; write it out a key a line first")
        if hit is None:
            raise ProposeError(f"{one['part']}: no sensor {sname}")
        return [ye.set_inline(path, hit, k, _value(v)) if re.search(r":\s*\{", ls[hit - 1]) else ye.set_key(path, hit, k, _value(v))
                for k, v in keys.items()]
    out = []
    for k, v in keys.items():
        if re.search(r":\s*\{", ls[at - 1]):
            out.append(ye.set_inline(path, at, str(k), _value(v)))
        else:
            out.append(ye.set_key(path, at, str(k), _value(v)))
    return out


def edits(spec: Spec, raw) -> list[ye.Edit]:
    """A proposal's edit, as ``ye.Edit``s on the model's files: the review queue's form, ``replace``, or ``set``."""
    if isinstance(raw, dict) and "files" in raw:
        raw = raw["files"]
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list) or not raw:
        raise ProposeError("edit: {files: [{file, hunks: [{line, old, new}]}]}, or {file, replace, with}")
    out = []
    for one in raw:
        if not isinstance(one, dict) or not (one.get("file") or one.get("part") or one.get("add")):
            raise ProposeError("each edit names its file (from the model's folder), or the part it sets")
        if "set" in one:
            try:
                got = _set(spec, one)
            except ye.EditError as e:
                raise ProposeError(str(e)) from None
            by: dict[str, list] = {}
            for e in got:
                by.setdefault(e.file, []).append(e)
            out += [ye.merge(es_) for es_ in by.values()]
            continue
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

_FOUND: dict[str, tuple] = {}             # the model's findings by its files' texts: one check a model, however
_FOUND_LOCK = threading.Lock()            # many proposals a block prints against it


def _found(path: Path, files) -> tuple[dict[str, str], set[str]]:
    """What ``check`` finds in the model at ``path`` as its files read now (``finding_id``: message), and its notes."""
    from ..spec import read
    h = hashlib.sha1(str(path).encode())
    for f in sorted({str(x) for x in files}):
        try:
            h.update(f.encode() + b"\0" + Path(f).read_bytes() + b"\0")
        except OSError:
            h.update(f.encode() + b"\0-\0")
    key = h.hexdigest()
    with _FOUND_LOCK:
        got = _FOUND.get(key)
    if got is None:
        _, problems = read(path)
        got = ({finding_id(x.code, x.about): x.message for x in problems if x.level != "error"},
               {finding_id(x.code, x.about) for x in problems if rq.as_note(x)})
        with _FOUND_LOCK:
            if len(_FOUND) > 8:
                _FOUND.clear()
            _FOUND[key] = got
    return dict(got[0]), set(got[1])


class Evidence:
    """What ergostat can check a reason against, worked out once and only when a reason needs it."""

    def __init__(self, p, spec: Spec, data: ob.Data | None = None, fit: dict | None = None):
        self.p, self.spec, self.data, self._fit = p, spec, data, fit
        self._findings = None
        self._residuals = None

    def findings(self) -> dict[str, str]:
        if self._findings is None:
            self._findings, self._notes = _found(self.p.model.path, getattr(self.spec, "files", None) or [])
        return self._findings

    def notes(self) -> set[str]:
        self.findings()
        return self._notes

    def fit(self) -> dict:
        if self._fit is None:
            data = self.data or ob.measured(self.p, ob.reference(self.p))
            _, self._fit = tr.fit_of(self.spec, data)
        return self._fit

    def mismatches(self) -> dict[str, str]:
        """The coherence mismatches over the record (``coherence.py``), by ``CODE@ABOUT``."""
        if getattr(self, "_mismatches", None) is None:
            try:
                from .. import coherence as co
                got = co.of_project(self.p, self.spec)
            except Exception:
                got = {"findings": []}
            self._mismatches = {f"{f['code']}@{f['about']}": f["message"] for f in got.get("findings") or []
                                if f.get("level") == "mismatch"}
        return self._mismatches

    def residuals(self) -> dict:
        if self._residuals is None:
            from .. import state
            self._residuals = state.snapshot(self.p, state.WINDOW, None).get("residuals") or {}
        return self._residuals

    def check(self, ev) -> str:
        """What the evidence says, checked; or ``ProposeError`` with why it is not evidence."""
        if isinstance(ev, dict) and len(ev) == 1:
            (k, v), = ev.items()
            ev = f"{k}:{v}" if k in ("finding", "fit", "residual", "rule", "coherence", "request") else str(v)
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
        if kind == "request":
            from . import requests as rq
            x = rq.stored(self.p).get(what.removeprefix(f"{rq.MODELLING_REQUEST}/"))
            if x is None or x["state"] == "answered":
                raise ProposeError(f"{ev}: no request open by that id")
            return str(x.get("says") or x.get("code"))
        if kind == "coherence":
            got = self.mismatches()
            if what not in got:
                raise ProposeError(f"{ev}: coherence does not find it now over the record")
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
        raise ProposeError(f"{ev}: not evidence ergostat can check: a finding (finding:CODE@PART), a coherence mismatch "
                           f"(coherence:CODE@PART), a fit statistic "
                           f"(fit:total.nmse), a residual (residual:stock.NAME), a document or code line (path:LINE), a URL, "
                           f"or a modelling rule (rule:NAME)")

    def supports(self, ev, near: set[str], answered: set[str], fit_after: dict | None) -> str | None:
        """Whether checked evidence supports the change, not only exists: None when it does, else why not. A finding
        is about a part the change touches or one next to it, or one it answers (gone in the model it leaves); a fit
        statistic is
        of such a part, or the total and the change does not raise it; a residual is of such a stock, and significant;
        a rule is one ``check`` applies to such a part now. A rule ``check`` does not test, a line and a URL are cited
        only: they say where a reason comes from, never that it holds here."""
        if isinstance(ev, dict) and len(ev) == 1:
            (k, v), = ev.items()
            ev = f"{k}:{v}" if k in ("finding", "fit", "residual", "rule", "coherence", "request") else str(v)
        ev = str(ev).strip()
        kind, _, what = ev.partition(":")
        where = ", ".join(sorted(near)[:6]) + ("…" if len(near) > 6 else "")
        if kind == "request":
            from . import requests as rq
            x = rq.stored(self.p).get(what.removeprefix(f"{rq.MODELLING_REQUEST}/")) or {}
            about = x.get("about")
            if x.get("source") == "events":            # events no projection takes: the judge counts them before and
                return None                            # after (unexplained.judged); only a projection change answers it
            return None if about in (None, "model") or about in near else \
                f"{ev}: about {about}, which the change does not touch (it touches {where})"
        if kind in ("finding", "coherence"):
            about = what.split("@", 1)[1] if "@" in what else None
            if about is None:
                return None if what in answered else f"{ev}: about no part, and the change does not answer it"
            if about in near or what in answered:          # (a finding about a kind, items.K, the change answers)
                return None
            return f"{ev}: about {about}, which the change does not touch (it touches {where})"
        if kind == "fit":
            ref, _, stat = what.rpartition(".")
            if ref == "total":
                b, a = gt.total(self._fit), gt.total(fit_after)
                if b is not None and a is not None and a > b + TRIFLE:
                    return f"{ev}: the change raises the scaled error it cites ({gt.said(b, a)})"
                return None
            return None if ref in near else f"{ev}: of {ref}, which the change does not touch (it touches {where})"
        if kind == "residual":
            ref = what if what.startswith("stock.") else f"stock.{what}"
            if ref not in near:
                return f"{ev}: of {ref}, which the change does not touch (it touches {where})"
            r = self.residuals().get(ref[6:]) or {}
            return None if r.get("significant") else f"{ev}: not significant"
        if kind == "rule":
            hits = [k for k in self.findings() if k.split("@")[0] == what]
            if hits:
                mine = [k for k in hits if "@" in k and k.split("@", 1)[1] in near]
                return None if mine else (f"{ev}: check finds it at {', '.join(hits[:3])}, none of which the change touches "
                                          f"(it touches {where})")
            return f"{ev}: {CITED} (check does not test this rule against the parts it touches)"
        return f"{ev}: {CITED}"

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
    """What the change is, by what it does, whatever it was called: a goal, a block (the judge's policy among its
    keys) or an agent changed is a **control** change; a sensor of a part already there, a **measurement** change; the
    same model under new names (each says ``formerly:`` its old one) a **rename**; else values only is a parameter
    change, units alone a **unit** change, descriptions alone a **description** change, and the rest an equation or the
    structure. The parameter, equation and structure are the dynamics model's to judge on the record; a description,
    a unit and a rename change what a reader is told, not what moves; ``dashboards:`` alone is a **display** change."""
    if dp.display_only(before, after):
        return "display"
    if ver.renamed_parts(before, after):
        return "rename"
    if ver.control(before) != ver.control(after):
        return "control"
    if ver.changed_sensors(before, after):
        return "measurement"
    if ver.items(before) != ver.items(after):
        return "structure"                                   # how items move: what the chains and the record read
    if ver.structure_but_units(before) == ver.structure_but_units(after) and ver.values(before) == ver.values(after):
        if ver.units(before) != ver.units(after):
            return "unit"
        if ver.words(before) != ver.words(after):
            return "description"
        return "parameter"
    if ver.structure(before) == ver.structure(after):
        return "parameter"
    return said if said in ("equation", "structure") else "structure"


def governs(before: Spec, after: Spec) -> list[str]:
    """What a change alters of who decides what is written: the judge's policy (``accept``, its threshold, hold-out,
    windows), a block's ``accept``, a template instance's ``with:``. Only the owner changes these, by hand: a proposal
    that does is refused, whoever made it."""
    import dataclasses
    out = []
    if dataclasses.asdict(before.improve) != dataclasses.asdict(after.improve):
        out.append("the judge's policy")
    for n in sorted(set(before.blocks) & set(after.blocks)):
        if (before.blocks[n].params or {}).get("accept") != (after.blocks[n].params or {}).get("accept"):
            out.append(f"block {n}'s accept")
    for n in sorted(set(before.uses) | set(after.uses)):
        a, b = (before.uses.get(n) or {}).get("values"), (after.uses.get(n) or {}).get("values")
        if a != b:
            out.append(f"use {n}'s with:")
    return out


def _governed(before: Spec, after: Spec) -> None:
    got = governs(before, after)
    if got:
        raise ProposeError(f"it changes {', '.join(got)}: who decides what is written is the owner's to change, by hand")


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
    said_parts = list(parts)
    es_ = edits(spec, raw.get("edit"))
    try:
        texts = ye.apply_together(es_)
    except ye.EditError as e:
        raise ProposeError(f"its edit cannot be made: {e}") from None
    after, problems = tr.compiled(p.model.path, texts)   # its errors first; what check finds once, on the text kept
    errors = [x for x in problems if x.level == "error"]
    if errors:
        raise ProposeError("the model it leaves does not compile: " + "; ".join(str(x) for x in errors[:3]))
    _governed(spec, after)
    marked = mark_new(es_, spec, after)                  # what it adds says so: inferred: (the change's id when recorded)
    problems = None
    if marked is not None:
        try:
            after2, problems2 = tr.compiled(p.model.path, ye.apply_together(marked), findings=True)
        except (ye.EditError, tr.TrialError):
            after2, problems2 = None, []
        if after2 is not None and not [x for x in problems2 if x.level == "error"]:
            es_, after, problems = marked, after2, problems2
    if problems is None:
        after, problems = tr.compiled(p.model.path, texts, findings=True)
    before_f = set(ev.findings())
    after_f = {finding_id(x.code, x.about) for x in problems if x.level != "error"}
    notes = {finding_id(x.code, x.about) for x in problems if rq.as_note(x)} | ev.notes()   # the craft: not findings
    kind = kind_of(spec, after, said_kind)
    if "display" in (said_kind, kind):                    # dashboards: alone, said so, and nothing beside them
        bad = dp.beside(texts)
        if bad or said_kind != kind:
            raise ProposeError(f"not a display change: it changes {', '.join(bad)}" if bad else
                               f"not a display change: it is a {kind} change" if said_kind == "display" else
                               "it changes dashboards: alone: a display change, proposed as kind: display")
    if kind == "rename":                                  # the same findings under the new names are not new
        before_f = {_renamed_id(f, ver.renamed_parts(spec, after) or {}) for f in before_f}
    if kind in WORDING:                                   # what a reader is told: the replay reads the same record alike
        fit_a, again, best_fit = fit_b, None, fit_b
    else:
        data_a = ob.measured(p, data.grid, after)
        run_a, fit_a = tr.fit_of(after, data_a)
        again = refit(spec, after, data_a)
        a = _nmse(fit_a)
        ar = _nmse(again["fit"]) if again else None
        best_fit = again["fit"] if ar is not None and (a is None or ar < a) else fit_a
        if run_b.valid and not run_a.valid and not (again and again["fit"].get("total")):
            raise ProposeError("with it the replay is not valid: " + "; ".join(run_a.invalid[:2]))
    refs = touched_refs(spec, after, said_parts, kind)
    near = gt.neighbourhood(spec, refs) | gt.neighbourhood(after, refs)
    g = gt.check(spec, fit_b, best_fit, refs)
    if kind in WORDING:
        g["worse"] = None
    if g["worse"]:
        key = mem.key({"kind": kind, "target": _target(spec, after, said_parts, kind), "made_by": by})
        raise GateError(f"it clearly worsens the fit: {g['worse']}" + (" even refitted" if again else ""), key)
    from . import exercised as ex
    q = ex.quiet(spec, data)
    renames = ver.renamed_parts(spec, after) or {}
    for r in sorted(_parts(spec) - _parts(after) - set(renames)):   # a declared part taken away for being quiet: not proposed
        kind_, _, name = r.partition(".")
        if r in q and not ex.inferred(spec.measured(kind_).get(name)):
            key = mem.key({"kind": kind, "target": _target(spec, after, said_parts, kind), "made_by": by})
            raise GateError(f"it removes {r}, which the model declares and the record has not exercised ({q[r]['says']}): "
                            f"quiet is not absent, so the record is no evidence against it (rule:not-exercised). A removal "
                            f"needs the record to show the part redundant, and waits for the owner", key)
    answered = before_f - after_f
    supported = 0
    for r in kept:
        r["supports"] = [ev.supports(e, near, answered, best_fit) for e in r["evidence"]]
        r["supported"] = any(x is None for x in r["supports"])
        supported += r["supported"]
    if not supported and kind != "display":            # a display change moves nothing a fit or a finding could support
        raise ProposeError("no reason with evidence that supports it: " +
                           "; ".join(w for r in kept for w in r["supports"] if w)[:600])
    j = joined(es_)
    x = {"kind": kind, "said_kind": said_kind, "made_by": by, "parts": parts,
         "touched": [r for r in parts if r.split(".")[0] in ("stock", "flow", "auxiliary")] or
                    [r for r in sorted(_moved(spec, after)) if r.split(".")[0] in ("stock", "flow", "auxiliary")],
         "title": str(raw.get("title") or kept[0]["says"])[:200], "reasons": kept, "refused_reasons": refused,
         "reason": "; ".join(r["says"] for r in kept), "confidence": conf, "edit": j,
         "findings": {"answered": sorted((before_f - after_f) - notes), "new": sorted((after_f - before_f) - notes),
                      "notes_answered": sorted((before_f - after_f) & notes), "notes_new": sorted((after_f - before_f) & notes)},
         "gate": {"whole": g["whole"], "local": g["local"], "said": gt.summary(g)}, "neighbourhood": g["neighbourhood"],
         "fit_before": fit_b, "fit_after": fit_a, "refit": again, "new_parts": sorted(_parts(after) - _parts(spec)),
         "gone_parts": sorted(_parts(spec) - _parts(after))}
    if kind == "parameter":
        moved = {n: q.value for n, q in after.parameters.items() if n in spec.parameters and q.value != spec.parameters[n].value}
        x["parameters"], x["previous"] = moved, {n: spec.parameters[n].value for n in moved}
        x["target"] = _target(spec, after, parts, kind)
        x["parts"] = parts or sorted({r for n in moved for r in pr.users_of(spec, n)})
        held = [h for n in moved if (h := ex.parameter_quiet(spec, data, n, q))]
        if held and len(held) == len(moved):              # nothing it sets is exercised: held, not judged on this record
            x["not_exercised"] = "; ".join(f"{h['ref']}: {h['says']}" for h in held)
        else:                                             # too little record to identify what it sets: held likewise
            from . import identify as idf
            short = idf.record_says(spec, data, moved)
            if short and len(short) == len(moved):
                needs = [h["needs"] for h in short.values()]
                x["needs"] = None if None in needs else max(needs)
                x["too_short"] = ("; ".join(f"parameter.{n}: {'; '.join(h['why'])}" for n, h in sorted(short.items())) +
                                  (f"; it needs about {dur(x['needs'])} more record" if x["needs"] else
                                   "; it needs record in which what it acts through moves"))
    else:
        moved_ctl = ver.changed_control(spec, after) if kind == "control" else ver.changed_sensors(spec, after) \
            if kind == "measurement" else []
        x["target"] = _target(spec, after, parts, kind) or (x["new_parts"] or x["gone_parts"] or [""])[0]
        x["change"] = {"equation": "an equation changed", "structure": "a change to the structure",
                       "control": "a change to what decides (a goal, a block or the judge)",
                       "measurement": "a change to how the world is read (a sensor)",
                       "description": "a part's description: what the diagrams say of it",
                       "unit": "a part's unit", "display": "a dashboard declared: what a page shows",
                       "rename": "a part renamed, every reference with it, its history kept"}[kind]
        from . import structural as stc
        if stc.rewired(spec, after):                     # whoever made it: a chain rewired is the owner's to write
            x["rewires"] = True
        if kind == "rename":
            x["renames"] = renames
        if kind in ("description", "unit"):
            x["parts"] = list(dict.fromkeys([*(".".join(r.split(".")[:2]) for r in (
                ver.changed_words(spec, after) if kind == "description" else ver.changed_units(spec, after))), *parts]))
        if moved_ctl:
            x["parts"] = list(dict.fromkeys([*moved_ctl, *parts]))
    joins = [f"stock.{s}" for n in set(after.flows) - set(spec.flows) for s in (after.flows[n].source, after.flows[n].target) if s]
    about = [r for r in [*refs, *joins, *x["gone_parts"]] if pr._part(spec, r) is not None]
    if about:                                            # what it is about, as the model has it: held to it when carried
        x["subject"] = pr.subject(spec, about)
    explains = sorted({str(e).split(":", 1)[1].removeprefix(f"{rq.MODELLING_REQUEST}/") for r in kept for e in r["evidence"]
                       if isinstance(e, str) and e.startswith("request:")
                       and (rq.stored(p).get(e.split(":", 1)[1].removeprefix(f"{rq.MODELLING_REQUEST}/")) or {}).get("source")
                       == "events"})
    if explains:                                         # it answers events no projection takes: judged by what it takes
        from . import unexplained as ux
        x["explains"] = explains
        x["projections_changed"] = ux.changed_projections(spec, after)
        if not x["projections_changed"]:
            raise ProposeError("it cites events no projection takes, and changes no projection")
        bodies = raw.get("drafted") if isinstance(raw.get("drafted"), dict) else {}
        x["drafted"] = {str(n): str(b)[:20000] for n, b in bodies.items() if str(n) in x["projections_changed"]}
    x["key"] = mem.key(x)
    return x


def _renamed_id(fid: str, renames: dict[str, str]) -> str:
    code, _, about = fid.partition("@")
    return f"{code}@{renames.get(about, about)}" if about else fid


def _new_named(before: Spec, after: Spec) -> list[tuple[str, str]]:
    """``(section, name)`` of each stock, flow, auxiliary and parameter a change adds and does not mark inferred."""
    out = []
    for sec, a, b in (("stocks", before.stocks, after.stocks), ("flows", before.flows, after.flows),
                      ("auxiliaries", before.auxiliaries, after.auxiliaries), ("parameters", before.parameters, after.parameters)):
        out += [(sec, n) for n in sorted(set(b) - set(a)) if not getattr(b[n], "inferred", None)]
    return out


def mark_new(es_: list[ye.Edit], before: Spec, after: Spec) -> list[ye.Edit] | None:
    """A block's edit with ``inferred:`` written on each part it adds (SPEC §12e), under the line its name is on in the
    lines it adds, indented as that part's keys are; the change's own id is stamped in when it is recorded
    (``structural.stamp``). None when it adds nothing to mark; a part written in the short form (``k: 0.45``), or
    whose name is not on a line of its own, is left as written."""
    from . import structural as stc
    want = _new_named(before, after)
    if not want:
        return None
    out, done = [], 0
    for e in es_:
        hunks = []
        for h in e.hunks:
            new = list(h.new)
            for _, name in want:
                pat = re.compile(rf"^(\s*){re.escape(name)}:\s*(#.*)?$")
                for i, line in enumerate(new):
                    m = pat.match(line)
                    if not m:
                        continue
                    nxt = new[i + 1] if i + 1 < len(new) else ""
                    ind = len(nxt) - len(nxt.lstrip()) if nxt.strip() and ye.indent(nxt) > len(m.group(1)) else len(m.group(1)) + 2
                    new.insert(i + 1, " " * ind + f"inferred: {stc.PENDING}")
                    done += 1
                    break
            hunks.append(ye.Hunk(h.line, list(h.old), new))
        out.append(ye.Edit(e.file, hunks))
    return out if done else None


def unstamped(diff: str | None) -> str:
    """A diff with every model change's id said alike, so the same edit from two runs is the same edit."""
    return re.sub(r"ergostat\.model-change/[0-9a-z-]+", "ergostat.model-change/new", diff or "")


def stamped(edit: dict, pid: str) -> dict:
    """An edit (the review queue's form) with ``inferred: PENDING`` made this change's item."""
    from . import structural as stc
    return json.loads(json.dumps(edit).replace(stc.PENDING, pr.item_of(pid)))


def _target(spec: Spec, after: Spec, parts: list[str], kind: str) -> str:
    """What a change is to, as ``validate`` names it: the parameters it sets, else the goal, block or sensor it alters,
    else the first part it names."""
    if kind == "parameter":
        moved = [f"parameter.{n}" for n, q in after.parameters.items() if n in spec.parameters and q.value != spec.parameters[n].value]
        if moved:
            return ", ".join(moved)
    ctl = ver.changed_control(spec, after) if kind == "control" else ver.changed_sensors(spec, after) if kind == "measurement" else []
    return (ctl or parts or [""])[0]


def touched_refs(before: Spec, after: Spec, parts: list[str], kind: str) -> list[str]:
    """What a change touches: the parts it names, the parts whose definition it moves, the parameters whose values
    it changes, and the goals, blocks and sensors it alters."""
    out = list(parts) + sorted(_moved(before, after))
    out += [f"parameter.{n}" for n, q in after.parameters.items()
            if n in before.parameters and q.value != before.parameters[n].value]
    out += ver.changed_control(before, after) + ver.changed_sensors(before, after)
    out += [".".join(r.split(".")[:2]) for r in ver.changed_words(before, after) + ver.changed_units(before, after)]
    out += list((ver.renamed_parts(before, after) or {}).values())
    return list(dict.fromkeys(out))


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
             "at": x.get("made") or x.get("created"), "held_back": x.get("held_back")}
            for x in sorted(xs, key=lambda x: -(x.get("made") or 0))]


def _rung(spec: Spec, by: str) -> str | None:
    b = spec.blocks.get(by)
    if b is None:
        return None
    if b.agent in spec.agents and spec.agents[b.agent].kind:
        return spec.agents[b.agent].kind
    return {"ai": "ai", "program": "program", "person": "person", "external": "external"}.get(b.type, b.builtin_rung)


def submit(p, by: str, raw, run: str | None = None, data: ob.Data | None = None, at: float | None = None) -> dict:
    """A block's proposal: recorded as made (``ergostat.model-change.made``, from the block, caused by its run), then
    checked, or refused with why. Returns ``{"status": "proposed" | "not-proposed", "id", "title", "why"}``."""
    from . import reviewer as rv
    spec: Spec = p.model.spec
    now = at or time.time()
    title = str((raw or {}).get("title") or "a change")[:200] if isinstance(raw, dict) else "a change"
    pid = _id("made", by, run, now, json.dumps(raw, sort_keys=True, default=str))
    made = {"title": title, "made_by": by, "made_by_rung": _rung(spec, by), "made": now, "created": now,
            "version": ver.version(spec), "structure": ver.structure(spec), "run": run,
            **({k: raw.get(k) for k in ("kind", "parts", "edit", "reasons", "confidence") if k in raw} if isinstance(raw, dict) else {})}
    with pr.locked(p):
        x, err = None, None
        try:
            x = validate(p, spec, by, raw, data)
            x.update(rv.asked(p, by, x.get("parts")))   # sent back by the reviewer: this is its next round
            if x.get("review_held"):
                raise ProposeError(x["review_held"])
            same = next((y for y in pr.stored(p).values() if y["id"] != pid and y.get("version") == made["version"] and
                         unstamped((y.get("edit") or {}).get("diff")) == unstamped(x["edit"]["diff"])
                         and y["state"] != "refused"), None)
            if same is not None:
                raise ProposeError(f"the same change is {'waiting' if same['status'] == 'pending' else same['status']} "
                                   f"already: {pr.item_of(same['id'])}, made by {same.get('made_by') or 'ergostat'}")
        except (ProposeError, tr.TrialError) as e:
            err = e
        gated = isinstance(err, GateError)
        if err is None or gated:                    # what the record said of it: turned away before, and not again yet?
            k = err.args[1] if gated else mem.key(x)
            h = mem.held(p, spec, k, now)
            if h is not None:
                n = int(mem.repeat(p, h, title, str(run or now), by).get("repeats") or 0)
                why = f"held back: {pr.item_of(h['prior']['id'])} was {h['prior']['state']} for the same target; " + \
                    mem.said(n, h["until"], h["wait"])
                return {"status": "not-proposed", "id": h["prior"]["id"], "title": title, "why": why}
        pr.event(p, pid, "made", made, source=by, causedby=run)
        if err is not None:
            g = data.grid if data else ob.reference(p, now)
            pr.event(p, pid, "refused", {"why": err.args[0] if gated else str(err), "window": g.until - g.since,
                                         **({"gated": True, "key": k} if gated else {})})
            return {"status": "not-proposed", "id": pid, "title": title, "why": err.args[0] if gated else str(err)}
        x["edit"] = stamped(x["edit"], pid)
        x.update({"made_by_rung": _rung(spec, by), "window": data.grid.until - data.grid.since if data else None,
                  "method": f"made by {by} ({_rung(spec, by) or 'a block'}); checked by ergostat on a scratch copy: "
                            f"compiled, checked, replayed and refitted on the reference window"})
        if x["window"] is None:
            g = ob.reference(p)
            x["window"] = g.until - g.since
        x["span"] = x["window"]
        if x.get("not_exercised") or x.get("too_short"):  # a value the record cannot identify yet: held, inconclusive
            why = (f"held, inconclusive: the record has not exercised what it sets ({x['not_exercised']}); its value "
                   f"cannot be identified from this record, and nothing says the value written is wrong"
                   if x.get("not_exercised") else
                   f"held, inconclusive: the record is too short to identify what it sets ({x['too_short']}), and nothing "
                   f"says the value written is wrong")
            pr.event(p, pid, "inconclusive", {**x, "why": why, "verdict": {"verdict": "inconclusive", "why": why, "at": now,
                                                                              "by": "ergostat"}})
            return {"status": "not-proposed", "id": pid, "title": x["title"], "why": why}
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
