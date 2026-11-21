"""pipeline-watch: the triggers of the pipeline manager, from the record (dev/README.md, *The pipeline manager*): while
managing is open and no situation is raised or leased, the first standing trigger not raised before (its fingerprint)
is raised as `situation/...`: the queue blocked, a gap dead or parked (for a kind no program resumes: a defect, the
kill rule, or a kind not said), a waits_on / needs park not cleared in `[manager] park_wait_hours` (parks.py), a gap
stuck in its state, an old intervention, the heartbeat. `watch.py stuck` counts the stuck gaps (a sensor);
`watch.py open` reads the switch managing-open."""

from __future__ import annotations

import hashlib
import json
import sys
import time

sys.dont_write_bytecode = True
import fac  # noqa: E402
import parks  # noqa: E402
import pools  # noqa: E402

BY = "pipeline-manager"
ENDED = ("merged", "parked", "closed")
DECISIONS = ("operator-decision", "factory-tuning", "queue")    # records of a decision (or the queue's own trigger)
STUCK = {"ready": 6, "fix": 6, "leased": 3, "building": 5, "built": 2, "in-review": 2, "approved": 4, "queued": 3,
         "push-pending": 4, "queue-failed": 1}                         # hours, the defaults of [manager.stuck_hours]


def settings(cfg: dict) -> dict:
    m = cfg.get("manager") or {}
    return {"open": int(m.get("open", 1)), "parked": float(m.get("parked_within_hours", 48)),
            "park_wait": float(m.get("park_wait_hours", 24)),
            "intervention": float(m.get("intervention_hours", 12)), "heartbeat": float(m.get("heartbeat_minutes", 30)),
            "per_hour": int(m.get("interventions_per_hour", 3)),
            "stuck": {**STUCK, **(m.get("stuck_hours") or {})}}


def queue_state(cfg: dict) -> dict:
    p = fac.run_dir(cfg) / "queue.json"                 # (queue.py's own: its name is the standard library's too)
    return json.loads(p.read_text()) if p.exists() else {}


def branch(g: dict) -> str:
    try:
        return fac.branch_of(g)
    except ValueError:
        return ""


def detail(iid: str) -> dict:
    return json.loads(fac.ergostat("item", iid, "--json").stdout)


def sit(trigger: str, subject: str, why: str, *key) -> dict:
    """A trigger standing, with its fingerprint: the same situation unchanged has the same one."""
    return {"trigger": trigger, "subject": subject, "why": why,
            "print": hashlib.sha1("|".join(map(str, (trigger, subject, *key))).encode()).hexdigest()[:12]}


def visit_start(moves: list[dict], state: str) -> float | None:
    """When the gap came into its state this time: a lease taken and given back (leased and back) is the same visit."""
    t = None
    for m in reversed(moves):
        if m.get("to") not in (state, "leased"):
            break
        t = float(m["time"])
        if m.get("from") not in (state, "leased"):
            break
    return t


def hours_in(g: dict, start: float, now: float) -> float:
    """Its time in its state: state-times' closed visits (time_in) and the one it is in, else this visit alone."""
    t = (g["fields"].get("time_in") or {}).get(g["state"])
    if isinstance(t, dict):
        return float(t.get("hours") or 0) + (now - float(g.get("entered") or start)) / 3600
    return (now - start) / 3600


def explained(g: dict, gaps: dict, cfg: dict) -> bool:
    """A wait that is no trouble: waiting on main to move, its dependencies unmerged or its pool full, the queue busy or
    its push held (a push-pending gap whose outcome waits for its batch's push, queue.py tell())."""
    st, n, p = g["state"], lambda *s: sum(x["state"] in s for x in gaps.values()), pools.state(cfg)  # noqa: E731
    waits = [d for d in fac.ids(g["fields"].get("depends_on")) if gaps.get(d, {}).get("state") != "merged"]
    if g["fields"].get("waits_on_main"):                 # (main-broken: it waits for main to move, by design)
        return True
    return (st in ("ready", "fix") and bool(waits or n("building") >= p["implementor"])) or (
        st == "built" and n("in-review") >= p["reviewer"]) or (
        st == "approved" and bool(n("queued", "queue-failed") or queue_state(cfg).get("pending"))) or (
        st == "push-pending" and any(e.get("item") == g["id"] for e in (queue_state(cfg).get("pending") or {}).get("then") or []))


def stuck(cfg: dict, gaps: dict, now: float) -> list[dict]:
    s, out = settings(cfg), []
    for g in gaps.values():
        limit = s["stuck"].get(g["state"])
        if limit is None or now - float(g.get("first") or now) < float(limit) * 3600 or explained(g, gaps, cfg):
            continue
        start = visit_start(detail(g["id"]).get("moves") or [], g["state"]) or float(g.get("entered") or now)
        h = hours_in(g, start, now)
        if h >= float(limit):
            out.append({**sit("stuck", g["id"], f"{g['id']} has been {g['state']} for {h:.1f}h (its threshold {limit}h)",
                              g["state"], start), "hours": round(h, 2)})
    return sorted(out, key=lambda x: -x["hours"])


