"""pipeline-watch: when the pipeline manager runs, and what its session is given (dev/README.md, *The pipeline
manager*). Every few minutes, while managing is open and no session is raised or under way, it raises one
`situation/...` carrying every standing trigger an earlier session has not handled (by fingerprint): the queue blocked,
a gap dead or parked (for a kind no program resumes: a defect, the kill rule, or a kind not said; never a deferred or
cancelled park), a waits_on / needs park not cleared in [manager] park_wait_hours (parks.py), a gap stuck in its
state, an aging defect. It raises one:

  broken     before the schedule, when the merge pipeline has been broken past [manager] broken_minutes (the queue
             blocked, a push pending, no merge while approved gaps wait, the same test failing on two main commits,
             the load interlock holding the queue or its limits unreadable): when each began is kept in
             run/manager.json; never sooner than broken_minutes after the last session of any kind
  scheduled  every [manager] every (2h), the routine review
and none when nothing changed since the last session (no new trigger, no new broken condition, the pipeline the same).

    watch.py           the block           watch.py stuck      the stuck gaps now (a sensor)
    watch.py broken    minutes the merge pipeline has been broken past broken_minutes (a sensor; 0 when it flows)
    watch.py since     minutes since the last session (a sensor)       watch.py open    the switch managing-open"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import secrets
import sys
import time

sys.dont_write_bytecode = True
import fac  # noqa: E402
import load  # noqa: E402
import parks  # noqa: E402
import pools  # noqa: E402

BY = "pipeline-manager"
ENDED = ("merged", "parked", "closed")
DECISIONS = ("operator-decision", "factory-tuning", "queue")    # records of a decision (or the queue's own trigger)
STUCK = {"ready": 6, "fix": 6, "leased": 3, "building": 5, "built": 2, "in-review": 2, "approved": 4, "queued": 3,
         "push-pending": 4, "queue-failed": 1}      # hours, the defaults of [manager.stuck_hours]
MOST_ACTIONS = 12                                   # the ceiling of [manager] most_actions, whatever the settings say
EVERY_FLOOR, BROKEN_FLOOR = 15.0, 5.0              # minutes: the floors of [manager] every and broken_minutes


def minutes(v, default: float) -> float:
    m = re.fullmatch(r"\s*([\d.]+)\s*([mh]?)\s*", str(v if v is not None else default))
    return float(m[1]) * (60 if m[2] == "h" else 1) if m else float(default)


def settings(cfg: dict) -> dict:
    m = cfg.get("manager") or {}
    return {"open": int(m.get("open", 1)), "parked": float(m.get("parked_within_hours", 48)),
            "park_wait": max(1.0, float(m.get("park_wait_hours", 24))),
            "intervention": float(m.get("intervention_hours", 12)),
            "every": max(EVERY_FLOOR, minutes(m.get("every"), 120)),             # (each session is a paid one)
            "broken": max(BROKEN_FLOOR, minutes(m.get("broken_minutes"), 30)),
            "most": min(MOST_ACTIONS, max(1, int(m.get("most_actions", 8)))),   # (each call can start paid sessions)
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
    return {"trigger": trigger, "subject": subject, "why": why[:600],
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
    its push held (a push-pending gap whose outcome waits for its batch's push, queue.py tell(), while that push still
    waits for the coordinator)."""
    st, n, p = g["state"], lambda *s: sum(x["state"] in s for x in gaps.values()), pools.state(cfg)  # noqa: E731
    waits = [d for d in fac.ids(g["fields"].get("depends_on")) if gaps.get(d, {}).get("state") != "merged"]
    if "landed, not closed" in str(g["fields"].get("blocked_reason") or ""):   # (deps.py: closing it is the wait)
        return False
    if g["fields"].get("waits_on_main"):                 # (main-broken: it waits for main to move, by design)
        return True
    return (st in ("ready", "fix") and bool(waits or n("building") >= p["implementor"])) or (
        st == "built" and n("in-review") >= p["reviewer"]) or (
        st == "approved" and bool(n("queued", "queue-failed") or queue_state(cfg).get("pending"))) or (
        st == "push-pending" and carried(g, cfg) and push_waits(cfg))


