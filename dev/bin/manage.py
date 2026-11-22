"""The pipeline manager's tools (dev/README.md, *The pipeline manager*), each checked here and recorded as an
intervention by whoever asked (the coordinator by hand, `pipeline-manager` from its run) with a class:

  continue GAP [--depends-on a,b]       a new gap continuing a parked (or dead) gap's branch
  reapprove GAP --why W                 past an environmental failure: its failed tests run again on main where they
                                        failed (the checkout, or a container) must fail there too
  measure-runs GAP --runs N --tests T [--load K]   a parked or built gap's named measurement (runs.py): N watched
                                        runs (1-50) of the pytest selection T on its branch head, the CPU loaded by K
                                        busy processes (1-8); all passed: back to review, else to fix with the tail;
                                        from the block's run, asked in the inbox (manager-measure, run outside it)
  flake TEST --why W                    the test recorded as a flake
  file-gap --title T --definition-text D [--depends-on a,b] [--branch B]
  remedy INTERVENTION --why W           an open intervention remedied (a queue one: main clean and pushed)
  propose --title T --definition-text D --why W   the review's change to the merge pipeline, a gap (one open at a time)
  ask QUESTION --why W                  a question for the researcher on speeding up the merge pipeline (one open)
  close GAP | park GAP | pool ROLE N | change --what W   (each --why W) asked in the inbox, from the block's run"""

from __future__ import annotations

import argparse
import fcntl
import json
import re
import shlex
import sys
import time
import uuid

sys.dont_write_bytecode = True
import agents  # noqa: E402
import fac  # noqa: E402
import onmain  # noqa: E402
import runs  # noqa: E402

BY = ["coordinator"]                      # who acts: the coordinator by hand, the pipeline manager from its run
SITUATION = [""]
CLASSES = {"continue": "parked-continued", "reapprove": "environment-defect", "flake": "flake", "file-gap": "missing-gap",
           "remedy": "remedied", "measure-runs": "operator-decision", "close": "groom", "park": "stuck", "pool": "operator-decision",
           "change": "factory-change", "propose": "velocity", "ask": "velocity-research"}
MEASURED_PARKS = ("needs", "defect")      # the park kinds a measurement may clear (manage.measurable)
GATED = {"close": "manager-close", "park": "manager-park", "pool": "manager-pool", "change": "manager-change",
         "measure-runs": "manager-measure"}       # (measure-runs gated only from the block's run: hours, past its 1 h)


class Refused(Exception):
    pass


def record(event: str, item: str, **data) -> None:
    fac.ergostat("event", "--add", event, "--item", item, "--data", json.dumps(data, default=str), "--as", BY[0])


def intervene(action: str, subject: str, why: str, cls: str = "", **more) -> str:
    iid = f"intervention/{BY[0]}-{time.strftime('%Y%m%d-%H%M%S')}-{action}-{fac.slug(subject.split('/')[-1], 30)}"
    record("intervention.recorded", iid, reason=f"{action} {subject}: {why}"[:1000], by=BY[0], action=action,
           subject=subject, recorded_at=time.time(), situation=SITUATION[0], **{"class": cls or CLASSES[action]}, **more)
    return iid


def item(iid: str) -> dict:
    r = fac.ergostat("item", iid, "--json", check=False)
    if r.returncode:
        raise Refused(f"no item {iid}")
    return json.loads(r.stdout)


def gap_ids(names: str, known: set[str]) -> list[str]:
    got = [d if d.startswith("gap/") else f"gap/{d}" for d in (x.strip() for x in names.split(",")) if d]
    if [d for d in got if d not in known]:
        raise Refused(f"no such gap: {', '.join(d for d in got if d not in known)}")
    return got


def do_continue(cfg: dict, a) -> str:
    gid, branch = continue_gap(cfg, a.gap, a.depends_on, cleared=f"continued by {BY[0]}: {a.why}"[:500])
    intervene("continue", a.gap, a.why or f"continued as {gid}", a.cls, gap=gid)
    return f"{gid} requested, continuing {branch}"


