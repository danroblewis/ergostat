"""ask-review: ask for a review: a review request to REVIEWERS, or, with none, a comment saying it is ready."""

import github
from act import act
from step import Move
from tf import conf, key_of, now


def run(ticket):
    f = ticket["fields"]
    key, repo, pr = key_of(ticket), f["repo"], f["pr"]
    reviewers = conf("REVIEWERS").replace(",", " ").split()
    if reviewers:
        act("github.request-review", key, "ask-review", f"Ask {', '.join(reviewers)} to review #{pr}",
            github.request_review, repo, pr, reviewers)
    else:
        act("github.comment", key, "ask-review", f"Ask for a review on #{pr}", github.comment, repo, pr,
            f"Ready for review: {f.get('title', '')}. Comment here, or `{conf('APPROVE_WORD')}` when it is good.")
    return Move({"asked_at": now()})
