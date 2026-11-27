# Writing a daemon for ergostat

Read this before you write or change a daemon: a long-lived program ergostat hands sensor readings and block runs
to as JSON lines (SPEC §9.7). People's how-to, with longer examples and the migration steps, is `docs/DAEMONS.md`.
Every template here is run by ergostat's tests (`tests/test_daemon_docs.py`); copy them rather than starting
from nothing.

## Decide first

Write a daemon only when process starts or sessions are the cost: many `run:` sensors on short schedules, items
arriving faster than a process starts, a client that is slow to start or log in, or many sensors that one batched
query could answer. Keep `run:` for a few sensors, hourly or daily ones, one-liners, and blocks whose runs must not
share a process. `projection:`, `changes:` and `query:` sensors start no process: never replace them with a daemon.

Pick the shape:

| Need | Shape | YAML |
|---|---|---|
| one costly sensor | its own daemon | `sensor: {daemon: {run: ...}, every: 1m}` |
| several sensors on one service | one shared daemon per service, session kept, reads batched | `daemons: {svc: {run: ...}}`, each `sensor: {daemon: svc, every: 1m}` |
| readings that arrive by themselves | push daemon | `sensor: {daemon: {run: ...}, push: true}` |
| a program block taking many items | block daemon | `daemon: {run: ..., concurrency: N, heartbeat: 30s}` instead of `run:`, with `takes:`, `pool:`, `lease:` |
| a block's program slow to start, one item at a time, keeping nothing between items | warm block daemon (SPEC §9.7, *Warm*) | `daemon: {run: ..., warm: true, concurrency: N}`: N processes, one run each at a time, each run charged its CPU |
| a block daemon whose items take long, kept going through an engine restart | kept block daemon (SPEC §9.7, *A daemon that outlives its engine*) | `daemon: {run: ..., outlive-engine: true}`: an item may be sent again with the same `run` id after a restart; keep the ids taken and drop a repeat |

A warm daemon's program reads one item, does it, reaps everything it started, and says `done`; it never writes
`os.environ` (pass `{**os.environ, **env}` to what it starts) and keeps nothing for the next item. A process that
leaves a child running at `done`, or prints a line for no run it holds, is restarted. Check the promise with
`ergostat block NAME --check-warm input.json` (four real runs: use a scratch copy when it acts).

Group by failure: **one daemon per outside service.** A daemon fails as a whole (its runs fail, its sensors go
unread when it is given up), so a daemon serving two services takes both down. Do not share a daemon between a
block and sensors unless they share a session.

## The protocol

In (one JSON object per line on standard input; ergostat writes `"key": "value"` with one space):

- `{"op": "read", "sensor": "STOCK.SENSOR", "request": ID}`: answer `{"reading": NUMBER, "request": ID}`, or
  `{"error": WHY, "request": ID}`. A single `sensor:` is named `main`. Unanswered within the sensor's `timeout`
  (30 s): a failed reading.
- `{"op": "item", "run": ID, "item": ITEM, "lease": {...}, "input": {...}, "env": {...}}`: a run. `input` is a
  `run:` block's standard input (`input["item"]["fields"]`, `input["goals"]`, ...); `env` its `ERGOSTAT_*` values
  (`ERGOSTAT_ITEM`, `ERGOSTAT_RUN`, `ERGOSTAT_LEASE`, ...). Print its lines with `"run": ID` added; end it with
  `{"done": EXIT, "run": ID}`.
- `{"op": "cancel", "run": ID}`: stop that run; say `{"done": 1, "run": ID}` within 10 s.
- `{"op": "stop"}`: finish what you hold, exit 0. Standard input closes after it; treat end of input the same.

Out (standard output, flushed per line): only tagged lines. A run's line (`{"event": ..., "run": ID}`), `done`,
an answer, a push `{"reading": V, "sensor": "STOCK.SENSOR"}` (at most one a second per sensor is taken: send the
latest), `{"heartbeat": true}`. Everything else, and everything for a run or request you were not given, is
dropped into the log. Standard error is the log (`logs/daemon-NAME.log` in the state folder).

## Rules

1. **Never block the standard-input reader.** The loop over standard input only parses and hands on: a thread per
   item or reading, or a queue to a worker. Work, network calls and waits happen elsewhere. A daemon that does not
   read for `stdin-timeout` (10 s), or lets 1,000 lines queue, is restarted with an alarm.
