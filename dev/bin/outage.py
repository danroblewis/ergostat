"""An outage: a run failed because Docker or the AI service could not be reached, a cause outside its item. Such a
run is given back uncounted and put off for AFTER (fac.guarded, queue.py take()): it spends none of the item's
attempts, takes no kill-rule count and parks nothing, and the item is taken again in its block's order once AFTER has
passed, as many times as the outage lasts (one look each AFTER: a bounded rate, no AI money spent while Docker is down).

- **Docker**: the failure's words name Docker (a container that did not start, `docker ...: ...`, exit 125), and
  `docker info` then fails or does not answer within PROBE seconds. With no `docker` installed it is no outage (this
  factory does not use Docker), and a Docker that answers is none either: the failure is the run's own.
- **The AI service**: the session's words are a connection error (no route, refused, a name that does not resolve, a
  request timed out), never an API's answer (a 4xx or 5xx is the service reached)."""

from __future__ import annotations

import os
import re
import subprocess

AFTER = "10m"
PROBE = 30
NAMES_DOCKER = re.compile(r"docker|container|\bexit 125\b", re.I)
AI_DOWN = re.compile(r"API Error: (?:Connection error|Request timed out)|Unable to connect to (?:the )?API|"
                     r"ECONNREFUSED|ENOTFOUND|EAI_AGAIN|ETIMEDOUT|getaddrinfo|fetch failed", re.I)


def docker_down() -> str | None:
    """Why Docker cannot be reached now (``docker info`` failed, or did not answer), or None."""
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "DOCKER_HOST", "DOCKER_CONFIG", "DOCKER_CONTEXT",
                                                       "TMPDIR")}
    try:
        r = subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"], capture_output=True, text=True,
                           timeout=PROBE, env=env)
    except FileNotFoundError:
        return None                                    # (no Docker here: none of this factory's runs use it)
    except (OSError, subprocess.SubprocessError) as e:
        return f"`docker info` did not answer ({type(e).__name__})"
    if r.returncode:
        return f"`docker info` failed (exit {r.returncode}): {(r.stderr or r.stdout).strip()[-200:]}"
    return None


def of(e: BaseException) -> str | None:
    """Why the failure ``e`` is an outage, or None (the run's own failure)."""
    text = f"{type(e).__name__}: {e}"
    if AI_DOWN.search(text):
        return f"the AI service is unreachable: {text[-200:]}"
    if NAMES_DOCKER.search(text) and (down := docker_down()):
        return f"Docker is unreachable: {down}"
    return None