def continue_lock(cfg: dict):
    lock = open(fac.run_dir(cfg) / "continue.lock", "a")
    fcntl.flock(lock, fcntl.LOCK_EX)
    return lock


def holders(g: dict, gaps: dict) -> list[str]:
    """The other live gaps on ``g``'s branch: its own, or continuing it."""
    branch = fac.branch_of(g)
    return [x["id"] for x in gaps.values() if x["id"] != g["id"] and x["state"] not in ("parked", "merged", "closed")
            and (x["fields"].get("branch") == branch
                 or str(x["fields"].get("continues") or "").removeprefix("factory/") == branch)]


def continue_gap(cfg: dict, gap: str, depends_on: str = "", cleared: str = "", once: bool = False) -> tuple[str, str]:
    """A new gap continuing a parked (or dead) gap's branch: (its id, the branch). The parked gap's `gap.resumed` says
    as what and what cleared. Read, checked and written under the continue lock, so the coordinator's continue and the
    park resumer's never both take one park; ``once`` (the resumer's): refused when it was resumed already."""
    with continue_lock(cfg):
        g, gaps = item(gap), {x["id"]: x for x in fac.items("gap")}
        if g["state"] not in ("parked", "dead"):
            raise Refused(f"{gap} is {g['state']}: only a parked or dead gap is continued")
        branch = fac.branch_of(g)
        if held := holders(g, gaps):
            raise Refused(f"{branch} is held by {', '.join(held)}")
        if once and g["fields"].get("resumed_as"):
            raise Refused(f"{gap} was resumed already, as {g['fields']['resumed_as']}")
        gid = next(i for n in range(1, 99) if (i := f"gap/{fac.slug(g['id'].split('/', 1)[1], 40)}-continued"
                                               + (f"-{n}" if n > 1 else "")) not in gaps)
        rel = fac.definition_file(g)
        record("gap.requested", gid, title=f"{g['fields'].get('title') or g['id']}, continued", source="request",
               continues=branch, depends_on=gap_ids(depends_on, set(gaps)), requested_at=time.time(),
               requested_by=BY[0], **({"definition": f"{fac.git_branch(branch)}:{rel}"}
                                      if rel != f"{fac.DEFS}/{branch}.md" else {}))
        record("gap.resumed", g["id"], resumed_as=gid, resumed_at=time.time(), resumed_by=BY[0],
               resumed_for=g["fields"].get("parked_for") or "defect", cleared=cleared or f"continued by {BY[0]}")
        return gid, branch


def on_main(cfg: dict, g: dict, tests: list[str], contained: bool) -> tuple[int, list[str], str]:
    """The tests again on main where they failed: the fast suites' in a suite container on the main the branch merged
    (main-broken's own run, onmain.failing), the queue's in a worktree of the checkout of its own at main. (exit, the
    tests that failed, the log)."""
    base, tag = cfg["git"]["base"], f"manager-{time.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:4]}"
    if contained:
        main = str(g["fields"].get("built_main") or "") or f"origin/{base}"
        by = onmain.AGAIN.get(str((g["fields"].get("suites_fast") or {}).get("failed")), "alone")  # (browser: rerun)
        got = onmain.failing(cfg, fac.branch_of(g), main, tests, fac.run_dir(cfg, "manager"), tag, by)
        return int(bool(got.get("failed"))), list(got.get("tests") or []), fac.rel(fac.run_dir(cfg, "manager")
                                                                                   / f"{tag}-{by}.txt")
    log = fac.run_dir(cfg, "manager") / f"{tag}.txt"
    cmd = cfg["suites"]["rerun"].format(tests=" ".join(map(shlex.quote, tests)))
    wt = fac.path(cfg, "worktrees") / ".manager"
    if not (wt / ".git").exists():
        wt.parent.mkdir(parents=True, exist_ok=True)
        fac.git(fac.path(cfg, "checkout"), "worktree", "add", "-q", "--detach", str(wt), base)
    fac.git(wt, "checkout", "-q", "--detach", fac.git(fac.path(cfg, "checkout"), "rev-parse", base))
    rc, _ = fac.suite(cfg, "rerun", wt, log, command=cmd)
    return rc, fac.failed_tests(log.read_text()), fac.rel(log)


