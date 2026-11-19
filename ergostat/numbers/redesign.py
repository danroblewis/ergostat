"""Redesign beside refinement (SPEC §12e, *Redesign*): one change set (``changeset.py``), many coordinated edits
proposed together, judged as a whole by a scorecard (``scorecard.py``), kept as one ``ergostat.model-change`` item of
kind ``redesign``.

A change set is written ``{"title", "system", "summary", "edits": [...], "confidence"}``: the edits are made in order on
a scratch copy, it must compile, and it is measured against the record as it is; what it adds says ``inferred:`` (the
change's own id once recorded). Its verdict is the scorecard's, said again by the judge on the record when it takes it
up. It is never written by the judge unless the owner promoted the class by name (``accept: {redesign: auto}``).

When one is made (``due``): the model clearly wrong (many findings, a kind's coherence low on the record, a fit that
cannot be worked out, refinement stalling: its last changes all turned away), the owner asking (``ergostat improve
--redesign [SYSTEM]``, the Model page's button: ``ask``), or the model's first run with ``use: modelling``. At most one
waits for each system; on its own it is made once a version of the model (the owner's ask is not held to that)."""

from __future__ import annotations

import json
import time

from ..spec.ir import Spec
from . import changeset as cs
from . import improve as im
from . import proposals as pr
from . import version as ver

KIND = "redesign"
ASKED = "ergostat.model.redesign-asked"
RAN = "ergostat.model.redesign-ran"
MANY_FINDINGS = 3            # findings check reports (that a change to the model answers) that make the model clearly wrong
LOW_COHERENCE = 0.8          # a kind whose views agree on less than this share of the record's comparisons
STALL = 4                    # refinement's last changes judged, all turned away: refinement stalling
REFINERS = ("fixer", "modeller", "improver", "improver-by-hand")


def settings(spec: Spec) -> dict:
    """The redesigner's settings, as the template's ``redesign:`` gave its block (``--model``, ``--budget``,
    ``--rounds``, ``--when``), else the defaults."""
    import shlex
    out = {"when": "auto", "model": "haiku", "budget": 0.5, "rounds": 3}
    b = spec.blocks.get("redesigner")
    run = str((b.params.get("run") if b is not None else "") or "")
    try:
        words = shlex.split(run)
    except ValueError:
        words = []
    for k in ("when", "model", "budget", "rounds"):
        if f"--{k}" in words and words.index(f"--{k}") + 1 < len(words):
            v = words[words.index(f"--{k}") + 1]
            out[k] = float(v) if k == "budget" else int(v) if k == "rounds" else v
    return out


def system_of(spec: Spec, system: str | None) -> str:
    s = (system or "").strip()
    if s and s not in ("model", "all") and s not in spec.systems:
        raise ValueError(f"no system {s} (the model's: {', '.join(sorted(spec.systems)) or 'none: the whole model'})")
    return s if s and s not in ("all",) else "model"


def members(spec: Spec, system: str) -> list[str]:
    """The parts of a system (every part of the model for ``model``)."""
    if system == "model":
        return [f"{k}.{n}" for k, t in (("stock", spec.stocks), ("flow", spec.flows), ("auxiliary", spec.auxiliaries),
                                       ("parameter", spec.parameters), ("goal", spec.goals), ("block", spec.blocks))
                for n in t]
    from ..correspond import inside
    return [x for x in inside(spec, system) if not x.startswith("system.")]


# ---- made and recorded

