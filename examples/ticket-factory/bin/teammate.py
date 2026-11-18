"""The scripted teammate: the people outside the factory, for the demo (TEAMMATE=yes).

As the reviewer: TEAMMATE_AFTER after a pull request first waits for review, it writes a review asking for
one change; once the factory has answered it, it approves (a comment starting APPROVE_WORD: one GitHub
account cannot approve its own pull request). It only looks at the factory's own pull requests.

Offline only, as the owner: it approves each gated action that has waited four seconds, so the offline demo
runs through. Online, the owner approves (bin/act.py).

Prints how many pull requests it is looking at (the auxiliary team-reviewing)."""

from __future__ import annotations

import sys
import time
from datetime import datetime

import github
from tf import OFFLINE, RUN, conf, items, read_json, record, seconds, write_json, yes

ASK = ("Could the file also say which ticket it is for, with the ticket's link? "
       "(A scripted review by the ticket factory's teammate.)")


def when(iso: str) -> float:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() if iso else 0.0


def main() -> int:
    if not yes("TEAMMATE"):
        print(0)
        return 0
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
        elif m["phase"] == 1:
            looking += 1
            p = github.pr(f["repo"], f["pr"])
            answered = [c for c in p.get("comments", []) if github.MARK in (c.get("body") or "")
                        and when(c.get("createdAt", "")) > m["asked"] - 1 and "Thanks." in (c.get("body") or "")]
            if answered:
                github.teammate_comment(f["repo"], f["pr"], f"{conf('APPROVE_WORD')} Looks good, thanks.")
                m.update(phase=2, approved=time.time())
    write_json(RUN / "teammate.json", mem)
    if OFFLINE:                                          # the owner's stand-in: only ever offline
        for a in items("action", "requested"):
            if time.time() - float(a.get("entered") or 0) > 4:
                record("action.approved", a["id"], {"approved_by": "owner (offline stand-in)"}, by="owner")
    print(looking)
    return 0


if __name__ == "__main__":
    sys.exit(main())
