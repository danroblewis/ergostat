"""The code host, for real (JOB_GH=1): my own open PRs and the reviews asked of me, read from GitHub with `gh`.

Read only, by construction: gh() refuses anything but `gh search prs` and `gh pr view`, the two
read-only commands this needs, and runs them with your own sign-in (`gh auth login`, once). Nothing
is ever posted, commented, approved or merged. It polls at most every JOB_GH_EVERY seconds
(default 120), and a working day here is JOB_GH_DAY seconds (default 86400: a real day), so a
review is late a day after it was first seen, and a PR of mine stale a day after it was opened.

The rest of the job (chat, the pager, flags, ...) stays simulated."""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import time

from job import event

READ_ONLY = {("search", "prs"), ("pr", "view")}
EVERY = float(os.environ.get("JOB_GH_EVERY", "120"))
DAY = float(os.environ.get("JOB_GH_DAY", "86400"))
FIELDS = "number,title,url,repository,createdAt,author"


def gh(*args: str):
    if tuple(args[:2]) not in READ_ONLY:
        raise SystemExit(f"refused: gh {' '.join(args[:2])} is not one of the read-only commands this may run")
    p = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        raise SystemExit(f"gh {' '.join(args[:2])}: {p.stderr.strip()[:200]}")
    return json.loads(p.stdout or "null")


def item_id(kind: str, pr: dict) -> str:
    return f"{kind}/{pr['repository']['nameWithOwner'].replace('/', '-')}-{pr['number']}".lower()


def created(pr: dict) -> float:
    return dt.datetime.fromisoformat(pr["createdAt"].replace("Z", "+00:00")).timestamp()


def details(url: str) -> dict:
    """What a brief or a nudge is drafted from: the PR's files, size and reviewers."""
    v = gh("pr", "view", url, "--json", "files,additions,deletions,author,reviewRequests")
    return {"files": [f["path"] for f in v.get("files") or []][:12], "additions": v.get("additions", 0),
            "deletions": v.get("deletions", 0), "author": (v.get("author") or {}).get("login", ""),
            "reviewers": [r.get("login") or r.get("name") or "" for r in v.get("reviewRequests") or []]}


def watch(kind: str, mem: dict) -> None:
    now = time.time()
    mem.setdefault("arrivals", [])
    if now - mem.get("polled", 0) >= EVERY:
        mem["polled"] = now
        (mine if kind == "pr" else asked)(mem, now)
    mem["arrivals"] = [t for t in mem["arrivals"] if t > now - 600]


def mine(mem: dict, now: float) -> None:
    """My open PRs: new ones opened; a first review; stale after a day without one, late after two; merged or closed."""
    known = mem.setdefault("open", {})
    seen = {}
    for pr in gh("search", "prs", "--author=@me", "--state=open", "--json", FIELDS, "--limit", "50") or []:
        id = item_id("pr", pr)
        seen[id] = known.get(id) or {"url": pr["url"], "t": created(pr), "flags": []}
        if id not in known:
            event("pr.opened", id, title=pr["title"], repo=pr["repository"]["nameWithOwner"], url=pr["url"], nudged="no")
            mem["arrivals"].append(now)
    for id, k in seen.items():
        if "reviewed" in k["flags"]:
            continue
        reviews = gh("pr", "view", k["url"], "--json", "reviews").get("reviews") or []
        if reviews:
            k["flags"].append("reviewed")
            event("pr.reviewed", id, reviewer=(reviews[0].get("author") or {}).get("login", ""),
                  verdict=reviews[0].get("state", "").lower())
            continue
        for flag, after, what in (("stale", 1, "pr.stale"), ("late", 2, "pr.late")):
            if flag not in k["flags"] and now - k["t"] > after * DAY:
                k["flags"].append(flag)
                event(what, id, **({"late": "yes"} if flag == "late" else {}))
    for id, k in known.items():
        if id not in seen:
            v = gh("pr", "view", k["url"], "--json", "state")
            event("pr.merged" if v.get("state") == "MERGED" else "pr.closed", id)
    mem["open"] = seen


def asked(mem: dict, now: float) -> None:
    """Reviews asked of me: new requests; late a day after first seen; answered once the request is gone."""
    known = mem.setdefault("asked", {})
    seen = {}
    for pr in gh("search", "prs", "--review-requested=@me", "--state=open", "--json", FIELDS, "--limit", "50") or []:
        id = item_id("review", pr)
        seen[id] = known.get(id) or {"url": pr["url"], "t": now, "flags": []}
        if id not in known:
            event("review.requested", id, title=pr["title"], author=(pr.get("author") or {}).get("login", ""),
                  repo=pr["repository"]["nameWithOwner"], url=pr["url"])
            mem["arrivals"].append(now)
        if "late" not in seen[id]["flags"] and now - seen[id]["t"] > DAY:
            seen[id]["flags"].append("late")
            event("review.late", id, late="yes")
    for id in known:
        if id not in seen:
            event("review.answered", id)               # I reviewed it (or the request was withdrawn)
    mem["asked"] = seen
