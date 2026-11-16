"""The preparers (stand-ins): Prepare is the second verb. Each takes the items waiting in one state, oldest first,
writes a draft for each into outbox/, records the item as prepared, and reports how many it moved.

    prepare.py ROLE      review-brief, pr-nudge, team-nudge, mention-triage, secret-ticket, alert-comment,
                         action-plan, ramp-brief, ci-plan, ticket-explain, doc-draft, update

ergostat runs one while its goal is off (every review has a brief, every alert a draft comment...),
with at most `max` items a run. The draft is a file the item names (its page shows it); the event
moves the item on (review.briefed: requested → briefed). It never posts, comments, approves or runs
anything: what is done with a draft is mine (the person blocks ask me)."""

from __future__ import annotations

import os
import sys
import time

import drafts
from job import GH, ROOT, draft_path, event, items, moved, world, write_draft

# role: (kind, the state it prepares, the event that moves it on, the field naming the draft)
ROLES = {
    "review-brief": ("review", "requested", "review.briefed", "brief"),
    "pr-nudge": ("pr", "stale", "pr.nudge-drafted", "nudge"),
    "team-nudge": ("team-pr", "stale", "team-pr.nudge-drafted", "nudge"),
    "mention-triage": ("mention", "new", "mention.triaged", "reply"),
    "secret-ticket": ("secret", "expiring", "secret.ticket-drafted", "ticket"),
    "alert-comment": ("alert", "fired", "alert.drafted", "comment"),
    "action-plan": ("action", "open", "action.planned", "plan"),
    "ramp-brief": ("ramp", "pending", "ramp.briefed", "brief"),
    "ci-plan": ("ci", "released", "ci.planned", "plan"),
    "ticket-explain": ("ticket", "new", "ticket.explained", "explanation"),
    "doc-draft": ("doc", "needed", "doc.drafted", "draft"),
    "update": ("update", "due", "update.drafted", "draft"),
}


def week_ledger(since: str) -> str:
    """The ledger's lines since a date: what the weekly update is built from."""
    lines = []
    for p in sorted((ROOT / "outbox").glob("ledger-*.md")):
        if p.stem.removeprefix("ledger-") >= since:
            lines += [x for x in p.read_text().splitlines() if x.startswith("- ")][:6]
    return "\n".join(lines[:15])


def main() -> int:
    kind, state, moves, field = ROLES[sys.argv[1]]
    most = max(1, int(float(os.environ.get("ERGOSTAT_COMMAND") or 1)))      # what it was asked for, within its max
    w = world()
    things = w.get("things", {}).get(kind, {})
    done = 0
    for it in items(kind, state)[:most]:
        th = {**things.get(it["id"], {}), **it["fields"]}
        if GH and kind in ("pr", "review") and "github.com" in th.get("url", ""):
            import codehost
            th.update(codehost.details(th["url"]))      # read only: gh pr view
        if kind == "update":
            text = drafts.update_draft(it, th, w, week_ledger(th.get("week_of", "")))
        else:
            text = drafts.DRAFTS[kind](it, th, w)
        extra = {"nudged": "yes"} if kind == "pr" else {}
        event(moves, it["id"], **{field: write_draft(it["id"], text, draft_path(it["id"])), **extra})
        done += 1
        time.sleep(0.3)                      # a stand-in's pass: an AI agent's would take seconds to minutes
    moved(done)
    return 0


if __name__ == "__main__":
    sys.exit(main())
