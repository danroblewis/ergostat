"""review: wait for the reviewers. Each comment or review a person wrote (whatever the factory did not mark as
its own) that is not answered yet: an approval (a review that approves, or a comment starting APPROVE_WORD)
moves the ticket to approved; anything else to changes-asked, for `address`. No answer within REPING_AFTER of
asking: ask again, at most REPING_MAX times (each one counted in `repings`). While it waits, the ticket is
given back and looked at again soon (step.py: Wait), at once when a review is pushed (README, "Pushed, not
polled"), and when the re-ping falls due."""

import github
from gated import act
from step import Move, Wait
from tf import conf, now, seconds


def entries(p):
    out = []
    for e in github.from_people(p.get("comments", []) + p.get("reviews", [])):
        when = e.get("createdAt") or e.get("submittedAt") or ""
        who = (e.get("author") or {}).get("login", "?")
        out.append({"id": str(e.get("id") or f"{who}@{when}"), "who": who, "when": when,
                    "body": (e.get("body") or "").strip(), "state": e.get("state", "")})
    return sorted(out, key=lambda e: e["when"])


def approves(e):
    return e["state"] == "APPROVED" or e["body"].lower().startswith(conf("APPROVE_WORD").lower())


def run(ticket):
    f = ticket["fields"]
    repo, pr = f["repo"], f["pr"]
    p = github.pr(repo, pr)
    if p["state"] != "OPEN":
        return Wait(f"#{pr} is {p['state'].lower()}")
    new = [e for e in entries(p) if e["id"] not in set(f.get("answered", [])) and (e["body"] or e["state"])]
    if p.get("reviewDecision") == "APPROVED" or any(approves(e) for e in new):
        later = [e for e in new if not approves(e)]
        return Move({"approved_at": now(), "answered": [e["id"] for e in new], "approval_notes": [e["body"] for e in later]})
    if new:
        return Move({"comments": new, "review_rounds": 1}, event="ticket.changes-asked",
                    out="flow.review-changes")
    waited = now() - float(f.get("asked_at") or now())
    n = int(f.get("repings") or 0)
    if waited < seconds(conf("REPING_AFTER", "90s")):
        return Wait(f"no answer yet ({waited:.0f}s)", due=seconds(conf("REPING_AFTER", "90s")) - waited)
    if n >= int(conf("REPING_MAX", "3")):
        return Wait(f"no answer after {n} re-pings")
    act("pr-comment", repo=repo, pr=pr, body=f"Friendly re-ping ({n + 1}): this is waiting for a review." + (
        " " + " ".join("@" + r for r in conf("REVIEWERS").replace(",", " ").split()) if conf("REVIEWERS") else ""))
    return Wait("re-pinged", {"repings": 1, "asked_at": now()})
