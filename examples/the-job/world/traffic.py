"""What arrives: everyone and everything else in the job. Rates are per working day.

Teammates open PRs and ask me to review theirs; chat channels talk; production deploys, fires
alerts and has outages; teams ask to ramp feature flags; secrets age; the CI server releases;
customers file tickets; changes need their documents, reviewed by peers and approved by the change
advisory board. How the world answers what I do is here too: a nudge that was sent gets a review
sooner, a flag ramped without my review is likelier to break something."""

from __future__ import annotations

import math
import random

from world.world import World, days, drafted_at, u

SERVICES = ["checkout-api", "search", "billing", "auth-gateway", "notifications", "ingest", "reports", "storage"]
REPOS = ["platform", "deploy-tools", "service-mesh", "infra-config", "observability"]
PEOPLE = ["Ana", "Ben", "Chen", "Dara", "Eli", "Femi", "Gus", "Hana"]
TEAMS = ["payments", "search", "identity", "data", "mobile"]
CHANNELS = ["#my-team", "#platform-ops", "#incidents", "#deploys", "#flag-ramps", "#support-escalations"]
TOPICS = ["rollout", "cert", "latency", "quota", "migration", "on-call swap", "flag", "deploy freeze"]
AREAS = {"retry": ["client/retry.go", "client/backoff.go"], "config": ["deploy/values.yaml", "config/limits.yaml"],
         "auth": ["auth/tokens.go", "auth/session.go"], "schema": ["db/migrations/0042_add_index.sql", "db/models.go"],
         "metrics": ["telemetry/metrics.go", "dashboards/service.json"], "pipeline": ["ci/pipeline.yaml", "ci/steps.sh"]}
PR_TITLES = {"retry": "Cap retries on {svc} calls", "config": "Raise connection limits for {svc}",
             "auth": "Rotate session signing for {svc}", "schema": "Index lookups in {svc}",
             "metrics": "Export queue depth from {svc}", "pipeline": "Split {svc} pipeline into stages"}
RATES = {"pr": 1.6, "review": 3.0, "team-pr": 2.0, "chat": 36.0, "alert": 1.2, "outage": 0.25, "ramp": 1.3,
         "ticket": 0.9, "change": 0.35, "deploy": 3.0}
STAGES = ["problem", "proposal", "design", "board"]
STAGE_NAMES = {"problem": "Problem statement", "proposal": "Proposal", "design": "Design document",
               "board": "Change advisory board ticket"}
COMMANDS = ["re-run the export for account {acct} for the last 7 days", "clear the stuck sync job for tenant {acct}",
            "raise the API quota for {acct} to 2x for 48h", "reissue the webhook signing key for {acct}",
            "replay the failed invoices for {acct} from the dead-letter queue"]


def poisson(mean: float) -> int:
    if mean <= 0:
        return 0
    k, p, limit = 0, 1.0, math.exp(-mean)
    while True:
        p *= random.random()
        if p <= limit:
            return k
        k += 1


def note(w: World, what: str, service: str, ref: str) -> None:
    """The recent history the preparers correlate against: deploys, flag changes, merged commits."""
    w.s["log"].append({"t": w.now, "what": what, "service": service, "ref": ref})
    del w.s["log"][:-300]


def change_like(w: World) -> dict:
    area = random.choice(list(AREAS))
    svc = random.choice(SERVICES)
    return {"title": PR_TITLES[area].format(svc=svc), "repo": random.choice(REPOS), "service": svc, "area": area,
            "files": AREAS[area] + random.sample(["README.md", "tests/test_main.go", "Makefile"], random.randint(0, 2)),
            "additions": random.randint(8, 420), "deletions": random.randint(0, 120)}


# ---- arrivals

def open_my_pr(w: World, t: float | None = None) -> None:
    n = w.next_id("pr", 1180)
    c = change_like(w)
    th = w.add("pr", f"pr/{n}", "pr.opened", number=n, **c, reviewers=random.sample(PEOPLE, 2),
               url=f"https://code.example/{c['repo']}/pull/{n}")
    if t is not None:
        th["t"] = t
    th["_review_at"] = th["t"] + u(0.4, 2.6)


