"""Work for modelling (SPEC §12e): everything ``check`` finds becomes a **request** the modelling subsystem holds, an
item of ergostat's built-in kind ``ergostat.modelling-request`` (``ergostat.modelling-request/<id>``), until it is answered.

What raises one: a finding ``check`` reports (the structure tests, a kind's chain, control, signs, the extreme
conditions), a craft note (``spec/craft.py``: a part with no description, a flow between stocks
with no equation, an undescribed collector, event types in mixed forms, a queue's goal whose tolerance lets items wait,
a process nobody identified), and, once there is record enough to compare, a coherence mismatch (``coherence.py``) that
no finding already says. A stock with no unit (``no-unit``, ``CHECK_ONLY``) raises none: it is a property of the model,
which check reports and the Dynamics view marks ``unit ?``; the rule tier reads it from check (``rules.unitless``).
Each says what it is about (``about``: the part), why (``says``: check's own words), where it is written, and which
tier can answer it first (``tier``): the **rule** tier, for what a mechanical change answers safely and certainly
(``rules.py``), or the **ai** tier (``modeller.py``), for what needs judgement (a description, a missing loop, a block
that moves nothing).

| State | Reached by | When |
|---|---|---|
| open | ``.raised``, ``.reopened`` | check finds it, and no change for it is waiting |
| proposed | ``.proposed`` | a change citing it (its finding as evidence) waits for the judge or the owner |
| held | ``.held`` | no tier enabled can answer it, or its change was turned away: it waits for the owner, the ai tier, or more record |
| answered | ``.answered`` | check no longer finds it (a change written, or anything else) |
| dismissed | ``.dismissed`` | the owner denied it from the inbox, with why: not raised again until its part changes |

A held request approved from the inbox is ``.reopened`` (open again, for the ai tier, its tries given back), only
when the tiers take it up (``approvable``: check's, not a redesign's; not the owner's alone) and the model has the ai
tier; else only a dismissal is offered. Every write of a request's state is made under ``locked``, read again first.

``sync`` is the request collector: run by the modelling template's sensor on ``open-requests``, it raises what is
new, answers what has gone, and moves each to where its changes say it is. The record is the only store."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

from ..spec.ir import MODELLING_REQUEST, Spec, template_made
from . import proposals as pr
from . import version as ver

RULE = {"no-unit"}             # what the rule tier answers (else the ai tier)
OWNER = {"queue-goal-tolerance": "a goal's setpoint and tolerance are what decides: the owner's to change",
         "process-not-identified": "a loop's process is the owner's to declare or take out"}   # held for the owner at once
NOT_MODELLING = {              # said by check, but no change to the model answers it: the owner's
    "no-modelling-loop", "template-stand-in", "template-library", "yaml-1.1", "where-typed", "deprecated-name",
    "used-twice", "not-exercised",
    "schedule-removed",        # a goal: with every: is also a meant pace (SPEC §9.1): only its author can say which
}
CHECK_ONLY = {"no-unit"}       # a property of the model check reports, no request: the rule tier reads check (rules.py)


def as_note(x) -> bool:
    """Counted as a craft note by the judge and the scorecard: a note, or a check-only finding (a modeller adds a stock,
    the fixer gives it its unit), so neither is among a change's new or answered findings."""
    return x.level == "note" or x.code in CHECK_ONLY


OPEN = ("open", "proposed", "held")
LIVE = pr.OPEN                 # a change waiting: checked, testing or passed
ENDED = ("refused", "failed", "rejected", "dismissed", "inconclusive")
DISMISSAL = ("note", "dismissed_by", "dismissed", "part", "approved_by")   # cleared when it is raised again
TAKEN_UP = {"check", "craft", "coherence", "fit"}   # the sources the tiers take up (gather's): never a redesign's
TIERS = {"rule", "ai"}
DRAFTED = ("modelling", "draft")                    # the drafter's run: it takes up the events' requests (unexplained.py)


