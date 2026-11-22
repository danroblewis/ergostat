"""Offline stand-ins for Jira and GitHub, kept in run/fake/ as JSON, so the whole workflow runs with no
account and no network (scripts/demo_check.py, a fresh copy). They answer the same calls as bin/jira.py and
bin/github.py, with the same shapes. The repository is real git: a bare repository in run/ plays GitHub's
copy, pushes go to it, and its CI runs the sample repository's own check (every work/*.txt has something
in it) on the pushed commit.

Issues arrive on their own: three at first, then one every 20 seconds, up to eight.
"""

from __future__ import annotations

import fcntl
import json
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

from tf import RUN, SCRATCH, conf, git

FAKE = RUN / "fake"
STATUSES = {"To Do": ["In Progress"], "In Progress": ["In Review", "Done", "To Do"], "In Review": ["Done", "In Progress"],
            "Done": ["To Do"]}
ARRIVE_EVERY = 20.0
FIRST, MOST = 3, 8
TITLES = ["Say hello in Portuguese", "Add a line about the weather", "Write a limerick about queues",
          "Note today's date in words", "Greet the new teammate", "List three prime numbers",
          "Describe a stock and a flow in one sentence", "Thank the reviewers"]


@contextmanager
def _state(name: str):
    FAKE.mkdir(parents=True, exist_ok=True)
    with open(FAKE / f"{name}.lock", "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        path = FAKE / f"{name}.json"
        data = json.loads(path.read_text()) if path.exists() else {}
        yield data
        path.write_text(json.dumps(data, indent=1))


# --- Jira -----------------------------------------------------------------------------------------

def _issues(j: dict) -> dict:
    """The fake board, moved on to now: issues arrive on their own."""
    if "started" not in j:
        j.update(started=time.time(), issues={}, made=0)
    want = min(MOST, FIRST + int((time.time() - j["started"]) / ARRIVE_EVERY))
    while j["made"] < want:
        j["made"] += 1
        key = f"{conf('JIRA_PROJECT', 'SCRUM')}-{j['made']}"
        title = TITLES[(j["made"] - 1) % len(TITLES)]
        j["issues"][key] = {"key": key, "summary": title, "status": "To Do", "labels": [conf("JIRA_LABEL")],
                            "description": f"{title}.\n\nrepo: {conf('GITHUB_REPO')}", "comments": [],
                            "created": time.time(), "issuelinks": _links_made(j["made"])}
    return j["issues"]


def _links_made(n: int) -> list[dict]:
    """The second issue waits on the first (a Blocks link, as Jira gives it on the blocked side): a blocked ticket."""
    if n != 2:
        return []
    return [{"type": {"name": "Blocks", "inward": "is blocked by", "outward": "blocks"},
             "inwardIssue": {"key": f"{conf('JIRA_PROJECT', 'SCRUM')}-1"}}]


def _issue_out(i: dict) -> dict:
    return {**{k: i[k] for k in ("key", "summary", "status", "labels", "description")},
            "url": f"{conf('JIRA_URL')}/browse/{i['key']}"}


def jira_waiting() -> list[dict]:
    with _state("jira") as j:
        return [_issue_out(i) for i in _issues(j).values()
                if i["status"] == conf("JIRA_PICK_FROM") and conf("JIRA_LABEL") in i["labels"]]


def jira_counts() -> dict[str, int]:
    with _state("jira") as j:
        out: dict[str, int] = {}
        for i in _issues(j).values():
            out[i["status"]] = out.get(i["status"], 0) + 1
        return out


def jira_linked() -> dict[str, dict]:
    """The labelled issues' raw issuelinks and parent, as Jira's search answers them (jira.links() reads them)."""
    with _state("jira") as j:
        return {k: {f: i[f] for f in ("issuelinks", "parent") if f in i}
                for k, i in _issues(j).items() if conf("JIRA_LABEL") in i["labels"]}


def jira_get(key: str) -> dict:
    with _state("jira") as j:
        return _issue_out(_issues(j)[key])


def jira_transitions(key: str) -> list[dict]:
    with _state("jira") as j:
        st = _issues(j)[key]["status"]
    return [{"id": str(n), "name": f"to {to}", "to": to} for n, to in enumerate(STATUSES.get(st, []), 11)]


def jira_transition(key: str, transition_id: str) -> None:
    to = {t["id"]: t["to"] for t in jira_transitions(key)}[transition_id]
    with _state("jira") as j:
        _issues(j)[key]["status"] = to


def jira_comment(key: str, text: str) -> None:
    with _state("jira") as j:
        _issues(j)[key]["comments"].append({"body": text, "time": time.time()})


# --- GitHub ---------------------------------------------------------------------------------------

def origin(repo: str) -> Path:
    """The fake GitHub's copy of a repository: a bare repository, made with the sample's content the first
    time it is asked for."""
    bare = SCRATCH / "origin" / (repo.replace("/", "__") + ".git")
    if not bare.exists():
        seed = SCRATCH / "origin" / "seed"
        seed.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q", "-b", "main", str(seed)], check=True)
        (seed / "README.md").write_text("# sample\n\nA stand-in for the sample repository.\n")
        (seed / "greeting.txt").write_text("hello\n")
        (seed / "work").mkdir(exist_ok=True)
        (seed / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
        (seed / ".github" / "workflows" / "ci.yml").write_text(
            "name: ci\non: pull_request\njobs:\n  check:\n    runs-on: ubuntu-latest\n    steps:\n"
            "      - uses: actions/checkout@v4\n      - run: for f in work/*.txt; do test -s \"$f\"; done\n")
        git("add", "-A", cwd=seed)
        git("commit", "-qm", "the sample", cwd=seed)
        subprocess.run(["git", "clone", "-q", "--bare", str(seed), str(bare)], check=True)
        subprocess.run(["rm", "-rf", str(seed)], check=True)
    return bare


def _head(repo: str, branch: str) -> str | None:
    r = subprocess.run(["git", "rev-parse", f"refs/heads/{branch}"], cwd=origin(repo), capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def _ci(repo: str, sha: str) -> tuple[bool, str]:
    """The sample's check, on the commit pushed: every work/*.txt has something in it."""
    tree = subprocess.run(["git", "ls-tree", "-r", "-l", sha], cwd=origin(repo), capture_output=True, text=True).stdout
    empty = [ln.split("\t")[1] for ln in tree.splitlines()
             if "\t" in ln and ln.split("\t")[1].startswith("work/") and ln.split("\t")[1].endswith(".txt")
             and ln.split()[3] == "0"]
    if empty:
        return False, "".join(f'check\tRun for f in work/*.txt\t+ test -s {f}\ncheck\tRun for f in work/*.txt\t'
                              f'##[error]Process completed with exit code 1.\n' for f in empty)
    return True, ""


def gh_repo(repo: str) -> dict:
    return {"mergeCommitAllowed": True, "squashMergeAllowed": True, "rebaseMergeAllowed": True,
            "defaultBranchRef": {"name": "main"}}


def gh_find_pr(repo: str, branch: str) -> dict | None:
    with _state("github") as g:
        for p in g.get("prs", {}).values():
            if p["repo"] == repo and p["branch"] == branch and p["state"] == "OPEN":
                return {"number": p["number"], "url": p["url"]}
    return None


def gh_open_pr(repo: str, branch: str, title: str, body: str, base: str) -> dict:
    with _state("github") as g:
        prs = g.setdefault("prs", {})
        n = len(prs) + 1
        prs[str(n)] = {"number": n, "repo": repo, "branch": branch, "title": title, "body": body, "base": base,
                       "state": "OPEN", "labels": [], "comments": [], "reviews": [], "reviewers": [],
                       "url": f"https://github.invalid/{repo}/pull/{n}", "created": time.time()}
        return {"number": n, "url": prs[str(n)]["url"]}


def gh_comment(repo: str, pr: int, body: str, author: str = "me") -> None:
    with _state("github") as g:
        g["prs"][str(pr)]["comments"].append({"author": {"login": author}, "body": body,
                                              "createdAt": _iso(time.time())})


def gh_review_comment(repo: str, pr: int, body: str, author: str = "teammate") -> None:
    with _state("github") as g:
        g["prs"][str(pr)]["reviews"].append({"author": {"login": author}, "body": body, "state": "COMMENTED",
                                             "submittedAt": _iso(time.time())})


def gh_request_review(repo: str, pr: int, reviewers: list[str]) -> None:
    with _state("github") as g:
        g["prs"][str(pr)]["reviewers"] += reviewers


def gh_add_label(repo: str, pr: int, label: str) -> None:
    with _state("github") as g:
        if label not in g["prs"][str(pr)]["labels"]:
            g["prs"][str(pr)]["labels"].append(label)


def gh_pr(repo: str, pr: int) -> dict:
    with _state("github") as g:
        p = dict(g["prs"][str(pr)])
    return {"number": p["number"], "url": p["url"], "state": p["state"], "title": p["title"], "body": p["body"],
            "headRefName": p["branch"], "headRefOid": _head(repo, p["branch"]) or "",
            "labels": [{"name": n} for n in p["labels"]], "comments": p["comments"], "reviews": p["reviews"],
            "reviewDecision": "", "mergeable": "MERGEABLE", "author": {"login": "me"}}


def gh_checks(repo: str, pr: int) -> dict:
    """The CI run on the pull request's head: pending for 3 seconds after a push, then its result."""
    with _state("github") as g:
        p = g["prs"][str(pr)]
        sha = _head(repo, p["branch"])
        runs = g.setdefault("runs", {})
        if sha not in runs:
            runs[sha] = {"id": len(runs) + 1, "started": time.time(), "sha": sha}
        r = runs[sha]
        if time.time() - r["started"] < 3:
            return {"state": "pending", "runs": [{"id": r["id"], "status": "in_progress", "conclusion": ""}]}
        ok, log = _ci(repo, sha)
        r["log"] = log
        return {"state": "success" if ok else "failure",
                "runs": [{"id": r["id"], "status": "completed", "conclusion": "success" if ok else "failure"}]}


def gh_failed_log(repo: str, run_id: int) -> str:
    with _state("github") as g:
        for r in g.get("runs", {}).values():
            if r["id"] == run_id:
                return r.get("log", "")
    return ""


def gh_rerun(repo: str, run_id: int) -> None:
    with _state("github") as g:
        for r in g.get("runs", {}).values():
            if r["id"] == run_id:
                r["started"] = time.time()


def gh_merge(repo: str, pr: int, method: str) -> None:
    with _state("github") as g:
        p = g["prs"][str(pr)]
        p["state"] = "MERGED"
    subprocess.run(["git", "update-ref", "refs/heads/main", _head(repo, p["branch"])], cwd=origin(repo), check=True)


def gh_close(repo: str, pr: int, delete_branch: bool) -> None:
    with _state("github") as g:
        g["prs"][str(pr)]["state"] = "CLOSED"


def gh_open_prs(repo: str) -> list[dict]:
    with _state("github") as g:
        return [{"number": p["number"], "labels": [{"name": n} for n in p["labels"]], "headRefName": p["branch"]}
                for p in g.get("prs", {}).values() if p["repo"] == repo and p["state"] == "OPEN"]


def _iso(t: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))
