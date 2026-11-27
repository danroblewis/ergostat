# The Coordinator of a software factory

The control architecture designed in `docs/proposals/coordinator/` (00 to 11), built as an ergostat model and run
against a simulated factory. `docs/proposals/coordinator/12-model.md` walks it part by part, maps it to the
architecture, and gives the tests and what ergostat could not express.

- **The plant** is the work (items through a leased work queue to a pool of six AI-agent workers), the rework cycle
  (what the acceptance check lets through wrong, found hours later), the codebase (code per feature) and the owner
  (at the desk or away, answering, directing, correcting, pruning).
- **The observer** is the context: the working window, the corrections written down or held only in the window, and
  the age of the oldest silence among the runs.
- **The loops** are 07's: the quality cascade (LP1 the acceptance check inside LP2, escaped rework), the merge queue
  (LP4), dispatch under the owner's cap scheduled on the owner's presence (LP3, S2), the lease watchdog (LP5),
  admission (LP6), the owner's attention under S1 and S5 (LP7), externalising (LP9) and consolidation (LP10).
- **Modelling** is ergostat's own loop (an improver stand-in and the judge), as in the-job.

Everything is simulated and free: no AI is called. The world (`world/plant.py`) is stepped by the clock, a factory
hour every `COORD_HOUR` seconds (30, so a factory day takes 12 minutes); the controllers' laws are
`world/policy.py`, run by the blocks through `bin/coord.py`.

## Run it

```bash
cp -r examples/coordinator /tmp/coordinator && cd /tmp/coordinator
ergostat run                          # the designed Coordinator
COORD_POLICY=harness ergostat run     # the same blocks with the harness's policy as it was: the controllers "off"
ergostat loop                         # each goal, holding or off
ergostat item --projection work             # the work items, by state
ergostat run --stop
```

The owner's first direction arrives at once (150 items); four more follow over the factory's month.

## The behaviour test

ergostat's projection does not yet simulate the blocks' laws, so the thirty-day closed-loop runs are made headless,
by the same code on the same clock:

```bash
python3 -m world.experiment --seed 1 2 3 4 5 6 7 8 9 10     # harness, designed, designed with LP2 off
uv run --with matplotlib python world/charts.py               # docs/proposals/coordinator/img/model-*.png
```