def fresh() -> dict:
    """What a dismissed request raised again starts from: a new finding, untried, no failed call nor error, not the
    owner's, no dismissal."""
    return {"tried": {}, "failed": {}, "error": None, "owner": False, **dict.fromkeys(DISMISSAL)}


class RequestError(ValueError):
    pass


def rid(source: str, code: str, about: str) -> str:
    return hashlib.sha256(f"{source}|{code}|{about}".encode()).hexdigest()[:10]


def item_of(x: str) -> str:
    return f"{MODELLING_REQUEST}/{x}"


def evidence_of(r: dict) -> str:
    """How a change cites a request: its finding (``finding:CODE@ABOUT``) or its mismatch (``coherence:CODE@ABOUT``)."""
    if r.get("source") in ("fit", "events"):          # (an event request: its group, by its id)
        return f"request:{r['id']}"
    fid = f"{r['code']}@{r['about']}" if r.get("about") else r["code"]
    return f"{'coherence' if r.get('source') == 'coherence' else 'finding'}:{fid}"


def _where(w) -> str | None:
    return f"{Path(w.file).name}:{w.line}" if w is not None else None


def gather(p, spec: Spec, coherence: bool = True, extremes: bool = True) -> list[dict]:
    """What check finds now, each as the request it raises: its findings and notes (not about a part a template made,
    nor one no change to the model answers) and, with ``coherence``, the coherence mismatches no finding already
    says."""
    from ..spec import read
    _, problems = read(p.model.path, extremes=extremes)
    out: dict[str, dict] = {}
    for x in problems:
        if x.level == "error" or x.code in NOT_MODELLING | CHECK_ONLY or template_made(x.where) or not x.code:
            continue
        source = "craft" if x.level == "note" else "check"
        k = rid(source, x.code, x.about)
        out.setdefault(k, {"id": k, "source": source, "code": x.code, "about": x.about or "model", "says": x.message,
                           "where": _where(x.where), "level": x.level, "tier": "rule" if x.code in RULE else "ai"})
    try:                                            # a fit that cannot be worked out is work too: say why
        from .measures import fit_why
        v, why = fit_why(p)
    except Exception as e:
        v, why = None, f"{type(e).__name__}: {e}"
    from .measures import NOTHING_READ
    if v is None and why and why != NOTHING_READ:       # nothing read yet: nothing to do yet, no request
        k = rid("fit", "fit-unknown", "model")
        out[k] = {"id": k, "source": "fit", "code": "fit-unknown", "about": "model", "level": "finding", "tier": "ai",
                  "says": f"the model's fit (ergostat.model.fit) cannot be worked out: {why}. Until it can, the goal "
                          f"model-fits says nothing and the improver never runs; what would make it measurable is work"}
    if coherence:
        try:
            from .. import coherence as co
            got = co.of_project(p, spec)
        except Exception:                          # a record that cannot be read now raises nothing
            got = {"findings": []}
        said = {f"{x.code}@{x.about}" for x in problems}
        for f in got.get("findings") or []:
            if f.get("level") != "mismatch" or any(link in said for link in f.get("links") or []):
                continue
            if str(f.get("kind") or "").startswith("ergostat."):     # ergostat's own bookkeeping (the modelling loop's)
                continue
            if f"{f['code']}@{f['about']}" in said:
                continue
            k = rid("coherence", f["code"], f["about"])
            out.setdefault(k, {"id": k, "source": "coherence", "code": f["code"], "about": f["about"], "says": f["message"],
                               "where": f"{Path(f['file']).name}:{f['line']}" if f.get("file") else None, "level": "mismatch",
                               "pair": f.get("pair"), "fix": f.get("fix") or None,
                               "tier": "rule" if f["code"] in RULE else "ai"})
    return list(out.values())


