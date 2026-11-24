## Entry

section: Modelling

- **Resource levelling and completion estimates** (done, on `eta`; SPEC §5a, *Completion estimates*): the
  projection levels resources now: each open item's p50 and p90 finish from a Monte Carlo over every open item (a
  block's capacity, its recorded runs and rework, time in a state by Kaplan–Meier given the item's age, the
  record's paths, dependencies and arrivals); the Timeline's lanes, the list's *done by*, the item's why. Left: a
  goal's gate on a block is not simulated, and a capacity no block declares is not modelled (a block's `workspace:`
  pool is: held from the item's first take until it finishes).
