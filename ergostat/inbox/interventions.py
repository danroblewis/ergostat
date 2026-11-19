"""Interventions, a stock under control (SPEC §12p): each time a person was needed (an approval held, a request, an
advised command, a raised alarm, a notification sent) is evidence of a missing loop or a gap in the model, read from
the record with its class and cause. The ``interventions`` template's controller (``requests``) turns each recurring
class into an ``ergostat.model-request`` naming its candidate remedies; ``watch`` tells a remedy from suppression
(a guard removed or loosened with nothing automated in its place), whose class keeps counting at its rate before.
The trend is a weighted least-squares slope over a long window, investment days weighted down, so the rise a fix
needs on its way does not count against it."""

from __future__ import annotations

import hashlib
import json
import time

from ..spec.ir import MODEL_REQUEST

DAY = 86400.0
INVESTING_WEIGHT = 0.25
CHATTER, CHATTER_SPAN = 3, 600.0
OPEN = ("open", "investing", "verifying")


def _settings(spec) -> dict:
    n = getattr(spec, "notify", None)
    return {"window": getattr(n, "trend_window", None) or 21 * DAY, "recurs": getattr(n, "recurs", None) or 3,
            "verify": getattr(n, "verify", None) or 7 * DAY, "standing": getattr(n, "standing", None) or DAY}


def read(p, spec, since: float, until: float) -> list[dict]:
    """Every intervention asked since then: its class, cause, when asked and answered, and the answer."""
    from . import stats
    out = stats.asked(p, spec, since, until)
    for b in spec.blocks.values():                          # an alarm raised, until it cleared
        if b.type != "alarm":
            continue
        up = None
        for t, v in p.measurements.range(f"block/{b.name}", since, until):
            if v and up is None:
                up = t
            elif not v and up is not None:
                out.append({"class": f"alarm:{b.name}", "cause": ", ".join(str(r) for r in b.reads()), "time": up,
                            "answered": t, "verdict": "cleared"})
                up = None
        if up is not None:
            out.append({"class": f"alarm:{b.name}", "cause": ", ".join(str(r) for r in b.reads()), "time": up,
                        "answered": None, "verdict": None})
    from .deliver import SENT
    for e in p.events.query(n=None, type=SENT, since=since, until=until):
        out.append({"class": f"notify:{e['data'].get('channel')}", "cause": ", ".join(e["data"].get("entries") or []),
                    "time": e["time"], "answered": e["time"], "verdict": e["data"].get("state")})
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


def _periods(r: dict, state: str, now: float) -> list[tuple[float, float]]:
    """When a request was in a state: (from, to) for each stay."""
    out, start = [], None
    for m in r["moves"]:
        if m["to"] == state and start is None:
            start = m["time"]
        elif m["to"] != state and start is not None:
            out.append((start, m["time"]))
            start = None
    return out + ([(start, now)] if start is not None else [])


