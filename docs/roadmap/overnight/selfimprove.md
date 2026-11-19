# selfimprove (and redesign on top of it)

## The gap

From `docs/GAPS.md` (Modelling): the **one-line modelling loop** (`use: modelling` instead of about 150 lines copied
into each example), **craft findings in `check`** (a part with no description, a stock with no unit, a flow between
stocks with no equation, an undescribed collector, event types in mixed forms, a `process:` with no `identified:`),
and **a step whose goal never goes off** (a takes queue's goal with a tolerance or a setpoint above 0). The branch
`selfimprove` (`docs/proposals/self-improvement.md`) answers them with modelling's tiered improver: what `check` finds
held as requests, a rule tier and an AI tier as template blocks, the description/unit/rename change classes with
`accept:`, and `use: modelling` in every example. `redesign` (`docs/proposals/redesign.md`) is built on it and is
finished and verified; it lands right after it.

## Done

The branch is done when selfimprove's own claims are verified and both branches are rebased on main with every suite
green. Verified means: every example run briefly with `use: modelling` (the rule tier, and the AI tier on haiku, total
spend under $3, recorded) through `scripts/self_improve_runs.py`, and what each tier proposed and what was accepted
written per example into the proposal's *Results*, with the planted cases (`ergostat bench improve --suite craft`)
scored. Rebased means: `selfimprove` on main 24748b1 with the cloud check, reports, gapsfix, reloadfix, indexfix and
the test ports kept, and `redesign` on the rebased `selfimprove`, its redesigner's guide given the report line (a block
printing `{"report": "..."}` when the format cannot express a change).

## Acceptance tests

- `tests/test_self_improve.py` (all ten), `tests/test_modelling_template.py`, `tests/test_improve.py`,
  `tests/test_redesign.py`, all passing on redesign's tip;
- the four suites on redesign's tip with rc 0: `uv run python -m pytest -q`; the four Playwright files;
  `uv run ruff check ergostat tests scripts`; `scripts/demo_check.py image-squeeze alert-triage ticket-factory the-job`;
- `scripts/self_improve_runs.py` over every example (haiku), and `ergostat bench improve --suite craft`, recorded.

## Size budget

Over the default 600, with this reason: both branches were written before the overnight gates, as two whole
subsystems (the tiered improver, and redesign's change set, scorecard and redesigner). Net lines outside `tests/` and
`docs/` before the rebase: `selfimprove` +2,610 (of which about 80 are the examples' `use: modelling` lines, 236 the
verification harness and 304 the craft bench), `redesign` +1,900 on top of it. Tonight adds no features: only the
rebase's conflict resolutions, the report line in the redesigner's guide, and the results written down.
