"""upgrader. `upgrade.py watch` (a collector): opens an upgrade (upgrade/<sha12>, available) for each new commit on
the remote's pushed main (origin/main, fetched into the checkout), never for a merge not pushed; then records the
reverts pushed to main since its last read as escapes (dev/bin/escapes.py; a failure there stops that step alone).

`upgrade.py` takes an upgrade (upgrade/<sha12>, available) under a lease, installs it into
<live>/<sha> with its own environment (live.py install), checks the model with its own code, and asks for the gated
action `switch-instance` (its id kept on the upgrade, switch_action). Approving it arms the switcher (drain.py): it
waits for a quiet moment or the daily window, drains the runs under way, then runs the switch itself (stop, point
current at it, start, health-check, revert to the previous on failure) in a process of its own (live.py switch
--detach), since it stops the engine that runs it; it records switched, then healthy or reverted.

An upgrade older than the version running, or than a newer one waiting, is superseded: only the newest is installed."""

from __future__ import annotations

import re
import subprocess
import sys
import time

sys.dont_write_bytecode = True
import fac  # noqa: E402
import live  # noqa: E402


def watch() -> int:
    cfg = fac.config()
    if cfg["ai"]["mode"] != "standin":
        import agents
        try:
            gone = agents.sweep(cfg)                    # the factory's containers left past their time
            if gone:
                print(f"swept {', '.join(gone)}", file=sys.stderr)
        except (OSError, RuntimeError) as e:
            print(f"sweep: {e}", file=sys.stderr)
    repo, base, remote = fac.path(cfg, "checkout"), cfg["git"]["base"], cfg["git"]["remote"]
    fac.git(repo, "fetch", "-q", remote, f"+refs/heads/{base}:refs/remotes/{remote}/{base}")
    sha = fac.git(repo, "rev-parse", f"refs/remotes/{remote}/{base}")
    known = {u["fields"].get("sha") for u in fac.items("upgrade")}
    running = live.target(live.live(cfg) / "current")
    if sha not in known and sha != running:
        fac.say("upgrade.opened", f"upgrade/{sha[:12]}", sha=sha, available_at=time.time(), source=f"{remote}/{base}")
    try:                                                # reverts on the pushed main, escapes (dev/bin/escapes.py)
        import escapes
        escapes.watch(cfg, repo, sha)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as e:      # (this step alone stops)
        print(f"escapes: {e}", file=sys.stderr)
    return 0


def main() -> int:
    cfg = fac.config()
    item = fac.read_input()["item"]
    sha = item["fields"]["sha"]
    repo = fac.path(cfg, "checkout")
    running = live.target(live.live(cfg) / "current")
    newer = [u for u in fac.items("upgrade", "available") if u["id"] != item["id"]
             and fac.git_ok(repo, "merge-base", "--is-ancestor", sha, u["fields"].get("sha", ""))]
    if newer or (running and fac.git_ok(repo, "merge-base", "--is-ancestor", sha, running)):
        fac.say("upgrade.superseded", by=newer[0]["id"] if newer else f"running {running[:12]}")
        return 0
    got = live.install(cfg, sha)
    if got["check"] != "ok":
        fac.say("upgrade.failed", **got, failed_at=time.time())
        return 0
    fac.say("upgrade.installed", **got, installed_at=time.time(), previous=running or "")
    try:
        rc, said = fac.act("switch-instance", key=sha, sha=sha)
        m = re.search(r"ergostat\.action/[0-9a-f]+", said)
        fac.say("upgrade.switch-asked", switch={0: "approved", 3: "held", 4: "denied"}.get(rc, f"exit {rc}"),
                switch_said=said[-300:], switch_action=m.group(0) if m else "")
    except FileNotFoundError:
        fac.say("upgrade.switch-asked", switch="not asked: not run by ergostat")
    return 0


if __name__ == "__main__":
    sys.exit(watch() if sys.argv[1:2] == ["watch"] else main())
