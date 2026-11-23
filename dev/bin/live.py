"""The running instance and its versions (dev/README.md). The instance never runs from the checkout the queue merges
into and resets: each version is its own worktree, detached at its commit, with its own environment.

    <live>/<sha>/        a version: a detached worktree of the checkout, its .venv made by `uv sync --frozen`
    <live>/current       -> the version running;   <live>/previous -> the one before it (what a revert goes back to)
    <live>/instance/     the instance's own folder, the same across versions (so its record is: ergostat keys a
                         record by the model's folder, where its files really are): copies of the current version's
                         ergostat.yaml and dev/ (made at each switch; what was edited in them since is kept as a
                         patch in run/model-edits/ first), run/ (briefs, logs, the cost ledger), factory.local.toml,
                         ergostat.local.yaml (the instance's web:, this machine's: never placed, compared or a gap)

    live.py install REF       make the version (worktree, environment) and check the model with its own code
    live.py init [SHA]        make the instance's folder, on SHA (after the first install)
    live.py start | stop      start or stop the engine of the current version, on [instance] port
    live.py switch SHA        stop, point current at SHA, start, check its health; back to the previous on failure
    live.py switch SHA --detach   the same in a process of its own (the switcher's, dev/bin/drain.py, once the runs
                              under way drained: the engine that runs it is the one it stops); a switch ends the
                              drain (run/drain.json) whatever becomes of it
    live.py revert            switch to the previous version
    live.py health            the running engine's health: a pass, the sensors reading, the record read, the queue
    live.py status            which version runs, which is previous, and the versions installed

Every switch is recorded on the upgrade's item (upgrade/<sha12>): switched, then healthy or reverted."""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
import fac  # noqa: E402

HEALTH_WAIT = 300            # seconds a new version has to show it is healthy
STOP_WAIT = 120              # seconds a stopping engine has to close before a start is tried
PASS_FRESH = 30              # a pass at most this old
DISPATCH_FAILING = 120       # seconds the dispatcher may meet an error in every look before it is a situation
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
    r = run(["uv", "sync", "--frozen", "--quiet"], cwd=d, timeout=600)
    if r.returncode:
        raise RuntimeError(f"uv sync in {d}: {r.stderr[-400:]}")
    home = live(cfg) / ".check" / sha                  # check with a record of its own, outside the version
    r = run([ergostat_of(cfg, sha), "-C", d, "check"], env={**os.environ, "ERGOSTAT_HOME": str(home)}, timeout=300)
    errors = re.search(r"(\d+) errors?", r.stdout)
    ok = r.returncode == 0 or (errors is not None and errors.group(1) == "0")
    return {"sha": sha, "dir": str(d), "check": "ok" if ok else "failed", "check_said": r.stdout[-600:]}


def edits(cfg: dict, was: str | None) -> Path | None:
    """What was changed in the instance's copy of the model since it was placed (an accepted change to the model, an
    edit by hand), kept as a patch in run/model-edits/ before a switch replaces it: bring it to the repository as a gap.
    Only ergostat.yaml and dev/ are compared: the instance's ergostat.local.yaml (this machine's web:, never in the
    repository) is neither placed nor compared, so a switch keeps it and never makes a gap of it."""
    inst, lv = instance(cfg), live(cfg)
    if not was or not (inst / "ergostat.yaml").is_file():
        return None
    out = []

    def files(root: Path) -> set[str]:
        return {str(p.relative_to(root)) for p in (root / "dev").rglob("*") if p.is_file()
                and "__pycache__" not in p.parts} if (root / "dev").is_dir() else set()
    for rel in ["ergostat.yaml", *sorted(files(lv / was) | files(inst))]:
        a, b = lv / was / rel, inst / rel
        old = a.read_text().splitlines(True) if a.is_file() else []
        new = b.read_text().splitlines(True) if b.is_file() else []
        if old != new and b.is_file():
            out += difflib.unified_diff(old, new, f"a/{rel}" if a.is_file() else "/dev/null", f"b/{rel}")
    if not out:
        return None
    d = fac.run_dir(cfg, "model-edits")
    p = d / f"{time.strftime('%Y%m%d-%H%M%S')}-{was[:12]}.patch"
    p.write_text("".join(out))
    return p


