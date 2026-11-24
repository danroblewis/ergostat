## Entry

section: Modelling

- **Redesign beside refinement** (landing, `modelling-core`; `docs/proposals/redesign.md`): one change set of many
  coordinated edits for a whole system, made over a few rounds on a scratch copy by the redesigner (an `ai` block,
  haiku by default, within a budget a run and a cap a day), judged as a whole by a scorecard, one
  `ergostat.model-change` of kind `redesign`, drawn dashed on both diagrams, never written without the owner unless
  `accept: {redesign: auto}` (and never one that removes, rewires or changes control). Runs on its own a system at a
  time when it is due (the owner's decision, 2026-11-19: `when: auto` by default), or when the owner asks. Open: removed parts are named, not drawn as ghosts. A change
  set that adds a system or moves parts between systems is scored by how connected each system it touches is (its
  links inside against its links across, `redesign-split-scored`), not by what each system is for. (A waiting redesign is scored again as the record it reads moves, and a promoted one
  written only on a scorecard of the record as it is: `redesign-rescored-as-the-record-moves`.)