def carried(g: dict, cfg: dict) -> bool:
    """A push-pending gap whose outcome the pending push holds back (queue.py tell()); not carried, nothing settles it."""
    return any(e.get("item") == g["id"] for e in (queue_state(cfg).get("pending") or {}).get("then") or [])


def push_waits(cfg: dict) -> bool:
    """The pending push still waits for the coordinator; ran, denied, failed or unreadable: it is no reason to wait."""
    aid = (queue_state(cfg).get("pending") or {}).get("action")
    try:
        return bool(aid) and detail(aid).get("state") in ("held", "requested", "approved")
    except (RuntimeError, ValueError, FileNotFoundError):
        return False


def stuck(cfg: dict, gaps: dict, now: float) -> list[dict]:
    s, out = settings(cfg), []
    for g in gaps.values():
        limit = 0 if g["state"] == "push-pending" and not carried(g, cfg) else s["stuck"].get(g["state"])
        if limit is None or now - float(g.get("first") or now) < float(limit) * 3600 or explained(g, gaps, cfg):
            continue
        start = visit_start(detail(g["id"]).get("moves") or [], g["state"]) or float(g.get("entered") or now)
        h = hours_in(g, start, now)
        if h >= float(limit):
            out.append({**sit("stuck", g["id"], f"{g['id']} has been {g['state']} for {h:.1f}h (its threshold {limit}h)"
                              + (f": {g['fields']['blocked_reason']}" if g["fields"].get("blocked_reason") else ""),
                              g["state"], start), "hours": round(h, 2)})
    return sorted(out, key=lambda x: -x["hours"])


def triggers(cfg: dict, gaps: dict, opened: list[dict], now: float) -> list[dict]:
    """Every trigger standing now, the most urgent first."""
    s, out = settings(cfg), []
    blocked = queue_state(cfg).get("blocked")
    if blocked:
        out.append(sit("queue", blocked.get("intervention", "queue"), f"the merge queue is blocked: {blocked.get('why')}"))
    out += [sit("queue", i["id"], f"{i['id']}: {i['fields'].get('reason')}") for i in opened
            if i["fields"].get("class") == "queue" and (blocked or {}).get("intervention") != i["id"]]
    holders = {branch(g) for g in gaps.values() if g["state"] not in (*ENDED, "dead")}
    for g in gaps.values():
        f, at = g["fields"], float(g["fields"].get("parked_at") or g.get("entered") or 0)
        if g["state"] == "dead" and now - float(g.get("entered") or now) > 1800:     # (dead-letters parks it first)
            out.append(sit("dead", g["id"], f"{g['id']} is a dead letter: {str(f.get('last_error'))[:300]}",
                           g.get("entered")))
        elif parks.waiting(g, now, s["park_wait"]) and branch(g) not in holders:
            out.append(sit("waiting", g["id"], f"{g['id']} parked for {f['parked_for']} "
                           f"{json.dumps(f.get('parked_until'))[:300]} {(now - at) / 3600:.0f}h, not cleared", at))
        elif (g["state"] == "parked" and now - at < s["parked"] * 3600 and branch(g) not in holders
              and f.get("parked_for") not in (*parks.RESUMED, "deferred", "cancelled")
              and not (f.get("deferred") or f.get("cancelled"))):           # a coordinator's decision, not a stall
            out.append(sit("parked", g["id"], f"{g['id']} was parked ({f.get('parked_for') or 'its kind not said'}): "
                           f"{str(f.get('where_it_stopped'))[:300]}", at))
    out += stuck(cfg, gaps, now)
    for i in sorted(opened, key=lambda i: float(i["fields"].get("recorded_at") or i.get("first") or 0)):
        f = i["fields"]
        at = float(f.get("recorded_at") or i.get("first") or now)
        defect = f.get("class") not in DECISIONS and f.get("factory") is not False and not f.get("remedied_at")
        if defect and not f.get("remedy") and now - at > s["intervention"] * 3600:
            out.append(sit("intervention", i["id"], f"{i['id']} ({f.get('class')}) open {(now - at) / 3600:.0f}h: "
                                                    f"{f.get('reason')}", i.get("last")))
    return out


