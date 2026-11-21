"""merge queue: takes an approved gap, under a lease, one run at a time (pool 1), and does what the coordinator's
queue-fast.sh does, under the same lock file (`paths.queue_lock`), so the two never run at once:

1. wait for the lock and a quiet machine (no other suite running);
2. fetch the remote and fast-forward the checkout's main to main as pushed (``--ff-only``); one that cannot is
   nacked, not counted;
3. take the batch: the run's gap and up to `batch` - 1 more approved gaps no run holds (the pool `batch` in
   run/pools.json, 1 to start, which is one gap a run; dev/bin/pools.py), walked in rank order and each dry-merged
   onto the batch so far (`git merge-tree`, picks()): one that conflicts with main is sent back and takes no slot, one
   that conflicts only with a batch-mate stays `approved`. The others stay `approved` until the run settles them, and
   the run's start is kept in run/queue.json (`running`), so a run killed part way (SIGKILL, a crash) strands nothing:
   the next run puts main back where it began and takes them again;
4. merge each into a clean main of the checkout in turn (`--no-ff`), the tree dry-merged; a conflict (a re-merge
   after bisecting) is undone and sent back;
5. ruff, then the unit suite (-n 8) and the four browser files (-n 4) at once under scripts/suite_watch.py, then
   demo_check, once for the batch; a browser test skipped counts as a failure;
6. green: `gap.merged` for each, and one push to origin main of the batch's last merge asked for as the gated action
   `push-main` (one approval for the batch; held for the coordinator; the upgrader follows pushed origin/main). Red:
   bisected to the first failing merge (land()), which goes on to flake triage with what failed (`queue-failed`) and
   the rest lands. On any error or stop, main is undone with `git reset --keep`. The push is asked under the run's
   own gap's lease: when that gap does not land, its outcome waits for the push to settle (tell()), so no later lease
   on it fences the approval out.

It merges exactly the commit the reviewer approved, fetched from the drop (never the branch's name), and refuses a
branch that moved since. A conflict is a failed gate (the second parks).

`queue.py push SHA` is the action's command: it pushes exactly that commit to the remote's main, never anything else."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import threading  # never concurrent.futures: this file is named queue.py, which shadows the stdlib queue it imports
import time

sys.dont_write_bytecode = True
import agents  # noqa: E402
import fac  # noqa: E402
import pools  # noqa: E402
import review  # noqa: E402


def clean_main(cfg: dict, repo) -> str | None:
    """Why the checkout cannot take a merge now, or None."""
    if fac.git(repo, "symbolic-ref", "--short", "-q", "HEAD", check=False) != cfg["git"]["base"]:
        return f"the checkout is not on {cfg['git']['base']}"
    if fac.git(repo, "status", "--porcelain", "--untracked-files=no"):
        return "the checkout has uncommitted changes"
    if (repo / ".git" / "MERGE_HEAD").exists():
        return "the checkout is in the middle of a merge"
    return None


def up_to_date(cfg: dict, repo) -> str | None:
    """The checkout's main fast-forwarded to main as pushed (``<remote>/<base>``), once a run, before its first merge:
    the batch merges onto that, never a stale checkout main (other queues push from elsewhere). Why not, or None."""
    remote, base = cfg["git"].get("remote", "origin"), cfg["git"]["base"]
    if not fac.git_ok(repo, "fetch", "-q", remote, base):
        return f"the checkout cannot fetch {base} from {remote}"
    if not fac.git_ok(repo, "merge", "-q", "--ff-only", f"{remote}/{base}"):
        return f"the checkout's {base} cannot fast-forward to {remote}/{base} (unpushed commits?)"
    return None


def suites(cfg: dict, repo, tag: str, logs) -> dict:
    """ruff; then unit and browser at once; then demo (under the other two's load its pages drew nothing). The first
    failure in that order is the one reported; a failure stops the later steps."""
    def one(name: str) -> dict:
        log = logs / f"{tag}-{name}.txt"
        rc, secs = fac.suite(cfg, name, repo, log, slot=False)        # the queue's lock is its slot
        text = log.read_text()
        skipped = len(re.findall(r"^SKIPPED", text, re.M)) if name == "browser" else 0
        got = {"rc": rc, "seconds": round(secs), **({"skipped": skipped} if skipped else {})}
        if rc or skipped:
            got["failure"] = {"failed": name, "tests": fac.failed_tests(text), "tail": text[-2000:], "log": str(log)}
        return got

    def together(names: tuple) -> dict:
        got, ts = {}, []
        for n in names:
            def body(n=n):
                try:
                    got[n] = one(n)
                except BaseException as e:             # (raised again below, in the queue's own thread)
                    got[n] = e
            ts.append(threading.Thread(target=body, daemon=True))
            ts[-1].start()
        try:
            for t in ts:
                t.join()
        except BaseException:                          # stopped: the suites' process groups go with the queue
            fac.stop_suites()
            raise
        for n in names:
            if isinstance(got[n], BaseException):
                raise got[n]
        return {n: got[n] for n in names}

    out = {}
    for step in (("ruff",), ("unit", "browser"), ("demo",)):
        got = together(step)
        for name in step:
            failure = got[name].pop("failure", None)
            out[name] = got[name]
            if failure and "failed" not in out:
                out.update(failure)
        if "failed" in out:
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


def pushed(p: dict | None) -> list[str]:
    """The gaps a pending push carries: a batch's, or one (a pending record from before batches)."""
    return list(p.get("gaps") or [p["gap"]]) if p else []


HELD: dict = {"own": None, "said": []}    # the run's own gap's outcome, kept back while its push waits (tell())


def tell(event: str, gid: str, **data) -> None:
    """A gap's outcome said, but the run's own gap's kept back: the push is asked under that gap's lease, which must
    not be taken again (by the implementor, flake triage) before the push is approved, or the push is fenced out. Said
    at the run's end, or once its push settles (``then`` in the pending record, release())."""
    if gid == HELD["own"]:
        HELD["said"].append({"event": event, "item": gid, "data": data})
    else:
        fac.say(event, gid, **data)


def release(p: dict | None) -> None:
    for e in (p or {}).get("then") or []:
        fac.say(e["event"], e["item"], **e["data"])


def waits(cfg: dict) -> str | None:
    """Why the queue can take no gap now, read only: a push held for approval, or the queue blocked. Its sensor
    (`queue.py waiting`) keeps the merge queue from leasing gaps only to give them back."""
    st = state(cfg)
    if st.get("blocked"):
        return None if action_state(st["blocked"]["intervention"]) == "remedied" else "blocked"
    p = st.get("pending")
    if p and p.get("action") and action_state(p["action"]) in ("held", "requested", "approved"):
        return f"the push of {p['sha'][:12]} waits"
    return None


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
        for gid in pushed(p):
            fac.say("gap.push-settled", gid, push="settled by the coordinator", settled_by=iid,
                    settled_at=time.time())
        release(p)
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
        for gid in pushed(p):
            fac.say("gap.pushed", gid, pushed_at=time.time(), push="pushed")
        release(st.pop("pending"))
        save(cfg, st)
        return None
    if now == "denied":
        head = fac.git(repo, "rev-parse", "HEAD")
        if head != p["sha"] or not fac.git_ok(repo, "reset", "-q", "--keep", p["pre"]):
            return block(cfg, st, f"the push of {p['sha'][:12]} was denied, and its merge could not be undone "
                                  f"(main at {head[:12]})")
        for gid in pushed(p):                          # one approval for the batch: a denial sends back all of it
            fac.say("gap.sent-back", gid, sent_back_by="queue", push="denied",
                    findings=[f"the push of its merge ({p['sha'][:12]}) was denied: the merge is undone"])
        release(st.pop("pending"))
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


def dry(repo, onto: str, sha: str, msg: str) -> tuple[str | None, list[str]]:
    """`sha` merged onto `onto` without touching the checkout (`git merge-tree --write-tree`): (that merge as a commit
    on no branch, or None; the files in conflict). A commit, so the next dry merge finds the merge base a real one would."""
    r = subprocess.run(["git", "-C", str(repo), "merge-tree", "--write-tree", "--name-only", "--no-messages", "-z",
                        onto, sha], capture_output=True, text=True, timeout=600)
    m = re.match(r"([0-9a-f]{40,64})[\0\n]", r.stdout)
    if r.returncode not in (0, 1) or not m:
        raise RuntimeError(f"git merge-tree {onto[:12]} {sha[:12]}: {r.stderr.strip()[-400:]}")
    if r.returncode:
        return None, sorted({p for p in r.stdout[m.end():].split("\0") if p})
    return fac.git(repo, "commit-tree", m.group(1), "-p", onto, "-p", sha, "-m", msg), []


def message(g: dict) -> str:
    return f"Merge branch '{fac.git_branch(fac.branch_of(g))}'\n\n{fac.TRAILER}"


def picks(cfg: dict, repo, gap: dict, n: int, pre: str) -> tuple[list[tuple[dict, str]], str]:
    """The batch, and its dry-merged head: the run's own gap and the approved gaps no run holds (only its own when n is
    1), walked in rank order (the groomer's rank, then when approved), each dry-merged onto the batch so far, until n
    merge. A gap that conflicts with main (`pre`) is sent back at once, a failed gate, and takes no slot; one that
    conflicts only with a batch-mate stays `approved`, no gate failed. The run's own gap is in its batch unless it is
    sent back: the last slot is kept for it, and if it conflicts only with batch-mates the walk is made again with it
    first, so its lease, which the batch's push is asked under, is never given back while others land. The others
    stay `approved` until the run settles them (merged, sent back, queue-failed): a run killed part way leaves them to
    be taken again, and the queue's pool is 1, so no other run takes them meanwhile. A dry merge git cannot make
    (RuntimeError) fails the run after some gaps may have been sent back: those stand, the rest stay `approved`."""
    def key(g: dict) -> tuple:
        rank = g["fields"].get("rank")                    # (rank 0 is a rank: only none is unranked)
        return (10**9 if rank is None else rank, float(g["fields"].get("approved_at") or 0), g["id"])
    others = [g for g in fac.items("gap", "approved") if g["id"] != gap["id"]
              and not (g["fields"].get("lease") or {}).get("holder")] if n > 1 else []
    shas: dict = {}                                       # each gap's reviewed commit; None once sent back

    def walk(order: list[dict]) -> tuple[list[tuple[dict, str]], str] | None:
        batch, head, own = [], pre, False
        for g in order:
            mine = g["id"] == gap["id"]
            if len(batch) >= n or (not mine and not own and shas.get(gap["id"], 1) and len(batch) >= n - 1):
                continue                                  # (full, or the last slot kept for the run's own gap)
            if g["id"] not in shas:
                shas[g["id"]], why = reviewed(cfg, repo, g)
                if not shas[g["id"]]:
                    tell("gap.sent-back", g["id"], sent_back_by="queue", findings=[f"not merged: {why}"])
            if not shas[g["id"]]:
                continue
            made, files = dry(repo, head, shas[g["id"]], message(g))
            if made:
                batch.append((g, shas[g["id"]]))
                head, own = made, own or mine
                continue
            onmain = files if head == pre else dry(repo, pre, shas[g["id"]], message(g))[1]
            if onmain:
                refuse(cfg, g, onmain, time.time())
                shas[g["id"]] = None
            elif mine:
                return None                               # only with batch-mates: walked again, the own gap first
        return batch, head
    order = sorted([gap, *others], key=key)
    return walk(order) or walk([gap, *[g for g in order if g is not gap]]) or ([], pre)


def waited_hours(g: dict, began: float) -> float:
    return round((began - float(g["fields"].get("approved_at") or began)) / 3600, 3)


def merge(cfg: dict, repo, g: dict, sha: str, began: float) -> bool:
    """One gap's reviewed commit merged onto the checkout's HEAD; a conflict is undone, and is a failed gate."""
    if fac.git_ok(repo, "merge", "-q", "--no-ff", sha, "-m", message(g)):
        return True
    files = fac.conflicted(repo)
    fac.git(repo, "merge", "--abort", check=False)
    refuse(cfg, g, files, began)
    return False


def refuse(cfg: dict, g: dict, files: list[str], began: float) -> None:
    """A gap whose merge conflicts: sent back, a failed gate (the kill rule's last parks it)."""
    findings = [f"conflicts with {cfg['git']['base']}: {' '.join(files)}"]
    if int(g["fields"].get("failed_gates") or 0) + 1 >= fac.kill_after(cfg):          # a conflict is a failed gate too
        fac.say("gap.measured", g["id"], failed_gates=1, findings=findings)
        review.park(cfg, g, f"Failed its gates {fac.kill_after(cfg)} times (the kill rule); the last, a conflict in the "
                            f"merge queue: {findings[0]}", "merge-queue", where="queue")
    else:
        tell("gap.sent-back", g["id"], sent_back_by="queue", findings=findings, failed_gates=1, fix_rounds=1,
                queue_wait_hours=waited_hours(g, began))


def land(cfg: dict, repo, batch: list[tuple[dict, str]], pre: str, began: float, waited: float,
         dried: str = "") -> tuple[list, str]:
    """Merge the batch onto main in turn and run the suites once. Green: every merge lands. Red: bisected (the suites
    run again on the first half of the merges, then on half of what is left, ...) to the first merge whose prefix
    fails; that gap goes to flake triage with its failures and the commit it was merged onto (its `pre`), the merges
    before it land, and those after it are merged again onto them and tried as a batch of their own. Each failing merge
    found costs at most 1 + ceil(log2 m) runs (m: the merges left), so n <= pools.BATCH_MOST. Returns (each gap landing with its
    timing, main's head), the checkout's main left at that head. Gaps sent on are said so here; those landing, by the
    caller, once main is settled."""
    base, todo, landed, runs, tag = pre, batch, [], [0], fac.run_tag(fac.branch_of(batch[0][0]), began)
    logs = fac.run_dir(cfg, "queue")

    def run() -> dict:
        runs[0] += 1
        return suites(cfg, repo, tag + (f"-{runs[0]}" if runs[0] > 1 else ""), logs)

    def timing(g: dict, got: dict) -> dict:
        return dict(queue_wait_hours=waited_hours(g, began), queue_minutes=round((time.time() - began) / 60, 1),
                    lock_and_load_wait_s=round(waited), suites_queue=got, batch_size=len(batch), batch_id=tag,
                    batch_runs=runs[0])
    while todo:
        fac.git(repo, "reset", "-q", "--keep", base)
        kept, heads = [], []                               # heads[i]: main with the first i + 1 merges
        for g, sha in todo:
            if merge(cfg, repo, g, sha, began):
                kept.append((g, sha))
                heads.append(fac.git(repo, "rev-parse", "HEAD"))
        tree = lambda c: fac.git(repo, "rev-parse", f"{c}^{{tree}}")              # noqa: E731
        if dried and kept == batch and tree("HEAD") != tree(dried):             # the tree tested is the one dry-merged
            raise RuntimeError(f"the batch's merges differ from its dry merge ({dried[:12]})")
        todo, dried = kept, ""
        if not todo:
            break
        red = run()
        if not red.get("failed"):
            landed += [(g, timing(g, red)) for g, _ in todo]
            base = heads[-1]
            break
        lo, hi, green = 0, len(todo), {}         # the first lo merges ran green (or none); the first hi red
        while hi - lo > 1:
            mid = (lo + hi) // 2
            fac.git(repo, "reset", "-q", "--keep", heads[mid - 1])
            got = run()
            lo, hi, red, green = (lo, mid, got, green) if got.get("failed") else (mid, hi, red, got)
        g, onto = todo[hi - 1][0], heads[hi - 2] if hi > 1 else base
        tell("gap.queue-failed", g["id"], failed_suite=red["failed"], failed_tests=red["tests"], pre=onto,
                findings=[f"{red['failed']} failed in the queue: {', '.join(red['tests'][:8]) or red['tail'][-300:]}"]
                + ([f"the first failing merge of a batch of {len(todo)}, found by bisecting"] if len(todo) > 1 else []),
                **timing(g, red))
        landed += [(x, timing(x, green)) for x, _ in todo[:hi - 1]]    # (hi - 1 == lo: that prefix's run was green)
        base, todo = onto, todo[hi:]
    fac.git(repo, "reset", "-q", "--keep", base)
    return landed, base


def recover(cfg: dict, repo) -> str | None:
    """A run killed part way (no finally: SIGKILL, a crash, an engine restart) left its record in queue.json: main
    goes back to where that run began. Its batch's other gaps never left `approved`, and its own gap is given back by
    its lease, so both are taken again. Killed while saying its batch merged: the queue blocked, for the coordinator."""
    st = state(cfg)
    r = st.get("running")
    if not r:
        return None
    st.pop("running")                                  # (blocked or not, never asked twice: the block waits)
    if r.get("landing"):
        return block(cfg, st, f"a run was stopped while saying {', '.join(r['landing'])} merged (main at "
                              f"{fac.git(repo, 'rev-parse', 'HEAD')[:12]}, the run began at {r['pre'][:12]})")
    if (repo / ".git" / "MERGE_HEAD").exists():
        fac.git(repo, "merge", "--abort", check=False)
    if not fac.git_ok(repo, "reset", "-q", "--keep", r["pre"]):
        return block(cfg, st, f"a killed run's merges could not be undone (reset --keep to {r['pre'][:12]})")
    save(cfg, st)
    return None


def main() -> int:
    fac.stop_on_term()
    cfg = fac.config()
    gap = fac.read_input()["item"]
    repo = fac.path(cfg, "checkout")
    fac.say("gap.queued", queued_at=time.time(), queue_attempts=1)
    HELD["own"] = gap["id"]
    try:
        return take(cfg, gap, repo)
    finally:                                              # what was kept back and not handed to a pending push
        release({"then": HELD["said"]})


def take(cfg: dict, gap: dict, repo) -> int:
    with fac.queue_lock(cfg):
        why = recover(cfg, repo) or clean_main(cfg, repo) or settle(cfg, repo) or up_to_date(cfg, repo)
        if why:
            fac.nack(f"queue: {why}", after="10m", count=False)
            return 0
        pre = fac.git(repo, "rev-parse", "HEAD")
        n = min(pools.state(cfg)["batch"], pools.BATCH_MOST)          # (the ceiling again, at run time)
        batch, dried = picks(cfg, repo, gap, n, pre)
        if not batch:
            return 0
        waited = fac.wait_quiet(cfg)
        began = time.time()
        if fac.git(repo, "rev-parse", "HEAD") != pre:      # (under the lock nothing should move it: never merged onto)
            fac.nack(f"queue: {cfg['git']['base']} moved while the run waited", after="10m", count=False)
            return 0
        save(cfg, {**state(cfg), "running": {"pre": pre, "gaps": [g["id"] for g, _ in batch], "at": began}})
        done = settled = False
        try:
            landed, merged = land(cfg, repo, batch, pre, began, waited, dried)
            if not landed:                                 # no push to wait for: the run's own gap's outcome now
                release({"then": HELD["said"]})
                HELD["said"] = []
            done = True                                    # the point of no return: main holds the landed merges
            ids = [g["id"] for g, _ in landed]
            save(cfg, {**state(cfg), "running": {"pre": pre, "gaps": ids, "at": began, "landing": ids}})
            run = {"run": fac.run_tag(fac.branch_of(gap), began), "minutes": round((time.time() - began) / 60, 1),
                   "at": time.time()}                  # the whole run, on each of its gaps, for merges-per-hour
            extra = lambda g: {} if g["id"] == gap["id"] else {"queued_at": began, "queue_attempts": 1}  # noqa: E731
            for g, timing in landed:
                fac.say("gap.merged", g["id"], merged_at=time.time(), main_sha=merged, pre=pre, queue_runs=[run],
                        **timing, **extra(g))
            for g, _ in batch:
                if g["id"] not in ids:
                    fac.say("gap.measured", g["id"], queue_runs=[run], **extra(g))
            settled = True
        finally:
            if not done:                                   # raised or stopped: main as it was
                fac.git(repo, "merge", "--abort", check=False)
                if not fac.git_ok(repo, "reset", "-q", "--keep", pre):
                    block(cfg, state(cfg), f"a failed batch could not be undone (reset --keep to {pre[:12]})")
            if settled or not done:                        # (stopped while landing: kept, and recover() blocks)
                st = state(cfg)
                st.pop("running", None)
                save(cfg, st)
    if not landed:
        return 0
    try:                                                  # one gated push for the batch: its last merge holds them all
        rc, said = fac.act("push-main", key=merged, sha=merged)
        push = {0: "pushed", 1: "failed", 3: "held", 4: "denied"}.get(rc, f"refused ({rc})")
    except FileNotFoundError:
        push, said = "not asked: not run by ergostat", ""
    gids = [g["id"] for g, _ in landed]
    for gid in gids:
        fac.say("gap.push-asked", gid, push=push, push_said=said[-600:])
    if push != "pushed":
        m = re.search(r"ergostat\.action/[0-9a-f]+", said)
        then, HELD["said"] = HELD["said"], []           # the run's own gap's outcome waits for the push to settle
        save(cfg, {**state(cfg), "pending": {"sha": merged, "pre": pre, "gap": gids[0], "gaps": gids,
                                             "action": m.group(0) if m else "", "known": push.split(" ")[0],
                                             "said": said[-600:], "at": time.time(), "then": then}})
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
    if sys.argv[1:2] == ["waiting"]:                   # the sensor push-waiting: 1 while the queue can take no gap
        print(1 if waits(fac.config()) else 0)
        sys.exit(0)
    sys.exit(push(sys.argv[2]) if sys.argv[1:2] == ["push"] else main())
