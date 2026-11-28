# The daemon YAML: seven questions, their costs, and a recommendation each

Status: a review, written 2026-11-21 on the `daemon-yaml-schema-review` branch, for the owner to choose from. Nothing
here is decided and the schema has not changed: every "Today" below is main as it is, and every "proposed" model is
refused or read differently by today's `check`. The questions are the seven in the GAPS entry *Daemon YAML schema
review*.

What this covers: how a model's YAML says **which process** serves a sensor or a block (a `daemon:` written on the
sensor or block, or one under the top-level `daemons:` named from it) and **how that process is supervised** (its
`concurrency`, `heartbeat`, `restart` and `stdin-timeout`). The protocol of SPEC §9.7, the JSON lines exchanged with
the process, is out of scope, except where an alternative would add to it: only *Per-sensor arguments* does (its
`with:` becomes a field of the read line).

How to read each section:

- **Today**: the current form, each fact with the line of code it comes from.
- **Pairs**: a `today` model and a `proposed` model, each small and complete. The proposed one is the today one with
  only that section's change made. The tests (`tests/test_daemon_yaml_review.py`) check every `today` model with
  `ergostat check` (it passes) and every `proposed` one. A **syntax** pair's proposed model is refused today, and
  the error names the changed key. A **semantics** pair's proposed model is accepted today but means something else
  today; the section says what, with the line that does it.
- **What changes**: the modules and SPEC sections, whether the protocol gains anything, and whether the old
  spelling could stay accepted. Line counts are estimates and say so. ergostat already has the means to read an old
  name and report it: `Compiler.deprecated` (`ergostat/spec/compile.py:139`), which `check` reports once per file as
  a finding (`compile.py:147-154`). It is how `variables:` became `auxiliaries:`. So most renames below need not be
  a hard break for people who install from main.
- **Recommendation** and **Owner's decision**.

Every schema change below also changes `schema/ergostat.schema.json`, the machine-checkable form of SPEC, which
describes `daemons:`, a sensor's `daemon:` and `push:`, and a block's `daemon:` (its lines 478, 663-664, 1135 and
2678-2702). That is not repeated in each section.

## A modifier instead of a kind

**Today.**

- A sensor has exactly one of seven kinds: `run`, `query`, `manual`, `items`, `changes`, `builtin` or `daemon`
  (`ergostat/spec/compile.py:485`, refused otherwise at `compile.py:486-488`). `daemon` and `push` are sensor keys
  (`compile.py:65`).
- A `program` block takes `daemon` as a key (`compile.py:87`). It may then leave out `run` (`compile.py:1352`), and
  must: a block with both, or a `daemon:` on a block that is not a program, is an error
  (`ergostat/daemons/config.py:83-84`).
- `daemon:` is either a map, the daemon's own, or a name under the top-level `daemons:` (`config.py:72-80`). The
  map's keys are `KEYS`: `run`, `concurrency`, `heartbeat`, `restart`, `stdin-timeout`, `description`, `warm`,
  `recycle` (`config.py:8`). `run` is required (`config.py:24-27`).
- So moving a sensor over moves its command into the map: `run: X` becomes `daemon: {run: Y}`. **The command
  changes too**, in the docs' own example: `ls inbox | wc -l` became `sh bin/count-files.sh inbox`
  (`docs/DAEMONS.md:103`), because a daemon is a different program. It reads JSON lines on its standard input
  (`DAEMONS.md:84-91`), where a `run:` sensor prints one reading and exits. "The command stays where it was" holds
  for the YAML's layout, not for the command.

<!-- today: modifier -->
```yaml
name: inbox
stocks:
  inbox:
    unit: files
    description: files waiting in inbox/
    sensor:
      daemon: {run: sh bin/count-files.sh inbox}
      every: 10s
```

A syntax change: `keep: true` is no key of a sensor's today.

<!-- proposed: modifier, syntax: 'keep' -->
```yaml
name: inbox
stocks:
  inbox:
    unit: files
    description: files waiting in inbox/
    sensor:
      run: sh bin/count-files.sh inbox
      keep: true
      every: 10s
```

A block's daemon has knobs, and a modifier has to put them somewhere. Here they go in `keep:` as a map: it is
then today's `daemon:` map, renamed, with `run` outside it. The pair is the docs' `shell-jobs` block
(`docs/DAEMONS.md:566-588`).

<!-- today: modifier-block -->
```yaml
name: shell-jobs
projections:
  job:
    query: key.startswith('job/')
    fields:
      state: {values: [ready, done]}
    events:
      job-opened:
        when: type == 'job.opened'
        state: set('ready')
      job-done:
        when: type == 'job.done'
        state: set('done')
      other:
        when: true
        '...': data
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

<!-- proposed: modifier-block, syntax: 'keep' -->
```yaml
name: shell-jobs
projections:
  job:
    query: key.startswith('job/')
    fields:
      state: {values: [ready, done]}
    events:
      job-opened:
        when: type == 'job.opened'
        state: set('ready')
      job-done:
        when: type == 'job.done'
        state: set('done')
      other:
        when: true
        '...': data
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
    run: sh bin/worker.sh
    keep: {concurrency: 1}
