"""The factory's daemons' side of ergostat's JSON lines (SPEC 9.7, docs/DAEMONS.md): what the four daemons share.

    serve(read=fn)     a sensors' daemon: fn(["ai-spend.main", "repings.main"]) -> {sensor: number}, called once
                       for the readings asked within BATCH of each other (one look at the source for all of them)
    serve(work=fn)     a block's daemon: fn(line) for each run ({"op": "item", ...}), on a thread of its own, with
                       the run's own ERGOSTAT_* values (tf.env) and its lines tagged with its run (tf.say); `done`
                       with what fn returns (None: 0), or 1 when it raises (as a run's exit 1: the attempt counts)

The reader only hands lines on and never waits, so a slow Jira, GitHub or step never keeps it from the next line or a
cancel. A cancel is answered at once (done 1), and whatever that run says after it is dropped: its lease is gone
(anything it still asks of ergostat is refused, fencing). A source that fails says why on each reading, and the daemon
carries on: it keeps no connection that could be left broken (each call to Jira, GitHub or ergostat is made afresh).
A line it cannot read, or a bug in the daemon itself, ends it, and ergostat starts it again.
"""

from __future__ import annotations

import json
import os
import queue
import sys
import threading
import time
import traceback

import tf

BATCH = 0.05                 # readings asked within 50 ms of each other share one look at the source
BEAT = 10.0                  # a heartbeat this often (the steps' daemon declares heartbeat: 30s)


def fail_hard(args) -> None:
    traceback.print_exception(args.exc_type, args.exc_value, args.exc_traceback)
    os._exit(1)


def _answer(read, asked: queue.Queue) -> None:
    while (first := asked.get()) is not None:
        time.sleep(BATCH)                                  # the rest of this round's readings arrive meanwhile
        batch = [first]
        while not asked.empty():
            batch.append(asked.get())
        stopping = None in batch
        batch = [m for m in batch if m is not None]
        why = ""
        try:
            got = read(sorted({m["sensor"] for m in batch}))
        except Exception as e:                             # noqa: BLE001: each reading says why it has none
            tf.log(traceback.format_exc())
            got, why = {}, f"{type(e).__name__}: {e}"
        for m in batch:
            v = got.get(m["sensor"])
            tf.say({"reading": v, "request": m["request"]} if v is not None else
                   {"error": why or f"no reading for {m['sensor']}", "request": m["request"]})
        if stopping:
            return


def _run(work, m: dict) -> None:
    tf.CURRENT.set({"run": m["run"], "env": m.get("env") or {}})
    try:
        code = work(m) or 0                                # (what it returns: its exit)
    except Exception:                                      # noqa: BLE001: as a run that crashed: exit 1
        tf.log(traceback.format_exc())
        code = 1
    tf.finish(m["run"], code)
    tf.forget(m["run"])                                    # (nothing more of it can come: its id is let go)


def _beat() -> None:
    while True:
        tf.say({"heartbeat": True})
        time.sleep(BEAT)


def serve(read=None, work=None) -> int:
    threading.excepthook = fail_hard
    asked: queue.Queue = queue.Queue()
    answering = threading.Thread(target=_answer, args=(read, asked), daemon=True) if read else None
    if answering:
        answering.start()
    if work:
        threading.Thread(target=_beat, daemon=True).start()
    runs: dict[str, threading.Thread] = {}
    for line in sys.stdin:                                 # the reader: hands each line on, never waits
        m = json.loads(line)                               # a line it cannot read ends it: restarted by ergostat
        if m["op"] == "read" and read:
            asked.put(m)
        elif m["op"] == "item" and work:
            for r in [r for r, t in runs.items() if not t.is_alive()]:
                del runs[r]
            runs[m["run"]] = threading.Thread(target=_run, args=(work, m), daemon=True)
            runs[m["run"]].start()
        elif m["op"] == "cancel" and m["run"] in runs:
            tf.finish(m["run"], 1)                         # at once; what the run says after this is dropped
        elif m["op"] == "stop":
            break
    if answering:                                          # stop, or the end of its input: what was asked is answered
        asked.put(None)
        answering.join()
    for t in runs.values():
        t.join(timeout=8)                                  # (ergostat's grace is 10 s)
    return 0
