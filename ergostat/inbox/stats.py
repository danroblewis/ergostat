"""What each class of what waits on a person asked of them over the last week (SPEC §12o): asked, approved (or, for a
person's request, done; for an alarm, cleared), denied, waiting, and the median time to answer; and, when a class is
always approved, one line pointing up the ladder. Answers an agent gave on the owner's behalf (``owner via mcp``) are
counted apart and are never evidence for graduating. Nothing here changes a gate: the owner promotes a class by
editing the model. Also the approval budget: how many were asked over the last day."""

from __future__ import annotations

import time

WEEK, DAY = 7 * 86400.0, 86400.0
PROMOTE = 5                         # approved this many times, none denied: suggested up the ladder
BY_AGENT = "owner via mcp"          # who an answer given through the MCP is recorded as


def by_person(source) -> bool:
    """An answer the owner gave themself: on this machine (``owner``), or through the page's login, as its email
    (SPEC §4d)."""
    return source == "owner" or "@" in str(source or "")


def asked(p, spec, since: float, until: float) -> list[dict]:
    """Each thing asked of a person since then: its class, cause, when asked and answered, the answer (approved,
    denied, superseded, or None while it waits) and who gave it. Alarms are added by ``interventions.read``."""
    from ..actions import record
    from ..control import proposals as cp
    from . import entries as en
    out = []

    def one(cls, cause, t0, t1, verdict, by=None):
        out.append({"class": cls, "cause": cause, "time": t0, "answered": t1, "verdict": verdict, "by": by})
    for a in record.stored(p, since=since, until=until).values() if spec.actions else []:
        if a.get("gate") != "approve" or record.GATE in (a.get("approved_by"), a.get("denied_by")):
            continue                                         # let through, or fenced, by the gate: no one was asked
        ans = next((m for m in a["moves"] if m["to"] in ("approved", "denied")), None)
        one(a.get("class") or a.get("action"), f"block {a.get('block')}" + (f", {a['item']}" if a.get("item") else ""),
            a["time"], ans and ans["time"], ans and ans["to"], a.get("approved_by") or a.get("denied_by"))
    for b in spec.blocks.values():
        if b.type == "person" or b.mode == "advise":
            for x in en.asks(p, b, since, until):
                one(f"{'person' if b.type == 'person' else 'advise'}:{b.name}", f"block {b.name}", x["time"],
                    x["answered"], x["verdict"], x.get("by"))
    done, by = cp.decisions(p), {e["data"].get("id"): e["source"] for e in p.events.query(n=50, type="steptest.approved")}
    for pid, x in en.offers(p, until).items():
        if x["time"] >= since:
            d = done.get(pid) or {}
            one("steptest", f"goal {x.get('goal')}", x["time"], d.get("decided"),
                {"approved": "approved", "dismissed": "denied"}.get(d.get("status")), by.get(pid))
    made: dict[str, tuple] = {}
    for e in p.events.query(n=None, type="ergostat.model-change.*", since=since, until=until):
        if e["type"].endswith(".made"):
            made[e["item"]] = (f"change:{e['data'].get('kind')}", e["time"])
        elif (e["item"] in made and (by_person(e["source"]) or e["source"] == BY_AGENT)
              and e["type"].rsplit(".", 1)[1] in ("accepted", "dismissed")):
            cls, t0 = made.pop(e["item"])
            one(cls, e["item"], t0, e["time"], "approved" if e["type"].endswith("accepted") else "denied", e["source"])
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
        r = out.setdefault(x["class"], {"asked": 0, "approved": 0, "denied": 0, "by_agent": 0, "waiting": 0,
                                        "times": []})
        r["asked"] += 1
        if x["answered"] is None:
            r["waiting"] += 1
        elif x["verdict"] != "superseded":
            r["by_agent" if x.get("by") == BY_AGENT else "denied" if x["verdict"] == "denied" else "approved"] += 1
            r["times"].append(x["answered"] - x["time"])
    for cls, r in out.items():
        t = sorted(r.pop("times"))
        r["median"] = t[len(t) // 2] if t else None
        r["suggest"] = suggest(cls, r)
    _CACHE.clear()
    _CACHE[key] = out
    return out


def suggest(cls: str, r: dict) -> str | None:
    """One line up the ladder for a class always approved by the owner; None for the rest (a person's own work, an
    alarm: their remedies are the interventions loop's)."""
    kind, _, name = cls.partition(":")
    if r["approved"] < PROMOTE or r["denied"] or kind in ("person", "steptest", "alarm"):
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
            + (f", {r['by_agent']} by an agent for the owner" if r.get("by_agent") else "")
            + (f", answered in {human(r['median'])} (median)" if r.get("median") is not None else ""))


def listing(p, spec, now: float | None = None) -> list[dict]:
    """The inbox as every surface shows it (the CLI, the MCP, the page, the API): each entry with its class's record
    and its suggestion up the ladder."""
    from . import entries
    got = entries.entries(p, spec, now)
    rec = by_class(p, spec, now) if got else {}
    for e in got:
        if e["class"] in rec:
            e.update(record=record_said(rec[e["class"]]), suggest=rec[e["class"]]["suggest"])
    return got