def ask_review(w: World, t: float | None = None) -> None:
    n = w.next_id("review", 2040)
    c = change_like(w)
    th = w.add("review", f"review/{n}", "review.requested", number=n, author=random.choice(PEOPLE), **c,
               url=f"https://code.example/{c['repo']}/pull/{n}")
    if t is not None:
        th["t"] = t


def open_team_pr(w: World) -> None:
    n = w.next_id("team-pr", 3100)
    c = change_like(w)
    th = w.add("team-pr", f"team-pr/{n}", "team-pr.opened", number=n, author=random.choice(PEOPLE), **c,
               url=f"https://code.example/{c['repo']}/pull/{n}")
    th["_review_at"] = th["t"] + days(min(7.0, random.expovariate(1 / 1.8)))


def chat(w: World) -> None:
    n = w.next_id("chat", 0)
    ch = random.choice(CHANNELS)
    to_me = random.random() < 0.16
    topic = random.choice(TOPICS)
    who = random.choice(PEOPLE)
    text = random.choice([f"@me can you take a look at the {topic} question in {ch}?",
                          f"@me is the {topic} change safe to ship today?",
                          f"@me who owns the {topic} alerts now?"]) if to_me else \
        random.choice([f"{topic} for {random.choice(SERVICES)} is done", f"anyone seen {topic} issues today?",
                       f"reminder: {topic} review at 3pm", f"{random.choice(SERVICES)} {topic} looks fine"])
    w.emit("chat", f"chat/{n}", "chat.message", channel=ch, author=who, text=text, topic=topic, to_me=to_me)
    if to_me:
        w.things("mention")[f"mention/{n}"] = {"t": w.now, "channel": ch, "author": who, "text": text, "topic": topic}


def fire_alert(w: World, service: str, outage: str | None = None) -> None:
    n = w.next_id("alert", 700)
    summary = random.choice(["error rate above 2%", "p99 latency above 800ms", "queue depth rising",
                             "pod restarts", "5xx from load balancer", "disk 90% full"])
    w.add("alert", f"alert/{n}", "alert.fired", service=service, summary=f"{service}: {summary}",
          severity=random.choice(["high", "low"]) if not outage else "high", outage=outage or "")


def start_outage(w: World, service: str, cause: str) -> None:
    n = w.next_id("outage", 40)
    w.things("outage")[f"outage/{n}"] = {"t": w.now, "service": service, "cause": cause, "alerts": 0,
                                         "_alerts_left": random.randint(3, 5), "_next_alert": w.now}


def ask_ramp(w: World, t: float | None = None) -> None:
    n = w.next_id("ramp", 300)
    svc = random.choice(SERVICES)
    flag = f"{svc}-{random.choice(['new-cache', 'async-write', 'v2-router', 'batch-api', 'lazy-load'])}"
    th = w.add("ramp", f"ramp/{n}", "ramp.requested", flag=flag, team=random.choice(TEAMS), service=svc,
               schedule=random.choice(["1% → 10% → 50% → 100% over 3 days", "5% → 25% → 100% over 2 days",
                                       "10% → 100% tomorrow"]),
               pr=f"https://code.example/{random.choice(REPOS)}/pull/{random.randint(2000, 3999)}")
    if t is not None:
        th["t"] = t


def file_ticket(w: World, t: float | None = None) -> None:
    n = w.next_id("ticket", 5200)
    acct = f"customer-{random.choice('ABCDEFGH')}{random.randint(10, 99)}"
    th = w.add("ticket", f"ticket/{n}", "ticket.assigned", customer=acct,
               title=random.choice(["Export missing rows", "Sync stuck since yesterday", "Hitting API quota",
                                    "Webhook signatures failing", "Invoices not sent"]),
               asks=random.choice(COMMANDS).format(acct=acct), sla="1 working day")
    if t is not None:
        th["t"] = t


def start_change(w: World, stage: int = 0) -> None:
    n = w.next_id("change", 10)
    svc = random.choice(SERVICES)
    title = random.choice([f"Move {svc} to the new queue", f"Retire the old {svc} endpoint",
                           f"Encrypt {svc} backups at rest", f"Regional failover for {svc}"])
    w.things("change")[f"change-{n}"] = {"t": w.now, "title": title, "service": svc, "stage": stage, "rollout": None}
    need_doc(w, f"change-{n}")