def daily(p, spec, now: float, days: int) -> tuple[list[float], list[float]]:
    """The interventions on each of the last ``days`` days (oldest first), with each suppressed class's rate before
    added on every day after (it never counts as a reduction); and each day's weight (investment days down)."""
    since = now - days * DAY
    counts, weights = [0.0] * days, [1.0] * days
    for x in read(p, spec, since, now):
        counts[min(days - 1, int((x["time"] - since) // DAY))] += 1
    for r in requests_now(p).values():
        for kind, (a, b) in [("suppressed", s) for s in _periods(r, "suppressed", now)] + \
                [("investing", s) for s in _periods(r, "investing", now)]:
            for d in range(days):
                lo, hi = since + d * DAY, since + (d + 1) * DAY
                if b > lo and a < hi:
                    if kind == "investing":
                        weights[d] = INVESTING_WEIGHT
                    else:
                        counts[d] += float(r.get("rate") or 0.0) * (min(b, hi) - max(a, lo)) / DAY
    return counts, weights


def slope(ys: list[float], ws: list[float]) -> float:
    """The weighted least-squares slope of ys against their day, per day: Σw(x−x̄)(y−ȳ) / Σw(x−x̄)²."""
    sw = sum(ws)
    if len(ys) < 3 or sw <= 0:
        return 0.0
    mx = sum(w * x for x, w in enumerate(ws)) / sw
    my = sum(w * y for y, w in zip(ys, ws, strict=True)) / sw
    den = sum(w * (x - mx) ** 2 for x, w in enumerate(ws))
    return 0.0 if den == 0 else sum(w * (x - mx) * (y - my) for x, (y, w) in enumerate(zip(ys, ws, strict=True))) / den


def measures(p, spec, now: float | None = None) -> dict:
    """The alarm-management measures (ISA-18.2, EEMUA 191): per day, the trend (per day, per week), standing,
    chattering, hours blocked over the last day, and the repeat offenders over the window with their share."""
    from . import entries
    now = time.time() if now is None else now
    s = _settings(spec)
    first = p.events.first_time() or now
    days = max(1, min(int(s["window"] // DAY), int((now - first) // DAY) + 1))
    counts, weights = daily(p, spec, now, days)
    xs = read(p, spec, now - s["window"], now)
    day = [x for x in xs if x["time"] >= now - DAY]
    by: dict[str, dict] = {}
    for x in xs:
        o = by.setdefault(x["class"], {"class": x["class"], "count": 0, "hours": 0.0, "causes": {}})
        o["count"] += 1
        o["hours"] += 0.0 if x["class"].startswith("notify:") else ((x["answered"] or now) - x["time"]) / 3600.0
        o["causes"][x["cause"]] = o["causes"].get(x["cause"], 0) + 1
    top = sorted(by.values(), key=lambda o: (-o["hours"], -o["count"]))
    for o in top:
        o["share"], o["cause"] = o["count"] / len(xs), max(o["causes"], key=o["causes"].get)
        del o["causes"]
    chatter = {c for c in {x["class"] for x in day}
               if any(sum(1 for y in day if y["class"] == c and 0 <= y["time"] - t <= CHATTER_SPAN) >= CHATTER
                      for t in (x["time"] for x in day if x["class"] == c))}
    return {"per-day": counts[-1], "trend": round(slope(counts, weights) * 7, 6), "days": days,
            "standing": sum(1 for e in entries.entries(p, spec) if e["age"] > s["standing"]),
            "chattering": len(chatter), "chattering_classes": sorted(chatter),
            "blocked-hours": sum((min(x["answered"] or now, now) - max(x["time"], now - DAY)) / 3600.0 for x in xs
                                 if not x["class"].startswith("notify:") and (x["answered"] or now) > now - DAY),
            "top-share": top[0]["share"] if top else 0.0, "top": top[:10]}


def remedies(spec, cls: str, rec: dict | None) -> list[str]:
    """The candidate remedies for a class, the evidence for graduating it among them."""
    from .stats import record_said, suggest
    kind, _, name = cls.partition(":")
    ev = f" (this week: {record_said(rec)})" if rec else ""
    grad = suggest(cls, rec) if rec else None
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
    if kind == "notify":
        return ["remedy the entries it carried: each is a class of its own"]
    first = (grad or f"graduate it with its evidence{ev}: " + {"advise": f"mode: auto on block {name}",
             "change": f"the judge's accept: {{{name}: auto}}", "steptest": "identify the loop from the record "
             "instead (more record, or a disturbance that excites it)"}.get(kind, f"gate: auto for class {cls}, or an "
             "AI approver"))
    return [first, "add the missing loop that checks the result, so approving it is a rule", "change the software so "
            "the act no longer needs approval (reversible, or checked before it is asked)"]


# ---- the controller

def surface(spec) -> dict[str, dict]:
    """What intervenes, as the model declares it: alarms and their bounds, gates, advised and person blocks, channels."""
    out: dict[str, dict] = {}
    for b in spec.blocks.values():
        if b.type == "alarm":
            w = [str(r) for r in b.reads()]
            out[f"alarm:{b.name}"] = {"above": b.params.get("above"), "below": b.params.get("below"), "watches": w,
                                      "held": any(f"{g.of.kind}.{g.of.name}" in w for g in spec.goals.values())}
        elif b.type == "person":
            out[f"person:{b.name}"] = {"flows": sorted(t.name for t in b.targets() if t.kind == "flow")}
        elif b.mode == "advise":
            out[f"advise:{b.name}"] = {"mode": "advise"}
    for a in spec.actions.values():
        k = f"notify:{a.name[7:]}" if a.name.startswith("notify.") else a.cls or a.name
        if out.get(k, {}).get("gate") != "approve":
            out[k] = {"gate": a.gate}
    return out


def _judge(p, spec, k: str, was: dict, now_: dict | None, rec: dict) -> str | None:
    """suppressed, graduated, or None (tightened, or nothing that intervened went)."""
    from .stats import PROMOTE
    kind, _, name = k.partition(":")
    earned = rec.get("approved", 0) >= PROMOTE and not rec.get("denied")
    if kind == "alarm":
        held = not was.get("held") and any(f"{g.of.kind}.{g.of.name}" in was["watches"] for g in spec.goals.values())
        looser = now_ is None or (was["above"] is not None and (now_["above"] is None or now_["above"] > was["above"])) \
            or (was["below"] is not None and (now_["below"] is None or now_["below"] < was["below"]))
        return None if not looser else "graduated" if held else "suppressed"
    if kind == "person":
        moved = any(b.machine and b.type != "person" and {t.name for t in b.targets() if t.kind == "flow"} & set(was["flows"])
                    for b in spec.blocks.values())
        return "graduated" if moved else "suppressed"
    if kind == "advise":
        b = spec.blocks.get(name)
        return "graduated" if b is not None and b.machine and earned else "suppressed"
    gone = now_ is None or now_.get("gate") == "deny"
    if was.get("gate") == "deny" or (now_ or {}).get("gate") == was.get("gate"):
        return None
    return "suppressed" if gone or not earned or kind == "notify" else "graduated"


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
        for k, was in old.items():
            how = _judge(p, spec, k, was, new.get(k), rec.get(k) or {}) if new.get(k) != was else None
            if how is None:
                if (reqs.get(k) or {}).get("state") == "suppressed" and new.get(k) == reqs[k].get("before"):
                    p.events.add(f"{MODEL_REQUEST}.opened", item=request_id(k), source="ergostat",
                                 data={"class": k, "why": "the guard is back as it was"}, at=now)
                continue
            n = sum(1 for x in read(p, spec, now - s["window"], now) if x["class"] == k)
            p.events.add(f"{MODEL_REQUEST}.{how}", item=request_id(k), source="ergostat",
                         data={"class": k, "before": was, "after": new.get(k), "rate": n / (s["window"] / DAY),
                               "evidence": rec.get(k) or {}}, at=now)
            said.append(f"{k}: {how}")
    f.write_text(json.dumps(new, default=str))
    return said


def requests(p, spec, now: float | None = None) -> dict:
    """One pass of the controller: suppression and graduation recorded; each recurring class (ranked by the time it
    blocked, then its count) without a request made one, with its remedies; a request resolved once its class has not
    intervened over the verification window and the process it blocked has run since; one resolved, reopened when its
    class intervenes again."""
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
        last = max((x["time"] for x in xs if x["class"] == cls), default=None)
        block = spec.blocks.get((r.get("cause") or "").split(",")[0].removeprefix("block "))
        ran = block is None or p.events.query(n=1, item=block.name, type="agent.ran", since=now - s["verify"])
        if r["state"] in OPEN and r["moves"][-1]["time"] <= now - s["verify"] and \
                (last is None or last <= now - s["verify"]) and ran:
            p.events.add(f"{MODEL_REQUEST}.resolved", item=r["id"], source="ergostat",
                         data={"why": f"no intervention for {s['verify'] / DAY:g}d, and its process ran"}, at=now)
            resolved += 1
    return {"made": made, "resolved": resolved, "said": said, "measures": m}
