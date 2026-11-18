"""Gated actions asked for by a program block's run (SPEC §12k): ``$ERGOSTAT_CMD act NAME --arg K=V``.

A ``program`` (or ``ai``) block that names ``actions:`` is given, in its run's environment, ``ERGOSTAT_ACTIONS``: the
file of what the run was given (its block, run, item, lease, folder, branch, and the actions it may ask for). Its
command asks for an action by name, with its arguments, and is answered when the gate has taken it:

- ``auto``: approved by the gate, and **run by ergostat's engine** (not in the asking process, so not with its
  environment), the call waiting for its result;
- ``approve``: held for the owner, the call waiting up to ``--wait`` (default: not at all) for the answer;
- ``deny``: denied.

The same request again (the same action, arguments and ``--key``, about the same item) is the same action: one held is
answered as it stands, and taken over by the asking run's lease (``ergostat.action.reasked``), so a step that gives
its item back while it waits, and is taken again, finds its action and its result when the owner has answered; one
that ran is never run again, its result given back; one the owner denied stays denied. One that failed is asked for
anew. Every result given to the run that asked is ``delivered`` (``how: run``)."""

from __future__ import annotations

import hashlib
import json
import os
import time

from . import gate as gt
from . import record as rec

ENV = "ERGOSTAT_ACTIONS"
EXIT = {"ran": 0, "failed": 1, "requested": 3, "approved": 3, "denied": 4}
MARGIN = 30.0                    # seconds past an action's timeout that a call waits for ergostat's engine to run it


class AskError(ValueError):
    """The run cannot ask for that action: no run, or not one of its block's actions:, or its arguments are wrong."""


def given(env: dict | None = None) -> dict:
    """What the run was given (``ERGOSTAT_ACTIONS``), checked against the run it says it is."""
    env = os.environ if env is None else env
    f = env.get(ENV) or env.get("ERGOSTAT_SANDBOX")
    if not f:
        raise AskError("this is not a run of a block with actions: (no $ERGOSTAT_ACTIONS): name the actions it may ask "
                       "for under its actions:")
    try:
        cfg = json.loads(open(f, encoding="utf-8").read())
    except (OSError, ValueError) as e:
        raise AskError(f"$ERGOSTAT_ACTIONS: {e}") from None
    if env.get("ERGOSTAT_RUN") and cfg.get("run") != env["ERGOSTAT_RUN"]:
        raise AskError(f"$ERGOSTAT_ACTIONS is run {str(cfg.get('run'))[:8]}'s, not this run's")
    return cfg


def key_of(name: str, args: dict, key: str | None = None) -> str:
    """What makes two requests the same act: the action, its arguments, and the caller's key."""
    return hashlib.sha1(json.dumps([name, sorted(args.items()), key or ""]).encode()).hexdigest()[:12]


def known(p, spec, cfg: dict, name: str, k: str, scoped: bool) -> dict | None:
    """The same act asked for before, when it still stands: held, approved, ran, or denied by the owner (or by a gate
    that is deny still). None for one that failed, or was denied by a gate since changed, or by fencing."""
    item = cfg.get("item")
    if not item and not scoped:                       # no item, no --key: every run's request is its own
        return None
    same = [a for a in rec.stored(p).values()
            if a.get("action") == name and a.get("key") == k
            and (a.get("item") == item if item else a.get("block") == cfg.get("block"))]
    if not same:
        return None
    a = max(same, key=lambda a: a["time"])
    if a["state"] in ("requested", "approved", "ran"):
        return a
    if a["state"] == "denied":
        note = str(a.get("note") or "")
        if a.get("denied_by") != rec.GATE:
            return a
        act = spec.actions.get(name)
        if act is not None and act.gate == "deny" and not note.startswith("fenced"):
            return a
    return None


def reask(p, a: dict, cfg: dict) -> dict:
    """A held action asked for again by a later run of the same work: taken over by its lease (its fencing number)."""
    fence = cfg.get("lease")
    if fence is None or fence == (a.get("fence") or a.get("lease")) and cfg.get("run") == a.get("run"):
        return a
    rec.step(p, a["id"], "reasked", {"fence": fence, "run": cfg.get("run")}, by=cfg.get("block") or "program",
             causedby=cfg.get("run"))
    return rec.get(p, a["id"])


def ask(p, spec, cfg: dict, name: str, args: dict, key: str | None = None, wait: float = 0.0) -> dict:
    """A run asks for an action; returns it as it stands when the call returns (ran, failed, denied, or still held)."""
    if name not in (cfg.get("actions") or []):
        raise AskError(f"no action {name!r} for block {cfg.get('block')}: its actions: are "
                       f"{', '.join(cfg.get('actions') or []) or 'none'}")
    act = spec.actions.get(name)
    if act is None:
        raise AskError(f"no action {name!r} in the model")
    extra = sorted(set(args) - set(act.args))
    if extra:
        raise AskError(f"{name} takes no {', '.join(extra)} (its args: {', '.join(act.args) or 'none'})")
    args = {k: str(v) for k, v in args.items()}
    k = key_of(name, args, key)
    a = known(p, spec, cfg, name, k, key is not None)
    if a is not None and a["state"] in ("requested", "approved"):
        a = reask(p, a, cfg)
        why = gt.fenced(p, spec, a)
        if why and a["state"] == "requested":         # a run whose own lease is over asks again: refused, as new
            a = None
    if a is None:
        ctx = {x: cfg.get(x) for x in ("block", "run", "item", "workdir", "branch", "lease")}
        try:
            a = gt.request(p, spec, name, args, ctx, asker="program", key=k)
        except gt.GateError as e:
            raise AskError(str(e)) from None
    a = settle(p, spec, cfg, a, wait)
    if a["state"] in ("ran", "failed", "denied") and not any(d.get("run") == cfg.get("run")
                                                             for d in a.get("deliveries") or []):
        gt.delivered(p, a["id"], "run", run=cfg.get("run"), block=cfg.get("block"))
        a = rec.get(p, a["id"])
    return a


def settle(p, spec, cfg: dict, a: dict, wait: float) -> dict:
    """Wait for the action's answer: up to ``wait`` for the owner's, and, once approved, for its run (by ergostat's
    engine; by this process when no engine follows the record: a run started outside ``ergostat run``)."""
    act = spec.actions.get(a.get("action") or "")
    end = time.monotonic() + max(0.0, wait)
    ran_by = None
    while True:
        if a["state"] == "approved":
            if cfg.get("runner") != "ergostat":
                a = gt.run_once(p, spec, a["id"]) or rec.get(p, a["id"])
            elif ran_by is None:
                ran_by = time.monotonic() + (act.timeout if act else 120.0) + MARGIN
        if a["state"] in ("ran", "failed", "denied"):
            return a
        now = time.monotonic()
        if a["state"] == "requested" and now >= end:
            return a
        if a["state"] == "approved" and ran_by is not None and now >= ran_by:
            return a
        time.sleep(gt.POLL / 2)
        a = rec.get(p, a["id"])


def exit_code(a: dict) -> int:
    return EXIT.get(a["state"], 2)
