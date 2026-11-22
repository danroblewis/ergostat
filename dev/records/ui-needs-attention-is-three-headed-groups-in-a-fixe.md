# ui-needs-attention-is-three-headed-groups-in-a-fixe: Needs attention is three headed groups in a fixed order

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q42 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram side list

**The problem:** 'Needs attention 4' beside '2 loops off': one list mixes goals that are off, asks of a person, requests and model notes, told apart only by red or amber. On big 24 requests bury the one alarm.

**The change:** Three headings, always in this order, each with its count: 'Waiting for you 3', 'Goals off 2' (the system's first, modelling's after a rule), 'Model housekeeping 25' (collapsed). Each entry starts with its state word ('off ·', 'unknown ·') so colour is not the only cue. The count in the header equals the 'Goals off' group.

**User stories it serves:** E1, B2, H5

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8791/ the side list has three headings in that order, each ending in a number; the 'Goals off' number equals the header's; no entry's kind is conveyed only by colour (each begins with a state or kind word).

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Round 1, built (commit cd71c13e). About 25 net lines outside tests: `ergostat/web/static/diagram.js` (renderSide),
`ergostat/web/static/style.css` (3 lines), and `ergostat/state.py` (6 lines).

What it does: the side list's one "Needs attention" list is now three headings, always in this order, each ending in
its count: "Waiting for you N" (the inbox's asks, and the reports upstream line), "Goals off N" (loops whose status is
off: the system's goals first, then an `hr` rule, then the goals of a `use: modelling` instance), "Model housekeeping N"
(everything else, in a `<details>`). Every entry begins with a word and " · ": the loop's status (off, unknown, stale,
open), "waiting", "fault" (a bad entry that is not a goal: an alarm, a failed daemon or agent, a dead letter), or "note".

Choices made with nobody to ask (the most reversible in each case):
- `state.py` is outside "Files to touch" (it lists only `ergostat/web/`). The page cannot tell which goals are
  modelling's or what state a loop entry is in from what it is sent. So `state.attention` now adds `state` (the loop's
  status) and `modelling: true` to each loop entry, and `waiting: true` to the reports-upstream line. These are only
  extra keys, and nothing else reads them.
- Housekeeping starts folded, except when it has a "fault" entry. That way an alarm or a failed daemon is never hidden,
  which is the problem the review described. Once the reader opens or closes it, it stays as they left it
  (`S.houseOpen`, the same way Suggestions works).
- The old cap of six entries with "N more on Loops and Model" is gone. Every ask shows, so each one can be answered
  where it is listed. Every goal off shows, so the list matches its count.
- The reports-upstream line is counted under "Waiting for you": it is for the owner to read and submit.
- Known edge: the header's "N loops off" counts every loop. `state.attention` leaves out a remote's own loops ("its
  business, said on its own page"). In a model with a remote loop that is off, the two numbers can differ. No example
  on main has one, and changing the header is outside this gap.

Tests:
- New: `tests/test_diagram_rendering.py::test_needs_attention_is_three_headed_groups_in_a_fixed_order`. It covers `/`
  and `/diagram?view=blocks`, with one ask, the system's goal off and modelling's goal off. It passes (rc 0, under
  suite_watch, with Playwright 1.63.0).
- Checked that it can fail (lesson-9). Each break below failed it at the expected assertion:
  - the state-word span removed;
  - the modelling sort reversed;
  - the server's modelling flag broken.
- Also passing: `tests/test_inbox_page.py`,
  `tests/test_items_page.py::test_a_reports_page_shows_its_text_a_copy_button_the_issue_link_and_the_scrub_log`,
  `tests/test_inbox.py` and `tests/test_dynamics_view.py`. ruff is clean.
- Not run: the whole of `tests/test_diagram_rendering.py`. The command
  `uv run python scripts/suite_watch.py -- uv run --with playwright==1.63.0 python scripts/named_tests.py tests/test_diagram_rendering.py`
  was refused. The unit suite and the other browser files were not run either: they are left to the factory and the
  merge queue.
- No merge of main: local `main` is this branch's base.

Round 1, build fix: the factory's `build` step (`scripts/affected_tests.py`) picked only
`tests/test_diagram_rendering.py`. There is no `tests/test_state.py` for the `state.py` change. The build has no
Playwright, so that file skipped as a whole and pytest returned rc 5 (no tests ran). No code was at fault. This round
adds the missing unit test for the `state.py` change, so the build now also runs `tests/test_inbox.py`:
`tests/test_inbox.py::test_each_loop_line_carries_its_state_and_whether_the_goal_is_modellings`. It checks three
things: each loop entry's `state` is its status; only the `use: modelling` goal is marked `modelling`; the
reports-upstream line is marked `waiting`. It passes, and so does the whole of `tests/test_inbox.py` (31 passed).
Checked that it can fail: with the modelling match broken in `state.py`, it failed (KeyError 'modelling'). No code
outside tests changed.

Round 2, the review's two findings:
- Finding 1 (blocking): modelling's held requests filled "Waiting for you". Fixed. `state.attention` now passes each
  inbox entry's `kind` (one more key on the asks; nothing else reads it). The page counts an entry with answers as
  "Waiting for you" only when its kind is not `request`. Modelling's held requests (`request/…`) go under "Model
  housekeeping", each starting "request · ". They keep their answer controls there, so they can still be answered
  where they are listed. Choice made with nobody to ask (the most reversible one): model changes waiting for approval
  (`change/…`) stay under "Waiting for you". They are a person's approval of a change, not a note. Moving them is a
  one-word change in `ask` in `diagram.js`. Net code outside tests is still about 27 lines, inside the budget of 60.
- Finding 2 (blocking, lesson-9): the browser test now seeds two held `ergostat.modelling-request` entries. It checks
  that "Waiting for you" holds only the person's ask (one row, no `request/`), and that both requests are under
  "Model housekeeping" and start with "request · ". The unit test in `tests/test_inbox.py` also checks that a held
  request's attention entry has `kind` `request` and that the person's ask does not.
- Checked that both tests can fail. With `ask` reverted to taking every entry that has answers, the browser test
  failed (`assert (3 == 1)` on the "Waiting for you" rows). With `kind` broken in `state.py`, the unit test failed
  (`assert 'x' == 'request'`). Both pass again on the restored code.

Tests run in round 2 (rc 0 unless stated): the acceptance browser test, under suite_watch with Playwright 1.63.0;
`tests/test_inbox_page.py` (browser); `tests/test_inbox.py` (31 passed). ruff is clean.
Not run to the end: the whole of `tests/test_diagram_rendering.py`. It was started under suite_watch, ran for over
20 minutes with its output buffered, and was stopped at the session's time limit with no result. It was not
restarted, since it is one of the four browser files left to the merge queue. The unit suite and the other browser
files were not run either. No merge of main: local `main` is this branch's base.
