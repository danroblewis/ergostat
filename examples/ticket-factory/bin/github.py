"""GitHub: every call the factory makes to it, each in one function, through the gh command line (signed in
with `gh auth login`; GitHub Enterprise with GH_HOST). Offline, the same calls go to bin/fakes.py.

Writes (push, open_pr, comment, request_review, add_label, rerun, merge) are only ever made through
bin/act.py, under a gate; the AI agent never calls these, nor gh, nor git push.

    github.py pr REPO N | checks REPO N | repo REPO      read, for a person checking the setup
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import fakes
from tf import OFFLINE, conf, git

MARK = "<!-- ergostat ticket-factory -->"          # on everything the factory writes: whatever lacks it is a person's


class GitHubError(RuntimeError):
    pass


def _gh(*args: str) -> str:
    r = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise GitHubError(f"gh {' '.join(args[:3])}: {(r.stderr or r.stdout).strip()[:400]}")
    return r.stdout


def allowed(repo: str) -> None:
    if repo not in conf("GITHUB_REPOS").split():
        raise GitHubError(f"{repo} is not in GITHUB_REPOS: the factory works only in the repositories it is given")


def repo_settings(repo: str) -> dict:
    if OFFLINE:
        return fakes.gh_repo(repo)
    return json.loads(_gh("repo", "view", repo, "--json",
                          "mergeCommitAllowed,squashMergeAllowed,rebaseMergeAllowed,defaultBranchRef"))


def push(workspace: Path, branch: str) -> str:
    """The workspace's branch to the repository (git, but an act on GitHub all the same)."""
    git("push", "-q", "--force-with-lease", "origin", f"HEAD:refs/heads/{branch}", cwd=workspace)
    return git("rev-parse", "HEAD", cwd=workspace)


def find_pr(repo: str, branch: str) -> dict | None:
    if OFFLINE:
        return fakes.gh_find_pr(repo, branch)
    got = json.loads(_gh("pr", "list", "-R", repo, "--head", branch, "--state", "open", "--json", "number,url"))
    return got[0] if got else None


def open_pr(repo: str, branch: str, title: str, body: str, base: str) -> dict:
    allowed(repo)
    if (pr := find_pr(repo, branch)):
        return pr
    if OFFLINE:
        return fakes.gh_open_pr(repo, branch, title, body + "\n\n" + MARK, base)
    url = _gh("pr", "create", "-R", repo, "--head", branch, "--base", base, "--title", title,
              "--body", body + "\n\n" + MARK).strip().splitlines()[-1]
    return {"number": int(url.rsplit("/", 1)[1]), "url": url}


def comment(repo: str, pr: int, body: str) -> str:
    allowed(repo)
    if OFFLINE:
        fakes.gh_comment(repo, pr, body + "\n\n" + MARK)
        return "commented"
    return _gh("pr", "comment", str(pr), "-R", repo, "--body", body + "\n\n" + MARK).strip()


def request_review(repo: str, pr: int, reviewers: list[str]) -> str:
    allowed(repo)
    if OFFLINE:
        fakes.gh_request_review(repo, pr, reviewers)
        return "asked"
    return _gh("pr", "edit", str(pr), "-R", repo, "--add-reviewer", ",".join(reviewers)).strip()


def add_label(repo: str, pr: int, label: str) -> str:
    allowed(repo)
    if OFFLINE:
        fakes.gh_add_label(repo, pr, label)
        return f"labelled {label}"
    return _gh("pr", "edit", str(pr), "-R", repo, "--add-label", label).strip()


def pr(repo: str, number: int) -> dict:
    """The pull request now: its state, head, labels, reviews, comments, and reviewDecision."""
    if OFFLINE:
        return fakes.gh_pr(repo, number)
    return json.loads(_gh("pr", "view", str(number), "-R", repo, "--json",
                          "number,url,state,title,body,headRefName,headRefOid,labels,comments,reviews,"
                          "reviewDecision,mergeable,author"))


