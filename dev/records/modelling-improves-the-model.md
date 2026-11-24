## Entry

section: Modelling

- **Modelling improves the model** (done, `modelling-core`, `modelling-core2` and `modelling-improves-the-model`;
  `docs/proposals/self-improvement.md`): what `check` finds is held as requests (`ergostat.modelling-request`); the
  rule tier (units, a queue's goal, a process nobody identified) and the AI tier (off unless `ai: true`), each a block
  of `use: modelling`, answer them with ordinary changes, checked in the tier's own process; the judge decides by class
  (description, unit, rename judged by check; values, equations and structure by the record). Every example uses it.
  The AI tier runs within `ai-daily`: a call starts only when the day's spend plus its reservation stays within it, one
  call at a time, and a call that reports more than its reservation can take the day above it by that one overrun. Its
  counts have ceilings (`ai-most` 1 to 16, `--tries` 1 to 3, `ai-daily` 0 to 20; template parameters take
  `min:`/`max:`). Parked on `selfimprove` (its definition file says why): the rule tier's first-order equations,
  event-type renames that edit programs, the rule tier's copies of the chain fixes.
