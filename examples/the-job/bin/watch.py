"""The watchers: programs that read a work system and record what they see as events about items. Watch is the
first verb (charter §2): programs filter, nothing calls a model, nothing is written back.

    watch.py KIND      read what is new for one kind of item; print it as observations, then the arrivals per hour

Each is a sensor on its kind's arrival flow (review-requests, alerts-fired, ...): its number is how
many arrived in the last ten minutes, per hour, and the lines before it are what it saw (ergostat
records them as events, and the items fold from them). The note watcher relays what I said about the
work as my messages ({"message": {...}} lines), which ergostat routes to the work they concern. Besides passing on what happened, a watcher
notices what has gone on too long: a review unanswered for a working day (review.late), a PR of
mine with no first review after one (pr.stale), a teammate's PR stale three days (that is the only
kind of teammate's PR it reports), a secret within 30 days of expiry, a board ticket with its
rollout a day away.

The world is the simulation (world/); with JOB_GH=1 the code host's kinds (pr, review) are read
from GitHub with read-only gh commands instead (bin/codehost.py)."""

from __future__ import annotations

import json
import sys
import time

from job import ROOT

from world import world as W

WATCH = ROOT / "run" / "watch"
WINDOW = 600.0                                    # arrivals per hour, over the last ten minutes

# kind: (the feed kinds it reads, the event that brings a new item, what it passes on)
KINDS = {
    "pr": (["pr"], "pr.opened", ["pr.reviewed", "pr.merged", "pr.nudge-sent"]),
    "review": (["review"], "review.requested", ["review.answered"]),
    "team-pr": (["team-pr"], "team-pr.stale", []),
    "mention": (["chat", "mention"], "mention.received", ["mention.answered"]),
    "secret": (["secret"], "secret.expiring", ["secret.rotated"]),
    "alert": (["alert"], "alert.fired", ["alert.commented"]),
    "outage": (["outage"], "outage.suspected", ["outage.declared", "outage.dismissed", "outage.resolved",
                                               "outage.reviewed"]),
    "action": (["action"], "action.filed", ["action.done"]),
    "ramp": (["ramp"], "ramp.requested", ["ramp.approved", "ramp.rejected", "ramp.went-ahead", "ramp.broke",
                                         "ramp.proved-fine"]),
    "ci": (["ci"], "ci.released", ["ci.upgraded"]),
    "ticket": (["ticket"], "ticket.assigned", ["ticket.answered"]),
    "doc": (["doc"], "doc.needed", ["doc.approved", "doc.circulated"]),
    "update": (["update"], "update.due", ["update.sent"]),
    "day": (["day"], "day.started", ["day.ended"]),
    "note": (["note"], "note.said", []),          # what I said about the work: relayed to ergostat as my message
}
# kind: (working days, the event saying so): what has waited too long, and is not done yet
LATE = {"review": (1.0, "review.late"), "pr": (2.0, "pr.late"), "mention": (0.5, "mention.late"),
        "alert": (0.5, "alert.late"), "ramp": (1.0, "ramp.late"), "ticket": (0.75, "ticket.late")}
DONE = {"review": "answered", "pr": "reviewed", "mention": "answered", "alert": "commented", "ramp": "decided",
        "ticket": "answered"}
SHOWN = {"pr": ["title", "repo", "url", "reviewers"], "review": ["title", "author", "repo", "url"],
         "alert": ["service", "summary", "severity", "outage"], "ramp": ["flag", "team", "service", "schedule"],
         "ticket": ["customer", "title", "asks", "sla"], "doc": ["change", "stage", "title", "rollout"]}


def say(type: str, item: str, data: dict | None = None) -> None:
    print(json.dumps({"event": type, "item": item, "data": data or {}}), flush=True)


