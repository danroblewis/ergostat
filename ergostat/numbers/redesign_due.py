"""When the redesigner runs on its own (SPEC §12e, *Redesign*, ``when: auto``): per system, never the whole of a large
model at once. The units are the model's systems as the architecture reads them (a system of more than ``MOST_PARTS``
parts is taken a subsystem at a time; one with none to split into is said to be too large, never attempted whole), and
the modelling template's own system is never one. A unit is due when any of these holds for it:

- **its replay is worse than its mean**: a stock of it replays with a scaled error over 1 on a record of at least
  ``SUSTAINED`` (the replay's skill below 0);
- **a finding that says the structure is wrong**: ``measured-not-caused`` or ``loop-not-identifiable`` on its parts,
  or a structural one (a kind's chain, the boundary, a coherence mismatch) held as a request for ``STALE`` and more;
- **refinement stalled**: its last ``STALL`` changes all turned away (refused, superseded, failed or inconclusive);
- **the first run** with ``use: modelling``, and **once a day** after that, as a scheduled review.

Bounds: at most one redesign waits for each unit; after one is judged not better, refused, or makes nothing (no change
set that compiles), the unit rests for ``COOL`` unless the model changed since; the daily cap (``redesign.spent``)
stops every run. Each automatic run's trigger is held as a modelling request (``source: redesign``) about the unit, so
the Items tab, the inbox and ``ergostat status`` say it; a unit too large to redesign is held for the owner the same
way (``too-large``)."""

from __future__ import annotations

import time

from ..spec.ir import Spec

MOST_PARTS = 40              # a unit of more parts is taken a subsystem at a time (haiku's change sets fail on more)
SUSTAINED = 30 * 60.0        # the record a replay worse than its mean must cover before it says the structure is wrong
STALE = 3600.0               # a structural finding held this long without a change for it
STALL = 4                    # refinement's last changes about a unit, all turned away
COOL = 6 * 3600.0            # the rest after a redesign judged not better, refused, or one that made nothing
DAILY = 86400.0              # the scheduled review
STRUCTURAL = {"many-cloud-inflows", "kind-enters-many-times"}
WRONG = {"measured-not-caused", "loop-not-identifiable"}
TURNED = ("refused", "superseded", "failed", "inconclusive", "dismissed")
REFINERS = ("fixer", "modeller", "improver", "improver-by-hand", "ergostat")


def units(spec: Spec) -> tuple[list[str], list[str]]:
    """The units a redesign may take whole, and those too large with nothing to split into: the model's systems (its
    own, not a once template's), each of at most ``MOST_PARTS`` parts, else its subsystems; a model with no systems
    of its own is one unit, ``model``."""
    from ..spec import architecture as ar
    chains = ar._chains(spec)                                  # part → its systems, innermost first (template's left out)

    def size(s: str | None) -> int:
        return sum(1 for ch in chains.values() if s is None or s in ch)
    own = [s for s in spec.systems if not (spec.uses.get(s) or {}).get("once")]
    out, big = [], []

    def take(s: str | None) -> None:
        if size(s) <= MOST_PARTS:
            out.append(s or "model")
            return
        subs = [t for t in spec.subsystems(s) if t in own]
        if not subs:
            big.append(s or "model")
            return
        for t in subs:
            take(t)
    if not own:
        take(None)
    else:
        for s in spec.subsystems(None):
            if s in own:
                take(s)
    return out, big


def _in(spec: Spec, unit: str, ref: str | None) -> bool:
    if not ref:
        return False
    if unit == "model":
        return True
    from ..spec import architecture as ar
    return unit in (ar._chains(spec).get(".".join(ref.split(".")[:2])) or [])


