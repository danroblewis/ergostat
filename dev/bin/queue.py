"""merge queue: takes an approved gap, under a lease, one run at a time (pool 1), and does what the coordinator's
queue-fast.sh does, under the same lock file (`paths.queue_lock`), so the two never run at once:

1. wait for the lock and a quiet machine (no other suite running);
2. fetch the remote and fast-forward the checkout's main to main as pushed (``--ff-only``); one that cannot is
   nacked, not counted;
3. take the batch: the run's gap and up to `batch` - 1 more approved gaps no run holds (the pool `batch` in
   run/pools.json, 1 to start, which is one gap a run; dev/bin/pools.py), walked in rank order and each dry-merged
   onto the batch so far (`git merge-tree`, picks()): one that conflicts with main is sent back and takes no slot, one
   that conflicts only with a batch-mate stays `approved`; a batch that comes back empty says why (emptied()). A
   stacked gap (`stacked_on: [{gap, sha}]`, written by its implementor) whose base is not merged on main (that sha
   not an ancestor of main) brings the base in below it, bottom-up, at any depth: approved and held by no run, the
   whole stack in or none of it (stack()). The run's own gap whose base cannot come, or whose stack does not fit the
   batch, is given back uncounted (10m) with the reason, never counted as an empty batch; a batch-mate's is skipped and
   stays `approved`. With no gap stacked, the batch is as before. The
   others stay `approved` until the run settles them, and the run's start is kept in run/queue.json (`running`), so a
   run killed part way (SIGKILL, a crash) strands nothing: the next run puts main back where it began and takes them
   again;
4. merge each into a clean main of the checkout in turn (`--no-ff`), the tree dry-merged; a conflict (a re-merge
   after bisecting) is undone and sent back;
5. ruff, then the unit suite (-n 8) and the four browser files (-n 4) at once under scripts/suite_watch.py (the first
   to fail stops the other), then demo_check, once for the batch; a browser test skipped counts as a failure. The
   tests in tests/quarantine.txt are deselected from unit and browser and run after them (`alone`), their results
   recorded and never blocking (fac.beside()). With `[suites] queue_container` (the default) each suite runs in a
   container of the agent image on `[agents] queue_cpuset` with no network (agents.queued); one that does not start
   fails the run (agents.NotStarted: undone, no gap blamed), and a stopped run kills its containers by name. A suite
   whose log stops growing, or that runs too long (fac.limits()), is stopped as a stall: undone, the next batch
   halved, no gap blamed until one alone stalls fac.STALLS_MOST times (stalled()). After unit and browser,
   `[suites] host` (the sandbox's tests, which skip in the container) runs on the Mac, never boxed, as a suite like
   the others (its log `<tag>-host.txt`; red bisects); empty, the step is off. The outer shell's exit 126 or 127
   is a step that did not start (NotStarted; a pytest missing behind uv exits 1: red), and a test it skips that the
   unit run skipped too fails it (nowhere());
6. green: `gap.merged` for each, and one push to origin main of the batch's last merge asked for as the gated action
   `push-main` (one approval for the batch; held for the coordinator; the upgrader follows pushed origin/main). Red:
   when its 1 to 3 named tests each pass alone on the red tree twice and the suites it did not finish pass, it lands as
   a flake (excusable(), excused()). Else, before any gap is blamed, the named tests run on main (`pre`) alone, in the
   same container and settings (on_main()): failing there and on a re-run, the failure is main's: no gap is sent back
   (all stay `approved`, the own gap's lease given back uncounted), run/queue.json holds `main_red`, an intervention
   of class queue names main and the tests (a pipeline situation), and no batch is taken until they pass alone on
   main's head, are quarantined or gone there, or the coordinator remedies it (main_red()); failing, then passing,
   each is a flake seen. Else (they pass on main, a test main lacks, a run that cannot tell, a failure naming no
   test) it is bisected to the first failing merge (land(): in parallel rounds of the named tests, or of ruff for a
   ruff failure, on every prefix at once; else serially, on the failing tests alone when the run named any), which goes
   on to flake triage with what failed (`queue-failed`) and the rest lands, each merge only on a full green run. A
   failing merge found in a round costs that round (every prefix's named tests at once: minutes, not a full run) and
   shares the one full run on the survivors; found serially, up to 2 ceil(log2 m) runs; a later merge whose
   `stacked_on` reaches the failing one (at any depth), or one whose merge (again) was sent back, is given back to
   `approved` uncounted, never merged without it (it holds its commits). Past its time allowance (allowance()) a
   run starts no suite run or round: the proven prefix lands, the rest back uncounted; a run that settled none of its batch
   halves the next run's batch (run/queue.json `cap`, cleared once one is). On any error or stop, main is undone with
   `git reset --keep`. The push is asked under the run's own gap's lease, and is not fenced by it (`fenced: false`:
   it pushes only that commit, only as a fast-forward), so it runs once approved
   whatever became of that lease. When that gap does not land, it waits at `push-pending` and its outcome is said
   once the push settles (tell()), never back at `approved` meanwhile.

While a push waits (run/queue.json, read under the queue's lock before a gap is taken; unreadable, the same), a run
takes no gap: it gives its lease back, uncounted, and says nothing of it.

It merges exactly the commit the reviewer approved, fetched from the drop (never the branch's name), and refuses a
branch that moved since. A conflict is a failed gate (the second parks).

`queue.py push SHA` is the action's command: it pushes exactly that commit to the remote's main, never anything else.
`queue.py settle` (the block push-settler) settles a push that ran, failed or was denied with no run started."""

from __future__ import annotations

import fcntl
import json
import re
import shlex
import shutil
import subprocess
import sys
import threading  # never concurrent.futures: this file is named queue.py, which shadows the stdlib queue it imports
import time
from pathlib import Path

sys.dont_write_bytecode = True
import agents  # noqa: E402
import fac  # noqa: E402
import flakes  # noqa: E402
import pools  # noqa: E402
import prefixes  # noqa: E402
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


