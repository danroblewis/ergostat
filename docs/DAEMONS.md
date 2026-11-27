# Daemons: one long-lived process instead of a process each time

A sensor written as `run:` starts a process for every reading, and a program block written as `run:` starts one for
every run. For a few sensors that is the simplest thing and the right one. For many it adds up: 170 sensors read
every 3 minutes are 57 process starts a minute, and each start loads an interpreter, its libraries, and often a
fresh connection to the service it reads.

A **daemon** is a program ergostat starts once and keeps running. Instead of starting a process, ergostat writes a
line of JSON to the daemon's standard input ("read this sensor", "work this item"), and the daemon answers with
lines of JSON on its standard output. One daemon can answer many sensors and work many items at once.

This page says when a daemon is worth it, shows the four shapes with programs you can copy, and covers testing,
moving existing sensors over, keeping failures apart, and what it costs. The reference is
[SPEC section 9.7](SPEC.md); [RUNTIME.md](RUNTIME.md) explains where daemons sit inside a running ergostat and
has the measurements. Every example on this page is run by ergostat's tests, so what you copy works.

The YAML keys may still change: the owner is reviewing the schema (see `docs/GAPS.md`, "daemon YAML schema
review"). The protocol and the behaviour described here are what runs today.

## When to use a daemon, and when not

Use one when:

- **Process starts are the cost.** Many sensors on short schedules, or items arriving faster than a process
  starts. The bench in [RUNTIME.md](RUNTIME.md) measured 170 Python sensors every 3 minutes: 9.7 CPU seconds over
  six and a half minutes as processes, 2.2 as one daemon, with one process start instead of 510.
- **A session is worth keeping.** A client that logs in, opens a connection pool or loads a large library once
  can serve every reading after that. Command sensors pay for it every time.
- **Queries can be batched.** Thirty sensors that read the same service on the same schedule are asked within
  the same moment. A daemon can answer all of them with one query.
- **Readings arrive on their own.** A log being followed, or a stream being watched, has news when it has news. A
  push daemon sends a reading when it sees one, rather than waiting to be asked.

Keep `run:` when:

- there are only a few sensors, or they read rarely (hourly, daily): a process start is nothing at that rate;
- the command is a one-liner you can read in the YAML (`ls inbox | wc -l`): a daemon is a program to keep;
- each run must be isolated: a block whose runs should share nothing (memory, open files, a crash) is safer as a
  process each, and its CPU and memory are then measured per run. A daemon's are measured only for the daemon
  as a whole.
- the readings come from items or from Prometheus: `projection:` and `query:` sensors start no process already.

## The protocol in plain words

ergostat and a daemon exchange one JSON object per line, in both directions.

ergostat writes four kinds of line to the daemon:

| Line | What it asks |
|---|---|
| `{"op": "read", "sensor": "orders.main", "request": "7f3a..."}` | Read this sensor now and answer, quoting the request |
| `{"op": "item", "run": "fe51...", "item": "job/12", "lease": {...}, "input": {...}, "env": {...}}` | Work this item. `input` is what a `run:` block gets on its standard input (the item, its fields, its goal); `env` holds the `ERGOSTAT_*` values that run's process would have had |
| `{"op": "cancel", "run": "fe51..."}` | Stop that run (its lease expired, it ran past its timeout, or the owner stopped it) and say it is done |
| `{"op": "stop"}` | Finish what you hold and exit. Standard input is closed after it |

The daemon writes back, every line tagged with what it belongs to:

| Line | What it says |
|---|---|
| `{"reading": 12, "request": "7f3a..."}` | The answer to a reading. `{"error": "why", "request": "7f3a..."}` when there is none |
| `{"reading": 12, "sensor": "errors.main"}` | A reading sent unasked, for a sensor declared `push: true` |
| `{"event": "job.done", "run": "fe51..."}` | Anything a `run:` block's process may print (events, `out`, `moved`), with the run added |
| `{"done": 0, "run": "fe51..."}` | The run ended with this exit code. Exactly these two keys, and a whole number |
| `{"event": "aws.eventbridge", "item": "...", "data": {...}}` | An event of its own, tagged with no run, request or sensor: what a collector that runs forever saw, recorded from the daemon (its name the source). `item` (or `key`) is optional. At most 50 a second, as a sensor's observations |
| `{"heartbeat": true}` | Still alive. Any line says so; this one says nothing else |

Sensors are named `STOCK.SENSOR`: a stock's single `sensor:` is called `main`, so `orders.main`. A line that is
not JSON, names no run or request, or names one the daemon was never given, is written to the daemon's log and
dropped. It is never given to another run. What the daemon writes to standard error goes to its log,
`logs/daemon-NAME.log` in the project's state folder (`~/.ergostat/<project>/`).

## Shape 1: one sensor with a daemon of its own

The smallest daemon serves one sensor, and is written inside it. This one counts the files in a folder. In shell,
with no process started per reading at all: the count is a glob, and the line is taken apart by the shell itself.

<!-- example: inbox, file: bin/count-files.sh -->
```sh
#!/bin/sh
# count-files.sh DIR: a sensor's daemon. It answers each reading asked of it with how many files are in DIR,
# and starts no process to do it: the count is a shell glob, the line is taken apart by the shell itself.
dir=${1:?usage: count-files.sh DIR}
mkdir -p "$dir" || exit 1
while IFS= read -r line; do
  case $line in
    *'"op": "read"'*)
      req=${line##*'"request": "'}; req=${req%%'"'*}
      set -- "$dir"/*
      [ -e "$1" ] || shift $#            # an empty folder: the glob matched nothing
      printf '{"reading": %d, "request": "%s"}\n' $# "$req" ;;
    *'"op": "stop"'*) exit 0 ;;
  esac
done
```

<!-- example: inbox, file: ergostat.yaml -->
```yaml
name: inbox
stocks:
  inbox:
    unit: files
    description: files waiting in inbox/
    sensor:
      daemon: {run: sh bin/count-files.sh inbox}     # was: run: ls inbox | wc -l
      every: 10s
```

`daemon:` takes the place of `run:`. Written as a map, the daemon belongs to this sensor alone and is named after
it (`sensor.inbox.main`). The shell takes the line apart by matching text, which relies on how ergostat writes
JSON (`"key": "value"`, one space after the colon). That is fine for ids and sensor names; for anything richer,
read the line with a JSON parser (Python's `json`, or `jq`).

## Shape 2: one daemon for several sensors, one per outside service

When several sensors read the same service, give them one daemon between them, declared once under `daemons:`
and named from each sensor. The daemon keeps one session to the service for as long as it lives, and answers the
readings asked at the same moment with one query.

The example reads a job service's queues, one stock per queue. The service is a SQLite file standing in for
yours: replace `connect()` and `depths()` with your own client (an HTTP session, a database pool).

<!-- example: job-service, file: bin/queues.py -->
```python
#!/usr/bin/env python3
"""queues.py: one daemon for every sensor that reads the job service's queues (a stock per queue, named for it).

It keeps one connection to the service for as long as it lives, and answers the readings asked at the same moment
with one query between them. The service here is a SQLite file standing in for yours: put your client (an HTTP
session, a database pool) in connect() and depths()."""
import json
import os
import queue
import sqlite3
import sys
import threading
import time
import traceback

BATCH = 0.05                                     # readings asked within 50 ms share one query
asked: queue.Queue = queue.Queue()
out = threading.Lock()


def say(**line):
    with out:
        print(json.dumps(line), flush=True)


def fail_hard(args):
    traceback.print_exception(args.exc_type, args.exc_value, args.exc_traceback)
    os._exit(1)


def connect():
    return sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)   # read-only: a sensor never changes what it reads


def depths(db, queues: list[str]) -> dict[str, int]:
    marks = ",".join("?" * len(queues))
    rows = db.execute(f"SELECT queue, COUNT(*) FROM jobs WHERE state = 'waiting' AND queue IN ({marks}) "
                      "GROUP BY queue", queues)
    return {q: 0 for q in queues} | dict(rows)


def answer():
    db = connect()                               # the kept session: opened once, used for every reading
    while (first := asked.get()) is not None:
        time.sleep(BATCH)                        # the rest of this round's readings arrive meanwhile
        batch = [first]
        while not asked.empty():
            batch.append(asked.get())
        stopping = None in batch
        batch = [m for m in batch if m is not None]
        queues = sorted({m["sensor"].split(".")[0] for m in batch})
        try:
            got = depths(db, queues)             # one query for the whole batch
        except Exception as err:                 # each reading says why it has none; then the daemon ends
            for m in batch:
                say(error=f"the job service: {err}", request=m["request"])
            raise
        for m in batch:
            say(reading=got[m["sensor"].split(".")[0]], request=m["request"])
        if stopping:
            return


threading.excepthook = fail_hard
answering = threading.Thread(target=answer, daemon=True)   # (daemon=True: a broken line below ends the process)
answering.start()
for line in sys.stdin:                           # the reader: hands each reading on, never waits for the service
    m = json.loads(line)
    if m["op"] == "read":
        asked.put(m)
    elif m["op"] == "stop":
        break
asked.put(None)                                  # the readings already asked are answered, then it ends
answering.join()
```

<!-- example: job-service, file: ergostat.yaml -->
```yaml
name: job-service

daemons:
  job-service:
    run: python3 bin/queues.py jobs.db
    description: the job service's queues, one connection, readings batched
    restart: {max: 5, within: 10m, backoff: [2s, 5m]}

stocks:
  orders:
    unit: jobs
    description: order jobs waiting in the job service
    sensor: {daemon: job-service, every: 1m}
  refunds:
    unit: jobs
    description: refund jobs waiting in the job service
    sensor: {daemon: job-service, every: 1m}
  emails:
    unit: jobs
    description: email jobs waiting in the job service
    sensor: {daemon: job-service, every: 1m}
```

To try it, make the stand-in service: twelve orders and three refunds waiting.

<!-- example: job-service, run -->
```sh
python3 - <<'EOF'
import sqlite3
db = sqlite3.connect("jobs.db")
db.execute("CREATE TABLE IF NOT EXISTS jobs (id INTEGER PRIMARY KEY, queue TEXT, state TEXT)")
db.executemany("INSERT INTO jobs (queue, state) VALUES (?, ?)",
               [("orders", "waiting")] * 12 + [("refunds", "waiting")] * 3 + [("orders", "done")] * 5)
db.commit()
EOF
```

Three things in it are worth copying whatever the service:

- **The reader never waits.** The loop over standard input only puts each request on a queue. The service is
  asked on another thread, so a slow service never stops the daemon from reading (ergostat restarts a daemon that
  stops reading, below).
- **Errors are said, then the daemon ends.** A query that fails answers each reading in the batch with
  `{"error": ...}`, so the sensors' failures say why, and then the exception ends the daemon
  (`threading.excepthook`). ergostat starts it again after a back-off, with a fresh connection. A daemon that
  carries on half-broken, its connection dead, is worse than one that stops.
- **Stop finishes what was asked.** On `stop`, the readings already asked are answered before it exits.

Shell is a poor fit for this shape: it cannot keep a session open or wait on two things at once without
starting processes. Write a shared daemon in the language of the service's client.

## Shape 3: readings the daemon sends by itself

With `push: true`, nothing asks the sensor for readings: its daemon sends them when it has them, as
`{"reading": V, "sensor": "STOCK.SENSOR"}`. ergostat takes at most one a second for each sensor and drops the
rest, so send the latest, not every change. A push daemon still reads its standard input, to be told to stop.

In Python, a daemon that follows a log as it grows, reading only what was added since it last looked:

<!-- example: pushed, file: bin/tail-errors.py -->
```python
#!/usr/bin/env python3
"""tail-errors.py LOG SENSOR: a push daemon. It follows LOG as it grows and, every 5 seconds, sends SENSOR the number
of lines with ERROR in them so far, reading only what was added since it last looked."""
import json
import os
import sys
import threading
import time
import traceback

log, sensor = sys.argv[1], sys.argv[2]
out = threading.Lock()


def say(**line):
    with out:
        print(json.dumps(line), flush=True)


def fail_hard(args):
    traceback.print_exception(args.exc_type, args.exc_value, args.exc_traceback)
    os._exit(1)


def follow():
    errors, at = 0, 0                            # what it has counted, and how far into the file
    while True:
        try:
            with open(log, "rb") as f:
                if os.fstat(f.fileno()).st_size < at:
                    errors, at = 0, 0            # the log was rotated or emptied: counted afresh
                f.seek(at)
                new = f.read()
        except FileNotFoundError:
            new = b""
        whole = new[:new.rfind(b"\n") + 1]       # a line still being written waits for the next look
        errors += sum(b"ERROR" in line for line in whole.splitlines())
        at += len(whole)
        say(reading=errors, sensor=sensor)
        time.sleep(5)


threading.excepthook = fail_hard
threading.Thread(target=follow, daemon=True).start()
for line in sys.stdin:                           # nothing is asked of a push daemon but to stop
    if json.loads(line)["op"] == "stop":
        break
```

In shell, one that sends how full the disk is every 30 seconds. The sending runs in the background, so the loop
can wait to be told to stop. If `df` gives nothing, it ends the whole daemon (`kill $$`) rather than going quiet.

<!-- example: pushed, file: bin/disk-used.sh -->
```sh
#!/bin/sh
# disk-used.sh SENSOR: a push daemon. Every 30 seconds it sends SENSOR how full, in percent, the disk holding the
# model's folder is. The sending runs in the background; the loop below only waits to be told to stop.
sensor=${1:?usage: disk-used.sh STOCK.SENSOR}
(
  while :; do
    used=$(df -P . | awk 'NR == 2 { sub("%", "", $5); print $5 }')
    [ -n "$used" ] || { echo "df gave no reading" >&2; kill $$; exit 1; }   # fail hard: the whole daemon ends
    printf '{"reading": %s, "sensor": "%s"}\n' "$used" "$sensor"
    sleep 30
  done
) &
while IFS= read -r line; do
  case $line in *'"op": "stop"'*) break ;; esac
done
kill $! 2>/dev/null
```

<!-- example: pushed, file: ergostat.yaml -->
```yaml
name: pushed

stocks:
  errors:
    unit: lines
    cumulative: true
    description: lines with ERROR in app.log, so far
    sensor:
      daemon: {run: python3 bin/tail-errors.py app.log errors.main}
      push: true
  disk-used:
    unit: percent
    description: how full the disk holding this folder is
    sensor:
      daemon: {run: sh bin/disk-used.sh disk-used.main}
      push: true
```

(The shell one still starts `df` and `awk` every 30 seconds. It saves ergostat's process start and the shell's,
not the command's.)

## Shape 4: a block's daemon, working items under leases

A program block may say `daemon:` instead of `run:`. Each item the block takes is handed to the daemon as an `item`
line, and many may be under way at once, up to the smaller of the block's `pool` and the daemon's `concurrency`.
Each is still a run in the record, with its lease: the lines the daemon prints for it renew the lease as a run's
lines always do, and its `done` ends the run and the lease: acknowledged when the item moved on to one of the
block's `to:` states, given back to the queue otherwise.

This model is `examples/daemon-demo/`. Jobs arrive every five seconds from a stand-in for the outside; one worker
daemon works them, eight at once; and the files they leave are counted by the daemon from shape 1.

<!-- example: daemon-demo, file: ergostat.yaml -->
```yaml
# Jobs worked by one long-lived worker, many at once, and the finished ones counted by a second daemon.
name: daemon-demo

projections:
  job:
    match:
      key: job/*
    states: [ready, done]
    events:
      job.opened:
        state: set('ready')
      job.done:
        state: set('done')
    otherwise: rest
    description: a job; its work leaves a file in done/

stocks:
  ready:
    unit: jobs
    description: jobs waiting for the worker
    sensor: {projection: job, state: ready, every: 3s}
  finished:
    unit: jobs
    cumulative: true
    description: the files the jobs left in done/
    sensor:
      daemon: {run: sh bin/count-files.sh done}      # its own daemon: no process started per reading
      every: 5s

flows:
  arrivals:
    to: ready
    description: jobs opened from outside
    sensor: {projection: job, entering: ready, over: 10m}
  working:
    from: ready
    to: finished
    description: jobs the worker finished
    driven-by: [+stock.ready]
    equation: stock.ready / job-time
    sensor: {projection: job, entering: done, over: 10m}

parameters:
  job-time: {value: 3s, estimate: true, description: roughly how long a job takes}

goals:
  nothing-waits:
    stock: ready
    hold: "<= 0"
    tolerance: 0
    description: every job taken as it comes

blocks:
  arrive:
    type: program
    every: 5s
    run: sh bin/arrive.sh
    out: flow.arrivals
    description: a stand-in for the outside, opening a job
  worker:
    type: program
    goal: nothing-waits
    takes: {projection: job, at: ready, to: [done]}
    pool: 8
    lease: {ttl: 1m, attempts: 3}
    daemon: {run: python3 bin/worker.py, concurrency: 8, heartbeat: 30s}
    out: flow.working
    description: works each job in a process of its own, eight at once, in one long-lived worker
```

<!-- example: daemon-demo, file: bin/worker.py -->
```python
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
```

<!-- example: daemon-demo, file: bin/arrive.sh -->
```sh
#!/bin/sh
# arrive.sh: a stand-in for the outside. Each run opens one job, which takes 1 to 4 seconds.
n=$(date +%s)
printf '{"event": "job.opened", "item": "job/%s", "data": {"seconds": %d}}\n' "$n" $((n % 4 + 1))
```

(`bin/count-files.sh` is the one from shape 1.) What the worker does that every block daemon should:

- **Each item on a thread of its own.** The loop over standard input starts the work and goes back to reading
  at once, so a cancel or the next item is never kept waiting.
- **Each item's environment stays with its item.** `env` in the item line holds `ERGOSTAT_ITEM`, `ERGOSTAT_RUN`,
  `ERGOSTAT_LEASE` and the rest. The worker hands them to the process it starts for that job and never sets them
  in its own environment, where the next job would find them. The daemon's own environment holds only what every
  item shares (`ERGOSTAT_CMD`, `ERGOSTAT_PROJECT`, `ERGOSTAT_STATE_DIR`, `ERGOSTAT_SOCKET`).
- **The job's own output goes to the log** (`stdout=sys.stderr`): the daemon's standard output is for its lines.
- **A cancel is honoured.** It stops that job's process group, and `work()` then says `done` for it with exit 1.
  ergostat waits a grace (10 seconds) for that `done`; a daemon still holding the run after it is restarted.
- **A heartbeat**, every 10 seconds, against the `heartbeat: 30s` declared. ergostat restarts a daemon that prints
  nothing at all for that long, and a busy worker may be quiet.
- **`done` is exact**: `{"done": 0, "run": ...}`, nothing else in the line, the exit a whole number (`0`, never
  `true` or `0.0`). Anything else is dropped, and the run would wait until its timeout.

The same block in shell, one job at a time. The work runs in the background so the loop keeps reading and can
act on a cancel; `concurrency: 1` keeps ergostat from handing it a second job meanwhile.

<!-- example: shell-jobs, file: bin/worker.sh -->
```sh
#!/bin/sh
# worker.sh: a block's daemon in shell, one job at a time (declare concurrency: 1). The job's work runs in the
# background, with the job's own ERGOSTAT_ITEM, so this loop goes on reading and can act on a cancel.
mkdir -p done || exit 1
run= job=
while IFS= read -r line; do
  case $line in
    *'"op": "item"'*)
      run=${line#*'"run": "'}; run=${run%%'"'*}        # the first "run" and "item" are the line's own
      item=${line#*'"item": "'}; item=${item%%'"'*}
      (
        export ERGOSTAT_ITEM="$item" ERGOSTAT_RUN="$run"  # in the job's subshell only, never the daemon's
        if sleep 1 && date > "done/${ERGOSTAT_ITEM#job/}"; then
          printf '{"event": "job.done", "run": "%s"}\n{"done": 0, "run": "%s"}\n' "$run" "$run"
        else
          printf '{"done": 1, "run": "%s"}\n' "$run"
        fi
      ) &
      job=$! ;;
    *'"op": "cancel"'*)
      kill "$job" 2>/dev/null && printf '{"done": 1, "run": "%s"}\n' "$run" ;;
    *'"op": "stop"'*) break ;;
  esac
done
wait                                                    # the job under way finishes before it exits
```

<!-- example: shell-jobs, file: ergostat.yaml -->
```yaml
name: shell-jobs
projections:
  job:
    match:
      key: job/*
    states: [ready, done]
    events:
      job.opened:
        state: set('ready')
      job.done:
        state: set('done')
    otherwise: rest
stocks:
  ready:
    unit: jobs
    sensor: {projection: job, state: ready, every: 3s}
goals:
  nothing-waits: {stock: ready, hold: "<= 0", tolerance: 0}
blocks:
  worker:
    type: program
    goal: nothing-waits
    takes: {projection: job, at: ready, to: [done]}
    pool: 1
    lease: {ttl: 1m}
    daemon: {run: sh bin/worker.sh, concurrency: 1}
```

Give it a job by hand, with ergostat running: `ergostat event --add job.opened --item job/1`.

## The settings

A daemon is written either as a map in place of `run:` (on a sensor or a program block: its own daemon, named
`sensor.STOCK.SENSOR` or `block.NAME`), or under `daemons:` and named from each sensor and block that uses it.
Either way it takes:

| Key | Default | What it does |
|---|---|---|
| `run` | (required) | The command that starts it, run in the model's folder |
| `concurrency` | 10 | The most runs it holds at once, shared by every block that uses it. Readings are not counted |
| `heartbeat` | never | Restarted when it prints no line of any kind for this long |
| `restart` | `{max: 5, within: 10m, backoff: [1s, 2m]}` | Restarts wait `backoff`'s first, doubled each time up to its second; more than `max` restarts within `within` and it is given up |
| `stdin-timeout` | 10s | Restarted, with an alarm, when a write to its standard input waits this long |
| `description` | | What it is, for the Agents page |

On a sensor: `daemon:` (the map or a name), `every:` or `cron:` as for any sensor, `timeout:` (30 seconds by
default: a reading not answered by then fails), and `push: true` for a daemon that sends readings itself. On a
block: `daemon:` instead of `run:`, with `takes:`, `pool:`, `lease:` and `timeout:` as for any program block.

## How ergostat looks after a daemon

ergostat starts each daemon when the model needs it and watches it on a thread of its own. Nothing a daemon does
can hold up the engine: every line written to a daemon goes through a queue of its own and a writer thread.

- **It exits.** It is started again after a back-off: 1 second, then 2, 4, and so on up to 2 minutes (or the
  `backoff:` you set). The runs it held fail and are counted against their items' attempts; the readings it was
  asked fail.
- **It goes quiet.** With `heartbeat:` set, a daemon that prints nothing for that long is restarted.
- **It stops reading its standard input.** A write that waits longer than `stdin-timeout`, or 1,000 lines
  queued and unread, and it is restarted and an alarm raised: a daemon that does not read is stuck.
- **A run must stop.** When an item's lease expires, a run passes its `timeout`, or the owner runs
  `ergostat block NAME --stop`, ergostat sends `cancel`. A daemon that still holds the run 10 seconds later is
  restarted, and the other items it held are given back without counting against them.
- **It keeps failing.** More than `max` restarts within `within` and ergostat gives up: the daemon is `failed`,
  an alarm stands, and one `ergostat.daemon.failed` is recorded naming every block and sensor it served. While it
  is failed its blocks are handed no items (they wait in their queue) and its sensors are not read. Fix the
  cause, then `ergostat block job-service --restart` (a daemon's name, or a block's name for its daemon) starts it
  afresh with its count of restarts forgotten. Any change to the model does the same.
- **Whatever it started goes with it.** Each daemon leads a process group of its own; when it ends for any reason
  the whole group is stopped, so no child outlives it.
- **The model changes.** A daemon whose definition changed is sent `stop` and drained: its runs finish, and a
  new one, started at once, takes the new work. One whose definition is the same carries on untouched.
- **ergostat stops.** Each daemon is sent `stop`, and killed if it has not exited within 10 seconds.
- **ergostat restarts itself** (a new model's name or store, or its watchdog's last resort). Just before, every
  daemon's process group is sent SIGTERM, then SIGKILL after at most 3 seconds in all; on the watchdog's restart
  they are sent no `stop`, and the items they held are taken again when their leases end.

The Agents page lists the daemons, each with its state (running, backoff, failed, stopped), its process, how many
times it restarted, the last line it printed, the runs it holds, what it serves, and its CPU and memory. `ergostat status` shows a
failed daemon's alarm.

## Testing a daemon by hand

A daemon is a program that reads lines and writes lines, so it can be tried without ergostat: pipe lines into it
from the model's folder, as ergostat would start it, and read what comes out.

A sensor daemon, asked for two readings, then told to stop:

<!-- example: job-service, run -->
```sh
printf '%s\n' \
  '{"op": "read", "sensor": "orders.main", "request": "1"}' \
  '{"op": "read", "sensor": "refunds.main", "request": "2"}' \
  '{"op": "stop"}' | python3 bin/queues.py jobs.db
```

<!-- example: job-service, output -->
```text
{"reading": 12, "request": "1"}
{"reading": 3, "request": "2"}
```

A block daemon, given two jobs, the second cancelled while it works. An item line needs only what your daemon
reads from it; this worker reads `run`, `env` and the job's `seconds`:

<!-- example: daemon-demo, run -->
```sh
printf '%s\n' \
  '{"op": "item", "run": "r1", "item": "job/1", "input": {"item": {"fields": {"seconds": 1}}}, "env": {"ERGOSTAT_ITEM": "job/1"}}' \
  '{"op": "item", "run": "r2", "item": "job/2", "input": {"item": {"fields": {"seconds": 5}}}, "env": {"ERGOSTAT_ITEM": "job/2"}}' \
  '{"op": "cancel", "run": "r2"}' \
  '{"op": "stop"}' | python3 bin/worker.py
```

<!-- example: daemon-demo, output -->
```text
{"heartbeat": true}
{"done": 1, "run": "r2"}
{"event": "job.done", "run": "r1", "data": {"seconds": 1}}
{"done": 0, "run": "r1"}
```

What to look for:

- **Every line is JSON and tagged** with the `request` or `run` it answers (a heartbeat excepted). Anything else
  on standard output (a stray `print`, a child's output) would be dropped by ergostat.
- **Every request is answered and every run ends with exactly one `done`**, whose exit is a whole number.
- **A cancel is answered at once**, not when the work would have finished: here `r2` ends after a moment, not
  after its five seconds.
- **`stop` ends it, with exit 0**, once what it held is finished; so does the end of its input (`echo $?`).
- **A broken line ends it, with an exit other than 0**: `echo 'not json' | python3 bin/worker.py; echo $?`.
- **The reader is never blocked**: give it a slow item, then a read or a cancel, and the second is answered
  without waiting for the first.

Then run it under ergostat in a copy of the project, where nothing real is touched:
`cp -r . /tmp/try && ergostat -C /tmp/try check && ergostat -C /tmp/try run`, and after a minute
`ergostat -C /tmp/try sensor orders.main` (the readings), the Agents page (the daemon, running, with no
restarts), and its log in the state folder's `logs/`. `ergostat -C /tmp/try run --stop` when done.

## Moving existing `run:` sensors to a daemon

Move them a group at a time, a group being the sensors that read one service, and compare the readings before
you switch.

1. **Choose a group.** The sensors whose commands talk to the same service, with the same client. Say the job
   service's three queues were read by one small script each:

   <!-- example: job-service, file: bin/depth.py -->
   ```python
   #!/usr/bin/env python3
   """depth.py QUEUE: the old sensor, a process per reading, connecting each time."""
   import sqlite3
   import sys

   db = sqlite3.connect("jobs.db")
   print(db.execute("SELECT COUNT(*) FROM jobs WHERE queue = ? AND state = 'waiting'", (sys.argv[1],)).fetchone()[0])
   ```

   ```yaml
   stocks:
     orders:
       unit: jobs
       sensor: {run: python3 bin/depth.py orders, every: 1m}
   ```

2. **Write the daemon** to answer each sensor of the group by its name (shape 2), and test it by hand.

3. **Compare it with the old commands**, sensor by sensor, before ergostat sees it. This script runs each old
   command once and asks the daemon for the same sensor, side by side, and exits 1 when any differ:

   <!-- example: job-service, file: compare.py -->
   ```python
   #!/usr/bin/env python3
   """compare.py DAEMON SENSOR=COMMAND ...: each sensor's old run: command, run once, beside the daemon's answer for the
   same sensor. Run it in the model's folder. Exits 1 when any differ."""
   import json
   import subprocess
   import sys

   daemon = subprocess.Popen(sys.argv[1], shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
   differ = 0
   for n, pair in enumerate(sys.argv[2:]):
       sensor, command = pair.split("=", 1)
       old = subprocess.run(command, shell=True, capture_output=True, text=True, check=True).stdout.strip()
       old = json.loads(old)["value"] if old.startswith("{") else float(old)
       daemon.stdin.write(json.dumps({"op": "read", "sensor": sensor, "request": str(n)}) + "\n")
       daemon.stdin.flush()
       while True:                                  # (heartbeats and pushes skipped)
           line = daemon.stdout.readline()
           if not line:
               sys.exit(f"the daemon ended (exit {daemon.wait()}): see what it wrote above")
           got = json.loads(line)
           if got.get("request") == str(n):
               break
       new = got.get("reading", got.get("error"))
       same = isinstance(new, int | float) and abs(new - old) < 1e-9
       differ += not same
       print(f"{sensor:30} old {old:>10g}   daemon {new!s:>10}   {'same' if same else 'DIFFERENT'}")
   daemon.stdin.write(json.dumps({"op": "stop"}) + "\n")
   daemon.stdin.close()
   daemon.wait()
   sys.exit(1 if differ else 0)
   ```

   <!-- example: job-service, run -->
   ```sh
   python3 compare.py "python3 bin/queues.py jobs.db" \
     "orders.main=python3 bin/depth.py orders" \
     "refunds.main=python3 bin/depth.py refunds" \
     "emails.main=python3 bin/depth.py emails"
   ```

   <!-- example: job-service, output -->
   ```text
   orders.main                    old         12   daemon         12   same
   refunds.main                   old          3   daemon          3   same
   emails.main                    old          0   daemon          0   same
   ```

   A service that changes between the two reads can differ by a little; run it twice, at a quiet moment.

4. **Run them side by side for a while** (a day, or a few rounds of the slowest schedule). Give each stock a
   second sensor read by the daemon, beside the old one, under `sensors:`:

   ```yaml
   daemons:
     job-service: {run: python3 bin/queues.py jobs.db}
   stocks:
     orders:
       unit: jobs
       sensors:
         main: {run: python3 bin/depth.py orders, every: 1m}
         via-daemon: {daemon: job-service, every: 1m}
   ```

   (The daemon is then asked for `orders.via-daemon`; `queues.py` reads the queue from the stock's name, so it
   answers the same.) Compare `ergostat sensor orders.main` with `ergostat sensor orders.via-daemon`. While both run,
   the stock takes whichever read last, so a difference shows up on the diagram as a jagged line, and in
   `ergostat residual`.

5. **Switch.** Remove the old sensor and name the daemon's one `main` (or write it back as `sensor:`), so the
   series keeps its name and its history: `sensor: {daemon: job-service, every: 1m}`. Delete the old scripts once
   nothing names them.

6. **Watch the next group's first day** on the Agents page: the daemon's restarts, and its CPU and memory beside
   what the old processes cost.

## Keeping failures apart

A daemon fails as a whole: when it crashes, every run it held fails and every reading it was asked fails; when it
is given up, every sensor it serves goes unread and every block it serves stops getting items. So group by what
fails together:

- **One daemon per outside service.** When the service is down, its daemon fails and is given up, with one alarm
  naming its sensors, and the sensors reading other services go on. A daemon that reads two services takes both
  groups down when either fails.
- **Keep blocks apart from sensors** unless they share a session worth sharing. A block's work is the likelier
  to crash, and its sensors would go with it.
- **Keep risky work in a process of its own.** A job that may run out of memory or hang belongs in a child
  process (as `worker.py` does) or in a `run:` block, not in the daemon's own memory.
- **Set `restart:` for the service.** A service that is down for minutes at a time wants a longer back-off and a
  wider window (`backoff: [2s, 5m]`), so the daemon is not given up during an outage it would ride out.

## What it costs

- **Per daemon:** one process for as long as it runs (a small Python daemon held about 11 to 13 MB in the bench),
  its CPU while it works, two threads in the engine (one writing to it, one reading from it), and its log file.
  The Agents page shows its CPU and memory, sampled every 30 seconds.
- **Per reading:** one line each way. No process, and no thread of the sensor pool held while it waits.
- **Per item:** the run is recorded as any run is, with its wall time only. A process serving many items at once
  cannot say which CPU second was whose, so no run claims CPU or memory: they are the daemon's.
- **Against processes:** at 170 sensors every 3 minutes, one daemon cut the CPU of the engine and everything it
  started from 9.7 to 2.2 seconds over 6.5 minutes, and the process starts from 510 to 1. A shell one-liner costs
  less to start than a Python script, and a sensor that loads a client library more, so the saving grows with what
  each start loads. The figures, and how to measure again, are in [RUNTIME.md](RUNTIME.md).

## Try it

`cd examples/daemon-demo && ergostat run`, then open its page: the Agents page lists the two daemons, the items
move from `ready` to `done`, and `finished` counts the files the worker left.