def do_reapprove(cfg: dict, a) -> str:
    g = item(a.gap)
    f, st = g["fields"], g["state"]
    fast = f.get("suites_fast") or {}
    tip = fac.git(agents.drop(cfg), "rev-parse", "--verify", "-q", f"refs/heads/{fac.git_branch(fac.branch_of(g))}",
                  check=False)
    if f.get("failed_tests") and (st == "queue-failed" or (st == "fix" and f.get("sent_back_by") in ("triage", "queue"))):
        tests, contained, head, to = list(f["failed_tests"]), False, str(f.get("reviewed_head") or ""), "approved"
    elif fast.get("failed") and fast.get("tests") and st in ("ready", "fix"):
        tests, contained, head, to = list(fast["tests"]), True, str(f.get("head") or ""), "built"
    else:
        raise Refused(f"{a.gap} ({st}) has no failure of named tests in the queue or its fast suites to re-approve")
    if not head or head != tip:
        raise Refused(f"{a.gap}'s branch moved since its failure ({head[:12] or 'none'} failed, {tip[:12] or 'none'} now)")
    rc, failed, log = on_main(cfg, g, tests, contained)
    passed = [t for t in tests if t not in failed]
    if not rc or passed:
        raise Refused(f"not environmental: on main {', '.join(passed) or 'they'} passed ({log}); the failure is the branch's")
    env = {"tests": tests, "on_main": log, "where": "container" if contained else "checkout", "why": a.why}
    if to == "approved":
        record("gap.retried", a.gap, approved_by="manager-reapprove", reapproved=env, reapproved_at=time.time())
    else:
        record("gap.built", a.gap, built_at=time.time(), head=head, reapproved=env)
    intervene("reapprove", a.gap, a.why, a.cls, tests=tests, on_main=log)
    return f"{a.gap} back to {to}: {', '.join(tests)} fail on main too ({log})"


def do_measure_runs(cfg: dict, a) -> str:
    """The runs (runs.measure), their counts appended to the gap's `measured_runs` and said in its `findings`, which
    the reviewer's and implementor's briefs carry. All passed: gap.built at the head measured (review, unchanged); any
    failed: gap.sent-back, the first failing run's tail its input. A parked gap only as `measurable` allows, checked
    before the runs and again after, under the continue lock with the move (lesson-1). The gap and its branch are read
    again there: one that left parked or built, whose branch moved, or that is no longer measurable keeps its state,
    the counts recorded alone."""
    measurable(item(a.gap))
    got = runs.measure(cfg, item(a.gap), a.runs, runs.selection(a.tests), a.load)
    head, bad = got["head"], [r for r in got["runs"] if not r["passed"]]
    said = (f"measure-runs at {head[:12]}: {got['passed']} of {got['n']} runs passed, {got['failed']} failed, of "
            f"`{' '.join(got['tests'])}`" + (f", the CPU loaded by {got['load']} busy processes" if got["load"] else ""))
    with continue_lock(cfg):
        moved(cfg, a, got, said, bad)
    intervene("measure-runs", a.gap, a.why or said, a.cls, head=head, passed=got["passed"], failed=got["failed"])
    return f"{a.gap} back to {'fix' if bad else 'built'}: {said}"


