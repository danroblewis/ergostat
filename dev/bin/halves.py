"""A red batch's checks, at once: split() cuts its merges in two, keeping each stack whole; share() gives each of two
full runs its own half of the queue's CPUs; and run_all() runs a check (the full suites on a half, or a failing test on
each prefix: queue.land()) on each head, in a detached worktree of its own, run/queue-half/<tag>-<i> (named here,
removed by that name), in a thread. A check's result is what it returned, or the
exception it raised: never a pass (lesson-3). Stopped part way (SIGTERM through fac.stop_on_term, an error), no check
starts, every suite is killed (fac.stop_suites) and every worktree it made is removed. Call it under the queue's lock:
at its start it removes what a SIGKILLed run left under run/queue-half/, by allowlist (only names of the <tag>-<i>
pattern), which no live run can own then."""

from __future__ import annotations

import re
import shutil
import threading
from collections.abc import Callable
from pathlib import Path

import fac

ROOT = "queue-half"                                     # under [paths] run
TAG = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}-\d{8}T\d{6}Z$")          # a run's tag (fac.run_tag)
MADE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}-\d{8}T\d{6}Z-\d{1,2}$")  # a worktree this code names: <tag>-<i>
HEADS_MOST, NAMED_AT_ONCE = 64, 4                       # a round's most heads; prefixes checked at once (serial tests)
WORKERS = re.compile(r"(?<!\S)-n (\d+)\b")
CPUS = re.compile(r"\d+(-\d+)?(,\d+(-\d+)?)*")


def share(cfg: dict, i: int) -> dict:
    """``cfg`` for half ``i`` of two full runs at once. Each gets its own half of [agents] queue_cpuset (12-23: 12-17 and
    18-23), so neither can starve the other; unit and browser keep their 2:1 split with half the CPUs and pytest
    workers (agents.queued: 4 and 2); and as each may take twice as long, the stall and wall limits are doubled, up to
    their ceilings. An unset or unreadable cpuset is left as it is (agents.limits refuses the unreadable)."""
    stall, wall = fac.limits(cfg)
    s = {**cfg["suites"], "stall_minutes": min(2 * stall / 60, fac.STALL_MOST),
         "wall_minutes": min(2 * wall / 60, fac.WALL_MOST)}
    for name in ("unit", "browser"):
        if isinstance(s.get(name), str):
            s[name] = WORKERS.sub(lambda m: f"-n {max(1, int(m[1]) // 2)}", s[name])
    a = {**(cfg.get("agents") or {}), "queue_half": True}
    pin = str(a.get("queue_cpuset") or "").strip()
    if CPUS.fullmatch(pin):
        ids = [c for x in pin.split(",") for c in range(int(x.split("-")[0]), int(x.split("-")[-1]) + 1)]
        if len(ids) >= 2:
            a["queue_cpuset"] = ",".join(map(str, ids[:len(ids) // 2] if i == 0 else ids[len(ids) // 2:]))
    return {**cfg, "suites": s, "agents": a}


def split(merges: list, linked: Callable[[object, object], bool]) -> tuple[list, list, bool]:
    """``merges`` (two or more, bases before what stacks on them) as (first, second, apart). Merges ``linked`` (one's
    `stacked_on` reaches the other) are one stack. With two stacks or more, whole stacks go to each half, the first
    filled to half the merges and the second never empty; apart is True: either half can be tested and land alone.
    With one stack, first is its lower half and second the rest, which cannot be tested without it: apart is False."""
    stacks: list[list[int]] = []
    for i, m in enumerate(merges):
        touching = [s for s in stacks if any(linked(m, merges[j]) for j in s)]
        stacks = [s for s in stacks if s not in touching] + [sorted([x for s in touching for x in s] + [i])]
    stacks.sort()
    if len(stacks) == 1:
        cut = (len(merges) + 1) // 2
        return merges[:cut], merges[cut:], False
    first: list[int] = []
    for k, s in enumerate(stacks):
        if k == len(stacks) - 1 or (first and len(first) + len(s) > (len(merges) + 1) // 2):
            break
        first += s
    keep = set(first)
    return [m for i, m in enumerate(merges) if i in keep], [m for i, m in enumerate(merges) if i not in keep], True


def remove(repo: Path, root: Path, name: str) -> None:
    """The worktree ``name`` under ``root``, gone: only a name this code makes, never a path that leads out."""
    if not MADE.match(name):
        raise ValueError(f"not a half's worktree: {name!r}")
    wt = root / name
    if wt.is_symlink():                                 # (the link alone, never what it points to)
        wt.unlink()
        return
    fac.git(repo, "worktree", "remove", "--force", str(wt), check=False)
    if wt.exists():
        shutil.rmtree(wt)


def sweep(cfg: dict, repo: Path, where: str = ROOT) -> list[str]:
    """The worktrees a SIGKILLed run left under run/queue-half/ (or run/<where>/: the verification lane's own,
    verify.py, swept under its own lock), removed (under the queue's lock); their names. Anything else there is kept."""
    root = fac.run_dir(cfg, where).resolve()
    gone = sorted(p.name for p in root.iterdir() if MADE.match(p.name))
    for name in gone:
        remove(repo, root, name)
    return gone


def run_all(cfg: dict, repo: Path, heads: list[str], check, tag: str, most: int = 2, where: str = ROOT) -> list:
    """check(i, worktree) on each of ``heads`` (head i in run/<where>/<tag>-i: run/queue-half/ unless the verification
    lane's own), at most ``most`` at a time; one result per head, in heads' order: what it returned, or the exception
    that ended it."""
    if not TAG.match(tag) or not 1 <= len(heads) <= HEADS_MOST or where not in (ROOT, "verify-half"):
        raise ValueError(f"a round's tag {tag!r} is not a run tag, or {len(heads)} heads are not 1 to {HEADS_MOST}, "
                         f"or {where!r} is not a half's folder")
    root, repo = fac.run_dir(cfg, where).resolve(), Path(repo)
    sweep(cfg, repo, where)
    made, out, stop, gate = [], [None] * len(heads), threading.Event(), threading.Semaphore(most)
    done = [threading.Event() for _ in heads]           # (set as each ends: never is_alive, a broken join's lie)

    def one(i: int, head: str) -> None:
        try:
            with gate:
                if stop.is_set():
                    out[i] = RuntimeError("stopped")
                    return
                wt = root / f"{tag}-{i}"
                made.append(wt.name)                    # (before it is made: a half-made one is removed too)
                fac.git(repo, "worktree", "add", "-q", "--detach", str(wt), head)
                out[i] = RuntimeError("stopped") if stop.is_set() else check(i, wt)
        except BaseException as e:                      # (a check that raised: said, and never a pass)
            out[i] = e
        finally:
            done[i].set()

    ts = [threading.Thread(target=one, args=(i, h), daemon=True) for i, h in enumerate(heads)]
    try:
        for t in ts:
            t.start()
        for d in done:
            d.wait()
    except BaseException:                               # stopped: no check starts, each running one is killed
        stop.set()                                      # (one not yet in one() sees it; one in it is waited for)
        live = [d for t, d in zip(ts, done, strict=True) if t.ident is not None]
        while not all(d.is_set() for d in live):
            fac.stop_suites()                           # (again each pass: one started as the stop came)
            for d in live:
                d.wait(0.5)
        raise
    finally:
        for name in list(made):
            remove(repo, root, name)
    return out
