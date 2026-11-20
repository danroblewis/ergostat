"""merge queue: takes an approved gap, under a lease, one at a time (pool 1), and does what the coordinator's
queue-fast.sh does, under the same lock file (`paths.queue_lock`), so the two never run at once:

1. wait for the lock and a quiet machine (no other suite running);
2. merge the branch into a clean main of the checkout (`--no-ff`); a conflict is undone and sent back;
3. ruff, the unit suite (-n 8) and the four browser files (-n 4) under scripts/suite_watch.py, then demo_check; a
   browser test skipped counts as a failure;
4. green: `gap.merged`, and the push to origin main asked for as the gated action `push-main` (held for the
   coordinator; the upgrader follows pushed origin/main); else, and on any error or stop, the merge undone with
   `git reset --keep`, and a failed gap sent on to flake triage with what failed (`queue-failed`).

It merges exactly the commit the reviewer approved, fetched from the drop (never the branch's name), and refuses a
branch that moved since. A conflict is a failed gate (the second parks).

`queue.py push SHA` is the action's command: it pushes exactly that commit to the remote's main, never anything else."""

from __future__ import annotations

import json
import re
import sys
import time

sys.dont_write_bytecode = True
import agents  # noqa: E402
import fac  # noqa: E402
import review  # noqa: E402

KILL = 2


def clean_main(cfg: dict, repo) -> str | None:
    """Why the checkout cannot take a merge now, or None."""
    if fac.git(repo, "symbolic-ref", "--short", "-q", "HEAD", check=False) != cfg["git"]["base"]:
        return f"the checkout is not on {cfg['git']['base']}"
    if fac.git(repo, "status", "--porcelain", "--untracked-files=no"):
        return "the checkout has uncommitted changes"
    if (repo / ".git" / "MERGE_HEAD").exists():
        return "the checkout is in the middle of a merge"
    return None


def suites(cfg: dict, repo, branch: str, logs, n: int) -> dict:
    out = {}
    for name in ("ruff", "unit", "browser", "demo"):
        log = logs / f"{branch}-{n}-{name}.txt"
        rc, secs = fac.suite(cfg, name, repo, log, slot=False)        # the queue's lock is its slot
        text = log.read_text()
        skipped = len(re.findall(r"^SKIPPED", text, re.M)) if name == "browser" else 0
        out[name] = {"rc": rc, "seconds": round(secs), **({"skipped": skipped} if skipped else {})}
        if rc or skipped:
            out["failed"] = name
            out["tests"] = fac.failed_tests(text)
            out["tail"] = text[-2000:]
            out["log"] = str(log)
            break
    return out


# ---- the queue's own state: the merge whose push is not settled yet, and a block the coordinator must lift

def state(cfg: dict) -> dict:
    p = fac.run_dir(cfg) / "queue.json"
    return json.loads(p.read_text()) if p.exists() else {}


def save(cfg: dict, st: dict) -> None:
    p = fac.run_dir(cfg) / "queue.json"
    tmp = p.with_suffix(".new")
    tmp.write_text(json.dumps(st, indent=1))
    tmp.replace(p)


def block(cfg: dict, st: dict, why: str) -> str:
    """Stop the queue and ask the coordinator: an intervention, open until they record it remedied."""
    iid = f"intervention/queue-{time.strftime('%Y%m%d-%H%M%S')}"
    fac.say("intervention.recorded", iid, reason=f"the merge queue stopped: {why}", recorded_at=time.time(),
            **{"class": "queue"})
    st["blocked"] = {"why": why, "intervention": iid, "at": time.time()}
    save(cfg, st)
    return why


def action_state(aid: str) -> str:
    try:
        return json.loads(fac.ergostat("item", aid, "--json").stdout).get("state") or "unknown"
    except (RuntimeError, ValueError, FileNotFoundError):
        return "unknown"


