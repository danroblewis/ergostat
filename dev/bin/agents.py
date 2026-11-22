"""The implementor's and the reviewer's sessions, each in a Docker container of its own (the owner, 2026-11-20: "the
risk is much lower"). What a session's container is given, and nothing else:

- **its work**: a clone made by this program (never the owner's repository or its .git), mounted at /work: read-write
  for the implementor, read-only for the reviewer. Its result comes out as a git bundle (``finish``, in a container of
  its own with no network), fetched into the factory's drop repository (``<live>/drop.git``), never the owner's;
- **the network to the Anthropic API alone**: the container is on an internal Docker network (no route out) whose
  only way out is the egress proxy (dev/agent/egress.py, its own container), which tunnels to [agents] hosts on 443;
- **its transcript's folder**: one folder of its own (sessions.py), mounted as Claude Code's projects folder
  (/home/dev/.claude/projects), read-write, so the session's own file is kept (copied, the token scrubbed, into
  run/sessions/); nothing else of the host's home;
- **one secret, the session token**: read from [agents] token_file (mode 600, written by the owner from
  `claude setup-token`), given as CLAUDE_CODE_OAUTH_TOKEN at `docker run` by name (never in the command line, a log
  or an error), and nothing else of the host's environment: no home, no ERGOSTAT_*, no other variable;
- the dev image's limits (processes, memory, CPUs), no capabilities, no new privileges; removed when it ends.

Inside, Claude Code still runs --restricted, with the role's narrow tools, in dontAsk mode: a second layer."""

from __future__ import annotations

import contextlib
import json
import os
import re
import shlex
import stat
import subprocess
import time
import uuid
from pathlib import Path

import fac

NET, PROXY, PORT = "ergostat-agents", "ergostat-egress", 3128
DENY = ["Bash(git push:*)", "Bash(git remote:*)", "Bash(git config:*)", "Bash(git stash:*)", "Bash(curl:*)",
        "Bash(wget:*)", "Bash(ssh:*)", "Bash(gh:*)", "WebFetch", "WebSearch"]
NAMED = "uv run python scripts/named_tests.py"   # (an allowlist: 1 to 3 named test files, no options; never a suite)
BROWSER_FILE = "uv run python scripts/suite_watch.py -- uv run --with playwright==1.63.0 python scripts/named_tests.py"
TOOLS = {
    "implementor": ["Read", "Edit", "Write", "Glob", "Grep", "Bash(git status:*)", "Bash(git diff:*)",
                    "Bash(git log:*)", "Bash(git show:*)", "Bash(git add:*)", "Bash(git commit:*)",
                    "Bash(git merge:*)",           # (to finish main's merge, implement.py; its clone has no remote)
                    f"Bash({NAMED}:*)", "Bash(uv run ruff check:*)", "Bash(ls:*)", "Bash(wc:*)",
                    "Bash(mkdir:*)", "Bash(git rm:*)", "Bash(git mv:*)", "Bash(git restore:*)", "Bash(rm:*)",
                    f"Bash({BROWSER_FILE}:*)"],  # (a browser file: under the watchdog, with Playwright)
    "reviewer": ["Read", "Glob", "Grep", "Bash(git diff:*)", "Bash(git log:*)", "Bash(git show:*)"],
}
PREFIX = "ergostat-factory-"          # every container the factory starts is named so (the sweeper finds them)
TIMEOUTS = {"implementor": 7200, "reviewer": 3600, "finish": 600, "suite": 3600, "planner": 3600,
            "plan_reviewer": 1200, "join_judge": 1800, "researcher": 3600, "librarian": 600, "groomer": 3000,
            "pipeline_manager": 2400, "suite-queue": 3600, "suite-triage": 3600,   # seconds, each below its block's
            "measure-load": 43200}   # (runs.WALL, a whole measurement: its load lives through every run)
