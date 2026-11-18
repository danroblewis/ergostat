"""The gate (SPEC §12k): a session's request for an action, taken as the action's gate says, and run only after it is
let through.

- ``request``: recorded (``requested``); ``deny``: denied at once; ``auto``: approved by the gate and run at once;
  ``approve``: held for the owner.
- ``approve`` / ``deny``: the owner's answer (the page, ``ergostat actions ID --approve``). An approved action runs once
  (``run_once``, which takes a lock file, so a waiting session, the owner's act and the engine's sweep never run it
  twice): by the session's server while it waits for it (``wait``), else at once by whoever approved it.
- The result goes back to the session that asked (the tool call's answer, while it waits), else to the block's next
  run (``for_context``: under ``actions`` in its input), and is recorded as ``delivered`` either way."""

from __future__ import annotations

import os
import shlex
import string
import subprocess
import time
from pathlib import Path

from ..spec.ir import Action
from . import record as rec
from .record import GATE

OUTPUT_MAX = 4000
POLL = 0.5


class GateError(ValueError):
    """An answer that cannot be given: no such action, or it was answered already."""


def render(a: Action, args: dict, ctx: dict) -> str:
    """The command, its template filled: the session's arguments and ergostat's own values, each shell-quoted."""
    vals = {k: shlex.quote(str(ctx.get(k) or "")) for k in ("item", "branch", "workdir", "block", "run")}
    vals.update({k: shlex.quote(str(v)) for k, v in args.items() if k in a.args})
    return string.Formatter().vformat(a.run, (), vals)


def folder(p) -> Path:
    d = p.dir / "actions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def request(p, spec, name: str, args: dict, ctx: dict) -> dict:
    """A session asks for an action. ``ctx``: its ``block``, ``run``, ``session``, ``item``, ``workdir``, ``branch``.
    Returns the action as recorded after its gate took it."""
    a = spec.actions.get(name)
    if a is None:
        raise GateError(f"no action {name!r}")
    missing = [k for k in a.args if not str(args.get(k) or "").strip()]
    if missing:
        raise GateError(f"{name} needs {', '.join(missing)}")
    args = {k: str(args[k]) for k in a.args}
    where = str(Path(ctx["workdir"]) if not a.in_ else (spec.root / a.in_).resolve()) if (a.in_ or ctx.get("workdir")) \
        else str(spec.root)
    aid = rec.new_id(name)
    data = {"action": name, "class": a.cls or name, "gate": a.gate, "args": args, "command": render(a, args, ctx),
            "in": where, **{k: ctx.get(k) for k in ("block", "run", "session", "item", "workdir", "branch")},
            "description": a.description}
    rec.step(p, aid, "requested", data, by=ctx.get("block") or "session", causedby=ctx.get("run"))
    if a.gate == "deny":
        rec.step(p, aid, "denied", {"denied_by": GATE, "note": "its gate is deny: never run"})
    elif a.gate == "auto":
        rec.step(p, aid, "approved", {"approved_by": GATE, "note": "its gate is auto: run at once"})
        run_once(p, spec, aid)
    return rec.get(p, aid)


def approve(p, spec, aid: str, by: str = "owner", note: str | None = None) -> dict:
    a = _open(p, aid)
    rec.step(p, a["id"], "approved", {"approved_by": by, **({"note": note} if note else {})}, by=by)
    if not waiting(p, a["id"]):                       # no session waits for it: it runs now, here
        run_once(p, spec, a["id"])
    return rec.get(p, a["id"])


def deny(p, aid: str, by: str = "owner", note: str | None = None) -> dict:
    a = _open(p, aid)
    rec.step(p, a["id"], "denied", {"denied_by": by, **({"note": note} if note else {})}, by=by)
    return rec.get(p, a["id"])


def _open(p, aid: str) -> dict:
    a = rec.get(p, aid)
    if a is None:
        raise GateError(f"no action {aid!r}")
    if a["state"] != "requested":
        raise GateError(f"{a['id']} is {a['state']} already: only a held action is approved or denied")
    return a


