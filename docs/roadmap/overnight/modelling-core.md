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

Second stop, 2026-11-19 11:50, on main 2ed2f16. Everything in the definition of done is in place except one suite.

**Done:**
- the split, and every blocking fix (1, 2, 3, 5, 6, 7). Fixes 4 and, mostly, 3 are moot with the parked parts gone;
- the "also" list: the automatic triggers parked, the daily cap, carried redesigns checked again, Accept puts every
  file back on any failure, `keep_history`'s result stored, the boundary rule scoped to a template's own parts, the
  judged-not-better section gone (model-change items, on the Items page), `requests-handled` reachable, the
  harness's ports;
- `tests/test_modelling_core.py` has all 17 acceptance tests, passing. The four stale tests in
  `tests/test_redesign.py` were rewritten. SPEC, ADDING, GAPS and both proposals are updated;
- cuts: the craft bench went (it scored the parked rule tier; it stays on `selfimprove`), and the thirteen stocks
  live in `scripts/self_improve_runs.py`. That also means the bench is no longer "in `scripts/`" as the definition
  says above. Net lines outside `tests/` and `docs/`: +3,973.

**Suites on 53f7032:**
- unit: rc 0, 1,501 passed. The 12 skips are 5 page files when run without playwright (they run in the page
  suite) and 7 VictoriaMetrics conformance tests;
- ruff: rc 0;
- `demo_check` on image-squeeze, alert-triage, ticket-factory and the-job: rc 0, all ok;
- the four Playwright files: **not green**. Sizes and layout ceilings were recorded again (every example now draws
  its modelling system; several examples' `satellite-far` ceilings rose, from 6 to 17 for backups). One test then
  fails for all 20 examples: `test_model_errors_drain_is_a_short_straight_satellite_of_its_stock`, from `layout2`,
  merged after `selfimprove` branched. With the larger modelling template, the router takes the connector
  `model-error → gap:model-fits` out of the stock's bottom edge, 10 px left of `model-mended`'s pipe (stock bottom at
  y 228, connector out at x 298, pipe at x 308). It then runs right 5.5 px below the stock and crosses the pipe.
  Each failing test leaves its page open, so the suite grew past 6 GB and the watchdog killed it.

**Left:** a layout fix (the connector should leave a stock by the side facing its target when that target sits
within the stock's height, or the router should keep connectors off a pipe's first segment), or the layout
owner's ruling on that test. Then the four suites again.
