"""What each class of what waits on a person asked of them over the last week (SPEC §12o): asked, approved (or, for a
person's request, done), denied, waiting, and the median time to answer; and, when a class is always approved, one line
pointing up the ladder. Nothing here changes a gate: the owner promotes a class by editing the model. Also the approval
budget: how many were asked over the last day."""

from __future__ import annotations

import time

WEEK, DAY = 7 * 86400.0, 86400.0
PROMOTE = 5                         # approved this many times, none denied: suggested up the ladder


def asked(p, spec, since: float, until: float) -> list[dict]:
    """Each thing asked of a person since then: its class, cause, when asked and answered, and the answer (approved,
    denied, or None while it waits). Alarms and notifications are added by ``interventions.read``."""
    from ..actions import record
    from ..control import proposals as cp
    from . import entries as en
    out = []

    def one(cls, cause, t0, t1, verdict):
        out.append({"class": cls, "cause": cause, "time": t0, "answered": t1, "verdict": verdict})
    for a in record.stored(p, since=since, until=until).values() if spec.actions else []:
        if a.get("gate") != "approve" or record.GATE in (a.get("approved_by"), a.get("denied_by")):
            continue                                         # let through, or fenced, by the gate: no one was asked
        ans = next((m for m in a["moves"] if m["to"] in ("approved", "denied")), None)
        one(a.get("class") or a.get("action"), f"block {a.get('block')}" + (f", {a['item']}" if a.get("item") else ""),
            a["time"], ans and ans["time"], ans and ans["to"])
    for b in spec.blocks.values():
        if b.type != "person" and b.mode != "advise":
            continue
        person, t0 = b.type == "person", None
        cls = f"{'person' if person else 'advise'}:{b.name}"
        for e in p.events.query(n=None, item=b.name, since=since, until=until,
                                type="person.asked,agent.ran" if person else "block.advised,block.approved,block.denied"):
            if e["type"] in ("person.asked", "block.advised"):
                t0 = e["time"] if t0 is None else t0              # asked again while it waits: still one
            elif t0 is not None:
                one(cls, f"block {b.name}", t0, e["time"], "denied" if e["type"] == "block.denied" else "approved")
                t0 = None
        if t0 is not None:
            one(cls, f"block {b.name}", t0, None, None)
    done = cp.decisions(p)
    for pid, x in en.offers(p, until).items():
        if x["time"] >= since:
            d = done.get(pid) or {}
            one("steptest", f"goal {x.get('goal')}", x["time"], d.get("decided"),
                {"approved": "approved", "dismissed": "denied"}.get(d.get("status")))
    made: dict[str, tuple] = {}
    for e in p.events.query(n=None, type="ergostat.model-change.*", since=since, until=until):
        if e["type"].endswith(".made"):
            made[e["item"]] = (f"change:{e['data'].get('kind')}", e["time"])
        elif e["item"] in made and e["source"] == "owner" and e["type"].rsplit(".", 1)[1] in ("accepted", "dismissed"):
            cls, t0 = made.pop(e["item"])
            one(cls, e["item"], t0, e["time"], "approved" if e["type"].endswith("accepted") else "denied")
    waiting = {e["id"].split("/", 1)[1] for e in en.entries(p, spec, until) if e["kind"] == "change"}
    for item, (cls, t0) in made.items():
        if item.split("/", 1)[1] in waiting:
            one(cls, item, t0, None, None)
    return out


_CACHE: dict = {}


def by_class(p, spec, now: float | None = None) -> dict[str, dict]:
    now = time.time() if now is None else now
    key = (str(p.dir), id(spec), p.events.last_seq(), now // 60)        # worked out again when the record changes
    if key in _CACHE:
        return _CACHE[key]
    out: dict[str, dict] = {}
    from .interventions import read
    for x in read(p, spec, now - WEEK, now):
        r = out.setdefault(x["class"], {"asked": 0, "approved": 0, "denied": 0, "waiting": 0, "times": []})
        r["asked"] += 1
        r[x["verdict"] if x["verdict"] in ("approved", "denied") else "waiting" if x["answered"] is None else "approved"] += 1
        if x["answered"] is not None:
            r["times"].append(x["answered"] - x["time"])
    for cls, r in out.items():
        t = sorted(r.pop("times"))
        r["median"] = t[len(t) // 2] if t else None
        r["suggest"] = suggest(cls, r)
    _CACHE.clear()
    _CACHE[key] = out
    return out


def suggest(cls: str, r: dict) -> str | None:
    """One line up the ladder for a class always approved; None for the rest (and for a person's own work)."""
    kind, _, name = cls.partition(":")
    if r["approved"] < PROMOTE or r["denied"] or kind in ("person", "steptest", "notify", "alarm"):
        return None
    said = f"{r['approved']} approvals of {cls} this week, all approved: consider "
    if kind == "advise":
        return said + f"mode: auto on block {name}, or an AI approver"
    if kind == "change":
        return said + f"the judge's accept: {{{name}: auto}}"
    return said + f"gate: auto for the actions of class {cls}, or an AI approver"


def asked_today(p, spec, now: float | None = None) -> list[str]:
    """The class of each thing asked of a person over the last day (ergostat's own notifications left out)."""
    now = time.time() if now is None else now
    return [x["class"] for x in asked(p, spec, now - DAY, now) if x["class"] != "notify"]


def record_said(r: dict) -> str:
    from ..durations import human
    return (f"{r['asked']} asked this week, {r['approved']} approved, {r['denied']} denied"
            + (f", answered in {human(r['median'])} (median)" if r.get("median") is not None else ""))
