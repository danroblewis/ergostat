"""Interventions, a stock under control (SPEC §12p): each time a person was needed (an approval held, a request, an
advised command, a raised alarm) is evidence of a missing loop or a gap in the model, read from the record with its
class and cause. The ``interventions`` template's controller (``requests``) turns each recurring class into an
``ergostat.model-request`` naming its candidate remedies; ``watch`` tells a remedy from suppression (a guard removed
or loosened with nothing automated in its place), whose class keeps counting at its rate before. The trend is held
off only on a rise the record shows beyond its noise (the slope's lower bound above 0), and a class being worked on
counts at most at its rate before the work began, for a while, so the rise its fix needs does not count against it.
(Notifications are not interventions of their own: they carry these, and counting them twice would reward grouping.)"""

from __future__ import annotations

import hashlib
import json
import math
import time

from ..spec.ir import MODEL_REQUEST

DAY = 86400.0
CHATTER, CHATTER_SPAN = 3, 60.0          # ISA-18.2's chattering alarm: three or more times in a minute
OPEN = ("open", "investing", "verifying")
STRICT = {"auto": 0, "approve": 1, "deny": 2}   # a gate's strictness: only a step down, or its removal, is judged
_CACHE: dict = {}


def _settings(spec) -> dict:
    n = getattr(spec, "notify", None)
    return {"window": getattr(n, "trend_window", None) or 21 * DAY, "recurs": getattr(n, "recurs", None) or 3,
            "verify": getattr(n, "verify", None) or DAY, "standing": getattr(n, "standing", None) or DAY,
            "invest": getattr(n, "invest_for", None) or 14 * DAY}


def read(p, spec, since: float, until: float) -> list[dict]:
    """Every intervention asked since then: its class, cause, when asked and answered, the answer and by whom."""
    from . import stats
    out = stats.asked(p, spec, since, until)
    for b in spec.blocks.values():                          # an alarm raised, until it cleared
        if b.type != "alarm":
            continue
        up, cause = None, ", ".join(str(r) for r in b.reads())
        for t, v in p.measurements.range(f"block/{b.name}", since, until):
            if v and up is None:
                up = t
            elif not v and up is not None:
                out.append({"class": f"alarm:{b.name}", "cause": cause, "time": up, "answered": t, "verdict": "cleared"})
                up = None
        if up is not None:
            out.append({"class": f"alarm:{b.name}", "cause": cause, "time": up, "answered": None, "verdict": None})
    for f in p.events.query(n=None, type="ergostat.daemon.failed", since=since, until=until):   # a daemon given up (§9.7)
        back = p.events.query(n=None, type="ergostat.daemon.started", item=f["item"], after_seq=f["seq"])
        out.append({"class": f"alarm:daemon:{f['item']}", "cause": ", ".join(f["data"].get("users") or []),
                    "time": f["time"], "answered": back[0]["time"] if back else None, "verdict": "revived" if back else None})
    return sorted(out, key=lambda x: x["time"])


def request_id(cls: str) -> str:
    return f"{MODEL_REQUEST}/{hashlib.sha1(cls.encode()).hexdigest()[:10]}"


def requests_now(p) -> dict[str, dict]:
    """Every modelling request, folded, by its class."""
    from ..spec import items as its
    from ..spec.ir import model_request_kind
    by: dict[str, list] = {}
    for e in p.events.query(n=None, type=f"{MODEL_REQUEST}.*"):
        by.setdefault(e["item"], []).append(e)
    out = {}
    for item, es in by.items():
        it = its.fold(item, es, model_request_kind())
        out[it.fields.get("class") or item] = {**it.fields, "id": item, "state": it.state, "moves": it.moves}
    return out


def _periods(r: dict, state: str, now: float, most: float | None = None) -> list[tuple[float, float]]:
    """When a request was in a state: (from, to) for each stay, each at most ``most`` long."""
    out, start = [], None
    for m in r["moves"]:
        if m["to"] == state and start is None:
            start = m["time"]
        elif m["to"] != state and start is not None:
            out.append((start, m["time"]))
            start = None
    out += [(start, now)] if start is not None else []
    return [(a, min(b, a + most)) if most else (a, b) for a, b in out]