def triggers(p, spec: Spec, unit: str, now: float, fit: dict | None = None, reqs: dict | None = None,
             changes: dict | None = None, ran: list | None = None, ever: bool | None = None) -> list[str]:
    """Why this unit is due now, each reason in words (none: it is not)."""
    from . import proposals as pr
    from . import redesign as rd
    from . import requests as rq
    from . import structural as stc
    why = []
    fit = fit if fit is not None else _fit(p, spec)
    if (fit.get("span") or 0.0) >= SUSTAINED:
        worse = [r for r, s in (fit.get("stocks") or {}).items()
                 if _in(spec, unit, r) and (s or {}).get("nmse") is not None and s["nmse"] > 1.0]
        if worse:
            why.append(f"its replay is worse than its mean ({', '.join(sorted(worse)[:3])}: scaled error over 1)")
    reqs = reqs if reqs is not None else rq.stored(p)
    for r in reqs.values():
        if r["state"] not in rq.OPEN or r.get("source") == "redesign" or not _in(spec, unit, r.get("about")):
            continue
        if r["code"] in WRONG:
            why.append(f"{r['code']} on {r['about']}")
        elif (r["code"] in stc.CHAIN_CODES or r["code"] in STRUCTURAL or r.get("source") == "coherence") and \
                now - float(r.get("raised") or now) >= STALE:
            why.append(f"{r['code']} on {r['about']}, unresolved for {round((now - float(r['raised'])) / 3600, 1)} h")
    changes = changes if changes is not None else _changes(p)
    mine = sorted((x for x in changes.values() if x.get("kind") != rd.KIND and x.get("made_by") in REFINERS
                   and any(_in(spec, unit, t) for t in (x.get("parts") or x.get("touched") or []))
                   and x["state"] not in pr.OPEN and not _sent_back(x)), key=lambda x: x.get("made") or x.get("created") or 0)[-STALL:]
    if len(mine) >= STALL and all(x["state"] in TURNED for x in mine):
        why.append(f"refinement stalled: its last {STALL} changes were all turned away")
    ran = ran if ran is not None else _ran(p, now)
    mine_ran = [e for e in ran if ((e.get("data") or {}).get("system") or "model") == unit]
    if not (ever if ever is not None else bool(p.events.query(n=1, type=rd.RAN))):
        why.append("the first run with use: modelling")
    elif not mine_ran or now - max(e["time"] for e in mine_ran) >= DAILY:
        why.append("its daily review")
    return why


def signature(spec: Spec, unit: str) -> str:
    """The unit's own parts as written (what they are and connect, not their words): what a rest is keyed on, so a
    change elsewhere in the model does not end it, and one to its parts does."""
    from ..spec import architecture as ar
    from . import version as ver
    refs = sorted(r for r, ch in ar._chains(spec).items() if unit == "model" or unit in ch)
    tables = {"stock": spec.stocks, "flow": spec.flows, "auxiliary": spec.auxiliaries, "goal": spec.goals,
              "block": spec.blocks}
    used = set()
    for r in refs:
        x = tables[r.split(".")[0]].get(r.split(".", 1)[1])
        if getattr(x, "equation", None) is not None:
            used |= set(x.equation.parameters)
    return ver._hash([[r, ver._plain(tables[r.split(".")[0]].get(r.split(".", 1)[1]))] for r in refs]
                     + [[f"parameter.{n}", ver._plain(spec.parameters.get(n))] for n in sorted(used)])


ENDED = ("failed", "refused", "dismissed", "superseded")


def resting(p, spec: Spec, unit: str, now: float, ran: list | None = None, changes: dict | None = None) -> str | None:
    """Why this unit is not to be redesigned now, whatever is due: a redesign waiting, or the rest after one that was
    no better, dismissed, superseded, made nothing, or never ended, while the unit's own parts have not changed
    since (``signature``)."""
    from . import redesign as rd
    if rd.waiting(p, spec, unit) is not None:
        return "a redesign of it is waiting already"
    sig = signature(spec, unit)
    ran = ran if ran is not None else _ran(p, now)
    mine = [e for e in ran if ((e.get("data") or {}).get("system") or "model") == unit
            and (e.get("data") or {}).get("result") not in ("call", "waiting")]
    last = max(mine, key=lambda e: e["time"], default=None)            # its last run, ended or not
    if last is not None and now - last["time"] <= COOL + rd.RUNNING_FOR:
        d = last.get("data") or {}
        if d.get("result") == "started" and now - last["time"] > rd.RUNNING_FOR:
            return "resting: its last run never ended"
        if d.get("result") not in ("proposed", "started") and now - last["time"] <= COOL and d.get("unit_sig") == sig:
            return f"resting: its last redesign was {d.get('result')}, and its parts have not changed since"
    for x in (changes if changes is not None else _changes(p)).values():
        if x.get("kind") == rd.KIND and (x.get("system") or "model") == unit and x["state"] in ENDED and not _sent_back(x) \
                and now - float(x.get("decided") or x.get("made") or 0) <= COOL and x.get("unit_sig") == sig:
            return f"resting: its last redesign was {x['state']}"
    return None


def unfinished(p, ran: list, now: float) -> None:
    """A run that never ended (crashed, or its block timed out: only ``started`` and ``call``): its ``redesign-due``
    request closed, saying so."""
    from . import redesign as rd
    from . import requests as rq
    last: dict = {}
    for e in sorted(ran, key=lambda e: e["time"]):
        d = e.get("data") or {}
        if d.get("result") not in ("call", "waiting"):
            last[d.get("system") or "model"] = e
    for u, e in last.items():
        if (e.get("data") or {}).get("result") == "started" and now - e["time"] > rd.RUNNING_FOR:
            rq.move(p, rq.rid("redesign", "redesign-due", u), "answered",
                    {"why": "its run never ended (it crashed, or its block timed out)"}, ("open", "proposed"))