def stored(p) -> dict[str, dict]:
    """Every request in the record, folded: ``{id: {state, ...fields, moved}}``; ``moved`` is the seq of its last move
    (an event that put it in another state, or any reopening: an approval reopens a held request, and a tier that read
    it open before it was held must not write over that), which a tier compares under the lock to know nobody moved it
    since it read it. Read from the item index's table (``projections.stored``), caught up as it is read."""
    from ..spec import projections
    return projections.stored(p, "request")


def event(p, x: str, what: str, data: dict | None = None, source: str = "ergostat") -> dict:
    return p.events.add(f"{MODELLING_REQUEST}.{what}", item=item_of(x), source=source, data=data or {})


def _citing(changes: dict[str, tuple[str, dict]]) -> dict[str, list[dict]]:
    """Each piece of evidence a change gives (``finding:...``, ``coherence:...``) → the changes giving it, oldest first."""
    out: dict[str, list[dict]] = {}
    for pid, (st, f) in changes.items():
        for r in f.get("reasons") or []:
            evs = r.get("evidence") if isinstance(r, dict) else None
            for ev in (evs if isinstance(evs, list) else [evs]):
                if isinstance(ev, str):
                    out.setdefault(ev.strip(), []).append({**f, "id": pid, "state": st})
    for xs in out.values():
        xs.sort(key=lambda x: x.get("made") or x.get("created") or 0.0)
    return out


def sync(p, spec: Spec | None = None, now: float | None = None, coherence: bool = True, extremes: bool = True) -> dict:
    """Raise what check finds that no request holds, answer what it no longer finds, and move each open one to where
    its changes say it is. Returns ``{raised, answered, proposed, held, reopened, open}``: the moves, and the count of
    requests open now (the level the template's sensor reads)."""
    spec = spec or p.model.spec
    now = now or time.time()
    found = {r["id"]: r for r in gather(p, spec, coherence, extremes)}
    with locked(p):                                       # what it read is what it moves: no answer lands between
        return _moved(p, spec, now, found)


def locked(p):
    """Held while a request is read, decided on and written: the owner's answer, the collector's moves, a tier's
    word. Never taken inside ``proposals.locked``, nor that inside it."""
    return pr.locked(p, "requests")


