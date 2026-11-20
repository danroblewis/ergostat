"""The pipeline manager's tools (dev/README.md, *The pipeline manager*), each checked here and recorded as an
intervention by whoever asked (the coordinator by hand, `pipeline-manager` from its run) with a class:

  continue GAP [--depends-on a,b]       a new gap continuing a parked (or dead) gap's branch
  reapprove GAP --why W                 past an environmental failure: its failed tests run again on main where they
                                        failed (the checkout, or a container) must fail there too
  flake TEST --why W                    the test recorded as a flake
  file-gap --title T --definition-text D [--depends-on a,b] [--branch B]
  remedy INTERVENTION --why W           an open intervention remedied (a queue one: main clean and pushed)
  close GAP | park GAP | pool ROLE N | change --what W   (each --why W) asked in the inbox, from the block's run"""

from __future__ import annotations

import argparse
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

BY = ["coordinator"]                      # who acts: the coordinator by hand, the pipeline manager from its run
SITUATION = [""]
CLASSES = {"continue": "parked-continued", "reapprove": "environment-defect", "flake": "flake", "file-gap": "missing-gap",
           "remedy": "remedied", "close": "groom", "park": "stuck", "pool": "operator-decision", "change": "factory-change"}
GATED = {"close": "manager-close", "park": "manager-park", "pool": "manager-pool", "change": "manager-change"}


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
    g, gaps = item(a.gap), {x["id"]: x for x in fac.items("gap")}
    if g["state"] not in ("parked", "dead"):
        raise Refused(f"{a.gap} is {g['state']}: only a parked or dead gap is continued")
    branch = fac.branch_of(g)
    held = [x["id"] for x in gaps.values() if x["id"] != g["id"] and x["state"] not in ("parked", "merged", "closed")
            and (x["fields"].get("branch") == branch or str(x["fields"].get("continues") or "").removeprefix("factory/") == branch)]
    if held:
        raise Refused(f"{branch} is held by {', '.join(held)}")
    gid = next(i for n in range(1, 99) if (i := f"gap/{fac.slug(g['id'].split('/', 1)[1], 40)}-continued"
                                           + (f"-{n}" if n > 1 else "")) not in gaps)
    rel = fac.definition_file(g)
    record("gap.requested", gid, title=f"{g['fields'].get('title') or g['id']}, continued", source="request",
           continues=branch, depends_on=gap_ids(a.depends_on, set(gaps)), requested_at=time.time(), requested_by=BY[0],
           **({"definition": f"{fac.git_branch(branch)}:{rel}"} if rel != f"{fac.DEFS}/{branch}.md" else {}))
    intervene("continue", a.gap, a.why or f"continued as {gid}", a.cls, gap=gid)
    return f"{gid} requested, continuing {branch}"


def on_main(cfg: dict, g: dict, tests: list[str], contained: bool) -> tuple[int, list[str], str]:
    """The tests again on main where they failed: the fast suites' in a suite container on the main the branch merged
    (main-broken's own run, onmain.failing), the queue's in a worktree of the checkout of its own at main. (exit, the
    tests that failed, the log)."""
    base, tag = cfg["git"]["base"], f"manager-{time.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:4]}"
    if contained:
        main = str(g["fields"].get("built_main") or "") or f"origin/{base}"
        got = onmain.failing(cfg, fac.branch_of(g), main, tests, fac.run_dir(cfg, "manager"), tag)
        return int(bool(got.get("failed"))), list(got.get("tests") or []), fac.rel(fac.run_dir(cfg, "manager")
                                                                                   / f"{tag}-alone.txt")
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


def gated(cfg: dict, a) -> str:
    args = {"close": lambda: {"gap": a.gap}, "park": lambda: {"gap": a.gap}, "pool": lambda: {"role": a.role, "to": str(int(a.n))},
            "change": lambda: {"what": a.what}}[a.cmd]()
    if a.cmd in ("close", "park"):
        item(a.gap)
    rc, said = fac.act(GATED[a.cmd], key=fac.slug(f"{a.cmd}-{json.dumps(args)}", 60), why=a.why, **args)
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
        review.park(cfg, item(gap), why, "pipeline-manager", where="manager")
    return f"{gap} {argv[0]}"


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="manage.py", description=__doc__, formatter_class=argparse.RawTextHelpFormatter,
                                 exit_on_error=False)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, args in (("continue", "gap --depends-on"), ("reapprove", "gap"), ("flake", "test"), ("remedy", "intervention"),
                       ("file-gap", "--title! --definition-text! --depends-on --branch"), ("close", "gap"),
                       ("park", "gap"), ("pool", "role n"), ("change", "--what!")):
        p = sub.add_parser(name, exit_on_error=False)
        for x in args.split():
            p.add_argument(x.rstrip("!"), **({"required": x.endswith("!")} if x.startswith("--") else {}),
                           **({"default": ""} if x.startswith("--") and not x.endswith("!") else {}))
        p.add_argument("--why", default="", required=name not in ("continue", "file-gap"))
        p.add_argument("--class", dest="cls", default="")
    return ap


def run(cfg: dict, argv: list[str]) -> dict:
    """One call: {call, ok, said}. A refusal, or arguments that do not parse, is said, not raised."""
    try:
        a = parser().parse_args(argv)
        if a.cls and not fac.SAFE.match(a.cls):
            raise Refused(f"--class {a.cls!r}: lowercase words and dashes")
        if a.cmd in GATED:
            return {"call": argv, "ok": True, "said": gated(cfg, a)}
        do = {"continue": do_continue, "reapprove": do_reapprove, "flake": do_flake, "remedy": do_remedy,
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
    if argv[:1] in ([], ["-h"], ["--help"]) or argv[0] in ("closed", "parked", "approved"):
        print(approved(cfg, argv) if argv[:1] and argv[0] in ("closed", "parked", "approved") else __doc__)
        return 0
    got = run(cfg, argv)
    print(got["said"], file=sys.stdout if got["ok"] else sys.stderr)
    return 0 if got["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