def suites(cfg: dict, repo, tag: str, logs, pre: str = "HEAD", only: tuple | None = None) -> dict:
    """ruff; then unit and browser at once; then host (when set); then demo (under the other two's load its pages drew
    nothing). The first to fail is the one reported; it stops its sibling (killed, `stopped_by` it, its own failure
    unsaid) and the later steps. With `[suites] queue_coverage`, the
    unit run is traced into run/coverage/<tag> and scored with ``pre``'s script (coverage_kept). The quarantine is
    main's (``pre``), never the batch's: a branch's own line in tests/quarantine.txt holds nothing back in its run.
    ``only``: just those suites (the rest of a run whose failures were excused, excused())."""
    held = fac.quarantine(repo, pre)

    def one(name: str) -> dict:
        log = logs / f"{tag}-{name}.txt"
        cov = fac.run_dir(cfg, "coverage") / tag \
            if name == "unit" and cfg["suites"].get("queue_coverage") is True else None
        cmd = fac.deselected(name, f"ERGOSTAT_COVERAGE={shlex.quote(str(cov))} {cfg['suites']['unit']}", held) \
            if cov else None
        rc, secs = fac.suite(cfg, name, repo, log, slot=False, command=cmd, quarantined=held,
                             box="host" if name == "host" else "queue")  # (lock: slot; host: limited, on the Mac)
        text = log.read_text()
        if name == "host" and rc in (126, 127):      # (lesson-3: a step that could not start is never its result)
            raise agents.NotStarted(f"the host suite did not start (exit {rc}): {text[-400:].strip()}")
        skipped = len(re.findall(r"^SKIPPED", text, re.M)) if name == "browser" else 0
        lost = nowhere(text, logs / f"{tag}-unit.txt") if name == "host" else []
        got = {"rc": rc, "seconds": round(secs), **({"skipped": skipped} if skipped else {}),
               **({"nowhere": lost} if lost else {}), **({"counts": fac.counts(text) or "unknown"} if name in PYTEST else {})}
        if cov:
            got["coverage"] = coverage_kept(cfg, repo, cov, rc, pre)
        if rc or skipped or lost:
            got["failure"] = {"failed": name, "tests": fac.failed_tests(text), "log": str(log),
                              "tail": text[-2000:] + "".join(f"\nran nowhere: {x}" for x in lost)}
        return got

    def together(names: tuple) -> dict:
        got, ts, first, said = {}, [], [], threading.Lock()
        for n in names:
            def body(n=n):
                try:
                    r = one(n)
                except BaseException as e:             # (raised again below, in the queue's own thread)
                    r = e
                with said:                             # (which failed first, decided and kept in one hold)
                    if isinstance(r, dict) and r.get("failure") and first:
                        r = {k: v for k, v in r.items() if k != "failure"} | {"stopped_by": first[0]} \
                            | ({"counts": "unknown"} if n in PYTEST else {})      # (killed: its counts unsaid)
                    elif isinstance(r, BaseException) or r.get("failure"):   # (a container that did not start:
                        first.append(n)                                          # its sibling is stopped too)
                    got[n] = r
            ts.append(threading.Thread(target=body, daemon=True))
            ts[-1].start()
        try:
            while any(t.is_alive() for t in ts):
                for t in ts:
                    t.join(0.5)
                if first:                              # again each pass: a sibling's suite started after the failure
                    fac.stop_suites()
        except BaseException:                          # stopped: the suites' process groups go with the queue
            fac.stop_suites()
            raise
        for n in names:
            if isinstance(got[n], BaseException):
                raise got[n]
        return {n: got[n] for n in names}

    def quarantined(tests: list[str]) -> None:
        fac.suite(cfg, "alone", repo, logs / f"{tag}-quarantined.txt", slot=False, box="queue", tests=tests)

    out = {}
    for step in (("ruff",), ("unit", "browser"), ("host",), ("demo",)):
        if not (step := tuple(n for n in step if (only is None or n in only) and (n != "host" or host_on(cfg)))):
            continue
        got = together(step)
        if step[0] == "unit":                          # the quarantined tests after them, whatever they said
            fac.beside(held, logs / f"{tag}-quarantined.txt", quarantined)
        for name in step:
            failure = got[name].pop("failure", None)
            out[name] = got[name]
            if failure and "failed" not in out:
                out.update(failure)
        if "failed" in out:
            break
    return out


def present(repo, head: str, tests: list[str]) -> list[str]:
    """The named tests that exist at ``head``: a test a later merge adds is not on the prefixes before it."""
    keep, files = [], {}
    for t in tests:
        path, *rest = t.split("::")
        if path not in files:
            r = subprocess.run(["git", "-C", str(repo), "show", f"{head}:{path}"], capture_output=True, text=True)
            files[path] = r.stdout if r.returncode == 0 else ""
        if rest and re.search(rf"\bdef {re.escape(rest[-1].split('[')[0])}\b", files[path]):
            keep.append(t)
    return keep


def named(cfg: dict, repo, tag: str, logs, failed: dict) -> dict | None:
    """Only the tests a red run named, on the checkout as it is (`[suites] rerun`, serial, `-rA`), for bisecting. Red
    when one of them fails (said as the suite that named them); green only when the run passed and said PASSED for
    every one asked. A test whose `def` is in the red tree (``failed["tip"]``) and not here was added by a later merge,
    so it cannot fail here and is not asked; green when none is left. Else (a test not found for any other reason, a
    run that could not start) None, and that step runs every suite. It never counts as the green run anything lands on
    (land())."""
    tests, tip = failed["tests"], failed.get("tip")
    if tip:
        tests = [t for t in tests if present(repo, "HEAD", [t]) or not present(repo, tip, [t])]
        if not tests:
            return {"named": {"suite": failed["failed"], "tests": 0, "rc": 0, "seconds": 0, "not_on_this_prefix": True}}
    log = logs / f"{tag}-named.txt"
    rc, secs = fac.suite(cfg, "rerun", repo, log, slot=False, box="queue", tests=[*tests, "-rA"])
    text = log.read_text()
    said = fac.outcomes(text, tests)
    got = {"named": {"suite": failed["failed"], "tests": len(tests), "rc": rc, "seconds": round(secs)}}
    if bad := sorted(t for t, r in said.items() if r == "fail"):
        return got | {"failed": failed["failed"], "tests": bad, "tail": text[-2000:], "log": str(log)}
    return got if rc == 0 and set(said.values()) == {"pass"} else None


def prefixed(cfg: dict, repo, heads: list[str], failed: dict, tag: str, logs) -> list[tuple[str, list[str], dict]]:
    """One parallel round: ``failed``'s check on every one of ``heads`` at once (prefixes.run_all, its logs in
    ``logs``): its named tests (`[suites] rerun`, `-rA`), or ruff when it named none. Each (pass, fail or unknown; the
    tests failing; run_all's result), read from the whole log as named() reads: fail on a test's FAILED or ERROR line
    (ruff: its exit); pass only on rc 0 and a PASSED line for each test; else unknown, never a pass (lesson-3). Each
    prefix is asked only the tests it has: one a later merge adds cannot fail before it. A named test found on no prefix
    (not written as a plain `def`) is asked of every prefix, as it cannot be told where it starts."""
    tests = failed.get("tests") or []
    logs.mkdir(parents=True, exist_ok=True)
    here = [present(repo, h, tests) for h in heads] if tests else [[] for _ in heads]
    unseen = [t for t in tests if not any(t in x for x in here)]
    here = [[*x, *unseen] for x in here]

    def asked(i: int, work) -> int:
        if not here[i]:
            prefixes.log_of(logs, tag, i).write_text("none of the named tests is on this prefix\n")
            return 0
        return prefixes.suite(cfg, "rerun", logs, tag, tests=[*here[i], "-rA"])(i, work)

    check = asked if tests else prefixes.suite(cfg, "ruff", logs, tag)
    out = []
    for i, r in enumerate(prefixes.run_all(cfg, repo, heads, check, tag, logs)):
        said = fac.outcomes(Path(r["log"]).read_text(errors="replace"), here[i]) if r["result"] != "unknown" else {}
        bad = sorted(t for t, v in said.items() if v == "fail")
        ok = r["result"] == "pass" and set(said.values()) <= {"pass"} and len(said) == len(here[i])
        out.append(("fail", bad, r) if bad or (not tests and r["result"] == "fail") else
                   ("pass", [], r) if ok else ("unknown", [], r))
    return out


EXCUSE_MOST = 3                                         # more failed tests than this in one run is not a flake
NEVER_EXCUSED = ("tests/test_page_polling.py",)         # (dynamics-open-dom-growth: is it a leak?)
SUITES = ("ruff", "unit", "browser", "host", "demo")
PYTEST = ("unit", "browser", "host")                    # the suites whose pytest counts are kept (ruff, demo: none)
SKIP = re.compile(r"^SKIPPED \[\d+\] (\S+:\d+): (.*)$", re.M)     # pytest -rs: one line a skip's place and reason
EXTERNAL = re.compile(r"\bERGOSTAT_\w+_URL\b|^spends money\b|^no Chromium to drive\b|^could not import 'playwright\b"
                      r"|^needs Docker and the agent image\b|^no \d+ free ports in\b")  # the stated external needs in use
COUNTED = re.compile(r"\b\d+ skipped\b")


def host_on(cfg: dict) -> bool:
    """`[suites] host`, the tests the queue's container cannot run (the sandbox's), on the Mac: empty or absent, off."""
    return bool(str(cfg["suites"].get("host") or "").strip())


