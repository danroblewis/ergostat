"""Merge first, verify after (dev/records/merge-first-verify-after.md; dev/README.md, *Merge first, verify after*).
Off unless `[verify] after = true`: then the queue lands on a quick check and this lane verifies main beside it. Off,
the queue runs its full suites as before, and only reapplied() and taken_out() here are read (they act on nothing but
this lane's own reverts).

- Landing (queue.py land()): quick() stands in for the full suites. The batch merged cleanly (the queue's dry merge), it
  imports (`[suites] imports`), and the test files it added or changed pass with the smoke set ([verify] smoke, under 2
  minutes), through `[suites] rerun`. A red quick check takes the queue's two paths as a red full run does.
- Verifying (`verify.py run`, the block verifier, every 10 minutes, under its own lock and never the queue's while a
  suite runs): main as pushed is verified when due(): the merges since the verified commit reach verify-lines net lines
  (each merge's own net count, as its absolute value, so a deletion never hides an addition), or its oldest unverified
  commit is verify-hours old (the parameters in dev/model/landing.yaml; [verify] lines and hours override them), or a
  revert was pushed since, or a run was asked for (`verify.py run --now WHY`: before a publish). The full suites
  (queue.suites, the browser files always) run in a worktree of the lane's own (run/verify-half/), on the second half of
  the queue's CPUs (halves.share), in containers named suite-verify-* that the queue's sweep never kills. Before each
  round it waits for the load interlock (room()): the suites running and its own leave the last of machine-quiet's
  slots free, and the suites' threads and memory are within suite-threads-within and suite-memory-within.
- Green: the ref `verified` (refs/heads/verified in the checkout) moves to it, compare-and-swap from the commit it was
  read at, and each gap merged in the window says gap.measured verified_sha, verified_at and verify_hours (its merge to
  verified). Version switches take only that commit (switchable(), upgrade.py watch); the publish job reads
  `verify.py verified`.
- Red, as the queue does: 1 to 3 tests that pass alone twice on the tip, with the suites the run did not finish green, are
  flakes (flake.seen; green). Tests that fail alone twice on the verified commit are main's own: an intervention (class
  queue), the lane held until it is remedied, nothing reverted. Else the merges since the verified commit are bisected,
  each round checking up to NAMED_AT_ONCE prefixes at once on the failing tests (when they fail alone on the tip), or
  FULL_AT_ONCE full runs (halves.run_all), and the first red merge is tried alone on the verified commit (`confirmed`
  true or false, said with it). When that is the window's first merge and the bisection ran by full runs, the
  verified commit itself is run first: red or not told there, main's own (held, nothing reverted). It and every later
  merge whose branch holds its branch (a stacked gap; read again from main's head under the queue's lock, so one landed
  meanwhile goes too) are reverted on main under that lock, newest first, each a commit of its own (`This reverts
  commit`, `Reverted-tip:`, which taken_out() and escapes.py read, and for a stacked one `Stacked-on:`, which escapes.py
  counts as no escape). The culprit is to say gap.queue-failed (failed_tests, its base as `pre`), so flake triage takes
  it as today; each dependent gap.retried, back to approved uncounted. The reverts' push is asked as the queue asks its
  own, its pending record marked `reverts`, and those outcomes are kept in it (`then`) until it settles: ran or failed,
  said; denied, main is back over the reverts, nothing is said and the lane is held (denied()). No verification starts
  while it waits. The next run verifies again. A culprit that is no gap's merge, a revert that conflicts, or a
  bisection that cannot tell holds the lane with an intervention instead (lesson-3: never a guess).
- Coming back: a gap whose merge this lane reverted (reverted_by_verify) has those reverts undone first when the queue
  merges it again (reapplied()): a branch's commits already on main would merge as nothing.

Each verification is a line of run/verify-log.jsonl, read by the dashboard series (reading()) and by nothing else."""

from __future__ import annotations

import fcntl
import json
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
import fac  # noqa: E402
import halves  # noqa: E402

REF = "refs/heads/verified"
HALF, BOX = "verify-half", "verify"
SHA = re.compile(r"[0-9a-f]{40}")
LINES_MOST, HOURS_MOST, SMOKE_MOST = 100_000, 48.0, 50   # (lesson-4: each refused past its ceiling, never clamped)
FULL_AT_ONCE = 2
REAPPLY_CONFLICT = "(the revert of its earlier merge cannot be undone on this base)"
TESTS = re.compile(r"^tests/(?:[^/]+/)*test_[^/]*\.py$")
MERGE = re.compile(r"^Merge branch 'factory/([a-z0-9][a-z0-9-]{0,63})'")
MEASURES = ("verify-escapes", "verify-reverts", "merge-to-verified-hours", "suite-runs-per-merged-gap")


def on(cfg: dict) -> bool:
    return (cfg.get("verify") or {}).get("after") is True


def retroactive(cfg: dict, repo: Path) -> bool:
    """Whether regressions that land are found and reverted after: the lane on, a verified commit to bisect from, and
    the lane not held. What the error budget's level may drop on (the auxiliary verify-retroactive); run/verify.json
    unreadable raises, so the reading is missing and the level stays at its strictest."""
    return on(cfg) and bool(verified(repo)) and not state(cfg).get("held")


# ---- the settings