def place_model(cfg: dict, was: str | None = None) -> Path | None:
    """The current version's ergostat.yaml and dev/, copied into the instance's folder: copies, not links, since
    ergostat takes a model's folder (and keys its record) by where its files really are. The instance's model as it
    was is kept beside them (dev.prev, ergostat.yaml.prev) until the new one is healthy (``forget_previous``), so a
    revert puts back exactly what ran (``restore_previous``). What was edited in the copy since ``was`` was placed is
    kept as a patch first (``edits``); the patch is returned."""
    inst, cur = instance(cfg), live(cfg) / "current"
    kept = edits(cfg, was)
    for p in ("dev.new", "dev.prev"):
        shutil.rmtree(inst / p, ignore_errors=True)
    shutil.copytree(cur / "dev", inst / "dev.new", ignore=shutil.ignore_patterns("__pycache__"))
    if (inst / "dev").is_symlink() or (inst / "dev").is_file():
        (inst / "dev").unlink()
    elif (inst / "dev").exists():
        (inst / "dev").rename(inst / "dev.prev")
    (inst / "dev.new").rename(inst / "dev")
    if (inst / "ergostat.yaml").is_file():
        shutil.copy2(inst / "ergostat.yaml", inst / "ergostat.yaml.prev")
    tmp = inst / "ergostat.yaml.new"
    tmp.write_bytes((cur / "ergostat.yaml").read_bytes())
    tmp.replace(inst / "ergostat.yaml")
    return kept


def restore_previous(cfg: dict) -> bool:
    """The instance's model as it was before the last placing, back in place; False when none was kept."""
    inst = instance(cfg)
    if not (inst / "dev.prev").is_dir() or not (inst / "ergostat.yaml.prev").is_file():
        return False
    shutil.rmtree(inst / "dev", ignore_errors=True)
    (inst / "dev.prev").rename(inst / "dev")
    (inst / "ergostat.yaml.prev").replace(inst / "ergostat.yaml")
    return True


def forget_previous(cfg: dict) -> None:
    inst = instance(cfg)
    shutil.rmtree(inst / "dev.prev", ignore_errors=True)
    (inst / "ergostat.yaml.prev").unlink(missing_ok=True)


def init(cfg: dict, sha: str | None = None) -> Path:
    """The instance's folder, on ``sha`` (else the current version)."""
    inst = instance(cfg)
    (inst / "run").mkdir(parents=True, exist_ok=True)
    if sha:
        point(live(cfg) / "current", fac.git(fac.path(cfg, "checkout"), "rev-parse", "--verify", f"{sha}^{{commit}}"))
    place_model(cfg)
    return inst


