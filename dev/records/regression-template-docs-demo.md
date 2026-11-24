# regression-template-docs-demo: SPEC and the agent guide describe regression guarantees, and a demo uses the template

depends-on: [regression-template]

## Problem

Once the `regressions` template exists, nothing tells a user or an agent when to offer it, and no demo shows it working (proposal milestone gap 7: "SPEC gains a section on regression guarantees, and the agent guide a paragraph on when to offer the template").

## Change

- docs/SPEC.md gains a short section next to 12g (claims and trust) and 12r (repair). It covers the four parts of a guarantee (measured quantity, setpoint, a loop that acts, seen broken on the diagrams), the template's parts, and what holding does not promise (proposal section 6c).
- docs/AGENT-GUIDE.md gets one paragraph: offer the template when a model declares `claims: tests` or uses `repair`, never add it unasked.
- examples/image-squeeze, which declares `claims:` (examples/image-squeeze/lab.yaml:43), uses the template.

## Definition of done

1. The SPEC section and the guide paragraph exist and match the template's parts.
2. image-squeeze uses it and passes `demo_check`.
3. Its goals hold in the healthy demo.

## Files to touch

docs/SPEC.md, docs/AGENT-GUIDE.md, examples/image-squeeze/lab.yaml, tests (the demo's own check, if one names its goals).

## Acceptance tests

- `scripts/demo_check.py image-squeeze` passes.
- `ergostat check` on the example: no errors.

## Size budget

20 net lines outside docs/ and examples/.

Area: regression. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Round 1: built, except that `scripts/demo_check.py image-squeeze` and `ergostat check` as a command could not be run
here. Both commands were refused in this session (`uv run python scripts/demo_check.py image-squeeze`,
`uv run python -m ergostat -C examples/image-squeeze check`). `ergostat check` is run instead in-process by the
acceptance test (`main(["-C", ..., "check", "--json"])`: ok, no error). demo_check is left for the merge queue.

- **SPEC**: a subsection *Regression guarantees: `use: regressions`* at the end of 12r, with a pointer from the end of
  12g and from the template's entry in 2a. It gives the four parts of a guarantee, a table of the template's parts
  (parameter, auxiliary, goal, person block), how an unreadable run counts, and what holding does not promise
  (proposal 6c, applied to the template's own goals). It is a subsection, not a new lettered section, since 12g and 12r
  are not adjacent and 12s follows 12r. That is the reversible choice.
- **Agent guide**: in step 9, one paragraph. Offer `use: regressions` when a model declares `claims: tests` or uses
  `repair`, add it only when the person says yes, and only the parts they ask for. It also says what holding does not
  promise. The sentence the regression-template gap had put mid-paragraph was moved into it.
- **image-squeeze**: `uses: regressions` in lab.yaml with `every: 5m`, `timeout: 3m` and `changes: true`. `block:` is
  left out because `developer-honest` already holds `ergostat.trust.contradicted@developer`, and a second goal on the
  same measure would say the same thing twice. `regressions` is declared in ergostat.yaml as a top-level system, beside
  lab and modelling. Inside lab, the lab's drawing grew past its recorded size and gained a critical flow-excursion
  (messages-delivered). As a system declared in lab.yaml, it took lab's `defaults: system:`.
- **The seed's tests** (seed/test_squeeze.py) now end with a pytest-style summary (`3 passed, 0 failed in 0.05s`) in
  place of `ok: 0 failed`, which the reader cannot read (it gave no value, so tests-green was never read). Nothing else
  parsed that line. The exit code is unchanged, so the claim check is unchanged.
- **The reader** (ergostat/regressions.py, +6 net): it waits for the claim's `in:` folder within its time, and with
  its shell gone it stops. The demo's `run/product` is made by the customers block's first run, which starts in the
  same pass as the first reading. Losing that race crashed the reader (FileNotFoundError), so tests-green stayed
  unknown until the next reading 5 minutes later, and demo_check fails a loop that is `unknown`. A folder never made
  still gives no value, never 0. The SPEC table and the module docstring say so.
- **Fixtures**: tests/fixtures/diagram_sizes.json `image-squeeze/open=lab` is now 2715x1958 fit 0.44 (was 2528x1691
  0.49), and layout_known.json raises image-squeeze's `satellite-far` ceiling from 24 to 27. These are the values the
  test measured with the new box. They were written by hand because the recording run (`RECORD_SIZES=1 RECORD_LAYOUT=1
  ...`) was refused here. The new views (`open=regressions`, `system=regressions`) have no recorded size yet. The +3
  satellite-far are taken to be the new system's two cloud inflows (tests-fixed, changes-corrected) across its views.
  That was not shown instance by instance.
- No `## Entry` was added: the definition allows only this section to be appended, and the sibling regression records
  have none.

Tests: tests/test_image_squeeze_regressions.py (3: `test_image_squeeze_uses_the_template_and_checks_clean`,
`test_its_goals_hold_in_the_healthy_demo`, which runs the seed's real tests through the sensor, reads 0 and 0, and
evaluates both goals `holding`, and `test_the_reader_waits_for_its_test_folder`). Seen to fail: with the seed's old
summary line, the healthy test fails ("exited 0 with no test summary"). With the wait removed, the folder test fails
(FileNotFoundError).

Run here, each passing: those 3 with tests/test_regressions_template.py (21 in all). The unit files that load every example or
image-squeeze: test_blockdiagram, test_correspond, test_finished_states, test_extremes_closed, test_dynamics_view,
test_architecture, test_modelling_core, test_item_systems, test_chains, test_changesets, test_cloud_arrivals,
test_daemon_docs, test_graph_cli_web, test_rollup and test_scale_caches. In test_diagram_rendering.py, the
image-squeeze cases of: every_view_draws_cleanly_and_in_time, each_polarity_sign..., the_dynamics_view_draws_only...,
every_lines_panel..., every_process_view..., model_errors_drain..., every_view_loads_with_no_console_error...,
the_readers_pages..., the_control_view_draws_every_example... (image-squeeze alone), plus
an_examples_closed_modules..., a_module_counts_its_loops..., a_closed_systems_panel_charts... and the other examples'
cases of sensors_polled_alike and every_block_carries_a_function. ruff is clean.

Failing, not this gap's (lesson 13):
- `test_diagram_rendering.py::test_the_dynamics_view_speaks_system_dynamics_and_marks_only_loops_whose_sign_is_known`
  fails the same way with this branch's use and system commented out, which is main's model. The side panel's "open ·
  goal developer-honest cannot close ..." lines contain the control word "goal", and those three open loops are main's.
- `test_the_control_view_draws_every_example_cleanly_as_a_block_diagram` across all examples timed out once in a
  wait of 240 s (Page.wait_for_function), on one example's case, twice in three runs. The third run passed whole. Its
  image-squeeze case passed alone. Which example timed out was not captured.

Not run: the unit suite as a whole, the four browser files whole (test_items_page, test_page_polling and
test_page_refresh all serve image-squeeze), demo_check, and the merge of main (main is this branch's base, unchanged
since the clone).
Overrun reason: counted as the factory counts (outside tests/, docs/ and dev/), it is 23 net lines: 6 in the reader, which the wait for the demo's test folder needs, and 17 in examples/image-squeeze (the use, its system, the seed's summary line). The definition's own budget leaves out examples/, and by it the branch is 6 lines.

Round 2. One finding, blocking: the reader waited only for run/product to exist, but `lab.py init` made the folder
before it copied the seed's files into it, so a reading that landed in that window ran no tests and gave no value.
- **Fixed in the model, not the reader**: `lab.py init` (examples/image-squeeze/bin/lab.py) now fills `run/product.new`,
  makes its git repository there, and renames it to `run/product` before adding production's worktree. A reader that
  sees the folder sees it whole. A leftover `product.new` from an init that died midway is removed first. That folder is
  init's own, under the demo's `run/`. This is the more reversible option (the finding's first suggestion). A readiness
  signal would have meant a new convention in the reader and in SPEC. The init still holds lab.py's lock, as before.
- **SPEC** (the template's table, `tests-failing` row) now says the folder is run as soon as it is there, so a model
  makes it whole, and gives image-squeeze's init as the example. The reader's comment says the same.
- **Test**: `test_the_reader_never_finds_the_test_folder_half_made` runs the copied demo's real `lab.init` in a thread,
  with the copy of test_squeeze.py held back 1 s (several of the reader's 0.2 s looks), while `regressions.counts`
  reads. It asserts 0, and that run/product holds the tests and no `product.new` is left. Seen to fail with init
  filling run/product in place (`exited 1 with no test summary`), and to pass with the fix.
- Run here, each passing: tests/test_image_squeeze_regressions.py (4) with tests/test_regressions_template.py (22 in
  all), and test_messages.py::test_image_squeeze_developer_session_takes_a_note_while_it_builds, which runs the
  real `lab.py init` and then builds a hypothesis on a worktree of the renamed repository. ruff is clean.
- Refused again here: `uv run python scripts/demo_check.py image-squeeze`. demo_check is left for the merge queue.
- Not run, as in round 1: the unit suite whole, the four browser files whole, and the merge of main (main is this
  branch's base, unchanged since the clone).
Overrun reason: counted as the factory counts (outside tests/, docs/ and dev/), it is now 25 net lines: 6 in the reader, which the wait for the demo's test folder needs, and 19 in examples/image-squeeze (the use, its system, the seed's summary line, and 2 for init filling the folder before renaming it into place, the round-2 fix). The definition's own budget leaves out examples/, and by it the branch is 6 lines.

Round 3. The queue's batch failed on two tests, both failing again alone. Both are pins of image-squeeze's old shape
that this gap's change makes stale, and they are fixed in tests only. Nothing outside tests/ and dev/ changed.
- `test_blockdiagram.py::test_closed_systems_are_subsystem_blocks_and_vectors_join_them` listed image-squeeze's
  closed systems exactly. `sys:regressions`, the system this gap declares, is now in the list.
- `test_observer.py::test_models_that_use_none_of_it_record_what_they_did_without_it[image-squeeze]` asserted that
  no example asks anything of the observer. The template's goals (tests-green, changes-hold) declare `on-stale: off`
  (the regression-template gap's template.yaml, as SPEC says: off while stale), so image-squeeze now asks that of it.
  The test now leaves out the examples named in `ASKS`, and a new test,
  `test_an_example_that_asks_the_observer_asks_only_what_is_listed`, asserts that each one asks exactly the goals
  listed (image-squeeze: those two, `off`) with no stocks and no blocks. So another example cannot slip out of the
  first test without being listed, and image-squeeze cannot ask more than the template's goals. The template was not
  changed (it is the regression-template gap's). The new test was not seen to fail: it compares the real opted value
  with the listed one, and it passed on the first run.
- Run here, passing: tests/test_blockdiagram.py and tests/test_observer.py whole (167). ruff is clean.
- Refused again here: `uv run python scripts/demo_check.py image-squeeze`.
- Not run: the unit suite whole and the four browser files whole (the queue runs them). Main is unchanged since
  the clone (29cf698d already merges b9341591), so there was nothing new to merge.
Overrun reason: as in round 2, 25 net lines outside tests/, docs/ and dev/: 6 in the reader for the wait on the demo's test folder, and 19 in examples/image-squeeze. Round 3 adds none. By the definition's own budget, which leaves out examples/, the branch is 6 lines.