HOLD = r"^  {name}:\s*$.*?hold: \"(<=|>=) ([\d.]+)\""
INTERLOCK = {"suites": "machine-quiet", "threads": "suite-threads-within", "memory": "suite-memory-within"}


def hold(file: str, name: str) -> float | None:
    """A goal's setpoint, from dev/model/<file>."""
    m = re.search(HOLD.format(name=re.escape(name)), (fac.HERE / "model" / file).read_text(), re.M | re.S)
    return float(m[2]) if m else None


def conditions(cfg: dict, gaps: dict, opened: list[dict], now: float, starts: dict | None = None) -> dict[str, str]:
    """The ways the merge pipeline is broken now: {name: why}. ``starts`` (when given) gets when those that say so began:
    a new push or block has its own clock, never the last one's."""
    s, q, out = settings(cfg), queue_state(cfg), {}
    starts = {} if starts is None else starts
    approved = [g for g in gaps.values() if g["state"] == "approved"]
    waited = [g for g in approved if now - float(g["fields"].get("approved_at") or now) > s["broken"] * 60]
    if q.get("blocked"):
        out["blocked"], starts["blocked"] = f"the merge queue is blocked: {q['blocked'].get('why')}", q["blocked"].get("at")
    if q.get("pending"):
        out["push"] = f"the push of {str(q['pending'].get('sha'))[:12]} is pending ({', '.join(q['pending'].get('gaps') or [])})"
        starts["push"] = q["pending"].get("at")
    last = max([float(g["fields"].get("merged_at") or 0) for g in gaps.values()] or [0])
    if waited and now - last > s["broken"] * 60:
        out["no-merge"] = f"no merge for {(now - last) / 60:.0f} minutes while {len(waited)} approved gaps wait"
        starts["no-merge"] = max(last, min(float(g["fields"]["approved_at"]) for g in waited))
    seen: dict[str, set] = {}
    for i in fac.items("intervention", "open"):             # (unremedied only: a remedied one clears it)
        if i["fields"].get("class") == "main-broken" and not (i["fields"].get("remedied_at") or i["fields"].get("remedy")):
            for t in i["fields"].get("tests") or []:
                seen.setdefault(t, set()).add(i["fields"].get("main"))
    twice = sorted(t for t, mains in seen.items() if len(mains) >= 2)
    if twice:
        out["main-twice"] = f"failing on two or more main commits: {', '.join(twice[:5])}"
    limits = {w: hold("interlock.yaml", g) for w, g in INTERLOCK.items()}
    unknown = [INTERLOCK[w] for w, lim in limits.items() if lim is None]
    probe = approved and cfg.get("load", {}).get("wait", True)      # (the tests' machine is not the factory's)
    over = [w for w, lim in limits.items() if lim is not None and load.reading(w) > lim] if probe else []
    if unknown:                                # (a goal renamed or reworded: never read as within its limit)
        out["interlock"] = f"the load interlock's goals {', '.join(unknown)} have no hold in dev/model/interlock.yaml"
    elif over:
        out["interlock"] = f"the load interlock holds the queue ({', '.join(over)} over) while {len(approved)} gaps wait"
    return out


def broken(cfg: dict, gaps: dict, opened: list[dict], now: float) -> dict[str, dict]:
    """The conditions broken past [manager] broken_minutes ({name: {why, since}}), with when each began kept in
    run/manager.json (a condition that clears starts again); `main-twice` counts at once."""
    p = fac.run_dir(cfg) / "manager.json"
    with open(p.with_name("manager.lock"), "a") as lock:  # (the sensor and the block both keep it: read to write held)
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            was = json.loads(p.read_text()).get("since", {}) if p.exists() else {}
            starts: dict = {}
            now_on = conditions(cfg, gaps, opened, now, starts)
            since = {k: float(starts.get(k) or was.get(k) or now) for k in now_on}
            tmp = p.with_name(f"manager.{os.getpid()}.new")
            tmp.write_text(json.dumps({"since": since}))
            tmp.replace(p)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
    return {k: {"why": why, "since": since[k]} for k, why in now_on.items()
            if k == "main-twice" or now - since[k] >= settings(cfg)["broken"] * 60}