def param(text: str, name: str) -> str:
    """A parameter's value in dev/model/landing.yaml (`  NAME:` then its indented fields)."""
    m = re.search(rf"^  {re.escape(name)}:[ \t]*(?:#.*)?\n((?:    .*\n?)+)", text, re.M)
    v = re.search(r"^\s+value:\s*([^\s#]+)", m.group(1), re.M) if m else None
    if not v:
        raise ValueError(f"no parameter {name} with a value in dev/model/landing.yaml")
    return v.group(1)


def settings(cfg: dict) -> tuple[int, float]:
    """(verify-lines, verify-hours): [verify] lines and hours when set, else the model's parameters. A value that is not
    a count of 1 to LINES_MOST, or hours over 0 and at most HOURS_MOST (`2h`, `90m`, 2), is refused: ValueError."""
    v = cfg.get("verify") or {}
    text = "" if "lines" in v and "hours" in v else (fac.HERE / "model" / "landing.yaml").read_text()
    lines, hours = v.get("lines", None), v.get("hours", None)
    lines = param(text, "verify-lines") if lines is None else lines
    hours = param(text, "verify-hours") if hours is None else hours
    n = int(lines) if not isinstance(lines, bool) and re.fullmatch(r"\d{1,9}", str(lines)) else 0
    m = None if isinstance(hours, bool) else re.fullmatch(r"(\d{1,6}(?:\.\d{1,6})?)(h|m)?", str(hours))
    h = float(m[1]) / (60 if m[2] == "m" else 1) if m else 0.0
    if not 1 <= n <= LINES_MOST or not 0 < h <= HOURS_MOST:
        raise ValueError(f"verify-lines {lines!r} is not 1 to {LINES_MOST}, or verify-hours {hours!r} is not over 0 "
                         f"and at most {HOURS_MOST:g} h")
    return n, h


def smoke(cfg: dict) -> list[str]:
    """[verify] smoke: test files or ids under tests/, at most SMOKE_MOST; anything else refused (ValueError)."""
    s = (cfg.get("verify") or {}).get("smoke", [])
    if not isinstance(s, list) or len(s) > SMOKE_MOST or not all(isinstance(t, str) and t.startswith("tests/")
                                                                  and ".." not in t for t in s):
        raise ValueError(f"[verify] smoke is not a list of at most {SMOKE_MOST} tests under tests/")
    return list(s)


# ---- landing: the quick check

def changed_tests(repo: Path, pre: str) -> list[str]:
    """The test files `git diff pre HEAD` names that HEAD has. A diff that cannot be read raises (never none)."""
    r = subprocess.run(["git", "-C", str(repo), "diff", "--name-only", "--no-renames", "-z", pre, "HEAD"],
                       capture_output=True, text=True, timeout=600)
    if r.returncode:
        raise RuntimeError(f"git diff {pre[:12]} HEAD: {r.stderr.strip()[-300:]}")
    return sorted(p for p in r.stdout.split("\0") if TESTS.match(p) and (Path(repo) / p).is_file())


def quick(cfg: dict, repo, tag: str, logs: Path, pre: str = "HEAD", only: tuple | None = None, cover: bool = True,
          browser: bool | None = None) -> dict:
    """The landing check, in queue.suites()'s shape: `[suites] imports`, then the changed test files and the smoke set
    through `[suites] rerun` (main's quarantine deselected). Red: `failed` (imports or quick), the failing tests, the
    tail. ``only`` (the rest of a run whose failures were excused): nothing is left, {}. Exit 5 (no test collected,
    every one deselected) is no failure; exit 3 is a crash, naming no test."""
    if only is not None:
        return {}
    repo, out = Path(repo), {}
    for name in ("imports", "quick"):
        log = logs / f"{tag}-{name}.txt"
        if name == "quick":
            tests = sorted(set(changed_tests(repo, pre)) | set(smoke(cfg)))
            if not tests:
                return out | {"quick": {"not_run": "no test file changed and no smoke set", "counts": "not_run"}}
            held = [x for t in fac.quarantine(repo, pre) for x in ("--deselect", t)]
            rc, secs = fac.suite(cfg, "rerun", repo, log, slot=False, box="queue", tests=[*tests, *held])
        else:
            rc, secs = fac.suite(cfg, "imports", repo, log, slot=False, box="queue")
        text = log.read_text(errors="replace")
        out[name] = {"rc": rc, "seconds": round(secs), "log": str(log),
                     **({"files": tests, "counts": fac.counts(text) or "unknown"} if name == "quick" else {})}
        if rc and not (name == "quick" and rc == 5):
            crash = "exit 3: an internal error, or the suite's watchdog stopped it" if rc == 3 else ""
            return out | {"failed": name, "tests": [] if crash or name == "imports" else fac.failed_tests(text),
                          "tail": text[-2000:], "log": str(log), **({"crashed": crash} if crash else {})}
    return out


# ---- main's history

def verified(repo: Path) -> str:
    return fac.git(repo, "rev-parse", "--verify", "-q", f"{REF}^{{commit}}", check=False)


def pushed_main(cfg: dict, repo: Path) -> str:
    remote, base = cfg["git"].get("remote", "origin"), cfg["git"]["base"]
    fac.git(repo, "fetch", "-q", remote, f"+refs/heads/{base}:refs/remotes/{remote}/{base}")
    return fac.git(repo, "rev-parse", f"refs/remotes/{remote}/{base}")


def switchable(cfg: dict, repo: Path, pushed: str) -> str | None:
    """The commit a version switch may take: the pushed main when the lane is off; on, the verified commit when the
    pushed main holds it, else none."""
    if not on(cfg):
        return pushed
    v = verified(repo)
    return v if v and fac.git_ok(repo, "merge-base", "--is-ancestor", v, pushed) else None


