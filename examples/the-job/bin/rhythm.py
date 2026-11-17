"""The operating rhythm (charter §5): the morning brief and the ledger, both files in the outbox.

    rhythm.py brief     for each working day started: outbox/brief-<date>.md, the false conditions ranked, overnight
                        alerts and outages, the channels' digests, what waits on me, today's meetings with prep notes
    rhythm.py ledger    for each working day ended: outbox/ledger-<date>.md, what I did that day with links, and
                        tomorrow's top three

Record is the fifth verb: the ledger is how work becomes evidence. The weekly update (prepare.py
update) is built from it."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from job import DAY, OUTBOX, ROOT, clock_of, event, every_item, loops, moved, world, write_draft

# the register (charter §4): each goal as the condition it checks, true or false right now
CONDITIONS = {
    "stale-prs-nudged": "No PR of mine has waited over a working day for a first review without a nudge drafted",
    "my-prs-reviewed": "No PR of mine waits over 2 working days for a first review",
    "every-review-briefed": "Every review requested of me has a brief",
    "reviews-on-time": "Every review requested of me is answered within 1 working day",
    "every-doc-drafted": "Every document a change needs next has a draft",
    "board-before-rollout": "Every change shipping to the regulated environment is approved by the board before rollout",
    "every-mention-triaged": "Every message mentioning me is triaged",
    "mentions-answered": "Every message mentioning me is answered within 4 hours",
    "secrets-ticketed": "No secret I own expires within 30 days without a ticket",
    "every-alert-drafted": "Every alert from my rotation has a drafted usefulness comment",
    "alerts-commented": "Every alert ticket has my usefulness comment within half a day",
    "outages-decided": "Every suspected outage is declared or dismissed",
    "actions-planned": "Every postmortem action assigned to me has an owner, a date and a first step",
    "every-ramp-briefed": "Every pending flag ramp awaiting my approval has a research brief",
    "ramps-decided": "No flag ramp waits over a working day for my decision",
    "ci-upgrade-planned": "The CI server is within one version of current, or an upgrade plan exists",
    "every-ticket-explained": "Every customer ticket assigned to me has its command explained",
    "tickets-within-sla": "Every customer ticket assigned to me has a response within its SLA",
    "team-prs-nudged": "No teammate PR is stale over 3 days without a nudge drafted",
    "update-drafted": "This week's manager update is drafted by Thursday",
    "morning-brief-ready": "Today's morning brief is written before standup",
    "day-recorded": "Every working day is in the ledger",
}
DONE = {"review": ("answered", "answered the review"), "pr": ("merged", "merged my PR"),
        "mention": ("answered", "answered"), "alert": ("commented", "commented on the alert"),
        "outage": ("declared", "declared the incident"), "action": ("done", "did the postmortem action"),
        "ramp": ("approved", "approved the ramp"), "ticket": ("answered", "answered the customer"),
        "doc": ("approved", "got approval for"), "update": ("sent", "sent the weekly update"),
        "ci": ("upgraded", "upgraded the CI server to"), "secret": ("drafted", "drafted the rotation ticket for")}
WAITING = [("review", "briefed", "Reviews, briefed", "brief"), ("review", "requested", "Reviews, no brief yet", None),
           ("pr", "stale", "My PRs stuck", None), ("pr", "nudged", "My PRs nudged, waiting", "nudge"),
           ("ramp", "briefed", "Flag ramps pending", "brief"), ("secret", "expiring", "Secrets expiring", None),
           ("secret", "drafted", "Secrets with a ticket drafted", "ticket"),
           ("ticket", "explained", "Customer tickets", "explanation"), ("doc", "drafted", "Documents to finish", "draft"),
           ("mention", "triaged", "Mentions to answer", "reply")]


def title(it: dict) -> str:
    f = it["fields"]
    return f.get("title") or f.get("summary") or f.get("flag") or f.get("name") or f.get("text") or f.get("version") or ""


def link(it: dict, field: str | None) -> str:
    v = it["fields"].get(field or "", "")
    if not (isinstance(v, str) and v.startswith("file:")):
        return ""
    p = v.removeprefix("file:")
    return f" · [{Path(p).stem}]({os.path.relpath(ROOT / p, OUTBOX)})"     # relative: it opens beside the brief


def brief(day: dict, everything: list[dict], w: dict) -> str:
    date = day["fields"].get("date", day["id"].split("/")[1])
    off = [(g, lp) for g, lp in loops().items() if lp["status"] == "off" and g != "morning-brief-ready"]
    off.sort(key=lambda x: -abs(x[1].get("error") or 0))
    out = [f"# Morning brief: {date}", ""]
    out += ["## False conditions, ranked", ""]
    out += [f"{n}. **{CONDITIONS.get(g, g)}**: {lp['stock']} is {lp['value']:g} (holds {str(lp['setpoint']).replace('<=', '≤').replace('>=', '≥').replace('==', '=')})"
            for n, (g, lp) in enumerate(off, 1)] or ["All true: nothing is off."]
    since = day["first"] - DAY                        # since yesterday's start
    overnight = [i for i in everything if i["kind"] in ("alert", "outage") and i["first"] >= since]
    out += ["", "## Since yesterday: alerts and outages", ""]
    out += [f"- {i['id']} {title(i) or i['fields'].get('service', '')} · {i['state']}{link(i, 'comment')}"
            for i in overnight[-12:]] or ["- none"]
    digest = ROOT / "run" / "watch" / "digest.json"
    d = json.loads(digest.read_text()) if digest.exists() else {}
    out += ["", "## Channel digests", ""]
    out += [f"- {ch}: {x['messages']} messages; most about " +
            ", ".join(f"{t} ({n})" for t, n in sorted(x["topics"].items(), key=lambda kv: -kv[1])[:3])
            for ch, x in sorted(d.items())] or ["- quiet"]
    digest.write_text("{}")                            # each brief digests what came since the last
    out += ["", "## Waiting on me", ""]
    for kind, state, label, field in WAITING:
        its = [i for i in everything if i["kind"] == kind and i["state"] == state]
        if its:
            out.append(f"**{label}** ({len(its)})")
            out += [f"- {i['id']} {title(i)}{link(i, field)}" for i in its[:6]] + [""]
    follow = [i for i in everything if i["kind"] == "note" and i["state"] == "open"]
    if follow:                                        # my notes on finished work (SPEC §12h follow-ups)
        out += ["## My notes on finished work", ""]
        out += [f"- {i['id']} on {i['fields'].get('follows')}: \u201c{i['fields'].get('note', '')}\u201d" for i in follow[:8]] + [""]
    lost = [i for i in everything if i["kind"] == "ergostat.message" and i["state"] == "unrouted"]
    if lost:                                          # what I said that reached no work
        out += ["## What I said that reached no work", ""]
        out += [f"- \u201c{i['fields'].get('text', '')}\u201d ({i['id'].split('/')[1]}: `ergostat messages "
                f"{i['id'].split('/')[1]} --about ITEM`)" for i in lost[-6:]] + [""]
    out += ["## Today's meetings", ""]
    boards = [i for i in everything if i["kind"] == "doc" and i["fields"].get("stage") == "board" and
              i["state"] != "approved"]
    for m in day["fields"].get("meetings", []):
        prep = {"standup": "yesterday's ledger and today's top three",
                "one-to-one": "the weekly update draft, and anything stuck over 2 days",
                "change advisory board": "board tickets: " + (", ".join(i["id"] for i in boards) or "none due"),
                "incident review": "the outage's timeline and the action items"}
        note = next((v for k, v in prep.items() if k in m), "")
        out.append(f"- {m}" + (f" · prep: {note}" if note else ""))
    out += ["", f"*Built at {clock_of(w, w.get('now', 0))} from the watchers' record; nothing was sent.*"]
    return "\n".join(out)


def ledger(day: dict, everything: list[dict]) -> str:
    date = day["fields"].get("date", day["id"].split("/")[1])
    start, end = day["first"], day["entered"]
    out = [f"# Ledger: {date}", "", "## What I did", ""]
    for i in everything:
        done = DONE.get(i["kind"])
        if done and i["state"] == done[0] and start <= i["entered"] <= end:
            url = i["fields"].get("url", "")
            out.append(f"- {done[1]} {i['id']} {title(i)}" + (f" ({url})" if url else ""))
    if len(out) == 4:
        out.append("- nothing recorded")
    prepared = sum(1 for i in everything if i["kind"] in DONE and start <= i["last"] <= end)
    waiting = [i for i in everything if (i["kind"], i["state"]) in {(k, s) for k, s, _, _ in WAITING}]
    out += ["", f"Items touched today: {prepared}.", "", "## Tomorrow's top three", ""]
    out += [f"{n}. {i['id']} {title(i)} ({i['state']})" for n, i in enumerate(waiting[:3], 1)] or ["1. nothing waiting"]
    return "\n".join(out)


def main() -> int:
    what = sys.argv[1]
    everything = every_item()
    w = world()
    state, field, make = {"brief": ("started", "brief", lambda d: brief(d, everything, w)),
                          "ledger": ("ended", "ledger", lambda d: ledger(d, everything))}[what]
    n = 0
    for day in [i for i in everything if i["kind"] == "day" and i["state"] == state]:
        date = day["id"].split("/")[1]
        path = OUTBOX / f"{what}-{date}.md"
        event(f"day.{'briefed' if what == 'brief' else 'recorded'}", day["id"], **{field: write_draft(day["id"], make(day), path)})
        if what == "brief":                           # the follow-ups it put in front of me
            for i in [i for i in everything if i["kind"] == "note" and i["state"] == "open"][:8]:
                event("note.briefed", i["id"], day=day["id"])
        n += 1
    moved(n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