def settle(cfg: dict, repo) -> str | None:
    """Before a merge: what became of the last merge's push. None when the queue may go on; else why it waits.
    Pushed: done. Held: wait (one unpushed merge at a time, so a denial undoes only its own). Denied: the merge undone
    (`reset --keep` to before it) and its gap sent back. Failed, or an undo that fails: the queue blocked, with an
    intervention, until the coordinator records it remedied."""
    st = state(cfg)
    if st.get("blocked"):
        iid = st["blocked"]["intervention"]
        if action_state(iid) != "remedied":
            return f"blocked until {iid} is remedied: {st['blocked']['why']}"
        st.pop("blocked")
        p = st.pop("pending", None)                    # the coordinator's remedy settled that merge, whatever its push
        if p:
            fac.say("gap.push-settled", p["gap"], push="settled by the coordinator", settled_by=iid,
                    settled_at=time.time())
        save(cfg, st)
        return None
    p = st.get("pending")
    if not p:
        return None
    now = action_state(p["action"]) if p.get("action") else p.get("known") or "unknown"
    if now == "held" and not p.get("action"):
        return block(cfg, st, f"the push of {p['sha'][:12]} is held, and its action's id was not said: "
                              f"it cannot be followed")
    if now == "ran":
        fac.say("gap.pushed", p["gap"], pushed_at=time.time(), push="pushed")
        st.pop("pending")
        save(cfg, st)
        return None
    if now == "denied":
        head = fac.git(repo, "rev-parse", "HEAD")
        if head != p["sha"] or not fac.git_ok(repo, "reset", "-q", "--keep", p["pre"]):
            return block(cfg, st, f"the push of {p['sha'][:12]} was denied, and its merge could not be undone "
                                  f"(main at {head[:12]})")
        fac.say("gap.sent-back", p["gap"], sent_back_by="queue", push="denied",
                findings=[f"the push of its merge ({p['sha'][:12]}) was denied: the merge is undone"])
        st.pop("pending")
        save(cfg, st)
        return None
    if now in ("held", "requested", "approved"):
        return f"the push of {p['sha'][:12]} ({p['gap']}) is {now}"
    return block(cfg, st, f"the push of {p['sha'][:12]} is {now}" + (f": {p['said'][-200:]}" if p.get("said") else ""))


def reviewed(cfg: dict, repo, gap: dict) -> tuple[str | None, str]:
    """The commit the reviewer approved, fetched from the drop into the checkout: (its id, or None; why not)."""
    branch, f = fac.branch_of(gap), gap["fields"]
    sha = str(f.get("reviewed_head") or "")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        return None, "no reviewed commit recorded"
    drop = agents.drop(cfg)
    ref = fac.git_branch(branch)
    tip = fac.git(drop, "rev-parse", "--verify", "-q", f"refs/heads/{ref}", check=False)
    if tip != sha:
        return None, f"its branch moved after the review ({sha[:12]} reviewed, {tip[:12] or 'none'} now)"
    fac.git(repo, "fetch", "-q", str(drop), f"refs/heads/{ref}")
    if fac.git(repo, "rev-parse", "FETCH_HEAD") != sha:
        return None, "the fetched branch is not the reviewed commit"
    return sha, ""


