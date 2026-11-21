"""switcher. An approved switch drains the runs under way instead of killing them (`drain.py`, a block every minute).

The upgrader asks for the gated action `switch-instance` once a version is installed; approving it (by the
coordinator, or standing: the action's `gate: auto` in the instance's model) only arms the switch. Then, under
run/switch.lock:

- every switch asked for a version older than the newest waiting, or than the one running, is **withdrawn**: its held
  action denied (by the switcher, saying which version supersedes it) and its upgrade `withdrawn`; only the newest waits;
- the newest, once approved, waits for a **quiet moment** (at most `[upgrade] quiet_runs` AI runs under way) or, at the
  latest, the **daily window** (`[upgrade] daily_at`, local) passing after its approval; then it **drains**:
  run/drain.json is written, and each AI run takes no new item while it is there (fac.drain_holds);
- once no AI run is under way, or `[upgrade] drain_minutes` after the drain began, each run still going is given back
  uncounted (its lease nacked with no count: not a failure of its gap), and the switch runs as before (live.py switch,
  in a process of its own: health check, revert), which removes run/drain.json whatever becomes of it. A drain never
  switches in the step that began it.
- a switch it started that recorded no outcome (live.py failed before it stopped the engine: its flag gone and the
  upgrade still draining, or the flag still there 30 minutes on) is recorded `failed`, with an intervention, and never
  begun again.

    drain.py              the step (the block)
    drain.py approve SHA  the action's command: the approval is the record's, read by the next step
    drain.py status       one line: what the newest switch waits for
    drain.py minutes      how long the drain under way has gone (a sensor; 0 when none, or once its switch began)
    drain.py overrun      the minutes it has gone past [upgrade] drain_minutes (a sensor; 0 within it)"""

from __future__ import annotations

import fcntl
import json
import os
import re
import shlex
import subprocess
import sys
import time
from contextlib import contextmanager

sys.dont_write_bytecode = True
import fac  # noqa: E402
import live  # noqa: E402

AI = ("implementor", "reviewer", "planner", "researcher", "pipeline-manager", "groomer")   # the type: ai blocks
KINDS = ("gap", "research", "situation")                                                          # what they take
WAITING = ("installed", "approved", "draining")
STALE = 30 * 60                       # a switch begun this long ago whose process never cleared the flag: given up


def settings(cfg: dict) -> tuple[int, tuple[int, int], float]:
    """(quiet_runs, daily_at as (hour, minute), drain_minutes), each within its bounds or refused."""
    u = cfg.get("upgrade") or {}
    quiet, minutes, at = int(u.get("quiet_runs", 1)), float(u.get("drain_minutes", 45)), str(u.get("daily_at", "04:00"))
    m = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", at)
    if not 0 <= quiet <= 10 or not 1 <= minutes <= 240 or not m:
        raise SystemExit(f"[upgrade] quiet_runs {quiet} (0-10), drain_minutes {minutes:g} (1-240), daily_at {at!r}"
                         " (HH:MM): out of bounds")
    return quiet, (int(m[1]), int(m[2])), minutes


def flag_path(cfg: dict):
    return fac.run_dir(cfg) / "drain.json"


def flag(cfg: dict) -> dict | None:
    """The drain under way; one that cannot be read counts as a drain begun when the file was written."""
    p = flag_path(cfg)
    try:
        return json.loads(p.read_text())
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return {"sha": "", "since": p.stat().st_mtime}


def save(cfg: dict, st: dict) -> None:
    tmp = flag_path(cfg).with_suffix(".new")
    tmp.write_text(json.dumps(st))
    tmp.replace(flag_path(cfg))


