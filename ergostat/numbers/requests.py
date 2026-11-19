"""Work for modelling (SPEC §12e): everything ``check`` finds becomes a **request** the modelling subsystem holds, an
item of ergostat's built-in kind ``ergostat.model-request`` (``ergostat.model-request/<id>``), until it is answered.

What raises one: a finding ``check`` reports (the structure tests, a kind's chain, control, signs, the extreme
conditions), a craft note (``spec/craft.py``: a part with no description, a stock with no unit, a flow between stocks
with no equation, an undescribed collector, event types in mixed forms, a queue's goal whose tolerance lets items wait,
a process nobody identified), and, once there is record enough to compare, a coherence mismatch (``coherence.py``) that
no finding already says. Each says what it is about (``about``: the part), why (``says``: check's own words), where it
is written, and which tier can answer it first (``tier``): the **rule** tier, for what a mechanical change answers
safely and certainly (``rules.py``), or the **ai** tier (``modeller.py``), for what needs judgement (a description,
a missing loop, a block that moves nothing).

| State | Reached by | When |
|---|---|---|
| open | ``.raised``, ``.reopened`` | check finds it, and no change for it is waiting |
| proposed | ``.proposed`` | a change citing it (its finding as evidence) waits for the judge or the owner |
| held | ``.held`` | no tier enabled can answer it, or its change was turned away: it waits for the owner, the ai tier, or more record |
| answered | ``.answered`` | check no longer finds it (a change written, or anything else) |

``sync`` is the request collector: run by the modelling template's sensor on ``open-requests``, it raises what is
new, answers what has gone, and moves each to where its changes say it is. The record is the only store."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

from ..spec.ir import MODEL_REQUEST, Spec
from . import proposals as pr
from . import version as ver

RULE = {"no-unit", "queue-goal-tolerance", "process-not-identified"}   # what the rule tier answers (else the ai tier)
NOT_MODELLING = {              # said by check, but no change to the model answers it: the owner's
    "no-modelling-loop", "template-stand-in", "template-library", "yaml-1.1", "where-typed", "deprecated-name",
    "used-twice", "not-exercised",
}
OPEN = ("open", "proposed", "held")
LIVE = pr.OPEN                 # a change waiting: checked, testing or passed
ENDED = ("refused", "failed", "dismissed", "inconclusive")


def rid(source: str, code: str, about: str) -> str:
    return hashlib.sha256(f"{source}|{code}|{about}".encode()).hexdigest()[:10]


def item_of(x: str) -> str:
    return f"{MODEL_REQUEST}/{x}"


def evidence_of(r: dict) -> str:
    """How a change cites a request: its finding (``finding:CODE@ABOUT``) or its mismatch (``coherence:CODE@ABOUT``)."""
    if r.get("source") == "fit":
        return f"request:{r['id']}"
    fid = f"{r['code']}@{r['about']}" if r.get("about") else r["code"]
    return f"{'coherence' if r.get('source') == 'coherence' else 'finding'}:{fid}"


def _where(w) -> str | None:
    return f"{Path(w.file).name}:{w.line}" if w is not None else None


def _made(w) -> bool:
    return bool(getattr(w, "template", None))


def gather(p, spec: Spec, coherence: bool = True, extremes: bool = True) -> list[dict]:
    """What check finds now, each as the request it raises: its findings and notes (not about a part a template made,
    nor one no change to the model answers) and, with ``coherence``, the coherence mismatches no finding already
    says."""
    from ..spec import read
    _, problems = read(p.model.path, extremes=extremes)
    out: dict[str, dict] = {}
    for x in problems:
        if x.level == "error" or x.code in NOT_MODELLING or _made(x.where) or not x.code:
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
    if v is None and why:
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
    """Every request in the record, folded: ``{id: {state, ...fields}}``."""
    from ..spec import items as its
    from ..spec.ir import model_request_kind
    by: dict[str, list[dict]] = {}
    for e in p.events.query(n=None, type=f"{MODEL_REQUEST}.*"):
        if "/" in str(e.get("item") or ""):
            by.setdefault(e["item"], []).append(e)
    kind = model_request_kind()
    out = {}
    for item, evs in by.items():
        it = its.fold(item, evs, kind)
        out[item.split("/", 1)[1]] = {**it.fields, "id": item.split("/", 1)[1], "state": it.state}
    return out


def event(p, x: str, what: str, data: dict | None = None, source: str = "ergostat") -> dict:
    return p.events.add(f"{MODEL_REQUEST}.{what}", item=item_of(x), source=source, data=data or {})


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
    have = stored(p)
    changes = pr.changes(p)
    cites = _citing(changes)
    v = ver.version(spec)
    moved = {"raised": 0, "answered": 0, "proposed": 0, "held": 0, "reopened": 0}
    for k, r in found.items():
        x = have.get(k)
        if x is None or x["state"] == "answered":
            event(p, k, "raised" if x is None else "reopened",
                  {**{a: b for a, b in r.items() if a != "id"}, **({"raised": now} if x is None else {}), "since": now,
                   "version": v, "change": None, "why": None})
            moved["raised" if x is None else "reopened"] += 1
            x = {**(x or {}), **r, "state": "open", "since": now, "version": v}
            have[k] = x
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
        if x["state"] in OPEN and k not in found:
            event(p, k, "answered", {"answered": now, "why": "check no longer finds it"})
            moved["answered"] += 1
    return {**moved, "open": sum(1 for k in found if (have.get(k) or {}).get("state") != "answered")}


def waiting(p, states=("open",)) -> list[dict]:
    """The requests in these states that no change waiting cites yet (the collector may not have seen it): what a tier
    may take up now."""
    cites = _citing(pr.changes(p))
    return [r for r in current(p, states)
            if not any(c["state"] in LIVE for c in cites.get(evidence_of(r), []))]


def current(p, states=OPEN) -> list[dict]:
    """The requests in these states, oldest first."""
    return sorted((x for x in stored(p).values() if x["state"] in states), key=lambda x: x.get("raised") or 0.0)


def mark(p, x: dict, what: str, why: str, **more) -> None:
    """A tier's word on a request: held (it has nothing it can make), with why."""
    event(p, x["id"], what, {"why": why, **more})


def counts(p) -> dict[str, int]:
    out = {s: 0 for s in ("open", "proposed", "held", "answered")}
    for x in stored(p).values():
        out[x["state"]] = out.get(x["state"], 0) + 1
    return out
