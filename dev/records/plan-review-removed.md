# plan-review-removed: the advisory plan review is removed

The owner, 2026-11-23: plan review costs about as much as writing the code and gives no value ("the plan is bad, we dont have a way to say the plan is good at all"; "we want as few reviews as possible"). The coordinator switched it off live (the `plan-review-when` expression multiplied by 0).

Change. Remove the plan-review block, its gate, its sensors and goals, `dev/bin/planreview.py`, the `plan_reviewer` role and prompt, and the planner's `plan_review: wanted` marking. Keep any lesson or knowledge it fed only if another block still uses it. Update dev/README.md and the model so `ergostat check` passes.

Definition of done.
1. No plan-review session can start, proven by a test on the model.
2. `ergostat check` passes and no measure reads a removed part.
3. Do not measure or change the live instance in the session.
