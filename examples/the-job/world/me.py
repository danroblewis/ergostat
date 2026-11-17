"""Me, the owner, simulated: the part of the job that is mine (charter §7), done by hand in the work systems.

I answer reviews, mentions and customer tickets, post the alert-usefulness comments, declare
incidents, approve or reject flag ramps, send nudges, finish and circulate documents, do my
postmortem actions, send the weekly update and upgrade the CI server. Nothing does these for me:
ergostat's person blocks only ask, and the preparers only leave drafts in outbox/.

Now and then I also say something about the work while it is under way (notes()): that a review
can wait, that a flag ramp should be looked at first, that a review I answered needs another look,
or something too vague to place. I say it to ergostat (the note watcher relays it, as
`ergostat message` would): it routes it to the work it concerns.

What I am faster on is what was prepared: with a draft in the outbox I act within hours, without
one I get to it late or not at all. While I am in an outage, everything else takes three times as
long. On your laptop, with JOB_GH=1, the code host's part of this is you, for real."""

from __future__ import annotations

import random

from world.world import GH, World, days, drafted_at, u


def due(thing: dict, prepared: float | None, slow: tuple[float, float] | None, fast: tuple[float, float],
        busy: float) -> float | None:
    """When I get to it: soon after it was prepared, or (when it never is) late. Drawn once each."""
    if "_slow" not in thing:
        thing["_slow"] = thing["t"] + u(*slow) if slow else None
    if prepared and "_fast" not in thing:
        thing["_fast"] = prepared + u(*fast) * busy
    times = [x for x in (thing.get("_slow"), thing.get("_fast")) if x]
    return min(times) if times else None


NOTES_PER_DAY = 1.5                               # how often I say something about the work under way


def notes(w: World) -> None:
    """A note, now and then, about something under way: said as I would say it, never naming an id."""
    from world.world import DAY, STEP
    if random.random() > NOTES_PER_DAY * STEP / DAY:
        return
    settled = w.now - days(0.2)                     # what I talk about has been around a while (the watchers saw it)
    waiting = [(id, r) for id, r in w.things("review").items() if not r.get("answered") and not drafted_at(id)
               and r["t"] < settled]
    ramps = [(id, r) for id, r in w.things("ramp").items() if not r.get("decided") and not drafted_at(id)
             and not r.get("went_ahead") and r["t"] < settled]
    answered = [(id, r) for id, r in w.things("review").items() if r.get("answered") and r["answered"] < settled]
    choices = []
    if waiting:
        id, r = random.choice(waiting)
        choices.append((f"that review of {r.get('author', 'theirs')}'s, the {r.get('service', '')} one, can wait until "
                        f"tomorrow", None))
    if ramps:
        id, r = random.choice(ramps)
        choices.append((f"check the flag ramp first: {r['flag']}, before anything else", None))
    if answered and random.random() < 0.5:
        id, r = random.choice(answered)
        choices.append((f"on review {id.split('/')[1]}: I missed the {r.get('area', 'config')} change in it, it needs "
                        f"another look", None))
    if random.random() < 0.15 or not choices:       # now and then, too vague to place
        choices = [(random.choice(["hold that one for now", "can that wait?", "let's not do that today"]), None)]
    text, about = random.choice(choices)
    w.emit("note", f"note/{w.next_id('note', 0)}", "note.said", text=text, **({"about": about} if about else {}))