def state_now(cfg: dict, now: float) -> dict:
    gaps = {g["id"]: g for g in fac.items("gap")}
    opened = [i for i in fac.items("intervention", "open") if i["fields"].get("by") != BY]
    return {"gaps": gaps, "triggers": triggers(cfg, gaps, opened, now), "broken": broken(cfg, gaps, opened, now),
            "shape": hashlib.sha1(json.dumps([sorted((g["id"], g["state"]) for g in gaps.values()
                                                     if g["state"] not in ENDED), queue_state(cfg).get("blocked"),
                                              [i["id"] for i in opened]], default=str).encode()).hexdigest()[:12]}


def raise_one(cfg: dict, now: float | None = None) -> dict | None:
    """The session's situation, when one is due: broken (at once) or scheduled, and something changed since the last."""
    now = now or time.time()
    s = settings(cfg)
    known = fac.items("situation")
    if not s["open"] or any(x["state"] in ("raised", "leased") for x in known):
        return None
    st = state_now(cfg, now)
    handled = {p for x in known if x["state"] == "handled" for p in x["fields"].get("prints") or []}   # (answered)
    handled |= {x["fields"]["print"] for x in known if "prints" not in x["fields"] and x["fields"].get("print")
                and x["state"] in ("handled", "failed")}     # (the one-trigger watch's: each looked at, never raised again)
    new = [t for t in st["triggers"] if t["print"] not in handled]
    broke = {k: v for k, v in st["broken"].items() if f"broken-{k}-{v['since']:.0f}" not in handled}
    last = max(known, key=lambda x: float(x["fields"].get("raised_at") or 0), default=None)
    since = now - float((last or {}).get("fields", {}).get("raised_at") or 0)
    changed = bool(new or broke) or (last or {}).get("fields", {}).get("shape") != st["shape"]
    why = "broken" if broke and since >= s["broken"] * 60 else "scheduled" if since >= s["every"] * 60 else None
    if not why or not changed:
        return None
    sid = f"situation/{why}-{time.strftime('%Y%m%d-%H%M%S', time.gmtime(now))}-{secrets.token_hex(3)}"  # (never reused)
    prints = [t["print"] for t in new] + [f"broken-{k}-{v['since']:.0f}" for k, v in broke.items()]
    fac.say("situation.raised", sid, reason=why, triggers=new, broken=st["broken"], shape=st["shape"], prints=prints,
            raised_at=now, triggers_n=len(new), gap=sorted({t["subject"] for t in new if t["subject"].startswith("gap/")}))
    return {"id": sid, "reason": why, "triggers": new, "broken": st["broken"]}


def main(argv: list[str]) -> int:
    cfg = fac.config()
    now = time.time()
    if argv[:1] == ["open"]:
        print(settings(cfg)["open"])
    elif argv[:1] == ["stuck"]:
        print(len(stuck(cfg, {g["id"]: g for g in fac.items("gap")}, now)))
    elif argv[:1] == ["broken"]:
        grace = settings(cfg)["broken"]                  # (minutes past broken_minutes: the goal holds at 0)
        st = state_now(cfg, now)["broken"]
        print(round(max([(now - v["since"]) / 60 - (0 if k == "main-twice" else grace) for k, v in st.items()] + [0]), 1))
    elif argv[:1] == ["since"]:
        print(round((now - max([float(x["fields"].get("raised_at") or 0) for x in fac.items("situation")] or [now])) / 60, 1))
    else:
        print(f"watch: {(raise_one(cfg, now) or {}).get('id', 'nothing raised')}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
