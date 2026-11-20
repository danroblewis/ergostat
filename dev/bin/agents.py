"""The implementor's and the reviewer's sessions, each in a Docker container of its own (the owner, 2026-11-20: "the
risk is much lower"). What a session's container is given, and nothing else:

- **its work**: a clone made by this program (never the owner's repository or its .git), mounted at /work: read-write
  for the implementor, read-only for the reviewer. Its result comes out as a git bundle (``finish``, in a container of
  its own with no network), fetched into the factory's drop repository (``<live>/drop.git``), never the owner's;
- **the network to the Anthropic API alone**: the container is on an internal Docker network (no route out) whose
  only way out is the egress proxy (dev/agent/egress.py, its own container), which tunnels to [agents] hosts on 443;
- **one secret, the session token**: read from [agents] token_file (mode 600, written by the owner from
  `claude setup-token`), given as CLAUDE_CODE_OAUTH_TOKEN at `docker run` by name (never in the command line, a log
  or an error), and nothing else of the host's environment: no home, no ERGOSTAT_*, no other variable;
- the dev image's limits (processes, memory, CPUs), no capabilities, no new privileges; removed when it ends.

Inside, Claude Code still runs --restricted, with the role's narrow tools, in dontAsk mode: a second layer."""

from __future__ import annotations

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
                    "Bash(uv run python -m pytest:*)", "Bash(uv run ruff check:*)", "Bash(ls:*)", "Bash(wc:*)",
                    "Bash(mkdir:*)"],
    "reviewer": ["Read", "Glob", "Grep", "Bash(git diff:*)", "Bash(git log:*)", "Bash(git show:*)"],
}
LIMITS = ["--pids-limit", "4096", "--memory", "12g", "--memory-swap", "12g", "--cpus", "4", "--cap-drop", "ALL",
          "--security-opt", "no-new-privileges", "--tmpfs", "/tmp:rw,exec,size=2g"]


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
    """The internal network and the egress proxy on it, started when not running."""
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


def claude_args(cfg: dict, role: str) -> list[str]:
    usd = float(cfg["ai"][f"{role}_session_usd"])
    tools = TOOLS[role]
    return ["claude", "-p", "--model", cfg["ai"][f"{role}_model"], "--output-format", "json", "--max-budget-usd",
            f"{usd:g}", "--restricted", "--tools", ",".join(sorted({t.split("(", 1)[0] for t in tools})),
            "--permission-mode", "dontAsk", "--strict-mcp-config", "--allowedTools", ",".join(tools),
            "--disallowedTools", ",".join(DENY)]