def step(w: World) -> None:
    now, busy = w.now, w.busy()
    notes(w)

    def ready(kind: str, done: str, slow, fast):
        for id, th in list(w.things(kind).items()):
            if th.get(done):
                continue
            at = due(th, drafted_at(id), slow, fast, busy)
            if at and now >= at:
                th[done] = now
                yield id, th

    if not GH:
        for id, th in ready("review", "answered", (1.4, 2.3), (0.15, 0.7)):
            w.emit("review", id, "review.answered", verdict=random.choice(["approved", "approved", "changes requested"]),
                   comments=random.randint(1, 7))
        for id, pr in list(w.things("pr").items()):          # a nudge drafted for my PR: I send it, or say it in person
            sent = drafted_at(id)
            if sent and not pr.get("nudge_sent") and not pr.get("reviewed"):
                pr.setdefault("_send_at", sent + u(0.05, 0.3) * busy)
                if now >= pr["_send_at"]:
                    pr["nudge_sent"] = now
                    pr["_review_at"] = min(pr["_review_at"], now + u(0.1, 0.4))
                    w.emit("pr", id, "pr.nudge-sent", to=pr["reviewers"])
    for id, pr in list(w.things("team-pr").items()):
        if drafted_at(id) and not pr.get("nudge_sent") and not pr.get("reviewed"):
            pr.setdefault("_send_at", drafted_at(id) + u(0.05, 0.3) * busy)
            if now >= pr["_send_at"]:
                pr["nudge_sent"] = now
                w.emit("team-pr", id, "team-pr.nudge-sent")
    for id, _ in ready("mention", "answered", (0.3, 0.6), (0.02, 0.2)):
        w.emit("mention", id, "mention.answered")
    for id, _ in ready("alert", "commented", (0.8, 1.6), (0.05, 0.35)):
        w.emit("alert", id, "alert.commented", useful=random.choice(["yes", "yes", "no: noisy", "no: duplicate"]))
    for id, o in list(w.things("outage").items()):          # the decision to declare is mine, prepared or not
        if o.get("suspected") and not (o.get("declared") or o.get("dismissed")):
            o.setdefault("_decide_at", o["suspected"] + u(0.12, 0.3))
            if now >= o["_decide_at"]:
                if random.random() < 0.85:
                    o["declared"] = now
                    o["_resolve_at"] = now + u(0.3, 0.7)
                    w.emit("outage", id, "outage.declared", commander="me")
                else:
                    o["dismissed"] = o["resolved"] = now
                    w.emit("outage", id, "outage.dismissed", why="one noisy dependency, not an outage")
    for id, r in ready("ramp", "decided", None, (0.1, 0.6)):
        if r.get("went_ahead"):
            continue
        ok = random.random() < 0.85
        r["approved" if ok else "rejected"] = now
        w.emit("ramp", id, "ramp.approved" if ok else "ramp.rejected")
        if ok:
            from world.traffic import note
            note(w, "flag", r["service"], f"{r['flag']} ramping ({r['schedule']})")
    for id, _ in ready("ticket", "answered", (0.9, 1.6), (0.1, 0.5)):
        w.emit("ticket", id, "ticket.answered", ran=random.choice(["ran it, after checking the account", "ran it",
                                                                   "declined: asked support for the account owner's OK"]))
    for id, d in list(w.things("doc").items()):             # a drafted document: I finish it and take it to its reviewers
        if drafted_at(id) and not d.get("circulated"):
            d.setdefault("_circulate_at", drafted_at(id) + u(0.05, 0.3) * busy)
            if now >= d["_circulate_at"]:
                d["circulated"] = now
                w.emit("doc", id, "doc.circulated", to="peers and the owning teams" if d["stage"] != "board"
                       else "the change advisory board")
    for id, _ in ready("action", "done", None, (1.0, 3.5)):
        w.emit("action", id, "action.done")
    for id, up in list(w.things("update").items()):
        if drafted_at(id) and not up.get("sent") and w.day_index() % 5 == 4:   # sent on Friday
            up["sent"] = now
            w.emit("update", id, "update.sent", to="my manager")
    ci = w.s.get("ci", {})
    plans = [drafted_at(id) for id in w.things("ci") if drafted_at(id)]
    if plans and ci.get("installed", 0) < ci.get("latest", 0):
        ci.setdefault("_upgrade_at", max(plans) + u(1.0, 2.5))
        if now >= ci["_upgrade_at"]:
            del ci["_upgrade_at"]
            target = ci["latest"]
            for id, th in list(w.things("ci").items()):
                if not th.get("upgraded") and int(id.split(".")[1]) <= target:
                    th["upgraded"] = now
                    w.emit("ci", id, "ci.upgraded", installed=f"2.{target}")
            ci["installed"] = target
