"""merge: once CI is green, merge (MERGE_METHOD) if MERGE=yes and the repository allows that method; otherwise,
or when the owner denies the merge (or its gate is deny), stop at approved: the ticket still moves on,
`merged: false`, and says why."""

import github
from gated import Denied, act
from step import Move
from tf import conf, now

ALLOWS = {"squash": "squashMergeAllowed", "merge": "mergeCommitAllowed", "rebase": "rebaseMergeAllowed"}


def run(ticket):
    f = ticket["fields"]
    repo, pr, method = f["repo"], f["pr"], conf("MERGE_METHOD", "squash")
    if conf("MERGE", "yes") != "yes":
        return Move({"merged": False, "merge_note": "MERGE=no: stopped at approved"})
    if not github.repo_settings(repo).get(ALLOWS.get(method, ""), False):
        return Move({"merged": False, "merge_note": f"{repo} does not allow {method} merges: stopped at approved"})
    try:
        act("pr-merge", repo=repo, pr=pr, method=method)
    except Denied as e:
        return Move({"merged": False, "merge_note": f"{e}: stopped at approved"})
    return Move({"merged": True, "merged_at": now()})
