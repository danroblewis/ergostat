"""Checking a warm daemon's promise (SPEC §9.7, *Warm*): that the program keeps no state between runs. One input is run
twice on one fresh process and once on each of two other fresh processes, and what each run printed (its lines, its
run's id put back as RUN, and its exit) compared. It runs the program for real, four times, as a daemon process is
started but without what the engine prepares for a run (no workspace or workdir, no action policy; only
``ERGOSTAT_RUN`` and ``ERGOSTAT_ITEM`` in its env). Nothing is concluded unless every run ended with its own done."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
import uuid

from .proc import SHARED


def _start(d, cwd, env: dict) -> tuple[subprocess.Popen, queue.Queue]:
    env = {k: v for k, v in env.items() if not k.startswith("ERGOSTAT_") or k in SHARED}
    p = subprocess.Popen(d.run, shell=True, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         text=True, start_new_session=True)
    q: queue.Queue = queue.Queue()
    threading.Thread(target=lambda: [q.put(x) for x in p.stdout] + [q.put(None)], daemon=True).start()
    return p, q


def _run(p, q, given: dict, timeout: float) -> list:
    """One run handed over: what it printed for it, its id as RUN, until its ``done``."""
    run = uuid.uuid4().hex
    item = (given.get("item") or {}).get("id")
    try:
        p.stdin.write(json.dumps({"op": "item", "run": run, "item": item, "lease": given.get("lease"), "input": given,
                                  "env": {"ERGOSTAT_RUN": run, **({"ERGOSTAT_ITEM": item} if item else {})}}) + "\n")
        p.stdin.flush()
    except (BrokenPipeError, OSError, ValueError):
        return ["(the process ended before it was handed the run)"]
    got, end = [], time.monotonic() + timeout
    while (left := end - time.monotonic()) > 0:
        try:
            raw = q.get(timeout=left)
        except queue.Empty:
            break
        if raw is None:
            return got + ["(the process ended)"]
        try:
            obj = json.loads(raw.replace(run, "RUN"))
        except ValueError:
            obj = raw.strip()
        if obj != {"heartbeat": True}:
            got.append(obj)
        if _done(obj) is not None:
            return got
    return got + [f"(no done within {timeout:g}s)"]


def _done(obj) -> int | None:
    """Its exit, from a line that is exactly its run's done; None from any other."""
    if isinstance(obj, dict) and set(obj) == {"done", "run"} and obj["run"] == "RUN" and type(obj["done"]) is int:
        return obj["done"]
    return None


def check(d, cwd, env: dict, given: dict, timeout: float = 60.0) -> tuple[int, str]:
    """0 and why when the promise holds for this input; 1 when state leaked; 2 when nothing can be concluded."""
    outs, procs = [], []
    try:
        for n in (2, 1, 1):                          # one process given it twice, then two given it once
            p, q = _start(d, cwd, env)
            procs.append(p)
            outs += [_run(p, q, given, timeout) for _ in range(n)]
    finally:
        for p in procs:
            for end in (p.stdin.close, lambda p=p: os.killpg(p.pid, 9)):
                try:                                 # (its standard input gone with it: a broken pipe, said above)
                    end()
                except OSError:
                    pass
            p.wait()
    first, second, fresh, fresh2 = outs
    exits = [_done(o[-1]) if o else None for o in outs]
    said = "exits: " + ", ".join(f"{w} {'no done' if x is None else x}" for w, x in
                                 zip(("one process, 1st", "2nd", "fresh", "fresh"), exits, strict=True)) + "\n"
    if None in exits:
        bad = next(o for o, x in zip(outs, exits, strict=True) if x is None)
        return 2, said + f"nothing concluded: a run did not end with its own done ({bad[-1] if bad else 'it printed nothing'})"
    if not first == fresh == fresh2:
        return 2, said + f"not deterministic for this input: three fresh processes printed different lines ({fresh} / {fresh2})"
    if second != fresh:
        return 1, said + f"state kept between runs: its second run on one process printed {second}, a fresh one {fresh}"
    return 0, said + "the same on one process twice as on fresh processes: no state kept, for this input"