def validate(p, spec: Spec, by: str, raw: dict, scratch: cs.Scratch | None = None) -> dict:
    """A change set checked and scored: its record to keep, or ``ProposeError`` with why it is not proposed."""
    from . import scorecard as sc
    if not isinstance(raw, dict):
        raise im.ProposeError("a change set: {title, system, summary, edits: [...]}")
    edits = raw.get("edits")
    if not isinstance(edits, list) or not edits:
        raise im.ProposeError("edits: a list of edits, made in order")
    system = system_of(spec, raw.get("system"))
    s = scratch
    if s is None:
        s = cs.Scratch(p, spec)
        for i, e in enumerate(edits):
            try:
                s.apply(e)
            except cs.ChangeSetError as err:
                raise im.ProposeError(f"edit {i + 1} ({cs.said(e) if isinstance(e, dict) else e!r}): {err}") from None
    s.keep_names()
    if not s.changed():
        raise im.ProposeError("it changes nothing")
    after, problems = s.compiled()
    if after is None:
        raise im.ProposeError("the model it leaves does not compile: " + "; ".join(s.errors()[:3]))
    es_ = s.edits()
    marked = _renamed_unmarked(im.mark_new(es_, spec, after), spec, after)   # what it adds says inferred: (its id when
    # recorded); a part renamed is not new: it keeps what it said (formerly: its old name)
    if marked is not None:
        try:
            after2, problems2 = s_compiled(p, marked)
            if after2 is not None and not [x for x in problems2 if x.level == "error"]:
                es_, after, problems = marked, after2, problems2
        except Exception:
            pass
    from ..spec import read
    _, before_problems = read(p.model.path)
    card = sc.score(p, spec, before_problems, after, problems)
    parts = card["parts"]
    refs = [*parts["added"], *parts["changed"], *(x.split(" → ")[1] for x in parts["renamed"])]
    j = im.joined(es_)
    conf = raw.get("confidence")
    return {"kind": KIND, "said_kind": KIND, "made_by": by, "system": system,
            "title": str(raw.get("title") or f"A redesign of {system}")[:200],
            "summary": str(raw.get("summary") or "")[:2000], "reason": str(raw.get("summary") or raw.get("title") or "")[:500],
            "confidence": conf if isinstance(conf, int | float) and 0 <= conf <= 1 else None,
            "parts": refs[:60], "touched": [r for r in refs if r.split(".")[0] in ("stock", "flow", "auxiliary")][:60],
            "target": system, "new_parts": parts["added"], "gone_parts": parts["removed"],
            "redesign": {"edits": s.done, "parts": parts, "rounds": raw.get("rounds"), "cost": raw.get("cost")},
            "scorecard": card, "findings": {"answered": card["findings"]["resolved"], "new": card["findings"]["introduced"],
                                            "notes_answered": card["craft"]["closed"], "notes_new": card["craft"]["opened"]},
            "edit": j, "change": "a redesign: many edits judged together by a scorecard",
            "renames": {o: n for o, n in (x.split(" → ") for x in parts["renamed"])
                        if o.split(".")[0] in ("stock", "flow", "auxiliary")}}


def _renamed_unmarked(es_, before: Spec, after: Spec):
    """``mark_new``'s edits without the ``inferred:`` it wrote under a part that says ``formerly:`` a part taken away."""
    import re

    from . import structural as stc
    from . import yamledit as ye
    if es_ is None:
        return None
    renamed = set()
    for attr in ("stocks", "flows", "auxiliaries"):
        a, b = getattr(before, attr), getattr(after, attr)
        renamed |= {n for n in b if n not in a and any(w in a for w in (getattr(b[n], "formerly", None) or []))}
    out = []
    for e in es_:
        hunks = []
        for h in e.hunks:
            new, name = [], None
            for line in h.new:
                m = re.match(r"^\s*([a-z][a-z0-9-]*):\s*(#.*)?$", line)
                if m:
                    name = m.group(1)
                if line.strip() == f"inferred: {stc.PENDING}" and name in renamed:
                    continue
                new.append(line)
            hunks.append(ye.Hunk(h.line, list(h.old), new))
        out.append(ye.Edit(e.file, hunks))
    return out


def s_compiled(p, es_):
    from . import trial as tr
    return tr.compiled(p.model.path, tr.texts_after(es_), findings=True)