def commits(repo: Path, base: str, tip: str) -> list[dict]:
    """main's first-parent commits after ``base`` up to ``tip``, oldest first: sha, parents, commit time, message."""
    out = fac.git(repo, "log", "--first-parent", "--reverse", "--format=%H %P%x00%ct%x00%B%x1e", f"{base}..{tip}")
    got = []
    for e in out.split("\x1e"):
        if e.strip():
            head, at, body = e.lstrip("\n").split("\0", 2)
            sha, *parents = head.split()
            got.append({"sha": sha, "parents": parents, "at": int(at), "body": body.strip()})
    return got


def merges(cs: list[dict]) -> list[dict]:
    return [c for c in cs if len(c["parents"]) == 2]


def grep(repo: Path, text: str, rng: str) -> list[str]:
    return fac.git(repo, "log", "--format=%H", "--fixed-strings", f"--grep={text}", rng, check=False).split()


def taken_out(repo: Path, tip: str, onto: str) -> bool:
    """Whether this lane's reverts of the branch at ``tip`` on ``onto`` outnumber its reapplies: its work is off main
    though its commits are in its history (queue.stack(): a base not merged)."""
    if not SHA.fullmatch(tip or ""):
        return False
    return len(grep(repo, f"Reverted-tip: {tip}", onto)) > len(grep(repo, f"Reapplied-tip: {tip}", onto))


def revert_commit(repo: Path, onto: str, commit: str, msg: str) -> str | None:
    """``commit`` (its change from its first parent) undone on ``onto``, as a commit; None when that conflicts."""
    r = subprocess.run(["git", "-C", str(repo), "merge-tree", "--write-tree", "--no-messages",
                        f"--merge-base={commit}", onto, f"{commit}^1"], capture_output=True, text=True, timeout=600)
    m = re.match(r"([0-9a-f]{40,64})\s", r.stdout)
    if r.returncode == 1:
        return None
    if r.returncode or not m:
        raise RuntimeError(f"git merge-tree (revert {commit[:12]} on {onto[:12]}): {r.stderr.strip()[-400:]}")
    return fac.git(repo, "commit-tree", m.group(1), "-p", onto, "-m", f"{msg}\n\n{fac.TRAILER}")


def reapplied(repo, onto: str, g: dict) -> str | None:
    """``onto`` with this lane's reverts of ``g`` (its field reverted_by_verify) undone, newest first, each a commit
    (`Reapplied-tip:`): ``onto`` itself when there are none on it, or each is undone already; None when one conflicts."""
    revs = g["fields"].get("reverted_by_verify")
    for rv in reversed(revs if isinstance(revs, list) else []):
        if not (isinstance(rv, str) and SHA.fullmatch(rv) and fac.git_ok(repo, "merge-base", "--is-ancestor", rv, onto)) \
                or grep(Path(repo), f"This reverts commit {rv}", f"{rv}..{onto}"):
            continue
        tip = re.search(r"^Reverted-tip: ([0-9a-f]{40})$", fac.git(repo, "log", "-1", "--format=%B", rv), re.M)
        onto = revert_commit(Path(repo), onto, rv, f"Reapply {g['id']} (verification had reverted it)\n\nThis reverts "
                                                   f"commit {rv}.\nReapplied-tip: {tip[1] if tip else ''}")
        if onto is None:
            return None
    return onto


REVERTS = re.compile(r"^This reverts commit ([0-9a-f]{40})", re.M)


def reverts(window: list[dict]) -> dict[str, str]:
    """This lane's reverts in ``window`` still standing (none reapplied there): {the commit reverted: its revert}."""
    back = {m[1] for c in window if "Reapplied-tip:" in c["body"] and (m := REVERTS.search(c["body"]))}
    return {m[1]: c["sha"] for c in window if "Reverted-tip:" in c["body"] and (m := REVERTS.search(c["body"]))
            and c["sha"] not in back}


def gap_of(gaps: list[dict], c: dict) -> dict | None:
    """The one gap whose merge ``c`` is: its second parent the gap's reviewed_head, else its branch named."""
    hit = [g for g in gaps if str(g["fields"].get("reviewed_head") or "") == c["parents"][1]]
    m = MERGE.match(c["body"])
    if len(hit) != 1 and m:
        hit = [g for g in gaps if g["fields"].get("branch") == m[1] or g["id"] == f"gap/{m[1]}"]
    return hit[0] if len(hit) == 1 else None


# ---- the lane's own record

def state(cfg: dict) -> dict:
    """run/verify.json (`again`, `found`, `held`); unreadable raises: the run fails where it is seen."""
    p = fac.run_dir(cfg) / "verify.json"
    st = json.loads(p.read_text()) if p.exists() else {}
    if not isinstance(st, dict):
        raise ValueError("run/verify.json is not a map")
    return st


def save(cfg: dict, st: dict) -> None:
    p = fac.run_dir(cfg) / "verify.json"
    tmp = p.with_suffix(".new")
    tmp.write_text(json.dumps(st, indent=1))
    tmp.replace(p)


def logged(cfg: dict, **line) -> None:
    with open(fac.run_dir(cfg) / "verify-log.jsonl", "a") as f:
        f.write(json.dumps({"at": time.time(), **line}) + "\n")


