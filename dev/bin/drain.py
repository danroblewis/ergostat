"""switcher. An approved switch starts at once and leaves the runs under way alone (`drain.py`, a block every minute).

The upgrader asks for the gated action `switch-instance` once a version is installed; approving it (by the
coordinator, or standing: the action's `gate: auto` in the instance's model) only arms the switch. Then, under
run/switch.lock:

- every switch asked for a version older than the newest waiting, or than the one running, is **withdrawn**: its held
  action denied (by the switcher, saying which version supersedes it) and its upgrade `withdrawn`; only the newest waits;
- the newest, once approved, **switches** in the same step: run/switch.json is written, `upgrade.switch-begun` said,
  and the switch runs in a process of its own (live.py switch: stop, swap, start, health check, revert), which removes
  run/switch.json whatever becomes of it. Nothing waits for the runs under way and none is stopped or given back: with
  `runs: outlive_engine` they carry on under the version they started with, and the new engine takes them up from
  their journals (SPEC section 9.1, *Runs taken up again*);
- a switch it started that recorded no outcome (live.py failed before it stopped the engine: its flag gone and the
  upgrade still approved with its switch begun, or the flag still there 30 minutes on) is recorded `failed`, with an
  intervention, and never begun again. (An upgrade left `draining` by the switcher before this one, which drained, is
  read the same way, and so is its flag: run/drain.json marked `switch_started` is a switch under way, the first one
  onto this version, run by that switcher's live.py, which removes it once the switch ends.)

    drain.py              the step (the block)
    drain.py approve SHA  the action's command: the approval is the record's, read by the next step
    drain.py status       one line: what the newest switch waits for"""

from __future__ import annotations

import fcntl
import json
import re
import sys
import time
from contextlib import contextmanager

sys.dont_write_bytecode = True
import fac  # noqa: E402
import live  # noqa: E402

WAITING = ("installed", "approved", "draining")     # (draining: an upgrade the draining switcher before this one left)
STALE = 30 * 60                       # a switch begun this long ago whose process never cleared the flag: given up


def flag_path(cfg: dict):
    return fac.run_dir(cfg) / "switch.json"


def old_flag_path(cfg: dict):
    """The draining switcher's flag (the version before this one): its live.py marks the switch it runs there
    (``switch_started``) and removes it once the switch ends, so the first switch onto this version is under way
    while it is there."""
    return fac.run_dir(cfg) / "drain.json"


def flags(cfg: dict) -> list[dict]:
    """The switches under way, this switcher's and the draining one's (a drain.json only draining is none: nothing
    reads it now); one that cannot be read counts as begun when the file was written."""
    out = []
    for p in (flag_path(cfg), old_flag_path(cfg)):
        st = read_flag(p)
        if st is not None and (p == flag_path(cfg) or st.get("switch_started")):
            out.append({**st, "path": p})
    return out


def flag(cfg: dict) -> dict | None:
    return (flags(cfg) or [None])[0]


def read_flag(p) -> dict | None:
    try:
        st = json.loads(p.read_text())
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return {"sha": "", "switch_started": p.stat().st_mtime}
    return st if isinstance(st, dict) else {"sha": "", "switch_started": p.stat().st_mtime}


def save(cfg: dict, st: dict) -> None:
    tmp = flag_path(cfg).with_suffix(".new")
    tmp.write_text(json.dumps(st))
    tmp.replace(flag_path(cfg))