def _moved(p, spec: Spec, now: float, found: dict[str, dict], scope=None) -> dict:
    """``found`` raised, moved and answered against the requests ``scope`` holds (by default every one but the events'
    requests, which ``unexplained.sync`` collects apart)."""
    scope = scope or (lambda x: x.get("source") != "events")
    have = stored(p)
    changes = pr.changes(p)
    cites = _citing(changes)
    v = ver.version(spec)
    moved = {"raised": 0, "answered": 0, "proposed": 0, "held": 0, "reopened": 0}
    for k, r in found.items():
        x = have.get(k)
        if x is not None and x["state"] == "dismissed" and x.get("part") == ver.part(spec, r["about"]):
            continue                                      # the owner dismissed it, and its part is as it was
        if x is None or x["state"] in ("answered", "dismissed"):
            new = fresh() if x and x["state"] == "dismissed" else {}
            event(p, k, "raised" if x is None else "reopened",   # a dismissal's part changed: a new finding, untried
                  {**{a: b for a, b in r.items() if a != "id"}, **({"raised": now} if x is None else {}), "since": now,
                   "version": v, "change": None, "why": None, **new})
            moved["raised" if x is None else "reopened"] += 1
            x = {**(x or {}), **r, **new, "state": "open", "since": now, "version": v}
            have[k] = x
            if r["code"] in OWNER:                        # control: no tier changes it; it waits for the owner
                event(p, k, "held", {"why": OWNER[r["code"]], "owner": True, "tier": "owner", "version": v})
                x.update(state="held", owner=True)
                moved["held"] += 1
                continue
        elif x.get("says") != r["says"]:                  # check says it otherwise now (its counts, its fix): kept current
            event(p, k, x["state"], {"says": r["says"], "where": r.get("where"), "fix": r.get("fix")})
        since = float(x.get("since") or x.get("raised") or 0.0)
        mine = [c for c in cites.get(evidence_of(r), []) if (c.get("made") or c.get("created") or 0.0) >= since - 1]
        live = [c for c in mine if c["state"] in LIVE]
        ended = [c for c in mine if c["state"] in ENDED]
        written = [c for c in mine if c["state"] in ("accepted", "verified", "regressed")]
        if live:
            c = live[-1]
            if x["state"] != "proposed" or x.get("change") != c["id"]:
                event(p, k, "proposed", {"change": c["id"], "by": c.get("made_by") or "ergostat", "kind": c.get("kind"),
                                         "why": None})
                moved["proposed"] += 1
            continue
        if x["state"] == "held":
            if x.get("version") != v and not x.get("owner"):     # the model has changed since: worth another look
                event(p, k, "reopened", {"version": v, "why": None, "change": None, "since": now})
                moved["reopened"] += 1
            continue
        last = max([*ended, *written], key=lambda c: c.get("decided") or c.get("made") or 0.0, default=None)
        if last is not None and (x["state"] == "proposed" or x.get("change") != last["id"]):
            how = "written, and check still finds it" if last in written else last["state"]
            why = (last.get("why") or (last.get("verdict") or {}).get("why") or last.get("dismissed_because") or "")
            tier = "ai" if (last.get("made_by") or "") in ("fixer", "ergostat") else x.get("tier")
            event(p, k, "held", {"change": last["id"], "why": f"its change {pr.item_of(last['id'])} was {how}"
                                 + (f": {why}" if why else ""), "version": v, "tier": tier,
                                 "owner": last["state"] == "dismissed"})
            moved["held"] += 1
        elif x["state"] == "proposed":                    # its change was let go (superseded): open again
            event(p, k, "reopened", {"change": None, "version": v, "why": None, "since": now})
            moved["reopened"] += 1
    for k, x in have.items():
        if not scope(x):
            continue
        if x.get("source") == "redesign":                 # a redesign's trigger: answered when its change is decided
            c = (changes.get(x.get("change") or "") or (None, {}))[0]
            if x["state"] == "proposed" and c is not None and c not in LIVE:
                event(p, k, "answered", {"answered": now, "why": f"its redesign was {c}"})
                moved["answered"] += 1
            continue
        if x.get("source") == "architecture":             # an architecture review's: answered only by the next review
            continue
        if x["state"] in OPEN and k not in found:
            event(p, k, "answered", {"answered": now, "why": "check no longer finds it" if x.get("code") not in CHECK_ONLY
                                     else "a check finding now, not a request"})
            moved["answered"] += 1
    return {**moved, "open": sum(1 for k in found if (have.get(k) or {}).get("state") not in ("answered", "dismissed"))}


def approvable(spec: Spec, r: dict) -> bool:
    """Whether approving a held request hands it to a tier that takes it, an allowlist: a finding of check's, a craft
    note, a coherence mismatch or the fit (``TAKEN_UP``; never a redesign's, which the redesigner holds), its tier the
    rule or the ai tier (never ``owner``), its code not one only the owner changes (``OWNER``), and the model running
    the ai tier (a block whose run is ``... modelling ai``, the modelling template's ``modeller``)."""
    def ai(b, run=("modelling", "ai")) -> bool:
        w = str(b.params.get("run") or "").split()
        return any(tuple(w[i:i + 2]) == run for i in range(len(w)))
    if r.get("source") == "events":                 # an event request: the drafter's, when the model runs one
        return any(ai(b, DRAFTED) for b in spec.blocks.values())
    return (r.get("source") in TAKEN_UP and r.get("tier") in TIERS and r.get("code") not in OWNER
            and any(ai(b) for b in spec.blocks.values()))