def nowhere(host: str, unit_log) -> list[str]:
    """The host step's skips (`path:line: reason`) the container's unit run skipped too, but those of a stated
    external need (EXTERNAL): tests that ran in neither place. A unit log that is missing, or that counts skips
    without naming them (no `-rs`), cannot tell, so each host skip counts; so does a host log that does the same."""
    try:
        unit = unit_log.read_text()
    except OSError:
        unit = ""
    theirs = {w for w, _ in SKIP.findall(unit)}
    blind = not unit or (COUNTED.search(unit) and not theirs)
    out = sorted(f"{w}: {r}" for w, r in SKIP.findall(host) if not EXTERNAL.search(r) and (blind or w in theirs))
    return out + (["skips counted but not named: run the host step with -rs"]
                  if COUNTED.search(host) and not SKIP.search(host) else [])


def summed(got: dict) -> dict:
    """A landed run's pytest counts, summed over the pytest suites that ran (``suites``, by name); "unknown" if any of
    them is or says none. A suite not run by rule (counts "not_run") or not in the run at all is neither."""
    ran = [n for n in PYTEST if isinstance(got.get(n), dict) and got[n].get("counts") != "not_run"]
    each = [got[n].get("counts") for n in ran]
    if not all(isinstance(c, dict) for c in each):
        return {"counts": "unknown", "suites": ran}
    return {"counts": {k: sum(c.get(k, 0) for c in each) for k in fac.COUNTS}, "suites": ran}


def excusable(red: dict) -> bool:
    """A red run whose failures may be flakes: it named 1 to EXCUSE_MOST tests, none of NEVER_EXCUSED, and its
    failed suite skipped none (a skipped page test is a failure, never excused)."""
    tests = red.get("tests") or []
    return bool(red.get("failed")) and 0 < len(tests) <= EXCUSE_MOST and not red.get(red["failed"], {}).get(
        "skipped") and not any(t.split("::")[0] in NEVER_EXCUSED for t in tests)


def passed(alone: dict | None) -> bool:
    """A named() run green on every test it was given (None: it could not tell, a failure)."""
    return alone is not None and not alone.get("failed")


def rest(red: dict) -> tuple:
    """The suites a red run did not finish: stopped by its failure, or never reached."""
    return tuple(n for n in SUITES if n not in red or red[n].get("stopped_by"))


def excused(red: dict, more: dict, tag: str, gaps: list[str]) -> dict:
    """A red run whose failed tests each passed alone twice on its tree, and ``more`` (the suites it did not finish):
    red again when ``more`` is; else green, each test a flake seen (flake/<test>, its run, suite and log)."""
    if more.get("failed"):
        return more
    for t in red["tests"]:
        flakes.say("flake.seen", t, gaps=gaps, times=1, seen_at=time.time(), run=tag, suite=red["failed"],
                   passed_alone=2, log=red["log"])
    keep = {k: v for k, v in red.items() if k not in ("failed", "tests", "tail", "log", "named")}
    return keep | more | {"excused": {"suite": red["failed"], "tests": red["tests"], "log": red["log"]}}


COVERAGE_KEEP = 5                                       # coverage reports kept under run/coverage/, by their seq
COVERAGE_RUN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}-\d{8}T\d{6}Z(-\d+)?$")  # (a run_tag; -N: a bisecting run)