@contextmanager
def locked(cfg: dict):
    with (fac.run_dir(cfg) / "switch.lock").open("w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        yield


def action_state(u: dict) -> str:
    aid = str(u["fields"].get("switch_action") or "")
    if not aid:
        return "unknown"
    got = fac.ergostat("item", aid, "--json", check=False)
    try:
        return json.loads(got.stdout).get("state") or "unknown" if got.returncode == 0 else "unknown"
    except ValueError:
        return "unknown"


def withdraw(u: dict, by: str, now: float) -> None:
    aid = str(u["fields"].get("switch_action") or "")
    if aid and action_state(u) in ("held", "requested"):
        fac.ergostat("actions", aid, "--deny", "--as", "switcher", "--note", f"withdrawn: superseded by {by}",
                     check=False)          # (approved meanwhile: it ran, and arms nothing withdrawn)
    fac.say("upgrade.withdrawn", u["id"], superseded_by=by, withdrawn_at=now)


def failed(u: dict, why: str, now: float) -> None:
    """A switch the switcher started that recorded no outcome: failed, and asked of the coordinator."""
    fac.say("upgrade.failed", u["id"], why=why, failed_at=now)
    fac.say("intervention.recorded", f"intervention/switch-{u['id'].rsplit('/', 1)[-1]}-{int(now)}", reason=why,
            recorded_at=now, **{"class": "switch"})


def begun(u: dict):
    """When its switch began (this switcher's ``switch_begun_at``, or the draining one's ``drained_at``), or None."""
    return u["fields"].get("switch_begun_at") or u["fields"].get("drained_at")


def step(cfg: dict, now: float | None = None) -> str:
    now = time.time() if now is None else now
    repo = fac.path(cfg, "checkout")
    older = lambda a, b: a != b and fac.git_ok(repo, "merge-base", "--is-ancestor", a, b)  # noqa: E731
    with locked(cfg):
        for st in flags(cfg):                       # (first: nothing is withdrawn while a switch runs)
            try:
                fresh = now - float(st["switch_started"]) < STALE
            except (KeyError, TypeError, ValueError):
                fresh = False                       # (a start that is not a time: never fresh, given up)
            if fresh:
                return f"switching to {str(st.get('sha'))[:12]}"
        for st in flags(cfg):
            st["path"].unlink(missing_ok=True)      # (its upgrade, still approved or draining, is recorded failed below)
        running = live.target(live.live(cfg) / "current") or ""
        waiting = [u for u in fac.items("upgrade") if u["state"] in WAITING]
        for u in [u for u in waiting if u["state"] != "installed" and begun(u)]:
            failed(u, f"the switch to {u['fields']['sha'][:12]} begun at {begun(u)} ended with no "
                      "outcome recorded (live.py switch failed before it stopped the engine?): never begun again", now)
            waiting.remove(u)
        for u in [u for u in waiting if running and older(u["fields"]["sha"], running)]:
            withdraw(u, f"the running {running[:12]}", now)
            waiting.remove(u)
        tops = [u for u in waiting if not any(older(u["fields"]["sha"], v["fields"]["sha"]) for v in waiting)]
        if len(tops) > 1:
            return f"cannot tell the newest of {', '.join(u['id'] for u in tops)}: none switched"
        top = tops[0] if tops else None
        for u in waiting:
            if u is not top:
                withdraw(u, top["id"], now)
        if top is None:
            return "no switch waiting"
        if top["state"] == "installed":
            if action_state(top) not in ("approved", "ran"):
                return f"{top['id']} waits for its switch to be approved"
            fac.say("upgrade.switch-approved", top["id"], approved_at=now, switch_begun_at=None,   # (an earlier
                    drained_at=None)                    # switch of the same version, installed again: not this one's)
        sha = top["fields"]["sha"]
        save(cfg, {"sha": sha, "switch_started": now})
        fac.say("upgrade.switch-begun", top["id"], switch_begun_at=now)
        live.detach(cfg, sha)
        return f"switching to {sha[:12]}: the runs under way carry on, taken up by its engine"


def describe(cfg: dict) -> str:
    """For status.py: the switch under way, or the newest waiting and its state."""
    st = flag(cfg)
    if st and isinstance(st.get("switch_started"), int | float):
        return f"Switch to {str(st.get('sha'))[:12]}: switching since {time.ctime(float(st['switch_started']))}"
    ups = [u for u in fac.items("upgrade") if u["state"] in WAITING]
    return "Switch: " + (", ".join(f"{u['id']} {u['state']}" for u in ups) or "none waiting")


def main(argv: list[str]) -> int:
    cfg = fac.config()
    if argv[:1] == ["approve"]:
        if len(argv) != 2 or not re.fullmatch(r"[0-9a-f]{40}", argv[1]):
            raise SystemExit("drain.py approve SHA (a full commit id)")
        print(f"the switch to {argv[1][:12]} is approved: the switcher starts it within a minute; the runs under way "
              "carry on, and the new version's engine takes them up")
        return 0
    if argv[:1] == ["status"]:
        fac.cli(cfg)
        print(describe(cfg))
        return 0
    print(step(cfg), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
