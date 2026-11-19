#!/usr/bin/env python3
"""worker.py: a block's daemon. Each job handed to it is worked on a thread of its own, many at once: its work runs
in a process of its own, with the job's own ERGOSTAT_* values, and leaves a file in done/. A cancel stops that job's
process and says done for it."""
import json
import os
import signal
import subprocess
import sys
import threading
import time
import traceback

WORK = 'sleep "$JOB_SECONDS" && date > "done/${ERGOSTAT_ITEM#job/}"'   # one job's work, in a shell of its own
out, jobs = threading.Lock(), threading.Lock()
running: dict[str, subprocess.Popen] = {}       # run id: its job's process
cancelled: set[str] = set()


def say(**line):                                 # one whole line at a time, from any thread
    with out:
        print(json.dumps(line), flush=True)


def fail_hard(args):                             # an error on any thread ends the daemon: ergostat restarts it
    traceback.print_exception(args.exc_type, args.exc_value, args.exc_traceback)
    os._exit(1)


def beat():
    while True:
        say(heartbeat=True)
        time.sleep(10)


def work(m):
    run = m["run"]
    seconds = m["input"]["item"]["fields"].get("seconds", 1)
    env = {**os.environ, **m["env"], "JOB_SECONDS": str(seconds)}     # this job's values, for its process only
    with jobs:
        if run in cancelled:                     # cancelled before it started
            return say(done=1, run=run)
        p = subprocess.Popen(["sh", "-c", WORK], env=env, stdout=sys.stderr, start_new_session=True)
        running[run] = p
    code = p.wait()
    with jobs:
        running.pop(run, None)
    if code == 0:
        say(event="job.done", run=run, data={"seconds": seconds})
    say(done=0 if code == 0 else 1, run=run)     # exactly these two keys; a whole number


def cancel(run):
    with jobs:
        cancelled.add(run)
        p = running.get(run)
        if p is not None:
            os.killpg(p.pid, signal.SIGTERM)     # its work() sees it end and says done


threading.excepthook = fail_hard
os.makedirs("done", exist_ok=True)
threading.Thread(target=beat, daemon=True).start()
for line in sys.stdin:                           # the reader: it only hands lines on, never waits on the work
    m = json.loads(line)                         # a line it cannot read raises: the daemon ends, and is restarted
    if m["op"] == "item":
        threading.Thread(target=work, args=(m,)).start()
    elif m["op"] == "cancel":
        cancel(m["run"])
    elif m["op"] == "stop":
        break
# (stop, or the end of its input: the jobs under way finish before it exits)