def measurable(g: dict) -> None:
    """Raises Refused for a parked gap a measurement may not move: one resumed already (its continuation holds the
    branch), one whose branch another live gap holds, or one parked for a kind not in MEASURED_PARKS (an allowlist:
    deferred and cancelled are the coordinator's, the kill rule is past its rounds), or a `needs` park whose
    parked_until action does not name a measurement (a word starting `measure`: an approval, say, is not cleared)."""
    f = g["fields"]
    if g["state"] != "parked":
        return
    if f.get("resumed_as"):
        raise Refused(f"{g['id']} was resumed already, as {f['resumed_as']}")
    if f.get("parked_for") not in MEASURED_PARKS or f.get("deferred") or f.get("cancelled"):
        raise Refused(f"{g['id']} is parked for {f.get('parked_for') or 'no kind said'}: a measurement clears only "
                      f"{' or '.join(MEASURED_PARKS)}")
    need = (f.get("parked_until") or {}).get("action") if isinstance(f.get("parked_until"), dict) else None
    if f["parked_for"] == "needs" and not re.search(r"\bmeasure", str(need or ""), re.I):
        raise Refused(f"{g['id']} needs {need or 'nothing said'}: a measurement clears only a need that names one")
    if held := holders(g, {x["id"]: x for x in fac.items("gap")}):
        raise Refused(f"{fac.branch_of(g)} is held by {', '.join(held)}")


def moved(cfg: dict, a, got: dict, said: str, bad: list[dict]) -> None:
    head, g = got["head"], item(a.gap)
    try:
        if g["state"] not in ("parked", "built") or runs.tip(cfg, fac.branch_of(g)) != head:
            raise Refused(f"{a.gap} is {g['state']} now, or its branch moved since {head[:12]}")
        measurable(g)
    except Refused as e:
        record("gap.measured", a.gap, measured_runs=got)
        raise Refused(f"{said}; recorded alone: {e}") from None
    if bad:
        first = bad[0]
        record("gap.sent-back", a.gap, sent_back_by="measure-runs", measured_runs=got, failed_gates=1, fix_rounds=1,
               findings=[said, f"run {first['run']} of {got['n']}: {first['why']}; its tail:\n{first.get('tail', '')}"])
    else:
        record("gap.built", a.gap, built_at=time.time(), head=head, measured_runs=got,
               findings=[*list(g["fields"].get("findings") or []), said])


def do_flake(cfg: dict, a) -> str:
    if not re.fullmatch(r"[\w./-]+\.py::\S+", a.test):
        raise Refused(f"{a.test!r} is not a test id (path.py::name)")
    record("flake.seen", f"flake/{fac.slug(a.test, 80)}", test=a.test, times=1, seen_at=time.time(), by=BY[0], why=a.why)
    intervene("flake", a.test, a.why, a.cls)
    return f"{a.test} recorded as a flake"


def file_gap(cfg: dict, title: str, text: str, depends_on: str = "", branch: str = "", why: str = "", cls: str = "",
             **more) -> str:
    known = {g["id"] for g in fac.items("gap")}
    branch = branch or fac.slug(title, 32)
    p = fac.run_dir(cfg, "defs") / f"{branch}.md"
    if not fac.SAFE.match(branch) or f"gap/{branch}" in known or p.exists():
        raise Refused(f"{branch}: not a branch name, or a gap or definition of that name exists")
    if not re.search(r"^## Definition of done", text, re.M):
        raise Refused("the definition has no '## Definition of done' section")
    deps = gap_ids(depends_on, known)
    p.write_text(text.strip() + "\n")
    record("gap.requested", f"gap/{branch}", title=title[:200], source="request", branch=branch, depends_on=deps,
           definition=fac.rel(p), requested_at=time.time(), requested_by=BY[0], **more)
    intervene("file-gap", f"gap/{branch}", why or title, cls)
    return f"gap/{branch} requested ({fac.rel(p)})"


def do_remedy(cfg: dict, a) -> str:
    i = item(a.intervention)
    if i["state"] != "open":
        raise Refused(f"{a.intervention} is {i['state']}, not open")
    if i["fields"].get("class") == "queue":
        repo, base, remote = fac.path(cfg, "checkout"), cfg["git"]["base"], cfg["git"]["remote"]
        if fac.git(repo, "status", "--porcelain", "--untracked-files=no") or (repo / ".git" / "MERGE_HEAD").exists():
            raise Refused("the checkout is not clean: the queue cannot go on")
        ahead = fac.git(repo, "rev-list", "--count", f"{remote}/{base}..{base}", check=False)
        if ahead != "0":
            raise Refused(f"main is {ahead or 'unknown'} commit(s) ahead of {remote}: pushing or undoing it is gated")
    record("intervention.remedied", a.intervention, remedy=a.why, remedied_by=BY[0], remedied_at=time.time())
    intervene("remedy", a.intervention, a.why, a.cls)
    return f"{a.intervention} remedied"


