## Entry

section: Modelling

- **Operating modes, regime-scheduled thresholds, interlocks, risk gating** (open; designed in
  `docs/proposals/coordinator/08-modes-and-protection.md`). *Done*: act-risk gating, on `act-risk-gating` (SPEC §12k):
  an action's `risk:` steps its gate one step stricter when the act scores at or above its threshold, at the request
  and again at the act. *Left*: operating modes, thresholds scheduled by regime, reshaping an act, and the staleness of
  the state an act was planned on.