@contextmanager
def locked(cfg: dict):
    with (fac.run_dir(cfg) / "switch.lock").open("w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        yield


def under_way() -> list[dict]:
    """The AI runs under way: the items whose lease an AI block holds."""
    return [i for k in KINDS for i in fac.items(k)
            if (i["fields"].get("lease") or {}).get("holder") and i["fields"]["lease"].get("block") in AI]


def window_passed(at: tuple[int, int], since: float, now: float) -> bool:
    """Whether the daily window (local time) came between ``since`` and ``now``."""
    t = time.localtime(now)
    last = time.mktime((t.tm_year, t.tm_mon, t.tm_mday, at[0], at[1], 0, 0, 0, -1))
    if last > now:
        last = time.mktime((t.tm_year, t.tm_mon, t.tm_mday - 1, at[0], at[1], 0, 0, 0, -1))
    return since < last <= now


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


def give_back(runs: list[dict], sha: str) -> list[str]:
    """Each run still going, given back uncounted: its lease nacked with no count, as that run would."""
    out = []
    for i in runs:
        lease = i["fields"]["lease"]
        env = {**os.environ, "ERGOSTAT_ITEM": i["id"], "ERGOSTAT_LEASE": str(lease.get("fence")),
               "ERGOSTAT_RUN": str(lease.get("holder"))}
        r = subprocess.run([*shlex.split(os.environ["ERGOSTAT_CMD"]), "lease", "--nack", "--no-count", "--after", "5m",
                            f"stopped for the switch to {sha[:12]}: given back uncounted"], env=env,
                           capture_output=True, text=True, timeout=60)
        if r.returncode == 0:
            out.append(i["id"])
    return out


def step(cfg: dict, now: float | None = None) -> str:
    now = time.time() if now is None else now
    quiet, at, minutes = settings(cfg)
    repo = fac.path(cfg, "checkout")
    older = lambda a, b: a != b and fac.git_ok(repo, "merge-base", "--is-ancestor", a, b)  # noqa: E731
    with locked(cfg):
        st = flag(cfg)
        if st and st.get("switch_started"):         # (first: nothing is withdrawn while a switch runs)
            if now - float(st["switch_started"]) < STALE:
                return f"switching to {st['sha'][:12]}"
            flag_path(cfg).unlink(missing_ok=True)
            st = None                               # (its upgrade, still draining, is recorded failed below)
        running = live.target(live.live(cfg) / "current") or ""
        waiting = [u for u in fac.items("upgrade") if u["state"] in WAITING]
        for u in [u for u in waiting if st is None and u["state"] == "draining" and u["fields"].get("drained_at")]:
            failed(u, f"the switch to {u['fields']['sha'][:12]} begun at {u['fields']['drained_at']} ended with no "
                      "outcome recorded (live.py switch failed before it stopped the engine?): never begun again", now)
            waiting.remove(u)
        for u in [u for u in waiting if running and older(u["fields"]["sha"], running)]:
            withdraw(u, f"the running {running[:12]}", now)
            waiting.remove(u)
        tops = [u for u in waiting if not any(older(u["fields"]["sha"], v["fields"]["sha"]) for v in waiting)]
        if len(tops) > 1:
            return f"cannot tell the newest of {', '.join(u['id'] for u in tops)}: none switched"
        for u in waiting:
            if tops and u is not tops[0]:
                withdraw(u, tops[0]["id"], now)
        top = tops[0] if tops else None
        if top is not None and top["state"] == "installed" and action_state(top) in ("approved", "ran"):
            fac.say("upgrade.switch-approved", top["id"], approved_at=now)
            top = {**top, "state": "approved", "fields": {**top["fields"], "approved_at": now}}
        if top is None or top["state"] == "installed":
            flag_path(cfg).unlink(missing_ok=True)
            return "no switch approved"
        sha, runs = top["fields"]["sha"], under_way()
        if st is None:
            if len(runs) > quiet and not window_passed(at, float(top["fields"].get("approved_at") or now), now):
                return f"{top['id']} waits for at most {quiet} run(s) under way ({len(runs)} now) or {at[0]:02d}:{at[1]:02d}"
            save(cfg, {"sha": sha, "since": now})
            fac.say("upgrade.draining", top["id"], drain_began_at=now, runs_at_drain=len(runs), drained_at=None)
            return f"{top['id']} drains: {len(runs)} run(s) under way"   # (never switched in the same step: a run
            # whose lease was taken after under_way() read, and that read no flag, is seen by the next step)
        if st.get("sha") != sha:            # a newer version approved while an older one drained: the drain is its
            st = {**st, "sha": sha}
            save(cfg, st)
            fac.say("upgrade.draining", top["id"], drain_began_at=float(st["since"]), runs_at_drain=len(runs),
                    drained_at=None)
        took = (now - float(st["since"])) / 60
        if runs and took < minutes:
            return f"{top['id']} drains: {len(runs)} run(s) under way, {took:.0f} of {minutes:g} minutes"
        given = give_back(runs, sha) if runs else []
        fac.say("upgrade.drained", top["id"], drain_minutes=round(took, 2), given_back=given, drained_at=now)
        save(cfg, {**st, "switch_started": now})
        live.detach(cfg, sha)
        return f"switching to {sha[:12]}" + (f"; given back uncounted: {', '.join(given)}" if given else "")


def gone(st: dict | None, now: float) -> float:
    """How long the drain under way has gone: 0 when none, or once its switch began (the switch's own time is not
    the drain's)."""
    return 0.0 if not st or st.get("switch_started") else (now - float(st["since"])) / 60


def describe(cfg: dict) -> str:
    """For status.py: the newest switch, and what it waits for."""
    ups = [u for u in fac.items("upgrade") if u["state"] in WAITING]
    st = flag(cfg)
    if st:
        return f"Switch to {st['sha'][:12]}: " + (f"switching since {time.ctime(float(st['switch_started']))}"
                                                   if st.get("switch_started") else
                                                   f"draining for {gone(st, time.time()):.0f} of "
                                                   f"{settings(cfg)[2]:g} minutes, {len(under_way())} run(s) under way")
    return "Switch: " + (", ".join(f"{u['id']} {u['state']}" for u in ups) or "none waiting")


def main(argv: list[str]) -> int:
    cfg = fac.config()
    if argv[:1] == ["approve"]:
        if len(argv) != 2 or not re.fullmatch(r"[0-9a-f]{40}", argv[1]):
            raise SystemExit("drain.py approve SHA (a full commit id)")
        print(f"the switch to {argv[1][:12]} is approved: it drains the runs under way at a quiet moment "
              f"or the daily window, then switches")
        return 0
    if argv[:1] in (["minutes"], ["overrun"]):
        print(round(max(0.0, gone(flag(cfg), time.time()) - (settings(cfg)[2] if argv[0] == "overrun" else 0)), 1))
        return 0
    if argv[:1] == ["status"]:
        fac.cli(cfg)
        print(describe(cfg))
        return 0
    print(step(cfg), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
