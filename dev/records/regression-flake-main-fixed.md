# regression-flake-main-fixed: A test broken on main leaves main-broken when it passes twice alone on a newer main

depends-on: [regression-flake-writes-hold-state]

Problem: nothing takes an item out of main-broken (ergostat.yaml:197-200; the only writer is dev/bin/onmain.py:94 and nothing emits fixed), so a stock of tests failing on main would only rise. Change: declare `flake.main-fixed: fixed`. New dev/bin/mend.py as a block main-mend in dev/model/landing.yaml (every 30m, pool 1, a lease, timeout 30m): fetch the pushed main, wait for a quiet machine (fac.wait_quiet), take at most `[gates] mend_most` main-broken items oldest first (default 5, ceiling 20), and run their tests alone twice on that sha in a suite container with -rA (a browser test with the browser suite's command and playwright), results from fac.outcomes over the whole log. A test passing both gets flake.main-fixed with passed_on, main_fixed_at and fixed_by: main-mend, written as a patch changeset whose first op tests the item's `main` as read, and only if that main is passed_on or an ancestor of it, so a newer break written in between refuses it. Failed, skipped, not collected, quarantined or unreadable is unknown and stays main-broken. Done: only two passes on the pushed main clear an item; a refused patch also refuses the state move; at most mend_most a run; dev/README.md describes the block. Files: dev/bin/mend.py, dev/model/landing.yaml, ergostat.yaml, dev/factory.toml, dev/README.md, tests/test_factory.py (five tests). Budget: 150 net lines.

Area: regression. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Built: dev/bin/mend.py and the block main-mend, `flake.main-fixed: fixed`, `[gates] mend_most = 5`, the dev/README.md
paragraph, and the five tests in tests/test_factory.py (`test_main_mend_clears_only_a_test_passing_twice_on_the_pushed_main`,
`test_main_mend_writes_only_where_the_items_main_is_the_commit_run_on_or_an_ancestor`,
`test_a_newer_break_written_in_between_refuses_main_fixed_and_its_move`, `test_main_mend_takes_at_most_mend_most_a_run_oldest_first`,
`test_main_mend_is_a_scheduled_block_and_main_fixed_moves_to_fixed`). Choices made alone, each the most reversible found:

- Outside the Files list, ergostat/spec/items.py (2 lines): the fold moved an item to the event's state even when its
  changeset was refused, so "a refused patch also refuses the state move" could not hold from dev/ alone. Now a refused
  `patch` or `set` moves nothing; a refused `data` event still moves as before (narrowest: blocks' plain data reports
  are unchanged). SPEC §5a and ergostat/help/blocks.md say so. Seen to matter: with the line off,
  `test_a_newer_break_written_in_between_refuses_main_fixed_and_its_move` fails (the item ends `fixed`).
- dev/bin/flakes.py (outside the list, one word): `passed_on` added to REMAKE_CLEARS, so a fixed flake made again
  drops it with main_fixed_at and fixed_by (lesson-5).
- A browser file's test runs with `[suites] rerun` (the browser suite's rerun command, with Playwright, as onmain.py
  reruns browser failures), not the whole four-file `[suites] browser` command.
- The tests picked are run together, twice per command (alone and rerun), not each in its own container: at most four
  container runs, inside the 30 m timeout at mend_most 20.
- `mend_most` past 20 or under 1 is held to the bound at run time; not a whole number, 5 (not refused at config time:
  fac.config is not in the Files list).
- The write holds run/flakes.lock (flakes.held) across the read and the patch, so the patch's `test` op guards only
  against writers outside the lock (fac.add); the test puts such a write between the read and the patch.
