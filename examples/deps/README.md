# Two loops in series, a person behind

Upstream releases make packages outdated. A program opens update pull requests, as many as the
packages are over the goal (`proportional`), at most two a run (`max: 2`), and never more than 12
waiting. A person reviews them (`type: person`, `goal: reviews-flowing`) and has fallen behind.

```bash
cd examples/deps
ergostat check                 # ok; one finding: upstream acts on its own (the load, intended)
ergostat run                   # prints the page's address
ergostat event -n 60           # loop.off, block.commanded (asked vs allowed), valve.opened, person.asked
ergostat                       # what needs attention
ergostat run --stop
```

Things to look at:

- The status explains it: the first loop is at its block's limit (`commanded 2, asked 4`), and
  work piles up behind the second, which waits on a person.
- The person is asked once (`person.asked`); they report what they merged with
  `ergostat block review --done N`. In this simulation the maintainer (played by `sim.py`)
  merges one now and then without reporting it, so the PRs fall by more than the flows explain;
  a report you make is recorded but does not reach the simulation.

Shows: a person in a loop, a proportional controller, `max`, saturation, work piling up downstream.
