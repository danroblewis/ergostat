"""locate: which repository the issue names (a `repo: owner/name` line, or a GitHub link in its description),
else GITHUB_REPO; its clone (run/repo, the workspace pool's) made or fetched. The factory works in one
repository, GITHUB_REPO: an issue naming another stops, for the owner to decide (another repository is
another workspace pool, and the steps that use it)."""

import re

import github
from step import Move, Stop
from tf import conf


def run(ticket):
    text = ticket["fields"].get("description", "")
    named = re.findall(r"(?im)^\s*repo(?:sitory)?\s*:\s*([\w.-]+/[\w.-]+)", text)
    named += re.findall(r"github\.com/([\w.-]+/[\w.-]+?)(?:\.git|/|\s|$)", text)
    repo = named[0] if named else conf("GITHUB_REPO")
    if repo != conf("GITHUB_REPO"):
        return Stop(f"it names {repo}; the factory works only in {conf('GITHUB_REPO')} (GITHUB_REPO)")
    github.refresh(repo)
    return Move({"repo": repo, "repo_from": "the description" if named else "GITHUB_REPO"})