def one_open(cfg: dict):
    """The lock held across the check for an open proposal or question and its write (lesson-1): a session's
    manage.py and the coordinator's by hand never both get past the one-open rule."""
    lock = open(fac.run_dir(cfg) / "one-open.lock", "a")
    fcntl.flock(lock, fcntl.LOCK_EX)
    return lock


def do_propose(cfg: dict, a) -> str:
    with one_open(cfg):
        return propose(cfg, a)


def do_ask(cfg: dict, a) -> str:
    with one_open(cfg):
        return ask(a)


def propose(cfg: dict, a) -> str:
    open_ =[g["id"] for g in fac.items("gap") if g["fields"].get("velocity") and g["state"] not in ("merged", "parked", "closed")]
    if open_:
        raise Refused(f"a proposal of the review's is open already ({', '.join(open_)}): one at a time")
    return file_gap(cfg, a.title, a.definition_text, a.depends_on, a.branch, a.why, a.cls or "velocity", velocity=True)


def ask(a) -> str:
    # open =anything not answered: asked, leased by the researcher, or dead (given up on, for the coordinator to see)
    mine = [r["id"] for r in fac.items("research") if r["fields"].get("asked_by") == BY[0] and r["state"] != "answered"]
    if mine:
        raise Refused(f"a question of yours waits for the researcher already ({', '.join(mine)}): one at a time")
    question = " ".join(a.question.split())
    if len(question) < 15:
        raise Refused("ask a whole question")
    rid = f"research/{fac.slug(question, 40) or 'question'}-{uuid.uuid4().hex[:6]}"
    record("research.asked", rid, question=question, asked_by=BY[0], asked_at=time.time(), situation=SITUATION[0])
    intervene("ask", rid, a.why, a.cls)
    return f"{rid} asked"


def gated(cfg: dict, a) -> str:
    args = {"close": lambda: {"gap": a.gap}, "park": lambda: {"gap": a.gap}, "pool": lambda: {"role": a.role, "to": str(int(a.n))},
            "change": lambda: {"what": a.what},
            "measure-runs": lambda: {"gap": a.gap, "runs": str(a.runs), "tests": a.tests, "load": str(a.load)}}[a.cmd]()
    if a.cmd in ("close", "park", "measure-runs"):
        g = item(a.gap)
        if a.cmd == "measure-runs":                              # (refused now if it would be refused when run)
            measurable(g)
    rc, said = fac.act(GATED[a.cmd], key=fac.slug(f"{a.cmd}-{json.dumps(args)}", 60), why=a.why or a.cmd, **args)
    how = {0: "ran", 1: "failed", 3: "held for the coordinator", 4: "denied"}.get(rc)
    if how is None:                                              # (asked outside the block's run, or not its action)
        raise Refused(f"{GATED[a.cmd]} was not asked: {said[-300:]}")
    intervene(a.cmd, str(args.get("gap") or args.get("role") or "factory"), f"{a.why} ({how})", a.cls, held=rc == 3, asked=args)
    return f"{GATED[a.cmd]}: {how}"


