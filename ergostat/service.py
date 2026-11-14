"""``ergostat run --service``: the text that keeps this repository's ergostat running across logins
and reboots, for the machine's own service manager (launchd on macOS, systemd elsewhere). Printed,
never installed: where it goes and when it is loaded is the owner's to decide."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from xml.sax.saxutils import escape


def command(repo: Path, extra: list[str]) -> list[str]:
    """This very ergostat (the Python running it), not whichever is first on PATH."""
    return [sys.executable, "-m", "ergostat", "-C", str(repo), "run", "--foreground", *extra]


def label(name: str) -> str:
    return "local.ergostat." + "".join(ch if ch.isalnum() or ch in "-." else "-" for ch in name)


def launchd(name: str, repo: Path, cmd: list[str], state: Path) -> str:
    env = {k: os.environ[k] for k in ("ERGOSTAT_HOME", "PATH") if k in os.environ}
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
  <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
  <key>StandardOutPath</key><string>{escape(str(state / "run.log"))}</string>
  <key>StandardErrorPath</key><string>{escape(str(state / "run.log"))}</string>
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
    env = "".join(f"Environment={qe(k + '=' + os.environ[k])}\n" for k in ("ERGOSTAT_HOME", "PATH") if k in os.environ)
    log = pct(str(state / "run.log"))
    return f"""[Unit]
Description=ergostat for {pct(name)} ({pct(str(repo))})

[Service]
WorkingDirectory={pct(str(repo))}
ExecStart={" ".join(q(a) for a in cmd)}
{env}Restart=on-failure
RestartSec=5
StandardOutput=append:{log}
StandardError=append:{log}

[Install]
WantedBy=default.target
"""


def text(project, extra: list[str]) -> tuple[str, str]:
    """(the service text, how to install it), for this machine's service manager."""
    name, repo, state = project.model.name, project.repo, project.dir
    cmd = command(repo, extra)
    if sys.platform == "darwin":
        path = f"~/Library/LaunchAgents/{label(name)}.plist"
        how = (f"save it as {path}, then: launchctl load -w {path}\n"
               f"(it restarts after a crash or a reboot; ergostat run --stop stops it until the next login; "
               f"for good: launchctl unload -w {path})")
        return launchd(name, repo, cmd, state), how
    unit = f"ergostat-{label(name).removeprefix('local.ergostat.')}.service"
    how = (f"save it as ~/.config/systemd/user/{unit}, then: systemctl --user enable --now {unit}\n"
           f"(a user unit starts at login; to start at boot without one: loginctl enable-linger $USER. "
           f"Stop it for good: systemctl --user disable --now {unit})")
    return systemd(name, repo, cmd, state), how