```

`mode: daemon`, the GAPS entry's other spelling, would collide. `mode` is already a block key (`compile.py:84`),
`auto` or `advise` (`compile.py:1360-1362`). `keep` is no key of a sensor's or a block's today.

**What changes.**

- Modules: `ergostat/spec/compile.py` (`SENSOR_KEYS`, the seven kinds at line 485, the program keys at line 87, the
  `run` requirement at line 1352); `ergostat/daemons/config.py` (`section`, which would build the daemon from `run` +
  `keep` where it now reads the `daemon:` map, lines 66-80). After compiling, the rest reads `Sensor.daemon` and
  `b.params["daemon"]` as now (`supervise.py:77-78`), so `supervise.py`, `work.py` and `proc.py` do not change.
  An estimate: 30 to 50 lines.
- SPEC: §6 (the kinds, the table's `daemon` row), §9 (the program row: "`daemon` instead of `run`"), §9.7 (its
  opening and example). Also DAEMONS.md's shapes 1, 3 and 4 and its settings, and the skill's table
  (`docs/skills/ergostat-author/daemons.md:17-23`).
- Protocol: nothing.
- Old form: it can stay accepted. `daemon: {run: ...}` and `run:` + `keep:` compile to the same daemon, and `check`
  reports the old one through `deprecated`. `daemon: NAME`, naming a shared daemon, stays as it is in either case.

**Recommendation.** Keep today's. The modifier saves the YAML one line of indentation, not the move itself: the
command is rewritten anyway. A block daemon's knobs need a map, so `keep: {...}` is `daemon: {...}` with one key
moved out of it. Its cost is a second spelling across every place that writes an inline daemon (the table below).

**Owner's decision:** open.

## Per-sensor arguments

**Today.**

- The read line a daemon is sent is `{"op": "read", "sensor": "STOCK.SENSOR", "request": ID}`, and nothing more
  (`ergostat/daemons/work.py:136-137`; SPEC §9.7's table, `docs/SPEC.md:2310`).
- A sensor has no key for arguments: `SENSOR_KEYS` (`compile.py:65-66`) has none.
- So a shared daemon works out what to read from the sensor's name: the job service's `queues.py` takes the queue
  from `m["sensor"].split(".")[0]` (`docs/DAEMONS.md:173` and `181`), and the docs say so (`DAEMONS.md:794`). So do
  the skill's `service.py` (`docs/skills/ergostat-author/daemons.md:189` and `195`) and ticket-factory's
  `measure.py` (`examples/ticket-factory/bin/measure.py:35`). The skill's rule 11 tells authors to read a daemon's
  own configuration from its arguments (`daemons.md:81`), which is per daemon and not per sensor.
- The migration's side-by-side step works only because the daemon ignores the part after the dot:
  `orders.via-daemon` answers as `orders.main` does (`DAEMONS.md:790-795`).

The pair is the docs' job service (`docs/DAEMONS.md:199-221`), its stocks named for the queues:

<!-- today: with -->
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

A syntax change: `with` is no sensor key today.

<!-- proposed: with, syntax: 'with' -->
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
    sensor: {daemon: job-service, every: 1m, with: {queue: orders}}
  refunds:
    unit: jobs
    description: refund jobs waiting in the job service
    sensor: {daemon: job-service, every: 1m, with: {queue: refunds}}
  emails:
    unit: jobs
    description: email jobs waiting in the job service
    sensor: {daemon: job-service, every: 1m, with: {queue: emails}}
```

With it, a stock could be called anything (`pending-orders`), and a second sensor on it would still read the
`orders` queue.

**The protocol changes.** A `with:` sent in the read line **adds a field** to SPEC §9.7's
`{"op": "read", "sensor": "STOCK.SENSOR", "request": ID}` line:
`{"op": "read", "sensor": "orders.main", "request": ID, "with": {"queue": "orders"}}`. That is only an addition, but
it is a change to the protocol. The GAPS entry's statement that the protocol stays as it is holds for the other six
questions and not for this one.

**What a daemon written to today's protocol does with the extra key**, read from the docs' own daemons:

- `count-files.sh` (DAEMONS.md shape 1): it matches the text `"op": "read"` and cuts the request id out of the
  text after the last `"request": "` (`DAEMONS.md:84-88`). It ignores `with`. One case breaks it: a `with` value
  written after `request` that itself contains the text `"request": "`.
- `queues.py` (shape 2): it parses the line as JSON and reads only `op`, `sensor` and `request`
  (`DAEMONS.md:189-194`, `173`, `181`), so it ignores `with`. It also gains nothing from it until it is changed to
  read `m["with"]["queue"]`.
- `tail-errors.py`, `disk-used.sh` (shape 3) and the skill's `push-inbox.py`: push daemons. They look only for
  `stop` (`DAEMONS.md:306-308`, `329`; `daemons.md:272-274`). A read line, with or without `with`, is not acted on.
- `worker.py` and `worker.sh` (shape 4, `shell-jobs`) and the skill's `worker.py`: block daemons. They act on
  `item`, `cancel` and `stop` (`DAEMONS.md:499-506`, `544-561`; `daemons.md:346-354`). They are never sent a read.
- The skill's `disk-free.py` and `service.py`: JSON, reading `op`, `sensor` and `request` (`daemons.md:127-131`,
  `121`; `203-206`, `189`, `195`). Both ignore `with`. `disk-free.py` ignores the sensor's name too.
- Outside the docs, ticket-factory's shared reader (`examples/ticket-factory/bin/daemon.py:95-98`) parses JSON and
  reads only `op` before handing the line on: it ignores `with`.

So no daemon in the docs breaks on the extra key. The only hazard is the shell one's text matching, in the case
above.

**What changes.**