def candidates(cfg: dict, now: float) -> list[dict]:
    """Every trigger standing now, in order; the heartbeat last."""
    s = settings(cfg)
    gaps = {g["id"]: g for g in fac.items("gap")}
    opened = [i for i in fac.items("intervention", "open") if i["fields"].get("by") != BY]
    out = []
    blocked = queue_state(cfg).get("blocked")
    if blocked:
        out.append(sit("queue", blocked.get("intervention", "queue"), f"the merge queue is blocked: {blocked.get('why')}"))
    out += [sit("queue", i["id"], f"{i['id']}: {i['fields'].get('reason')}") for i in opened
            if i["fields"].get("class") == "queue" and (blocked or {}).get("intervention") != i["id"]]
    holders = {branch(g) for g in gaps.values() if g["state"] not in (*ENDED, "dead")}
    for g in gaps.values():
        at = float(g["fields"].get("parked_at") or g.get("entered") or 0)
        if g["state"] == "dead" and now - float(g.get("entered") or now) > 1800:     # (dead-letters parks it first)
            out.append(sit("dead", g["id"], f"{g['id']} is a dead letter: {str(g['fields'].get('last_error'))[:300]}",
                           g.get("entered")))
        elif parks.waiting(g, now, s["park_wait"]) and branch(g) not in holders:
            out.append(sit("waiting", g["id"], f"{g['id']} parked for {g['fields']['parked_for']} "
                           f"{json.dumps(g['fields'].get('parked_until'))[:300]} {(now - at) / 3600:.0f}h, not cleared", at))
        elif (g["state"] == "parked" and now - at < s["parked"] * 3600 and branch(g) not in holders and not g["fields"].get("deferred")
              and not g["fields"].get("cancelled") and g["fields"].get("parked_for") not in (*parks.RESUMED, "deferred", "cancelled")):
            out.append(sit("parked", g["id"], f"{g['id']} was parked ({g['fields'].get('parked_for') or 'its kind not said'}): "
                           f"{str(g['fields'].get('where_it_stopped'))[:300]}", at))
    out += stuck(cfg, gaps, now)
    for i in sorted(opened, key=lambda i: float(i["fields"].get("recorded_at") or i.get("first") or 0)):
        at = float(i["fields"].get("recorded_at") or i.get("first") or now)
        f = i["fields"]
        defect = f.get("class") not in DECISIONS and f.get("factory") is not False and not f.get("remedied_at")
        if defect and not f.get("remedy") and now - at > s["intervention"] * 3600:
            out.append(sit("intervention", i["id"], f"{i['id']} ({i['fields'].get('class')}) open {(now - at) / 3600:.0f}h:"
                           f" {i['fields'].get('reason')}", i.get("last")))
    shape = sorted((g["id"], g["state"]) for g in gaps.values() if g["state"] not in ENDED)
    return out + [sit("heartbeat", "pipeline", "the heartbeat: the pipeline as a whole", shape, blocked,
                      [i["id"] for i in opened])]


def raise_one(cfg: dict, now: float | None = None) -> dict | None:
    now = now or time.time()
    s = settings(cfg)
    known = fac.items("situation")
    if not s["open"] or any(x["state"] in ("raised", "leased") for x in known):
        return None
    seen = {x["fields"].get("print") for x in known}
    beat = max([float(x["fields"].get("raised_at") or 0) for x in known if x["fields"].get("trigger") == "heartbeat"] or [0])
    hour = sum(x["fields"].get("trigger") == "intervention" and now - float(x["fields"].get("raised_at") or 0) < 3600
               for x in known)                             # (old interventions at most per_hour: the first run's backlog)
    for c in candidates(cfg, now):
        if c["print"] in seen or (c["trigger"] == "heartbeat" and now - beat < s["heartbeat"] * 60) or (
                c["trigger"] == "intervention" and hour >= s["per_hour"]):
            continue
        sid = f"situation/{c['trigger']}-{fac.slug(c['subject'].split('/')[-1], 40)}-{c['print'][:8]}"
        fac.say("situation.raised", sid, **c, raised_at=now, **({"gap": c["subject"]} if c["subject"].startswith("gap/") else {}))
        return {"id": sid, **c}
    return None


def main(argv: list[str]) -> int:
    cfg = fac.config()
    if argv[:1] == ["open"]:
        print(settings(cfg)["open"])
    elif argv[:1] == ["stuck"]:
        print(len(stuck(cfg, {g["id"]: g for g in fac.items("gap")}, time.time())))
    else:
        print(f"watch: {(raise_one(cfg) or {}).get('id', 'nothing raised')}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