def hold(cfg: dict, st: dict, why: str, **line) -> str:
    """The lane stopped, with an intervention (class queue), until the coordinator records it remedied."""
    iid = f"intervention/verify-{time.strftime('%Y%m%d-%H%M%S')}"
    st.pop("found", None)
    st["held"] = {"why": why, "intervention": iid, "at": time.time()}
    save(cfg, st)
    fac.say("intervention.recorded", iid, reason=f"the verification of main stopped: {why}", recorded_at=time.time(),
            **{"class": "queue"})
    logged(cfg, outcome="held", why=why, **line)
    return why


# ---- the lane

def due(cfg: dict, repo: Path, st: dict, base: str, tip: str, now: float) -> str:
    """Why main's tip is to be verified now, or "" (see the module's text)."""
    if not base:
        return "no commit is verified yet"
    if base == tip:
        return ""
    if not fac.git_ok(repo, "merge-base", "--is-ancestor", base, tip):
        return f"the verified commit {base[:12]} is not in main's history"
    if st.get("again"):
        return str(st["again"])
    try:
        most, hours = settings(cfg)
        cs = commits(repo, base, tip)
        n = sum(abs(fac.net_lines(repo, c["parents"][0], c["sha"], core=False)) for c in merges(cs))
    except (OSError, ValueError, RuntimeError) as e:     # (lesson-3: not knowing is verifying)
        return f"its settings or lines cannot be read ({str(e)[-200:]}): verified now"
    if n >= most:
        return f"{n} lines merged since {base[:12]} (verify-lines {most})"
    age = (now - min((c["at"] for c in cs), default=now)) / 3600
    return f"its oldest unverified commit is {age:.1f} h old (verify-hours {hours:g})" if age >= hours else ""


