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
TOOLS = {
    "implementor": ["Read", "Edit", "Write", "Glob", "Grep", "Bash(git status:*)", "Bash(git diff:*)",
                    "Bash(git log:*)", "Bash(git show:*)", "Bash(git add:*)", "Bash(git commit:*)",
                    "Bash(git merge:*)",           # (to finish main's merge, implement.py; its clone has no remote)
                    "Bash(uv run python -m pytest:*)", "Bash(uv run ruff check:*)", "Bash(ls:*)", "Bash(wc:*)",
                    "Bash(mkdir:*)"],
    "reviewer": ["Read", "Glob", "Grep", "Bash(git diff:*)", "Bash(git log:*)", "Bash(git show:*)"],
}
PREFIX = "ergostat-factory-"          # every container the factory starts is named so (the sweeper finds them)
TIMEOUTS = {"implementor": 7200, "reviewer": 3600, "finish": 600, "suite": 3600, "planner": 3600,
            "plan_reviewer": 1200, "researcher": 3600, "librarian": 600,
            "pipeline_manager": 2400}   # seconds, each below its block's
LIMITS = ["--init", "--pids-limit", "4096", "--memory", "12g", "--memory-swap", "12g", "--cpus", "4", "--cap-drop", "ALL",
          "--security-opt", "no-new-privileges", "--tmpfs", "/tmp:rw,exec,size=2g"]
TOOLS.update(planner=TOOLS["reviewer"], plan_reviewer=TOOLS["reviewer"], librarian=["Read"],
             pipeline_manager=TOOLS["reviewer"],
             researcher=TOOLS["reviewer"] + ["WebSearch"])      # all read-only: only the implementor writes; WebSearch is
                                                                 # run by the API itself


class Refused(RuntimeError):
    """A session that must not start (no token, a token file others may read): said without the token."""


def settings(cfg: dict) -> dict:
    a = cfg.get("agents") or {}
    return {"image": a.get("image", "ergostat-agent:latest"), "hosts": list(a.get("hosts") or ["api.anthropic.com"]),
            "token_file": Path(os.path.expanduser(a.get("token_file", "~/.config/ergostat/claude-token"))),
            "proxy_image": a.get("proxy_image", "ergostat-dev:latest")}


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
    return ["run", "--rm", "-i", "--name", name, "--network", NET, *LIMITS,
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
    """The factory's own bare repository: what sessions return lands here, never in the owner's."""
    d = fac.path(cfg, "live") / "drop.git"
    if not (d / "HEAD").exists():
        d.parent.mkdir(parents=True, exist_ok=True)
        fac.git(d.parent, "init", "-q", "--bare", str(d))
    base = cfg["git"]["base"]
    fac.git(d, "symbolic-ref", "HEAD", f"refs/heads/{base}")
    fac.git(d, "fetch", "-q", str(fac.path(cfg, "checkout")), f"+refs/heads/{base}:refs/heads/{base}")
    return d


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
            docker("run", "--rm", "--name", name, "--network", "none", *LIMITS, "-v", f"{home / 'work'}:/work",
                   "-v", f"{out}:/out", "-w", "/work", settings(cfg)["image"], "sh", "-c", script,
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
    for n in names:
        cmd, name = cfg["suites"][n], None
        if tests is not None:
            cmd = cmd.format(tests=" ".join(map(shlex.quote, tests)))
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
        if rc:
            text = log.read_text()
            out.update(failed=n, tail=text[-3000:], tests=fac.failed_tests(text))
            break
    return out


def contained(cfg: dict, cmd: str, work: Path) -> tuple[str, str]:
    """(a suite container's name, the command that runs ``cmd`` in it on ``work``, with no network)."""
    name = container("suite")
    return name, " ".join(["docker", "run", "--rm", "--name", name, "--network", "none", *LIMITS, "-v", f"{work}:/work",
                           "-w", "/work", settings(cfg)["image"], "sh", "-c", shlex.quote(cmd)])


def suite_containers() -> int:
    """The factory's suite containers running now (the load interlock counts them: their processes are in Docker's VM)."""
    try:
        got = subprocess.run(["docker", "ps", "-q", "--filter", f"name={PREFIX}suite-"], capture_output=True,
                             text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return 0
    return len(got.stdout.split())