def daily(p, spec, now: float, days: int, xs: list[dict] | None = None) -> list[float]:
    """The interventions on each of the last ``days`` days (oldest first). A suppressed class adds its rate before on
    every day after (it never counts as a reduction); a class being worked on (investing, at most ``invest-for``)
    counts on those days at most at its rate before the work began."""
    s, since = _settings(spec), now - days * DAY
    xs = read(p, spec, since - s["window"], now) if xs is None else xs
    counts = [0.0] * days
    per: dict[tuple[str, int], int] = {}
    for x in xs:
        if x["time"] >= since:
            d = min(days - 1, int((x["time"] - since) // DAY))
            counts[d] += 1
            per[(x["class"], d)] = per.get((x["class"], d), 0) + 1
    for cls, r in requests_now(p).items():
        for a, b in _periods(r, "suppressed", now):
            for d in range(days):
                lo, hi = since + d * DAY, since + (d + 1) * DAY
                counts[d] += float(r.get("rate") or 0.0) * max(0.0, min(b, hi) - max(a, lo)) / DAY
        for a, b in _periods(r, "investing", now, s["invest"]):
            ts = [x["time"] for x in xs if x["class"] == cls and a - s["window"] <= x["time"] < a]
            before = len(ts) / max(1.0, (a - ts[0]) / DAY) if ts else 0.0     # its rate over the window before
            for d in range(days):
                lo, hi = since + d * DAY, since + (d + 1) * DAY
                if b > lo and a < hi:
                    counts[d] -= max(0.0, per.get((cls, d), 0) - before)
    return counts


def slope(ys: list[float]) -> tuple[float, float]:
    """The least-squares slope of ys against their day, per day, and its standard error."""
    n = len(ys)
    if n < 3:
        return 0.0, math.inf
    mx, my = (n - 1) / 2, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in range(n))
    b = sum((x - mx) * (y - my) for x, y in enumerate(ys)) / sxx
    res = sum((y - my - b * (x - mx)) ** 2 for x, y in enumerate(ys))
    return b, math.sqrt(res / (n - 2) / sxx)


def measures(p, spec, now: float | None = None) -> dict:
    """The alarm-management measures (ISA-18.2, EEMUA 191): per day; the trend (per day, per week: the slope, its
    lower bound and its standard error); waiting, standing, chattering, hours blocked over the last day; and the
    repeat offenders over the window with their share."""
    from . import entries
    live = now is None
    now = time.time() if live else now
    key = (str(p.dir), id(spec), p.events.last_seq(), now // 60)          # the record's version, and the minute
    if key in _CACHE:
        return _CACHE[key]
    s = _settings(spec)
    first = p.events.first_time() or now
    days = max(1, min(int(s["window"] // DAY), int((now - first) // DAY) + 1))
    xs = read(p, spec, now - 2 * s["window"], now)
    counts = daily(p, spec, now, days, xs)
    xs = [x for x in xs if x["time"] >= now - s["window"]]
    b, se = slope(counts)
    by: dict[str, dict] = {}
    for x in xs:
        o = by.setdefault(x["class"], {"class": x["class"], "count": 0, "hours": 0.0, "causes": {}})
        o["count"] += 1
        o["hours"] += ((x["answered"] or now) - x["time"]) / 3600.0
        o["causes"][x["cause"]] = o["causes"].get(x["cause"], 0) + 1
    top = sorted(by.values(), key=lambda o: (-o["hours"], -o["count"]))
    for o in top:
        o["share"], o["cause"] = o["count"] / len(xs), max(o["causes"], key=o["causes"].get)
        del o["causes"]
    day = [x for x in xs if x["time"] >= now - DAY]
    chatter = sorted({x["class"] for x in day if sum(1 for y in day if y["class"] == x["class"]
                                                     and 0 <= y["time"] - x["time"] <= CHATTER_SPAN) >= CHATTER})
    waiting = entries.entries(p, spec, None if live else now)
    got = {"per-day": counts[-1], "slope": round(b * 7, 6), "se": round(se * 7, 6) if math.isfinite(se) else None,
           "trend": round(max(0.0, b - 2 * se) * 7, 6) if math.isfinite(se) else 0.0, "days": days,
           "waiting": len(waiting) + sum(1 for x in xs if x["class"].startswith("alarm:") and x["answered"] is None),
           "standing": sum(1 for e in waiting if e["age"] > s["standing"]),
           "chattering": len(chatter), "chattering_classes": chatter,
           "blocked-hours": sum((min(x["answered"] or now, now) - max(x["time"], now - DAY)) / 3600.0 for x in xs
                                if (x["answered"] or now) > now - DAY),
           "top-share": top[0]["share"] if top else 0.0, "top": top[:10]}
    _CACHE.clear()
    _CACHE[key] = got
    return got


def remedies(spec, cls: str, rec: dict | None) -> list[str]:
    """The candidate remedies for a class, the evidence for graduating it among them."""
    from .stats import record_said, suggest
    kind, _, name = cls.partition(":")
    if kind == "person":
        b = spec.blocks.get(name)
        ask = (b.params.get("ask") if b else "") or name
        return [f"automate the person's step with a block (an ai or program block doing: {ask}), the person reviewing "
                "until its claims hold", "add the missing loop that makes the request unnecessary (a goal on what they "
                "are asked to restore)", "change the software so the step is not needed"]
    if kind == "alarm":
        return [f"add the missing loop: a goal and a controller on what {name} watches, acting before it rises",
                "change the software so what it watches no longer drifts", "an AI or program block that answers the "
                "alarm, the person reviewing until it holds"]
    ev = f" (this week: {record_said(rec)})" if rec else ""
    first = (suggest(cls, rec) if rec else None) or f"graduate it with its evidence{ev}: " + {
        "advise": f"mode: auto on block {name}", "change": f"the judge's accept: {{{name}: auto}}",
        "steptest": "identify the loop from the record instead (more record, or a disturbance that excites it)"}.get(
        kind, f"gate: auto for class {cls}, or an AI approver")
    return [first, "add the missing loop that checks the result, so approving it is a rule", "change the software so "
            "the act no longer needs approval (reversible, or checked before it is asked)"]


# ---- the controller

def surface(spec) -> dict[str, dict]:
    """What intervenes, as the model declares it: alarms (bounds, what they watch, whether a goal holds it), each action
    class's strictest gate, advised and person blocks, channels."""
    out: dict[str, dict] = {}
    for b in spec.blocks.values():
        if b.type == "alarm":
            w = [str(r) for r in b.reads()]
            out[f"alarm:{b.name}"] = {"above": b.params.get("above"), "below": b.params.get("below"), "watches": w}
        elif b.type == "person":
            out[f"person:{b.name}"] = {"flows": sorted(t.name for t in b.targets() if t.kind == "flow")}
        elif b.mode == "advise":
            out[f"advise:{b.name}"] = {"mode": "advise"}
    for a in spec.actions.values():
        k = f"notify:{a.name[7:]}" if a.name.startswith("notify.") else a.cls or a.name
        if STRICT[a.gate] >= STRICT[out.get(k, {}).get("gate", "auto")]:
            out[k] = {"gate": a.gate}
    return out


def _judge(spec, k: str, was: dict, now_: dict | None, rec: dict) -> str | None:
    """A guard removed or loosened: suppressed, or graduated (with its evidence, or something now doing its work);
    None for a guard kept or tightened."""
    from .stats import PROMOTE
    kind, _, name = k.partition(":")
    earned = rec.get("approved", 0) >= PROMOTE and not rec.get("denied")
    if kind == "alarm":
        if now_ is not None and not ((was["above"] is not None and (now_["above"] is None or now_["above"] > was["above"]))
                                     or (was["below"] is not None and (now_["below"] is None or now_["below"] < was["below"]))):
            return None                                       # kept, or tightened
        held = any(f"{g.of.kind}.{g.of.name}" in was["watches"] for g in spec.goals.values())
        return "graduated" if held else "suppressed"          # a goal holds what it watched: a loop does its work
    if kind in ("person", "advise"):
        if now_ is not None:
            return None                                       # still there (an edit is not a removal)
        b = spec.blocks.get(name)
        if kind == "advise":
            return "graduated" if b is not None and b.machine and earned else "suppressed"
        moved = any(x.machine and x.type != "person" and {t.name for t in x.targets() if t.kind == "flow"} & set(was["flows"])
                    for x in spec.blocks.values())
        return "graduated" if moved else "suppressed"
    if kind == "notify":                                      # a channel silenced: shown, though it lowers nothing
        g = (now_ or {}).get("gate")
        return "suppressed" if g is None or STRICT[g] > STRICT[was["gate"]] else None
    g = (now_ or {}).get("gate")
    if was["gate"] != "approve" or (g is not None and STRICT[g] >= STRICT["approve"]):
        return None                                           # only an approval loosened, or gone, is judged
    return "graduated" if g == "auto" and earned else "suppressed"


def watch(p, spec, now: float) -> list[str]:
    """The model's guards against the last version seen: each one gone or loosened recorded as suppressed (with its
    class's rate before) or graduated (with its evidence); a suppressed guard put back reopens its request."""
    from .stats import by_class
    f = p.dir / "interventions.json"
    try:
        old = json.loads(f.read_text())
    except (OSError, ValueError):
        old = None
    new, said = surface(spec), []
    if old is not None:
        rec, reqs, s = by_class(p, spec, now), requests_now(p), _settings(spec)
        xs = read(p, spec, now - s["window"], now)
        for k, was in old.items():
            how = _judge(spec, k, was, new.get(k), rec.get(k) or {}) if new.get(k) != was else None
            if how is None:
                if (reqs.get(k) or {}).get("state") == "suppressed" and new.get(k) == reqs[k].get("before"):
                    p.events.add(f"{MODEL_REQUEST}.opened", item=request_id(k), source="ergostat",
                                 data={"class": k, "why": "the guard is back as it was"}, at=now)
                continue
            n = sum(1 for x in xs if x["class"] == k)
            p.events.add(f"{MODEL_REQUEST}.{how}", item=request_id(k), source="ergostat",
                         data={"class": k, "before": was, "after": new.get(k), "rate": n / (s["window"] / DAY),
                               "evidence": rec.get(k) or {}}, at=now)
            said.append(f"{k}: {how}")
    f.write_text(json.dumps(new, default=str))
    return said


def _ran(p, spec, cls: str, cause: str, since: float) -> bool:
    """Whether the process a class blocked has worked since then without it: its block ran; an alarm was evaluated and
    clear; a kind of change was decided without the owner; a step test's loop holds its process."""
    kind, _, name = cls.partition(":")
    if kind == "alarm":
        return any(not v for _, v in p.measurements.range(f"block/{name}", since, time.time() + DAY))
    if kind == "change":
        from .stats import by_person
        return any(not by_person(e["source"]) for e in p.events.query(n=200, type="ergostat.model-change.accepted",
                                                                      since=since))
    if kind == "steptest":
        g = spec.goals.get(cause.removeprefix("goal "))
        return bool(g is not None and g.process)
    block = spec.blocks.get(cause.split(",")[0].removeprefix("block "))
    return block is not None and bool(p.events.query(n=1, item=block.name, type="agent.ran", since=since))


def requests(p, spec, now: float | None = None) -> dict:
    """One pass of the controller: suppression and graduation recorded; each recurring class (ranked by the time it
    blocked, then its count) without a request made one, with its remedies; a request resolved once its class has not
    intervened for three of its mean intervals (at least ``verify``) and the process it blocked has worked since; one
    resolved, reopened when its class intervenes again."""
    from .stats import by_class
    now = time.time() if now is None else now
    s, said = _settings(spec), watch(p, spec, now)
    m, reqs, rec = measures(p, spec, now), requests_now(p), by_class(p, spec, now)
    xs = read(p, spec, now - s["window"], now)
    made = resolved = 0
    for rank, o in enumerate(m["top"], 1):
        r = reqs.get(o["class"])
        again = r is not None and r["state"] == "resolved" and any(
            x["class"] == o["class"] and x["time"] > r["moves"][-1]["time"] for x in xs)
        if o["count"] >= s["recurs"] and (r is None or again):
            p.events.add(f"{MODEL_REQUEST}.opened", item=request_id(o["class"]), source="ergostat",
                         data={**o, "rank": rank, "remedies": remedies(spec, o["class"], rec.get(o["class"])),
                               "why": "it intervened again after it was resolved" if again else "it recurs"}, at=now)
            made += 1
    for cls, r in reqs.items():
        ts = [x["time"] for x in xs if x["class"] == cls]
        wait = max(s["verify"], 3 * (ts[-1] - ts[0]) / (len(ts) - 1) if len(ts) > 1 else s["verify"])
        quiet = now - max([*ts, r["moves"][-1]["time"]])
        if r["state"] in OPEN and quiet >= wait and _ran(p, spec, cls, r.get("cause") or "", now - wait):
            p.events.add(f"{MODEL_REQUEST}.resolved", item=r["id"], source="ergostat",
                         data={"why": f"no intervention for {wait / DAY:.2g}d (three of its mean intervals, at least "
                                      f"{s['verify'] / DAY:g}d), and its process worked meanwhile"}, at=now)
            resolved += 1
    return {"made": made, "resolved": resolved, "said": said, "measures": m}
