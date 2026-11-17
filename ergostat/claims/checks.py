"""ergostat's checks of a claim (SPEC §12g), run after the run that made it, against the record and the world; never
the claimant's own. Each gives a verdict, verified or contradicted with its evidence, or unchecked with why:

- **tests** ("tests pass"): the project's declared test command (``claims: {tests: {run: ...}}``) run by ergostat
  itself, where the claim says (a folder, a commit, an item that names its commit or branch); without one, the
  latest test run in the record (``tests.ran`` with its ``exit``, ``tests.passed``, ``tests.failed``);
- **changed** (a file or a part changed): git (uncommitted, or committed since the run began, or in the commit
  named), a file's time where there is no git, ``ergostat.model.changed`` for a part; a commit named alone: that it
  exists;
- **state** (an item moved to a state): the item, folded;
- **exit** (a command succeeded): the exit code its run recorded;
- **level** (a value reached a level): the part's latest reading against the level;
- a check the project declares under ``claims:``: its command's exit code.

A claim no check knows is unchecked: recorded, and not trusted. A command a claim names for its own check is never
run: what checks a claim is the model's, not the claimant's."""

from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path

from ..spec.ir import CLAIM_CHECKS, Ref, Setpoint, Spec
from . import record

TESTS = re.compile(r"\b(tests?|test suite|suite|checks)\b.*\b(pass(es|ed|ing)?|green|succeed(s|ed)?|ok)\b|"
                   r"\b(passing|green)\b.*\btests?\b", re.I)
FAILS = re.compile(r"\bfail(s|ed|ing)?\b|\bred\b", re.I)
CHANGED = re.compile(r"^\s*(changed|edited|modified|wrote|written|updated|added|fixed|removed|deleted|committed|"
                     r"created|renamed)\b", re.I)
EXITED = re.compile(r"\b(succeeded|exit(ed)?( with)?( code)? 0|ran (cleanly|without errors?))\b", re.I)
TAIL = 1500
TEST_EVENTS = "tests.ran,tests.passed,tests.failed"


class Unchecked(Exception):
    """No verdict: why not."""


def kind_of(spec: Spec, claim: dict) -> tuple[str | None, dict]:
    """Which check a claim gets, and what it is given: the check it names, else the first that knows what it says."""
    chk, says, about = claim.get("check"), claim["says"], claim.get("about") or {}
    params: dict = {}
    name = None
    if isinstance(chk, str):
        name = chk
    elif isinstance(chk, dict):
        params = {k: v for k, v in chk.items() if k not in ("kind", "run")}
        name = chk.get("kind") or next((k for k in ("state", "level", "exit", "changed", "tests") if k in chk), None)
    if name:
        if name in CLAIM_CHECKS or name in spec.claims:
            return str(name), params
        return None, {"unknown": str(name)}
    for c in spec.claims.values():
        if c.says and re.search(c.says, says, re.I):
            return c.name, {}
    if TESTS.search(says):
        return "tests", {}
    item = about.get("item")
    if item:
        k = next((k for k in spec.items.values() if k.matches(item)), None)
        for st in (k.states if k else []):
            if re.search(rf"\b{re.escape(st)}\b", says, re.I):
                return "state", {"state": st}
    if (about.get("file") or about.get("part") or about.get("commit")) and CHANGED.search(says):
        return "changed", {}
    if EXITED.search(says):
        return "exit", {}
    return None, {}


# ---- running a command where the claim says