- Modules: `ergostat/spec/compile.py` (`with` in `SENSOR_KEYS`, read as a map of plain values, refused without
  `daemon:` and on a `push: true` sensor, which is never sent a read); `ergostat/spec/ir.py` (the `Sensor` gains it);
  `ergostat/daemons/work.py:136-137` (the read line). An estimate: 20 to 35 lines.
- SPEC: §6 (a row for `with`) and §9.7 (the read line, `docs/SPEC.md:2310`). DAEMONS.md's protocol table
  (`DAEMONS.md:51`), shape 2 and the migration's step 4; the skill's protocol and rule 11.
- Protocol: gains the optional `with` field of the read line, and nothing else.
- Old form: nothing becomes old. `with:` is optional, a sensor without it is sent the line it is sent today, and a
  daemon that ignores it goes on reading the name. No break.

**Recommendation.** Adopt `with:`. It is the one change here that only adds: old models and old daemons go on as
they are (above), and names stop carrying configuration. Its cost is one optional field in the protocol, and the
docs' shared examples rewritten to use it.

**Owner's decision:** open.

## Where shared daemons are declared

**Today.**

- A shared daemon is declared under the top-level `daemons:`, a section of its own (`ergostat/spec/load.py:19-20`,
  read by `config.py:62-64`), and named from a sensor or block as a string (`config.py:76-77`).
- `agents:` is the machine several blocks share (SPEC §10, `docs/SPEC.md:2400-2403`). An agent's keys are `kind`,
  `external`, `at-once`, `model`, `cost`, `host`, `description` (`compile.py:80`). They do not include `daemon`.
  `program` is one of its kinds (`compile.py:81`).
- A block names its agent with `agent:` (`compile.py:84`). A sensor has no `agent:` (`compile.py:65-66`).
- A block's capacity is "its `pool`, its agent's `at-once` and its daemon's `concurrency`, whichever binds"
  (`docs/SPEC.md:840-841`). An agent already carries a shared limit.

**The first alternative, a top-level `daemons:` beside `agents:`, is today's form.** Today's compiler accepts it
(the model below passes `check`), so the review drops it as a proposal. Keeping it is the "keep today's" choice.

<!-- today: where-top -->
```yaml
name: job-service
daemons:
  job-service: {run: python3 bin/queues.py jobs.db}
stocks:
  orders:
    unit: jobs
    sensor: {daemon: job-service, every: 1m}
```

**The second: a daemon as an agent's process.** The same model, with the daemon moved into an agent of kind
`program` and the sensor naming that agent. A syntax change: an agent has no `daemon` key and a sensor no `agent`
key today.

<!-- today: where-agent -->
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
```

<!-- proposed: where-agent, syntax: 'daemon' -->
```yaml
name: job-service

agents:
  job-service:
    kind: program
    daemon:
      run: python3 bin/queues.py jobs.db
      description: the job service's queues, one connection, readings batched
      restart: {max: 5, within: 10m, backoff: [2s, 5m]}

stocks:
  orders:
    unit: jobs
    description: order jobs waiting in the job service
    sensor: {agent: job-service, every: 1m}
  refunds:
    unit: jobs
    description: refund jobs waiting in the job service
    sensor: {agent: job-service, every: 1m}
```

What it gains: the process is an agent, so it shows its rung (`program`) as every agent does (CLAUDE.md, invariant
4). What it costs:

- Sensors would name agents, which they never do today. Agents fill roles, and a sensor is a role (invariant 3), so
  this is allowed. It is still a new statement in the model, and every reader of `Sensor.daemon` would read it
  through the agent.
- An agent's `at-once` and its daemon's `concurrency` would be two limits on one agent. They would have to be
  merged, or one forbidden (see *The knobs*).
- A block daemon written inline (`daemon: {run: ...}` on the block) still has no agent. Either it stays inline, or
  every block daemon gets an agent of its own.

**What changes.**

- Modules: `ergostat/spec/compile.py` (`AGENT_KEYS` at line 80, `SENSOR_KEYS`, the sensor kinds at line 485, the
  agents section at lines 988-999); `ergostat/daemons/config.py` (`section`: daemons read from agents, and `agent:`
  on a sensor resolved to them); `ergostat/daemons/supervise.py` only by name (`users`, lines 323-326). An estimate:
  60 to 100 lines, most of it in compile.py and config.py.
- SPEC: §6, §9.7, §10 (an agent's keys), and the capacity sentence at `docs/SPEC.md:840-841`.
- Protocol: nothing.
- Old form: `daemons:` could stay accepted and be reported as an old spelling (as `variables:` is).

**Recommendation.** Keep today's top-level `daemons:`. Moving it into `agents:` gives sensors agents and gives one
agent two limits, `at-once` and `concurrency`. Both are larger changes than the gain, which is a rung shown. That
rung could be shown from today's YAML instead: a daemon is a program, whatever section declares it.

**Owner's decision:** open.

## The names of inline daemons

**Today.**

- A daemon written as a map on a block is named `block.NAME`; on a sensor, `sensor.STOCK.SENSOR`
  (`ergostat/daemons/config.py:66` and `68`, given at `config.py:73-75`).
- A top-level daemon's name must match `^[a-z][a-z0-9-]*$` (`ergostat/spec/ir.py:17`, checked at `compile.py:810`).
  It has no dot, so it can never be the same as a derived name.
- Where the name is used:
  - the users listed when a daemon is given up (`ergostat/daemons/supervise.py:323-326`, recorded at
    `supervise.py:306-308`);
  - its log, `logs/daemon-NAME.log` (`supervise.py:239`, `ergostat/runner.py:63-66`), e.g.
    `logs/daemon-sensor.inbox.main.log`;
  - the item of its events, `ergostat.daemon.started`, `restarted` and `failed` (`supervise.py:260`, `306`, `312`);
  - its key in `daemons.json` and on the Agents page (`supervise.py:331-339`);
  - a warm one's processes, `NAME#1` ... `NAME#N` (`supervise.py:82`);
  - and `ergostat block NAME --restart` (`ergostat/cli/spec_cmds.py:175-183`). A block's name finds the block's
    daemon. Otherwise NAME must be a daemon's name, so a sensor's own daemon is revived as
    `ergostat block sensor.inbox.main --restart`, a name the owner never wrote. The supervisor's own message names
    it that way too (`supervise.py:309-310`).

