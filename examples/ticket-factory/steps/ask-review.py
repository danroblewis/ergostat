"""ask-review: ask for a review: a review request to REVIEWERS, or, with none, a comment saying it is ready."""

from gated import act
from step import Move
from tf import conf, now


def run(ticket):
    f = ticket["fields"]
    reviewers = conf("REVIEWERS").replace(",", " ").split()
    if reviewers:
        act("request-review", repo=f["repo"], pr=f["pr"], reviewers=",".join(reviewers))
    else:
        act("pr-comment", repo=f["repo"], pr=f["pr"],
            body=f"Ready for review: {f.get('title', '')}. Comment here, or `{conf('APPROVE_WORD')}` when it is good.")
    return Move({"asked_at": now()})