def inside(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def git(repo: Path, *args, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=check, timeout=60)


def item_fields(p, spec: Spec, item: str) -> dict:
    from ..spec import items as it
    got = it.one(p.events, spec, item)
    return dict(got.fields) if got else {}


def revision(p, spec: Spec, about: dict) -> tuple[str | None, str]:
    """The commit a claim is about: named, or named by the item it is about (its ``commit`` or ``branch`` field)."""
    if about.get("commit"):
        return about["commit"], "the commit it names"
    if about.get("item"):
        f = item_fields(p, spec, about["item"])
        for k in ("commit", "branch"):
            if isinstance(f.get(k), str) and f[k]:
                return f[k], f"{about['item']}'s {k}"
    return None, ""


def place(p, spec: Spec, about: dict, base: str) -> tuple[Path, Path | None, dict]:
    """Where a check's command runs: the folder the claim names, a copy of the commit it is about (exported from
    the repository at ``base``, or the one it names, into a scratch folder), or ``base``. Returns (folder, the
    scratch folder to remove, what was found)."""
    root = spec.root.resolve()
    if about.get("dir"):
        d = (root / about["dir"]).resolve()
        if not (inside(root, d) or inside(p.dir, d)):
            raise Unchecked(f"{about['dir']} is outside the project")
        if not d.is_dir():
            raise Unchecked(f"no folder {about['dir']}")
        return d, None, {"in": about["dir"]}
    rev, how = revision(p, spec, about)
    repo = (root / (about.get("repo") or base)).resolve()
    if not inside(root, repo):
        raise Unchecked(f"{about.get('repo') or base} is outside the project")
    if rev:
        if not repo.is_dir():
            raise Unchecked(f"no repository at {repo.relative_to(root)} to take {rev} from")
        got = git(repo, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}")
        if got.returncode:
            raise Contradicted(f"no commit {rev} in {repo.relative_to(root) or '.'}", {"commit": rev, "from": how})
        sha = got.stdout.strip()
        tar = subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", sha], capture_output=True, timeout=120)
        if tar.returncode:
            raise Unchecked(f"git archive {sha[:10]}: {tar.stderr.decode(errors='replace').strip()[:200]}")
        scratch = Path(tempfile.mkdtemp(prefix="ergostat-claim-"))
        with tarfile.open(fileobj=io.BytesIO(tar.stdout)) as t:
            t.extractall(scratch, filter="data")
        return scratch, scratch, {"commit": sha, "from": how, "repo": str(repo.relative_to(root)) or "."}
    if not repo.is_dir():
        raise Unchecked(f"no folder {base} to run it in")
    return repo, None, {"in": str(repo.relative_to(root)) or "."}


class Contradicted(Exception):
    def __init__(self, why: str, evidence: dict):
        super().__init__(why)
        self.evidence = evidence


def run_check(p, spec: Spec, command: str, about: dict, base: str, timeout: float, cid: str) -> dict:
    """A command run by ergostat, where the claim says: its exit code and the end of what it printed."""
    cwd, scratch, found = place(p, spec, about, base)
    env = {**os.environ, "ERGOSTAT_ROOT": str(spec.root), "ERGOSTAT_STATE_DIR": str(p.dir), "ERGOSTAT_CLAIM": cid}
    started = time.time()
    try:
        r = subprocess.run(command, shell=True, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout,
                           start_new_session=True, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise Unchecked(f"{command} did not finish within {timeout:g}s") from None
    finally:
        if scratch is not None:
            shutil.rmtree(scratch, ignore_errors=True)
    out = (r.stdout + r.stderr).strip()
    return {"command": command, **found, "exit": r.returncode, "seconds": round(time.time() - started, 3),
            "output": out[-TAIL:], **({"truncated": True} if len(out) > TAIL else {})}


# ---- the checks

def tests(p, spec: Spec, c: dict, params: dict) -> tuple[str, dict, str]:
    wants = not FAILS.search(c["says"])               # "tests pass" (or, said of a failure, "tests fail")
    decl = spec.claims.get("tests")
    if decl is not None:
        ev = run_check(p, spec, decl.run, c.get("about") or {}, decl.in_, decl.timeout, c["id"])
        ok = ev["exit"] == 0
        said = (f"the tests exited {ev['exit']}" + (f" at {ev['commit'][:10]}" if ev.get("commit") else "") +
                f", run by ergostat ({decl.run})")
        return ("verified" if ok == wants else "contradicted"), ev, said
    item = (c.get("about") or {}).get("item")
    got = (p.events.query(n=1, type=TEST_EVENTS, item=item) if item else []) or p.events.query(n=1, type=TEST_EVENTS)
    if not got:
        raise Unchecked("no test command is declared (claims: tests: run:) and no test run is in the record "
                        "(tests.ran, tests.passed, tests.failed)")
    e = got[-1]
    d = e["data"]
    ok = (e["type"] == "tests.passed" or (e["type"] == "tests.ran" and (d.get("exit") == 0 or d.get("passed") is True)))
    ev = {"event": e["id"], "type": e["type"], "time": e["time"], "item": e.get("item"),
          **{k: d[k] for k in ("exit", "passed", "failed", "summary") if k in d}}
    return ("verified" if ok == wants else "contradicted"), ev, f"the latest test run in the record ({e['type']}) " \
        f"{'passed' if ok else 'failed'}"


def run_start(p, c: dict) -> float:
    e = p.events.get(c["run"]) if c.get("run") else None
    return e["time"] if e else float(c.get("made") or time.time())


def changed(p, spec: Spec, c: dict, params: dict) -> tuple[str, dict, str]:
    about = c.get("about") or {}
    root = spec.root.resolve()
    since = run_start(p, c)
    if about.get("part"):
        name = about["part"].split(".", 1)[1]
        hits = [e for e in p.events.query(n=None, type="ergostat.model.changed", since=since)
                if e["data"].get("target") == about["part"] or re.search(rf"\b{re.escape(name)}\b", str(e["data"].get("diff")))]
        ev = {"part": about["part"], "since": since, "changes": [e["id"] for e in hits]}
        return ("verified" if hits else "contradicted"), ev, (f"{len(hits)} change{'s' if len(hits) > 1 else ''} to the "
                                                              f"model touched it since the run began" if hits else
                                                              "no change written to the model since the run began touches it")
    f = about.get("file")
    rev, _ = revision(p, spec, about)
    if not f:
        if not rev:
            raise Unchecked("a change is checked in a file, a part or a commit, and the claim names none")
        repo = (root / (about.get("repo") or ".")).resolve()
        got = git(repo, "log", "-1", "--format=%H %ct %s", rev)
        if got.returncode:
            return "contradicted", {"commit": rev}, f"no commit {rev}"
        sha, ct, subject = (got.stdout.strip().split(" ", 2) + ["", ""])[:3]
        return "verified", {"commit": sha, "time": float(ct), "subject": subject}, f"commit {sha[:10]} exists: {subject}"
    path = (root / f).resolve()
    if not inside(root, path):
        raise Unchecked(f"{f} is outside the project")
    where = path.parent if path.parent.is_dir() else root
    top = git(where, "rev-parse", "--show-toplevel")
    ev: dict = {"file": f, "since": since}
    if top.returncode:                                   # no git: the file's own time
        if not path.exists():
            return "contradicted", ev, f"there is no {f}"
        ev["modified"] = path.stat().st_mtime
        ok = ev["modified"] >= since - 1
        return ("verified" if ok else "contradicted"), ev, f"{f} was {'' if ok else 'not '}written since the run began"
    repo = Path(top.stdout.strip())
    rel = os.path.relpath(path, repo)
    if rev:
        names = git(repo, "show", "--name-only", "--format=", rev)
        ev["commit"] = rev
        ok = rel in names.stdout.split("\n")
        return ("verified" if ok else "contradicted"), ev, f"commit {rev} {'changes' if ok else 'does not change'} {f}"
    dirty = git(repo, "status", "--porcelain", "--", rel).stdout.strip()
    log = [x.split(" ", 1) for x in git(repo, "log", "-n", "50", "--format=%h %ct", "--", rel).stdout.split("\n") if x]
    since_run = [h for h, t in log if float(t) >= int(since)]       # (a commit's time is in whole seconds)
    ev.update({"uncommitted": bool(dirty), "commits": since_run})
    ok = bool(dirty or since_run)
    return ("verified" if ok else "contradicted"), ev, (f"{f} has uncommitted changes" if dirty else
                                                        f"{f} changed in {len(since_run)} commit(s) since the run began"
                                                        if since_run else f"{f} has not changed since the run began")


def state(p, spec: Spec, c: dict, params: dict) -> tuple[str, dict, str]:
    from ..spec import items as it
    item = (c.get("about") or {}).get("item")
    want = params.get("state")
    if not item or not want:
        raise Unchecked("a state is checked on an item, with the state claimed ({\"state\": \"done\"})")
    k = it.kind_of(spec, item)
    if k is None or want not in k.states:
        raise Unchecked(f"{item}'s kind has no state {want}" if k else f"no kind of item matches {item}")
    got = it.one(p.events, spec, item)
    if got is None:
        return "contradicted", {"item": item}, f"nothing is recorded about {item}"
    since = run_start(p, c)
    moved = [m for m in got.moves if m["to"] == want and m["time"] >= since - 1]
    ev = {"item": item, "state": got.state, "claimed": want, "moves": [{k_: m[k_] for k_ in ("time", "from", "to", "type")}
                                                                       for m in got.moves[-6:]]}
    if got.state == want or moved:
        return "verified", ev, f"{item} is {got.state}" + ("" if got.state == want else f" (it was {want} since the run began)")
    return "contradicted", ev, f"{item} is {got.state}, not {want}"


def exit_(p, spec: Spec, c: dict, params: dict) -> tuple[str, dict, str]:
    run = (c.get("about") or {}).get("run") or c.get("run")
    if not run:
        raise Unchecked("no run to read an exit code from")
    want = int(params.get("exit", 0))
    ended = [e for e in p.events.caused_by(run) if e["type"] in ("agent.ran", "agent.failed")]
    own = p.events.get(run)
    if not ended and own and "exit" in own["data"]:      # an event that records an exit code itself
        ended = [own]
    if not ended:
        raise Unchecked(f"no exit code is recorded for run {run[:8]}")
    e = ended[-1]
    code = e["data"].get("exit")
    ev = {"event": e["id"], "type": e["type"], "exit": code, **({"note": e["data"]["note"]} if e["data"].get("note") else {})}
    if code is None:
        raise Unchecked(f"run {run[:8]} recorded no exit code ({e['data'].get('note', 'it did not finish')})")
    return ("verified" if code == want else "contradicted"), ev, f"the run exited {code}"


def level(p, spec: Spec, c: dict, params: dict) -> tuple[str, dict, str]:
    part = (c.get("about") or {}).get("part")
    sp = Setpoint.parse(params.get("level"))
    r = Ref.parse(part) if part else None
    if r is None or sp is None:
        raise Unchecked("a level is checked on a part (stock.x, flow.x, auxiliary.x) with the level claimed "
                        "({\"level\": \">= 3\"})")
    x = spec.measured(r.kind).get(r.name) if r.kind in ("stock", "flow", "auxiliary") else None
    if x is None:
        raise Unchecked(f"no {r.kind} {r.name} is measured")
    reads = [(got, s.series) for s in x.sensors.values() if (got := p.measurements.latest(s.series))]
    if not reads:
        raise Unchecked(f"{part} has no reading")
    (t, v), series = max(reads, key=lambda g: g[0][0])
    ok = not sp.outside(v)
    ev = {"part": part, "value": v, "time": t, "series": series, "level": f"{sp.op} {sp.value:g}"}
    return ("verified" if ok else "contradicted"), ev, f"{part} reads {v:g}, " + ("which is" if ok else "not") + \
        f" {sp.op} {sp.value:g}"


def declared(p, spec: Spec, c: dict, params: dict) -> tuple[str, dict, str]:
    d = spec.claims[c["kind"]]
    ev = run_check(p, spec, d.run, c.get("about") or {}, d.in_, d.timeout, c["id"])
    wants = not FAILS.search(c["says"]) if c["kind"] == "tests" else True
    ok = ev["exit"] == 0
    return ("verified" if ok == wants else "contradicted"), ev, f"{d.run} exited {ev['exit']}"


CHECKS = {"tests": tests, "changed": changed, "state": state, "exit": exit_, "level": level}


def check(p, spec: Spec, c: dict) -> dict:
    """One claim checked, its verdict recorded. Returns the claim with its verdict."""
    started = time.time()
    kind = c.get("kind")
    try:
        if kind is None:
            unknown = (c.get("params") or {}).get("unknown")
            raise Unchecked(f"no check named {unknown}: the built-in ones are {', '.join(CLAIM_CHECKS)}, and claims: "
                            f"declares {', '.join(spec.claims) or 'none'}" if unknown else
                            "no check knows this kind of claim; say which (check: tests, changed, state, exit, level)")
        st, ev, why = CHECKS.get(kind, declared)(p, spec, c, c.get("params") or {})
    except Contradicted as e:
        st, ev, why = "contradicted", e.evidence, str(e)
    except Unchecked as e:
        st, ev, why = "unchecked", {}, str(e)
    except Exception as e:                               # a check that broke judges nothing: it says so
        st, ev, why = "unchecked", {}, f"the check failed: {type(e).__name__}: {e}"
    if isinstance(c.get("check"), dict) and c["check"].get("run"):
        ev = {**ev, "not_run": "the claim's own command: a claim is checked by the model's checks, not its own"}
    record.verdict(p, c, st, ev, why, time.time() - started)
    return {**c, "state": st, "verdict": st, "evidence": ev, "why": why}


def check_all(p, spec: Spec, claims: list[dict]) -> list[dict]:
    return [check(p, spec, c) for c in claims]


def pending(p, spec: Spec) -> list[dict]:
    """Claims made and never checked (ergostat stopped between the run and its checks), oldest first."""
    return sorted((c for c in record.stored(p).values() if c["state"] == "made"), key=lambda c: c["time"])
