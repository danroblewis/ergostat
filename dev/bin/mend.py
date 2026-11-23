"""main-mend: the way out of main-broken. Every 30 minutes (dev/model/landing.yaml): main as pushed (the checkout's
<remote>/<base>, fetched), once the machine is quiet (fac.wait_quiet), the main-broken tests not yet tried since
they broke, oldest first, then the least lately tried (<run>/mend/tried.json; at most `[gates] mend_most`, default
MOST, never past CEILING) run alone twice on that commit, in a worktree of its own
(<worktrees>/.mend) and a suite container ([suites] alone, `-rA`; a browser file's test with [suites] rerun, which
has Playwright). Each result is read from the whole log (fac.outcomes): pass only on a PASSED line and no FAILED or
ERROR one. A test passing both runs is `flake.main-fixed` (passed_on, main_fixed_at, fixed_by: main-mend); failed,
skipped, not collected, quarantined at that commit, or a run that stalled or left no log is unknown, and the item
stays main-broken.

The write is decided under flakes.py's lock, on the item read again there: only a main-broken item whose `main` is
the commit run on or an ancestor of it, written as a patch whose first op tests that `main` as read, so a newer break
written in between refuses the whole event, its move to fixed too (spec/items.py)."""

from __future__ import annotations

import json
import math
import re
import shlex
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
import fac  # noqa: E402
import flakes  # noqa: E402

MOST, CEILING, RUNS = 5, 20, 2
SHA = re.compile(r"[0-9a-f]{7,40}")


def most(cfg: dict) -> int:
    """[gates] mend_most, held to 1..CEILING; unset or not a whole number: MOST."""
    v = cfg.get("gates", {}).get("mend_most", MOST)
    return min(max(v, 1), CEILING) if isinstance(v, int) and not isinstance(v, bool) else MOST


def since(it: dict) -> float:
    """When it broke (main_broken_at); missing or not a finite number: the oldest, so it is looked at first."""
    try:
        v = float(it["fields"].get("main_broken_at"))
    except (TypeError, ValueError):
        return 0.0
    return v if math.isfinite(v) else 0.0


def broke(it: dict) -> str:
    """The commit it was last found broken on (its `main`)."""
    return str((it.get("fields") or {}).get("main") or "")


def tried(cfg: dict) -> dict:
    """<run>/mend/tried.json: {item id: [when main-mend last ran it, its `main` then]}.
    Unreadable: {} (every item untried, so oldest first again; nothing is cleared without its two passes)."""
    try:
        got = json.loads((fac.run_dir(cfg, "mend") / "tried.json").read_text())
        return got if isinstance(got, dict) else {}
    except (OSError, ValueError):
        return {}


def oldest(cfg: dict) -> list[dict]:
    """The main-broken flakes naming a test, at most most(cfg): those not tried since they broke first, oldest first,
    then the least lately tried, so items that stay unknown (deleted, quarantined, still broken) give up their place.
    A try counts only for the break it was made on (its `main` as then; a second break keeps main_broken_at, so that
    is not it): an item broken again on a newer main is untried."""
    got = [i for i in fac.items("flake", "main-broken") if isinstance((i.get("fields") or {}).get("test"), str)]
    was = tried(cfg)

    def last(i):
        v = was.get(i["id"])
        ok = isinstance(v, list) and len(v) == 2 and v[1] == broke(i) and isinstance(v[0], (int, float))
        return float(v[0]) if ok and math.isfinite(v[0]) else 0.0
    return sorted(got, key=lambda i: (last(i), since(i), i["id"]))[:most(cfg)], {i["id"] for i in got}


def remember(cfg: dict, picked: list[dict], broken: set[str], fixed: set[str]) -> None:
    """This run's try of each picked item not fixed; kept only for items main-broken now (main-mend runs one at a
    time, pool 1 and a lease, so nothing else writes the file)."""
    was = {**tried(cfg), **{i["id"]: [time.time(), broke(i)] for i in picked}}
    f = fac.run_dir(cfg, "mend") / "tried.json"
    f.with_suffix(".tmp").write_text(json.dumps({k: v for k, v in was.items() if k in broken and k not in fixed}))
    f.with_suffix(".tmp").replace(f)


def pushed(cfg: dict) -> str:
    """Main as pushed: the remote's base, fetched into the checkout (as upgrade.py watch fetches it)."""
    repo, base, remote = fac.path(cfg, "checkout"), cfg["git"]["base"], cfg["git"]["remote"]
    fac.git(repo, "fetch", "-q", remote, f"+refs/heads/{base}:refs/remotes/{remote}/{base}")
    return fac.git(repo, "rev-parse", f"refs/remotes/{remote}/{base}")


