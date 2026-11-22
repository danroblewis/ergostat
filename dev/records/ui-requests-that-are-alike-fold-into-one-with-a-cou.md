# ui-requests-that-are-alike-fold-into-one-with-a-cou: Requests that are alike fold into one, with a count and one answer

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q50 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram side list; /items 'Modelling requests'

**The problem:** On big 24 'no-unit' requests each take a seven-line row with its own Deny; four fill the list; the one real alarm and everything else are pushed away. /model says 'Changes to review: Nothing waiting' at the same time.

**The change:** Group by (code, asker): one <details> row '24 stocks have no unit (api, billing, build, data, support, web) · Deny all', whose body lists the members, each with its own control. /model's 'Changes to review' counts the same held requests.

**User stories it serves:** E4, E1, H1

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8797/ the side list has one entry containing '24' and 'no unit'; opening it lists 24 members; every other entry in the list is visible without scrolling at 1440x900; /model does not say 'Nothing waiting' while requests are held.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Round 1: built, 37 net lines outside tests and docs (budget 60).

- **What:** the inbox's held modelling requests carry `fold` (`code|source`: the code and the asker), `about` and their
  part's `system` (`ergostat/inbox/entries.py`, passed through to the attention list in `ergostat/state.py`). The side
  list (`diagram.js`: `folded`, `foldRow`) shows alike ones as one entry where the first stood: a closed `<details>`
  whose summary reads "24 stocks: no unit (api, billing, build, data, support, web)", with one why and **Deny all**
  (each member denied in turn through `POST /api/inbox/ID/deny`) below it; opened, each member is the usual row with its
  own Approve/Deny. A fold of one is shown as a plain row. /model's *Changes to review* counts the held requests
  (`/api/fit`'s new `held`, read from the request store) and says "N modelling requests held for you: answered in
  Needs attention" instead of "Nothing waiting". SPEC §12o says so.
- **Choices taken (nobody to ask; the most reversible):** "asker" read as the request's `source` (check, craft,
  coherence, fit). The summary is worked out from the code ("no unit"), not a written sentence per code. The CLI and
  the status text are left as they were: only the page folds. Deny all needs a why, as each deny does; with none,
  the server's refusal is shown for the members it refused.
- **Outside "Files to touch":** `ergostat/inbox/entries.py` and `ergostat/state.py` (one line), because the page needs
  the code, asker and system, and the attention entry didn't carry them. `/items` was not changed: it has no answer rows
  of its own (only the side list answers the inbox), so there is nothing there to fold.
- **Acceptance test:** `tests/test_diagram_rendering.py::test_alike_modelling_requests_fold_into_one_entry_with_a_count_and_one_answer`
  (24 no-unit stocks over 6 systems, held, plus a gated action as the real alarm, at 1440x900): one folded entry with
  '24' and 'no unit' and the six systems, no member as a row of its own, every entry inside the side panel unscrolled,
  24 members when opened, each with its own Deny, /model without 'Nothing waiting' and with '24 modelling requests
  held', and Deny all dismissing all 24 while the alarm stays. It was seen to fail on four breaks, each made by hand
  and put back: no folding (no fold entry), the fold drawn open (the in-view check), /model's count left out (the
  'Nothing waiting' check), Deny all skipping a member (a request left held).
- **Runs:** that test and `tests/test_inbox_page.py`: pass. `tests/test_inbox.py`, `tests/test_modelling_core.py`,
  `tests/test_runner_and_state.py`: 97 passed. ruff clean. All of `tests/test_diagram_rendering.py`, serially under the
  watchdog: 197 passed, 4 failed, rc 1, none of them failing on what this branch changed:
  - `test_every_view_draws_cleanly_and_in_time[coordinator]` (routing 25.5 s against 20 s),
    `[image-squeeze]` (23.3 s against 20 s), and `test_a_big_tangled_model_lays_out_in_time_and_cleanly` (draw 3.1 s
    against 2.5 s): time bounds on layout and routing. This branch touches no drawing code. Not run again on a
    quiet machine.
  - `test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page` expects "Nothing waiting." on /model
    after accepting k. A real change is in the queue there ("A missing delay on an inflow, as DELAY3"), from the
    residual finder main gained (0466dbff, 4e9e6046). It still fails with this branch's held count read straight from
    the request store, and the review queue reads nothing this branch changed. My attempts to run it on main's code
    (`git checkout main -- ergostat`, `git worktree add --detach /work/.git/main-check main`) were refused, so its
    failure on main is shown by reading the code, not by a run.
