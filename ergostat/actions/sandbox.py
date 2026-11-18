"""Where an AI block's session works, and what it may do there (SPEC §12k).

The engine writes, for each run of an ``ai`` block that says where it works or what it may use (``workdir:``,
``workspace:``, ``read:``, ``tools:``, ``actions:``), a file of what its session is given (``write``), named by
``$ERGOSTAT_SANDBOX``; ``claude -p`` started by the engine, or by ``ergostat session``, takes it (``flags``):

- the session starts in its folder (the workspace, or ``workdir:``), and may read ``read:`` too (``--add-dir``);
- with ``tools:`` or ``actions:``, it is **gated**: started ``--restricted`` (no user, project or local settings: only
  these), with only the built-in tools ``tools:`` names (``--tools``), allowed as written (``--allowedTools``, in
  ``dontAsk`` mode: anything else is refused, never asked), the commands that act outward refused by name
  (``--disallowedTools``: ``DENY``), no MCP server but ergostat's (``--strict-mcp-config``), which serves its
  ``actions:`` as tools, and Claude Code's OS sandbox on for every command it runs (``--settings``: writes only in its
  folder and what git needs to commit there, no network, no way around it, and no start without it)."""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

DENY = ["Bash(git push:*)", "Bash(git send-email:*)", "Bash(git remote:*)", "Bash(git config:*)", "Bash(gh:*)",
        "Bash(hub:*)", "Bash(glab:*)", "Bash(curl:*)", "Bash(wget:*)", "Bash(http:*)", "Bash(ssh:*)", "Bash(scp:*)",
        "Bash(sftp:*)", "Bash(rsync:*)", "Bash(nc:*)", "Bash(ncat:*)", "Bash(telnet:*)", "Bash(ftp:*)",
        "Bash(npm publish:*)", "Bash(twine:*)", "Bash(docker push:*)", "Bash(kubectl:*)", "Bash(jira:*)",
        "Bash(slack:*)", "Bash(open:*)", "Bash(osascript:*)", "WebFetch", "WebSearch"]
SERVER = "actions"                 # its MCP server's name: the session's tools are mcp__actions__NAME
MARGIN = 60.0                      # seconds added to the longest wait and run, for the tool call's own time limit


def gated(cfg: dict) -> bool:
    return cfg.get("tools") is not None or bool(cfg.get("actions"))


def write(p, block: str, run: str, cfg: dict) -> Path:
    d = p.dir / "sandbox"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{block}-{run[:8]}.json"
    f.write_text(json.dumps(cfg, indent=1))
    return f


def load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text())


def mcp_config(cfg: dict, session: str | None = None) -> dict:
    env = {"ERGOSTAT_SANDBOX": cfg["file"], **({"ERGOSTAT_SESSION": session} if session else {})}
    return {"mcpServers": {SERVER: {"type": "stdio", "command": sys.executable, "args": ["-m", "ergostat.actions.server"],
                                    "env": env}}}


def settings(cfg: dict) -> dict:
    read = cfg.get("read") or []
    return {"sandbox": {"enabled": True, "failIfUnavailable": True, "allowUnsandboxedCommands": False,
                        "network": {"allowedDomains": [], "strictAllowlist": True},
                        "filesystem": {"allowWrite": list(cfg.get("writes") or []), "denyWrite": list(read)}},
            "permissions": {"deny": [f"{t}(/{r}/**)" for r in read for t in ("Edit", "Write")]}}


def flags(cfg: dict, session: str | None = None) -> list[str]:
    """The arguments ``claude -p`` takes for this session, after its own."""
    out: list[str] = []
    for r in cfg.get("read") or []:
        out += ["--add-dir", r]
    if not gated(cfg):
        return out
    tools = list(cfg.get("tools") or [])
    builtin = sorted({t.split("(", 1)[0] for t in tools})
    allowed = [*tools, *([f"mcp__{SERVER}"] if cfg.get("actions") else [])]
    out += ["--restricted", "--tools", ",".join(builtin), "--permission-mode", "dontAsk", "--strict-mcp-config",
            "--settings", json.dumps(settings(cfg))]
    if cfg.get("actions"):
        out += ["--mcp-config", json.dumps(mcp_config(cfg, session))]
    if allowed:
        out += ["--allowedTools", ",".join(allowed)]
    out += ["--disallowedTools", ",".join(DENY)]
    return out


def env(cfg: dict) -> dict:
    """What the session's environment adds: a tool call to an action may wait for the owner this long."""
    if not cfg.get("actions"):
        return {}
    most = max([float(x) for x in cfg.get("waits") or [0]] or [0])
    return {"MCP_TOOL_TIMEOUT": str(int((most + MARGIN) * 1000))}


def command_line(cfg: dict) -> str:
    return " ".join(shlex.quote(x) for x in flags(cfg))
