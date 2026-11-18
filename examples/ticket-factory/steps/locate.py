"""locate: which repository the issue names (a `repo: owner/name` line, or a GitHub link in its description),
else GITHUB_REPO. Only the repositories in GITHUB_REPOS are worked in: one it names that is not there stops
the ticket, for the owner to decide."""

import re

from step import Move, Stop
from tf import conf


def run(ticket):
    text = ticket["fields"].get("description", "")
    named = re.findall(r"(?im)^\s*repo(?:sitory)?\s*:\s*([\w.-]+/[\w.-]+)", text)
    named += re.findall(r"github\.com/([\w.-]+/[\w.-]+?)(?:\.git|/|\s|$)", text)
    repo = named[0] if named else conf("GITHUB_REPO")
    if repo not in conf("GITHUB_REPOS").split():
        return Stop(f"it names {repo}, which is not in GITHUB_REPOS")
    return Move({"repo": repo, "repo_from": "the description" if named else "GITHUB_REPO"})