- **Not run:** the other browser files (`test_page_polling.py`, `test_items_page.py`, `test_page_refresh.py`), the
  whole unit suite, and a merge of main (main is the clone's base, so there is nothing newer to merge).

Round 1, after the build step: `build` failed with rc 5. It ran only `tests/test_diagram_rendering.py` (the one test
file changed; no `tests/test_<module>.py` exists for `entries.py`, `state.py` or `numbers_api.py`), and that file
skips whole without Playwright, so nothing was collected. No page code changed. Added a unit test of the server side,
`tests/test_inbox.py::test_a_held_request_carries_its_fold_part_and_system_to_the_side_list` (the entry's
`fold`/`about`/`system`, and the attention row carrying them), so the build step now runs `tests/test_inbox.py` too. It
was seen to fail (KeyError) with `state.py`'s pass-through line removed, then put back. `tests/test_inbox.py`: 31
passed. ruff clean.

Round 2: the review's one finding (blocking), answered. 38 net lines outside tests and docs (budget 60).

- **Finding: Deny all acted on a detached build after a poll (lesson-5).** `foldRow`'s handler now reads the reason,
  the button and the status span from the clicked button's own row on the page (`ev.currentTarget.parentElement`),
  not from the elements made in its own build. The members it denies (`ms`) are still from the closure, and that is
  right: each patch hands the kept button the newest build's handler, so `ms` is the newest list.
- **The test now crosses a refresh:** between filling the reason and clicking Deny all it waits for two
  `/api/graph` answers. The second ask starts only after the first answer's side list was drawn and patched in, so
  the click is on a kept button whose handler came from a later build. With the old handler put back by hand, the test
  failed (the fold never went: all 24 stayed held, 60 s timeout); with the fix, it passes.
- **Not fixed, reported (lesson-13):** each member's own Approve/Deny is the shared `inboxAnswer` row, which still
  closes over its own build's `row`, `said`, `n` and `why`. A reason typed into one member's field across a poll has
  the same failure on every inbox row, on main as well. Fixing it means changing the shared renderer, which is outside
  this gap; it needs a gap of its own.
- **Runs:** the acceptance test (passed, and failed without the fix, as above), `tests/test_inbox_page.py` (passed),
  `tests/test_inbox.py` (31 passed), ruff clean. Not run: the rest of `tests/test_diagram_rendering.py`, the other
  browser files, the unit suite. No merge of main: main is the clone's base.

Round 3: the queue's finding (conflicts with main in `state.py`, `diagram.js`, `tests/test_diagram_rendering.py`),
answered by finishing the factory's merge of main (73d266e7).

- **How it was resolved:** main had split the side list into three headed groups (Waiting for you, Goals off, Model
  housekeeping, cd71c13e, 642e158e) and dropped the old MAX cut. Held modelling requests now sit under Model
  housekeeping, which is closed unless there's a fault. The branch's `folded`/`foldRow` now run inside main's `list`, so
  alike requests are one entry within whichever group holds them. Main's per-entry word goes on each row and on the
  fold's summary ("request · "), and the modelling rule (`hr`) reads the first member of a fold. `state.py` keeps main's
  `kind` and the branch's `fold`/`about`/`system`. The test file keeps both tests whole.
- **Choice taken (nobody to ask):** because the requests are housekeeping now, the acceptance test opens Model
  housekeeping first if it is closed. It then checks the one fold entry, that every entry is in view unscrolled at
  1440x900, the 24 members, /model, and Deny all across a refresh, as before. Leaving the requests where main put them
  is the most reversible option; moving them back to Waiting for you would undo main's decision.
- **Runs:** ruff clean. The acceptance test and main's `test_needs_attention_is_three_headed_groups_in_a_fixed_order`:
  2 passed. The acceptance test failed again, as expected, with folding broken by hand (60 s timeout waiting for the
  fold), then was put back. `tests/test_inbox_page.py`: passed. `tests/test_inbox.py`: 32 passed.
  All of `tests/test_diagram_rendering.py` under the watchdog: 200 passed, 9 failed, rc 1. None of the 9 depends on
  this branch:
  - `test_every_view_draws_cleanly_and_in_time[coordinator]`, `[image-squeeze]`,
    `test_a_big_tangled_model_lays_out_in_time_and_cleanly`,
    `test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page`: the same four as in round 1,
    for the reasons given there.
  - `test_the_dynamics_view_speaks_system_dynamics_and_marks_only_loops_whose_sign_is_known`: its SD-words check
    matches "Goals" in main's own "Goals off" heading (cd71c13e), text this branch doesn't write.
  - `test_every_lines_panel_links_to_the_parts_it_joins[alert-triage]`, `[coordinator]`, `[ticket-factory]` ("link
    ... opened nothing"): with `folded` made a pass-through by hand, so the side list was main's, `[coordinator]` and
    `[ticket-factory]` still failed. `[alert-triage]` passed on its own rerun.
  - `test_every_part_opens_its_panel_when_clicked_even_mid_redraw`: a different part fails each run. On its own it
    passed both with folding off and with folding on.
  - Not shown on main itself: running main's code was refused in round 1, so these are shown by the experiments above,
    not by a run on main.
- **Not run:** the other browser files, the unit suite.