LIMITS = ["--init", "--pids-limit", "4096", "--memory", "12g", "--memory-swap", "12g", "--cpus", "4", "--cap-drop", "ALL",
          "--security-opt", "no-new-privileges", "--tmpfs", "/tmp:rw,exec,size=2g"]
SHOTS = ["-e", "SPLIT_SHOTS=/tmp/split-shots"]   # the browser files' pictures: beside the checkout is / here (compose.yaml)
TOOLS.update(planner=TOOLS["reviewer"], plan_reviewer=TOOLS["reviewer"], librarian=["Read"],
             join_judge=TOOLS["reviewer"], pipeline_manager=TOOLS["reviewer"], groomer=TOOLS["reviewer"],
             researcher=TOOLS["reviewer"] + ["WebSearch"])      # all read-only: only the implementor writes; WebSearch is
                                                                 # run by the API itself


class Refused(RuntimeError):
    """A session that must not start (no token, a token file others may read): said without the token."""


def settings(cfg: dict) -> dict:
    a = cfg.get("agents") or {}
    return {"image": a.get("image", "ergostat-agent:latest"), "hosts": list(a.get("hosts") or ["api.anthropic.com"]),
            "token_file": Path(os.path.expanduser(a.get("token_file", "~/.config/ergostat/claude-token"))),
            "proxy_image": a.get("proxy_image", "ergostat-dev:latest")}


def session_cpus(a: dict) -> str:
    """[agents] session_cpus: a session container's --cpus (empty or absent: the suites' 4); outside (0, 4] refused."""
    got = str(a.get("session_cpus", "")).strip()
    try:
        if got and not 0 < float(got) <= 4:
            raise ValueError(got)
    except ValueError:
        raise Refused(f"[agents] session_cpus = {got!r}: a number of CPUs above 0 and at most 4") from None
    return got or LIMITS[LIMITS.index("--cpus") + 1]


def token(cfg: dict) -> str:
    """The session token, from its file: refused (fail closed) when missing, empty, or readable by anyone but the owner."""
    f = settings(cfg)["token_file"]
    try:
        st = f.stat()
    except FileNotFoundError:
        raise Refused(f"no session token: the owner writes {f} (mode 600) from `claude setup-token`; sessions refuse "
                      f"to start without it") from None
    if stat.S_IMODE(st.st_mode) != 0o600:
        raise Refused(f"{f} is mode {stat.S_IMODE(st.st_mode):o}: it must be 600 (only the owner may read it)")
    value = f.read_text().strip()
    if not value or "\n" in value:
        raise Refused(f"{f} must hold the token alone, on one line")
    return value


def docker(*args: str, check: bool = True, timeout: int = 120) -> subprocess.CompletedProcess:
    r = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout,
                       env={k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "DOCKER_HOST", "DOCKER_CONFIG",
                                                                          "DOCKER_CONTEXT", "TMPDIR")})
    if check and r.returncode:
        raise RuntimeError(f"docker {args[0]}: {r.stderr.strip()[-300:]}")
    return r


