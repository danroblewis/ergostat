"""``python -m ergostat.repair fix|apply|settle|revert`` (SPEC §12r). ``apply``, the approved ``apply-fix``: the tested
commit fast-forwarded onto the owner's HEAD it was made on, else back to open. ``settle``: a denied fix dismissed, an
applied fix judged by the runs of its block begun after it (verified, or regressed and ``revert-fix`` asked for), and
the clones no failure needs removed. ``revert``, the approved ``revert-fix``: the applied commit reverted by one new
commit. Each judges and writes one failure while holding its lock (``locked``)."""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from ..actions import record as rec
from ..sandbox import git as sgit
from . import FAILURE, VERIFY_MAX, VERIFY_MIN
from .fix import ID, Refused, failure, owner_repo, record

DONE = ("applied", "dismissed", "dead", "verified", "regressed", "reverted")
HEX40 = re.compile(r"^[0-9a-f]{40}$")
PENDING = ("REVERT_HEAD", "MERGE_HEAD", "CHERRY_PICK_HEAD", "sequencer")
ME = ["-c", "user.name=ergostat", "-c", "user.email=ergostat@localhost", "-c", "gc.auto=0"]


def apply() -> int:
    from ..library.run.common import project
    p = project()
    fid = os.environ.get("ERGOSTAT_ITEM", "")
    try:
        _, name, it = failure(p, fid)
        f = it.fields if it else {}
        if it is None or it.state != "awaiting-approval" or not f.get("fix"):
            raise Refused(f"{fid} has no tested fix waiting")
        if (rec.get(p, os.environ.get("ERGOSTAT_ACTION", "")) or {}).get("key") != f"{name}-{f['fix']}":
            raise Refused("the approved action was for another fix than the one waiting")
        work = Path(p.dir) / "repair" / name
        c = sgit.Repo(work, work / ".git")
        if c("rev-parse", "HEAD").strip() != f["fix"]:
            raise Refused("the clone is not at the tested commit")
        owner = owner_repo(p.model.spec.root)
        if owner("rev-parse", "HEAD").strip() != f["base"]:
            raise Refused(f"the repository moved since the fix was made on {f['base'][:12]}: fixed again on the new HEAD")
        owner("fetch", "-q", "--no-tags", str(work), "HEAD")
        if owner("rev-parse", "FETCH_HEAD").strip() != f["fix"]:
            raise Refused("what was fetched is not the tested commit")
        owner("merge", "--ff-only", "-q", f["fix"])
    except (Refused, sgit.Tampered, subprocess.CalledProcessError) as e:
        why = str(e) if not isinstance(e, subprocess.CalledProcessError) else f"git: {(e.stderr or '').strip()[-500:]}"
        record(p, "apply-failed", fid, {"why": why})
        print(f"not applied: {why}", file=sys.stderr)
        return 1
    record(p, "applied", fid, {"commit": f["fix"], "orig_head": f["base"]})
    shutil.rmtree(work, ignore_errors=True)
    print(f"applied {f['fix'][:12]} onto {f['base'][:12]}")
    return 0


@contextlib.contextmanager
def locked(p, name: str):
    """``<state>/repair/locks/<name>.lock`` held: an ``fcntl.flock``, which the kernel frees when the process dies.
    ``name`` must be a failure's (``fix.ID``), so the path is built from nothing else."""
    if not ID.match(f"{FAILURE}/{name}"):
        raise Refused(f"{name!r} is not a failure's name")
    d = Path(p.dir) / "repair" / "locks"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / f"{name}.lock", "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


def bounded(asked) -> dict:
    """``--verify`` clamped to VERIFY_MIN..VERIFY_MAX; one that cannot be read counts as VERIFY_MAX (the most cautious)."""
    try:
        n = int(str(asked).strip())
    except ValueError:
        n = None
    used = VERIFY_MAX if n is None else min(max(n, VERIFY_MIN), VERIFY_MAX)
    return {"used": used, "asked": str(asked), "clamped": used != n}