def approved(cfg: dict, argv: list[str]) -> str:
    """The approved actions' commands (run by the engine, outside the run): `closed GAP WHY`, `parked GAP WHY` (asked
    by the pipeline manager), `approved WHAT` (a change the coordinator makes)."""
    if argv[0] == "approved":
        return f"approved: {' '.join(argv[1:])} (the coordinator makes the change)"
    BY[0], gap, why = "pipeline-manager", argv[1], " ".join(argv[2:]) or "approved"
    if argv[0] == "closed":
        record("gap.closed", gap, closed_at=time.time(), closed_by=BY[0], why=why)
    else:
        import review
        fac.say = lambda event, it=None, **data: record(event, it or gap, **data)    # (said, outside a run: recorded)
        review.park(cfg, item(gap), why, "pipeline-manager", where="manager", kind="deferred")
    return f"{gap} {argv[0]}"


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="manage.py", description=__doc__, formatter_class=argparse.RawTextHelpFormatter,
                                 exit_on_error=False)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, args in (("continue", "gap --depends-on"), ("reapprove", "gap"), ("flake", "test"), ("remedy", "intervention"),
                       ("file-gap", "--title! --definition-text! --depends-on --branch"), ("close", "gap"),
                       ("propose", "--title! --definition-text! --depends-on --branch"), ("ask", "question"),
                       ("park", "gap"), ("pool", "role n"), ("change", "--what!")):
        p = sub.add_parser(name, exit_on_error=False)
        for x in args.split():
            p.add_argument(x.rstrip("!"), **({"required": x.endswith("!")} if x.startswith("--") else {}),
                           **({"default": ""} if x.startswith("--") and not x.endswith("!") else {}))
        p.add_argument("--why", default="", required=name not in ("continue", "file-gap", "propose"))
        p.add_argument("--class", dest="cls", default="")
    p = sub.add_parser("measure-runs", exit_on_error=False)              # (the caps checked here and again in runs.py)
    p.add_argument("gap")
    p.add_argument("--runs", type=runs.count, required=True)
    p.add_argument("--tests", type=lambda t: shlex.join(runs.selection(t)), required=True)
    p.add_argument("--load", type=lambda t: 0 if t == "0" else runs.procs(t), default=0)   # (0: no load)
    p.add_argument("--why", default="")
    p.add_argument("--class", dest="cls", default="")
    return ap


def run(cfg: dict, argv: list[str]) -> dict:
    """One call: {call, ok, said}. A refusal, or arguments that do not parse, is said, not raised."""
    try:
        a = parser().parse_args(argv)
        if a.cls and not fac.SAFE.match(a.cls):
            raise Refused(f"--class {a.cls!r}: lowercase words and dashes")
        if a.cmd in GATED and (a.cmd != "measure-runs" or BY[0] != "coordinator"):
            return {"call": argv, "ok": True, "said": gated(cfg, a)}
        do = {"continue": do_continue, "reapprove": do_reapprove, "flake": do_flake, "remedy": do_remedy,
              "measure-runs": do_measure_runs, "propose": do_propose, "ask": do_ask,
              "file-gap": lambda c, a: file_gap(c, a.title, a.definition_text, a.depends_on, a.branch, a.why, a.cls)}
        return {"call": argv, "ok": True, "said": do[a.cmd](cfg, a)}
    except (Refused, argparse.ArgumentError, KeyError, ValueError) as e:
        return {"call": argv, "ok": False, "said": f"refused: {e}"}
    except SystemExit as e:                                      # (argparse on a missing argument)
        return {"call": argv, "ok": False, "said": f"refused: the call does not parse ({e})"}
    except Exception as e:  # noqa: BLE001 - one call that fails is said; the session's others still run
        return {"call": argv, "ok": False, "said": f"failed: {type(e).__name__}: {str(e)[-500:]}"}


def main(argv: list[str]) -> int:
    cfg = fac.config()
    fac.cli(cfg)
    fac.stop_on_term()                                # (a SIGTERM runs the finallies: a measurement's load stopped)
    if argv[:1] in ([], ["-h"], ["--help"]) or argv[0] in ("closed", "parked", "approved"):
        print(approved(cfg, argv) if argv[:1] and argv[0] in ("closed", "parked", "approved") else __doc__)
        return 0
    got = run(cfg, argv)
    print(got["said"], file=sys.stdout if got["ok"] else sys.stderr)
    return 0 if got["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
