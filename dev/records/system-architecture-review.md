## Entry

section: Modelling

- **System architecture review** (computed measures done on `architecture`; design in
  `docs/proposals/architecture.md`): `check` notes `system-splits`, `systems-merge`, `interface`, `time-scales` and
  `purpose`, and each system's size (and whether it is nearly decomposable) in `explain`, its size on its panel; a
  model-level `purpose:`; candidates to aggregate from loop dominance over the window, an `aggregate` row on a
  system's Dynamics panel (`numbers/aggregation.py`, on `aggregation-from-dominance`); the stocks' modes at the start
  and each link's eigenvalue elasticity in `explain` (`numbers/modes.py`, on `eigenvalue-elasticity`); the AI rung's
  Viable System Model checklist and purpose coverage, on the owner's word (`ergostat improve --architecture`,
  `spec/vsm.py`, `numbers/vsm_review.py`, on `architecture-vsm-and-purpose`), its findings held for the owner; the
  relative gain array of a system's loops from approved step tests, a line of `explain system.NAME`
  (`control/rga.py`, on `relative-gain-array`). *Left*: the AI rung's proposal to aggregate (from loop dominance),
  elasticity over the replay, interface stability over the model's history, and the per-system redesign and daily
  larger-model review (after `redesign`).
  system's Dynamics panel (`numbers/aggregation.py`, on `aggregation-from-dominance`); the AI rung's Viable System
  Model checklist and purpose coverage, on the owner's word (`ergostat improve --architecture`, `spec/vsm.py`,
  `numbers/vsm_review.py`, on `architecture-vsm-and-purpose`), its findings held for the owner; how often each
  system's interface changed over the model's recorded versions, in `explain system.NAME` (on
  `interface-stability`; SPEC §4a). *Left*: eigenvalue elasticity, the AI rung's proposal to aggregate, and the
  per-system redesign and daily larger-model review (after `redesign`).
  system's Dynamics panel (`numbers/aggregation.py`, on `aggregation-from-dominance`); a system's redesign shown
  its architecture (its notes, size, interface and subsystems), and a daily architecture review on a larger model
  (sonnet by default, `redesign.review`) whose findings are requests: a redesign taken first, a split or merge held
  for the owner (`numbers/archreview.py`, on `architecture-per-system-redesign`). *Left*: eigenvalue elasticity,
  the AI rung's proposal to aggregate, interface stability over the model's history, the Viable System Model
  checklist and purpose coverage (the AI rung), and a merge of two systems redesigned as one change.