def judge(p, spec, fid: str, name: str, v: dict) -> str:
    """One applied failure, read again here (inside its lock): ``verified`` after ``v["used"]`` good runs of its block
    begun after the newest ``applied`` (by seq), ``regressed`` at a failed one the code may be to blame for; else, and
    when an input is missing, nothing written and why said."""
    from ..spec.items import one
    from .capture import NOT_THE_CODE, ended
    it = one(p.events, spec, fid)
    if it is None or it.state != "applied":
        return f"no longer applied ({it.state if it else 'gone'})"
    blk, commit = it.fields.get("block"), str(it.fields.get("commit") or "")
    applied = p.events.query(n=1, type=f"{FAILURE}.applied", item=fid)
    if not applied:
        return "no applied event found: not verified"
    if blk not in spec.blocks:
        return f"its block {blk!r} is no longer in the model: not verified"
    if not HEX40.match(commit):
        return "its commit cannot be read: not verified"
    seq, limit = applied[0]["seq"], 10 * v["used"]
    runs = p.events.query(n=limit, type="agent.started", item=blk, after_seq=seq)      # (the newest; all, when fewer)
    if runs and len(runs) == limit and p.events.query(n=1, type="agent.started", item=blk, after_seq=seq,
                                                      before_seq=runs[0]["seq"]):
        return f"more than {limit} runs began since the fix and none decided it: not verified, a person looks"
    ends = {e.get("causedby"): e for e in p.events.query(n=None, type="agent.ran,agent.failed", item=blk,
                                                         after_seq=runs[0]["seq"])} if runs else {}
    good: list[str] = []
    verdict = {"runs": good, "after_seq": seq, "verify": v}
    for r in runs:
        end = ends.get(r["id"])
        if end is None:
            return f"run {r['id'][:12]} has not ended: nothing counted past it ({len(good)} of {v['used']} good)"
        if end["type"] == "agent.ran":
            good.append(r["id"])
            if len(good) >= v["used"]:
                record(p, "verified", fid, {"verdict": verdict})
                return "verified"
        elif not ended(end.get("data") or {}).startswith(NOT_THE_CODE):
            mine = any(x.get("causedby") == r["id"] for x in p.events.query(n=None, type="ergostat.run.failed",
                                                                         item=fid, after_seq=seq))
            record(p, "regressed", fid, {"revert_key": f"{name}-{commit}", "verdict": {
                **verdict, "run": r["id"], "note": (end.get("data") or {}).get("note"), "failure": fid if mine else None,
                "same": mine}})
            ask_revert(p, spec, fid, f"{name}-{commit}")
            return "regressed"
    return f"{len(good)} of {v['used']} good runs begun after the fix so far"


def ask_revert(p, spec, fid: str, key: str) -> None:
    """``revert-fix`` asked for once a key: none asked if one about the failure already has it (in any state; the
    apply-fix that applied the commit has the same key, so the action's name is matched too)."""
    from ..actions import gate
    if not any(a.get("action") == "revert-fix" and a.get("key") == key for a in rec.about(p, fid)):
        gate.request(p, spec, "revert-fix", {}, {"block": "repair-settle", "run": os.environ.get("ERGOSTAT_RUN"),
                                                 "item": fid}, asker="program", key=key)


def settle(verify="3", p=None) -> int:
    from ..library.run.common import items, project
    p = p or project()
    spec, v = p.model.spec, bounded(verify)
    n, moved = 0, {"verified": 0, "regressed": 0}
    for it in items(p, FAILURE, ["awaiting-approval"]):
        asked = rec.about(p, it.id)                         # newest first: the answer to the latest asked
        if asked and asked[0]["state"] == "denied":
            record(p, "dismissed", it.id, {"by": asked[0].get("denied_by"), "note": asked[0].get("note")})
            n += 1
    for it in items(p, FAILURE, ["applied", "regressed"]):
        name = it.id.split("/", 1)[1]
        if not ID.match(it.id):
            print(f"{it.id}: not a failure's name: not judged", file=sys.stderr)
            continue
        with locked(p, name):
            if it.state == "applied":
                said = judge(p, spec, it.id, name, v)
                if said in moved:
                    moved[said] += 1
                else:
                    print(f"{it.id}: {said}", file=sys.stderr)
            else:                                           # asked again if lost (a crash between the two writes)
                now = one_of(p, spec, it.id)
                if now is not None and now.state == "regressed" and now.fields.get("revert_key"):
                    ask_revert(p, spec, it.id, now.fields["revert_key"])
    states = {i.id.split("/", 1)[1]: i.state for i in items(p, FAILURE)}
    for d in (Path(p.dir) / "repair").glob("*/"):
        if d.name != "locks" and states.get(d.name, "dead") in DONE:
            shutil.rmtree(d, ignore_errors=True)
    for out, k in (("flow.fixes-dismissed", n), ("flow.fixes-verified", moved["verified"]),
                   ("flow.fixes-regressed", moved["regressed"])):
        print(json.dumps({"out": out, "moved": k}))
    return 0


def one_of(p, spec, fid: str):
    from ..spec.items import one
    return one(p.events, spec, fid)


def _pending(owner: sgit.Repo) -> str | None:
    for x in PENDING:
        f = Path(owner("rev-parse", "--git-path", x).strip())
        if (f if f.is_absolute() else Path(owner.work) / f).exists():
            return x
    return None


