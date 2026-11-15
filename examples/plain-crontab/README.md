# Two cron one-liners, no scripts

Jobs as they would sit in a crontab (`find ... -delete -print | wc -l`, `mv` and `wc -c`), each printing a bare number: a sensor its reading, a job what it moved. No JSON, no wrapper scripts.

```bash
cd examples/plain-crontab
ergostat check        # ok, with four findings (below)
ergostat run          # prints the page's address
ergostat event -n 40  # after a minute: loop.off, block.commanded, valve.opened, loop.holding
ergostat run --stop
```

The log fills past 80 KB about a minute after the start; the pruner fires on the minute (`cron: "* * * * *"`), so give it two minutes.

Things to look at:

- `rotate-log` names its goal (`goal: log-under-64k`): the threshold lives in the goal, not in the one-liner, and ergostat runs the job only while the log is too big.
- `prune-old` deletes by age whatever the count: a timer, not feedback. Its goal `scratch-under-100` is only watched, so `check` reports it as **missing feedback** and the pruner as **acting on its own**. Both are true and meant: that is what a plain crontab line is. The status says the loop cannot close.
- `app-scratch` and `app-log` stand in for the app: they act on their own too (the load), one flow each, so they can print bare numbers.

Shows: bare numbers, cron, an open loop next to a closed one.

To see a job too slow for its load: add `every: 2m` to `rotate-log`, as if it were still a
`*/2 * * * *` crontab line. It can rotate at most every two minutes, the log outgrows it between
runs, and `log-under-64k` spends much of its time off.
