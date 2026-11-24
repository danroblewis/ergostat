## Entry

section: Modelling

- **Operating modes, regime-scheduled thresholds, interlocks, risk gating** (open; designed in
  `docs/proposals/coordinator/08-modes-and-protection.md`). *Done*: act-risk gating, on `act-risk-gating` (SPEC §12k):
  an action's `risk:` steps its gate one step stricter when the act scores at or above its threshold, at the request
  and again at the act. The operating state and the owner's presence, as a record, on `operating-state-record` (SPEC
  §12k): `ergostat operating` (normal, maintenance as a lease of at most 24 h, freeze, incident; present or away after
  `operating.away-after`), folded in seq order, an unreadable record read as incident and away; nothing gated on it
  yet. *Left*: thresholds scheduled by regime (the gates the operating state sets), reshaping an act, and keeping a state older than the record's `keep:` (pruned with its event).
