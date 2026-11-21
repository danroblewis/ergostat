# plan-by-size: the planner does as much as a gap's size class calls for, and the share of AI money spent on planning is measured

depends-on: [gap-size]

## Definition of done

The planner (`dev/bin/plan.py`, the `planner` block) reads the size class that gap-size records on the gap (S/M/L/XL with a confidence) and acts on it:
- **S**: no planner session. The gap's definition is written from its own title and text, with the house-rule done criteria and a fixed small budget, into `run/defs/<branch>.md`. It is never written over a definition already there (same rule as the plan review today). The gap goes to ready with `defined_by` naming the size path and a planning cost of 0.
- **M**: one planner session capped at a new `[ai] planner_m_session_usd`. The plan goes straight to ready, with no plan review. A one-definition plan is written to `run/defs/` like an approved plan, `defined_by` says it was not reviewed, and a split is handled as today.
- **L**: the full planner. The plan goes to plan review on a sample whose share is set by a new `[planning] l_review_share`. The pick is deterministic per gap, so a lease retry gives the same answer. A replan (a plan the review sent back) is always reviewed. An unsampled plan goes to ready as M does.
- **XL**: the planner must split. A single definition for the gap itself is refused through `send_back`, and the reason says an XL gap must split.
- **Fails closed**: a gap with no size class, a value other than exactly S/M/L/XL, or a confidence below `[planning] min_size_confidence` takes today's path: the full planner, always reviewed. Sub-gaps of a split have no class, so they take this path.
- **Limits**: `planner_m_session_usd` above `planner_session_usd`, and any share or confidence outside [0, 1], stop the run with an error before any session is started.
- **Cost recorded**: every planner and plan-review session also records its cost in a planning-only cost field on the gap. S records 0.
- **Measured**: `measure.py planning-cost-share` is planning cost over total AI cost, across gaps merged in the window that carry the planning-cost field. Gaps without the field are left out, never counted as 0. With none, it has no value (exit 1, like first-pass-yield). It is an auxiliary in `dev/model/knowledge.yaml`.
- **Model**: flows for the S path and for unreviewed plans (open → ready), each with a sensor on its `defined_by`.
- **Docs**: `dev/README.md`, the planner prompt (XL must split) and `measure.py`'s docstring say the above.

## Files to touch

`dev/bin/plan.py`, `dev/bin/measure.py`, `dev/factory.toml`, `dev/model/knowledge.yaml`, `dev/prompts/planner.md`, `dev/README.md`, `tests/test_factory_knowledge.py`

## Risks

- lesson-3: a missing, unknown or low-confidence size class, or a merged gap with no planning-cost field, could quietly be treated as S or as $0 of planning.
- lesson-4: `l_review_share`, `min_size_confidence` and `planner_m_session_usd` come from config; one above its ceiling (an M cap above the planner's) has to be refused before any session is started.
- lesson-8: "M and L skip review safely" is not claimed. What is claimed is only the routing and the measured share.

## Acceptance tests

- `tests/test_factory_knowledge.py::test_a_small_gap_is_ready_without_a_planner_session`: an S gap reaches ready with a definition, a planning cost of 0, and no planner session started (stand-in counts zero sessions). A definition already in `run/defs/` is left byte-for-byte.
- `tests/test_factory_knowledge.py::test_a_medium_plan_skips_review_under_its_own_cap`: an M gap's session is reserved at `planner_m_session_usd`, not `planner_session_usd`, and the gap reaches ready without passing through planned.
- `tests/test_factory_knowledge.py::test_large_plans_are_reviewed_on_a_stable_sample`: with share 0 an L plan is ready unreviewed, and with share 1 it is planned. Running the planner twice on one gap gives the same pick. A replan is reviewed even with share 0.
- `tests/test_factory_knowledge.py::test_an_xl_gap_planned_whole_is_sent_back`: one definition for an XL gap is refused with "must split". A split into two sub-gaps is accepted.
- `tests/test_factory_knowledge.py::test_an_unsized_or_unsure_gap_takes_the_full_path`: no size, the value `"s "`, and a class below the confidence bar each produce a planned gap (reviewed), never ready. (lesson-3)
- `tests/test_factory_knowledge.py::test_size_settings_out_of_bounds_stop_before_a_session`: an M cap above the planner's cap, a share of 1.5, and a confidence of -0.1 each stop the run with an error and no session reserved. (lesson-4)
- `tests/test_factory_knowledge.py::test_planning_cost_share_leaves_out_unrecorded_gaps`: merged gaps with planning costs 1 and 0 against totals 4 and 6 give 0.1. A merged gap without the field does not move it. Only such gaps give no value (exit 1). (lesson-3, lesson-8)

The implementor breaks each guarded line (the fail-closed check, the ceiling checks, the field filter) and reports that the test fails (lesson-9).

## Size budget

220 net lines (dev/bin, dev/model, dev/factory.toml, dev/prompts; no `ergostat/` code).

## Notes from the plan review (answer each)

- lesson-9: test_large_plans_are_reviewed_on_a_stable_sample only uses share 0 and 1, where random.random() < share is also 'stable'. Add a share strictly between 0 and 1 with two gap ids known to fall on opposite sides of it, and assert the same pick on a second run (a lease retry); break the per-gap keying (e.g. use random) and report the test fails.
- lesson-3: say and test what planning cost a planner or plan-review session that times out, errors or is cancelled records. It must be the reserved budget, never 0 and never nothing. A replan must add to the gap's planning cost, not overwrite it (test plan + review + replan gives the sum).
- lesson-3: a size class present with its confidence missing or unreadable must take the full, reviewed path. Add it to test_an_unsized_or_unsure_gap_takes_the_full_path.
- lesson-3: planning-cost-share must refuse or leave out a merged gap whose planning cost is above its total AI cost or negative, instead of folding it in. State which, and test it.
- lesson-1: the S path's 'never write over an existing definition' is a check-then-write. Use an exclusive create (O_EXCL / open mode 'x') and test a definition appearing between the check and the write; it must be left byte-for-byte.
- lesson-5: say how a replan is recognised (from the review's send-back record, by seq, not by timestamp, per lesson-2) and that defined_by is rewritten on each plan, so an old 'unreviewed' or size-path value never survives a replan.
- lesson-8: the S path sends to ready a definition no AI or reviewer has looked at. The README must say so plainly and must not describe S, M or unsampled L as checked.
- Model: no acceptance test covers the new knowledge.yaml flows, the sensors and the planning-cost-share auxiliary. Add one that fails if they are missing or misnamed.
- XL: say what stops an XL gap whose planner keeps sending a single definition (does send_back count toward the existing retry/park limit?), so it cannot loop on planner money (lesson-4).
- M split 'handled as today': state whether an M plan that splits gets reviewed. The sub-gaps then take the unsized path, which is reviewed; confirm that this is intended and tested.
- lesson-7: merge origin/main into the branch and rerun the suites before reporting it built.
