"""``ergostat run --service``: this repository's ergostat kept running across crashes, logins and reboots by the
machine's own service manager: a user LaunchAgent on macOS (``~/Library/LaunchAgents``), a systemd user unit
elsewhere (``~/.config/systemd/user``). What it keeps running is the outer watcher (``watcher.py``), which starts the
engine and starts it again when it dies or freezes; the service manager keeps the watcher itself alive. Printed by
``--service`` (the owner's decision, docs/cli-rounds.md), installed and loaded by ``--service --install``, removed by
``--service --uninstall``. It runs the installed ergostat's Python, never a worktree's or a temporary one's."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from xml.sax.saxutils import escape


def python() -> str | None:
    """The Python of an ``ergostat`` installed on PATH (each one in turn, as ``which -a``): its script's ``#!`` naming a
    Python, never a launcher (``/usr/bin/env``, a shell), a temporary one (uv's cache, the temporary folder) or a
    repository's own ``.venv``: a service must outlive whatever ran this."""
    import tempfile
    tmp = tempfile.gettempdir()
    bad = ("/.cache/uv/", "/uv/archive", tmp, str(Path(tmp).resolve()), "/.venv/")
    for d in os.environ.get("PATH", "").split(os.pathsep):
        script = Path(d or ".") / "ergostat"
        try:
            if not (script.is_file() and os.access(script, os.X_OK)):
                continue
            first = open(script, "rb").readline().decode(errors="replace")
        except OSError:
            continue
        words = first[2:].split() if first.startswith("#!") else []
        py = words[0] if len(words) == 1 else ""
        if Path(py).name.startswith("python") and Path(py).is_file() and not any(b in py for b in bad):
            return py
    return None


def command(repo: Path, extra: list[str], py: str) -> list[str]:
    """The outer watcher of the installed ergostat (``python()``)."""
    return [py, "-m", "ergostat.watcher", "-C", str(repo), *extra]


def _env() -> dict:
    """What the agents need from this shell: ERGOSTAT_HOME, and PATH with each folder once."""
    out = {}
    if "ERGOSTAT_HOME" in os.environ:
        out["ERGOSTAT_HOME"] = os.environ["ERGOSTAT_HOME"]
    if "PATH" in os.environ:
        out["PATH"] = ":".join(dict.fromkeys(x for x in os.environ["PATH"].split(":") if x))
    return out


def label(name: str) -> str:
    return "local.ergostat." + "".join(ch if ch.isalnum() or ch in "-." else "-" for ch in name)


def launchd(name: str, repo: Path, cmd: list[str], state: Path) -> str:
    env = _env()
    args = "\n".join(f"    <string>{escape(a)}</string>" for a in cmd)
    envs = "\n".join(f"    <key>{escape(k)}</key><string>{escape(v)}</string>" for k, v in env.items())
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{label(name)}</string>
  <key>ProgramArguments</key>
  <array>
{args}
  </array>
  <key>WorkingDirectory</key><string>{escape(str(repo))}</string>
  <key>EnvironmentVariables</key>
  <dict>
{envs}
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/dev/null</string>
  <key>StandardErrorPath</key><string>{escape(str(state / "watcher.err"))}</string>
</dict>
</plist>
"""


def systemd(name: str, repo: Path, cmd: list[str], state: Path) -> str:
    def pct(a: str) -> str:                     # % starts a specifier everywhere in a unit
        return a.replace("%", "%%")

    def q(a: str) -> str:                       # ExecStart's words: quoted when needed, $ not expanded
        a = pct(a).replace("$", "$$")
        return '"' + a.replace("\\", "\\\\").replace('"', '\\"') + '"' if any(c in a for c in ' "\\') else a

    def qe(a: str) -> str:                      # an Environment= assignment
        a = pct(a)
        return '"' + a.replace("\\", "\\\\").replace('"', '\\"') + '"' if any(c in a for c in ' "\\') else a
    env = "".join(f"Environment={qe(k + '=' + v)}\n" for k, v in _env().items())
    log = pct(str(state / "watcher.err"))
    return f"""[Unit]
Description=ergostat for {pct(name)} ({pct(str(repo))})

[Service]
WorkingDirectory={pct(str(repo))}
ExecStart={" ".join(q(a) for a in cmd)}
{env}Restart=always
RestartSec=5
StandardOutput=null
StandardError=append:{log}

[Install]
WantedBy=default.target
"""


def where(name: str, kind: str = "auto") -> tuple[str, Path, list[list[str]], list[list[str]]]:
    """(launchd or systemd, the file's place in the owner's home, the commands that load it, those that unload it)."""
    if kind == "launchd" or (kind == "auto" and sys.platform == "darwin"):
        path = Path.home() / "Library" / "LaunchAgents" / f"{label(name)}.plist"
        gui = f"gui/{os.getuid()}"
        return "launchd", path, [["launchctl", "bootstrap", gui, str(path)]], [["launchctl", "bootout", f"{gui}/{label(name)}"]]
    unit = f"ergostat-{label(name).removeprefix('local.ergostat.')}.service"
    ctl = ["systemctl", "--user"]
    return "systemd", Path.home() / ".config" / "systemd" / "user" / unit, \
        [[*ctl, "daemon-reload"], [*ctl, "enable", "--now", unit]], [[*ctl, "disable", "--now", unit]]


def text(project, extra: list[str], kind: str, py: str) -> tuple[str, Path, list[list[str]], list[list[str]]]:
    """(the service's text, where it goes, the commands that load it, those that unload it), for this machine's
    service manager, or the one named (``launchd``, ``systemd``: a unit for a Linux box can be read on a Mac). Named
    by the state folder (the model's name and its repository's hash): one per repository."""
    key, repo, state = project.dir.name, project.repo, project.dir
    how, path, load, unload = where(key, kind)
    body = (launchd if how == "launchd" else systemd)(key, repo, command(repo, extra, py), state)
    return body, path, load, unload


def run(cmds: list[list[str]]) -> list[str]:
    """Each command run; what went wrong with any, said."""
    import subprocess
    wrong = []
    for c in cmds:
        try:
            got = subprocess.run(c, capture_output=True, text=True, timeout=30)
            if got.returncode:
                wrong.append(f"{' '.join(c)}: {(got.stderr or got.stdout).strip() or f'exit {got.returncode}'}")
        except (OSError, subprocess.TimeoutExpired) as e:
            wrong.append(f"{' '.join(c)}: {e}")
    return wrong