2. **Worker threads, one lock around printing.** Print each whole line under one lock, `flush=True` (or
   `python3 -u`). Interleaved half-lines are dropped lines.
3. **Tag every line** with its `run` or `request` (or `sensor` when pushing). Never print anything else to
   standard output: send a child process's output to standard error (`stdout=sys.stderr`) or to a file.
4. **Strict `done`:** exactly `{"done": EXIT, "run": ID}`, `EXIT` an `int` (`0` or `1`; never `True`, never
   `0.0`), no other key, once per run. Events go on their own lines before it.
5. **Honour `cancel`** for a run in any phase: before its work started (remember the id), during (kill its child's
   process group: `start_new_session=True`, `os.killpg`), and after (nothing to do). Say `done` with 1. Not done
   within 10 s and the whole daemon is restarted, its other runs given back.
6. **Heartbeat** when you declare `heartbeat:`: a daemon thread printing `{"heartbeat": true}` at a third of it or
   less. Without `heartbeat:` you are never restarted for silence; declare it on block daemons whose work can hang.
7. **Fail hard.** A line you cannot parse, a lost session, a bug: exit non-zero (`threading.excepthook` calling
   `os._exit(1)` so a worker thread's exception ends the process, not just the thread). ergostat restarts with a
   back-off and records why. Never catch and carry on half-broken. A reading you cannot take this once is not a
   crash: answer `{"error": WHY}` (said, not swallowed); if the cause is the session, then exit.
8. **Per-item env from the line, never the process env.** Pass `{**os.environ, **m["env"]}` to what you start for
   that item. Never `os.environ.update(m["env"])` or `export` in the daemon's own shell: the next item would find
   it. The process env holds only what all items share (`ERGOSTAT_CMD`, `ERGOSTAT_PROJECT`, `ERGOSTAT_STATE_DIR`,
   `ERGOSTAT_SOCKET`).
9. **Batch and keep the session.** Open the client once (in the worker thread that uses it). Collect the reads
   that arrive within ~50 ms and answer them with one query. Sensors on the same schedule are asked together.
10. **Measure, never act** in a sensor daemon: open the service read-only. A block daemon acts only as its block
    may (gated actions through `$ERGOSTAT_CMD act`, with the item's env).
11. **Read your own config from arguments** (`run: python3 bin/x.py jobs.db`), not from the item lines.
12. **Stop cleanly:** on `stop` or end of input, let in-flight work finish (non-daemon worker threads, or join a
    sentinel on the queue), then exit 0. A long-lived helper thread (the batching reader, the heartbeat) is
    `daemon=True` and joined explicitly on stop: a non-daemon thread blocked on a queue keeps a crashed process
    alive, and the daemon hangs instead of failing hard.

## Templates

### A sensor with its own daemon

<!-- example: t-inline, file: bin/disk-free.py -->
```python
#!/usr/bin/env python3
"""A sensor's own daemon: each reading answered off the reader's thread."""
import json
import os
import shutil
import sys
import threading
import traceback

out = threading.Lock()


def say(**line):
    with out:
        print(json.dumps(line), flush=True)


def fail_hard(a):
    traceback.print_exception(a.exc_type, a.exc_value, a.exc_traceback)
    os._exit(1)


def measure(sensor: str) -> float:               # the reading: replace this
    return round(shutil.disk_usage(".").free / 1e9, 2)


def answer(m):
    try:
        say(reading=measure(m["sensor"]), request=m["request"])
    except OSError as err:                       # this reading could not be taken: said, with why
        say(error=str(err), request=m["request"])


threading.excepthook = fail_hard
for line in sys.stdin:
    m = json.loads(line)                         # a broken line raises: exit 1, restarted
    if m["op"] == "read":
        threading.Thread(target=answer, args=(m,)).start()
    elif m["op"] == "stop":
        break
```

<!-- example: t-inline, file: ergostat.yaml -->
```yaml
name: t-inline
stocks:
  disk-free:
    unit: GB
    description: free space on the disk holding the model
    sensor:
      daemon: {run: python3 bin/disk-free.py}
      every: 1m
```

### One daemon shared by a service's sensors: session kept, reads batched

<!-- example: t-shared, file: bin/service.py -->
```python
#!/usr/bin/env python3
"""One daemon per outside service: one session, the reads of a moment answered by one query."""
import json
import os
import queue
import sqlite3
import sys
import threading
import time
import traceback

asked: queue.Queue = queue.Queue()
out = threading.Lock()


def say(**line):
    with out:
        print(json.dumps(line), flush=True)


def fail_hard(a):
    traceback.print_exception(a.exc_type, a.exc_value, a.exc_traceback)
    os._exit(1)


def query(db, names: list[str]) -> dict[str, float]:   # one round trip for the batch: replace with your client
    marks = ",".join("?" * len(names))
    return {n: 0 for n in names} | dict(db.execute(f"SELECT name, value FROM gauges WHERE name IN ({marks})", names))


def answer():
    db = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)   # the session, opened once, read-only
    while (m := asked.get()) is not None:
        time.sleep(0.05)                         # the rest of this moment's reads arrive
        batch = [m] + [asked.get() for _ in range(asked.qsize())]
        last = None in batch
        batch = [b for b in batch if b is not None]
        try:
            got = query(db, sorted({b["sensor"].split(".")[0] for b in batch}))
        except sqlite3.Error as err:             # said for each reading, then exit: a fresh session on restart
            for b in batch:
                say(error=str(err), request=b["request"])
            raise
        for b in batch:
            say(reading=got[b["sensor"].split(".")[0]], request=b["request"])
        if last:
            return


threading.excepthook = fail_hard
worker = threading.Thread(target=answer, daemon=True)   # daemon: a broken line still ends the process
worker.start()
for line in sys.stdin:
    m = json.loads(line)
    if m["op"] == "read":
        asked.put(m)
    elif m["op"] == "stop":
        break
asked.put(None)
worker.join()
```

<!-- example: t-shared, file: ergostat.yaml -->
```yaml
name: t-shared
daemons:
  gauges:
    run: python3 bin/service.py gauges.db
    description: the gauge service, one session for all its sensors
    restart: {max: 5, within: 10m, backoff: [2s, 5m]}
stocks:
  backlog:
    unit: requests
    description: requests waiting in the service
    sensor: {daemon: gauges, every: 1m}
  stuck:
    unit: requests
    description: requests the service holds as stuck
    sensor: {daemon: gauges, every: 1m}
```

The stand-in service, for a try:

<!-- example: t-shared, run -->
```sh
python3 -c "
import sqlite3; db = sqlite3.connect('gauges.db')
db.execute('CREATE TABLE IF NOT EXISTS gauges (name TEXT PRIMARY KEY, value REAL)')
db.execute(\"INSERT OR REPLACE INTO gauges VALUES ('backlog', 42), ('stuck', 2)\"); db.commit()"
```

### A push daemon

<!-- example: t-push, file: bin/push-inbox.py -->
```python
#!/usr/bin/env python3
"""A push daemon: sends its sensor a reading every 5 s; reads standard input only to stop."""
import json
import os
import sys
import threading
import time
import traceback

sensor = sys.argv[1]


def fail_hard(a):
    traceback.print_exception(a.exc_type, a.exc_value, a.exc_traceback)
    os._exit(1)


def push():
    os.makedirs("inbox", exist_ok=True)
    while True:
        print(json.dumps({"reading": len(os.listdir("inbox")), "sensor": sensor}), flush=True)
        time.sleep(5)


threading.excepthook = fail_hard
threading.Thread(target=push, daemon=True).start()
for line in sys.stdin:
    if json.loads(line)["op"] == "stop":
        break
```

<!-- example: t-push, file: ergostat.yaml -->
```yaml
name: t-push
stocks:
  inbox:
    unit: files
    description: files waiting in inbox/
    sensor:
      daemon: {run: python3 bin/push-inbox.py inbox.main}
      push: true
```

### A block daemon taking items under leases

<!-- example: t-block, file: bin/worker.py -->
```python
#!/usr/bin/env python3
"""A block's daemon: each item on a thread, its work in a child with the item's env; cancel honoured; heartbeat."""
import json
import os
import signal
import subprocess
import sys
import threading
import time
import traceback

out, lock = threading.Lock(), threading.Lock()
children: dict[str, subprocess.Popen] = {}
cancelled: set[str] = set()


def say(**line):
    with out:
        print(json.dumps(line), flush=True)


def fail_hard(a):
    traceback.print_exception(a.exc_type, a.exc_value, a.exc_traceback)
    os._exit(1)


def beat():
    while True:
        say(heartbeat=True)
        time.sleep(10)


def work(m):
    run, fields = m["run"], m["input"]["item"]["fields"]
    with lock:
        if run in cancelled:
            return say(done=1, run=run)
        children[run] = p = subprocess.Popen(      # the work: replace this command
            ["sh", "-c", 'sleep "$SECONDS_TO_TAKE" && echo "$ERGOSTAT_ITEM" >> worked.log'],
            env={**os.environ, **m["env"], "SECONDS_TO_TAKE": str(fields.get("seconds", 1))},
            stdout=sys.stderr, start_new_session=True)
    code = p.wait()
    with lock:
        children.pop(run, None)
    if code == 0:
        say(event="job.done", run=run)
    say(done=0 if code == 0 else 1, run=run)


threading.excepthook = fail_hard
threading.Thread(target=beat, daemon=True).start()
for line in sys.stdin:
    m = json.loads(line)
    if m["op"] == "item":
        threading.Thread(target=work, args=(m,)).start()
    elif m["op"] == "cancel":
        with lock:
            cancelled.add(m["run"])
            if m["run"] in children:
                os.killpg(children[m["run"]].pid, signal.SIGTERM)
    elif m["op"] == "stop":
        break
```

<!-- example: t-block, file: ergostat.yaml -->
```yaml
name: t-block
projections:
  job:
    query: key.startswith('job/')
    fields:
      state:
        type: one of [ready, done]
    events:
      job-opened:
        when: type == 'job.opened'
        '...': data
        state: set('ready')
      job-done:
        when: type == 'job.done'
        '...': data
        state: set('done')
      other:
        when: true
        '...': data
stocks:
  ready:
    unit: jobs
    description: jobs waiting
    sensor: {projection: job, state: ready, every: 3s}
goals:
  nothing-waits: {stock: ready, hold: "<= 0", tolerance: 0}
blocks:
  worker:
    type: program
    goal: nothing-waits
    takes: {projection: job, at: ready, to: [done]}
    pool: 8
    lease: {ttl: 1m, attempts: 3}
    daemon: {run: python3 bin/worker.py, concurrency: 8, heartbeat: 30s}
```

Shell suits only the simplest daemons (a count by glob, a timer that pushes): see `docs/DAEMONS.md` for shell
versions, and their limits (no kept session, one item at a time).

## Before you call a daemon done

Run each of these on a scratch copy of the project, and say in your report what each showed:

1. **`ergostat check` passes**: no error; each sensor's and block's `daemon:` names a daemon that exists.
2. **The pipe test**, from the model's folder, the daemon started as its `run:` says:
   - `printf '%s\n' '{"op": "read", "sensor": "STOCK.main", "request": "1"}' '{"op": "stop"}' | CMD` answers
     `{"reading": N, "request": "1"}`, for each sensor it serves, and exits 0;
   - for a block: an `item` line (`run`, `item`, `input.item.fields`, `env`), then a slow item and a `cancel` for
     it: one `done` each, the cancel's at once, exit codes whole numbers; then `stop`, exit 0 after the work ends;
   - every output line is JSON and tagged; nothing else on standard output;
   - `echo 'not json' | CMD; echo $?` is not 0 (fails hard);
   - a read or cancel sent after a slow item is answered without waiting for it (the reader is not blocked).
3. **A short run** (`ergostat -C COPY run`, a minute or a few rounds of `every:`): `ergostat -C COPY sensor
   STOCK.main` shows readings from it; items reach their `to:` states (`ergostat -C COPY item --projection K`); no
   `ergostat.daemon.restarted` or `ergostat.daemon.failed` (`ergostat -C COPY event --type 'ergostat.daemon.*'`);
   its log in the state folder's `logs/daemon-NAME.log` holds no `dropped` lines. Stop it (`run --stop`).
4. **Replacing `run:` sensors: the readings match the old ones.** For every sensor of the group, run its old
   command and ask the daemon for the same sensor, side by side, and show both:
   `sh -c 'OLD COMMAND'; printf '%s\n' '{"op": "read", "sensor": "STOCK.main", "request": "1"}' '{"op": "stop"}' | CMD`
   (`compare.py` in ergostat's `docs/DAEMONS.md`, "Moving existing run: sensors", does a whole group). Then, if the
   owner wants it, both as two sensors on each stock (`sensors: {main: {run: ...}, via-daemon: {daemon: svc}}`) for a
   day. Keep the sensor's name (`main`) when you switch, so its history continues. Move one group (one service) at
   a time.
5. **Show the owner** what changed: the group moved, the daemon's restart settings, and the compare output.
