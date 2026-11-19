"""ci: watch CI on the pull request's head. Green: on to merge. Failed: to ci-failed, with the failing log,
for `fix-ci`. A repository with no CI is taken as green once five minutes pass with no run. While CI runs,
the ticket is given back and looked at again soon (step.py: Wait), at once when CI's result is pushed (README,
"Pushed, not polled")."""

import github
from step import Move, Wait
from tf import now


def run(ticket):
    f = ticket["fields"]
    got = github.checks(f["repo"], f["pr"], since=f.get("ci_since"))
    if got["state"] == "success":
        return Move({"ci_green_at": now()})
    if got["state"] == "failure":
        bad = [r for r in got["runs"] if r.get("conclusion") not in ("success", "skipped", "neutral")]
        log = github.failed_log(f["repo"], bad[0]["id"]) if bad else ""
        return Move({"ci_failures": 1, "ci_log": log[-4000:], "ci_failed_run": bad[0]["id"] if bad else None},
                    event="ticket.ci-failed", out="flow.ci-failing")
    if got["state"] == "none" and now() - float(f.get("sailed_at") or now()) > 300:
        return Move({"ci_green_at": now(), "ci_note": "no CI ran"})
    return Wait(f"CI is {got['state']}")
