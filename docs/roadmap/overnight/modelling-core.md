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

Stopped at 10:50 on 2026-11-19 at the coordinator's cut-off (green by 11:15 was not reachable). Nothing here is ready
to merge.

**Done** (on a09c176; not yet rebased onto main 945ccea, where closedloop, observer and extremes touch
`review.effect`, `proposals.accept` and `judge.run`, so expect conflicts there):
- the split: what the review passed came in whole (squashed from `selfimprove` and `redesign`), then the parked parts
  were taken out (the rule tier's first-order and measurable equations, its chain and structure copies, event-type
  renames that edit programs, and `formerly:` on item kinds). The rule tier keeps units, a queue's goal and a process
  nobody identified. The craft bench is in `scripts/craft_bench.py`; the harness's ports avoid 8798. `selfimprove`
  has its "Where it stopped";
- fix 1: `improve.governs`. A proposal or change set that changes the judge's policy, a block's `accept` or a
  template instance's `with:` is refused. A redesign that removes a part, rewires a chain (`structural.rewired`) or
  changes control is the owner's to write even under `redesign: auto` (`judge.owners`);
- fix 2: a rename is a rename only when the structure, the control and every sensor are unchanged
  (`version.renamed_parts`);
- fix 3: `rewires` is worked out from what a change does (`structural.rewired`) in `improve.validate`, whoever made
  it;
- fix 5: a promoted redesign that cannot be written is superseded, and the pass goes on to the rest;
- fix 6 (code done, untested): an owner's ask is only recorded (page and CLI), and the redesigner block takes it up.
  There is no thread in the page server. The AI tier and the redesigner print result lines (`modeller.result_line`);
- `when: auto` is parked (`ask` is the default). Redesign runs stop at a daily cap (`redesign: {daily: 2}`,
  `redesign.spent`). "Redesigns judged not better" is gone from the Model page: the ask line links to the last
  run's item. `unanswered-requests` counts only open and proposed requests, so `requests-handled` can be met.

**Left:**
- fix 7: the redesigner reading `MODELLING-WELL.md` through `helpdocs`;
- `redesigner.run` still replaces `p.model` in its own process before submitting;
- carried redesigns checked again; rollback of a multi-file write; `keep_history`'s result stored;
- `chains.boundary`'s exception scoped to the template's own parts (the general version from the rebase is still
  here);
- the tests: `tests/test_modelling_core.py` (the acceptance tests named above) is not written. Four tests in
  `tests/test_redesign.py` still assert the superseded behaviour (auto triggers; a chain-rewiring redesign written
  under `redesign: auto`; promotion first and alone) and fail: they need rewriting to the new rules;
- the SPEC and proposal text for the above, the rebase onto 945ccea, and the four suites.
