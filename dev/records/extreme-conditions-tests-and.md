## Entry

section: Runtime, scale and latency

- **Extreme-conditions tests and calibration per part of the model** (done on `extremes`,
  `docs/roadmap/overnight/extremes.md`): the extreme conditions run the closed-loop projection (inputs at 0 and 10×, a
  pool at 0, each setpoint at its limits, each parameter at its range's ends), kept on disk per condition and per
  connected part of the model, run in the background by one low-priority process per project and bounded (the Check
  page's first status 4 s → 0.02 s on ticket-factory; `check` again 4.1 s → 0.3 s); each equation's own fit (R²,
  scaled error, skill against its mean) on its panel, and a finding where it fits worse than its mean. Left: a law's
  windup is only tested where a block writes `gain:`; the CLI waits at most 5 s, so a large model's first `check` says
  the rest are still to run; a project never run (no state directory, which `check` never makes) keeps them in memory
  only, so its every `check` runs them again.