def need_doc(w: World, change: str) -> None:
    c = w.things("change")[change]
    stage = STAGES[c["stage"]]
    item = f"doc/{change.split('-')[1]}-{stage}"
    data = {"change": c["title"], "stage": stage, "title": f"{STAGE_NAMES[stage]}: {c['title']}"}
    if stage == "board":
        c["rollout"] = w.now + u(1.6, 2.6)
        data["rollout"] = w.clock(c["rollout"])
    w.add("doc", item, "doc.needed", **data)["change_id"] = change


def release_ci(w: World) -> None:
    ci = w.s.setdefault("ci", {"latest": 40, "installed": 40})
    ci["latest"] += 1
    w.add("ci", f"ci/2.{ci['latest']}", "ci.released", version=f"2.{ci['latest']}", installed=f"2.{ci['installed']}",
          notes=random.choice(["security fixes in the agent protocol", "plugin API change: pipeline steps",
                               "faster artifact uploads", "drops support for the old agent"]))


def seed(w: World) -> None:
    """The job as it is on Monday morning: some things already waiting, two of them for too long."""
    now = w.now
    for k, (name, svc, left) in enumerate([("db-replica-password", "storage", 9), ("tls-cert-api", "checkout-api", 21),
                                          ("ci-deploy-token", "deploy-tools", 33), ("pager-webhook", "notifications", 45),
                                          ("search-api-key", "search", 31.5), ("billing-signing-key", "billing", 58),
                                          ("ingest-bucket-key", "ingest", 70), ("oauth-client-secret", "auth-gateway", 38)]):
        w.things("secret")[f"secret/{name}"] = {"t": now, "name": name, "service": svc, "expires": now + days(left)}
    w.s["ci"] = {"latest": 40, "installed": 39}
    w.things("ci")["ci/2.40"] = {"t": now - days(3), "version": "2.40", "installed": "2.39"}
    w.emit("ci", "ci/2.40", "ci.released", version="2.40", installed="2.39", notes="new agent protocol")
    open_my_pr(w, now - days(0.9))
    open_my_pr(w, now - days(0.2))
    ask_review(w, now - days(0.95))
    ask_review(w, now - days(0.3))
    ask_ramp(w, now - days(0.6))
    file_ticket(w, now - days(0.5))
    for stage in (0, 2, 3):
        start_change(w, stage)
    w.s["day"] = -1
    w.s["planned_outage"] = now + days(1.3)          # Tuesday morning: something breaks, whatever else happens


# ---- every step

def step(w: World, d: float) -> None:
    now = w.now
    for _ in range(0 if _code_host_is_real() else poisson(RATES["pr"] * d)):
        open_my_pr(w)
    for _ in range(0 if _code_host_is_real() else poisson(RATES["review"] * d)):
        ask_review(w)
    for _ in range(poisson(RATES["team-pr"] * d)):
        open_team_pr(w)
    for _ in range(poisson(RATES["chat"] * d)):
        chat(w)
    for _ in range(poisson(RATES["alert"] * d)):
        fire_alert(w, random.choice(SERVICES))
    for _ in range(poisson(RATES["outage"] * d)):
        start_outage(w, random.choice(SERVICES), "unknown")
    for _ in range(poisson(RATES["ramp"] * d)):
        ask_ramp(w)
    for _ in range(poisson(RATES["ticket"] * d)):
        file_ticket(w)
    for _ in range(poisson(RATES["change"] * d)):
        start_change(w)
    for _ in range(poisson(RATES["deploy"] * d)):
        note(w, "deploy", random.choice(SERVICES), f"build {random.randint(1000, 9999)}")
    if random.random() < d / 3.5:
        release_ci(w)
    if w.s.get("planned_outage") and now >= w.s["planned_outage"]:
        del w.s["planned_outage"]
        start_outage(w, "checkout-api", "a bad config push")
    days_turn(w)
    reviewers(w)
    production(w)
    paper_trail(w)
    secrets(w)


def _code_host_is_real() -> bool:
    from world.world import GH
    return GH


