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

Round 2: main (ead497d1) merged in, its six conflicts resolved, and built again. About 19 net lines of code outside
`tests/` and `docs/` against main.

- Main had rewritten the answer row (`inboxAnswer`): buttons that name what they answer, Deny off until a reason is
  typed, the handlers reading the row on the page. The branch's labels and Yes/No are rebuilt on top of main's row.
  The branch's `sig: a.what` is dropped: main reads the inputs from the row on the page, which fixes the
  stale-handler problem the sig was there for. Main's placeholders ("how many", "why (to deny)") are removed, since
  each box now has its label. Main's aria-label on the reason ("Why deny ...") is kept, because main's tests find the
  box by it. The number box takes its name from its label.
- Main's Deny now always waits for a reason, so the reason's label says "(required)" for every entry, not only
  for a modelling request. SPEC §12o says the same.
- Yes and No carry aria-labels in main's form ("Yes to decider's ask (person/decider@N)"), so every button's name
  stays unique and more than one word.
- `entries.py` keeps main's new summary ("X asks: ...", `_cut` gone) and adds the branch's keys. `state.py` keeps
  main's new attention fields and passes on `flow`, `unit` and `yes_no`.
- Test: the yes-or-no person is added only by a new `decided` fixture. Main's fixtures are left as they were, so
  main's position-based tests (`nth(2)`) do not move. The acceptance test now leaves the list after answering,
  because main keeps an answered row until the reader leaves.
- Run here: `tests/test_inbox_page.py` under the watchdog with Playwright: 10 passed, rc 0, none skipped (the slow
  one included). `tests/test_inbox.py`: 34 passed. `tests/test_gated_actions.py`: 11 passed. ruff is clean. Breaks
  seen to fail the acceptance test: a placeholder put back on the reason box, and Yes/No switched off (3 inputs, not
  2). Not run here: the unit suite and the other three browser files (the merge queue runs them).

Round 3: the review's one finding answered. About 16 net lines of code outside `tests/` and `docs/` against main.

- The finding: the yes-or-no rule ("two named ends") also matched the-job's `approve-ramps` (approved / rejected),
  which the definition gives as its number example. It turned that ask into Yes/No, so a rejection never counted,
  and on `declare-incident` the page offered "No" as an answer that records nothing along `dismissed`. Fixed by
  removing the rule: `_done_in` no longer returns `yes_no`, `state.py` no longer passes it on, and the side list
  has no Yes/No buttons. Every person ask keeps its labelled number box. The label names the flow the number moves
  (its first flow, which is what `person_done` records) and its stock's unit: "Ramps done, along ramps-approved
  (number)" and "Outages done, along outages-declared (number)".
- Choice made without the owner (the most reversible one): nothing in a person block says that its answer is yes
  or no. The-job's two person blocks have the same shape, and `person_done` moves only the first flow. A true
  yes/no needs two things this quick UI gap should not add: a model key that says so (`compile.py` allows only
  `ask`, `goal`, `until`, `review` and the common keys on a person), and an answer path that sends No along its own
  end. So the definition's third sentence ("an ask whose answer is yes or no gets two buttons") is left undone: it
  waits for a gap of its own that adds both. The labels, units and full-width inputs (sentences 1 and 2, and the
  acceptance check) are built.
- Tests: `tests/test_inbox.py::test_the_jobs_two_ended_person_asks_keep_their_number_along_the_flow_it_moves`
  (new) loads examples/the-job and checks both real person blocks. `test_a_persons_entry_says_what_its_number_moves`
  replaces the round 2 yes/no unit test. The acceptance test's two-ended `decider` must now show a labelled number
  box ("Jobs done, along declared (number)"), and Done must record the 2 typed into it. Breaks seen to fail them:
  `_done_in` returning nothing for a two-ended block (both tests fail), and the page dropping the number box for
  the two-ended person (the acceptance test fails, 2 inputs not 3).
- Run here: `tests/test_inbox_page.py` under the watchdog with Playwright: 10 passed, rc 0, none skipped.
  `tests/test_inbox.py`: 35 passed. `tests/test_gated_actions.py`: 11 passed. ruff is clean. Not run here: the
  unit suite and the other three browser files (the merge queue runs them). Main has not moved since the round 2
  merge (no origin/main in the clone).

Round 4: main (dc47a763) merged in. Its two conflicts are resolved and nothing else changed. Code is unchanged
since round 3.

- `docs/SPEC.md` §12o: main's page paragraph is kept as main wrote it (*Waiting for you* at the top of the side
  panel, the fold past 3, folded modelling requests, and the side panel's order). The branch's sentences on labels,
  units and the number every person ask gets are added after its endpoints.
- `tests/test_inbox_page.py`: main's new
  `test_a_list_the_reader_is_in_is_not_folded_away_when_a_fourth_comes` and the branch's acceptance test had been
  spliced into one body. Both are now whole functions, each unchanged.
- Run here: `tests/test_inbox_page.py` under the watchdog with Playwright: 13 passed, rc 0, none skipped.
  `tests/test_inbox.py`: 37 passed. `tests/test_gated_actions.py`: 13 passed. ruff is clean. Not run here: the
  unit suite and the other three browser files. The definition's third sentence (Yes/No buttons) is still left
  for a gap of its own, as round 3 says.

Round 5: the queue's one finding answered. Code is otherwise unchanged since round 3.

- The finding: `tests/test_style_tokens.py::test_no_literal_colour_size_radius_or_spacing_outside_the_tokens`
  failed on the branch's `.ask-in { gap: 2px }` (a literal spacing). It is now `gap: var(--sp-0)`, the 2px token,
  so the page looks the same. It was the branch's own line, not a main failure.
- Run here: `tests/test_style_tokens.py`: 13 passed (it failed before the change). `tests/test_inbox_page.py` under
  the watchdog with Playwright: 13 passed, rc 0, none skipped. ruff is clean. Not run here: the unit suite and the
  other three browser files. Main has not moved (no origin/main in the clone). The Yes/No buttons stay left for a
  gap of its own, as round 3 says.

Round 6: the review's two findings answered. Code changed by 3 net lines in `diagram.js` since round 5.

- Finding 1 (`diagram.js` `foldRow`): the folded modelling requests' Deny all reason had no `<label>` and kept the
  placeholder "why (to deny all)" with aria-label "Why". It now sits in the same `label.ask-in` as every other box,
  "Reason for denying all (required)", with no placeholder; the box takes its name from that label. "Required" is
  true: a modelling request's deny needs a note, so Deny all with no reason is refused for each member. Deny all
  still reads `act.querySelector("input")`, which finds the box inside the label. SPEC §12o says so.
- Finding 2 (the acceptance test could not see the fold): new
  `tests/test_inbox_page.py::test_the_folded_requests_deny_all_reason_has_a_full_label_too`, with a `folds` fixture
  (three alike held requests), opens the fold and runs the same check (now the module's `INPUTS`) on every input
  of the side list: the fold's own reason and each member's. Seen to fail with the round 5 `foldRow` put back (no
  "Reason for denying all (required)" label), and to pass with the fix.
- Run here: `tests/test_inbox_page.py` under the watchdog with Playwright: 14 passed, rc 0, none skipped.
  `tests/test_diagram_rendering.py`'s two fold tests (`..._fold_into_one_entry_...`, `..._two_folds_each_keep_...`)
  pass. ruff is clean. Not run here: the unit suite and the four browser files whole (the merge queue runs them).
  Main has not moved (no origin/main in the clone). The Yes/No buttons stay left for a gap of its own, as round 3
  says.
