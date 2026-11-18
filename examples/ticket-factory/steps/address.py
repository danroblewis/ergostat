"""address: the agent answers the reviewers' comments with a change (prompts/review.md), committed and pushed,
and a reply on the pull request saying what was done. Back to review-asked: the reviewers look again."""

from pathlib import Path

import agent
import github
from act import act
from step import Move
from tf import key_of, now


def run(ticket):
    f = ticket["fields"]
    key, ws, repo, pr = key_of(ticket), Path(f["workspace"]), f["repo"], f["pr"]
    comments = f.get("comments") or []
    text = "\n\n".join(f"{c['who']}: {c['body']}" for c in comments)
    got = agent.run("review", ticket, ws, comments=text, comments_list=[c["body"] for c in comments])
    head = agent.commit(ws, f"{key}: answer the review") or f.get("head")
    if head != f.get("head"):
        act("github.push", key, "address", f"Push the answer to the review of #{pr}", github.push, ws, f["branch"],
            extra=head)
    act("github.comment", key, "address", f"Reply to the review on #{pr}", github.comment, repo, pr,
        f"Thanks. {got['said'].strip()[:1500]}" + (f"\n\nIn {head[:10]}." if head != f.get("head") else ""),
        extra=head + "|" + ",".join(c["id"] for c in comments))
    return Move({**agent.spent(got), "head": head, "answered": [c["id"] for c in comments], "comments": [],
                 "asked_at": now()})
