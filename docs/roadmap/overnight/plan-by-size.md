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

## Where it stopped

Built. These are the decisions made alone, each the more reversible option, and the answers to the notes.

**"Planned" read as "marked for the plan review".** The owner decided on 2026-11-20 that the plan review is never a
gate. On main a lint-clean plan is `ready` at once, `planned` is a legacy state that the lint sweep empties, and
`test_the_knowledge_model_loads` asserts that the planner never moves a gap to `planned`. So a "reviewed" plan here is
`ready` with `plan_review: wanted` (and `defined_by: plan`), and an unreviewed one is `ready` with `plan_review: null`
(`defined_by: plan-unreviewed`, or `size-s` for S). The tests assert those fields. Making the review a gate again
would be the owner's call. `[plan] review = off` still turns the review off for every path.

**Where the class comes from.** The planner reads `planned_size` and `size_confidence` (the gap-size fields) as they
are on the gap before it plans. A confidence counts as low 0.25, medium 0.5, high 0.75 against
`[planning] min_size_confidence`. Nothing in this gap sets a class on an open gap: the coordinator (or an earlier
plan) has to have recorded it. When the settings are unset, nothing is trusted (bar 1.0), the M cap is the planner's
own, and the L share is 1, so a config without `[planning]` behaves as main does, with every plan reviewed.
`dev/factory.toml` sets 0.5, $2 and 0.5.

Answers to the plan review's notes:
- *Stable sample (lesson-9)*: the test computes the two fixture gaps' picks and sets the share between them, so
  share is strictly in (0, 1) and one gap falls on each side. Each gap is planned three times, as lease retries
  would be. Replacing the per-gap pick with `random.random() < share` makes the test fail (checked).
- *Failed sessions (lesson-3)*: a planner or plan-review session that times out, errors or is cancelled (any
  BaseException, including SystemExit on SIGTERM) adds its whole reservation to `planning_cost_usd` and
  `ai_cost_usd`. So does a session that gives no cost. `planning_cost_usd` is a `sum` fold (ergostat.yaml: one line
  outside 'Files to touch', needed for the replan to add up). The test covers plan $0.25, then a plan review that
  timed out ($1), then a replan that timed out ($1), giving 2.25. Not covered: an error *after* a planner session
  returned (in the lint, say) loses that session's cost from the gap, as main already loses `ai_cost_usd` there.
  The ledger still holds it.
- *Confidence missing or unreadable*: `{"planned_size": "S"}`, a confidence of `0.9` (a number) and `"sure"` are
  cases of `test_an_unsized_or_unsure_gap_takes_the_full_path`.
- *Planning cost above the total, or negative*: left out of the share and named on stderr, never folded in. The same
  goes for a cost that is not a number (bool, NaN). Tested.
- *Exclusive create (lesson-1)*: `define` creates `run/defs/<branch>.md` with mode `"x"`. The test makes the
  coordinator's file appear inside the check (`intake.definition` patched to write it and answer None). The file is
  left byte for byte and the gap is `defined_by: coordinator`. Changing the mode to `"w"` makes the test fail
  (checked).
- *Replan (lesson-5, lesson-2)*: a replan is recognised by the gap's state `replan`, which the fold sets from the
  send-back event in record order (seq), never by comparing times. `defined_by` and `plan_review` are written by
  every `gap.defined`, so an old `plan-unreviewed` or `size-s` never survives a replan (tested: L unreviewed, sent
  back, then `plan` + `wanted`). The replanned gap's class is ignored, except XL.
- *README (lesson-8)*: it says in bold that no AI and no reviewer has looked at an S definition. It also says that
  nothing claims M, unsampled L or S plans are as good as reviewed ones.
- *Model*: `test_the_size_paths_are_in_the_model` checks both flows (open to ready, their sensors' `defined_by`, in
  the planner's `out`) and the auxiliary's sensor command. Renaming either one makes it fail (checked).
- *XL loop (lesson-4)*: the XL refusal goes through `send_back`, so it counts toward `plan_lint_failures`, and the
  6th refusal parks the gap (MOST_LINT). Tested: two refusals give counts 1 and 2. The planner learns the rule from
  the finding "an XL gap must split" (its brief does not carry the class).
- *M split*: an M plan that splits is not reviewed as a whole (a parent merges nothing). Its sub-gaps carry no class,
  so they are marked for review (`defined_by: plan-split`, `plan_review: wanted`) and get `planning_cost_usd: 0`,
  since their planning was paid on the parent. This is intended, and tested in the M test.
- *lesson-7*: this container has no `origin`. Local `main` is 505a93e9, the branch's own base, so there was nothing
  to merge. The queue merges main again.

Mutation checks (lesson-9). Each guarded line was broken by hand and its test watched fail: the confidence bar, the
exact-class check, the M ceiling, the share bound, the confidence floor, the per-gap pick, replan-always-reviewed,
the XL refusal, the exclusive create, the M cap in use, the planner's and the plan review's failure charge, the
field filter (a missing field counted as 0), the range filter, a flow's sensor and the auxiliary's sensor.

Size: 157 net lines in dev/bin, dev/model, dev/factory.toml, dev/prompts and ergostat.yaml, against a budget of 220.
`dev/bin/planreview.py` and `ergostat.yaml` are outside 'Files to touch'. They are needed for the plan review's
planning cost and for the summed field.

**The fast suites' failure after round 1.** The factory's `unit` run (`-n 8 --dist worksteal`) showed one `F` near
14%, but its tail does not name the test. This session was not allowed to run the whole suite, and there is no suite
log to read. Every test file that reads what this branch changes was run alone on the branch and passed:
`tests/test_factory_knowledge.py`, `test_factory.py`, `test_factory_resources.py`, `test_factory_manager.py`,
`test_factory_sessions.py`, `test_factory_times.py`, `test_backlog.py`, `test_code_health_coverage.py` and
`test_daemon_docs.py`. No other test file reads `dev/bin`, `dev/model`, `dev/factory.toml`, the root `ergostat.yaml`
or this definition. So no code was changed: a fix without the failing test's name would be a guess (lesson-10,
lesson-13). Left: the factory's rerun of the failed test on clean main. If it fails there too, it is unrelated. If it
is in one of the files above and fails only under load, its name is needed for a fix round.

