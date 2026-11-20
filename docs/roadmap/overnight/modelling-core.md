# modelling-core: the parts of selfimprove and redesign that the gate review passed

Branch `modelling-core`, from main at a09c176. It is the outcome of the gate review of `selfimprove` and `redesign`
(the coordinator: *split selfimprove, fix redesign*). Gaps (`docs/GAPS.md`, Modelling): *craft findings in check*,
*a step whose goal never goes off*, *modelling improves the model*, *redesign beside refinement*.

## What lands, what is parked

Lands: craft notes in `check`; `use: modelling` in every example; part renames that keep their history
(`formerly:`); the description, unit and rename change classes; the AI tier, whose changes the judge decides by class;
the one-line modelling status; each tier's changes recorded and checked in its own process; rebase and carry of
waiting changes; redesign (the change set, the scorecard, the redesigner, the review section, drawing as proposed).

Parked on `selfimprove` (its definition file says where it stopped): the rule tier's first-order equations and its
measurable-fit equation; event-type renames that edit program files (and `formerly:` on item kinds); the rule tier's
copies of the chain and structure fixes (`structural.py`'s own proposals, which carry `rewires`, answer those).

## Definition of done

The branch carries the landed parts on current main and none of the parked ones, with the review's blocking fixes:
a change set (or any proposal) that changes the judge's policy, a block's `accept` or a template instance's `with:` is
refused; a redesign that removes a part, rewires a kind's chain or changes control waits for the owner even under
`redesign: auto` (SPEC's policy row true as written); a rename is a rename only when no sensor and no control changes
with it; every change that rewires a chain says `rewires`; a promoted redesign whose edit fails is superseded and
never blocks the queue; a redesign the owner asks for is recorded as an ask that the redesigner block takes up (no
thread in the page server, the project's model never replaced there); the redesigner's and the AI tier's runs print
result lines, so `ergostat.cost.*` counts them; the redesigner reads `MODELLING-WELL.md` through the help documents.
Besides: redesign runs only when the owner asks (`when: ask` by default; the automatic triggers parked); a carried
redesign is checked again; a write of several files rolls back whole on any failure; what `keep_history` did is
stored; redesigns judged not better are shown as the model-change items they are (the Items tab), not a section of
their own; the goal `requests-handled` can be reached (held requests drain from what it counts); the craft bench
lives in `scripts/`; the verification harness's ports avoid 8798; `many-cloud-inflows` leaves out only the parts a
template made; redesign runs stop at a daily spending cap.

## Acceptance tests

`tests/test_modelling_core.py`:

- `test_a_change_set_that_changes_the_policy_is_refused`
- `test_a_proposal_that_changes_a_blocks_accept_or_a_templates_with_is_refused`
- `test_a_redesign_that_removes_rewires_or_changes_control_waits_for_the_owner`
- `test_a_rename_that_changes_a_sensor_or_control_is_not_a_rename`
- `test_every_change_that_rewires_a_chain_says_so`
- `test_a_promoted_redesign_whose_edit_fails_is_superseded`
- `test_an_owner_asked_redesign_is_an_ask_the_block_takes_up`
- `test_the_redesigner_and_the_ai_tier_print_result_lines`
- `test_the_redesigners_guides_come_through_the_help_documents`
- `test_a_carried_redesign_is_checked_again`
- `test_a_write_of_several_files_rolls_back_whole`
- `test_keep_history_says_what_it_did`
- `test_the_scorecard_says_behaviour_lost`
- `test_the_judges_hold_while_a_redesign_is_made_is_bounded`
- `test_redesigns_stop_at_the_daily_cap`
- `test_held_requests_leave_the_count_the_goal_holds`
- `test_the_boundary_leaves_out_only_a_templates_parts`

and the existing `tests/test_self_improve.py`, `tests/test_redesign.py`, `tests/test_modelling_template.py`,
`tests/test_improve.py`; the four suites with rc 0 and no page test skipped; `demo_check` on image-squeeze,
alert-triage, ticket-factory and the-job.

## Size budget

Over the default 600, with this reason: it lands two subsystems that were written before the overnight gates
(`selfimprove`'s modelling loop and `redesign`), now with their parked parts taken out. Expected about 4,000 net lines
outside `tests/` and `docs/`, of which about 100 are the examples' `use: modelling` lines and about 550 the
verification harness and the craft bench in `scripts/`.

## Where it stopped

Final state, on main 0a59c72 (churn, fastroute), after the final gate review's fixes and the owner's decision that
structural review runs on its own.

- The gate review's fixes: B1 (a rename keeps every number and item kind), B2 (each AI call charged as it is spent,
  charged the most it could have cost when it never says, timed to fit the block), and the smaller points and cuts
  (see the commits).
- **Redesign on its own** (`numbers/redesign_due.py`; the owner, 2026-11-19): `when: auto` is the default.
  - It works per system, a subsystem at a time past 40 parts; a system too large with nothing to split into is held
    for the owner as `too-large`.
  - A system is due when its replay is worse than its mean for 30 minutes, when a finding says its structure is
    wrong (or a structural one is held an hour), when refinement stalled, on the first run, and once a day. What is
    wrong is taken before the scheduled review.
  - Bounds: one waiting a system; a 6 h rest after one no better, refused, or that made nothing (unless the model
    changed); the daily cap.
  - A redesign of a system changes only that system (others follow its renames); the redesigner sees only its
    findings, and each stock's level on the record.
  - Each run's trigger and result are held as a modelling request (Items tab, inbox) and said in `ergostat status`.
    What it makes is written only with the owner's approval, unless `accept: {redesign: auto}`.
- One carrying mechanism with churn's: `supersede` carries ergostat's own changes (subject unchanged) and a
  description, unit or redesign whoever made it (edit still applies); `rebase` only moves lines.
- Verification on ticket-factory, offline, with a burst (12 issues at once, then one every 3 s, to 60), haiku:
  - every system's automatic run fired, each with its trigger said: oversight (measured-not-caused, first run),
    then intake, making, review and shipping (daily review). There were two runs of about 15 minutes each, $0.33 in
    all, within the $1 daily cap set;
  - the burst backed up in front of the work step (located: 53 at most), not in review. Asked about `making`, the
    redesigner proposed a capacity structure: `flow.work` as `MIN(stock.located / work-time, work-capacity /
    work-time)` with a new `work-capacity` parameter ($0.027). Its scorecard said mixed (the replay of `done`
    worse), so it would wait for the owner and not be written;
  - for review, haiku proposed descriptions and tolerances only.
  - The whole verification came to about $0.46.
- Net lines outside `tests/` and `docs/`: +3,969.
- Suites (fast commands, under `suite_watch`, one at a time):
  - unit: rc 0, 1,679 passed, 1 xfailed (13 skips: page files without playwright, run in the browser suite, and
    VictoriaMetrics);
  - browser: rc 0, 217 passed;
  - ruff: rc 0;
  - `demo_check` on the four: rc 0.
