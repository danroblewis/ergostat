"""The scripted teammate: the people outside the factory, for the demo (TEAMMATE=yes).

As the reviewer: TEAMMATE_AFTER after a pull request first waits for review, it writes a review asking for
one change; once the factory has answered it, it approves (a comment starting APPROVE_WORD: one GitHub
account cannot approve its own pull request). It only looks at the factory's own pull requests.

Offline only, as the owner: it approves each gated action held for approval (`ergostat actions ID --approve`),
so the offline demo runs through. Online, the owner approves.

Says how many pull requests it is looking at (the auxiliary team-reviewing).

    teammate.py serve    its daemon (factory/world.yaml): each run, every 5 seconds, handed to the one process
    teammate.py          one look, a process of its own (by hand)"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime

import github
from daemon import serve
from tf import OFFLINE, RUN, conf, items, read_json, record, run_ergostat, say, seconds, throttled, write_json, yes

ASK = ("Could the file also say which ticket it is for, with the ticket's link? "
       "(A scripted review by the ticket factory's teammate.)")


def when(iso: str) -> float:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() if iso else 0.0


def news(tid: str, what: str) -> None:
    """Offline, what GitHub's webhook would push at work (README, "Pushed, not polled"): news of the ticket, so the
    review step waiting on it looks again at once."""
    if OFFLINE:
        record("ticket.news", tid, {"news": f"github: {what}"}, by="github")


def look(_line=None) -> None:
    if not yes("TEAMMATE"):
        say({"value": 0})
        return
    mem = read_json(RUN / "teammate.json", {})
    looking = 0
    for t in items("ticket"):
        f = t["fields"]
        if t["state"] not in ("review-asked", "changes-asked") or not f.get("pr"):
            continue
        pr_key = f"{f['repo']}#{f['pr']}"
        m = mem.setdefault(pr_key, {"since": time.time(), "phase": 0})
        if m["phase"] == 0:
            looking += 1
            if time.time() - m["since"] >= seconds(conf("TEAMMATE_AFTER", "120s")):
                github.review_comment(f["repo"], f["pr"], ASK)
                m.update(phase=1, asked=time.time())
                news(t["id"], "a review asks for a change")
        elif m["phase"] == 1:
            looking += 1
            if throttled(f"teammate:{pr_key}"):
                continue
            p = github.pr(f["repo"], f["pr"])
            answered = [c for c in p.get("comments", []) if github.MARK in (c.get("body") or "")
                        and when(c.get("createdAt", "")) > m["asked"] - 1 and "Thanks." in (c.get("body") or "")]
            if answered:
                github.teammate_comment(f["repo"], f["pr"], f"{conf('APPROVE_WORD')} Looks good, thanks.")
                m.update(phase=2, approved=time.time())
                news(t["id"], "approved")
    write_json(RUN / "teammate.json", mem)
    if OFFLINE:                                          # the owner's stand-in: only ever offline
        for a in json.loads(run_ergostat("actions", "--json", "-n", "200"))["actions"]:
            if a["state"] == "requested":
                run_ergostat("actions", a["id"].split("/", 1)[1], "--approve", "--note", "the owner's offline stand-in")
    say({"value": looking})


def main() -> int:
    if sys.argv[1:] == ["serve"]:
        return serve(work=look)
    look()
    return 0


if __name__ == "__main__":
    sys.exit(main())
