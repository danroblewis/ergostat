"""The worker pool: runs as many workers as it is commanded (command.amount), each doing two jobs
in two seconds. Their logs fill the disk."""
import json
import sys
import time

from sim import say, world

workers = round(json.load(sys.stdin)["command"]["amount"])
time.sleep(2.0)                               # the workers take a while
with world() as w:
    done = min(w["waiting"], workers * 2)
    w["waiting"] -= done
    w["used"] += done * 0.1                   # each job writes a little log
say(out="flow.jobs-done", moved=done, note=f"{workers} workers")
say(out="flow.logs-written", moved=round(done * 0.1, 2))
