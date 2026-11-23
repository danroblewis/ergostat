"""stack-forward (the block stack-forward, dev/model/building.yaml): a stacked gap's moved bases merged forward into it.

A gap with `stacked_on` [{gap, sha}] (implement.py), approved, built or sent back to fix, is stale when a base was
approved again at a new reviewed head (a fix round after review or triage: it is in fac.STACKABLE with another
`reviewed_head`), or has landed (merged or closed: it is dropped from `stacked_on`, nothing merged). `stack.py stale`
is the sensor stale-stacks: how many there are. `stack.py` is a pass, under the queue's lock (taken only if free: a
queue run reads the reviewed heads it merges, and an approved gap moves only through it), the gaps read inside it,
each stale one in turn bottom-up (a base before the gaps stacked on it, so a stack of three moves in one pass):

- leased, building or in review: never touched; the next implementor round merges the base itself;
- an approved gap whose branch is no longer its reviewed head: left (the queue refuses it as it is);
- otherwise each base's new head merged into its branch (`--no-ff`, by the factory, never a rebase or a squash) in a
  scratch clone of the drop, and the drop's branch moved from the tip it was read at only (update-ref's old value: a
  branch moved meanwhile is refused and theirs kept; so is a gap whose state changed meanwhile). Clean: `stacked_on`
  updated; an approved gap stays approved with its new `reviewed_head` (`reviewed_by: stack-forward`: the merge
  brings only reviewed commits, and the queue tests the result), a built one gets its new `head` for the review;
- a conflict is aborted and the gap sent back to fix with the files (`stack_conflict`), not counted as a failed gate:
  implement.py's next round merges the base again and hands the conflict to its session (its conflict brief).

A `stacked_on` that cannot be read, or that names a gap not in the record, counts as stale (lesson-3) and is said,
never moved."""

from __future__ import annotations

import fcntl
import json
import re
import shutil
import sys

sys.dont_write_bytecode = True
import agents  # noqa: E402
import fac  # noqa: E402

MOVES = ("approved", "built", "fix")        # merged forward; leased, building and in-review never are
LANDED = ("merged", "closed")
SHA = re.compile(r"[0-9a-f]{40}")


def wanted(g: dict, gaps: dict) -> list[dict] | None:
    """``g``'s `stacked_on` as it should be now (each base approved again at its new reviewed head, a landed one
    dropped); None when it cannot be read or names a gap not in ``gaps``."""
    on, out = g["fields"].get("stacked_on"), []
    if not isinstance(on, list) or not all(isinstance(e, dict) and isinstance(e.get("gap"), str)
                                           and isinstance(e.get("sha"), str) for e in on):
        return None
    for e in on:
        if (b := gaps.get(e["gap"])) is None:
            return None
        new = str(b["fields"].get("reviewed_head") or "")
        if b["state"] not in LANDED:
            out.append({"gap": e["gap"], "sha": new if b["state"] in fac.STACKABLE and SHA.fullmatch(new) else e["sha"]})
    return out


def stale(g: dict, gaps: dict) -> bool:
    return g["state"] in MOVES and bool(g["fields"].get("stacked_on")) and wanted(g, gaps) != g["fields"]["stacked_on"]


def depth(gid: str, gaps: dict, seen: tuple = ()) -> int:
    """How many bases are below ``gid`` in the record (a loop counted where it closes, so it ends)."""
    on = gaps[gid]["fields"].get("stacked_on")
    below = [e["gap"] for e in on if isinstance(e, dict) and e.get("gap") in gaps] if isinstance(on, list) else []
    return max([len(seen) if b in seen else depth(b, gaps, (*seen, gid)) + 1 for b in below] or [0])


