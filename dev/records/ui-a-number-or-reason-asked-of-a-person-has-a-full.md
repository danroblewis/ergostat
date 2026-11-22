# ui-a-number-or-reason-asked-of-a-person-has-a-full: A number or reason asked of a person has a full label and a unit

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q45 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram side list inputs

**The problem:** Inputs are 80 px wide with placeholders cut to 'how ma' and 'why (to de'. 'how many' has no unit; it appears even on a yes or no decision ('declare an incident?'). The reader cannot say what a typed number means.

**The change:** A visible label above each input, from the ask: 'Ramps you decided (number)', 'Reason for denying (required)'. Inputs take the row's width. An ask whose answer is yes or no gets two buttons, not a number box.

**User stories it serves:** E2, H5

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
Every input in the side list has a visible <label> whose text is fully shown (scrollWidth ≤ clientWidth) and, for a number, names a unit; no placeholder is truncated.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Round 1: built. About 28 net lines of code outside `tests/` and `docs/`.

- The side list's answer row (`ergostat/web/static/diagram.js` `inboxAnswer`, `style.css` `.inbox-act`): each input
  sits in a `<label>` with its text above it and no placeholder, and fills the row's width. The number says
  "<Unit> done, along <flow> (number)" and the reason says "Reason for denying (required)" for a modelling request
  (its deny needs `--note`) or "(optional)" for anything else.
- Outside `ergostat/web/`, which the definition's Files list does not name: the page did not know a person's unit, so
  `ergostat/inbox/entries.py` (`_done_in`) adds `flow`, `unit` and `yes_no` to a person entry and `ergostat/state.py`
  passes them on into the attention list. It only adds keys, so it is easy to undo.
- Choice made without the owner (the most reversible one): "an ask whose answer is yes or no" is taken to be a person
  block whose `out:` has two named ends (the-job's `declare-incident`: `declared`, `dismissed`). It gets Yes (`n=1`)
  and No (`n=0`), and what is recorded is unchanged: `person_done` still moves only the first flow, so No moves
  nothing along `dismissed`, which is what typing 0 did before. Sending each answer down its own flow would change
  the answer path, which belongs in a gap of its own. The unit is the flow's own unit, else its stock's, else the
  flow's name.
- The row now has `sig: a.what`, so a refresh keeps it whole while its entry waits. Without it, the handlers a
  refresh handed over read the newest build's (empty) inputs, and `test_approve_in_the_side_panel` failed: the
  reviewer's typed 2 was lost and the row never went. It passed again once the sig was added. Main was not run to see
  whether this already failed there.
- SPEC §12o's page paragraph says what the labels and Yes/No are.
- Tests: `tests/test_inbox_page.py::test_every_answer_in_the_side_list_has_a_full_label_and_a_number_its_unit` (new)
  and the existing test both pass under the watchdog with Playwright (rc 0, none skipped); `tests/test_inbox.py` and
  `tests/test_gated_actions.py` pass; ruff is clean. Breaks seen to fail the new test: inputs back to 6em, yes/no
  ignored, the unit dropped. The four browser files and the unit suite were not run here (the merge queue runs
  them). There is no origin/main in the clone and main has not moved since the branch was made.

Round 1, after the build step: `build` failed with rc 5. It ran only `tests/test_inbox_page.py`, because
`ergostat/inbox/entries.py` and `ergostat/state.py` have no `tests/test_<module>.py`. Without Playwright that browser
file skips entirely, so pytest collected nothing. No code was wrong. The new unit test
`tests/test_inbox.py::test_a_persons_entry_says_what_its_number_moves_and_whether_it_is_yes_or_no` covers the keys
`_done_in` adds and that `attention` passes them on. It also puts `tests/test_inbox.py` in the build's selection.
It passes, and it was seen to fail with `yes_no` forced to False. `tests/test_inbox.py` passes (31), and ruff is clean.
The browser file was not run again in this session.
