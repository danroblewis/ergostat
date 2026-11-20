"""The steps' outward acts: each a gated action of ergostat's (factory/actions.yaml), asked for by name.

    act("jira-transition", key="SCRUM-5", status="In Progress")      -> what the action printed

ergostat takes it as its gate says and runs it itself (asked over the running engine's socket, else with
`$ERGOSTAT_CMD act NAME --arg K=V`, SPEC 12k): `auto`
at once, `approve` once the owner approves it, `deny` never. The step's own code makes no write. The same
request again (same action, same arguments, same `_key`) is the same action: one that ran is not run again
(its output comes back), one held is still held. So a step that must wait (Pending) gives its ticket back,
and asks again on its next run.

Raises Pending (held for the owner), Denied, or Failed (it ran, and failed).
"""

from __future__ import annotations

import json
import os
import subprocess

from tf import conf, engine, env, ergostat, seconds


class Pending(Exception):
    """Held for the owner's approval."""


class Denied(Exception):
    """Its gate is deny, or the owner denied it."""


class Failed(Exception):
    """It ran, and failed."""


def act(name: str, _key: str | None = None, **args) -> str:
    """Ask for the action `name` with these arguments; its output once it ran. `_key` tells this act from the same
    one asked before with the same arguments (a push of a later commit). (`key=` is an argument: a Jira issue.)"""
    run = {k: v for k in ("ERGOSTAT_ITEM", "ERGOSTAT_LEASE", "ERGOSTAT_RUN", "ERGOSTAT_ACTIONS", "ERGOSTAT_SANDBOX")
           if (v := env(k))}                       # the run's own: in a daemon, from its line (tf.env)
    got = engine("act", name=name, args={k: str(v) for k, v in args.items()}, key=_key,
                 wait=seconds(conf("ACT_WAIT", "10s")), env=run, _timeout=900)
    if got is not None:                                # the running engine answered (its socket)
        a, code = got["action"], int(got["exit"])
    else:
        cmd = [*ergostat(), "act", name, "--json", "--wait", conf("ACT_WAIT", "10s")]
        for k, v in args.items():
            cmd += ["--arg", f"{k}={v}"]
        if _key:
            cmd += ["--key", _key]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=900, env={**os.environ, **run})
        if r.returncode == 2 or not r.stdout.strip():
            raise RuntimeError(f"ergostat act {name}: {(r.stderr or r.stdout).strip()[:400]}")
        a, code = json.loads(r.stdout), r.returncode
    if code == 0:
        return (a.get("output") or "").strip()
    if code == 1:
        raise Failed(f"{name} failed (exit {a.get('exit')}): {(a.get('output') or '').strip()[-300:]}")
    if code == 4:
        raise Denied(f"{name} denied by {a.get('denied_by')}" + (f": {a['note']}" if a.get("note") else ""))
    raise Pending(f"{name} waits for the owner's approval ({a['id']})")


def act_json(name: str, _key: str | None = None, **args):
    return json.loads(act(name, _key, **args))
