# Writing a sensor and a block

Two kinds of program take part in a loop, and each does one thing.

- A **sensor** measures one stock, flow or auxiliary. Its command prints the reading.
- A **block** acts. Its command gets what it was asked to do on standard input, does it, and prints
  what it moved.

Deciding when to act is not in either: it is the goal and the block's controller, written in
`ergostat.yaml`, run by ergostat. A program that both measures and decides ("if the disk is over
80%, clean") is split in two: the measuring becomes a sensor, the threshold becomes a goal, and
the cleaning becomes a block.

## A sensor

Any command that prints a number:

```yaml
stocks:
  logs:
    unit: MB
    sensor:
      run: du -sm /var/log/app | cut -f1
      every: 1m
```

It may print `{"value": 412}` instead, or a sentence with `parse: "using (\\d+) MB"`. On a flow, the
reading is a rate per hour. A reading a person takes is `manual: true`, recorded with
`ergostat sensor logs.main --read 412`. A reading that lives in Prometheus is a query:

```yaml
    sensor:
      query:
        source: prom
        promql: 'sum(queue_depth{app="checkout"})'
      every: 30s
```

Many sensors reading one service on short schedules, or a block taking many items, can be served by one
long-lived program instead of a process each: `daemon:` in place of `run:` (SPEC §9.7; how to write one, in
ergostat's repository: docs/DAEMONS.md).

## A block

```yaml
blocks:
  rotate:
    type: program
    goal: logs-small          # runs while the goal is off ...
    until: "<= 300"           # ... until the logs are back to 300 MB
    run: ./rotate.sh
    out: flow.rotated
    max: 200                  # the most one run may move: its command is clamped to it
```

Its standard input is JSON:

```json
{"block": "rotate", "type": "program", "trigger": "command",
 "command": {"amount": 1, "from": "keep-logs-small"},
 "inputs": {},
 "goals": {"logs-small": {"hold": "<= 500", "value": 612, "error": -112, "status": "off"}},
 "outputs": {"out": ["flow.rotated"]}}
```

and it prints what it moved, in the stock's unit: a number (`412`), or JSON lines when it has more
to say:

```
{"out": "flow.rotated", "moved": 412}
{"decision": "rotated app.log: 612 MB", "why": "over the goal by 112"}
{"event": "logs.rotated", "item": "log/app.log"}
```

Each line takes effect when it is printed, not when the run ends: a long run's events are recorded and
folded into their items as it goes (flush each line), and each renews the lease the run holds. A bare
number is the exception: it counts when the run ends well. `ergostat help spec`, section 9.1.

A block that steps a setting (an integral controller: the quality up by the error) moves a
`two-way` flow into the setting's stock, and prints the step, which may be negative:
`{"out": "flow.quality-steps", "moved": -2.5}`. The setting is a stock because it keeps its value
between steps; only a value the block states whole each run, from what it reads now, is an
auxiliary it sets (`{"out": "auxiliary.mix", "value": 0.3}`).

Any block may also propose a change to the model, one line each:
`{"propose": {"kind": "parameter", "parts": [...], "edit": {"file": "x.yaml", "replace": "...", "with":
"..."}, "reasons": [{"says": "...", "evidence": "fit:stock.queue.um"}], "confidence": 0.6}}`. ergostat checks it
(compiles, checks, replays and refits it; every reason needs evidence it can check) and puts it in the review
queue as the block's candidate, or says why not (`ergostat improve`). `ergostat help spec`, section 12e.

And any block may say what it did, one line each: `{"claim": {"says": "tests pass", "about": "ticket/12"}}`
(`about`: an item, `stock.x`, a file, a commit; optional `check`: `tests`, `changed`, `state`, `exit`, `level`).
ergostat checks each claim itself after the run (it runs the project's declared test command, reads git, folds
the item, reads the exit code or the part's reading) and records it as verified, contradicted or unchecked
(`ergostat claims`; Items → `ergostat.claim`). A contradicted claim is a finding against the block, and lowers its
trust (`ergostat.trust.contradicted@BLOCK`). `ergostat help spec`, section 12g.

The owner's messages that waited for a block's run (`ergostat message "that review can wait"`, routed to the work it
concerns) come in its input, under `messages`: each `{"id", "text", "by", "sent", "items"}`. Take them into the work,
and answer one with `{"answer": {"message": ID, "says": "..."}}`. A Claude Code session run through `ergostat session
ROLE --model M` (as the block's `run:`, `$ERGOSTAT_CMD session ...`) gets a message while it works, as its next turn.
`ergostat help messages`.

Everything else it prints goes to its log. `ERGOSTAT_COMMAND` holds the amount too, for a shell
one-liner (`find tmp -mmin +60 -delete -print | head -n "$ERGOSTAT_COMMAND" | wc -l`).
`ERGOSTAT_CMD` runs this ergostat on this project, so a block (or the AI agent it starts) can read
and record items while it works: `$ERGOSTAT_CMD item --projection ticket --state open --json`.

A block nothing commands runs on its own schedule (`every: 5m`, `cron: "0 3 * * *"`): an open loop,
which `check` points out. One that a goal or another block commands runs while the command holds,
once per fresh reading, and never twice at once.

## When a block works items, one at a time each

```yaml
  developer:
    type: ai
    takes: {projection: ticket, at: ready}   # a run for each ticket that reaches ready
    pool: 3                            # at most three at once
    run: $ERGOSTAT_CMD session developer --model sonnet
```

A pool can follow the model's state instead: `pool: {now: stock.developers, most: 4}` takes as many at once as the
stock (which needs a sensor) reads now, read at each dispatch and never more than `most`. Lower the stock and the
block drains: nothing running is stopped, and no new run starts until fewer are going. With no reading it starts
nothing new, and says so.

Each run holds a **lease** on its item: its input carries the item (`item`: id, projection, state, fields) and the lease
(`lease`: fence, ttl, expires, attempt); its environment `ERGOSTAT_ITEM` and `ERGOSTAT_LEASE` (the fencing number);
an event line that names no item is about it. Whatever the run records about the item (`$ERGOSTAT_CMD event --add`,
its session's transcript, `$ERGOSTAT_CMD lease --renew`) keeps the lease. When the run ends, the lease ends: ack if
the item moved on (to a state in `takes.to`, or any but where it was taken from), else it is given back, its attempt
counted. Say why with `{"nack": "why"}`, or put it off without counting: `{"nack": {"why": "...", "after": "4h",
"count": false}}`. A run silent past its TTL (an AI agent's: 40 minutes) loses its lease; whatever it says about the
item after is refused. After three attempts the item is a dead letter (`ergostat lease`). `ergostat help spec`,
section 9.5.

## When a block acts outward: gated actions

A push, a pull request, a ticket moved, a message posted: name each under `actions:` (a command template and its
gate, `auto`, `approve` or `deny`), list the ones a block may ask for in its `actions:`, and ask from its program:

```bash
out=$($ERGOSTAT_CMD act open-pr --arg title="Fix the login page" --arg body="$body")   # exit 0: ran, its output
# 1: it failed; 3: held for the owner (ask again later: the same request is the same action); 4: denied
```

ergostat runs it, not the program, once its gate lets it through; the owner answers a held one with `ergostat actions
ID --approve`. Your program can still run `gh` itself: the gate is a record and a checkpoint, not a wall, unless the
program runs without the credentials. `ergostat help spec`, section 12k.

## Try it

```bash
ergostat check                          # does it compile? file:line for every error
ergostat block rotate --now             # one run, at once: what it was given, what it said
ergostat block rotate --now --command 3 # as if its controller had asked for 3
ergostat explain rotate                 # what it is, in sentences
ergostat event --item rotate            # what it did
```

A run is recorded like any other (`agent.ran`, `valve.opened`), and its log is in the state
directory (`ergostat block rotate --now` prints where).

## When a person does the work

```yaml
  oncall:
    type: person
    goal: alerts-acked
    ask: ack or silence the alerts that are duplicates
    out: flow.acked
```

ergostat records `person.asked` when the goal goes off; the person answers with
`ergostat block oncall --done 4`. A person who has not answered within the hour is a finding.

## Items: what the work is made of

An event about an id with a `/` in it (`ticket/12`, `github/pull_request/4231`) is about an item.
A block reports one with `{"event": "ticket.started", "item": "ticket/12", "data": {"title": "..."}}`;
something outside reports with `ergostat event --add ticket.opened --item ticket/12 --data '{...}'`
(or `record_event` over MCP). A projection gives its items states, and a stock can count them:

```yaml
projections:
  ticket:
    match:
      key: ticket/*
    states: [open, doing, done]
    events:
      ticket.started:
        state: set('doing')
      ticket.closed:
        state: set('done')
        # lock): a patch testing /main as read, so a newer break refuses it and its move
    otherwise: rest
stocks:
  backlog:
    unit: tickets
    sensor:
      projection: ticket
      state: open
      every: 30s
```

Each event is a changeset to the item's fields. Its `data` replaces each field it names, unless
the projection folds that field otherwise (`fold: {notes: append, hours: sum, labels: union}`; also
`min`, `max`, `merge`, `first`). Or it carries a JSON Patch in place of `data`, applied whole or
refused with why (a refused patch does not move the item's state either): `{"event": "ticket.tagged", "item": "ticket/12", "patch": [{"op": "add", "path":
"/labels/-", "value": "bug"}]}` (`ergostat event --add ... --patch '[...]'`), or the whole document,
`"set": {...}`.

`ergostat item` lists them by projection and state; `ergostat item ticket/12` shows one, how it moved,
and every event about it; `--history` shows every change to each field, with the event that made
it. The page's Items tab shows the same.
