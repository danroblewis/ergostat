"""The preparers (stand-ins): Prepare is the second verb. Each prepares one item waiting in one state: it writes a
draft for it into outbox/, records the item as prepared, and reports that it moved one.

    prepare.py ROLE      review-brief, pr-nudge, team-nudge, mention-triage, secret-ticket, alert-comment,
                         action-plan, ramp-brief, ci-plan, ticket-explain, doc-draft, update

ergostat starts a run for each item that reaches the state, while its goal is off (every review has a brief,
every alert a draft comment...), up to the block's pool at once; each run holds a lease on its item
($ERGOSTAT_ITEM: ergostat's SPEC §9.5), so no two runs prepare one item, and an item whose run stops or goes
silent is given back and taken again. My messages about the item that waited for the run come in its input:
"can wait" gives it back, not to be taken again for half a working day (a nack that does not count as an
attempt); anything else goes into its draft; each is answered. The draft is a file the item names (its page
shows it); the event moves the item on (review.briefed: requested → briefed), which ends the lease. It never
posts, comments, approves or runs anything: what is done with a draft is mine (the person blocks ask me)."""

from __future__ import annotations

import os
import sys
import time

import drafts
from job import DAY, GH, ROOT, draft_path, event, items, moved, world, write_draft

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


def notes(kind: str, item: str) -> tuple[bool, str | None]:
    """My messages about this item that waited for this run (ergostat gives them in the run's input, SPEC §12h):
    whether one said it can wait (the item is given back for half a working day), and the rest, to go into its
    draft. Every one is answered."""
    import json
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        msgs = json.loads(raw[raw.rfind("\n{") + 1:]).get("messages") or [] if raw.strip() else []
    except ValueError:
        msgs = []
    wait, said = False, []
    for m in msgs:
        mine = [i for i in m.get("items", []) if i == item]
        low = m["text"].lower()
        if not mine:
            answer(m, f"noted; it is about none of what I prepare now ({item})")
        elif "wait" in low or "later" in low or "tomorrow" in low:
            wait = True
            answer(m, f"left {item} for later, as you asked: its draft waits half a working day")
        else:
            said.append(m["text"])
            answer(m, f"your note is in the draft for {item}")
    return wait, "\n\n".join(said) or None


def answer(m: dict, says: str) -> None:
    import json
    print(json.dumps({"answer": {"message": m["id"], "says": says}}), flush=True)


def main() -> int:
    import json
    kind, state, moves, field = ROLES[sys.argv[1]]
    leased = os.environ.get("ERGOSTAT_ITEM")             # the item ergostat leased to this run (SPEC §9.5)
    waiting = items(kind, state) if not leased else [i for i in items(kind) if i["id"] == leased]
    if not waiting:                                       # by hand, with nothing waiting
        moved(0)
        return 0
    it = waiting[0]
    wait, said = notes(kind, it["id"])
    if wait:                                              # given back, not counted: taken again in half a day
        print(json.dumps({"nack": {"why": "the owner said it can wait", "after": f"{DAY / 2:g}s", "count": False}}))
        moved(0)
        return 0
    w = world()
    th = {**w.get("things", {}).get(kind, {}).get(it["id"], {}), **it["fields"]}
    if GH and kind in ("pr", "review") and "github.com" in th.get("url", ""):
        import codehost
        th.update(codehost.details(th["url"]))            # read only: gh pr view
    if kind == "update":
        text = drafts.update_draft(it, th, w, week_ledger(th.get("week_of", "")))
    else:
        text = drafts.DRAFTS[kind](it, th, w)
    if said:                                              # my note, kept with the draft
        text = text.rstrip() + f"\n\n## My note\n\n> {said}\n"
    extra = {"nudged": "yes"} if kind == "pr" else {}
    time.sleep(0.3)                                       # a stand-in's pass: an AI agent's would take seconds to minutes
    event(moves, it["id"], **{field: write_draft(it["id"], text, draft_path(it["id"])), **extra})
    moved(1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
