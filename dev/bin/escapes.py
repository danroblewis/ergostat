"""Escapes found on main: a step of `upgrade.py watch` (the block main-watch) that reads the commits pushed to main for
reverts (`This reverts commit <sha>`, as `git revert` writes) and records each as an escape (dev/bin/risk.py).

It walks `git rev-list --first-parent` from the last commit it read (run/escapes.json) to the pushed main, oldest
first, at most MOST commits a run (said when there are more: the rest at the next run, none skipped). A reverted commit
is matched to a merged gap first by its second parent being the gap's reviewed_head (the queue merges that commit with
--no-ff), then by its being the gap's main_sha, which a batch's gaps share, so it names a gap only when exactly one
carries it. A match says gap.reverted (reverted, revert_sha, reverted_at) unless the gap is reverted already; no
match says intervention.recorded as intervention/reverted-<sha12> (class reverted-unmatched), which risk.py counts as
an escape at the pool size then, unless that intervention exists. So a second read records nothing twice. A revert of
a revert puts the work back: not an escape."""

from __future__ import annotations

import fcntl
import json
import re
import sys
import time
from pathlib import Path

import fac

MOST = 200                                             # commits read a run
REVERTS = re.compile(r"This reverts commit ([0-9a-f]{7,64})")


def blamed(gaps: list[dict], sha: str, parents: list[str]) -> dict | None:
    """The one merged gap whose merge `sha` is: its second parent the gap's reviewed_head, else its main_sha."""
    merged = [g for g in gaps if g["state"] == "merged"]
    for field, want in (("reviewed_head", parents[1:2]), ("main_sha", [sha])):
        hit = [g for g in merged if want and str(g["fields"].get(field) or "") == want[0]]
        if len(hit) == 1:
            return hit[0]
    return None


def record(repo: Path, gaps: list[dict], ivs: set[str], revert: str, old: str) -> list[str]:
    """The revert commit `revert` of `old` recorded once: the item it was said of, or nothing when said already."""
    head, _, body = fac.git(repo, "log", "-1", "--format=%H %P%x00%B", f"{old}^{{commit}}", check=False).partition("\0")
    got = head.split()                                 # (a commit not in the checkout: unmatched, still an escape)
    if REVERTS.search(body):
        return []
    sha, now = got[0] if got else old, time.time()
    g = blamed(gaps, sha, got[1:])
    if g:
        if g["fields"].get("reverted"):
            return []
        g["fields"]["reverted"] = True                 # (two reverts of it in one read: recorded once)
        fac.say("gap.reverted", g["id"], reverted=True, revert_sha=revert, reverted_at=now, reverted_commit=sha)
        return [g["id"]]
    iid = f"intervention/reverted-{sha[:12]}"
    if iid in ivs:
        return []
    ivs.add(iid)
    fac.say("intervention.recorded", iid, recorded_at=now, revert_sha=revert, reverted_commit=sha,
            reason=f"main {revert[:12]} reverts {sha[:12]}, the merge of no one gap the record names: an escape "
                   "counted at the pool size then", **{"class": "reverted-unmatched"})
    return [iid]


def watch(cfg: dict, repo: Path, main: str) -> list[str]:
    """Reverts on main since the last commit read, up to `main` (the pushed main), recorded; the items said of."""
    run = fac.run_dir(cfg)
    with open(run / "escapes.lock", "w") as lk:        # held across the read, the records and the new last commit
        fcntl.flock(lk, fcntl.LOCK_EX)
        p = run / "escapes.json"
        last = str(json.loads(p.read_text()).get("last") or "") if p.exists() else ""
        if last and not fac.git_ok(repo, "cat-file", "-e", f"{last}^{{commit}}"):
            print(f"escapes: {last[:12]} is not in the checkout: main read again from its start", file=sys.stderr)
            last = ""
        shas = fac.git(repo, "rev-list", "--first-parent", "--reverse", f"{last}..{main}" if last else main).split()
        if len(shas) > MOST:
            print(f"escapes: {len(shas)} commits on main since {last[:12] or 'its start'}: the oldest {MOST} read, "
                  "the rest at the next run", file=sys.stderr)
            shas = shas[:MOST]
        said: list[str] = []
        if shas:
            log = fac.git(repo, "log", "--no-walk=unsorted", "--format=%H%x00%B%x1e", *shas)
            gaps, ivs = fac.items("gap"), {i["id"] for i in fac.items("intervention")}
            for entry in log.split("\x1e"):
                revert, _, body = entry.strip().partition("\0")
                for old in REVERTS.findall(body):
                    said += record(repo, gaps, ivs, revert, old)
        tmp = p.with_suffix(".new")
        tmp.write_text(json.dumps({"last": shas[-1] if shas else last or main, "at": time.time()}))
        tmp.replace(p)
    return said
