"""upgrader: takes an upgrade the merge queue opened (upgrade/<sha12>, available) under a lease, installs it into
<live>/<sha> with its own environment (live.py install), checks the model with its own code, and asks for the gated
action `switch-instance`. The switch itself (stop, point current at it, start, health-check, revert to the previous
on failure) runs in a process of its own once the coordinator approves it (live.py switch --detach), since it stops
the engine that runs it; it records switched, then healthy or reverted.

An upgrade older than the version running, or than a newer one waiting, is superseded: only the newest is installed."""

from __future__ import annotations

import sys
import time

sys.dont_write_bytecode = True
import fac  # noqa: E402
import live  # noqa: E402


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
        fac.say("upgrade.switch-asked", switch={0: "started", 3: "held", 4: "denied"}.get(rc, f"exit {rc}"),
                switch_said=said[-300:])
    except FileNotFoundError:
        fac.say("upgrade.switch-asked", switch="not asked: not run by ergostat")
    return 0


if __name__ == "__main__":
    sys.exit(main())