def run_args(cfg: dict, role: str, work: Path, name: str) -> list[str]:
    """`docker run` for a session: the token by name only (its value is in the docker client's environment alone)."""
    proxy = f"http://{PROXY}:{PORT}"
    return ["run", "--rm", "-i", "--name", name, "--network", NET, *LIMITS,
            "-v", f"{work}:/work{':ro' if role == 'reviewer' else ''}", "-w", "/work",
            "-e", "CLAUDE_CODE_OAUTH_TOKEN", "-e", f"HTTPS_PROXY={proxy}", "-e", f"https_proxy={proxy}",
            "-e", "NO_PROXY=", *[x for k in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME") for x in ("-e", f"{k}=factory")],
            *[x for k in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL") for x in ("-e", f"{k}=factory@localhost")],
            settings(cfg)["image"], *claude_args(cfg, role)]


def session(cfg: dict, role: str, brief: str, work: Path, timeout: int = 3 * 3600) -> dict:
    """One session in its container; Claude Code's result message. Raises on a failure (a timeout kills it)."""
    tok = token(cfg)
    egress(cfg)
    name = f"ergostat-{role}-{uuid.uuid4().hex[:10]}"
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "DOCKER_HOST", "DOCKER_CONFIG",
                                                        "DOCKER_CONTEXT", "TMPDIR")}
    env["CLAUDE_CODE_OAUTH_TOKEN"] = tok
    try:
        r = subprocess.run(["docker", *run_args(cfg, role, work, name)], input=brief, capture_output=True, text=True,
                           timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        docker("kill", name, check=False)
        raise RuntimeError(f"the {role} session ran past {timeout}s and was killed") from None
    finally:
        del env["CLAUDE_CODE_OAUTH_TOKEN"]
    said = scrub(r.stdout, tok)
    try:
        out = json.loads(said.strip().splitlines()[-1]) if said.strip() else None
    except json.JSONDecodeError:
        out = None
    if not isinstance(out, dict):
        raise RuntimeError(f"the {role} session answered no result (exit {r.returncode}): "
                           f"{scrub(r.stderr or said, tok)[-300:]}")
    return out


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


def publish(cfg: dict, work: Path, branch: str) -> None:
    """Before the session: what this program committed in the work (the definition) to the drop, then the remote
    removed, so nothing in the container names a host path."""
    ref = fac.git_branch(branch)
    fac.git(work, "push", "-q", "origin", f"{ref}:refs/heads/{ref}")
    fac.git(work, "remote", "remove", "origin")


def finish(cfg: dict, home: Path, branch: str, base_sha: str, must_hold: str) -> str:
    """After the implementor's session: what it left committed, and bundled, in a container with no network (git is
    never run here on a folder a session had); the bundle fetched into the drop. The new head (it must still hold the
    definition's commit)."""
    ref = fac.git_branch(branch)
    out = home / "out"
    out.mkdir(exist_ok=True)
    script = ("set -e; g='git -c core.hooksPath=/dev/null -c core.fsmonitor= -c commit.gpgsign=false'; "
              f"$g add -A; $g diff --cached --quiet || $g -c user.name=factory -c user.email=factory@localhost "
              f"commit -q -m {shlex.quote(f'{branch}: work the session left uncommitted')}; "
              f"$g bundle create /out/out.bundle {shlex.quote(base_sha)}..{shlex.quote(ref)} 2>/dev/null || "
              f"$g bundle create /out/out.bundle {shlex.quote(ref)}")
    if cfg["ai"]["mode"] == "standin":
        subprocess.run(["sh", "-c", script.replace("/out/", f"{out}/")], cwd=home / "work", check=True,
                       capture_output=True)
    else:
        docker("run", "--rm", "--network", "none", *LIMITS, "-v", f"{home / 'work'}:/work", "-v", f"{out}:/out",
               "-w", "/work", settings(cfg)["image"], "sh", "-c", script, timeout=600)
    d = drop(cfg)
    fac.git(d, "bundle", "verify", "-q", str(out / "out.bundle"))
    fac.git(d, "fetch", "-q", str(out / "out.bundle"), f"+refs/heads/{ref}:refs/heads/{ref}")
    head = fac.git(d, "rev-parse", f"refs/heads/{ref}")
    if not fac.git_ok(d, "merge-base", "--is-ancestor", must_hold, head):
        raise RuntimeError(f"the branch no longer holds its definition's commit {must_hold[:12]}: refused")
    return head


def suites(cfg: dict, home: Path, names: tuple[str, ...], logs: Path, tag: str) -> dict:
    """The fast suites on a session's work, in a container with no network, each in a machine-wide slot."""
    out: dict = {}
    for name in names:
        cmd = cfg["suites"][name]
        if cfg["ai"]["mode"] != "standin":
            cmd = " ".join(["docker", "run", "--rm", "--network", "none", *LIMITS, "-v", f"{home / 'work'}:/work",
                            "-w", "/work", settings(cfg)["image"], "sh", "-c", shlex.quote(cmd)])
        log = logs / f"{tag}-{name}.txt"
        rc, secs = fac.suite(cfg, name, home / "work", log, command=cmd)
        out[name] = {"rc": rc, "seconds": round(secs)}
        if rc:
            text = log.read_text()
            out.update(failed=name, tail=text[-3000:], tests=fac.failed_tests(text))
            break
    return out