The pair is the docs' shape 1 (`docs/DAEMONS.md:95-105`), with a name the owner chose. A syntax change: `name` is
not in `KEYS` today.

<!-- today: names -->
```yaml
name: inbox
stocks:
  inbox:
    unit: files
    description: files waiting in inbox/
    sensor:
      daemon: {run: sh bin/count-files.sh inbox}
      every: 10s
```

<!-- proposed: names, syntax: 'name' -->
```yaml
name: inbox
stocks:
  inbox:
    unit: files
    description: files waiting in inbox/
    sensor:
      daemon: {name: inbox-count, run: sh bin/count-files.sh inbox}
      every: 10s
```

Another alternative, not paired because the YAML would not change: derive shorter names (`inbox.main`, the
sensor's own id, with no `sensor.` prefix). That renames every log file and the item of every daemon event written
from then on. The record keeps the old names (events are never edited, invariant 10), so a daemon's history would
be split at the change.

**What changes.**

- Modules: `ergostat/daemons/config.py` (`name` in `KEYS`, used in place of the derived name in `section`, and
  refused when it is a top-level daemon's or another inline one's). Nothing in `supervise.py` changes: it reads
  `Daemon.name`. A renamed daemon is a changed definition, drained and started afresh (`supervise.py:86-91`). An
  estimate: 10 to 20 lines.
- SPEC: §9.7 (the inline daemon's name). DAEMONS.md's settings (`DAEMONS.md:594-596`).
- Protocol: nothing.
- Old form: nothing becomes old. `name:` is optional and the derived name stays the default. No break.

**Recommendation.** Keep today's. Derived names cannot collide (they have a dot, and a written name cannot). A
block's own daemon is restarted by the block's name already. Only a sensor's own daemon needs its derived name
typed, and that name is printed by the supervisor when it gives up. If the owner finds typing it a burden, `name:`
is small and additive.

**Owner's decision:** open.

## Push

**Today.**

- `push` is a sensor key (`compile.py:65`), true only when written `true` (`compile.py:547`).
- It is an error without a sensor `daemon:`: "push: a daemon's sensor (daemon:, and push: true when it sends readings
  itself)" (`ergostat/daemons/config.py:90-92`).
- It is per sensor, not per daemon. The supervisor keeps a map from (daemon, sensor) to push sensors
  (`supervise.py:98`). A pushed line is taken only for a sensor in that map (`work.py:140-143`), and at most once a
  second per sensor (`work.py:18`, `145`). One daemon may push for some sensors and be asked by others.

**The first alternative, `push: true` beside `daemon:` on the sensor, is today's form.** The review drops it as a
proposal. The docs' shape 3 (`docs/DAEMONS.md:334-351`) is written that way and passes `check`:

<!-- today: push -->
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

**The second: said once by the daemon**, which then pushes for every sensor that names it. A syntax change: `push` is
not in a daemon's `KEYS` (`config.py:8`).

<!-- proposed: push, syntax: 'push' -->
```yaml
name: pushed

stocks:
  errors:
    unit: lines
    cumulative: true
    description: lines with ERROR in app.log, so far
    sensor:
      daemon: {run: python3 bin/tail-errors.py app.log errors.main, push: true}
  disk-used:
    unit: percent
    description: how full the disk holding this folder is
    sensor:
      daemon: {run: sh bin/disk-used.sh disk-used.main, push: true}
```

For a sensor's own daemon, as here, it only moves the key. For a shared daemon it is said once instead of on every
sensor. But it removes what today allows: one daemon that pushes for some sensors and answers reads for others.

**What changes.**

- Modules: `ergostat/daemons/config.py` (`push` in `KEYS` and on `Daemon`, and the sensor's `push` set from its
  daemon); `ergostat/spec/ir.py` (`Daemon`); `ergostat/daemons/supervise.py:98` (the push map, built from the
  daemon). An estimate: 15 to 25 lines.
- SPEC: §6 (the `push` row, `docs/SPEC.md:1223`), §9.7 (its example, `docs/SPEC.md:2296`).
- Protocol: nothing. The pushed line `{"reading": V, "sensor": "STOCK.SENSOR"}` stays as it is.
- Old form: the sensor's `push: true` could stay accepted and be reported as an old spelling. A shared daemon with
  push sensors and asked sensors together could not be written in the new form, so that model would be a hard
  break. None of the docs' models or the examples has one today.

**Recommendation.** Keep today's. Per sensor is the finer statement, and it costs one line per push sensor. The
places that would be rewritten are few (the table), so the saving is small too.

**Owner's decision:** open.

## The knobs

**Today.**

- `concurrency`: a whole number, **floor 1, default 10, and no maximum** for a daemon that is not warm
  (`ergostat/daemons/config.py:52`, `whole(c, m, "concurrency", 1, 10, ...)`; `whole` at `config.py:14-19` checks
  only the floor). Only **warm** daemons are capped: `WARM_MOST` **32** processes per warm daemon (`config.py:10`,
  checked at `config.py:48-51`) and `WARM_ALL` **64** warm processes in all (`config.py:11`, checked at
  `config.py:93-94`). The cap is also held at run time: a warm process waits to start while 64 run, are being
  started, drain or are being killed (`supervise.py:94`, `114`, `124-129`, `174`).
- **What a non-warm `concurrency` multiplies: engine threads, not processes.** A daemon that is not warm is one
  process (`supervise.py:79-83`: only a warm one is expanded to `NAME#1` ... `NAME#N`) with two threads of the
  engine's own, a writer and a reader (`ergostat/daemons/proc.py:105-106`). Its `concurrency` bounds the runs that
  process holds at once (`work.py:70-72`) and the dispatcher's room for it (`work.py:85-89`, used at
  `ergostat/leases/dispatch.py:164-165`). Every run the dispatcher takes starts **a thread** (`dispatch.py:223`).
  That thread waits for the daemon's `done` (`ergostat/spec/engine.py:939`, `work.py:26-30`: "waited for on the
  run's own thread"). So `concurrency: N` lets N engine threads wait on one daemon at once, as far as its blocks'
  pools allow: the room is `min(pool - held, free - handing)` (`dispatch.py:163-165`). The pool has a floor of 1 and
  **no maximum either** (`ergostat/leases/compile.py:85-90`). `pool: 5000` with `concurrency: 5000` would ask for
  5,000 engine threads, and the daemon's own program would get 5,000 runs at once. The test
  `test_the_knobs_section_states_the_ceilings_the_code_has` shows `concurrency: 100000` accepted by `check`. This
  is lesson-4's shape. **It is recorded here and in GAPS, not fixed on this branch.**
