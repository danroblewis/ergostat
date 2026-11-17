"""The preparers (stand-ins): Prepare is the second verb. Each takes the items waiting in one state, oldest first,
writes a draft for each into outbox/, records the item as prepared, and reports how many it moved.

    prepare.py ROLE      review-brief, pr-nudge, team-nudge, mention-triage, secret-ticket, alert-comment,
                         action-plan, ramp-brief, ci-plan, ticket-explain, doc-draft, update

ergostat runs one while its goal is off (every review has a brief, every alert a draft comment...),
with at most `max` items a run. My messages about its items that waited for the run come in its input:
"can wait" puts an item off half a working day, "first" prepares it first, anything else goes into its draft;
each is answered. The draft is a file the item names (its page shows it); the event
moves the item on (review.briefed: requested → briefed). It never posts, comments, approves or runs
anything: what is done with a draft is mine (the person blocks ask me)."""

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


DEFER = ROOT / "run" / "watch" / "deferred.json"


def notes(kind: str, waiting: list[dict]) -> tuple[list[dict], dict[str, str]]:
    """My messages about this work that waited for this run (ergostat gives them in the run's input, SPEC §12h):
    "can wait" puts an item back half a working day, "first" puts it first; every one is answered, and the rest
    are written into the item's draft. Returns the items in the order to prepare them, and the notes by item."""
    import json
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        msgs = json.loads(raw[raw.rfind("\n{") + 1:]).get("messages") or [] if raw.strip() else []
    except ValueError:
        msgs = []
    deferred = json.loads(DEFER.read_text()) if DEFER.exists() else {}
    now = time.time()
    order = [it["id"] for it in waiting]
    said: dict[str, str] = {}
    for m in msgs:
        mine = [i for i in m.get("items", []) if i.split("/")[0] == kind]
        low = m["text"].lower()
        if not mine:
            answer(m, "noted; it is about none of the items I prepare")
            continue
        for i in mine:
            if "wait" in low or "later" in low or "tomorrow" in low:
                deferred[i] = now + DAY / 2
                answer(m, f"left {i} for later, as you asked: its draft waits half a working day")
            elif "first" in low and i in order:
                order.remove(i)
                order.insert(0, i)
                answer(m, f"prepared {i} first, as you asked")
            else:
                said[i] = m["text"]
                answer(m, f"your note is in the draft for {i}")
    DEFER.parent.mkdir(parents=True, exist_ok=True)
    DEFER.write_text(json.dumps({k: v for k, v in deferred.items() if v > now}))
    by = {it["id"]: it for it in waiting}
    return [by[i] for i in order if deferred.get(i, 0) <= now], said


def answer(m: dict, says: str) -> None:
    import json
    print(json.dumps({"answer": {"message": m["id"], "says": says}}), flush=True)


def main() -> int:
    kind, state, moves, field = ROLES[sys.argv[1]]
    most = max(1, int(float(os.environ.get("ERGOSTAT_COMMAND") or 1)))      # what it was asked for, within its max
    w = world()
    things = w.get("things", {}).get(kind, {})
    done = 0
    todo, said = notes(kind, items(kind, state))
    for it in todo[:most]:
        th = {**things.get(it["id"], {}), **it["fields"]}
        if GH and kind in ("pr", "review") and "github.com" in th.get("url", ""):
            import codehost
            th.update(codehost.details(th["url"]))      # read only: gh pr view
        if kind == "update":
            text = drafts.update_draft(it, th, w, week_ledger(th.get("week_of", "")))
        else:
            text = drafts.DRAFTS[kind](it, th, w)
        if it["id"] in said:                                # my note, kept with the draft
            text = text.rstrip() + f"\n\n## My note\n\n> {said[it['id']]}\n"
        extra = {"nudged": "yes"} if kind == "pr" else {}
        event(moves, it["id"], **{field: write_draft(it["id"], text, draft_path(it["id"])), **extra})
        done += 1
        time.sleep(0.3)                      # a stand-in's pass: an AI agent's would take seconds to minutes
    moved(done)
    return 0


if __name__ == "__main__":
    sys.exit(main())