def _sent_back(x: dict) -> bool:
    """Sent back to its author by the reviewer: not turned away, and no rest (its author is asked again)."""
    return x["state"] == "superseded" and (x.get("review") or {}).get("verdict") == "revise"


def _changes(p) -> dict:
    """Every change to the model, whatever its state (superseded and dismissed ones too), with its state."""
    from . import proposals as pr
    return {k: {**f, "id": k, "state": st} for k, (st, f) in pr.changes(p).items()}


def _ran(p, now: float) -> list:
    """The redesigner's runs over the last day and the rest after them (bounded: never the whole record)."""
    from . import redesign as rd
    return [e for e in p.events.query(n=None, type=rd.RAN, since=now - max(DAILY, COOL + rd.RUNNING_FOR) - 60)
            if (e.get("data") or {}).get("result") != "call"]


def next_due(p, now: float | None = None) -> dict:
    """The unit to redesign now, ``{"system", "why", "trigger", "unit_sig"}``, or ``{"system": None, "why"}``; units
    too large are held for the owner as requests (``too-large``) on the way. Among units equally due, the one reviewed
    longest ago (or never) comes first: they take turns."""
    from . import redesign as rd
    from . import requests as rq
    spec = p.model.spec
    now = now or time.time()
    ok, big = units(spec)
    for u in big:
        hold(p, u, "too-large", f"system {u} is too large to redesign in one pass (more than {MOST_PARTS} parts, and no "
             f"subsystems to take one at a time): split it into systems", owner=True)
    ran, reqs, changes = _ran(p, now), rq.stored(p), _changes(p)      # read once for every unit
    ever = bool(ran) or bool(p.events.query(n=1, type=rd.RAN))
    unfinished(p, ran, now)
    fit = _fit(p, spec)
    skipped, due = [], []
    for u in ok:
        why = triggers(p, spec, u, now, fit=fit, reqs=reqs, changes=changes, ran=ran, ever=ever)
        if not why:
            continue
        rest = resting(p, spec, u, now, ran=ran, changes=changes)
        if rest:
            skipped.append(f"{u}: {rest}")
            continue
        seen = max((e["time"] for e in ran if ((e.get("data") or {}).get("system") or "model") == u), default=0.0)
        due.append({"system": u, "why": why, "trigger": why[0], "unit_sig": signature(spec, u), "_seen": seen})
    routine = ("the first run with use: modelling", "its daily review")
    due.sort(key=lambda d: (all(w in routine for w in d["why"]), d["_seen"]))   # what is wrong first; then turns
    if not due:
        return {"system": None, "why": skipped or ["nothing is due"]}
    return {k: v for k, v in due[0].items() if k != "_seen"}


def hold(p, unit: str, code: str, says: str, owner: bool = False, state: str = "held") -> str:
    """A redesign's trigger or result, held as a modelling request about the unit (visible on the Items tab, in the
    inbox when held, and in ``ergostat status``). Read and written under the requests' lock: one the owner dismissed
    stays dismissed while its unit is as it was (``version.part``), and is raised again, a new finding, once it is not."""
    from . import requests as rq
    from . import version as ver
    k = rq.rid("redesign", code, unit)
    about = f"system.{unit}" if unit != "model" else "model"
    data = {"source": "redesign", "code": code, "about": about, "says": says,
            "tier": "redesigner", "level": "finding", "why": says, **({"owner": True} if owner else {})}
    with rq.locked(p):
        x = rq.stored(p).get(k)
        gone = x is not None and x["state"] == "dismissed"
        if gone and x.get("part") == ver.part(p.model.spec, about):
            return k
        if x is None:
            rq.event(p, k, "raised", {**data, "raised": time.time(), "since": time.time()})
        elif gone or (state == "open" and x.get("state") != "open"):
            rq.event(p, k, "reopened", {**data, "since": time.time(), "change": None, **(rq.fresh() if gone else {})})
        if state != "open" and (x is None or x.get("state") != state or x.get("why") != says):
            rq.event(p, k, state, data)
    return k


def _fit(p, spec: Spec) -> dict:
    """The replay's per-stock scaled errors on the reference window, with how much record it covers (``span``)."""
    from . import observe as ob
    from . import scorecard as sc
    try:
        g = ob.reference(p)
        got = sc.fit(p, spec)
        return {**got, "span": float(g.until - g.since)}
    except Exception:
        return {"stocks": {}, "span": 0.0}
