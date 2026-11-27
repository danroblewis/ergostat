# Your first loop: an inbox folder kept short

The smallest whole loop: a stock (the inbox), a goal on it (at most 20 files, give or take 5), a
sensor (a one-line count), a worker that handles 5 files a run, and a load that drops 3 files every
5 seconds. ergostat closes the loop itself: while the goal is off it runs the worker, once per
reading, until the inbox is back to 15; then it stops.

```bash
cd examples/first-loop
ergostat check        # ok, and one finding: drop acts on its own (it is the load, so that is right)
ergostat run          # prints the page's address
ergostat              # the loop, holding
ergostat event        # loop.off, then block.commanded and valve.opened for the worker, then loop.holding
ergostat run --stop
```

Things to look at:

- The inbox saws between about 12 and 27: it fills at 3 per 5s, crosses 25, and the worker drains it.
- `ergostat block` shows `keep-inbox-short`, the on/off controller ergostat put in front of the
  worker because the worker names its goal (`goal: inbox-short`).
- Change `hold: "<= 20"` to `"<= 40"` in `ergostat.yaml`; the running ergostat reloads it, and the
  saw moves up.
- Each worker run is followed at once by a fresh reading, so while the goal is off the worker runs
  back to back, and stops the moment the reading says 15 or fewer.

Shows: a closed loop in four entries, bare numbers, live reload.