def checks(repo: str, number: int, since: float | None = None) -> dict:
    """CI on the pull request's head commit: {state: pending | success | failure | none, runs: [...]}. With
    `since` (a time), only runs started or run again after it: a run asked to run again is pending until then."""
    if OFFLINE:
        return fakes.gh_checks(repo, number)
    head = pr(repo, number)
    runs = json.loads(_gh("run", "list", "-R", repo, "--commit", head["headRefOid"], "--json",
                          "databaseId,status,conclusion,name,event,updatedAt"))
    runs = [{"id": r["databaseId"], "status": r["status"], "conclusion": r["conclusion"], "name": r["name"],
             "updated": _when(r.get("updatedAt"))} for r in runs if r.get("event") == "pull_request"]
    if since and runs and all(r["updated"] < since - 5 for r in runs):
        return {"state": "pending", "runs": runs}
    if not runs:
        return {"state": "none", "runs": []}
    if any(r["status"] != "completed" for r in runs):
        return {"state": "pending", "runs": runs}
    bad = [r for r in runs if r["conclusion"] not in ("success", "skipped", "neutral")]
    return {"state": "failure" if bad else "success", "runs": runs}


def _when(iso: str | None) -> float:
    from datetime import datetime
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() if iso else 0.0


def failed_log(repo: str, run_id: int) -> str:
    if OFFLINE:
        return fakes.gh_failed_log(repo, run_id)
    return _gh("run", "view", str(run_id), "-R", repo, "--log-failed")[-6000:]


def rerun(repo: str, run_id: int) -> str:
    allowed(repo)
    if OFFLINE:
        fakes.gh_rerun(repo, run_id)
        return "rerun"
    return _gh("run", "rerun", str(run_id), "-R", repo).strip() or "rerun"


def merge(repo: str, number: int, method: str) -> str:
    allowed(repo)
    if OFFLINE:
        fakes.gh_merge(repo, number, method)
        return "merged"
    return _gh("pr", "merge", str(number), "-R", repo, f"--{method}", "--delete-branch").strip() or "merged"


def close(repo: str, number: int, delete_branch: bool = True) -> str:
    allowed(repo)
    if OFFLINE:
        fakes.gh_close(repo, number, delete_branch)
        return "closed"
    return _gh("pr", "close", str(number), "-R", repo, *(["--delete-branch"] if delete_branch else [])).strip()


def delete_branch(repo: str, branch: str) -> str:
    """Delete a branch the factory pushed (bin/demo_issues.py cleanup); gone already is fine."""
    allowed(repo)
    if OFFLINE:
        return "deleted"
    r = subprocess.run(["gh", "api", "-X", "DELETE", f"repos/{repo}/git/refs/heads/{branch}"], capture_output=True, text=True)
    return "deleted" if r.returncode == 0 else "not there"


def open_prs(repo: str) -> list[dict]:
    if OFFLINE:
        return fakes.gh_open_prs(repo)
    return json.loads(_gh("pr", "list", "-R", repo, "--state", "open", "--json", "number,labels,headRefName",
                          "--limit", "200"))


def review_comment(repo: str, number: int, body: str) -> str:
    """A review with a comment: the scripted teammate's (bin/teammate.py), never the factory's."""
    allowed(repo)
    if OFFLINE:
        fakes.gh_review_comment(repo, number, body)
        return "reviewed"
    return _gh("pr", "review", str(number), "-R", repo, "--comment", "--body", body).strip() or "reviewed"


def teammate_comment(repo: str, number: int, body: str) -> str:
    """A plain comment by the scripted teammate (no factory mark: it is a person's)."""
    allowed(repo)
    if OFFLINE:
        fakes.gh_comment(repo, number, body, author="teammate")
        return "commented"
    return _gh("pr", "comment", str(number), "-R", repo, "--body", body).strip()


def from_people(entries: list[dict]) -> list[dict]:
    """The comments and reviews a person wrote: everything the factory did not (it marks its own)."""
    return [e for e in entries if MARK not in (e.get("body") or "")]


if __name__ == "__main__":
    what = sys.argv[1:]
    fn = {"pr": pr, "checks": checks, "repo": repo_settings}[what[0]]
    print(json.dumps(fn(what[1], *[int(x) for x in what[2:]]), indent=1))