def engine(cfg: dict, sha: str, *args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return run([ergostat_of(cfg, sha), "-C", instance(cfg), *args], timeout=timeout)


def start(cfg: dict) -> str:
    sha = target(live(cfg) / "current")
    r = engine(cfg, sha, "run", "--no-web")          # the page is its own process (dev/bin/ui.py): it outlives this
    if r.returncode:
        raise RuntimeError(f"start {sha[:12]}: {(r.stderr or r.stdout)[-400:]}")
    if cfg["ai"]["mode"] != "standin":               # (a test's stand-in factory starts no page of its own)
        run([sys.executable, str(Path(__file__).with_name("ui.py")), "ensure"], timeout=30, cwd=instance(cfg))
    return sha


def stop(cfg: dict) -> None:
    """Stop the engine and wait until it has gone. `run --stop` gives up after 10 s while a busy engine is still closing,
    and a start in that time sees it running, starts nothing, and leaves no engine once it exits."""
    sha = target(live(cfg) / "current")
    if not sha:
        return
    deadline = time.monotonic() + STOP_WAIT
    while engine(cfg, sha, "run", "--stop").returncode and time.monotonic() < deadline:
        time.sleep(1)


def state_dir(cfg: dict) -> Path:
    inst = instance(cfg)
    name = re.search(r"^name:\s*(\S+)", (inst / "ergostat.yaml").read_text(), re.M).group(1)
    home = Path(os.environ.get("ERGOSTAT_HOME") or Path.home() / ".ergostat")
    return home / f"{name}-{hashlib.sha256(str(inst.resolve()).encode()).hexdigest()[:8]}"


def dispatch_failing(beat: dict, now: float) -> str | None:
    """The dispatcher's error, when every look has met one for more than DISPATCH_FAILING seconds (the heartbeat's
    ``dispatch_error``): what it says and for how long; a ``since`` that is not a time (missing, NaN) is never fresh."""
    err = beat.get("dispatch_error")
    if not isinstance(err, dict):
        return None
    try:
        age = now - float(err.get("since"))
    except (TypeError, ValueError):
        age = float("inf")
    return None if age <= DISPATCH_FAILING else f"the dispatcher has failed every look for {age / 60:.0f} min: {err.get('why')}"


def heartbeat(cfg: dict) -> dict:
    return json.loads((state_dir(cfg) / "heartbeat.json").read_text())


def health(cfg: dict, since: float = 0.0) -> dict:
    """What the running engine shows: a pass within PASS_FRESH seconds (its heartbeat), and no dispatcher error standing
    past DISPATCH_FAILING, the interlock's and the intake's sensors read since ``since``, the record read back (the
    gaps), and the merge queue in the model."""
    sha = target(live(cfg) / "current")
    out: dict = {"sha": sha}
    try:
        beat = heartbeat(cfg)
        out["pass_age_s"] = round(time.time() - float(beat["pass"]), 1)
        out["engine"] = out["pass_age_s"] <= PASS_FRESH and float(beat["pass"]) >= since
        out["dispatch_said"] = dispatch_failing(beat, time.time())
        out["dispatch"] = out["dispatch_said"] is None
    except (OSError, ValueError, KeyError) as e:
        out["engine"], out["dispatch"], out["engine_said"] = False, False, str(e)
    got = engine(cfg, sha, "sensor", SENSOR, "--json")
    readings = json.loads(got.stdout).get("now", {}).get("readings", []) if got.returncode == 0 else []
    out["sensors"] = any(float(r["at"]) >= since for r in readings)
    got = engine(cfg, sha, "item", "--kind", "gap", "--json", "-n", "1")
    out["record"] = got.returncode == 0 and "items" in json.loads(got.stdout or "{}")
    got = engine(cfg, sha, "block", "merge-queue", "--json")
    out["queue"] = got.returncode == 0
    out["healthy"] = all(out[k] for k in ("engine", "dispatch", "sensors", "record", "queue"))
    return out


def record(cfg: dict, sha: str, event: str, **data) -> None:
    engine(cfg, sha, "event", "--add", event, "--item", f"upgrade/{sha[:12]}", "--data", json.dumps(data),
           "--as", "upgrader")


def edits_as_gap(cfg: dict, sha: str, patch: Path) -> None:
    """A change made to the model inside the instance (one the owner accepted) becomes a gap through the factory's own
    pipeline: its definition, with the patch, in run/defs/, and gap.requested."""
    name = f"model-edit-{hashlib.sha256(patch.read_bytes()).hexdigest()[:10]}"      # the same edits, the same gap
    got = engine(cfg, sha, "item", f"gap/{name}", "--json")
    try:
        if got.returncode == 0 and json.loads(got.stdout).get("id") == f"gap/{name}":
            return
    except ValueError:
        pass
    (fac.run_dir(cfg, "defs") / f"{name}.md").write_text(
        f"# {name}: bring the model changes accepted in the instance into the repository\n\n## Definition of done\n\n"
        f"The changes below, made to the instance's copy of the model while it ran {sha[:12]}, are in the repository's"
        f" model files, `ergostat check` is clean, and tests/test_factory.py passes.\n\n```diff\n"
        f"{patch.read_text()}\n```\n\n## Size budget\n\n0 net lines of core code (the model and dev/ only).\n")
    engine(cfg, sha, "event", "--add", "gap.requested", "--item", f"gap/{name}", "--data",
           json.dumps({"title": f"Model changes accepted in the instance ({name})", "source": "request",
                       "branch": name, "definition": f"run/defs/{name}.md"}), "--as", "upgrader")


def intervene(cfg: dict, sha: str, why: str) -> None:
    """Ask the coordinator: the instance could not be brought back by itself."""
    engine(cfg, sha, "event", "--add", "intervention.recorded", "--item",
           f"intervention/switch-{time.strftime('%Y%m%d-%H%M%S')}", "--data",
           json.dumps({"reason": why, "class": "switch", "recorded_at": time.time()}), "--as", "upgrader")


def switch(cfg: dict, sha: str) -> dict:
    """Stop, point current at ``sha``, start, and wait for it to be healthy; on any failure after the stop (a model
    that does not place, an engine that does not start, a health check that does not pass or raises), back to the
    version before, with the instance's model as it was, recorded. A revert whose own start fails is tried once more,
    then recorded as failed with an intervention, and raised."""
    lv = live(cfg)
    if not ergostat_of(cfg, sha).exists():
        raise SystemExit(f"{sha[:12]} is not installed: live.py install {sha}")
    was, before = target(lv / "current"), target(lv / "previous")
    began = time.time()
    wait = float((cfg.get("instance") or {}).get("health_wait", HEALTH_WAIT))
    stop(cfg)
    h: dict = {"healthy": False}
    kept = None
    try:
        if was and was != sha:
            point(lv / "previous", was)
        point(lv / "current", sha)
        kept = place_model(cfg, was)
        start(cfg)
        record(cfg, sha, "upgrade.switched", switched_at=began, previous=was or "", switch="ran",
               model_edits=str(kept or ""))
        deadline = time.time() + wait
        while time.time() < deadline:
            time.sleep(min(5.0, wait))
            h = health(cfg, since=began)
            if h["healthy"]:
                record(cfg, sha, "upgrade.kept", health=h, healthy_at=time.time())
                forget_previous(cfg)
                if kept and (cfg.get("instance") or {}).get("edits_as_gaps", True):   # (false: an operator's live-only
                    edits_as_gap(cfg, sha, kept)                                     # edits stay in run/model-edits/)
                return h
        h["why"] = f"not healthy within {wait:g}s"
    except Exception as e:  # noqa: BLE001 - whatever failed, the instance goes back to what ran
        h = {"healthy": False, "why": f"{type(e).__name__}: {str(e)[:300]}"}
    try:
        stop(cfg)
    except Exception:  # noqa: BLE001
        pass
    if not was or was == sha:
        return h                                         # nothing to go back to: left stopped, said by the caller
    point(lv / "current", was)
    if before:
        point(lv / "previous", before)                  # previous is what it was: the failed one is never gone back to
    if not restore_previous(cfg):
        place_model(cfg, sha)
    for attempt in (1, 2):
        try:
            start(cfg)
            break
        except Exception as e:  # noqa: BLE001
            if attempt == 2:
                why = f"the switch to {sha[:12]} failed ({h.get('why')}), and its revert to {was[:12]} did not start: {e}"
                engine(cfg, was, "event", "--add", "upgrade.failed", "--item", f"upgrade/{sha[:12]}", "--data",
                       json.dumps({"health": h, "why": why, "failed_at": time.time()}), "--as", "upgrader")
                intervene(cfg, was, why)
                raise RuntimeError(why) from e
            time.sleep(5)
    engine(cfg, was, "event", "--add", "upgrade.reverted", "--item", f"upgrade/{sha[:12]}", "--data",
           json.dumps({"health": h, "reverted_to": was, "reverted_at": time.time()}), "--as", "upgrader")
    if kept:
        edits_as_gap(cfg, was, kept)                    # the instance's edits never lost, whatever became of the switch
    return h


def detach(cfg: dict, sha: str) -> Path:
    """The switch in a process of its own (it stops the engine that started it); its log."""
    log = fac.run_dir(cfg, "logs") / f"switch-{sha[:12]}.log"
    subprocess.Popen([sys.executable, __file__, "switch", sha], stdout=log.open("a"), stderr=subprocess.STDOUT,
                     stdin=subprocess.DEVNULL, start_new_session=True, cwd=instance(cfg))
    return log


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
        print(f"switching to {argv[1][:12]} in the background; its log: {detach(cfg, argv[1])}")
    elif what == "switch":
        try:
            h = switch(cfg, argv[1])
        finally:                                        # the drain that waited for it ends, whatever became of it
            (fac.run_dir(cfg) / "drain.json").unlink(missing_ok=True)
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
