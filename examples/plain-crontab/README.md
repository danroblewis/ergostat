# Two cron one-liners, no scripts

Jobs as they would sit in a crontab (`find ... -delete | wc -l`, `du | cut -f1`). The pruner deletes by age whatever the count, so its controller is an open loop: a timer that a sensor only watches.

```bash
cd examples/plain-crontab
ergostat check
ergostat run          # prints the page's address
ergostat              # what needs attention
ergostat run --stop
```

Things to look at:

- The pruner's controller has a clock instead of a Σ; in the blocks view it is driven by `t: every minute`.
- The rotator runs every 2 minutes and cannot keep its log under 64 KB: the hint says how often it would have to run, and that cron cannot.

Shows: bare numbers, cron, `open_loop`, a disturbance named with its agent, the longest period that can hold.
