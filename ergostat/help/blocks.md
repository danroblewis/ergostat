# Writing a sensor and a block

Two kinds of program take part in a loop, and each does one thing.

- A **sensor** measures one stock or one flow. Its command prints the reading.
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

Everything else it prints goes to its log. `ERGOSTAT_COMMAND` holds the amount too, for a shell
one-liner (`find tmp -mmin +60 -delete -print | head -n "$ERGOSTAT_COMMAND" | wc -l`).

A block nothing commands runs on its own schedule (`every: 5m`, `cron: "0 3 * * *"`): an open loop,
which `check` points out. One that a goal or another block commands runs while the command holds,
once per fresh reading, and never twice at once.

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
(or `record_event` over MCP). A kind of item gives it states, and a stock can count them:

```yaml
items:
  ticket:
    id: ticket/*
    states: [open, doing, done]
    on:
      ticket.started: doing
      ticket.closed: done
stocks:
  backlog:
    unit: tickets
    sensor:
      items: ticket
      state: open
      every: 30s
```

`ergostat item` lists them by kind and state; `ergostat item ticket/12` shows one, how it moved,
and every event about it. The page's Items tab shows the same.
