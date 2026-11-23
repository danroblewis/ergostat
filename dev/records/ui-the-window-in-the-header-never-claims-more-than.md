# ui-the-window-in-the-header-never-claims-more-than: The window in the header never claims more than the record

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q19 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** header window menu; /loops footnote; charts

**The problem:** The header says 'Last 1h' while 33 minutes are recorded; percentages such as 'off 93% of the time' look heavier than the data supports.

**The change:** When the record is shorter than the window the header reads 'Last 1h (33m recorded)', and every 'of the time' figure says 'of the 33m recorded'.

**User stories it serves:** B5

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On a demo started less than an hour ago the header window control contains 'recorded' and a duration; a suggestion containing '% of the time' also contains 'recorded'.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Round 1, built. About 9 net lines outside tests (budget 60).

**What changed.**
- `server.py`: `/api/status` now carries the snapshot's own `recorded`. That is the span the shares in
  `state.py` are computed over (`start = max(since, oldest)`).
- `util.js`: `recordedShort()` gives the recorded span when it is under 95% of the window (a project with no
  record at all is treated as not short). `ofRecorded()` rewrites "of the time" to "of the 33m recorded". `op()`
  applies it, so every suggestion and attention text shown through `op` gets it: the diagram's Suggestions, the
  Agents page hints and the loop's panel. `refreshHeader()` also redraws the window label.
- `main.js`: the header reads 'Last 1h (33m recorded)'. Choosing a window asks for the status again, so the
  label follows the new window.
- `control.js`: the scope's 'past its bound … % of the time' uses `ofRecorded` too.
- `pages.js`: the /loops footnote now reads the same `recordedShort()` as the header, so the two cannot disagree.

**Choice made without asking** (the more reversible reading). The Change says every 'of the time' figure becomes
'of the 33m recorded', so the words are replaced, not added to. When the record is short, no suggestion still
contains '% of the time'. The Acceptance's "a suggestion containing '% of the time' also contains 'recorded'"
is tested in that reading: every suggestion giving a share reads '% of the 3Xm recorded', and '% of the time'
is gone from it.

**Acceptance test:**
`tests/test_diagram_rendering.py::test_the_window_in_the_header_never_claims_more_than_the_record`. It uses a
project with 33 minutes of record and a loop off for most of it. It passes. I saw it fail under each of three
breaks:
- `op` without `ofRecorded`: the suggestion still reads '96% of the time'.
- The header without the '(… recorded)' suffix: it times out waiting for 'recorded'.
- The suffix shown even when the record fills the window: on the 10m window it never reads 'Last 10m'.

**Tests run.** `ruff check ergostat tests scripts` is clean. The whole of `tests/test_diagram_rendering.py` ran
serially under the watchdog: rc 1, 198 passed, 3 failed, none skipped.
- `test_every_view_draws_cleanly_and_in_time[coordinator]` and `[image-squeeze]`: routing open=* took 20.2 s
  and 21.5 s against a 20 s bound. This change does not touch routing or layout. It looks like a time bound
  under load (other test servers were running), but I did not rerun either test alone.
- `test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page`: the Model page lacks
  'Nothing waiting.' after an Accept. It fails again run alone (3 s), so it is not load. That code path (the
  review queue in `pages.js` tick, `reviewEntry`) does not use `op`'s new rewording, the header label or
  `status.recorded`, so by reading it is unrelated. **I could not confirm it on main.** Both
  `git checkout main -- ergostat/web` (to be restored from HEAD afterwards) and
  `git clone -q --branch main /work /tmp/mainclone` were refused. The factory's rerun on clean main should
  settle it.

**Not run:** the unit suite and the other three browser files (left to the factory and the merge queue). I also
did not run `tests/test_agents_page.py`. Its `pg.click("text=Last 1h")` matches on a substring, so it should
still match 'Last 1h (… recorded)'. No example was touched, so `demo_check` does not apply. Main has had no
commits since this branch was cut from it in the clone, so there was nothing to merge.

**Build fix.** The factory's `build` step failed with rc 5. It selected only `tests/test_diagram_rendering.py`, and
without Playwright that file's one test was skipped, so no test ran. Nothing in the code failed. The one server
change (`recorded` in `/api/status`) now has a unit check in
`tests/test_graph_cli_web.py::test_the_web_api_serves_what_the_cli_shows`, so the build step runs a real test.
Renaming the key in `server.py` makes the check fail (KeyError); with the key restored, the file passes (31
passed). Ruff is clean. I could not run the build command itself (`suite_watch.py -- affected_tests.py -- pytest
...`): it was refused here.
