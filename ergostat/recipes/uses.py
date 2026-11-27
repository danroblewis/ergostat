"""Each use of a recipe, and how the work it started turned out (SPEC §12j).

A block with ``context:`` renders its recipe at every run; the run records the use as an ``ergostat.context`` item,
``ergostat.context/<block>-<run>``: ``ergostat.context.used`` (the recipe, its version and definition, the hash of
the text, the item, the block, the run). Its **outcome** is the verdict on the work, found in the record, never in
what the work said of itself:

- the run's claims (and its session's): verified counts for it, contradicted against it;
- the run failed (``agent.failed``): against;
- each item it worked on (the one it was given, and those its run's events are about): in a state the recipe's
  ``outcome:`` names (``success: [kept]``, ``failure: [dropped]``); a change to the model accepted or verified (for),
  refused, failed or regressed (against); reopened since (``*.reopened``, against); a review's verdict on it
  (``review.passed`` or ``review.failed``, or an event whose data says ``verdict``).

Any evidence against: ``failed``; else any for: ``succeeded``; else it stays ``started``. ``refresh`` records a change
of outcome (``ergostat.context.succeeded`` or ``.failed``, with the evidence), and folds it onto the session item the
use started, when there is one (``context.outcome``: ``outcome``, ``recipe``). The measures
``ergostat.context.RECIPE.outcome`` (the share succeeded of those known), ``.cost``, ``.uses``, ``.succeeded`` and
``.failed`` compare recipes over the last week."""

from __future__ import annotations

import time

from ..spec.ir import CONTEXT, CONTEXT_MEASURE, MODEL_CHANGE, ItemKind
from .ir import CONTEXT_STATES

WEEK = 7 * 86400.0
PASS = {"pass", "passed", "ok", "approved", "accepted", "correct", "succeeded", "verified", "good"}
FAIL = {"fail", "failed", "rejected", "changes", "changes-requested", "wrong", "contradicts", "refused", "bad"}


def context_kind() -> ItemKind:
    on = {f"{CONTEXT}.{s}": s for s in ("succeeded", "failed")}
    on[f"{CONTEXT}.used"] = "started"
    return ItemKind(CONTEXT, f"{CONTEXT}/*", list(CONTEXT_STATES), on,
                    ["recipe", "item", "block", "session", "chars", "cost_usd"], {}, None,
                    "each use of a context recipe: the context a block's run started from (its recipe, version and "
                    "the hash of the text), and how the work turned out (built in, SPEC §12j)",
                    fold={"evidence": "replace"})


def use_id(block: str, run: str | None) -> str:
    return f"{CONTEXT}/{block}-{(run or f'{time.time_ns():x}')[:8]}"


def used(p, rendered, block: str, run: str | None, file: str | None = None) -> dict:
    """The use, recorded as the run begins: caused by the run."""
    data = {**rendered.record(), "recipe": rendered.tag, "name": rendered.recipe, "block": block, "run": run,
            **({"file": file} if file else {})}
    return p.events.add(f"{CONTEXT}.used", item=use_id(block, run), source="ergostat", causedby=run, data=data)


def _session_of(p, run: str | None) -> dict | None:
    """The session item a run started, when its helper said which run it was (``session.started`` with ``run``, or
    with the context's run)."""
    if not run:
        return None
    for e in p.events.query(n=200, type="session.started"):
        d = e.get("data") or {}
        if d.get("run") == run or (d.get("context") or {}).get("run") == run:
            return e
    return None


def _cost(p, session: str | None, run: str | None) -> float | None:
    if session:
        for e in p.events.query(n=5, item=session, type="session.ran,session.failed"):
            c = (e.get("data") or {}).get("cost_usd")
            if c is not None:
                return float(c)
    if run:
        for e in p.events.caused_by(run):
            if e["type"] in ("agent.ran", "agent.failed") and (e.get("data") or {}).get("cost_usd") is not None:
                return float(e["data"]["cost_usd"])
    return None


def evidence(p, spec, use: dict) -> list[dict]:
    """What the record says of the work a use started: each piece ``{"for": bool, "says": ...}``."""
    from ..claims import record
    from ..spec import items as its
    run, began = use.get("run"), use.get("time") or 0.0
    recipe = spec.contexts.get(use.get("name") or "")
    outcome = recipe.outcome if recipe else {}
    out: list[dict] = []
    claims = record.of_run(p, run) if run else []
    if use.get("session"):
        seen = {c["id"] for c in claims}
        claims += [c for c in record.stored(p, since=began - 60).values() if c.get("session") == use["session"]
                   and c["id"] not in seen]
    for c in claims:
        if c["state"] == "verified":
            out.append({"for": True, "says": f"claim verified: {c.get('says')}", "claim": c["id"]})
        elif c["state"] == "contradicted":
            out.append({"for": False, "says": f"claim contradicted: {c.get('says')} ({c.get('why')})", "claim": c["id"]})
    work = [use["item"]] if use.get("item") else []
    for e in p.events.caused_by(run) if run else []:
        if e["type"] == "agent.failed":
            out.append({"for": False, "says": f"the run failed: {(e.get('data') or {}).get('note') or 'exited badly'}"})
        it = e.get("item") or ""
        if "/" in it and not it.startswith((CONTEXT + "/", "ergostat.claim/", "session/")) and it not in work:
            if its.kind_of(spec, it) is not None:
                work.append(it)
    for wid in work:
        it = its.one(p.events, spec, wid)
        if it is None:
            continue
        if it.state and it.state in outcome.get("success", []):
            out.append({"for": True, "says": f"{wid} is {it.state}", "item": wid})
        elif it.state and it.state in outcome.get("failure", []):
            out.append({"for": False, "says": f"{wid} is {it.state}", "item": wid})
        if it.kind == MODEL_CHANGE and it.state in ("accepted", "verified"):
            out.append({"for": True, "says": f"{wid} was {it.state}", "item": wid})
        elif it.kind == MODEL_CHANGE and it.state in ("refused", "failed", "regressed"):
            out.append({"for": False, "says": f"{wid} was {it.state}", "item": wid})
        for e in p.events.query(n=None, item=wid, since=began):
            if e["type"].startswith("claude."):
                continue
            d = e.get("data") or {}
            v = str(d.get("verdict") or "").lower()
            if e["type"].endswith(".reopened"):
                out.append({"for": False, "says": f"{wid} reopened" + (f": {d['reason']}" if d.get("reason") else ""),
                            "item": wid})
            elif e["type"] in ("review.passed", "review.failed") or (v and e["type"] != f"{CONTEXT}.used"
                                                                     and not e["type"].startswith("ergostat.claim")):
                ok = e["type"] == "review.passed" or v in PASS
                bad = e["type"] == "review.failed" or v in FAIL
                if ok or bad:
                    out.append({"for": bool(ok and not bad), "says": f"{e['type']} on {wid} by {e.get('source')}"
                                + (f": {d.get('why') or d.get('reason')}" if d.get("why") or d.get("reason") else ""),
                                "item": wid})
    return out