- `concurrency` and `pool` count different things. `pool` is a block's: the items that block holds at once
  (`dispatch.py:163`). `concurrency` is the daemon's, shared by every block that uses it (`work.py:85-89`; SPEC
  §9.7, `docs/SPEC.md:2339-2340`). It does not count readings: a reading is asked (`work.py:136`), not held as a run
  (`work.py:49`). SPEC says "at most the smaller of pool and the daemon's concurrency at once"
  (`docs/SPEC.md:2301`). That is true for a daemon serving one block. For several, the binding limit is each
  block's pool and the daemon's concurrency together. They are two limits on one thing only when one block uses the
  daemon.
- `restart`: its keys are `RESTART`: `max`, `within`, `backoff` (`config.py:9`). `backoff` defaults to `[1s, 2m]`,
  **a two-item list** (`config.py:33`), and must be two durations (`config.py:36-42`). Nothing checks that the
  first is no more than the second. The wait is `min(first × 2^(n-1), most)` (`supervise.py:288`). `max`: floor 0,
  default 5 (`config.py:53`). `within`: default 10 minutes (`config.py:54`).
- `stdin-timeout`: default 10 s (`config.py:55`; `ergostat/spec/ir.py:716`). A write to the daemon's standard input
  waiting longer, or its queue full, restarts it with an alarm (`supervise.py:204-205`).
- `heartbeat`: **defaults to never**. It is read with no default (`config.py:53`, `c.duration(m, "heartbeat",
  what)`), `None` meaning never (`ir.py:712`), and a daemon is restarted for silence only when it is set
  (`supervise.py:206`).

Four pairs, one per knob.

**`concurrency` merged into `pool`.** A semantics change, from SPEC's own `builder` (`docs/SPEC.md:2297-2302`). The
proposed model drops the daemon's `concurrency`, and the daemon's room becomes the sum of its blocks' pools. Today
that same text is accepted, and the daemon's room is the default 10 (`config.py:52`, `work.py:88`), so the block
runs at most 10 at once where it said `pool: 20`.

<!-- today: knobs-pool -->
```yaml
name: builder
projections:
  ticket:
    query: key.startswith('ticket/')
    fields:
      state: {values: [ready, done]}
    events:
      ticket-opened:
        when: type == 'ticket.opened'
        state: set('ready')
      ticket-done:
        when: type == 'ticket.done'
        state: set('done')
      other:
        when: true
        '...': data
blocks:
  builder:
    type: program
    takes: {projection: ticket, at: ready, to: [done]}
    pool: 20
    daemon: {run: ./builder.py, concurrency: 20, heartbeat: 30s}
```

<!-- proposed: knobs-pool, semantics -->
```yaml
name: builder
projections:
  ticket:
    query: key.startswith('ticket/')
    fields:
      state: {values: [ready, done]}
    events:
      ticket-opened:
        when: type == 'ticket.opened'
        state: set('ready')
      ticket-done:
        when: type == 'ticket.done'
        state: set('done')
      other:
        when: true
        '...': data
blocks:
  builder:
    type: program
    takes: {projection: ticket, at: ready, to: [done]}
    pool: 20
    daemon: {run: ./builder.py, heartbeat: 30s}
```

The examples' largest shared daemon already follows that rule by hand. ticket-factory's `steps` has
`concurrency: 27`, "the nine steps' pools (3 each)" (`examples/ticket-factory/ergostat.yaml:75`). The other way to
merge them, `concurrency` alone with no `pool` on a daemon's block, loses each block's own limit within a shared
daemon.