def days_turn(w: World) -> None:
    """Each working day starts and ends; the calendar has its meetings; a new week's update falls due."""
    k = w.day_index()
    frac = (w.now - w.s["t0"]) / days(1) - k
    if w.s["day"] < k:
        last = w.things("day").get(f"day/{w.date(w.s['day'])}") if w.s["day"] >= 0 else None
        if last and not last.get("ended"):
            last["ended"] = w.now
            w.emit("day", f"day/{last['date']}", "day.ended")
        w.s["day"] = k
        date = w.date(k)
        meetings = ["09:30 standup"]
        if k % 5 == 2:
            meetings.append("11:00 one-to-one with my manager")
        if k % 2 == 1:
            meetings.append("14:00 change advisory board")
        if any(o.get("resolved") and o["resolved"] > w.now - days(1) for o in list(w.things("outage").values())):
            meetings.append("15:00 incident review")
        w.add("day", f"day/{date}", "day.started", date=date, meetings=meetings)
        if k % 5 == 3:                                    # Thursday: this week's update is due
            w.add("update", f"update/{w.date(k - 3)}", "update.due", week_of=w.date(k - 3), due=date + " (Thursday)")
    day = w.things("day").get(f"day/{w.date(k)}")
    if day and frac > 0.95 and not day.get("ended"):
        day["ended"] = w.now
        w.emit("day", f"day/{w.date(k)}", "day.ended")


def reviewers(w: World) -> None:
    """Teammates review my PRs (sooner once nudged), and their own PRs get reviewed and merged."""
    for id, pr in list(w.things("pr").items()):
        if pr.get("merged"):
            continue
        if not pr.get("reviewed") and w.now >= pr["_review_at"]:
            pr["reviewed"] = w.now
            w.emit("pr", id, "pr.reviewed", reviewer=random.choice(pr["reviewers"]),
                   verdict=random.choice(["approved", "approved", "changes requested"]))
            pr["_merge_at"] = w.now + u(0.1, 0.7)
        elif pr.get("reviewed") and w.now >= pr["_merge_at"]:
            pr["merged"] = w.now
            w.emit("pr", id, "pr.merged")
            note(w, "merged", pr["service"], f"{pr['repo']}#{pr['number']} {pr['title']}")
    for id, pr in list(w.things("team-pr").items()):
        if pr.get("merged"):
            continue
        if pr.get("nudge_sent"):
            pr["_review_at"] = min(pr["_review_at"], pr["nudge_sent"] + u(0.1, 0.4))
        if not pr.get("reviewed") and w.now >= pr["_review_at"]:
            pr["reviewed"] = w.now
            w.emit("team-pr", id, "team-pr.reviewed")
        elif pr.get("reviewed") and w.now >= pr["reviewed"] + days(0.3):
            pr["merged"] = w.now
            w.emit("team-pr", id, "team-pr.merged")
            note(w, "merged", pr["service"], f"{pr['repo']}#{pr['number']} {pr['title']}")