**`ergostat check`'s no-equation findings.** `flow.small-gaps-defined` and `flow.plans-unreviewed` now have
equations like the other plan flows: `small-share * stock.gaps-open / plan-time` and
`unreviewed-share * stock.gaps-open / plan-time`, driven by `stock.gaps-open`. The two new parameters are marked
`estimate: true` (0.2 and 0.3, range [0, 1]), since there is no record yet of how many gaps take each path.
`ergostat check` itself was refused by the shell in this session (`uv run ergostat check`), so the finding's removal
was not seen here. `tests/test_factory_knowledge.py` passes (91).

**The fast suites' failure after round 1, named.** The second `unit` run named its two failures:
`tests/test_leases.py::test_the_watchdog_renews_from_what_the_holder_does_elsewhere` (the lease history was
`['expired', 'ack']`, not `['ack']`) and `tests/test_daemons.py::test_a_short_lived_daemon_is_sampled_before_it_ends`
(no sample within 3 s). Both are unrelated to this branch (lesson-13): `git diff --stat main...HEAD` touches no file
under `ergostat/` and neither test file. The only test file it changes is `tests/test_factory_knowledge.py`. Both
tests build their own project in `tmp_path` from an inline model, so they never read `dev/`, the root
`ergostat.yaml` or this definition. (The only change to `ergostat.yaml` is one `planning_cost_usd: sum` field on the
factory's gap items.) Run alone on the branch, both pass (2 passed in 7.4 s). Both are timing tests: one renews a 1 s
lease from session events 0.4 s apart, the other expects a daemon sampled within 3 s of its start. They failed under
`-n 8` with the rest of the suite running, so they depend on load (lesson-10). The cause may be a real race in the
lease watchdog or the daemon sampler, or the tests' fixed timings. Finding out belongs in a gap of its own, not this
branch. No code was changed for them. Left: the factory's rerun of the two tests on clean main.

**Main merged (07f9b250).** There were two conflicts, and each was resolved by keeping both sides. In
`dev/bin/plan.py`, main's join judge constants (`MOST_SHORT`, `VERDICT`, `MISSING`, `REASONS`) sit beside the branch's
`TRUST`, `SMALL` and size helpers. In `dev/README.md`, main's join judge paragraph stays. The plan review sentence
keeps the branch's *Planning by size* pointer and adds main's `all` mode. After the merge, these pass:
`tests/test_factory_knowledge.py` (91 passed), `tests/test_factory.py` (126 passed, 2 skipped) and
`ruff check ergostat tests scripts`. `ruff check dev/bin` reports two findings (B023 at the join judge's `listed` in
plan.py, E501 at review.py:41). Both come from main unchanged. The unit suite and the browser files were not run here.
The factory runs them.

**Round 3: the S definition's text (review/plan-by-size-1, dev/bin/plan.py:126-133).** The S path read
`f['text']` / `f['description']`, which no gap source writes, so every S definition held only the gap's title. It now
reads the gap's own text through `entry_of`: the gap's `docs/GAPS.md` entry on main (`brief.gaps_entry`, as the
planner's brief does), or else a join sub-gap's `entry`. A gap that `manage.py file_gap` filed has a definition file
already, so `intake.definition` takes it first and the size path is never reached. An S gap with neither text takes
the full path, marked for the plan review, never a title-only definition (lesson-3). The test now asserts that the
entry's body ("what it lacks.", "More of it.") is in `run/defs/alpha-thing.md`. It also checks that an S gap not in
GAPS.md and with no entry gets a planner session at the planner's cap with `defined_by: plan` and
`plan_review: wanted`. The race gap now carries an `entry`, so it still reaches the exclusive create. Mutation checks
(lesson-9), both seen to fail the test: an empty text in the S definition, and the S path taken without text. The
other two round-1 findings stand as answered before. The failure charge leans towards charging too much, which the
review says is no fail-open. The reason for the scope (planreview.py, ergostat.yaml) is given above. After this round,
`tests/test_factory_knowledge.py` (91 passed), `tests/test_factory.py` (126 passed, 2 skipped) and
`ruff check ergostat tests scripts` pass. Local `main` is an ancestor of the branch. Size: +7 net lines in
plan.py, about 164 of 220 in all. The unit suite and the browser files were not run here.