def watch(kind: str, w: W.World, mem: dict) -> None:
    feed_kinds, arrival, passes = KINDS[kind]
    lines, mem["offset"] = W.feed(mem.get("offset", 0))
    seen = set(mem.setdefault("seen", []))
    flagged = mem.setdefault("flagged", {})
    arrivals = mem.setdefault("arrivals", [])

    def arrive(item: str, data: dict) -> None:
        say(arrival, item, data)
        seen.add(item)
        arrivals.append(time.time())

    for e in lines:
        if e["kind"] not in feed_kinds:
            continue
        if kind == "note":                          # my words, verbatim: ergostat routes them to the work (SPEC §12h)
            print(json.dumps({"message": {"text": e["data"]["text"], "by": "me",
                                          **({"about": e["data"]["about"]} if e["data"].get("about") else {})}}), flush=True)
            arrivals.append(time.time())
            continue
        data = {k: v for k, v in e["data"].items() if not SHOWN.get(kind) or k in SHOWN[kind] or e["type"] != arrival}
        if kind == "mention":
            if e["type"] == "chat.message":           # the filter: only what mentions me
                digest(e)
                if e["data"].get("to_me"):
                    arrive(e["item"].replace("chat/", "mention/"), {k: e["data"][k] for k in ("channel", "author", "text")})
            elif e["item"] in seen:
                say(e["type"], e["item"], data)
        elif kind == "team-pr":
            if e["item"] in seen and e["type"] in ("team-pr.reviewed", "team-pr.merged"):
                say("team-pr.moving", e["item"], {"moved": e["type"].split(".")[1]})
            elif e["item"] in seen and e["type"] == "team-pr.nudge-sent":
                say(e["type"], e["item"])
        elif kind == "secret":
            if e["type"] in passes and e["item"] in seen:
                say(e["type"], e["item"], data)
                flagged.pop(e["item"], None)
        elif e["type"] == arrival:
            arrive(e["item"], {**data, "nudged": "no"} if kind == "pr" else data)
        elif e["type"] in passes or e["item"] in seen:
            say(e["type"], e["item"], data)
    now = w.now
    if kind in LATE:
        limit, what = LATE[kind]
        for id, th in list(w.things(kind).items()):
            if id in seen and not th.get(DONE[kind]) and now - th["t"] > W.days(limit) and not flagged.get(id):
                flagged[id] = True
                say(what, id, {"late": "yes", "waited": f"over {limit:g} working day{'s' if limit != 1 else ''}"})
    if kind == "pr":                              # a working day with no first review: stale, until a nudge is drafted
        for id, th in list(w.things("pr").items()):
            if id in seen and not th.get("reviewed") and now - th["t"] > W.days(1) and flagged.get(id + "#stale") is None:
                flagged[id + "#stale"] = True
                say("pr.stale", id, {"waiting": "over 1 working day for a first review"})
    if kind == "team-pr":                         # the filter: a teammate's PR is mine to notice once stale 3 days
        for id, th in list(w.things("team-pr").items()):
            if id not in seen and not th.get("reviewed") and now - th["t"] > W.days(3):
                arrive(id, {k: th[k] for k in ("author", "title", "repo", "url")})
    if kind == "secret":                          # within 30 days of expiry (once per expiry date)
        for id, th in list(w.things("secret").items()):
            left = (th["expires"] - now) / W.days(1)
            if left <= 30 and flagged.get(id) != th["expires"]:
                flagged[id] = th["expires"]
                arrive(id, {"name": th["name"], "service": th["service"], "expires": w.clock(th["expires"]),
                            "days_left": round(left, 1)})
    if kind == "doc":                             # a board ticket not yet approved, its rollout within a working day
        changes = w.things("change")
        for id, th in list(w.things("doc").items()):
            c = changes.get(th.get("change_id", ""), {})
            if th["stage"] == "board" and not th.get("approved") and c.get("rollout") and \
                    c["rollout"] - now < W.days(1) and flagged.get(id) != c["rollout"]:
                flagged[id] = c["rollout"]
                say("doc.due", id, {"due": "yes", "rollout": w.clock(c["rollout"]), "slipped": c.get("slipped", 0)})
            if th.get("approved") and flagged.get(id):
                flagged[id] = None
                say("doc.due", id, {"due": "no"})
    mem["seen"] = sorted(seen)
    mem["arrivals"] = [t for t in arrivals if t > time.time() - WINDOW]


def digest(e: dict) -> None:
    """Each tracked channel's day, for the morning brief's digests."""
    path = WATCH / "digest.json"
    d = json.loads(path.read_text()) if path.exists() else {}
    ch = d.setdefault(e["data"]["channel"], {"messages": 0, "topics": {}, "since": e["t"]})
    ch["messages"] += 1
    ch["topics"][e["data"]["topic"]] = ch["topics"].get(e["data"]["topic"], 0) + 1
    path.write_text(json.dumps(d))


def main() -> int:
    kind = sys.argv[1]
    WATCH.mkdir(parents=True, exist_ok=True)
    path = WATCH / f"{kind}.json"
    mem = json.loads(path.read_text()) if path.exists() else {}
    if W.GH and kind in ("pr", "review"):
        import codehost
        codehost.watch(kind, mem)
    else:
        with W.advanced() as w:
            watch(kind, w, mem)
    path.write_text(json.dumps(mem))
    print(round(len(mem["arrivals"]) * 3600 / WINDOW, 2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