def answer(p, spec: Spec, x: str, yes: bool, note: str | None = None, by: str = "owner") -> str:
    """The owner's answer to a held request (the inbox): approved, it is open again for the ai tier, with its tries
    and its failed calls given back (the tier skips a request whose tries are used, or held for the owner); denied, it is dismissed with
    ``note``, until the part it is about changes. Approval is refused when no tier would take it up: it is then the
    owner's own change (citing it) that answers it, or a dismissal. Read and written under ``locked``."""
    with locked(p):
        return _answer(p, spec, x, yes, note, by)


def _answer(p, spec: Spec, x: str, yes: bool, note: str | None, by: str) -> str:
    r = stored(p).get(x)
    if r is None or r["state"] != "held":
        raise RequestError(f"request {x} is not held (it is {r and r['state']})")
    if yes:
        if not approvable(spec, r):
            raise RequestError(f"no tier of the modelling loop takes {r.get('code')} up: write the change (citing "
                               f"{evidence_of(r)}), or --deny --note WHY")
        event(p, x, "reopened", {"why": None, "change": None, "owner": False,
                                 "tier": "events" if r.get("source") == "events" else "ai", "since": time.time(),
                                 "tried": {**(r.get("tried") or {}), "ai": 0}, "version": ver.version(spec),
                                 "failed": {**(r.get("failed") or {}), "ai": 0}, "error": None,
                                 "approved_by": by}, source=by)
        return "approved: open again, for the " + ("drafter" if r.get("source") == "events" else "ai tier")
    if not (note or "").strip():
        raise RequestError("a dismissal says why: --note WHY")
    event(p, x, "dismissed", {"note": note, "dismissed_by": by, "dismissed": time.time(),
                              "part": ver.part(spec, r.get("about") or "model")}, source=by)
    return f"dismissed: not raised again until {r.get('about') or 'the model'} changes"


def waiting(p, states=("open",)) -> list[dict]:
    """The requests in these states that no change waiting cites yet (the collector may not have seen it): what a tier
    may take up now."""
    cites = _citing(pr.changes(p))
    return [r for r in current(p, states)
            if not any(c["state"] in LIVE for c in cites.get(evidence_of(r), []))]


def for_ai(p, tries: int) -> list[dict]:
    """What the ai tier takes up: open or held, its, not the owner's, and not yet tried ``tries`` times."""
    return [r for r in waiting(p, ("open", "held")) if r.get("tier") == "ai" and not r.get("owner")
            and int((r.get("tried") or {}).get("ai") or 0) < tries]


def current(p, states=OPEN) -> list[dict]:
    """The requests in these states, oldest first."""
    return sorted((x for x in stored(p).values() if x["state"] in states), key=lambda x: x.get("raised") or 0.0)


def mark(p, x: dict, what: str, why: str | None = None, **more) -> bool:
    """A tier's word on a request as it read it (``x``): held (it has nothing it can make), with why; or its tries
    and cost, in the state it was in. Written only if, read again under ``locked``, the request has not moved since the
    tier read it (the same ``moved`` seq, not only the same state): the owner's answer, or the collector's move, made
    while the tier was working, stands, even when the request has come back to the state the tier read."""
    return move(p, x["id"], what, {**({"why": why} if why is not None else {}), **more}, (x["state"],),
                x.get("moved", -1))


def move(p, x: str, what: str, data: dict, states, moved: int | None = None) -> bool:
    """``what`` written on request ``x`` only if, read again under ``locked``, it is in one of ``states`` and, given
    ``moved`` (the seq of its last move as it was read), it has not moved since."""
    with locked(p):
        now = stored(p).get(x)
        if now is None or now["state"] not in states or (moved is not None and now.get("moved") != moved):
            return False
        event(p, x, what, data)
        return True


def counts(p) -> dict[str, int]:
    out = {s: 0 for s in ("open", "proposed", "held", "answered", "dismissed")}
    for x in stored(p).values():
        out[x["state"]] = out.get(x["state"], 0) + 1
    return out