def production(w: World) -> None:
    """Outages fire their alerts; one becomes visible as an outage at its third; a declared one is resolved and
    leaves postmortem actions at its postmortem; a flag ramped without review may break its service, hours later, or
    prove fine after half a working day live."""
    for id, o in list(w.things("outage").items()):
        if o["_alerts_left"] > 0 and w.now >= o["_next_alert"]:
            fire_alert(w, o["service"], id)
            o["_alerts_left"] -= 1
            o["alerts"] += 1
            o["_next_alert"] = w.now + u(0.01, 0.05)
            if o["alerts"] == 3:
                o["suspected"] = w.now
                w.emit("outage", id, "outage.suspected", service=o["service"], alerts=3, cause=o["cause"])
        if o.get("declared") and not o.get("resolved") and w.now >= o["_resolve_at"]:
            o["resolved"] = w.now
            w.emit("outage", id, "outage.resolved")
            o["_postmortem_at"] = w.now + u(0.2, 0.4)
        if o.get("_postmortem_at") and w.now >= o["_postmortem_at"]:
            del o["_postmortem_at"]
            w.emit("outage", id, "outage.reviewed")
            for what in random.sample([f"Alert on {o['service']} saturation before it pages", "Add a runbook step",
                                       f"Load-test {o['service']} at 2x", "Make the rollback one command",
                                       "Proposal: owning team adds a circuit breaker"], random.randint(2, 3)):
                n = w.next_id("action", 900)
                w.add("action", f"action/{n}", "action.filed", outage=id, title=what, owner="me",
                      service=o["service"])
    for rid, ramp in list(w.things("ramp").items()):
        if ramp.get("went_ahead") and not ramp.get("_effect_done"):
            ramp["_effect_done"] = True
            if random.random() < 0.45:
                ramp["_breaks_at"] = w.now + u(0.1, 0.5)
            else:
                ramp["_fine_at"] = w.now + days(0.5)          # live half a day and nothing broke
        if ramp.get("_breaks_at") and w.now >= ramp["_breaks_at"]:
            del ramp["_breaks_at"]
            w.emit("ramp", rid, "ramp.broke", service=ramp["service"])
            start_outage(w, ramp["service"], f"flag {ramp['flag']} ramped without review")
        if ramp.get("_fine_at") and w.now >= ramp["_fine_at"]:
            del ramp["_fine_at"]
            w.emit("ramp", rid, "ramp.proved-fine")
        if ramp.get("approved") and not ramp.get("_effect_done"):
            ramp["_effect_done"] = True
            if random.random() < 0.05:
                fire_alert(w, ramp["service"])
    for id, ramp in list(w.things("ramp").items()):
        decided = ramp.get("approved") or ramp.get("rejected") or ramp.get("went_ahead")
        if not decided and w.now > ramp["t"] + days(1.6):
            ramp["went_ahead"] = w.now
            w.emit("ramp", id, "ramp.went-ahead")
            note(w, "flag", ramp["service"], f"{ramp['flag']} ramped (no review)")


def next_board(w: World, after: float) -> float:
    """The change advisory board meets at 14:00 every other working day."""
    k = w.day_index(after)
    while True:
        at = w.s["t0"] + days(k + 0.625)
        if k % 2 == 1 and at > after:
            return at
        k += 1


def paper_trail(w: World) -> None:
    """Circulated documents are approved by their reviewers, board tickets at the next board meeting; each approval
    opens the change's next document. A rollout whose board ticket is not approved in time slips a day."""
    for id, doc in list(w.things("doc").items()):
        if doc.get("approved") or not doc.get("circulated"):
            continue
        if "_approve_at" not in doc:
            doc["_approve_at"] = doc["circulated"] + u(0.4, 1.1) if doc["stage"] != "board" else \
                next_board(w, doc["circulated"] + days(0.1))
        if w.now >= doc["_approve_at"]:
            doc["approved"] = w.now
            w.emit("doc", id, "doc.approved", approvals=random.randint(2, 4), comments=random.randint(3, 14))
            c = w.things("change")[doc["change_id"]]
            if doc["stage"] == "board":
                c["approved"] = w.now
            else:
                c["stage"] += 1
                need_doc(w, doc["change_id"])
    for c in list(w.things("change").values()):
        if c.get("rollout") and not c.get("approved") and w.now > c["rollout"]:
            c["rollout"] += days(1)
            c["slipped"] = c.get("slipped", 0) + 1


def secrets(w: World) -> None:
    """Secrets whose rotation ticket was drafted (and filed by me) are rotated by the team; one nobody ticketed
    expires, and breaks its service."""
    for id, s in list(w.things("secret").items()):
        drafted = drafted_at(id)
        if drafted and drafted > s.get("rotated", 0) and "_rotate_at" not in s:
            s["_rotate_at"] = drafted + u(2, 6)
        if "_rotate_at" in s and w.now >= s["_rotate_at"]:
            del s["_rotate_at"]
            s["rotated"] = w.now
            s["expires"] = w.now + days(random.uniform(60, 90))
            w.emit("secret", id, "secret.rotated", expires=w.clock(s["expires"]))
        elif w.now >= s["expires"]:
            start_outage(w, s["service"], f"secret {s['name']} expired")
            s["rotated"] = w.now
            s["expires"] = w.now + days(90)
            w.emit("secret", id, "secret.rotated", expires=w.clock(s["expires"]), emergency=True)
