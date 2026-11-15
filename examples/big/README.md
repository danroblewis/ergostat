# 24 loops, for the layout

A made-up platform of six systems, each a chain of four queues; every queue has a goal and a
worker that drains it while the goal is off. What the diagram does at scale.

- `ergostat.yaml` names the project and includes `systems/*.yaml`, one file per system
  (`defaults: system: web` puts everything in it in that system).
- Each drain block names its goal (`goal: web-q0-low`): ergostat runs it while the goal is off.
- `tick.py` is the one script: `count` (a sensor), `arrive` (the load), `drain` (a worker,
  which moves its queue down to half its goal, into the next queue). `.sim.json` is the
  simulated platform.

```bash
cd examples/big
ergostat check        # ok; six findings: the arrivals blocks act on their own (the load, intended)
ergostat run          # prints the page's address
ergostat              # the 24 loops
ergostat event -n 60  # loop.off → block.commanded → valve.opened → loop.holding
ergostat run --stop
```

Things to look at:

- The first view keeps text legible and says when more lies beyond the edge; `fit` shows it all.
- The blocks view groups the loops by system; `ergostat block` lists the implied `keep-*` blocks.
- Work drained from one queue arrives at the next, so the loops in a chain set each other off.

Shows: layout at scale, includes and defaults, the `goal:` shortcut.