**Where the hard maximum would live, for each merge.** Today neither number has one, so a merge must add one:

- *The room is the sum of the pools*: the ceiling goes on `pool`. At config time in `ergostat/leases/compile.py`
  `pool()` (a most, beside its floor of 1 at line 87). At run time in the dispatcher's tick, where the room is
  worked out and each run's thread is started (`dispatch.py:163-165`, `223`), counting runs still going and those
  being handed over (`dispatch.py:140-143`). The same ceiling would cap a sum of pools: config time in
  `config.py:section`, over every block naming the daemon.
- *`concurrency` alone*: the ceiling goes in `config.py:52` (a most in `whole`, which has none today) and at run time
  in `work.py:70-72` and `85-89` (`_room`, `free`), counting runs held by a process being drained
  (`supervise.py:64`, `148-156`).
- Either way the ceiling is a number of engine threads, so it belongs beside `WARM_ALL` (64) in kind: one for the
  model as a whole, not only per daemon.

**`restart.backoff` as `backoff:` and `max-backoff:`.** A syntax change, from the job service's `restart:`
(`docs/DAEMONS.md:207`). `max-backoff` is no key of `restart` today (`config.py:9`), and a single duration is
refused as `backoff`.

<!-- today: knobs-backoff -->
```yaml
name: job-service
daemons:
  job-service:
    run: python3 bin/queues.py jobs.db
    restart: {max: 5, within: 10m, backoff: [2s, 5m]}
stocks:
  orders:
    unit: jobs
    sensor: {daemon: job-service, every: 1m}
```

<!-- proposed: knobs-backoff, syntax: 'max-backoff' -->
```yaml
name: job-service
daemons:
  job-service:
    run: python3 bin/queues.py jobs.db
    restart: {max: 5, within: 10m, backoff: 2s, max-backoff: 5m}
stocks:
  orders:
    unit: jobs
    sensor: {daemon: job-service, every: 1m}
```

Its floor and ceiling (lesson-4): `backoff` above 0 and `max-backoff` at least `backoff`, both checked in
`config.py` at config time. A ceiling on `max-backoff` (an hour, say) would keep a daemon from waiting a day to
come back. At run time `supervise.py:288` already takes the smaller of the doubled wait and the most.

**`stdin-timeout` renamed.** A syntax change, from SPEC §9.7's `probes` (`docs/SPEC.md:2283-2293`).
`input-timeout` is one candidate. It is not a key today.

<!-- today: knobs-stdin -->
```yaml
name: probes
daemons:
  probes:
    run: python3 probes.py
    concurrency: 50
    heartbeat: 30s
    stdin-timeout: 10s
stocks:
  queue-depth:
    unit: jobs
    sensor: {daemon: probes, every: 3m}
```

<!-- proposed: knobs-stdin, syntax: 'input-timeout' -->
```yaml
name: probes
daemons:
  probes:
    run: python3 probes.py
    concurrency: 50
    heartbeat: 30s
    input-timeout: 10s
stocks:
  queue-depth:
    unit: jobs
    sensor: {daemon: probes, every: 3m}
```

**A heartbeat on by default for block daemons.** A semantics change, from the skill's `t-block`
(`docs/skills/ergostat-author/daemons.md:357-380`). The proposed model leaves out `heartbeat: 30s` because it would
be the default. Today the same text means no heartbeat at all (`config.py:53`, `supervise.py:206`).

<!-- today: knobs-heartbeat -->
```yaml
name: t-block
projections:
  job:
    query: key.startswith('job/')
    fields:
      state: {values: [ready, done]}
    events:
      job-opened:
        when: type == 'job.opened'
        state: set('ready')
      job-done:
        when: type == 'job.done'
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

<!-- proposed: knobs-heartbeat, semantics -->
```yaml
name: t-block
projections:
  job:
    query: key.startswith('job/')
    fields:
      state: {values: [ready, done]}
    events:
      job-opened:
        when: type == 'job.opened'
        state: set('ready')
      job-done:
        when: type == 'job.done'
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
    daemon: {run: python3 bin/worker.py, concurrency: 8}
