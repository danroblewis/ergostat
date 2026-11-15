# AI agents in ergostat

An AI agent is a block, `type: ai`, and it takes either of a block's two roles. Which one depends
on what its output is, not on how clever it is.

## As an actuator: it does the work

```yaml
blocks:
  docs-writer:
    type: ai
    goal: docs-current            # runs while too many pages are stale
    prompt: prompts/rewrite.md    # a file, or the text itself
    out: flow.rewritten
    max: 1                        # one page a run
    timeout: 10m
```

The prompt goes to `claude -p` (or the command in `$ERGOSTAT_AI`, or the block's own `run:`), with
the block's JSON input and how to answer. It is judged by what it did to the stocks (the stale
pages), not by what it says it did: the sensor on the stock is the truth.

## As a controller: it decides, and other blocks act

```yaml
  triage:
    type: ai
    prompt: prompts/triage.md
    in: [goal.few-tickets.error, goal.alerts-acked.error]
    out:
      tickets: block.ticket-worker
      alerts: block.alert-worker
    every: 2m
```

Its output is only commands (`{"out": "block.ticket-worker", "command": 3}`), never a change to
the world. What we want of it is good behaviour at the level of the loop: more error never brings
less action, no wild commands (put `max` on the blocks it drives, or a `limit` block between),
the same situation gets much the same decision, and it answers in time for the loop. Each of
these is in the record: `block.commanded` and `controller.decided` for every run.

Keep the blocks it commands programs you trust: an AI deciding and a program acting is the safe
split. The grant lives with the actuator.

## Then move it down the ladder

When its decisions are consistent (the same situation, the same command), a rule can take its
place: an `onoff`, a `proportional`, a `lookup`, an `expr`. Write the built-in block with the same
`in` and `out`; the goal and the actuators stay as they are. `ergostat loop GOAL` shows the
decisions grouped, with how often each came up.

The `docs-fresh` example has this shape with a stand-in for the AI, so it costs nothing to run.
