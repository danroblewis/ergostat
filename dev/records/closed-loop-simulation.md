## Entry

section: Modelling

- **Closed-loop simulation** (done, `closedloop`; docs/roadmap/overnight/closedloop.md): projection held the blocks still; now it runs with the loops
  running by default (`numbers/closedloop.py`, SPEC §12b): goals and built-ins by the engine's own code, each machine
  block by its identified model (or a flagged assumption), on the causes strip, what-if (parameters,
  an input's rate, a setpoint, a pool), the fans, proposal effects and `ergostat project`; risk (Monte Carlo: each
  goal's chance of being off at the horizon and its expected time off). *Left*: a block's law written in the model
  (`law:`, 12-model gap 1) in place of a model identified from its record; loop dominance and leverage on the
  closed-loop run; a model for a machine block that commands another (held); stochastic arrivals within a run
  (the risk varies their mean over the horizon, not their timing).