```

A default heartbeat **breaks daemons that do not send one**. The docs' `shell-jobs` worker
(`docs/DAEMONS.md:587`, `daemon: {run: sh bin/worker.sh, concurrency: 1}`) prints nothing while it waits for a job
(`DAEMONS.md:537-563`). With a 30 s default it would be restarted every 30 s while idle, and given up after
`max` restarts within `within`. Its floor and ceiling, if adopted: no less than a second (the supervisor looks
every 0.2 s, `supervise.py:26`) and no more than a day, checked in `config.py` at config time.

**What changes.**

- *Merging `concurrency` and `pool`*: `ergostat/daemons/config.py`, `ergostat/daemons/work.py` (`free`,
  `_room`), `ergostat/leases/dispatch.py` (the room), `ergostat/leases/compile.py` (`pool`'s ceiling). SPEC §9.5
  (pool), §9.7 (`docs/SPEC.md:2301`, `2339-2340`), and the capacity sentence (`docs/SPEC.md:840-841`). An estimate:
  30 to 60 lines. Protocol: nothing. Old form: a written `concurrency` could be accepted and reported. A model that
  relies on the daemon's default 10 would change behaviour without changing text, and `check` cannot report that.
- *`backoff` and `max-backoff`*: `config.py` (`RESTART`, the parse at lines 33-42). SPEC §9.7, DAEMONS.md's settings
  (`DAEMONS.md:603`). An estimate: 10 to 15 lines. Protocol: nothing. Old form: the list can stay accepted and be
  reported.
- *`stdin-timeout` renamed*: `config.py` (`KEYS`, line 55). SPEC §9.7, DAEMONS.md (`DAEMONS.md:604`), the skill's
  rule 1. An estimate: 5 lines. Protocol: nothing. Old form: accepted and reported.
- *Heartbeat by default*: `config.py:53` (a default for block daemons only, which `one` does not know today: it
  would need to be told whether a block uses the daemon). SPEC §9.7, DAEMONS.md's table (`DAEMONS.md:602`) and the
  skill's rule 6. An estimate: 10 lines. Protocol: nothing. Old form: no text changes, so `check` has nothing to
  report. Every block daemon that sends no heartbeat breaks at run time: a hard break.

**Recommendation.**

- Keep `concurrency` and `pool` apart. They count different things once a daemon serves two blocks, and the only
  merge that keeps each block's limit changes the meaning of models that rely on the default. But **give both a
  hard maximum** (lesson-4), at config time and at run time, whatever the owner decides about the YAML. That is
  the follow-up gap *Ceilings on a daemon's concurrency and a block's pool* below.
- Keep `backoff: [first, most]`. Two keys would read a little more plainly, but a list of two durations is
  already checked (`config.py:39-42`). Add the missing check that the first is no more than the most to the
  ceilings gap.
- Keep `stdin-timeout`. It names what is watched (the daemon's standard input), and a rename changes words in four
  documents for no change of meaning.
- Keep the heartbeat off by default. On by default restarts the docs' own shell worker every 30 s.

**Owner's decision:** open.

## The word

**Today.** "daemon" is the word in:

- the YAML: the section `daemons:` (`ergostat/spec/load.py:20`), the sensor key and kind `daemon` (`compile.py:65`,
  `485`), the program block's key (`compile.py:87`), and the error messages (`config.py:25`, `79-80`, `84`, `88`,
  `91`);
- what ergostat writes: the events `ergostat.daemon.started`, `restarted` and `failed` (`supervise.py:260`, `306`,
  `312`), `daemon.restart.requested` (`ergostat/spec/engine.py:61`), the alarm class `alarm:daemon:NAME`
  (`supervise.py:307`), `logs/daemon-NAME.log` (`supervise.py:239`), `<state>/daemons.json` (`supervise.py:348`),
  and a daemon's runs' `daemon` field (SPEC §9.7, `docs/SPEC.md:2329`);
- the code's package, `ergostat/daemons/`.

Only the first group is the YAML. The record's event types are another decision. Events are never edited
(invariant 10), so a renamed type splits every daemon's history at the rename, and each reader of the record would
read both names.

Three pairs, one per word, each from the skill's `t-shared` (`docs/skills/ergostat-author/daemons.md:213-230`).
Each is a syntax change: the new section is unknown to `check` today (`load.py:188`).

<!-- today: word-runner -->
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

`runner`:

<!-- proposed: word-runner, syntax: 'runners' -->
```yaml
name: t-shared
runners:
  gauges:
    run: python3 bin/service.py gauges.db
    description: the gauge service, one session for all its sensors
    restart: {max: 5, within: 10m, backoff: [2s, 5m]}
stocks:
  backlog:
    unit: requests
    description: requests waiting in the service
    sensor: {runner: gauges, every: 1m}
  stuck:
    unit: requests
    description: requests the service holds as stuck
    sensor: {runner: gauges, every: 1m}
```

`server`:

<!-- today: word-server -->
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

<!-- proposed: word-server, syntax: 'servers' -->
```yaml
name: t-shared
servers:
  gauges:
    run: python3 bin/service.py gauges.db
    description: the gauge service, one session for all its sensors
    restart: {max: 5, within: 10m, backoff: [2s, 5m]}
stocks:
  backlog:
    unit: requests
    description: requests waiting in the service
    sensor: {server: gauges, every: 1m}
  stuck:
    unit: requests
    description: requests the service holds as stuck
    sensor: {server: gauges, every: 1m}
```

`keep-alive`:

<!-- today: word-keep-alive -->
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

<!-- proposed: word-keep-alive, syntax: 'keep-alive' -->
```yaml
name: t-shared
keep-alive:
  gauges:
    run: python3 bin/service.py gauges.db
    description: the gauge service, one session for all its sensors
    restart: {max: 5, within: 10m, backoff: [2s, 5m]}
stocks:
  backlog:
    unit: requests
    description: requests waiting in the service
    sensor: {keep-alive: gauges, every: 1m}
  stuck:
    unit: requests
    description: requests the service holds as stuck
    sensor: {keep-alive: gauges, every: 1m}
