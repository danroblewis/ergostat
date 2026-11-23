# fix-process-rework-flag: the Process view counts rework only when an item repeats a step

Confirmed 2026-11-23 in `ergostat/process.py`, `process()` (about line 474). The Process view reports concurrency as rework. Smallest failing case: two items, one doing steps `x, y` and the other `y, x`: nothing is repeated, yet passages are flagged as rework. A synthetic log with no repeated step showed 94 false rework passages.

See `docs/research/2026-11-23-charts/catalog.md`, item B1 and section 7.2.

Change.
- A passage is rework only when the same item returns to a step it has already done. The order in which different items take steps never counts.
- Show the count of returns.
- Where SPEC defines rework in two ways, keep one definition: a repeated step. Update SPEC.

Definition of done.
1. Two items doing `x, y` and `y, x` show no rework.
2. One item doing `x, y, x` shows one return.
3. A generated log with concurrency and no repeated step shows zero rework; the same log with known returns shows exactly those.
4. The existing process tests pass, or a test records a deliberate change.

## Where it stopped

Built, round 1. Everything the definition asks for is done; nothing is left.

- `ergostat/process.py`: as each item's lines are walked, it keeps the set of steps that item has done. A passage is
  a return when its target is already in that set. Each `follows` line gets `returns` (how many) and is `rework`
  when `returns > 0`, and each kind in `kinds[]` gets its total `returns`. The old rule, a line running back in the
  kind's order or round to one step, is gone. Layout still uses that order, so a line to an earlier step is still
  drawn running back.
- Choices made with nobody to ask (the most reversible ones, each a line or two to change):
  - A line is rework when any passage along it is a return, so a line that runs forward can be rework. In the
    existing states test, flag 3's second move into `researched` is now a return on `researching → researched`. That
    test records the change.
  - By States, states an item entered before the window count as done (its moves are already read). By Events, only
    the events in the window count, because earlier ones are not read.
  - The line itself keeps its plain `↺` marker. The number of returns is in the line's panel (`returns`) and in the
    node panel's list of lines (`rework ×N`), so the label widths used in layout do not change.
- SPEC §5b: the `rework` row now says a repeated step, which matches §5a's "rework is a repeated step". §12l's
  coherence row no longer treats ↺ as the same thing as a move back in order. The coherence check
  `rework-without-flow` itself is unchanged; changing it is outside this gap. The agent guide, its skill copy,
  MODELLING-WELL, the legend and the `follows` help text are updated to match.
- Acceptance tests, all in `tests/test_process.py`:
  - done 1: `test_two_items_in_opposite_orders_show_no_rework`
  - done 2: `test_one_item_coming_back_to_a_step_is_one_return`
  - done 3: `test_a_concurrent_log_with_no_repeated_step_shows_no_rework_and_its_planted_returns_exactly`
  - also: `test_a_state_entered_before_the_window_counts_as_done`
  - done 4: the assertions added to `test_states_count_the_moves_with_their_median_times_start_end_and_rework`

  Each runs by States and by Events.
- Checked that the tests can fail:
  - With the old order rule put back, 5 tests fail: done 1 and done 3 in both readings, and the recorded change.
  - With the states before the window ignored, the before-window test fails.
- Tests run:
  - `tests/test_process.py`: 19 passed.
  - `tests/test_remote_lines.py`: 20 passed.
  - `tests/test_daemon_docs.py` and `tests/test_daemon_yaml_review.py`: 62 passed.
  - Three Process-view tests in `tests/test_diagram_rendering.py`, under `suite_watch` with Playwright: 24 passed,
    rc 0, none skipped.
  - ruff is clean.
  - Not run: the whole unit suite and the four browser files, which the factory and the merge queue run.
- `main` had not moved since the branch began (the merge base is `main`), so there was nothing to merge.
