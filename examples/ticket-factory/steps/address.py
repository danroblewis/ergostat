"""address: the agent answers the reviewers' comments with a change (prompts/review.md), in the ticket's
workspace, committed and pushed, and a reply on the pull request saying what was done. Back to review-asked:
the reviewers look again."""

import os
from pathlib import Path

import agent
from gated import act
from step import Move
from tf import key_of, now, once


def run(ticket):
    f = ticket["fields"]
    key, ws, repo, pr = key_of(ticket), Path(os.environ["ERGOSTAT_WORKSPACE"]), f["repo"], f["pr"]
    comments = f.get("comments") or []
    text = "\n\n".join(f"{c['who']}: {c['body']}" for c in comments)
    def answer():
        got = agent.run("review", ticket, ws, comments=text, comments_list=[c["body"] for c in comments])
        return {**got, "head": agent.commit(ws, f"{key}: answer the review") or f.get("head")}
    got = once(f"{key}.address." + ",".join(c["id"] for c in comments), answer)
    head = got["head"]
    if head != f.get("head"):
        act("git-push", _key=head)
    act("pr-comment", repo=repo, pr=pr, body=f"Thanks. {got['said'].strip()[:1500]}" + (
        f"\n\nIn {head[:10]}." if head != f.get("head") else ""))
    return Move({**agent.spent(got), "head": head, "answered": [c["id"] for c in comments], "comments": [],
                 "asked_at": now()})