def _clean(owner: sgit.Repo) -> bool:
    return not owner("status", "--porcelain", "--untracked-files=no").strip()


def revert(p=None, aid: str | None = None, fid: str | None = None) -> int:
    """The approved ``revert-fix``: the failure's applied commit reverted in the owner's repository by one new commit,
    every step under the failure's lock (SPEC §12r). 0: reverted, or reverted already; 1: refused or failed."""
    from ..library.run.common import project
    p = p or project()
    aid, fid = aid or os.environ.get("ERGOSTAT_ACTION", ""), fid or os.environ.get("ERGOSTAT_ITEM", "")
    m = ID.match(fid)
    if not m:
        print(f"not reverted: {fid!r} is not a failure", file=sys.stderr)
        return 1
    with locked(p, f"{m[1]}-{m[2]}"):
        it = one_of(p, p.model.spec, fid)
        state = it.state if it else None
        if state == "reverted":
            print(f"{fid}: already reverted")
            return 0
        if state != "regressed":
            print(f"not reverted: {fid} is {state or 'not recorded'}: only a regressed fix is reverted", file=sys.stderr)
            return 1
        commit, key = str(it.fields.get("commit") or ""), it.fields.get("revert_key")
        if not key or (rec.get(p, aid) or {}).get("key") != key:
            print("not reverted: the approved action was for another fix's revert than the one regressed", file=sys.stderr)
            return 1
        head0, why, started, aborted = None, None, False, False
        try:
            if not HEX40.match(commit):
                raise Refused(f"its commit {commit[:50]!r} cannot be read")
            owner = owner_repo(p.model.spec.root)
            try:
                owner("merge-base", "--is-ancestor", commit, "HEAD")
            except subprocess.CalledProcessError:
                raise Refused(f"{commit[:12]} is not in your repository's HEAD: nothing to revert") from None
            head0 = owner("rev-parse", "HEAD").strip()
            done = owner("log", "--format=%H", "-F", f"--grep=This reverts commit {commit}.", f"{commit}..HEAD").split()
            if done:                                        # reverted by an earlier run whose event was never written
                record(p, "reverted", fid, {"revert": {"revert_commit": done[0], "of": commit, "found": True}})
                print(f"{fid}: reverted already by {done[0][:12]}")
                return 0
            if not _clean(owner):
                raise Refused("your repository has changes not committed: not reverted, nothing touched")
            if x := _pending(owner):
                raise Refused(f"a revert is in progress in your repository ({x}): not reverted, nothing touched")
            started = True
            owner(*ME, "revert", "--no-edit", commit)
        except (Refused, sgit.Tampered) as e:
            why = str(e)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            why = f"git: {(e.stderr or '').strip()[-500:]}" if isinstance(e, subprocess.CalledProcessError) else \
                f"git did not finish within {e.timeout:g}s"
            if started:                                     # (only a revert this call began is aborted)
                aborted = abort(owner, head0)
                why += "; aborted: your repository is as it was" if aborted else \
                    "; the abort did not restore it: your repository is left mid-revert (git status says how)"
        if why is not None:
            record(p, "revert-failed", fid, {"revert": {"why": why, "aborted": aborted, "of": commit}})
            print(f"not reverted: {why}", file=sys.stderr)
            return 1
        new = owner("rev-parse", "HEAD").strip()
        record(p, "reverted", fid, {"revert": {"revert_commit": new, "of": commit}})
    print(f"reverted {commit[:12]} with {new[:12]}")
    return 0


def abort(owner: sgit.Repo, head0: str) -> bool:
    """``git revert --abort``, then checked: True only when no revert is in progress, HEAD is ``head0`` and the tree is
    clean (whether or not the abort itself exited 0)."""
    with contextlib.suppress(subprocess.CalledProcessError, subprocess.TimeoutExpired):
        owner(*ME, "revert", "--abort", check=False)
    try:
        return _pending(owner) is None and owner("rev-parse", "HEAD").strip() == head0 and _clean(owner)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, sgit.Tampered):
        return False


def main(argv: list[str]) -> int:
    from . import fix
    if argv[:1] == ["fix"]:
        return fix.main(argv[1:])
    if argv in (["apply"], ["revert"]):
        return apply() if argv == ["apply"] else revert()
    if argv[:1] == ["settle"] and (len(argv) == 1 or (len(argv) == 3 and argv[1] == "--verify")):
        return settle(argv[2] if len(argv) == 3 else "3")
    print("usage: python -m ergostat.repair fix [...] | apply | settle [--verify N] | revert", file=sys.stderr)
    return 2
