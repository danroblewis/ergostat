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

After the final gate review's fixes, on main 214d864.

- B1: a rename keeps every number and item kind as they were (`version.renamed_parts`). A value, a rate or an item
  kind changed with a rename makes it no rename; the rename test has the three cases.
- B2: each AI call's cost is printed and charged as it is spent (`modeller.answer` / `redesigner.run` `on_call`;
  `redesign.charge`). A call that never says its cost is charged the most it could have cost (`modeller.unsaid`).
  Calls are timed to fit the block's timeout (`--timeout`, `modeller.per_call`). The daily cap fails closed.
- The smaller points:
  - a rename's fit after is measured once its history is kept;
  - files are written whole or not at all (written beside, then renamed over);
  - a carried redesign is held to who-decides and its owner flags again;
  - a rename is kept out of plain `accept: auto`; SPEC names what `accept: auto` promotes, what the judge never
    writes, and how each kind is judged (a redesign on the record it has, its fit allowed 10% worse);
  - an open redesign holds its lines only when the judge may write it;
  - held modelling requests are in the inbox, and they have an Items-page title;
  - the template skip is scoped to once library templates, with one helper for what a template made.
- Cuts:
  - the verification harness went back to `selfimprove` (the thirteen stocks are kept in the tests);
  - the review screenshot and the redesigner's transcript dump went;
  - in the changeset code: `Scratch.unified` and its own section map;
  - `version()` now uses `_numbers`; there is one `WORDING`; the redesigner's settings come from `use: modelling`;
  - a queue's goal and a guessed process are now control requests held for the owner, and the rule tier keeps
    units only.
- Net lines outside `tests/` and `docs/`: +3,667.
- Suites (fast commands under `suite_watch`, one at a time):
  - unit: rc 0, 1,667 passed, 1 xfailed. The 13 skips are page files without playwright (they run in the browser
    suite) and VictoriaMetrics;
  - ruff: rc 0;
  - `demo_check` on the four: rc 0;
  - browser: 216 passed, 1 failed, only the coordinator's `open=*` routing at the 20 s bound (20.0 s), which
    `fastroute` is fixing.