def submit(p, by: str, raw: dict, run: str | None = None, scratch: cs.Scratch | None = None, at: float | None = None) -> dict:
    """A change set recorded as made (``ergostat.model-change.made``, from its maker), then checked and scored, or
    refused with why. Returns ``{"status", "id", "title", "why", "scorecard"}``."""
    spec: Spec = p.model.spec
    now = at or time.time()
    title = str((raw or {}).get("title") or "a redesign")[:200]
    pid = im._id("redesign", by, run, now, json.dumps(raw, sort_keys=True, default=str))
    made = {"title": title, "made_by": by, "made_by_rung": im._rung(spec, by), "made": now, "created": now, "kind": KIND,
            "version": ver.version(spec), "structure": ver.structure(spec), "run": run,
            "system": (raw or {}).get("system") or "model"}
    with pr.locked(p):
        try:
            x = validate(p, spec, by, raw, scratch)
            same = waiting(p, spec, x["system"])
            if same is not None:
                raise im.ProposeError(f"a redesign of {x['system']} is waiting already: {pr.item_of(same['id'])}")
        except (im.ProposeError, ValueError) as e:
            pr.event(p, pid, "made", made, source=by, causedby=run)
            pr.event(p, pid, "refused", {"why": str(e)})
            return {"status": "not-proposed", "id": pid, "title": title, "why": str(e)}
        pr.event(p, pid, "made", made, source=by, causedby=run)
        x["edit"] = im.stamped(x["edit"], pid)
        x["method"] = (f"made by {by} ({im._rung(spec, by) or 'a block'}): {len(x['redesign']['edits'])} edits made in order on "
                       f"a scratch copy, compiled, checked, and scored on the record as it is")
        pr.event(p, pid, "checked", x)
    return {"status": "proposed", "id": pid, "title": x["title"], "why": None, "scorecard": x["scorecard"]}


def waiting(p, spec: Spec, system: str) -> dict | None:
    """The redesign of this system waiting (checked, under test or passed), if there is one."""
    for x in pr.stored(p).values():
        if x.get("kind") == KIND and x["state"] in pr.OPEN and (x.get("system") or "model") == system:
            return x
    return None


def judged(p, x: dict, at: float | None = None) -> tuple[str, str, dict]:
    """The judge's verdict on a redesign: its scorecard worked out again on the record as it is now; passed when it
    is better, failed otherwise (the scorecard kept either way)."""
    from ..spec import read
    from . import scorecard as sc
    from . import trial as tr
    spec = p.model.spec
    after, problems = tr.compiled(p.model.path, tr.texts_after(tr.edits_of(x)), findings=True)
    if any(e.level == "error" for e in problems):
        return "failed", "the model it leaves no longer compiles: " + "; ".join(str(e) for e in problems if e.level == "error")[:300], {}
    _, before = read(p.model.path)
    card = sc.score(p, spec, before, after, problems, at=at)
    return ("passed" if card["verdict"] == "better" else "failed"), card["why"], card


# ---- when one is made

def ask(p, system: str | None = None, by: str = "owner", why: str | None = None) -> dict:
    """The owner asks for a redesign of a system (or the whole model): recorded, for the redesigner to take up."""
    spec = p.model.spec
    s = system_of(spec, system)
    e = p.events.add(ASKED, item=p.model.name, source=by, data={"system": s, **({"why": why} if why else {})})
    return {"asked": s, "event": e.get("id") if isinstance(e, dict) else None}


def asked(p, now: float | None = None) -> list[str]:
    """The systems the owner asked a redesign of that no run has taken up since."""
    asks = p.events.query(n=None, type=ASKED)
    ran = p.events.query(n=None, type=RAN)
    last = {}
    for e in ran:
        s = (e.get("data") or {}).get("system") or "model"
        last[s] = max(last.get(s, 0.0), e["time"])
    out = []
    for e in asks:
        s = (e.get("data") or {}).get("system") or "model"
        if e["time"] > last.get(s, 0.0) and s not in out:
            out.append(s)
    return out


def ran(p, system: str, data: dict) -> None:
    p.events.add(RAN, item=p.model.name, source=data.get("by") or "redesigner", data={"system": system, **data})


RUNNING_FOR = 15 * 60.0      # a run started and not ended this long ago is taken as gone (the block's timeout)
HOLD_FOR = 5 * 60.0          # the judge holds its own writes for a run this long at most: refinement is never frozen


def running(p, now: float | None = None, within: float = RUNNING_FOR) -> bool:
    """A redesigner run is under way (started ``within`` seconds ago and not ended)."""
    now = now or time.time()
    last: dict = {}
    for e in p.events.query(n=None, type=RAN, since=now - within):
        last[(e.get("data") or {}).get("system") or "model"] = (e.get("data") or {}).get("result")
    return any(r == "started" for r in last.values())


