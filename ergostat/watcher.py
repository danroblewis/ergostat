"""The outer watcher (SPEC §9.1), which ``ergostat run --service --install`` has the service manager keep running:
``python -m ergostat.watcher -C REPO [--port N] [--no-web]``. It reads only ``run.pid`` (locked while the engine
lives), ``heartbeat.json`` (its last pass) and ``stopped``. An engine dead, unless stopped on purpose (``ergostat run
--stop`` leaves ``<state>/stopped``; a logout or a shutdown does not), is started again; one whose last pass is older
than ``STALE`` (frozen whole, past what its own watchdog mends), or than the heartbeat's own ``stale`` when it is 60
to 3600 s (``use: upkeep``'s goal ``heartbeat-fresh``: it moves the limit, never turns it off), is stopped and started
again; each in its turn in
``restarts.py``'s back-off, said on ``run.log`` and recorded as ``ergostat.engine.restarted`` when it started.
Prototyped as ``upkeep watch`` (branch ``upkeep``, with 60687a9's fixes)."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

from . import restarts

EVERY = 5.0
STALE = 180.0               # (past the startup deadline, which restarts a hung start itself)


def _say(d: Path, line: str) -> None:
    try:
        with open(d / "run.log", "a") as f:
            f.write(f"{time.strftime('%H:%M:%S')} watcher: {line}\n")
    except OSError:
        pass


def _events(d: Path):
    from .storage import Storage, open_events
    return open_events(Storage(), d)


STOPPED = "stopped"          # written by ``ergostat run --stop``, removed by the next start: a stop on purpose


def stopped(d: Path) -> bool:
    """Stopped on purpose (``ergostat run --stop``), not by a logout, a shutdown or a crash."""
    return (d / STOPPED).exists()


def beat(d: Path, name: str = "heartbeat.json") -> dict | None:
    try:
        got = json.loads((d / name).read_text())
        return got if isinstance(got, dict) else None
    except (OSError, ValueError):
        return None


def beats(d: Path) -> list[dict]:
    """``heartbeat.json`` and each shard engine's ``heartbeat.SHARD.json`` (SPEC §9.8), those that can be read."""
    try:
        listed = os.listdir(d)
    except OSError:                                    # (then heartbeat.json is unreadable too: no beat, as today)
        listed = []
    names = ["heartbeat.json", *sorted(n for n in listed if n.startswith("heartbeat.") and n.endswith(".json")
                                       and n != "heartbeat.json")]
    return [hb for hb in map(lambda n: beat(d, n), names) if hb]


_SAID: set[str] = set()      # the bad ``stale`` values said in run.log, each once a watcher process


def limit(d: Path, hb: dict | None) -> float:
    """How old a last pass may be: the heartbeat's ``stale`` (``use: upkeep``'s ``heartbeat-fresh``) when it is a
    number of seconds within 60 to 3600, else ``STALE``. A missing one is a model without the template, said nowhere;
    a malformed or out-of-range one is said in ``run.log``, once for each value."""
    from .spec.ir import STALE_RANGE, stale_ok
    if not hb or "stale" not in hb:
        return STALE
    got = hb["stale"]
    if stale_ok(got):
        return float(got)
    if repr(got) not in _SAID:
        _SAID.add(repr(got))
        _say(d, f"heartbeat.json's stale {got!r} is not {STALE_RANGE[0]} to {STALE_RANGE[1]} seconds: {STALE:g} used")
    return STALE


def look(repo: Path, d: Path, extra: list[str], now: float | None = None) -> dict | None:
    """One look: what was done (``{"what": "dead"|"stale", ...}``), or None."""
    from .runner import running_pid
    now = time.time() if now is None else now
    pid = running_pid(SimpleNamespace(dir=d), wait=False)
    did = None
    if not pid:
        if not stopped(d):
            did = {"what": "dead"}
    else:                                              # (a beat left by another pid: not this engine's)
        for hb in beats(d):
            if hb.get("pid") == pid and now - float(hb.get("pass") or now) > limit(d, hb):
                did = {"what": "stale", "pid": pid, "seconds": round(now - float(hb["pass"]), 1)}
                break
    if did is None:
        return None
    left, n = restarts.wait(d, now)
    if left > 0:
        return {**did, "waiting": round(left)}
    if did["what"] == "stale":
        os.kill(pid, signal.SIGTERM)
        for _ in range(100):
            if not running_pid(SimpleNamespace(dir=d), wait=False):
                break
            time.sleep(0.1)
        else:
            os.kill(pid, signal.SIGKILL)               # (frozen whole: only this reaches it)
    began = time.time()
    path = os.pathsep.join([str(Path(sys.executable).parent), os.environ.get("PATH", "")])
    try:
        got = subprocess.run([sys.executable, "-m", "ergostat", "-C", str(repo), "run", *extra], capture_output=True,
                             timeout=60, env={**os.environ, "PATH": path}, stdin=subprocess.DEVNULL)
        why = None if got.returncode == 0 else (got.stderr or got.stdout or b"").decode(errors="replace").strip()[-300:]
    except subprocess.TimeoutExpired:
        why = "it did not start within 60s"
    did["restart"] = restarts.note(d, f"the engine {did['what']}", "watcher")     # (a refusal backs off too)
    if why is not None:
        _say(d, f"the engine was {did['what']}; starting it again failed: {why or 'no reason given'}")
        return {**did, "failed": why}
    did["restarted_in"] = round(time.time() - began, 1)
    _say(d, f"the engine was {did['what']}: started again ({json.dumps(did)})")
    try:
        _events(d).add("ergostat.engine.restarted", source="ergostat", data=did)
    except Exception as e:
        _say(d, f"recording the restart: {type(e).__name__}: {e}")
    return did


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ergostat.watcher")
    ap.add_argument("-C", dest="repo", required=True)
    ap.add_argument("--port", type=int)
    ap.add_argument("--no-web", action="store_true")
    a = ap.parse_args(argv)
    repo = Path(a.repo).resolve()
    extra = [*(["--no-web"] if a.no_web else []), *(["--port", str(a.port)] if a.port else [])]
    from . import model as mdl
    from .projects import state_of
    waited = None
    while True:
        main_file = mdl.find(repo)
        d = state_of(main_file) if main_file else None
        if d is not None:
            try:
                did = look(repo, d, extra)
                if did and did.get("waiting") and not (waited and waited.get("waiting")):
                    _say(d, f"the engine is {did['what']}; a restart did not help, the next in {did['waiting']}s")
                waited = did
            except Exception as e:                      # the watcher itself never stops
                _say(d, f"{type(e).__name__}: {e}")
        time.sleep(EVERY)


if __name__ == "__main__":
    sys.exit(main())