def main() -> int:
    fac.stop_on_term()
    cfg = fac.config()
    gap = fac.read_input()["item"]
    f = gap["fields"]
    branch, base = fac.branch_of(gap), cfg["git"]["base"]
    repo = fac.path(cfg, "checkout")
    approved = float(f.get("approved_at") or time.time())
    fac.say("gap.queued", queued_at=time.time(), queue_attempts=1)
    with fac.queue_lock(cfg):
        why = clean_main(cfg, repo) or settle(cfg, repo)
        if why:
            fac.nack(f"queue: {why}", after="10m", count=False)
            return 0
        sha, why = reviewed(cfg, repo, gap)
        if not sha:
            fac.say("gap.sent-back", sent_back_by="queue", findings=[f"not merged: {why}"])
            return 0
        waited = fac.wait_quiet(cfg)
        began = time.time()
        pre = fac.git(repo, "rev-parse", "HEAD")
        done = False
        try:
            msg = f"Merge branch '{fac.git_branch(branch)}'\n\n{fac.TRAILER}"
            if not fac.git_ok(repo, "merge", "-q", "--no-ff", sha, "-m", msg):
                files = fac.git(repo, "diff", "--name-only", "--diff-filter=U", check=False).split()
                fac.git(repo, "merge", "--abort", check=False)
                findings = [f"conflicts with {base}: {' '.join(files)}"]
                if int(f.get("failed_gates") or 0) + 1 >= KILL:          # a conflict is a failed gate too
                    fac.say("gap.measured", failed_gates=1, findings=findings)
                    review.park(cfg, gap, "Failed its gates twice (the kill rule); the last, a conflict in the "
                                          f"merge queue: {findings[0]}", "merge-queue", where="queue")
                else:
                    fac.say("gap.sent-back", sent_back_by="queue", findings=findings, failed_gates=1, fix_rounds=1,
                            queue_wait_hours=round((began - approved) / 3600, 3))
                done = True
                return 0
            logs = fac.run_dir(cfg, "queue")
            n = int(f.get("queue_attempts") or 0) + 1
            got = suites(cfg, repo, branch, logs, n)
            minutes = round((time.time() - began) / 60, 1)
            timing = dict(queue_wait_hours=round((began - approved) / 3600, 3), queue_minutes=minutes,
                          lock_and_load_wait_s=round(waited), suites_queue=got)
            if got.get("failed"):
                fac.say("gap.queue-failed", failed_suite=got["failed"], failed_tests=got["tests"], pre=pre,
                        findings=[f"{got['failed']} failed in the queue: "
                                  f"{', '.join(got['tests'][:8]) or got['tail'][-300:]}"], **timing)
                return 0
            merged = fac.git(repo, "rev-parse", "HEAD")
            done = True
        finally:
            if not done:                                   # failed, raised or stopped: main as it was
                fac.git(repo, "merge", "--abort", check=False)
                if not fac.git_ok(repo, "reset", "-q", "--keep", pre):
                    block(cfg, state(cfg), f"a failed merge of {branch} could not be undone (reset --keep to {pre[:12]})")
    fac.say("gap.merged", merged_at=time.time(), main_sha=merged, pre=pre, **timing)
    try:
        rc, said = fac.act("push-main", key=merged, sha=merged)
        push = {0: "pushed", 1: "failed", 3: "held", 4: "denied"}.get(rc, f"refused ({rc})")
    except FileNotFoundError:
        push, said = "not asked: not run by ergostat", ""
    fac.say("gap.push-asked", push=push, push_said=said[-600:])
    if push != "pushed":
        m = re.search(r"ergostat\.action/[0-9a-f]+", said)
        save(cfg, {**state(cfg), "pending": {"sha": merged, "pre": pre, "gap": gap["id"], "branch": branch,
                                             "action": m.group(0) if m else "", "known": push.split(" ")[0],
                                             "said": said[-600:], "at": time.time()}})
        with fac.queue_lock(cfg):
            settle(cfg, repo)                             # a push denied or failed at once is handled now
    return 0


def push(sha: str) -> int:
    """The action push-main: that commit, and nothing else, to the remote's main (a fast-forward, or refused)."""
    cfg = fac.config()
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise SystemExit(f"not a full commit id: {sha!r}")
    repo = fac.path(cfg, "checkout")
    print(fac.git(repo, "push", "--porcelain", cfg["git"]["remote"], f"{sha}:refs/heads/{cfg['git']['base']}"))
    return 0


if __name__ == "__main__":
    sys.exit(push(sys.argv[2]) if sys.argv[1:2] == ["push"] else main())