def coverage_made(repo, cov, pre: str) -> str:
    """scripts/coverage_report.py as it is in ``pre`` (main before the merge, so a branch never scores its own
    coverage), run on the merged checkout. "reported", or why not; a timeout or a missing script is a "no report"."""
    try:
        script = fac.git(repo, "show", f"{pre}:scripts/coverage_report.py")
    except (RuntimeError, subprocess.SubprocessError) as e:
        return f"no report: main's scripts/coverage_report.py unreadable ({str(e)[-200:]})"
    path = cov / "coverage_report_main.py"
    try:
        path.write_text(script + "\n")
        r = subprocess.run([sys.executable, str(path), str(cov), "--root", str(repo)], cwd=repo, capture_output=True,
                           text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return "no report: timed out"
    except OSError as e:
        return f"no report: {e}"
    finally:
        path.unlink(missing_ok=True)
    return "reported" if r.returncode == 0 else f"no report: {r.stderr.strip()[-300:]}"


def coverage_kept(cfg: dict, repo, cov, rc: int, pre: str = "HEAD") -> str:
    """The unit run's coverage report made (coverage_made) and the last COVERAGE_KEEP kept, by the seq stamped in each
    (never a file's time); a red run's worker files, a run that made no report, and an unreadable report (which would
    hold the measure at no value) removed at once. It never fails the queue: the measure is read by measure.py, which
    has no value without a fresh report."""
    said = "not reported: the unit suite failed"
    if not rc:
        said = coverage_made(repo, cov, pre)
    top = fac.run_dir(cfg, "coverage").resolve()
    seqs = {}
    for d in top.iterdir():
        if not (d.is_dir() and COVERAGE_RUN.match(d.name) and d.resolve().parent == top):
            continue                                    # (only what this made, by name)
        try:
            seqs[d] = int(json.loads((d / "coverage.json").read_text())["seq"])
        except (OSError, ValueError, KeyError, TypeError):
            seqs[d] = -1                                # (no readable report: removed now)
    good = sorted((d for d in seqs if seqs[d] >= 0), key=lambda d: (seqs[d], d.name))
    for d in good[:-COVERAGE_KEEP] + [d for d in seqs if seqs[d] < 0] + ([cov] if said != "reported" else []):
        shutil.rmtree(d, ignore_errors=True)
    return said


# ---- the queue's own state: the merge whose push is not settled yet, and a block the coordinator must lift

class Unreadable(Exception):
    """run/queue.json is there and cannot be read: the queue takes no gap (it cannot tell whether a push waits)."""


def state(cfg: dict) -> dict:
    p = fac.run_dir(cfg) / "queue.json"
    try:
        st = json.loads(p.read_text()) if p.exists() else {}
    except (OSError, ValueError) as e:
        raise Unreadable(f"run/queue.json cannot be read ({type(e).__name__})") from None
    if not isinstance(st, dict):
        raise Unreadable("run/queue.json is not a map")
    return st


def save(cfg: dict, st: dict) -> None:
    p = fac.run_dir(cfg) / "queue.json"
    tmp = p.with_suffix(".new")
    tmp.write_text(json.dumps(st, indent=1))
    tmp.replace(p)


def block(cfg: dict, st: dict, why: str) -> str:
    """Stop the queue and ask the coordinator: an intervention, open until they record it remedied."""
    iid = f"intervention/queue-{time.strftime('%Y%m%d-%H%M%S')}"
    st["blocked"] = {"why": why, "intervention": iid, "at": time.time()}
    save(cfg, st)                                      # saved, then said: a run killed between says it at most once
    fac.say("intervention.recorded", iid, reason=f"the merge queue stopped: {why}", recorded_at=time.time(),
            **{"class": "queue"})
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
    """A gap's outcome said, but the run's own gap's kept back: a batch that lands without it asks its push under that
    gap's lease, and the gap waits at `push-pending` until the push settles, not taken by the implementor or flake
    triage meanwhile. Said at the run's end, or once its push settles (``then`` in the pending record, release())."""
    if gid == HELD["own"]:
        HELD["said"].append({"event": event, "item": gid, "data": data})
    else:
        fac.say(event, gid, **data)


def release(p: dict | None) -> None:
    for e in (p or {}).get("then") or []:
        fac.say(e["event"], e["item"], **e["data"])


def waits(cfg: dict) -> str | None:
    """Why the queue can take no gap now, read only: a push held for approval, or the queue blocked. Its sensor
    (`queue.py waiting`) keeps the merge queue from leasing gaps only to give them back; a run decides again from the
    file itself, under the queue's lock (take())."""
    try:
        st = state(cfg)
    except Unreadable as e:
        return str(e)
    if st.get("blocked"):
        return None if action_state(st["blocked"]["intervention"]) == "remedied" else "blocked"
    p = st.get("pending")
    if p and p.get("action") and action_state(p["action"]) in ("held", "requested", "approved"):
        return f"the push of {p['sha'][:12]} waits"
    return None


class Waits(str):
    """settle()'s answer while the last push waits for approval: take() puts its gap off for a minute, not ten (the
    push-waiting sensor keeps the queue from leasing meanwhile), so the next batch starts soon after the push runs."""


def settleable(cfg: dict) -> bool:
    """The sensor push-settleable (`queue.py settleable`): a pending push that ran, was denied, failed or cannot be
    read, or a block remedied: what push-settler settles. Unreadable: 1, so its runs fail where they can be seen."""
    try:
        st = state(cfg)
    except Unreadable:
        return True
    return bool(st.get("pending") or st.get("blocked")) and not waits(cfg)


def settle(cfg: dict, repo) -> str | None:
    """Before a merge: what became of the last merge's push. None when the queue may go on; else why it waits.
    Pushed: done. Held: wait (one unpushed merge at a time, so a denial undoes only its own). Denied: the merge undone
    (`reset --keep` to before it) and its gap sent back. Failed, or an undo that fails: the queue blocked, with an
    intervention, until the coordinator records it remedied (a failed push's held outcome is said at once)."""
    st = state(cfg)
    if st.get("blocked"):
        iid = st["blocked"]["intervention"]
        if action_state(iid) != "remedied":
            return f"blocked until {iid} is remedied: {st['blocked']['why']}"
        st.pop("blocked")
        p = st.pop("pending", None)                    # the coordinator's remedy settled that merge, whatever its push
        save(cfg, st)                                  # (saved before said, here and below: said at most once)
        for gid in pushed(p):
            fac.say("gap.push-settled", gid, push="settled by the coordinator", settled_by=iid,
                    settled_at=time.time())
        release(p)
        return None
    p = st.get("pending")
    if not p:
        return None
    now = action_state(p["action"]) if p.get("action") else p.get("known") or "unknown"
    if now == "held" and not p.get("action"):
        return block(cfg, st, f"the push of {p['sha'][:12]} is held, and its action's id was not said: "
                              f"it cannot be followed")
    if now == "unknown" and p.get("action") and p.get("unread", 0) < 2:   # a read that failed: blocked the third time
        p["unread"] = p.get("unread", 0) + 1
        save(cfg, st)
        return f"the push of {p['sha'][:12]} cannot be read ({p['unread']} of 3)"
    if now == "ran":
        st.pop("pending")
        save(cfg, st)
        for gid in pushed(p):
            fac.say("gap.pushed", gid, pushed_at=time.time(), push="pushed")
        release(p)
        return None
    if now == "denied":
        head = fac.git(repo, "rev-parse", "HEAD")
        if head != p["sha"] or not fac.git_ok(repo, "reset", "-q", "--keep", p["pre"]):
            return block(cfg, st, f"the push of {p['sha'][:12]} was denied, and its merge could not be undone "
                                  f"(main at {head[:12]})")
        st.pop("pending")
        save(cfg, st)
        for gid in pushed(p):                          # one approval for the batch: a denial sends back all of it
            fac.say("gap.sent-back", gid, sent_back_by="queue", push="denied",
                    findings=[f"the push of its merge ({p['sha'][:12]}) was denied: the merge is undone"])
        release(p)
        return None
    if now in ("held", "requested", "approved"):
        return Waits(f"the push of {p['sha'][:12]} ({p['gap']}) is {now}")
    then = {"then": p.pop("then", None)}               # failed: the held outcome said now, not once it is remedied
    why = block(cfg, st, f"the push of {p['sha'][:12]} is {now}" + (f": {p['said'][-200:]}" if p.get("said") else ""))
    release(then)
    return why


def settle_alone(cfg: dict) -> str | None:
    """`queue.py settle` (the block push-settler, every few minutes): a push that ran, failed or was denied is settled
    with no gap approved to start a run. Under the queue's lock, taken only if free: a run holding it settles the push
    itself (take()), and each re-reads run/queue.json inside the lock, so the outcome is applied once. Why it did
    nothing, or None."""
    lock = fac.path(cfg, "queue_lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    with open(lock, "a") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return "a run holds the queue's lock"
        try:
            repo = fac.path(cfg, "checkout")
            return recover(cfg, repo) or settle(cfg, repo)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


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
    try:
        r = subprocess.run(["git", "-C", str(repo), "merge-tree", "--write-tree", "--name-only", "--no-messages", "-z",
                            onto, sha], capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"git merge-tree {onto[:12]} {sha[:12]}: timed out after 600 s") from e
    m = re.match(r"([0-9a-f]{40,64})[\0\n]", r.stdout)
    if r.returncode not in (0, 1) or not m:
        raise RuntimeError(f"git merge-tree {onto[:12]} {sha[:12]}: {r.stderr.strip()[-400:]}")
    if r.returncode:                                      # (a conflict always names something: the exit code decides)
        return None, sorted({p for p in r.stdout[m.end():].split("\0") if p}) or ["(git named no file)"]
    return fac.git(repo, "commit-tree", m.group(1), "-p", onto, "-p", sha, "-m", msg), []


def message(g: dict) -> str:
    return f"Merge branch '{fac.git_branch(fac.branch_of(g))}'\n\n{fac.TRAILER}"


SENT = "it was sent back"   # (the start of an empty batch's why when the run's own gap's outcome is said already)


def picks(cfg: dict, repo, gap: dict, n: int, pre: str) -> tuple[list[tuple[dict, str]], str, str]:
    """The batch, its dry-merged head, and why it is empty ("" when it is not), from the walk itself: the run's own gap
    sent back (SENT, and what for), or its dry merge failing only with batch-mates on both walks, or (never expected)
    a walk that never reached it. The run's own gap and the approved gaps no run holds (only its own when n is
    1), walked in rank order (the groomer's rank, then when approved), each dry-merged onto the batch so far, until n
    merge. A gap that conflicts with main (`pre`) is sent back at once, a failed gate, and takes no slot; one that
    conflicts only with a batch-mate stays `approved`, no gate failed. The run's own gap is in its batch unless it is
    sent back: the last slot is kept for it, and if it conflicts only with batch-mates the walk is made again with it
    first, so its lease, which the batch's push is asked under, is never given back while others land; if it is sent
    back, the walk is made again in rank order, so the gaps passed over for its slot can fill the batch. The others
    stay `approved` until the run settles them (merged, sent back, queue-failed): a run killed part way leaves them to
    be taken again, and the queue's pool is 1, so no other run takes them meanwhile. A dry merge git cannot make
    (RuntimeError) fails the run after some gaps may have been sent back: those stand, the rest stay `approved`. Each
    gap is walked as its stack (stack(): its bases not on main, bottom-up, then it), all of it dry-merged or none, the
    slots kept for the own gap's whole stack; an own gap whose stack cannot come, does not fit ``n``, or lost a base
    sent back in the walk gives an empty batch, STACKED and why."""
    def key(g: dict) -> tuple:
        rank = g["fields"].get("rank")                    # (rank 0 is a rank: only none is unranked)
        return (10**9 if rank is None else rank, float(g["fields"].get("approved_at") or 0), g["id"])
    pool = {g["id"]: g for g in fac.items("gap", "approved") if g["id"] != gap["id"]
            and not (g["fields"].get("lease") or {}).get("holder")} if n > 1 or bases(gap) != [] else {}
    others, pool[gap["id"]] = list(pool.values()) if n > 1 else [], gap
    units = {g["id"]: stack(repo, g, pool, pre, n) for g in [gap, *others]}   # bases bottom-up, then the gap
    if isinstance(mine_unit := units[gap["id"]], str) or len(mine_unit) > n:
        return [], pre, f"{STACKED}: " + (mine_unit if isinstance(mine_unit, str)
                                          else f"its stack of {len(mine_unit)} does not fit a batch of {n}")
    others = [g for g in others if not isinstance(units[g["id"]], str)]   # (its base cannot come: stays approved)
    shas: dict = {}                                       # each gap's reviewed commit; None once sent back
    why = ["its walk never reached it"]                   # what kept the run's own gap out (never none: lesson-3)
    out = lambda x: x["id"] in shas and not shas[x["id"]]                 # noqa: E731

    def walk(order: list[dict]) -> tuple[list[tuple[dict, str]], str] | None:
        batch, head, own = [], pre, False
        for g in order:
            mine, inb = g["id"] == gap["id"], {x["id"] for x, _ in batch}
            unit = [x for x in units[g["id"]] if x["id"] not in inb]
            kept = [x for x in mine_unit if x["id"] not in inb and all(x is not y for y in unit)] \
                if not own and not any(out(x) for x in mine_unit) else []   # the slots kept for the own gap's stack
            if not unit or len(batch) + len(unit) + len(kept) > n:
                continue                                  # (full, or the last slots kept for the run's own gap)
            got, top = [], head
            for x in unit:                                # a stack all in, or none of it
                if x["id"] not in shas:
                    shas[x["id"]], no = reviewed(cfg, repo, x)
                    if not shas[x["id"]]:
                        tell("gap.sent-back", x["id"], sent_back_by="queue", findings=[f"not merged: {no}"])
                        why[0] = f"{SENT}: not merged: {no}" if x is gap else why[0]
                if not shas[x["id"]]:
                    break
                made, files = dry(repo, top, shas[x["id"]], message(x))
                if made:
                    got.append((x, shas[x["id"]]))
                    top = made
                    continue
                onmain = files if top == pre else dry(repo, pre, shas[x["id"]], message(x))[1]
                if onmain:
                    refuse(cfg, x, onmain, time.time())
                    shas[x["id"]] = None
                    why[0] = f"{SENT}: conflicts with {cfg['git']['base']}: {' '.join(onmain)}" if x is gap else why[0]
                elif mine:                                # only with batch-mates: walked again, the own gap first
                    why[0] = f"its dry merge failed only with batch-mates on both walks ({' '.join(files) or 'no file'})"
                    return None
                break
            else:
                batch += got
                head, own = top, own or any(x is gap for x in unit)
        return batch, head
    order = sorted([gap, *others], key=key)
    got = walk(order) or walk([gap, *[g for g in order if g is not gap]]) or ([], pre)
    if (lost := [x["id"] for x in mine_unit if out(x)]) and not out(gap):
        return [], pre, f"{STACKED}: its base {lost[0]} was sent back"
    if out(gap) and len(got[0]) < n:
        got = walk(order)                                 # own gap sent back: the gaps passed over for its slot too
    return *got, "" if got[0] else why[0]


STACKED = "its stack cannot come along"   # (an empty batch's why that is never counted: emptied())


def bases(g: dict) -> list[tuple[str, str]] | None:
    """A gap's `stacked_on` as (base gap id, sha) pairs, as the implementor wrote it; None when it cannot be read."""
    on = g["fields"].get("stacked_on") or []
    if not isinstance(on, list) or not all(isinstance(e, dict) and isinstance(e.get("gap"), str) for e in on):
        return None
    return [(e["gap"] if e["gap"].startswith("gap/") else f"gap/{e['gap']}", str(e.get("sha") or "")) for e in on]


def stack(repo, g: dict, pool: dict, pre: str, most: int, seen: tuple = ()) -> list[dict] | str:
    """``g``'s bases not merged on main (a `stacked_on` sha not an ancestor of ``pre``, or not a commit id), each from
    ``pool`` (the approved gaps no run holds), bottom-up, then ``g``; or why they cannot come along: a base not in
    ``pool``, a stack that loops or is deeper than ``most``, a `stacked_on` that cannot be read (lesson-3)."""
    if (on := bases(g)) is None:
        return f"{g['id']}'s stacked_on cannot be read"
    unit: list[dict] = []
    for bid, sha in on:
        if re.fullmatch(r"[0-9a-f]{40}", sha) and fac.git_ok(repo, "merge-base", "--is-ancestor", sha, pre):
            continue
        if bid == g["id"] or bid in seen or len(seen) >= most:
            return f"{g['id']}'s stack loops through {bid} or is deeper than a batch of {most}"
        if bid not in pool:
            return f"its base {bid} is not approved, or a run holds it"
        if isinstance(got := stack(repo, pool[bid], pool, pre, most, (*seen, g["id"])), str):
            return got
        unit += [x for x in got if all(x is not y for y in unit)]
    return [*unit, g]


def reaches(x: dict, gid: str, batch: list) -> bool:
    """``x``'s `stacked_on` reaches ``gid`` at any depth, through the batch's gaps (unreadable: it does)."""
    by, todo, seen = {g["id"]: g for g, _ in batch}, [x["id"]], set()
    while todo:
        if (on := bases(by.get(todo.pop(), {"fields": {}}))) is None:
            return True
        if gid in (new := {b for b, _ in on} - seen):
            return True
        seen |= new
        todo += new
    return False


EMPTY_MOST = 3      # empty batches on one reviewed commit before its gap is sent back (lesson-4: never taken forever)


def emptied(cfg: dict, gap: dict, why: str) -> None:
    """The run's own gap when its batch came back empty. Sent back already (SENT): that is its outcome (a nack would
    give it back to `approved` over it). Else counted, per reviewed commit (`empty_batches`, so a new commit starts
    again), and given back with the reason (`after` 10m), uncounted by its lease; the EMPTY_MOST-th time sent back
    instead, a failed gate, with the reason as its finding. Read and written under the queue's lock, for the run's
    own leased gap (the queue's pool is 1): nothing else counts it meanwhile."""
    if why.startswith(SENT):
        return
    if why.startswith(STACKED):                           # (its stack waits for its bases: never counted)
        fac.nack(f"queue: {why}", after="10m", count=False)
        return
    f = gap["fields"]
    was = f.get("empty_batches") if isinstance(f.get("empty_batches"), dict) else {}
    k = (int(was.get("n") or 0) if was.get("head") == f.get("reviewed_head") else 0) + 1
    fac.say("gap.measured", empty_batches={"head": f.get("reviewed_head"), "n": 0 if k >= EMPTY_MOST else k},
            empty_batch=why)
    if k >= EMPTY_MOST:
        refuse(cfg, gap, [], time.time(), [f"its queue batch came back empty {k} times: {why}"])
    else:
        fac.nack(f"queue: its batch came back empty ({k} of {EMPTY_MOST}): {why}", after="10m", count=False)


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


def refuse(cfg: dict, g: dict, files: list[str], began: float, findings: list[str] | None = None) -> None:
    """A gap whose merge conflicts (or ``findings``: why else): sent back, a failed gate (the kill rule's last parks
    it)."""
    findings = findings or [f"conflicts with {cfg['git']['base']}: {' '.join(files)}"]
    if int(g["fields"].get("failed_gates") or 0) + 1 >= fac.kill_after(cfg):          # a conflict is a failed gate too
        fac.say("gap.measured", g["id"], failed_gates=1, findings=findings)
        review.park(cfg, g, f"Failed its gates {fac.kill_after(cfg)} times (the kill rule); the last, in the "
                            f"merge queue: {findings[0]}", "merge-queue", where="queue", kind="kill-rule")
    else:
        tell("gap.sent-back", g["id"], sent_back_by="queue", findings=findings, failed_gates=1, fix_rounds=1,
                queue_wait_hours=waited_hours(g, began))


def lines(repo, before: str, after: str) -> dict:
    """A merge's net lines outside tests/ and docs/, dev/ counted. Both always said, so a merge again never keeps an
    old count; unreadable, the merge stands and its count is unknown (null and why), never 0."""
    try:
        return {"merged_lines": fac.net_lines(repo, before, after, core=False), "merged_lines_error": None}
    except Exception as e:
        return {"merged_lines": None, "merged_lines_error": f"{type(e).__name__}: {e}"[-300:]}


ALLOWANCE_MOST = 150     # minutes: one suite run begun at the allowance still ends inside the block's 3 h timeout


def allowance(cfg: dict) -> float:
    """A run's time allowance in seconds, from its start: [pools] batch_minutes (120 unset); a value not over 0 nor
    at most ALLOWANCE_MOST (NaN too, or not a number) is refused: ValueError, and the run takes no gap (take())."""
    m = float(cfg.get("pools", {}).get("batch_minutes", 120))
    if not 0 < m <= ALLOWANCE_MOST:
        raise ValueError(f"[pools] batch_minutes = {m} is not over 0 and at most {ALLOWANCE_MOST}")
    return 60 * m


class Late(Exception):
    """The run's time allowance is used: no more suite runs (land())."""


def land(cfg: dict, repo, batch: list[tuple[dict, str]], pre: str, began: float, waited: float,
         dried: str = "", until: float | None = None) -> tuple[list, str, list]:
    """Merge the batch onto main in turn and run the suites once. Green: every merge lands. Red: bisected (run again on
    the first half of the merges, then on half of what is left, ...) to the first merge whose prefix fails; that gap
    goes to flake triage with its failures and the commit it was merged onto (its `pre`). A red run that named failing
    tests is bisected on those tests alone (named()) only when they fail alone on the whole red tree too; else (they
    pass there, or it cannot tell), and when it named none, with every suite. A prefix green on every suite
    lands, and the merges after the failing one are merged again onto it and tried as a batch of their own; a prefix
    green on the named tests only lands nothing yet: it is merged again with those after the failing merge, and they
    all land only on a full green run of that tree (the failing gap's `pre` then main's head, `base`, as no commit of
    that prefix lands). Each failing merge found costs at most 2 + 2 ceil(log2 m) runs (m: the merges left; the red
    run, the named tests on its tree, and each step, two when a named run cannot tell). Rounds: when those named tests
    fail alone on the red tree (or ruff failed, with ruff), each bisecting is a parallel round instead: the check on
    every survivor prefix at once (prefixed()). The first failing prefix's last merge is the failing one (the prefixes
    before it passed: nothing lands on them); it is taken out, the survivors merged again, and a round follows at once
    only when a later prefix failed a test it did not (another failing merge); else the full suites run once on the
    survivors, green landing them, red starting again. So one failing merge costs one round, k independent ones k
    rounds, and the batch one full run after them. A round with a prefix that cannot tell (unknown) before its first
    failing one bisects serially, as above, from the prefixes that passed up to that failing one (in a first round,
    the red tree); a first round with none failing (its tree failed them alone just before), serially on the whole
    batch; a later round with none failing, the full run. A test that fails only when two merges are both in
    blames the later one, as the serial bisect does; a later merge failing the same test as the one found is caught by
    the full run. batch_rounds and prefix_runs (the heads checked) are said on each gap's suites_queue. No suite run
    or round starts past
    ``until`` (began + allowance() unset): the bisecting stops there, the prefix a full green run proved lands, and the
    gaps not settled yet are given back, never landed (the third of what it returns), as are the merges after a failing
    one whose `stacked_on` reaches it, or reaches a merge (again) sent back (reaches()). Returns (each gap landing
    with its timing, main's head, the gaps given back, each with why), the checkout's main left at that head. Gaps
    sent on are said so
    here; those landing and those given back, by the caller, once main is settled. A red run whose failed tests may be
    flakes (excusable()) and each pass alone on its tree twice is green once the suites it did not finish pass too: it
    lands with no bisect, each test a flake seen."""
    base, todo, landed, runs, tag = pre, batch, [], [0], fac.run_tag(fac.branch_of(batch[0][0]), began)
    logs, until = fac.run_dir(cfg, "queue"), began + allowance(cfg) if until is None else until

    def go():
        if time.time() > until:
            raise Late

    def run(failed: dict | None = None, every: bool = True, only: tuple | None = None) -> dict | None:
        go()
        runs[0] += 1
        t = tag + (f"-{runs[0]}" if runs[0] > 1 else "")
        got = named(cfg, repo, t, logs, failed) if failed and failed.get("tests") else None
        if got is not None or not every:
            return got
        go()
        runs[0] += bool(failed and failed.get("tests"))   # (a named run that could not tell, then every suite: two)
        return suites(cfg, repo, t, logs, pre, only)

    def timing(g: dict, got: dict) -> dict:
        return dict(queue_wait_hours=waited_hours(g, began), queue_minutes=round((time.time() - began) / 60, 1),
                    lock_and_load_wait_s=round(waited), batch_size=len(batch), batch_id=tag, batch_runs=runs[0],
                    suites_queue=got | {"batch_rounds": rounds[0], "prefix_runs": rounds[1]})

    def parallel(failed: dict, known: int) -> list:
        """A round on the survivors' prefixes past the ``known`` first merges (which passed it): [] when none is left."""
        if known >= len(heads):
            return []
        go()
        rounds[0] += 1
        rounds[1] += len(heads) - known
        return prefixed(cfg, repo, heads[known:], failed, tag, logs / f"{tag}-round-{rounds[0]}")
    counted, back, blamed, out = {}, [], [], []     # counted: each gap's own merge, main before it to it (its last
    #                                                  try); out: the gaps whose merge was sent back (merge())
    rounds, again = [0, 0], None                    # rounds: parallel rounds, prefix runs; again: the next round's
    try:                                            # failure and the merges before it that passed (no full run first)
        while todo:
            fac.git(repo, "reset", "-q", "--keep", base)
            kept, heads, lo, green = [], [], 0, {}         # heads[i]: main with the first i + 1 merges
            for g, sha in todo:
                if lost := next((x for x in out if reaches(g, x, batch)), None):    # its base was not merged: never
                    back.append((g, f"its base {lost} could not be merged in the queue"))   # merged without it
                    continue
                before = fac.git(repo, "rev-parse", "HEAD")
                if merge(cfg, repo, g, sha, began):
                    kept.append((g, sha))
                    heads.append(fac.git(repo, "rev-parse", "HEAD"))
                    counted[g["id"]] = lines(repo, before, heads[-1])
                else:
                    out.append(g["id"])
            tree = lambda c: fac.git(repo, "rev-parse", f"{c}^{{tree}}")          # noqa: E731
            if dried and kept == batch and tree("HEAD") != tree(dried):         # the tree tested is the one dry-merged
                raise RuntimeError(f"the batch's merges differ from its dry merge ({dried[:12]})")
            todo, dried = kept, ""
            if not todo:
                break
            if again:                                # a round found a failing merge: the next round, no full run yet
                (full, known), again = again, None
                red, rounded = full, True
            else:
                known, rounded, red = 0, False, run()
                if excusable(red):                         # each named test alone on the whole red tree, twice
                    alone = run(red, every=False)
                    if passed(alone) and passed(alone := run(red, every=False)):
                        red = excused(red, run(only=rest(red)), tag, [g["id"] for g, _ in todo])
                else:
                    alone = run(red, every=False) if len(todo) > 1 and red.get("tests") else None   # on the red tree
                if not red.get("failed"):
                    landed += [(g, timing(g, red) | counted[g["id"]]) for g, _ in todo]
                    base = heads[-1]
                    break
                if red.get("tests") and not blamed:  # main itself first, before any gap is blamed (on_main())
                    on_main(repo, pre, red, run, tag, [g["id"] for g, _ in todo])
                full = alone if alone and alone.get("failed") else None  # they fail there alone: on them; else full
                full = {**full, "tip": heads[-1]} if full else None      # (a test only later merges add: not asked before)
            hi, more = len(todo), False              # the first lo merges ran green (or none); the first hi red
            if rounded or len(todo) > 1 and (full or red["failed"] == "ruff"):
                got = parallel(full or red, known)
                k = next((i for i, (r, _, _) in enumerate(got) if r != "pass"), None)
                fail = next((i for i, (r, _, _) in enumerate(got) if r == "fail" and i >= (k or 0)), None)
                if rounded and fail is None:
                    continue                         # passed on the whole survivor tree, or none proven red: full run
                if k is not None:                    # (round one all green, though its tree failed alone: serial)
                    lo, green = known + k, {"named": {"round": rounds[0]}}   # (a round's green never lands: base)
                    hi = known + (len(got) if fail is None else fail + 1)    # (round one: the red tree failed it)
                if fail is not None:                 # k == fail: its last merge fails, found; else serial up to it
                    red = {"failed": red["failed"], "tests": got[fail][1], "log": got[fail][2]["log"],
                           "tail": got[fail][2]["tail"], "round": {"round": rounds[0], "prefixes": len(got)}}
                    more = k == fail and any(set(b) - set(red["tests"]) for _, b, _ in got[fail + 1:])
            while hi - lo > 1:                       # (a round that could not tell: today's serial step, for it)
                mid = (lo + hi) // 2
                fac.git(repo, "reset", "-q", "--keep", heads[mid - 1])
                got = run(full)
                lo, hi, red, green = (lo, mid, got, green) if got.get("failed") else (mid, hi, red, got)
            g, onto = todo[hi - 1][0], heads[hi - 2] if hi > 1 else base
            if "named" in green:                     # (that commit is merged again, never landed: main's own is told)
                onto = base
            blamed.append(g["id"])
            gone = [t for t in todo[hi:] if reaches(t[0], g["id"], batch)]   # its descendants: never merged again
            back += [(x, f"its base {g['id']} failed in the queue") for x, _ in gone]
            tell("gap.queue-failed", g["id"], failed_suite=red["failed"], failed_tests=red["tests"], pre=onto,
                 findings=[f"{red['failed']} failed in the queue: {', '.join(red['tests'][:8]) or red['tail'][-300:]}"]
                 + ([f"the first failing merge of a batch of {len(todo)}, found by bisecting" + (
                     f" in parallel round {rounds[0]}" if "round" in red else "")] if len(todo) > 1 else []),
                 **timing(g, red))
            # (hi - 1 == lo: that prefix's run was green)
            if "named" in green:                     # green on the named tests only: merged again with the rest, so it
                todo = todo[:hi - 1] + [t for t in todo[hi:] if t not in gone]   # lands only on a full green
                again = (full, hi - 1) if more else None    # run of the tree it lands as; a round first when a later
                continue                                    # merge failed other tests
            landed += [(x, timing(x, green) | counted[x["id"]]) for x, _ in todo[:hi - 1]]
            base, todo = onto, [t for t in todo[hi:] if t not in gone]
    except Late:                                     # out of time: only a prefix a full green run proved lands
        if lo and green and "named" not in green:
            landed += [(x, timing(x, green) | counted[x["id"]]) for x, _ in todo[:lo]]
            base, todo = heads[lo - 1], todo[lo:]
        back += [(g, "its run's time allowance was used before it was proven") for g, _ in todo]
    fac.git(repo, "reset", "-q", "--keep", base)
    return landed, base, back


class MainRed(Exception):
    """The batch's failing tests fail on main (``pre``) alone, twice: main's failure, no gap's (on_main())."""


def on_main(repo, pre: str, red: dict, run, tag: str, gaps: list[str]) -> None:
    """A red run's named tests on main (``pre``) alone, in the same container and settings (named()). Failing there and
    again on a re-run (or a re-run that cannot tell): MainRed. Failing, then passing: each a flake seen, not main's.
    Passing, or not told (a test main lacks, a run that could not start): bisected as before."""
    fac.git(repo, "reset", "-q", "--keep", pre)
    first = run(red, every=False)
    if not (first and first.get("failed")):
        return
    again = run(first, every=False)
    bad = first["tests"] if again is None else again["tests"] if again.get("failed") else []
    for t in sorted(set(first["tests"]) - set(bad)):
        flakes.say("flake.seen", t, gaps=gaps, times=1, seen_at=time.time(), run=tag, suite=red["failed"],
                   failed_on_main=pre, log=first["log"])
    if bad:
        raise MainRed({"pre": pre, "suite": red["failed"], "tests": bad})


def main_red(cfg: dict, repo) -> str | None:
    """While main is held red (run/queue.json `main_red`): its tests, less those quarantined at main's head now, run
    there alone, but those main's head lacks (lacks(): removed or renamed, they cannot hold it). Passing, or none left:
    cleared and its intervention remedied (None); its intervention remedied by the coordinator: cleared; else (failing,
    a run that could not tell or start, a remedy that cannot be read) why no batch is taken."""
    st = state(cfg)
    if not (r := st.get("main_red")):
        return None
    if action_state(r["intervention"]) == "remedied":     # (as settle() lifts `blocked`: said already, not again)
        st.pop("main_red")
        save(cfg, st)
        return None
    head = fac.git(repo, "rev-parse", "HEAD")
    if tests := [t for t in r["tests"] if t not in fac.quarantine(repo, head) and not lacks(repo, head, t)]:
        fac.wait_quiet(cfg)
        try:
            got = named(cfg, repo, f"main-{head[:12]}-{int(time.time())}", fac.run_dir(cfg, "queue"),
                        {"failed": r["suite"], "tests": tests})
        except agents.NotStarted as e:
            return f"main is held red and its check did not start: {e}"
        if not passed(got):
            return f"main {head[:12]} fails {', '.join(tests[:5])} (held since {r['pre'][:12]})"
    st.pop("main_red")
    save(cfg, st)
    fac.say("intervention.remedied", r["intervention"], remedied_by="queue", remedied_at=time.time(),
            remedy=f"main {head[:12]} passes them" if tests else "they are quarantined or gone from main")
    return None


def lacks(repo, ref: str, test: str) -> bool:
    """``ref`` has no such test: its file is gone, or no `def` of its function (less any `[param]`) is in it."""
    path, _, name = test.partition("::")
    fn = re.escape(name.split("::")[-1].split("[")[0])
    return not re.search(rf"^\s*(async\s+)?def\s+{fn}\s*\(", fac.git(repo, "show", f"{ref}:{path}", check=False), re.M)


def held_by_main(cfg: dict, r: dict) -> None:
    """main fails the batch's tests: no gap blamed (its batch-mates never left `approved`; the own gap's lease given
    back uncounted), main held red in run/queue.json, and one intervention (class queue) naming main and the tests,
    which pipeline-watch raises as a situation (watch.py triggers())."""
    iid = r["intervention"] = f"intervention/queue-main-red-{r['pre'][:12]}-{time.strftime('%Y%m%d-%H%M%S')}"  # (new)
    save(cfg, {**state(cfg), "main_red": r})
    for t in r["tests"]:
        flakes.say("flake.main-broken", t, main=r["pre"], main_broken_at=time.time())
    fac.say("intervention.recorded", iid, recorded_at=time.time(), main=r["pre"], tests=r["tests"], **{"class": "queue"},
            reason=f"main {r['pre'][:12]} fails {', '.join(r['tests'][:5])} alone in the queue's container: the queue "
                   "takes no batch until they pass on main or are quarantined")
    fac.nack(f"queue: main fails {', '.join(r['tests'][:3])}", after="10m", count=False)


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
    started = time.time()                                 # (the block's timeout counts from here: the lock wait too)
    fac.stop_on_term()
    cfg = fac.config()
    gap = fac.read_input()["item"]
    repo = fac.path(cfg, "checkout")
    HELD["own"] = gap["id"]
    try:
        return take(cfg, gap, repo, started)
    finally:                                              # what was kept back and not handed to a pending push
        release({"then": HELD["said"]})


def stalled(cfg: dict, gap: dict, batch: list, pre: str, e: fac.Stalled) -> None:
    """A suite stopped for a limit (fac.limits()) is a stall, not the batch's failure: said on the run's own gap
    (stalled: the suite, the test its log was on, its tail), whose lease is given back uncounted; its batch-mates never
    left `approved`, and the next run takes half as many (at least 1; a settled run clears it: likely, not sure). A stall
    of the own gap alone is counted (`stalls`); its fac.STALLS_MOST-th goes to triage (queue-failed, the stalled test
    as its failed test). Until then nothing goes to fix or triage for it (an outcome already held for it stands)."""
    save(cfg, {**state(cfg), "cap": max(1, len(batch) // 2)})          # (under the queue's lock: take())
    alone = int(len(batch) == 1 and batch[0][0]["id"] == gap["id"])
    fac.say("gap.measured", stalled=e.suite, stalled_why=e.why, stalled_test=e.test, stalled_tail=e.tail,
            stalled_batch=[g["id"] for g, _ in batch], stalls=alone)
    if HELD["said"]:
        return
    n = int(gap["fields"].get("stalls") or 0) + alone
    if alone and n >= fac.STALLS_MOST:
        tell("gap.queue-failed", gap["id"], failed_suite=e.suite, failed_tests=[e.test] if e.test else [], pre=pre,
             findings=[f"{e.suite} stalled {n} times with this gap alone in the queue, on {e.test or 'no named test'}"])
    else:
        fac.nack(f"queue: {e}", after="10m", count=False)


def take(cfg: dict, gap: dict, repo, started: float) -> int:
    """Under the queue's lock throughout: whether a push waits is read from run/queue.json, the gap is taken
    (`gap.queued`), and a push asked for is written there, in one hold, so no run between them takes a gap. Its
    suite runs end at its time allowance from ``started`` (land()): those given back say so in `queue_runs`. A run
    that settled none of its batch (all given back) leaves the next a cap of half its batch (at least 1), so a
    batch out of time before its first finding is not tried again whole: a batch of 1 is one suite run."""
    try:
        until = started + allowance(cfg)
    except (TypeError, ValueError) as e:
        fac.nack(f"queue: {e}", after="10m", count=False)
        return 0
    with fac.queue_lock(cfg):
        if cfg["suites"].get("queue_container", True) is not False:
            agents.sweep_box("queue")                  # a SIGKILLed run's containers (under the lock: none is live)
        try:
            why = recover(cfg, repo) or clean_main(cfg, repo) or settle(cfg, repo) or up_to_date(cfg, repo) \
                or main_red(cfg, repo)
            capped = state(cfg)                            # (read before the gap is taken: unreadable, none taken)
        except Unreadable as e:                        # (it cannot tell whether a push waits: no gap is taken)
            why = str(e)
        if why:
            fac.nack(f"queue: {why}", after="1m" if isinstance(why, Waits) else "10m", count=False)
            return 0
        fac.say("gap.queued", queued_at=time.time(), queue_attempts=1)
        pre = fac.git(repo, "rev-parse", "HEAD")
        n = min(pools.state(cfg)["batch"], pools.most(cfg, "batch"))  # (the ceiling again, at run time)
        cap = capped.get("cap", n)                         # (a cap that is not a count: 1, the smallest batch)
        n = min(n, cap if type(cap) is int and cap >= 1 else 1)
        batch, dried, empty = picks(cfg, repo, gap, n, pre)
        if not batch:
            emptied(cfg, gap, empty)
            return 0
        waited = fac.wait_quiet(cfg)
        began = time.time()
        if fac.git(repo, "rev-parse", "HEAD") != pre:      # (under the lock nothing should move it: never merged onto)
            fac.nack(f"queue: {cfg['git']['base']} moved while the run waited", after="10m", count=False)
            return 0
        save(cfg, {**state(cfg), "running": {"pre": pre, "gaps": [g["id"] for g, _ in batch], "at": began}})
        done = settled = False
        try:
            try:
                landed, merged, back = land(cfg, repo, batch, pre, began, waited, dried, until)
            except fac.Stalled as e:                       # (main undone below; no gap blamed for it)
                stalled(cfg, gap, batch, pre, e)
                return 0
            except MainRed as e:                           # (main undone below; no gap blamed for it)
                held_by_main(cfg, e.args[0])
                return 0
            if not landed:                                 # no push to wait for: the run's own gap's outcome now
                release({"then": HELD["said"]})
                HELD["said"] = []
            for g, why in back:                            # (the others never left approved)
                if g["id"] == gap["id"]:
                    fac.nack(f"queue: {why}", after="1m", count=False)
            done = True                                    # the point of no return: main holds the landed merges
            ids = [g["id"] for g, _ in landed]
            save(cfg, {**state(cfg), "running": {"pre": pre, "gaps": ids, "at": began, "landing": ids}})
            run = {"run": fac.run_tag(fac.branch_of(gap), began), "minutes": round((time.time() - began) / 60, 1),
                   "at": time.time(), "tried": len(batch), "landed": len(landed), "given_back": len(back),
                   **(summed(landed[-1][1]["suites_queue"]) if landed else {})}   # (the green run main ends at)
            # (the whole run, on each of its gaps, for merges-per-hour; given_back: sent back to approved, uncounted)
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
                if settled:                                # none settled: the next run tries half as many
                    st.pop("cap", None)
                    st.update({"cap": max(1, len(batch) // 2)} if len(back) == len(batch) else {})
                save(cfg, st)
        if landed:
            ask(cfg, repo, gap, landed, merged, pre)
    return 0


def ask(cfg: dict, repo, gap: dict, landed: list, merged: str, pre: str) -> None:
    """One gated push for the batch (its last merge holds them all), asked and written as pending under the queue's
    lock. The run's own gap, when it did not land, waits for it (`gap.push-pending`): its lease ends there, not back
    at approved, and its outcome is said once the push settles (release())."""
    try:
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
        if then:
            fac.say("gap.push-pending", gap["id"], push_pending=merged)
        settle(cfg, repo)                                 # a push denied or failed at once is handled now


def push(sha: str) -> int:
    """The action push-main: that commit, and nothing else, to the remote's main (a fast-forward, or refused: never
    forced, so the remote moves only from the main it had, which an approval that came late cannot rewind)."""
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
    if sys.argv[1:2] == ["settleable"]:                # the sensor push-settleable: 1 while push-settler has work
        print(1 if settleable(fac.config()) else 0)
        sys.exit(0)
    if sys.argv[1:2] == ["settle"]:                    # the block push-settler (unreadable: raised, a failed run)
        fac.stop_on_term()
        print(f"settle: {settle_alone(fac.config()) or 'nothing waits'}", file=sys.stderr)
        sys.exit(0)
    sys.exit(push(sys.argv[2]) if sys.argv[1:2] == ["push"] else main())
