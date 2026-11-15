# Scripts that print sentences, used unchanged

Three ordinary shell scripts print lines for people ("cleanup done: removed 12 stale uploads"). Each block's `parse` takes the number from its own words; the sentence itself goes to the block's log.

```bash
cd examples/talking-scripts
ergostat check        # ok, with five findings (below)
ergostat run          # prints the page's address
ergostat event -n 40  # loop.off, block.commanded, valve.opened, loop.holding
ergostat run --stop
```

The log passes 80 KB within about a minute and a half; the report is rebuilt on the minute.

Things to look at:

- `rotate-log` names its goal (`goal: log-small`): ergostat runs `rotate.sh` while the log is too big, and reads "freed 132 KB" as what it moved.
- The block logs (`logs/<block>.log` in the state directory) keep each sentence next to its run.
- The stand-in app moves two flows, so it speaks JSON lines instead: `{"out": "flow.logging", "moved": 3}`.
- The cleanup and the report are timers, not feedback: `check` reports their goals (`few-uploads`,
  `report-fresh`) as **missing feedback** and the blocks as **acting on their own**, which is true and meant. The app acts on its own too: it is the load.
- `clean.sh` caps itself at 25 a run. The block has no `max:`: a block's `max` limits the command it is given, and nothing commands this one.

Shows: `parse` on blocks, a goal-driven script, open loops, a declared disturbance rate.
