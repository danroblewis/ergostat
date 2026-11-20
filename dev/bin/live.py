"""The running instance and its versions (dev/README.md). The instance never runs from the checkout the queue merges
into and resets: each version is its own worktree, detached at its commit, with its own environment.

    <live>/<sha>/        a version: a detached worktree of the checkout, its .venv made by `uv sync --frozen`
    <live>/current       -> the version running;   <live>/previous -> the one before it (what a revert goes back to)
    <live>/instance/     the instance's own folder, the same across versions (so its record is: ergostat keys a
                         record by the model's folder, where its main file really is): a copy of the current version's
                         ergostat.yaml, dev -> ../current/dev, run/ (briefs, logs, the cost ledger),
                         factory.local.toml (local settings)

    live.py install REF       make the version (worktree, environment) and check the model with its own code
    live.py init [SHA]        make the instance's folder, on SHA (after the first install)
    live.py start | stop      start or stop the engine of the current version, on [instance] port
    live.py switch SHA        stop, point current at SHA, start, check its health; back to the previous on failure
    live.py switch SHA --detach   the same in a process of its own (the gated action switch-instance: the engine
                              that runs the action is the one it stops)
    live.py revert            switch to the previous version
    live.py health            the running engine's health: a pass, the sensors reading, the record read, the queue
    live.py status            which version runs, which is previous, and the versions installed

Every switch is recorded on the upgrade's item (upgrade/<sha12>): switched, then healthy or reverted."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
import fac  # noqa: E402

HEALTH_WAIT = 120            # seconds a new version has to show it is healthy
PASS_FRESH = 30              # a pass at most this old
SENSOR = "suites-running.main"     # the load interlock's, read every 15 s


def live(cfg: dict) -> Path:
    p = fac.path(cfg, "live")
    p.mkdir(parents=True, exist_ok=True)
    return p


def target(link: Path) -> str | None:
    return os.readlink(link) if link.is_symlink() else None


def point(link: Path, to: str) -> None:
    tmp = link.with_name(link.name + ".new")
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    tmp.symlink_to(to)
    tmp.replace(link)                                   # atomic


def ergostat_of(cfg: dict, sha: str) -> Path:
    return live(cfg) / sha / ".venv" / "bin" / "ergostat"


def instance(cfg: dict) -> Path:
    return live(cfg) / "instance"


def run(cmd: list, timeout: int = 900, **kw) -> subprocess.CompletedProcess:
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True, timeout=timeout, **kw)


def install(cfg: dict, ref: str) -> dict:
    repo = fac.path(cfg, "checkout")
    sha = fac.git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}")
    d = live(cfg) / sha
    if not (d / ".git").exists():
        fac.git(repo, "worktree", "add", "-q", "--detach", str(d), sha)
    r = run(["uv", "sync", "--frozen", "--quiet"], cwd=d)
    if r.returncode:
        raise RuntimeError(f"uv sync in {d}: {r.stderr[-400:]}")
    home = live(cfg) / ".check" / sha                  # check with a record of its own, outside the version
    r = run([ergostat_of(cfg, sha), "-C", d, "check"], env={**os.environ, "ERGOSTAT_HOME": str(home)}, timeout=600)
    errors = re.search(r"(\d+) errors?", r.stdout)
    ok = r.returncode == 0 or (errors is not None and errors.group(1) == "0")
    return {"sha": sha, "dir": str(d), "check": "ok" if ok else "failed", "check_said": r.stdout[-600:]}


def place_model(cfg: dict) -> None:
    """The current version's ergostat.yaml, copied into the instance's folder: a copy, not a link, since ergostat
    takes a model's folder (and keys its record) by where its main file really is."""
    inst = instance(cfg)
    tmp = inst / "ergostat.yaml.new"
    tmp.write_bytes((live(cfg) / "current" / "ergostat.yaml").read_bytes())
    tmp.replace(inst / "ergostat.yaml")


def init(cfg: dict, sha: str | None = None) -> Path:
    """The instance's folder, on ``sha`` (else the current version)."""
    inst = instance(cfg)
    (inst / "run").mkdir(parents=True, exist_ok=True)
    if sha:
        point(live(cfg) / "current", fac.git(fac.path(cfg, "checkout"), "rev-parse", "--verify", f"{sha}^{{commit}}"))
    if not (inst / "dev").is_symlink():
        (inst / "dev").symlink_to("../current/dev")
    place_model(cfg)
    return inst