```

How each reads:

- `runner`: SPEC §9.7's own title is "Daemons: long-lived runners" (`docs/SPEC.md:2275`). But `runner:` would sit
  beside `run:` (a sensor's kind, a block's command, the daemon's own command), and every `run:` command is a
  runner too in plain words. `ergostat/runner.py` is already the name of something else in the code.
- `server`: familiar, but a server is commonly taken to listen on a port. This one reads its standard input, and is
  started and stopped by ergostat.
- `keep-alive`: says what ergostat does to it, not what it is. It is HTTP's word for a kept connection. Its plural,
  for the section, has no good form, which is why the pair uses `keep-alive:` for both.

**What changes.** All of it is renaming: `ergostat/spec/load.py` (`SECTIONS`), `ergostat/spec/compile.py`
(`SENSOR_KEYS`, the kinds, the program keys, the `run` requirement at line 1352), `ergostat/daemons/config.py`
(`section` and its messages). The rest of the code keeps its names. An estimate: 15 to 30 lines, most of it the
old spellings read and reported. SPEC §6, §9 and §9.7, DAEMONS.md (every shape, the settings and its title), the
skill (all of it), and every example that writes one (the table). Protocol: nothing. Old form: `daemons:` and
`daemon:` can stay accepted and be reported, as `variables:` is (`compile.py:147-154`). Without that it is a hard
break for every model that uses a daemon.

**Recommendation.** Keep "daemon". The rename is the largest rewrite of the seven (the table), and each candidate
has a reading of its own that misleads. The docs already open by saying what one is: "one long-lived process
instead of a process each time" (`docs/DAEMONS.md:1`). If the owner wants the jargon gone anyway, `server` misleads
least of the three, and the old spelling should stay accepted.

**Owner's decision:** open.

## Places a change would rewrite

For each change, how many YAML places hold a line that the change would rewrite. A **place** is one fenced `yaml`
block in `docs/DAEMONS.md`, `docs/skills/ergostat-author/daemons.md` or `docs/SPEC.md`, or one `*.yaml` file
under `examples/`. A place counts once however many of its lines match. The regular expression is matched line by
line. The counts were taken at commit `f7b93be`, the main this branch was made from and merged with. While this
branch is built, `tests/test_daemon_yaml_review.py` recounts them from the tree and compares; once it is merged, it
recounts them at that commit, so another branch's new example does not fail it, and it checks that each expression
still matches somewhere in the tree.

| What changes | Expression | Places |
|---|---|---|
| A modifier instead of a kind | `daemon:\s*(\{\|$)` | 12 |
| Per-sensor arguments | `daemon: [a-z][\w-]*\s*([,}#]\|$)` | 14 |
| Where shared daemons are declared: top-level daemons: | `^daemons:` | 6 |
| Where shared daemons are declared: an agent's process | `^daemons:\|daemon: [a-z][\w-]*\s*([,}#]\|$)` | 15 |
| The names of inline daemons | `daemon:\s*(\{\|$)` | 12 |
| Push | `push: true` | 3 |
| The knobs: concurrency and pool | `concurrency:` | 7 |
| The knobs: restart.backoff | `backoff:` | 3 |
| The knobs: stdin-timeout | `stdin-timeout:` | 1 |
| The knobs: heartbeat on by default | `heartbeat:` | 6 |
| The word: runner | `daemons?:` | 25 |
| The word: server | `daemons?:` | 25 |
| The word: keep-alive | `daemons?:` | 25 |

How to read the rows:

- *A modifier* and *the names*: every daemon written inline, as a map (`daemon: {` or `daemon:` with its keys
  below). Those are the places a modifier rewrites, and the places with a derived name.
- *Per-sensor arguments*: every place that names a shared daemon. A sensor among them would gain `with:`; a block
  naming one would not change, so this is an upper bound.
- *Top-level daemons:*: the places that declare one. Keeping today's form rewrites none of them. *An agent's
  process* rewrites each, and each name of one.
- *Heartbeat on by default*: the places that set a heartbeat (it could be left out). The places that would break
  are block daemons that send none, which a line cannot show (see *The knobs*).
- *The word*: every line with `daemon:` or `daemons:`, the same for each of the three words.

## Follow-up gaps

Each is sized to become one branch once the owner chooses. None is in GAPS as a gap of its own: they wait for the
owner. Sizes are estimates: lines of code outside `tests/` and `docs/`.

1. **Ceilings on a daemon's concurrency and a block's pool** (recommended; depends on nothing). A hard maximum on a
   non-warm daemon's `concurrency` and on `pool`, each and summed per daemon, at config time and at run time
   counting runs being handed over and drained (lesson-4). Also that `restart.backoff`'s first is no more than its
   most. No YAML key changes, but models above the ceiling would be refused. Estimate: 30 to 50 lines.
2. **Per-sensor `with:`, sent in the read line** (recommended; depends on nothing). A sensor's `with:` map, sent as
   `with` in `{"op": "read", ...}`. SPEC §6 and §9.7, DAEMONS.md's shape 2 and the skill's shared template rewritten
   to read it. Estimate: 20 to 35 lines.
3. **An optional `name:` for an inline daemon** (only if the owner chooses it; depends on nothing). Estimate: 10 to
   20 lines.
4. **A daemon's knobs renamed** (`max-backoff:`, `stdin-timeout`'s new name), old spellings accepted and reported
   (only if the owner chooses; after 1, which touches the same parse). Estimate: 15 to 25 lines.
5. **The word renamed in the YAML**, `daemons:` and `daemon:` accepted and reported as old spellings, the docs and
   examples rewritten (only if the owner chooses; after 2, 3 and 4, so that the docs are rewritten once). Estimate:
   15 to 30 lines, and every place in the table's *The word* rows.
6. **The structure: a modifier, push on the daemon, or a daemon as an agent's process** (each only if the owner
   chooses; one branch each; after 5 if the word changes too, so that the new keys are written in the new word).
   Estimates: 30 to 50, 15 to 25, and 60 to 100 lines.