def run_once(p, spec, aid: str) -> dict | None:
    """An approved action, run: once only, whoever asks first. Returns it as recorded after, or None when it was not
    this caller's to run (not approved, or run or running elsewhere)."""
    a = rec.get(p, aid)
    if a is None or a["state"] != "approved":
        return None
    lock = folder(p) / f"{rec.short(a['id'])}.run"
    try:
        os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except FileExistsError:
        return None
    act = spec.actions.get(a.get("action") or "")
    timeout = act.timeout if act else 120.0
    env = {**os.environ, "ERGOSTAT_ACTION": a["id"], "ERGOSTAT_ITEM": a.get("item") or "",
           "ERGOSTAT_BRANCH": a.get("branch") or ""}
    started = time.time()
    try:
        r = subprocess.run(a["command"], shell=True, cwd=a.get("in") or str(spec.root), capture_output=True, text=True,
                           timeout=timeout, env=env, start_new_session=True)
        code, out = r.returncode, (r.stdout + (("\n" if r.stdout and r.stderr else "") + r.stderr if r.stderr else ""))
    except subprocess.TimeoutExpired as e:
        code, out = None, f"stopped after its timeout of {timeout:g}s\n{e.stdout or ''}"
    except OSError as e:
        code, out = None, f"could not start: {e}"
    out = out.strip()
    if len(out) > OUTPUT_MAX:
        out = "...\n" + out[-OUTPUT_MAX:]
    rec.step(p, a["id"], "ran" if code == 0 else "failed",
             {"exit": code, "output": out, "seconds": round(time.time() - started, 2)})
    return rec.get(p, a["id"])


# ---- a session waiting for its answer

def _marker(p, aid: str) -> Path:
    return folder(p) / f"{rec.short(aid)}.waiting"


def waiting(p, aid: str) -> bool:
    """Whether a session's server waits for this action now (its marker names a live process)."""
    f = _marker(p, aid)
    try:
        pid = int(f.read_text().strip())
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def wait(p, spec, aid: str, seconds: float, stop=None) -> dict:
    """Wait for the owner's answer to a held action, up to ``seconds``: run it when approved. Returns it as recorded
    when it was answered (and ran), or as it stands when the wait ran out."""
    f = _marker(p, aid)
    f.write_text(str(os.getpid()))
    try:
        end = time.monotonic() + seconds
        while True:
            a = rec.get(p, aid)
            if a["state"] == "approved":
                a = run_once(p, spec, aid) or rec.get(p, aid)
            if a["state"] in ("ran", "failed", "denied"):
                return a
            if time.monotonic() >= end or (stop is not None and stop()):
                return a
            time.sleep(POLL)
    finally:
        f.unlink(missing_ok=True)


def delivered(p, aid: str, how: str, **to) -> dict:
    return rec.step(p, aid, "delivered", {"deliveries": {"how": how, "at": time.time(), **{k: v for k, v in to.items() if v}}})


def result(a: dict) -> dict:
    """What a session, or a run, is given of an action."""
    out = {"id": a["id"], "action": a.get("action"), "args": a.get("args"), "state": a["state"]}
    if a["state"] in ("ran", "failed"):
        out.update({"exit": a.get("exit"), "output": a.get("output")})
    if a["state"] == "denied":
        out["denied_by"] = a.get("denied_by")
        if a.get("note"):
            out["note"] = a["note"]
    if a["state"] in ("requested", "approved"):
        out["note"] = "held for the owner's approval: it has not run" if a["state"] == "requested" else "approved, running"
    return out


def for_context(p, block: str, run: str | None) -> list[dict]:
    """The block's actions a session asked for and never got the answer to (it had ended): the answered ones are
    delivered to this run; those still held are said, not delivered."""
    out = []
    for a in rec.stored(p).values():
        if a.get("block") != block:
            continue
        if a["state"] in ("requested", "approved"):
            out.append(result(a))
        elif a["state"] in ("ran", "failed", "denied") and not a.get("deliveries"):
            out.append(result(a))
            delivered(p, a["id"], "context", run=run, block=block)
    return out


def sweep(p, spec) -> int:
    """Approved actions no one ran (the approver could not, and no session waits): run now. Returns how many."""
    n = 0
    for a in rec.stored(p, since=time.time() - rec.WEEK).values():
        if a["state"] == "approved" and not waiting(p, a["id"]) and run_once(p, spec, a["id"]):
            n += 1
    return n