def merged(cfg: dict, g: dict, tip: str, bases: list[dict]) -> tuple[str, list[str]]:
    """Each base's head merged into ``g``'s branch at ``tip`` in a scratch clone of the drop, `--no-ff`, by the factory:
    (the new head, or "" when a conflict was aborted; the files in conflict)."""
    branch = fac.branch_of(g)
    home, work = agents.clone(cfg, branch, "stack-forward", at=tip)
    try:
        who = ["-c", "user.name=factory", "-c", "user.email=factory@localhost", "-c", "commit.gpgsign=false"]
        for b in bases:
            if not fac.git_ok(work, *who, "merge", "--no-ff", "-m", f"Merge {b['gap']} ({b['sha'][:12]}) forward into "
                                                                     f"the branch\n\n{fac.TRAILER}", b["sha"]):
                files = fac.conflicted(work)
                fac.git(work, "merge", "--abort", check=False)
                if not files:                       # failed for another reason than a conflict: stop, never guess
                    raise RuntimeError(f"merging {b['gap']} {b['sha'][:12]} into {branch} failed without conflicts")
                return "", files
        head, d = fac.git(work, "rev-parse", "HEAD"), agents.drop(cfg)
        side = f"refs/incoming/{home.name}/{fac.git_branch(branch)}"
        fac.git(d, "fetch", "-q", str(work), f"+HEAD:{side}")
        try:
            now = json.loads(fac.ergostat("item", g["id"], "--json").stdout).get("state")
            if now != g["state"]:
                raise RuntimeError(f"{g['id']} went {g['state']} to {now} during the merge: refused")
            if not fac.git_ok(d, "update-ref", f"refs/heads/{fac.git_branch(branch)}", head, tip):
                raise RuntimeError(f"{g['id']}'s branch moved from {tip[:12]} during the merge: refused (theirs kept)")
        finally:
            fac.git(d, "update-ref", "-d", side)
        return head, []
    finally:
        shutil.rmtree(home, ignore_errors=True)


def one(cfg: dict, gaps: dict, g: dict) -> str:
    """``g`` merged forward (when stale and in MOVES); what was done."""
    f, want = g["fields"], wanted(g, gaps)
    if want is None:
        return "its stacked_on cannot be read or names a gap not in the record: left"
    d, ref = agents.drop(cfg), fac.git_branch(fac.branch_of(g))
    tip = fac.git(d, "rev-parse", "--verify", "-q", f"refs/heads/{ref}", check=False)
    if not SHA.fullmatch(tip) or g["state"] == "approved" and tip != f.get("reviewed_head"):
        return f"its branch ({tip[:12] or 'none'}) is not its reviewed head: left"
    new = [e for e in want if not fac.git_ok(d, "merge-base", "--is-ancestor", e["sha"], tip)]
    head, clash = merged(cfg, g, tip, new) if new else (tip, [])
    if clash:
        fac.say("gap.sent-back", g["id"], sent_back_by="stack-forward", stack_conflict=clash, findings=[
            f"merging its base {', '.join(e['gap'] for e in new)} forward conflicts in: {', '.join(clash)}"])
        f["stacked_on"] = want                       # (its descendants wait: it is in fix now, not STACKABLE)
        g["state"] = "fix"
        return f"conflict in {', '.join(clash)}: sent back to fix"
    data = {"stacked_on": want, **({"reviewed_head": head, "reviewed_by": "stack-forward"} if g["state"] == "approved"
                                    else {"head": head} if g["state"] == "built" else {})}
    fac.say("gap.measured", g["id"], **data)
    f.update(data)                                   # (read by the gaps stacked on it, later in this pass)
    return f"merged forward to {head[:12]}" if new else "stacked_on updated"


def forward(cfg: dict) -> str:
    """One pass, under the queue's lock if it is free; what it did."""
    lock = fac.path(cfg, "queue_lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    with open(lock, "a") as held:
        try:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return "a queue run holds the queue's lock: the next pass"
        try:
            gaps = {g["id"]: g for g in fac.items("gap")}
            said = []
            for gid in sorted(gaps, key=lambda i: (depth(i, gaps), i)):     # bottom-up: bases first
                if stale(gaps[gid], gaps):
                    try:
                        said.append(f"{gid}: {one(cfg, gaps, gaps[gid])}")
                    except RuntimeError as e:               # (refused, or git said no: this gap left, the pass goes on)
                        said.append(f"{gid}: {e}")
            return "\n".join(said) or "no stale stack"
        finally:
            fcntl.flock(held, fcntl.LOCK_UN)


def main(argv: list[str]) -> int:
    cfg = fac.config()
    fac.cli(cfg)
    if argv == ["stale"]:
        gaps = {g["id"]: g for g in fac.items("gap")}
        print(sum(stale(g, gaps) for g in gaps.values()))
        return 0
    if argv:
        print("usage: stack.py [stale]", file=sys.stderr)
        return 2
    print(forward(cfg), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
