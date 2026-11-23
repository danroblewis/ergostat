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
- The block's `in`/`out` need parts to name, so dev/model/landing.yaml also gains a stock `flakes-main-broken`
  (sensor: flake items in main-broken), a flow `flakes-mended` out of it (sensor: entering fixed with fixed_by
  main-mend) and an estimated parameter `mend-time` (1h). The model-loading and `ergostat check` tests in
  tests/test_factory.py pass with them. Removing them means removing the block's in/out lines too.
- Round 2 (no review findings to answer): main had not moved since the last merge (a72d29ea). Ruff is clean;
  tests/test_factory.py gave 204 passed, 2 skipped (both need Docker and the agent image); tests/test_changesets.py,
  tests/test_spec_items.py and tests/test_fac_items.py pass. Seen to fail: with the ancestor check in mend.py
  removed, `test_main_mend_writes_only_where_the_items_main_is_the_commit_run_on_or_an_ancestor` fails.
- The build's failure, `test_an_approved_switch_drains_and_switches_through_the_engine` (a switcher run past its
  120 s wait under the suite's load), is not this branch's, so no code changed for it (lesson-13). It passes alone
  here in 118 s. Timed with temporary marks, since removed: each of its two switcher runs (dev/bin/drain.py, about ten
  `ergostat item` calls) takes 27 s and 26 s with this branch's model, and 27 s and 26 s with the main-mend block,
  stock, flow and parameter taken out of landing.yaml. With the items.py line off, it took 34 s and 48 s (machine
  noise, not slower). Nothing in this branch runs on the switcher's path (drain.py reads upgrade, gap, research and
  situation items, not flakes). Not run: main itself (a second worktree was refused here). Left: the queue's run on
  clean main tells whether the 120 s wait is tight for main under load, which is a gap of its own (lesson-10).
- Round 3 (no review findings to answer): main had not moved since the last merge (a72d29ea, main at ead497d1), so
  no code changed. Ruff is clean; the five acceptance tests pass, and so do tests/test_spec_items.py (7),
  tests/test_changesets.py (58) and tests/test_fac_items.py (8). The whole of tests/test_factory.py was not run again
  this round (it gave 204 passed, 2 skipped in round 2, on the same code).
- Round 3, the build (`-n 8 --dist worksteal` on tests/test_factory.py) failed: its tail stops after 24 results with one
  `F` and no summary, so the failing test is not named and could not be checked against this branch. Serially, here,
  tests/test_factory.py gives 204 passed, 2 skipped (943 s). Found and fixed while looking: the mend tests' `mend.main()`
  ran `fac.stop_on_term()`, which left a SIGTERM handler (`sys.exit(143)`) in the pytest worker for every later test.
  The fixture now replaces it with a no-op (tests/test_factory.py, one line). Nothing on test_factory.py's path forks,
  so this probably did not cause the `F`; it could have reached forked tests (keeper.py, test_sandbox_attacks.py) in
  the merge queue's unit suite. Not run: the file under xdist (named_tests.py runs serially and takes no options).
  If the `F` comes back, it needs its name from the build's full log.
- Round 3, the build again (`-n 8`): it names `test_an_approved_switch_drains_and_switches_through_the_engine`, a
  switcher run still under way at its 120 s wait (1 failed, 203 passed, 2 skipped, 648 s). No code changed, because no
  cause in this branch was found. Checked: (1) mend.py and its tests leave no state in the pytest worker that
  the switcher's subprocesses could inherit. No environment is written (fac.cli is not called), no cwd, and no
  signal handler (stubbed since c7fee7cb). Every fac attribute and the flakes module are put back by monkeypatch,
  and the race test's thread is joined. (2) The `ergostat item` calls drain.py makes never run the extremes
  (model.py: problems are late). The block, stock and flow this branch adds are not on the switcher's path, and
  timed alone they changed nothing (27 s and 26 s per run either way, round 2). (3) items.py's line runs only on a
  refused event. A run that takes 27 s alone and more than 120 s here is load (lesson-10: neither a race in ergostat
  nor a sleep in the test, but a fixed wait over about ten cold `ergostat` starts). Making the switcher cheaper
  (fewer `fac.items` listings in drain.py's under_way) is in drain.py and fac.py, outside this gap's Files list
  (lesson-13), and the bound is not to be raised. That is the most reversible choice: nothing outside the gap is
  changed on a guess. Left: a gap of its own for the switcher test's cost under `-n 8`, or the factory's rerun of
  this test on clean main under the same load. If it fails there too, it is not this branch's. Not run: main under
  load, or any command but git and file reads (others were refused this session).
- Round 4 (no review findings to answer): main (5411f137) was already merged into the branch (231b15cf). I read the
  merge's three shared texts (dev/README.md, dev/factory.toml, ergostat.yaml) and found nothing spliced. Main's
  fac.py change (`suite(group=...)`, `stop_suites(group)`) keeps its defaults, so mend.py's calls are unchanged. Ruff
  (`ergostat tests scripts`) is clean. The five acceptance tests pass (3 in 14 s, 2 in 67 s), and so do
  tests/test_spec_items.py, tests/test_changesets.py and tests/test_fac_items.py (73 passed). `ruff check dev/bin`
  finds two errors in main's dev/bin/plan.py:439 and dev/bin/review.py:43; neither file is touched here (lesson-13).
  Not run: the whole of tests/test_factory.py after this merge. The background run of `uv run python
  scripts/suite_watch.py -- uv run python scripts/named_tests.py tests/test_factory.py` was refused, and the file
  takes about 943 s serially, longer than a foreground call is allowed. The build step runs it.
- Round 4, the build (`-n 8 --dist worksteal` on tests/test_factory.py) failed with no test named: its tail stops
  after 8 results (no `F`, no `E`, no summary). That fits the suite stopped by `[suites] stall_minutes = 10` (no
  output for 10 minutes), the same shape as round 3's first build. No code changed, because no cause in this branch
  was found. Read and ruled out: the mend tests stub every wait (fac.wait_quiet, fac.suite, pushed, tree,
  fac.quarantine, stop_on_term). flakes.held() locks a file under the test's own tmp_path (fac.config is not cached,
  and FACTORY_CONFIG is set per test). No other dev/bin writer sends a `patch` event, so the items.py line (a refused
  patch or set moves nothing) cannot hold back another block's move. Main's merged fac.py change (`suite(group=)`,
  `stop_suites(group)`) keeps its defaults, and mend.py's calls are unchanged. Refused this session, as given:
  `uv run python scripts/suite_watch.py -- uv run python scripts/named_tests.py tests/test_factory.py` (in the
  background), `timeout 580 uv run python -m pytest -q -rfEs -n 8 --dist worksteal -o faulthandler_timeout=240
  tests/test_factory.py` (to name a hung test from its stack), and a python3 script editing this file. So the whole
  file was not run after the merge of main. Left: the build's full log or a faulthandler dump to name the test that
  stops. A stall that also happens on clean main under `-n 8` is not this branch's (lesson-10, lesson-13).

Overrun reason: 160 net lines against 150 (131 in mend.py, 24 in landing.yaml); the 10 over are the stock, flow and parameter the block's in/out must name, which the definition's estimate did not count.
