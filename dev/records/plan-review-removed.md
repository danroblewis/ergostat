# plan-review-removed: the advisory plan review is removed

The owner, 2026-11-23: plan review costs about as much as writing the code and gives no value ("the plan is bad, we dont have a way to say the plan is good at all"; "we want as few reviews as possible"). The coordinator switched it off live (the `plan-review-when` expression multiplied by 0).

Change. Remove the plan-review block, its gate, its sensors and goals, `dev/bin/planreview.py`, the `plan_reviewer` role and prompt, and the planner's `plan_review: wanted` marking. Keep any lesson or knowledge it fed only if another block still uses it. Update dev/README.md and the model so `ergostat check` passes.

Definition of done.
1. No plan-review session can start, proven by a test on the model.
2. `ergostat check` passes and no measure reads a removed part.
3. Do not measure or change the live instance in the session.

## Where it stopped

Built, round 1. Nothing is left of the definition; the choices taken alone (no one to ask), each the more reversible:

- Removed from the model: the blocks `plan-review-when` and `plan-review`, the gated action `park-gap`, the stock
  `plan-reviews` and its flow `plan-reviews-written`, the auxiliaries `plan-reviews-waiting`, `plan-review-agreement`
  and `plan-{flagged,clean}-{fix-rounds,parks}`, the goals `plans-agreed` and `plan-reviews-done`, and `plans-agreed`
  as an input of `factory-off` (dev/model/measures.yaml). `ai-stopped` now feeds only `plan-when`. Removed in code:
  `dev/bin/planreview.py`, `dev/prompts/plan_reviewer.md`, the role's timeout and tools (agents.py), its settings
  (`[plan]`, `[planning] l_review_share`, `[ai] plan_reviewer_*`, `[knowledge] plan_reviewer_chars`), the planner's
  `plan_review: wanted` marking with its samplers (`review_wanted`, `wanted`, `sampled`), and the gap fold's
  `plan_reviews: append`.
- `defined_by: plan-unreviewed` keeps its name (the flow `plans-unreviewed`, its sensor and older records read it): it
  now means an M gap planned under its own cap. An L gap, which was sampled, is now always `plan`.
- Kept because something else still uses it, or the record still holds what the review left: the plan lint's sweep
  over old `replan` gaps the review sent back, with its "Notes from the plan review" heading; `parks.py` leaving
  alone a park by `plan-review`; the `planned` state and the `plans-reviewed` goal (the lint's sweep). No lesson or
  knowledge entry was fed only by the plan review; the librarian reads every `review.written`, unchanged.
- No `## Entry` was added: this definition may only gain this section.
- Tests: `tests/test_factory_knowledge.py::test_no_plan_review_session_can_start` (done items 1 and 2; seen to fail
  with a sensor running a missing `dev/bin/zz.py`, and with `plan_reviewer` put back in `agents.TIMEOUTS`), and
  `tests/test_code_health_measures.py::test_check_on_the_root_model_reports_no_errors` (`ergostat check`). The live
  instance was not read or changed (done item 3).
