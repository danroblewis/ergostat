"""The factory's daemons' side of ergostat's JSON lines (SPEC 9.7, docs/DAEMONS.md): what the four daemons share.

    serve(read=fn)     a sensors' daemon: fn(["ai-spend.main", "repings.main"]) -> {sensor: number}, called once
                       for the readings asked within BATCH of each other (one look at the source for all of them)
    serve(work=fn)     a block's daemon: fn(line) for each run ({"op": "item", ...}), on a thread of its own, with
                       the run's own ERGOSTAT_* values (tf.env) and its lines tagged with its run (tf.say); `done`
                       with what fn returns (None: 0), or 1 when it raises (as a run's exit 1: the attempt counts)

The reader only hands lines on and never waits, so a slow Jira, GitHub or step never keeps it from the next line or a
cancel. A cancel (its lease expired, its timeout, the owner's stop) is answered at once (done 1), and whatever that
run says after it is dropped: its lease is gone (anything it still asks of ergostat is refused, fencing). A thread
cannot be stopped from outside, so a cancelled run still going after CANCEL_GRACE (10 s) is stuck (a hung call, a
lock never let go): the daemon says so and ends, ergostat starts it again, and the stuck thread goes with the process
(the other runs it held fail, and are taken again). A source that fails says why on each reading, and the daemon
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
GRACE = tf.seconds(tf.conf("CANCEL_GRACE", "10s"))   # a cancelled run still going after this: the daemon ends


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
    tf.finish(m["run"], code)                              # (nothing, when it was cancelled: done was said then)


def _cancelled(run: str, t: threading.Thread) -> None:
    t.join(GRACE)
    if t.is_alive():                                       # stuck: only the process's end stops it
        tf.log(f"run {run[:8]} still going {GRACE:g}s after its cancel: ending, to be started again")
        os._exit(1)


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
            tf.begin(m["run"])                             # (under way from now: a cancel that follows finds it)
            runs[m["run"]] = threading.Thread(target=_run, args=(work, m), daemon=True)
            runs[m["run"]].start()
        elif m["op"] == "cancel" and m["run"] in runs and tf.finish(m["run"], 1):   # at once; its lines after: dropped
            threading.Thread(target=_cancelled, args=(m["run"], runs[m["run"]]), daemon=True).start()
        elif m["op"] == "stop":
            break
    if answering:                                          # stop, or the end of its input: what was asked is answered
        asked.put(None)
        answering.join()
    for t in runs.values():
        t.join(timeout=8)                                  # (ergostat's grace is 10 s)
    return 0