def engine(cfg: dict, sha: str, *args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return run([ergostat_of(cfg, sha), "-C", instance(cfg), *args], timeout=timeout)


def start(cfg: dict) -> str:
    sha = target(live(cfg) / "current")
    r = engine(cfg, sha, "run", "--port", str(cfg["instance"]["port"]))
    if r.returncode:
        raise RuntimeError(f"start {sha[:12]}: {(r.stderr or r.stdout)[-400:]}")
    return sha


def stop(cfg: dict) -> None:
    sha = target(live(cfg) / "current")
    if sha:
        engine(cfg, sha, "run", "--stop")


def state_dir(cfg: dict) -> Path:
    inst = instance(cfg)
    name = re.search(r"^name:\s*(\S+)", (inst / "ergostat.yaml").read_text(), re.M).group(1)
    home = Path(os.environ.get("ERGOSTAT_HOME") or Path.home() / ".ergostat")
    return home / f"{name}-{hashlib.sha256(str(inst.resolve()).encode()).hexdigest()[:8]}"


def health(cfg: dict, since: float = 0.0) -> dict:
    """What the running engine shows: a pass within PASS_FRESH seconds (its heartbeat), the interlock's and the intake's
    sensors read since ``since``, the record read back (the gaps), and the merge queue in the model."""
    sha = target(live(cfg) / "current")
    out: dict = {"sha": sha}
    try:
        beat = json.loads((state_dir(cfg) / "heartbeat.json").read_text())
        out["pass_age_s"] = round(time.time() - float(beat["pass"]), 1)
        out["engine"] = out["pass_age_s"] <= PASS_FRESH and float(beat["pass"]) >= since
    except (OSError, ValueError, KeyError) as e:
        out["engine"], out["engine_said"] = False, str(e)
    got = engine(cfg, sha, "sensor", SENSOR, "--json")
    readings = json.loads(got.stdout).get("now", {}).get("readings", []) if got.returncode == 0 else []
    out["sensors"] = any(float(r["at"]) >= since for r in readings)
    got = engine(cfg, sha, "item", "--kind", "gap", "--json", "-n", "1")
    out["record"] = got.returncode == 0 and "items" in json.loads(got.stdout or "{}")
    got = engine(cfg, sha, "block", "merge-queue", "--json")
    out["queue"] = got.returncode == 0
    out["healthy"] = all(out[k] for k in ("engine", "sensors", "record", "queue"))
    return out


def record(cfg: dict, sha: str, event: str, **data) -> None:
    engine(cfg, sha, "event", "--add", event, "--item", f"upgrade/{sha[:12]}", "--data", json.dumps(data),
           "--as", "upgrader")


def switch(cfg: dict, sha: str) -> dict:
    lv = live(cfg)
    if not ergostat_of(cfg, sha).exists():
        raise SystemExit(f"{sha[:12]} is not installed: live.py install {sha}")
    was = target(lv / "current")
    began = time.time()
    stop(cfg)
    if was and was != sha:
        point(lv / "previous", was)
    point(lv / "current", sha)
    place_model(cfg)
    start(cfg)
    record(cfg, sha, "upgrade.switched", switched_at=began, previous=was or "")
    deadline, h = time.time() + HEALTH_WAIT, {}
    while time.time() < deadline:
        time.sleep(5)
        h = health(cfg, since=began)
        if h["healthy"]:
            record(cfg, sha, "upgrade.kept", health=h, healthy_at=time.time())
            return h
    stop(cfg)
    if not was or was == sha:
        return h                                         # nothing to go back to: left stopped, said by the caller
    point(lv / "current", was)
    place_model(cfg)
    start(cfg)
    engine(cfg, was, "event", "--add", "upgrade.reverted", "--item", f"upgrade/{sha[:12]}", "--data",
           json.dumps({"health": h, "reverted_to": was, "reverted_at": time.time()}), "--as", "upgrader")
    return h


def main(argv: list[str]) -> int:
    cfg = fac.config()
    what = argv[0] if argv else "status"
    if what == "install":
        print(json.dumps(install(cfg, argv[1])))
    elif what == "init":
        print(init(cfg, argv[1] if len(argv) > 1 else None))
    elif what == "start":
        print(start(cfg))
    elif what == "stop":
        stop(cfg)
    elif what == "switch" and "--detach" in argv:
        log = fac.run_dir(cfg, "logs") / f"switch-{argv[1][:12]}.log"
        subprocess.Popen([sys.executable, __file__, "switch", argv[1]], stdout=log.open("a"), stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, start_new_session=True, cwd=instance(cfg))
        print(f"switching to {argv[1][:12]} in the background; its log: {log}")
    elif what == "switch":
        h = switch(cfg, argv[1])
        print(json.dumps(h))
        return 0 if h.get("healthy") else 1
    elif what == "revert":
        prev = target(live(cfg) / "previous")
        if not prev:
            raise SystemExit("no previous version to revert to")
        return main(["switch", prev])
    elif what == "health":
        h = health(cfg)
        print(json.dumps(h))
        return 0 if h["healthy"] else 1
    elif what == "status":
        lv = live(cfg)
        print(json.dumps({"current": target(lv / "current"), "previous": target(lv / "previous"),
                          "installed": sorted(p.name for p in lv.iterdir() if re.fullmatch(r"[0-9a-f]{40}", p.name))}))
    else:
        raise SystemExit(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