def first_red(lo: int, hi: int, check, most: int) -> tuple[int, int]:
    """Prefixes lo (green; -1: the verified commit) to hi (red) narrowed, ``most`` checked at once a round, to the first
    red (hi, with hi - lo == 1); a check that cannot tell ("unknown") stops it where it is."""
    while hi - lo > 1:
        k = min(most, hi - lo - 1)
        picks = sorted({lo + (hi - lo) * (j + 1) // (k + 1) for j in range(k)})
        for p, r in zip(picks, check(picks), strict=True):
            if r == "unknown":
                return lo, hi
            if r == "fail":
                hi = p
                break
            lo = p
    return lo, hi


INTERLOCK = (("machine-quiet", "suites"), ("suite-threads-within", "threads"), ("suite-memory-within", "memory"))


def holds() -> dict[str, float]:
    """The load interlock's setpoints (dev/model/interlock.yaml); one not found raises (lesson-3: never no limit)."""
    text, out = (fac.HERE / "model" / "interlock.yaml").read_text(), {}
    for goal, what in INTERLOCK:
        m = re.search(rf'^  {goal}:\s*$.*?hold: "<= ([\d.]+)"', text, re.M | re.S)
        if not m:
            raise ValueError(f"the goal {goal} has no hold in dev/model/interlock.yaml")
        out[what] = float(m[1])
    return out


def room(cfg: dict, n: int) -> float:
    """Waits until the machine has room for ``n`` more suites under the load interlock: the suites running and ``n``
    leave the last of machine-quiet's slots free (the queue's: slots.py; ``n`` past that, none may run), and the suites'
    threads and memory are within suite-threads-within and suite-memory-within. The seconds waited. Off with
    [load] wait = false (the tests' machine is not the factory's)."""
    if cfg["load"].get("wait", True) is False:
        return 0.0
    import load
    lim, began, poll = holds(), time.time(), float(cfg["load"]["wait_poll"])
    while fac.suites_running() + n > max(n, lim["suites"] - 1) or load.reading("threads") > lim["threads"] \
            or load.reading("memory") > lim["memory"]:
        fac.renew()
        time.sleep(poll)
    return time.time() - began


def run(cfg: dict, repo: Path, now: float | None = None, asked: str = "") -> str:
    """One turn of the lane, under its own lock (another holding it: nothing). What it did, said."""
    import queue as q  # (dev/bin/queue.py, loaded here: it imports this module)
    with open(fac.run_dir(cfg) / "verify.lock", "a") as lk:
        try:
            fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return "a verification runs already"
        if cfg["suites"].get("queue_container", True) is not False:
            fac.agents_module().sweep_box(BOX)          # (a SIGKILLed run's: none is live under this lock)
        if waiting(cfg, q):                             # (its gaps' outcomes wait on it: never verified past it)
            q.settle_alone(cfg)                         # (the push-settler's work, here when the queue's lock is free;
            if p := waiting(cfg, q):                    # denied, the lane is held: read below)
                return f"the push of its reverts ({p['sha'][:12]}) waits to settle"
        st = state(cfg)
        if h := st.get("held"):
            if q.action_state(h["intervention"]) != "remedied":
                return f"held until {h['intervention']} is remedied: {h['why']}"
            st.pop("held")
            save(cfg, st)
        if st.get("found"):
            return revert(cfg, repo, st, q)
        tip, base = pushed_main(cfg, repo), verified(repo)
        why = (asked if base != tip else "") or due(cfg, repo, st, base, tip, now or time.time())
        return verify(cfg, repo, st, base, tip, why, q) if why else "not due"


def waiting(cfg: dict, q) -> dict | None:
    """The queue's pending push when it is this lane's reverts (unreadable raises: the run fails where it is seen)."""
    p = q.state(cfg).get("pending")
    return p if p and p.get("reverts") else None


def stacked(repo: Path, c: dict, tip: str, gaps: list[dict]) -> list[dict] | str:
    """The merges after the culprit ``c`` up to ``tip`` whose branch holds the culprit's (stacked on it), not reverted
    there, each with its gap; why not, when one is the merge of no one gap."""
    if not fac.git_ok(repo, "merge-base", "--is-ancestor", c["sha"], tip):
        return f"the culprit's merge {c['sha'][:12]} is not in main's history at {tip[:12]}"
    window = commits(repo, c["sha"], tip)
    standing, out = reverts(window), []
    for x in merges(window):
        if x["sha"] in standing or not fac.git_ok(repo, "merge-base", "--is-ancestor", c["parents"][1], x["parents"][1]):
            continue
        if not (g := gap_of(gaps, x)):
            return f"{x['sha'][:12]}, stacked on the culprit, is the merge of no one gap the record names"
        out.append(found_of(x, g))
    return out


def found_of(x: dict, g: dict) -> dict:
    return {"sha": x["sha"], "gap": g["id"], "pre": x["parents"][0], "tip": x["parents"][1],
            "was": list(g["fields"].get("reverted_by_verify") or [])}


def verify(cfg: dict, repo: Path, st: dict, base: str, tip: str, why: str, q) -> str:
    began = time.time()
    tag, logs, conf, runs = fac.run_tag("verify", began), fac.run_dir(cfg, "verify"), halves.share(cfg, 1), [0]
    window, gaps = commits(repo, base, tip) if base else [], fac.items("gap")
    ids = [g["id"] for c in merges(window) if (g := gap_of(gaps, c))]
    line = {"tip": tip, "base": base, "due": why, "gaps": ids}

    def at(heads: list[str], fn, most: int, each: int) -> list:
        room(cfg, min(len(heads), most) * each)         # (the load interlock, before each round: lesson-4)
        runs[0] += len(heads)
        return halves.run_all(cfg, repo, heads, fn, tag, most, HALF)

    def full(heads: list[str], **kw) -> list:           # (unit and browser at once: 2 suites a run)
        k, confs = runs[0], [halves.share(conf, j) for j in range(2)] if len(heads) > 1 else [conf]
        return at(heads, lambda i, wt: q.suites(confs[i], wt, f"{tag}-{k}-{i}", logs, heads[i], cover=False,
                                                browser=True, box=BOX, **kw), FULL_AT_ONCE, 2)

    def said(r) -> str:
        return "unknown" if r is None or isinstance(r, BaseException) or r.get("crashed") else \
            "fail" if r.get("failed") else "pass"

    red = full([tip])[0]
    if said(red) == "pass":
        return green(cfg, repo, st, base, tip, window, gaps, line | {"runs": runs[0], "outcome": "green"})
    if said(red) == "unknown":                          # (a stall, a crash, a box that did not start: no merge's)
        why_not = red.get("crashed") if isinstance(red, dict) else f"{type(red).__name__}: {red}"
        logged(cfg, **line, runs=runs[0], outcome="unknown", why_not=str(why_not)[:300])
        return f"its run could not tell ({str(why_not)[:200]}): nothing moved"
    tests = red.get("tests") or []

    unseen = [t for t in tests if not q.present(repo, tip, [t])]   # (not found by name at the tip itself: asked
                                                                   # everywhere, so a blind lookup is never a pass)

    def alone(heads: list[str]) -> list[str]:
        k, here = runs[0], [q.present(repo, h, tests) + unseen for h in heads]
        got = at(heads, lambda i, wt: q.named(conf, wt, f"{tag}-{k}-{i}", logs, {"failed": red["failed"],
                                                                                 "tests": here[i]}, box=BOX)
                 if here[i] else {}, halves.NAMED_AT_ONCE, 1)
        return [said(r) for r in got]

    first = alone([tip])[0] if tests and len(tests) <= q.NAMED_MOST else "unknown"
    by_name = first == "fail"                           # (they fail alone on the tip: the bisection runs only them)
    if first == "pass" and q.excusable(red) and alone([tip]) == ["pass"]:   # (passed alone twice: then the rest)
        more = full([tip], only=q.rest(red))[0]
        if said(more) == "pass":
            for t in tests:
                q.flakes.say("flake.seen", t, gaps=ids, times=1, seen_at=time.time(), run=tag, suite=red["failed"],
                             passed_alone=2, log=red["log"])
            return green(cfg, repo, st, base, tip, window, gaps, line | {"runs": runs[0], "outcome": "flake",
                                                                         "flakes": tests})
    if not base:
        return hold(cfg, st, f"main {tip[:12]} is red and no commit is verified to bisect from", **line)
    if by_name and alone([base]) == ["fail"] and alone([base]) == ["fail"]:
        return hold(cfg, st, f"the verified {base[:12]} fails {', '.join(tests[:5])} alone now: main's own, no merge's",
                    **line, runs=runs[0])
    standing, at_ = reverts(window), {c["sha"]: k for k, c in enumerate(window)}
    places = [k for k, c in enumerate(window) if len(c["parents"]) == 2 and c["sha"] not in standing]
    places += [len(window) - 1] if not places or places[-1] != len(window) - 1 else []
    heads = []
    for k in places:                                    # (each prefix less what this lane reverted after it: a merge
        h = window[k]["sha"]                            # found and reverted before is never found again)
        for t in [c["sha"] for c in window[:k] if c["sha"] in standing and at_[standing[c["sha"]]] > k]:
            h = h and revert_commit(repo, h, t, f"verify: the prefix without {t[:12]}")
        heads.append(h)
    if None in heads:
        return hold(cfg, st, "a prefix of the window cannot be built without the merges reverted in it", **line)
    named_check = lambda picks: alone([heads[i] for i in picks])                            # noqa: E731
    full_check = lambda picks: [said(r) for r in full([heads[i] for i in picks])]          # noqa: E731
    lo, hi = first_red(-1, len(heads) - 1, named_check, halves.NAMED_AT_ONCE) if by_name else (-1, len(heads) - 1)
    lo, hi = first_red(lo, hi, full_check, FULL_AT_ONCE)
    if lo == -1 and hi == 0 and not by_name:           # (the first merge blamed, the verified commit not run since:
        was = said(full([base])[0])                     # main's own failure, a tool's or the clock's, is red there too)
        if was != "pass":
            return hold(cfg, st, f"the verified {base[:12]} {'is red' if was == 'fail' else 'could not be told'} now "
                                 "by full runs: main's own, no merge's", **line, runs=runs[0])
    c = window[places[hi]]
    if hi - lo != 1 or len(c["parents"]) != 2 or c["sha"] in standing:
        return hold(cfg, st, f"the bisection of {base[:12]}..{tip[:12]} could not name a merge (prefixes "
                             f"{lo + 1} to {hi} of {len(heads)})", **line, runs=runs[0])
    alone_on = q.dry(repo, base, c["parents"][1], "verify: the culprit alone on the verified commit")[0]
    r = (alone([alone_on]) if by_name else [said(full([alone_on])[0])]) if alone_on else ["unknown"]
    if not (g := gap_of(gaps, c)):
        return hold(cfg, st, f"main turned red at {c['sha'][:12]}, the merge of no one gap the record names",
                    **line, runs=runs[0])
    if isinstance(later := stacked(repo, c, tip, gaps), str):   # (read again inside the queue's lock: revert())
        return hold(cfg, st, later, **line, runs=runs[0])
    st["found"] = {"culprit": found_of(c, g), "dependents": later, "confirmed": {"fail": True, "pass": False}.get(r[0]),
                   "red": {"suite": red["failed"], "tests": tests, "tail": red.get("tail", "")[-1500:],
                           "log": red.get("log")}, "line": line | {"runs": runs[0]}}
    save(cfg, st)
    return revert(cfg, repo, st, q)


def green(cfg: dict, repo: Path, st: dict, base: str, tip: str, window: list, gaps: list, line: dict) -> str:
    """The ref moved to ``tip`` from ``base`` (from none: it must not exist), each merged gap told."""
    if not fac.git_ok(repo, "update-ref", "-m", "verify: green", REF, tip, base or "0" * 40):
        return f"the verified ref moved under this run: {tip[:12]} not recorded"
    st.pop("again", None)
    save(cfg, st)
    now, out = time.time(), reverts(window)
    for c in merges(window):
        if c["sha"] not in out and (g := gap_of(gaps, c)):           # (a merge reverted since: not verified)
            fac.say("gap.measured", g["id"], verified_sha=tip, verified_at=now,
                    verify_hours=round(max(0.0, now - c["at"]) / 3600, 3))
    logged(cfg, **line)
    return f"verified {tip[:12]} ({line['outcome']})"


def revert(cfg: dict, repo: Path, st: dict, q) -> str:
    """The found merges reverted on main, newest first, under the queue's lock, once nothing of the queue's waits: each
    gap told, the push asked, and the next run verifying again. One already reverted is not reverted twice."""
    f = st["found"]
    tests = f["red"]["tests"]
    with fac.queue_lock(cfg):
        try:
            why = q.recover(cfg, repo) or q.clean_main(cfg, repo) or q.settle(cfg, repo) or q.up_to_date(cfg, repo)
        except q.Unreadable as e:
            why = str(e)
        if why:
            return f"its reverts wait: {why}"
        head = top = fac.git(repo, "rev-parse", "HEAD")
        c = f["culprit"]
        # (read again here, under the lock: a gap stacked on the culprit may have landed since verify() read main)
        c_ = {"sha": c["sha"], "parents": [c["pre"], c["tip"]]}
        if isinstance(deps := stacked(repo, c_, head, fac.items("gap")), str):
            return hold(cfg, st, deps, **f["line"])
        f["dependents"] = deps
        made: dict[str, list[str]] = {}
        for m in [*reversed(deps), c]:
            for sha in [m["sha"], *reapplies(repo, m["pre"], m["tip"])]:
                if grep(repo, f"This reverts commit {sha}", f"{sha}..{top}"):
                    continue
                subject = fac.git(repo, "log", "-1", "--format=%s", sha)
                on = "" if m is c else f"\nStacked-on: {c['gap']}"     # (escapes.py: a dependent's is no escape)
                new = revert_commit(repo, top, sha, f'Revert "{subject}" (verification found main red)\n\nThis reverts '
                                                    f"commit {sha}.\nReverted-tip: {m['tip']}{on}\nFailing: "
                                                    f"{', '.join(tests[:5]) or f['red']['suite']}")
                if new is None:
                    return hold(cfg, st, f"the revert of {sha[:12]} ({m['gap']}) conflicts on main {top[:12]}",
                                **f["line"])
                made.setdefault(m["gap"], []).append(new)
                top = new
        if top != head and not fac.git_ok(repo, "reset", "-q", "--keep", top):
            return hold(cfg, st, f"main could not be moved to its reverts ({top[:12]})", **f["line"])
        n = f["line"].get("runs")
        then = [{"event": "gap.queue-failed", "item": c["gap"], "data": {
            "failed_suite": f["red"]["suite"], "failed_tests": tests, "pre": c["pre"],
            "reverted_by_verify": c["was"] + made.get(c["gap"], []), "verify_confirmed": f["confirmed"],
            "findings": [f"{f['red']['suite']} failed on main after it merged, found by verification in {n} runs, "
                         f"and its merge was reverted: {', '.join(tests[:8]) or f['red']['tail'][-300:]}"]}}]
        then += [{"event": "gap.retried", "item": d["gap"], "data": {
            "approved_by": "verify-given-back", "reverted_by_verify": d["was"] + made.get(d["gap"], []),
            "given_back": f"reverted with {c['gap']}, which it is stacked on"}} for d in deps]
        if top != head:                                 # (first: killed past here, the outcomes are kept, or said
            ask(cfg, repo, q, top, head, c["gap"], then)    # again by the next run, never lost)
        else:                                           # (reverted already: nothing to push, said now)
            q.release({"then": then})
        st = state(cfg)                                 # (read again: a push denied at once held the lane, denied(),
        st.pop("found", None)                           # and that hold is kept, never saved over: lesson-1)
        st["again"] = f"after the revert of {c['gap']}"
        save(cfg, st)
        logged(cfg, **f["line"], outcome="red", culprit=c["gap"], reverted=[c["gap"], *[d["gap"] for d in deps]],
               confirmed=f["confirmed"], tests=tests)
    return f"reverted {c['gap']} and {len(deps)} stacked on it; verifying again"


def reapplies(repo: Path, pre: str, tip: str) -> list[str]:
    """The reapply commits of the branch at ``tip`` just below its merge (whose first parent is ``pre``)."""
    out = []
    while f"Reapplied-tip: {tip}" in fac.git(repo, "log", "-1", "--format=%B", pre):
        out.append(pre)
        pre = fac.git(repo, "rev-parse", f"{pre}^1")
    return out


def ask(cfg: dict, repo: Path, q, sha: str, pre: str, culprit: str, then: list[dict]) -> None:
    """The reverts' push, asked as the queue asks its own (queue.ask), under its lock. Pushed: the gaps' outcomes
    (``then``) said. Else pending in run/queue.json, marked `reverts`, the outcomes kept in it until the push settles
    (queue.settle): ran, said; failed, said with the queue blocked (main still holds the reverts); denied, main back
    over the reverts, nothing said and the lane held (denied())."""
    try:
        rc, said = fac.act("push-main", key=sha, sha=sha)
        push = {0: "pushed", 1: "failed", 3: "held", 4: "denied"}.get(rc, f"refused ({rc})")
    except FileNotFoundError:
        push, said = "not asked: not run by ergostat", ""
    if push == "pushed":
        q.release({"then": then})
        return
    m = re.search(r"ergostat\.action/[0-9a-f]+", said)
    q.save(cfg, {**q.state(cfg), "pending": {"sha": sha, "pre": pre, "gap": f"the reverts of {culprit}", "gaps": [],
                                             "reverts": True, "action": m.group(0) if m else "",
                                             "known": push.split(" ")[0], "said": said[-600:], "at": time.time(),
                                             "then": then}})
    q.settle(cfg, repo)


def denied(cfg: dict, p: dict) -> None:
    """The reverts' push denied (queue.settle, which put main back over them): no gap told, the lane held, so the same
    merges are not found and reverted again until the coordinator records the intervention remedied."""
    hold(cfg, state(cfg), f"the push of {p['gap']} ({p['sha'][:12]}) was denied: main holds those merges again",
         denied=[e["item"] for e in p.get("then") or []])


# ---- the dashboard series and the replay

def num(v) -> float | None:
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) and v == v and abs(v) != float("inf") \
        else None


def log_lines(cfg: dict) -> list[dict]:
    p = fac.run_dir(cfg) / "verify-log.jsonl"
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


class NoValue(Exception):
    """Nothing to measure: no value, never a 0."""


def reading(name: str, lines: list[dict], batches: list[dict], gaps: list[dict], since: float) -> float:
    """One of MEASURES over the window from ``since``: verify-escapes (verifications that found a merge red),
    verify-reverts (merges reverted), merge-to-verified-hours (median, over gaps verified), suite-runs-per-merged-gap
    (the batches' runs and the verifications' over the gaps merged: today's queue alone, while the lane is off)."""
    mine = [x for x in lines if (num(x.get("at")) or 0) >= since]
    if name == "verify-escapes":                        # (less the reverts whose push was denied: undone, denied())
        return float(sum(x.get("outcome") == "red" for x in mine) - sum(bool(x.get("denied")) for x in mine))
    if name == "verify-reverts":
        return float(sum(len(x.get("reverted") or []) - len(x.get("denied") or []) for x in mine))
    if name == "merge-to-verified-hours":
        hs = [h for g in gaps if (num(g["fields"].get("verified_at")) or 0) >= since
              and (h := num(g["fields"].get("verify_hours"))) is not None]
        if not hs:
            raise NoValue("merge-to-verified-hours: no value (no gap verified in the window)")
        return round(statistics.median(hs), 3)
    if name == "suite-runs-per-merged-gap":
        merged = sum((num(g["fields"].get("merged_at")) or 0) >= since for g in gaps if g["state"] == "merged")
        if not merged:
            raise NoValue("suite-runs-per-merged-gap: no value (no gap merged in the window)")
        ran = sum(len([r for r in b["fields"].get("runs") or [] if isinstance(r, dict)]) for b in batches
                  if (num(b["fields"].get("started_at")) or 0) >= since)
        return round((ran + sum(int(num(x.get("runs")) or 0) for x in mine)) / merged, 3)
    raise KeyError(name)


def replay(batches: list[dict], gaps: list[dict], since: float, lines_most: int, hours_most: float,
           quick_minutes: float) -> dict:
    """The batches started since ``since`` replayed: before, as they ran (each run a full one; a gap's time to main
    from its approval to its batch's landing); after, as this flow would have run them (each run a quick check of
    ``quick_minutes``, a gap on main that long after its batch began; a verification of 1 full run at each
    ``lines_most`` net lines or ``hours_most`` hours of landed merges, and for each gap the queue found failing, one
    more red verification, its bisection of 2 runs a round over that window, 1 alone on the verified commit and 1 to
    verify again). An estimate, said with its assumptions: the queue's own wait is kept as it was."""
    by = {g["id"]: g["fields"] for g in gaps}
    bs = sorted((b for b in batches if (num(b["fields"].get("started_at")) or 0) >= since),
                key=lambda b: num(b["fields"]["started_at"]))
    landed = [(gid, b) for b in bs if b["state"] in ("landed", "partial") for gid in b["fields"].get("landed") or []]
    failed = [(gid, b) for b in bs for gid in b["fields"].get("failed") or []]
    ran = sum(len(b["fields"].get("runs") or []) for b in bs)
    before, after, windows, size, lines, first = [], [], [], 0, 0, None
    for gid, b in landed:
        f, start = by.get(gid, {}), num(b["fields"]["started_at"])
        approved = num(f.get("approved_at")) or start
        if (t := num(b["fields"].get("landed_at"))) is not None:
            before.append((t - approved) / 3600)
        after.append((start - approved) / 3600 + quick_minutes / 60)
        at, first = start + quick_minutes * 60, start if first is None else first
        size, lines = size + 1, lines + abs(int(num(f.get("merged_lines")) or 0))
        if lines >= lines_most or at - first >= hours_most * 3600:
            windows.append((first, at, size))
            size, lines, first = 0, 0, None
    if size:
        windows.append((first, float("inf"), size))
    full = len(windows)
    for _, b in failed:                                  # (its window: the one open when its batch began)
        n = next((w[2] for w in windows if w[1] >= num(b["fields"]["started_at"])), 1) + 1
        rounds = 0
        while n > 1:
            n, rounds = -(-n // 3), rounds + 1
        full += 1 + 2 * rounds + 2
    merged = len(landed)
    med = lambda xs: round(statistics.median(xs), 3) if xs else None   # noqa: E731
    return {"batches": len(bs), "merged": merged, "failed_in_queue": len(failed),
            "before": {"full_runs": ran, "runs_per_merged_gap": round(ran / merged, 3) if merged else None,
                       "hours_to_main_median": med(before)},
            "after": {"quick_checks": ran, "verifications": len(windows), "full_runs": full,
                      "runs_per_merged_gap": round(full / merged, 3) if merged else None,
                      "quick_per_merged_gap": round(ran / merged, 3) if merged else None,
                      "hours_to_main_median": med(after)},
            "assumptions": [f"a quick check takes {quick_minutes:g} min", "each batch run becomes one quick check",
                            "each gap the queue found failing lands and is caught by verification",
                            "the queue's wait for the lock is as it was"]}


def main(argv: list[str]) -> int:
    cfg = fac.config()
    repo = fac.path(cfg, "checkout")
    if argv[:1] == ["verified"]:                         # the publish job's commit (none: exit 1, nothing published)
        v = verified(repo)
        print(v)
        return 0 if v else 1
    if argv[:1] == ["retroactive"]:                      # 1 while regressions are found and reverted after they land
        print(1 if retroactive(cfg, repo) else 0)
        return 0
    if argv[:1] == ["start"]:                            # the switch-over: main as pushed, which the queue's full
        v = verified(repo) or pushed_main(cfg, repo)     # suites passed, is the first verified commit
        fac.git(repo, "update-ref", "-m", "verify: start", REF, v, verified(repo) or "0" * 40)
        print(v)
        return 0
    if argv[:1] == ["run"]:
        asked = argv[argv.index("--now") + 1] if "--now" in argv[:-1] else ""
        if not on(cfg) and not asked:
            print("verify: [verify] after is off", file=sys.stderr)
            return 0
        fac.stop_on_term()
        print(f"verify: {run(cfg, repo, asked=asked)}", file=sys.stderr)
        return 0
    if argv[:1] == ["replay"]:
        days = float(argv[argv.index("--days") + 1]) if "--days" in argv[:-1] else 7.0
        if not 0 < days <= 60:
            raise SystemExit("--days: over 0 and at most 60")
        lines_most, hours_most = settings(cfg)
        quick_minutes = float((cfg.get("verify") or {}).get("quick_minutes", 3))
        print(json.dumps(replay(fac.items("batch"), fac.items("gap"), time.time() - days * 86400, lines_most,
                                hours_most, quick_minutes), indent=1))
        return 0
    raise SystemExit("verify.py start | run [--now WHY] | verified | retroactive | replay [--days N]")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