def verdict(ev: list[dict]) -> str:
    if any(not x["for"] for x in ev):
        return "failed"
    return "succeeded" if ev else "started"


def stored(p, spec, since: float | None = None) -> list[dict]:
    """Every use since then (the last week by default), folded: its fields, ``state``, ``time`` and ``id``."""
    from ..spec import items as its
    since = time.time() - WEEK if since is None else since
    out = []
    for it in its.project(p.events, spec, CONTEXT, transcript=False):
        if it.first >= since:
            out.append({**it.fields, "id": it.id, "state": it.state, "time": it.first, "last": it.last})
    return sorted(out, key=lambda u: u["time"])


def refresh(p, spec, since: float | None = None) -> int:
    """Each use's outcome found again; a change recorded (and folded onto its session). Returns how many changed."""
    changed = 0
    for u in stored(p, spec, since):
        news = {}
        if not u.get("session"):
            s = _session_of(p, u.get("run"))
            if s:
                news["session"] = s["item"]
                u["session"] = s["item"]
        if u.get("cost_usd") is None:
            c = _cost(p, u.get("session"), u.get("run"))
            if c is not None:
                news["cost_usd"] = c
        ev = evidence(p, spec, u)
        st = verdict(ev)
        if st != u["state"] or len(ev) != len(u.get("evidence") or []) or news:
            t = f"{CONTEXT}.{st}" if st != "started" else f"{CONTEXT}.seen"
            p.events.add(t, item=u["id"], source="ergostat", causedby=u.get("run"),
                         data={"outcome": st, "evidence": ev, **news})
            if u.get("session") and (st != u["state"] or news.get("session")):
                p.events.add("context.outcome", item=u["session"], source="ergostat", causedby=u.get("run"),
                             data={"outcome": st, "recipe": u.get("recipe"), "context_hash": u.get("hash")})
            changed += 1
    return changed


def table(p, spec, since: float | None = None) -> dict:
    """Per recipe and version: its uses, how they turned out, the share succeeded of those known, the mean cost and
    the mean size of the context."""
    now = time.time()
    since = now - WEEK if since is None else since
    rows: dict[str, dict] = {}
    for u in stored(p, spec, since):
        tag = u.get("recipe") or "?"
        r = rows.setdefault(tag, {"recipe": tag, "name": u.get("name"), "uses": 0, "succeeded": 0, "failed": 0,
                                  "started": 0, "costs": [], "chars": []})
        r["uses"] += 1
        r[u["state"]] = r.get(u["state"], 0) + 1
        if u.get("cost_usd") is not None:
            r["costs"].append(float(u["cost_usd"]))
        if u.get("chars"):
            r["chars"].append(int(u["chars"]))
    out = []
    for r in rows.values():
        known = r["succeeded"] + r["failed"]
        out.append({**{k: v for k, v in r.items() if k not in ("costs", "chars")},
                    "outcome": r["succeeded"] / known if known else None,
                    "cost": sum(r["costs"]) / len(r["costs"]) if r["costs"] else None,
                    "chars": round(sum(r["chars"]) / len(r["chars"])) if r["chars"] else None})
    return {"since": since, "until": now, "rows": sorted(out, key=lambda r: r["recipe"]),
            "recipes": {n: {"version": x.version, "parts": [pt.label() for pt in x.parts], "description": x.description}
                        for n, x in spec.contexts.items()}}


def measure(p, spec, name: str) -> float:
    m = CONTEXT_MEASURE.match(name)
    if not m:
        raise ValueError(f"no measure {name!r}: ergostat.context.RECIPE.outcome (or cost, uses, succeeded, failed)")
    recipe, what = m.groups()
    us = [u for u in stored(p, spec) if u.get("name") == recipe]
    if what == "uses":
        return float(len(us))
    if what in ("succeeded", "failed"):
        return float(sum(1 for u in us if u["state"] == what))
    if what == "cost":
        cs = [float(u["cost_usd"]) for u in us if u.get("cost_usd") is not None]
        return sum(cs) / len(cs) if cs else 0.0
    known = [u for u in us if u["state"] in ("succeeded", "failed")]
    return sum(1 for u in known if u["state"] == "succeeded") / len(known) if known else 0.0