def stalling(p) -> str | None:
    """Refinement's last changes, judged, all turned away: why, or None."""
    xs = [x for x in pr.stored(p).values() if x.get("made_by") in REFINERS and x.get("kind") != KIND
          and x["state"] in ("accepted", "passed", "failed", "refused", "inconclusive", "dismissed", "verified", "regressed")]
    xs.sort(key=lambda x: x.get("decided") or x.get("made") or x.get("created") or 0)
    last = xs[-STALL:]
    if len(last) < STALL or any(x["state"] in ("accepted", "passed", "verified") for x in last):
        return None
    return f"refinement stalling: its last {len(last)} changes were all turned away ({', '.join(sorted({x['state'] for x in last}))})"


def due(p, spec: Spec | None = None) -> list[str]:
    """Why the model is clearly wrong now, each reason in words (none: it is not)."""
    from ..spec import read
    from .scorecard import findings
    spec = spec or p.model.spec
    why = []
    _, problems = read(p.model.path)
    fs = findings(problems)
    if len(fs) >= MANY_FINDINGS:
        why.append(f"{len(fs)} findings check reports ({', '.join(sorted({f.split('@')[0] for f in fs})[:4])})")
    try:
        from .. import coherence as co
        got = co.of_project(p, spec)
        low = [f"{k} {x['agree']}/{x['compared']}" for k, x in got["kinds"].items()
               if not k.startswith("ergostat.") and x["compared"] and x["agree"] / x["compared"] < LOW_COHERENCE]
        if low:
            why.append("coherence low on the record: " + ", ".join(low))
    except Exception:
        pass
    try:
        from .measures import fit_why
        v, w = fit_why(p)
        if v is None and w:
            why.append(f"the fit cannot be worked out: {w}")
    except Exception:
        pass
    st = stalling(p)
    if st:
        why.append(st)
    if not p.events.query(n=1, type=RAN) and not any(x.get("kind") == KIND for x in pr.stored(p).values()):
        why.append("the model's first run with use: modelling")
    return why


def which_system(p, spec: Spec) -> str:
    """The system with the most findings and craft notes in it (the whole model when it has no systems)."""
    if not spec.systems:
        return "model"
    from ..spec import read
    _, problems = read(p.model.path)
    count: dict[str, int] = {}
    from ..correspond import system_of as sys_of
    for x in problems:
        if x.level == "error" or not x.about or getattr(getattr(x, "where", None), "template", None):
            continue                                # a part a template made is the template's: not redesigned here
        try:
            s = sys_of(spec, x.about)
        except Exception:
            s = None
        if s:
            top = spec.chain(s)[-1] if spec.chain(s) else s
            count[top] = count.get(top, 0) + (3 if x.level != "note" else 1)
    return max(count, key=count.get) if count else "model"


def plan(p, when: str = "auto") -> dict:
    """What a run of the redesigner should do now: ``{"system", "why"}`` or ``{"system": None, "why"}`` (nothing).
    The owner's asks come first; ``auto`` also looks at whether the model is clearly wrong; ``ask`` only takes asks."""
    spec = p.model.spec
    for s in asked(p):
        w = waiting(p, spec, s)
        if w is not None:
            ran(p, s, {"result": "waiting", "why": f"asked, but a redesign of {s} is waiting already ({w['id']})"})
            continue
        return {"system": s, "why": ["the owner asked"], "asked": True}
    if when != "auto":
        return {"system": None, "why": [f"when: {when}, and nothing asked"]}
    reasons = due(p, spec)
    if not reasons:
        return {"system": None, "why": ["the model is not clearly wrong"]}
    s = which_system(p, spec)
    if waiting(p, spec, s) is not None:
        return {"system": None, "why": [f"a redesign of {s} is waiting already"]}
    v = ver.version(spec)
    for e in p.events.query(n=None, type=RAN):
        d = e.get("data") or {}
        if (d.get("system") or "model") == s and d.get("version") == v:
            return {"system": None, "why": [f"a redesign of {s} was made for this version of the model already ({d.get('result')})"]}
    return {"system": s, "why": reasons}