def egress(cfg: dict) -> None:
    """The internal network and the egress proxy on it, started when not running (under a lock: two sessions starting
    together never race to create them)."""
    import fcntl
    with open(fac.run_dir(cfg) / "egress.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            _egress(cfg)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _egress(cfg: dict) -> None:
    if docker("network", "inspect", NET, check=False).returncode:
        docker("network", "create", "--internal", NET)
    got = docker("inspect", "-f", "{{.State.Running}}", PROXY, check=False)
    if got.stdout.strip() == "true":
        return
    docker("rm", "-f", PROXY, check=False)
    s = settings(cfg)
    docker("run", "-d", "--name", PROXY, "--restart", "unless-stopped", "--network", "bridge", "--cap-drop", "ALL",
           "--security-opt", "no-new-privileges", "-v", f"{fac.HERE / 'agent'}:/egress:ro", s["proxy_image"],
           "python3", "/egress/egress.py", str(PORT), *s["hosts"])
    docker("network", "connect", NET, PROXY)


def claude_args(cfg: dict, role: str, sid: str | None = None) -> list[str]:
    usd = float(cfg["ai"][f"{role}_session_usd"])
    tools = TOOLS[role]
    return ["claude", "-p", "--model", cfg["ai"][f"{role}_model"], "--output-format", "json",
            *(["--session-id", sid] if sid else []), "--max-budget-usd", f"{usd:g}", "--restricted",
            "--tools", ",".join(sorted({t.split("(", 1)[0] for t in tools})),
            "--permission-mode", "dontAsk", "--strict-mcp-config", "--allowedTools", ",".join(tools),
            "--disallowedTools", ",".join(d for d in DENY if d not in tools)]


def run_args(cfg: dict, role: str, work: Path, name: str, keep=None) -> list[str]:
    """`docker run` for a session: the token by name only (its value is in the docker client's environment alone).
    ``keep`` (sessions.Session): its own folder mounted as Claude Code's projects folder, and its session id."""
    proxy = f"http://{PROXY}:{PORT}"
    return ["run", "--rm", "-i", "--name", name, "--network", NET, *limits(cfg, "session"), *SHOTS,
            "-v", f"{work}:/work{':ro' if role != 'implementor' else ''}", "-w", "/work",
            *(["-v", f"{keep.raw}:{keep.HOME}"] if keep else []),
            "-e", "CLAUDE_CODE_OAUTH_TOKEN", "-e", f"HTTPS_PROXY={proxy}", "-e", f"https_proxy={proxy}",
            "-e", "NO_PROXY=", *[x for k in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME") for x in ("-e", f"{k}=factory")],
            *[x for k in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL") for x in ("-e", f"{k}=factory@localhost")],
            settings(cfg)["image"], *claude_args(cfg, role, keep.sid if keep else None)]


RUNNING: set[str] = set()                # this process's containers, killed on any way out (killed())


def killed(name: str) -> None:
    docker("kill", name, check=False, timeout=60)
    docker("rm", "-f", name, check=False, timeout=60)
    RUNNING.discard(name)


def kill_all(*_) -> None:
    for name in list(RUNNING):
        killed(name)


def container(role: str) -> str:
    name = f"{PREFIX}{role}-{uuid.uuid4().hex[:10]}"
    RUNNING.add(name)
    return name


def sweep(cfg: dict) -> list[str]:
    """Containers of the factory's left past their time (a run killed before its finally): removed. Their names."""
    got = docker("ps", "-a", "--filter", f"name={PREFIX}", "--format", "{{.Names}}\t{{.CreatedAt}}", check=False)
    gone = []
    for line in got.stdout.splitlines():
        name, _, created = line.partition("\t")
        role = name[len(PREFIX):].rsplit("-", 1)[0]
        try:
            t = time.mktime(time.strptime(created[:19], "%Y-%m-%d %H:%M:%S"))
        except ValueError:
            continue
        if name not in RUNNING and time.time() - t > TIMEOUTS.get(role, 7200) + 600:
            killed(name)
            gone.append(name)
    return gone


def session(cfg: dict, role: str, brief: str, work: Path, timeout: int | None = None, keep=None) -> dict:
    """One session in its container; Claude Code's result message. Raises on a failure (a timeout kills it; so does
    any way out of this process: the container is killed in a finally). ``keep`` (sessions.Session): its transcript
    copied as it grows, the token scrubbed."""
    import resources
    timeout = timeout or TIMEOUTS[role]
    tok = token(cfg)
    sweep(cfg)
    egress(cfg)
    name = container(role)
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "DOCKER_HOST", "DOCKER_CONFIG",
                                                        "DOCKER_CONTEXT", "TMPDIR")}
    env["CLAUDE_CODE_OAUTH_TOKEN"] = tok
    stop = None
    if keep:
        keep.copy.tok = tok
        stop = keep.copy.follow()
    try:
        with resources.sampled(cfg, name, role) as use:
            r = subprocess.run(["docker", *run_args(cfg, role, work, name, keep)], input=brief, capture_output=True,
                               text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"the {role} session ran past {timeout}s and was killed") from None
    finally:
        del env["CLAUDE_CODE_OAUTH_TOKEN"]
        killed(name)
        if stop:
            stop()
    said = scrub(r.stdout, tok)
    try:
        out = json.loads(said.strip().splitlines()[-1]) if said.strip() else None
    except json.JSONDecodeError:
        out = None
    if not isinstance(out, dict):
        raise RuntimeError(f"the {role} session answered no result (exit {r.returncode}): "
                           f"{scrub(r.stderr or said, tok)[-300:]}")
    return out | ({"resources": use} if use else {})


def scrub(text: str, tok: str) -> str:
    return text.replace(tok, "[token]") if tok else text


# ---- the work: clones made here, bundles back

def drop(cfg: dict) -> Path:
    """The factory's own bare repository: what sessions return lands here, never in the owner's. Its main is the
    checkout's ``refs/remotes/<remote>/<base>`` (main as pushed), never the checkout's own main. Under
    <live>/drop.git.lock (sessions starting together fetched at once and failed on git's ref lock); a fetch that still
    fails on a ref lock is tried again, at most DROP_TRIES times in all; any other error raises at once."""
    import fcntl
    d = fac.path(cfg, "live") / "drop.git"
    d.parent.mkdir(parents=True, exist_ok=True)
    with open(d.parent / "drop.git.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)              # (released when the file closes, on any way out)
        if not (d / "HEAD").exists():
            fac.git(d.parent, "init", "-q", "--bare", str(d))
        base = cfg["git"]["base"]
        fac.git(d, "symbolic-ref", "HEAD", f"refs/heads/{base}")
        # main as pushed (the checkout's <remote>/<base>), never the checkout's own main, where the queue merges
        # before testing: branches forked from that carried merges that later failed and were undone (2026-11-20)
        remote = cfg["git"].get("remote", "origin")
        for tried in range(1, DROP_TRIES + 1):
            try:
                fac.git(d, "fetch", "-q", str(fac.path(cfg, "checkout")),
                        f"+refs/remotes/{remote}/{base}:refs/heads/{base}")
                break
            except RuntimeError as e:
                if "cannot lock ref" not in str(e) or tried == DROP_TRIES:
                    raise
                time.sleep(0.2 * tried)
    return d


DROP_TRIES = 3                           # a hard ceiling (lesson-4): fetches of the drop's main, in all


def scratch(cfg: dict, branch: str, role: str) -> Path:
    """A fresh folder for one session's work, under <live>/sessions/ (refusing anything that resolves elsewhere)."""
    root = (fac.path(cfg, "live") / "sessions").resolve()
    d = (root / f"{branch}-{role}-{time.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}").resolve()
    if root not in d.parents:
        raise ValueError(f"{d} is outside {root}")
    d.mkdir(parents=True)
    return d


def clone(cfg: dict, branch: str, role: str, at: str | None = None) -> tuple[Path, Path]:
    """(the session's folder, its work): a clone of the drop on the gap's branch (made from main when new), or
    detached at ``at``. Made here, before any session touches it; its remote removed."""
    d = drop(cfg)
    home = scratch(cfg, branch, role)
    work = home / "work"
    ref = fac.git_branch(branch)
    fac.git(home, "clone", "-q", "--no-hardlinks", str(d), str(work))
    if at:
        fac.git(work, "checkout", "-q", "--detach", at)
    elif fac.git_ok(d, "rev-parse", "--verify", "-q", f"refs/heads/{ref}"):
        fac.git(work, "checkout", "-q", "-b", ref, f"origin/{ref}")
    else:
        fac.git(work, "checkout", "-q", "-b", ref, f"origin/{cfg['git']['base']}")
    return home, work


def publish(cfg: dict, work: Path, branch: str) -> str:
    """Before the session: what this program committed in the work (the definition) to the drop, then the remote
    removed, so nothing in the container names a host path. The sha published: `finish` moves the drop's branch only
    from it."""
    ref = fac.git_branch(branch)
    fac.git(work, "push", "-q", "origin", f"{ref}:refs/heads/{ref}")
    fac.git(work, "remote", "remove", "origin")
    return fac.git(work, "rev-parse", ref)


def finish(cfg: dict, home: Path, branch: str, base_sha: str, must_hold: str, *also: str, was: str) -> str:
    """After the implementor's session: what it left committed, and bundled, in a container with no network (git is
    never run here on a folder a session had); the bundle fetched into the drop, to a side ref of its run's own first:
    the branch moves only when the new head holds the definition's commit and each of `also` (main, when it was merged
    in), and only from `was`, the sha the session was given (update-ref's old value): a branch another writer moved
    meanwhile is refused, not overwritten. The new head."""
    ref = fac.git_branch(branch)
    out = home / "out"
    out.mkdir(exist_ok=True)
    script = ("set -e; g='git -c core.hooksPath=/dev/null -c core.fsmonitor= -c commit.gpgsign=false'; "
              "if [ -e .git/MERGE_HEAD ]; then echo 'the session left its merge of main unfinished' >&2; exit 3; fi; "
              f"$g add -A; $g diff --cached --quiet || $g -c user.name=factory -c user.email=factory@localhost "
              f"commit -q -m {shlex.quote(f'{branch}: work the session left uncommitted')}; "
              f"$g bundle create /out/out.bundle {shlex.quote(base_sha)}..{shlex.quote(ref)} 2>/dev/null || "
              f"$g bundle create /out/out.bundle {shlex.quote(ref)}")
    if cfg["ai"]["mode"] == "standin":
        subprocess.run(["sh", "-c", script.replace("/out/", f"{out}/")], cwd=home / "work", check=True,
                       capture_output=True)
    else:
        name = container("finish")
        try:
            docker("run", "--rm", "--name", name, "--network", "none", *limits(cfg, "session"),
                   "-v", f"{home / 'work'}:/work", "-v", f"{out}:/out", "-w", "/work", settings(cfg)["image"], "sh", "-c", script,
                   timeout=TIMEOUTS["finish"])
        finally:
            killed(name)
    d = drop(cfg)
    fac.git(d, "bundle", "verify", "-q", str(out / "out.bundle"))
    side = f"refs/incoming/{home.name}/{ref}"            # (one per run: overlapping finishes never share it)
    fac.git(d, "fetch", "-q", str(out / "out.bundle"), f"+refs/heads/{ref}:{side}")
    head = fac.git(d, "rev-parse", side)
    try:
        for sha, what in [(must_hold, "its definition's commit"), *((a, "main, merged in before it") for a in also)]:
            if not fac.git_ok(d, "merge-base", "--is-ancestor", sha, head):
                raise RuntimeError(f"the branch no longer holds {what} {sha[:12]}: refused (the drop's branch kept)")
        if not fac.git_ok(d, "update-ref", f"refs/heads/{ref}", head, was):
            raise RuntimeError(f"the drop's branch moved from {was[:12]} during the session: refused (theirs kept)")
    finally:
        fac.git(d, "update-ref", "-d", side)
    return head


def suites(cfg: dict, home: Path, names: tuple[str, ...], logs: Path, tag: str, tests: list[str] | None = None) -> dict:
    """The fast suites on a session's work, each in a named container with no network, in a machine-wide slot;
    ``tests``: the test ids a suite's `{tests}` names (each shell-quoted)."""
    import resources
    out: dict = {}
    held = fac.quarantine(fac.path(cfg, "live") / "drop.git", cfg["git"]["base"])    # main's list: run beside
    own = [t for t in fac.quarantine(home / "work", "HEAD") if t not in held]   # the work's own lines: deselected
    for n in names:                                    # here only (this run lands nothing; the queue reads main's)
        cmd, name = cfg["suites"][n], None
        if tests is not None:
            cmd = cmd.format(tests=" ".join(map(shlex.quote, tests)))
        cmd = fac.deselected("unit" if n == "build" else n, cmd, held + own)   # (build: the unit suite's few)
        if cfg["ai"]["mode"] != "standin":
            name, cmd = contained(cfg, cmd, home / "work")
        log = logs / f"{tag}-{n}.txt"
        try:
            with resources.sampled(cfg, name, "suite") if name else contextlib.nullcontext({}) as use:
                rc, secs = fac.suite(cfg, n, home / "work", log, command=cmd)
        finally:
            if name:
                killed(name)
        out[n] = {"rc": rc, "seconds": round(secs)} | ({"resources": use} if use else {})
        text = log.read_text()
        skipped = max([len(re.findall(r"^SKIPPED", text, re.M))] + [int(k) for k in re.findall(  # (-rs's lines, or
            r"\b(\d+) skipped\b", text)]) if n in ("browser", "rerun") else 0   # pytest's summary; a skip fails, as
        if rc or skipped:                                                                   # in the queue)
            out[n] |= {"skipped": skipped} if skipped else {}
            out.update(failed=n, tail=text[-3000:], tests=fac.failed_tests(text))
            break
    if "unit" in out or "build" in out:                # the quarantined tests beside it, never blocking
        fac.beside(held, logs / f"{tag}-quarantined-alone.txt",
                   lambda ts: suites(cfg, home, ("alone",), logs, f"{tag}-quarantined", tests=ts))
    return out


def browser_ready(cfg: dict, home: Path, logs: Path, tag: str) -> None:
    """Playwright and its Chromium launched once, in a suite container of the implementor's image on the session's
    work, in the suite slot, before the round: missing (or no [suites] browser_ready to say how), the round stops here
    (Refused, uncounted), never a browser file skipped later."""
    if not str(cfg["suites"].get("browser_ready") or "").strip():
        raise Refused("no [suites] browser_ready in the factory's settings: the round cannot know the browser is there")
    got = suites(cfg, home, ("browser_ready",), logs, tag)
    if got.get("failed"):
        raise Refused(f"no browser: Playwright's Chromium does not launch in {settings(cfg)['image']} (the browser files "
                      f"would skip); rebuild the dev image, then `docker build -t {settings(cfg)['image']} dev/agent`. "
                      f"It said: {got['tail'][-400:]}")


def contained(cfg: dict, cmd: str, work: Path, role: str = "suite") -> tuple[str, str]:
    """(a suite container's name, the command that runs ``cmd`` in it on ``work``, with no network). ``role``, in its
    name: how long another process's sweep() leaves it (TIMEOUTS)."""
    name = container(role)
    return name, " ".join(["docker", "run", "--rm", "--name", name, "--network", "none", *limits(cfg, "suite"), *SHOTS,
                           "-v", f"{work}:/work", "-w", "/work", settings(cfg)["image"], "sh", "-c", shlex.quote(cmd)])


CPUSET = re.compile(r"^[0-9]+(-[0-9]+)?(,[0-9]+(-[0-9]+)?)*$")


def limits(cfg: dict, kind: str, cpus: float | None = None) -> list[str]:
    """LIMITS for one kind of container: `session`, `suite` (a gap's own suites) or `queue` (the merge queue's and flake
    triage's), each pinned to its own CPUs of Docker's VM by [agents] <kind>_cpuset (empty: not pinned), so none slows
    another. ``cpus``: its --cpus (a session's: [agents] session_cpus; else LIMITS' 4). A cpuset that is not a list of
    CPUs and ranges is refused (raised), never dropped."""
    a = cfg.get("agents") or {}
    cpus = cpus or (session_cpus(a) if kind == "session" else None)
    out = list(LIMITS)
    if cpus:
        out[out.index("--cpus") + 1] = f"{float(cpus):g}"
    pin = str(a.get(f"{kind}_cpuset") or "").strip()
    if pin and not CPUSET.match(pin):
        raise ValueError(f"[agents] {kind}_cpuset = {pin!r}: not a cpuset such as '12-23' or '0,2-5'")
    return out + (["--cpuset-cpus", pin] if pin else [])


QUEUE_CPUS = {"unit": 8, "browser": 4}   # the queue's unit and browser run at once in queue_cpuset (12); others 4
NOT_STARTED = (125, 126, 127)            # docker run's own failure, or a command that could not be run in it


class NotStarted(RuntimeError):
    """A queue suite's container that did not start: an infrastructure failure, never a red suite or a gap's fault."""


def queued(cfg: dict, suite: str, cmd: str, work: Path, box: str, env: tuple = ()) -> tuple[str, str]:
    """(a container's name, the shell command that runs ``cmd`` in it): one of the merge queue's (``box`` "queue") or
    flake triage's ("triage") suites, in the agent image on ``work`` at /work, with no network (a demo's servers and
    ports in its own namespace), pinned to [agents] queue_cpuset. The checkout is a copy, never a bind mount (Docker
    Desktop's file sharing keeps a handle open on every file a container reads through one,
    dev/records/suites-copy-their-checkout-into-the-container.md): tarred on the Mac (all but its .venv, with its git
    directory when that is inside it) into the container's stdin and unpacked at /work before ``cmd``, a copy that
    did not unpack exiting 125 (NotStarted); so the Mac's checkout is kept as the Mac left it. The image's own
    environment (/opt/venv); bytecode and ruff's cache under /tmp; a worktree's git directory (outside it) read-only at
    its own path. run/coverage/ mounted at its own path, as the unit run's ERGOSTAT_COVERAGE names it, so what it writes
    there reaches run/. ``env``: more NAME=value settings for it (fac.suite's PYTEST_ADDOPTS)."""
    name, work = container(f"suite-{box}"), work.resolve()
    common = Path(fac.git(work, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()
    cov = fac.run_dir(cfg, "coverage").resolve()
    git = [] if common.is_relative_to(work) else ["-v", f"{common}:{common}:ro"]
    args = ["docker", "run", "-i", "--rm", "--name", name, "--network", "none",
            *limits(cfg, "queue", QUEUE_CPUS.get(suite, 4)), *SHOTS, "-v", f"{cov}:{cov}", *git,
            "-e", "UV_PROJECT_ENVIRONMENT=/opt/venv", "-e", "PYTHONPYCACHEPREFIX=/tmp/pycache",
            "-e", "RUFF_CACHE_DIR=/tmp/ruff", *[x for e in env for x in ("-e", e)], "-w", "/work", settings(cfg)["image"],
            "sh", "-c", 'tar -xf - || exit 125; exec sh -c "$1"', "sh", cmd]
    copy = f"COPYFILE_DISABLE=1 tar -C {shlex.quote(str(work))} --exclude ./.venv --no-xattrs --no-acls -cf - ."
    return name, f"{copy} | {shlex.join(args)}"   # (macOS's tar: no ._ files, no headers GNU tar warns of)


def sweep_box(box: str) -> list[str]:
    """The ``box``'s containers left by a run killed with no finally (SIGKILL): removed now, by name. Called under
    the lock that lets one such run at a time (the queue's), so none of them is a live run's."""
    got = docker("ps", "-a", "--filter", f"name={PREFIX}suite-{box}-", "--format", "{{.Names}}", check=False)
    for name in got.stdout.split():
        killed(name)
    return got.stdout.split()


def suite_containers() -> int:
    """The factory's suite containers running now (the load interlock counts them: their processes are in Docker's VM)."""
    try:
        got = subprocess.run(["docker", "ps", "-q", "--filter", f"name={PREFIX}suite-"], capture_output=True,
                             text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return 0
    return len(got.stdout.split())