def tree(cfg: dict, sha: str) -> Path:
    """main-mend's own worktree, <worktrees>/.mend, detached at ``sha``."""
    repo, wt = fac.path(cfg, "checkout"), fac.path(cfg, "worktrees") / ".mend"
    if not (wt / ".git").exists():
        wt.parent.mkdir(parents=True, exist_ok=True)
        fac.git(repo, "worktree", "add", "-q", "--detach", str(wt), sha)
    fac.git(wt, "checkout", "-q", "--force", "--detach", sha)
    return wt


def by_suite(cfg: dict, tests: list[str]) -> dict[str, list[str]]:
    """The tests by the command that runs them: `rerun` (Playwright) for a file of the browser suite, else `alone`."""
    browser, out = set(shlex.split(str(cfg["suites"].get("browser") or ""))), {}
    for t in tests:
        out.setdefault("rerun" if t.split("::")[0] in browser else "alone", []).append(t)
    return out


def twice(cfg: dict, wt: Path, name: str, tests: list[str], logs: Path, tag: str) -> dict[str, str]:
    """Each test's result over RUNS runs of ``name``: pass only when every run said pass; else its first other word."""
    said = dict.fromkeys(tests, "pass")
    for n in range(1, RUNS + 1):
        log = logs / f"{tag}-{name}-{n}.txt"
        try:
            fac.suite(cfg, name, wt, log, box="mend", tests=[*tests, "-rA"])
            got = fac.outcomes(log.read_text(errors="replace"), tests)
        except Exception as e:  # noqa: BLE001 - stalled, not started, no log: unknown, never a pass
            print(f"main-mend: {name} run {n}: {type(e).__name__}: {e}", file=sys.stderr)
            got = {}
        said = {t: got.get(t, "unknown") if said[t] == "pass" else said[t] for t in tests}
    return said


def mend(iid: str, sha: str, repo: Path) -> str:
    """flake.main-fixed on ``iid``, decided under flakes.py's lock on the item read there; what came of it."""
    with flakes.held():
        it = flakes.read(iid)
        if not it or it.get("state") != "main-broken":
            return f"not written: it is {(it or {}).get('state') or 'unreadable'} now"
        main = str((it.get("fields") or {}).get("main") or "")
        if not SHA.fullmatch(main) or not fac.git_ok(repo, "merge-base", "--is-ancestor", main, sha):
            return f"not written: its main {main[:12] or '(none)'} is neither {sha[:12]} nor an ancestor of it"
        patch = [{"op": "test", "path": "/main", "value": main}, {"op": "add", "path": "/passed_on", "value": sha},
                 {"op": "add", "path": "/main_fixed_at", "value": time.time()},
                 {"op": "add", "path": "/fixed_by", "value": "main-mend"}]
        r = fac.ergostat("event", "--add", "flake.main-fixed", "--item", iid, "--patch", json.dumps(patch), check=False)
    return "fixed" if r.returncode == 0 else f"refused: {(r.stderr or r.stdout).strip()[-300:]}"


def main() -> int:
    fac.stop_on_term()                                  # (stopped: its suite's container killed by name, fac.suite)
    cfg = fac.config()
    picked, broken = oldest(cfg)
    if not picked:
        print("main-mend: no main-broken test", file=sys.stderr)
        return 0
    repo, sha = fac.path(cfg, "checkout"), pushed(cfg)
    fac.wait_quiet(cfg)
    held = set(fac.quarantine(repo, sha))
    tests = {i["fields"]["test"]: i["id"] for i in picked}
    said = {t: "quarantined" for t in tests if t in held}
    wt, logs, tag = tree(cfg, sha), fac.run_dir(cfg, "mend"), f"{sha[:12]}-{int(time.time())}"
    for name, ts in by_suite(cfg, [t for t in tests if t not in held]).items():
        said |= twice(cfg, wt, name, ts, logs, tag)
    fixed = set()
    for t, iid in tests.items():
        got = mend(iid, sha, repo) if said[t] == "pass" else f"stays main-broken ({said[t]})"
        fixed |= {iid} if got == "fixed" else set()
        print(f"main-mend: {t} on {sha[:12]}: {got}", file=sys.stderr)
    remember(cfg, picked, broken, fixed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
