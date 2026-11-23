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

Round 4: the factory's merge of main (bea24a23) finished, and the review's one finding (blocking) answered. 40 net
lines outside tests and docs (budget 60).

- **Merge:** `diagram.js` conflicted where main added `goalButton`/`showGoal` and gave a side-list entry named
  `loop NAME` a goal button. Both kept: the branch's `folded`/`foldRow` stand next to main's functions, and main's goal
  button is now in the branch's shared `row`, which both plain entries and fold members use. Committed as 6a643b6a.
- **Finding: the fold entry had no key, so a refresh patched a fold into another's nodes by place, typed reason
  included (lesson-5).** The fold's entry is now keyed `fold:CODE|ASKER` (`h()`'s `key`). `patchKids` matches keyed
  nodes only by key, never by place, so a fold keeps its own nodes and typed reason, and a gone fold's nodes go with it.
  Deny all also clears the reason once every member is denied (not when some were refused, so the reason can be used
  again).
- **New browser case:** `tests/test_diagram_rendering.py::test_two_folds_each_keep_their_own_reason_across_a_refresh`.
  Two folds: 3 no-unit stocks and 3 no-description stocks, held. It types B's reason, then A's, and clicks Deny all on A.
  A's field must be empty when its row says "3 denied" (a MutationObserver reads it then, because a refresh can take A
  away right after). After two `/api/graph` answers, with B where A was, B's field must still hold B's own reason.
  Deny all on B then has to dismiss all six, each with its own fold's note ("reason A" or "reason B"). Seen to fail
  on each break by hand, then put back: with the key removed, B's field read '' (it got A's cleared nodes); with
  the clear removed, A's field read 'reason A' after "3 denied".
- **Runs:** ruff clean. The new case and the acceptance test: passed. `tests/test_inbox.py` and
  `tests/test_inbox_page.py`: 33 passed.
- **Fails on main, not on this branch (lesson-13):** `test_needs_attention_is_three_headed_groups_in_a_fixed_order`
  times out waiting for `/loops? off/` in `#running`. Main's 35c0bb01 ("The header counts the system's goals, and the
  model's upkeep apart") changed the header to say "N off" (`util.js:394`). `util.js` and this test are identical to
  main's (`git diff main` shows only the branch's added tests in that file). It failed in the same way with `folded`
  made a pass-through by hand. Not fixed here.
- **Not run:** the rest of `tests/test_diagram_rendering.py`, the other browser files, the unit suite.

## Where it stopped

Parked by the factory (implementor, 2026-11-22 17:02).

Stopped on its last attempt by RuntimeError: docker network: failed to connect to the docker API at unix:///Users/user/.docker/run/docker.sock; check if the path is correct and if the daemon is running: dial unix /Users/user/.docker/run/docker.sock: connect: no such file or directory

```
Traceback (most recent call last):
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 166, in main
    return build(cfg, given, began)
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 221, in build
    got = fac.session(cfg, "implementor", prompt, work)
  File "/Users/user/ergostat-live/instance/dev/bin/fac.py", line 678, in session
    out = agents.session(cfg, role, brief, work, keep=kept)
  File "/Users/user/ergostat-live/instance/dev/bin/agents.py", line 204, in session
    egress(cfg)
    ~~~~~~^^^^^
  File "/Users/user/ergostat-live/instance/dev/bin/agents.py", line 117, in egress
    _egress(cfg)
    ~~~~~~~^^^^^
  File "/Users/user/ergostat-live/instance/dev/bin/agents.py", line 124, in _egress
    docker("network", "create", "--internal", NET)
    ~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/user/ergostat-live/instance/dev/bin/agents.py", line 106, in docker
    raise RuntimeError(f"docker {args[0]}: {r.stderr.strip()[-300:]}")
RuntimeError: docker network: failed to connect to the docker API at unix:///Users/user/.docker/run/docker.sock; check if the path is correct and if the daemon is running: dial unix /Users/user/.docker/run/docker.sock: connect: no such file or directory

```

## Where it stopped

Parked by the factory (dead-letters, 2026-11-22 17:03).

Its runs failed past their attempts (a dead letter):
- attempt 22: nack the implementor pool is full (run/pools.json): waits its turn
- attempt 23: nack the implementor pool is full (run/pools.json): waits its turn
- attempt 24: nack exited 1
- attempt 25: nack the run ended with gap/ui-requests-that-are-alike-fold-into-one-with-a-cou still parked

## Where it stopped

Parked by the factory (dead-letters, 2026-11-22 17:23).

Its runs failed past their attempts (a dead letter):
- attempt 23: nack the implementor pool is full (run/pools.json): waits its turn
- attempt 24: nack exited 1
- attempt 25: nack the run ended with gap/ui-requests-that-are-alike-fold-into-one-with-a-cou still parked
- attempt 26: nack the implementor pool is full (run/pools.json): waits its turn

## Where it stopped

Continued, round 1: the factory's merge of main (63998238) finished (a2ea5b34), and the tests updated to match
what main changed.

- **Merge:** `entries.py`: main's new request summary (a sentence saying what Approve and Deny do, `why` empty) kept,
  with the branch's `fold`/`about`/`system` added to it. `diagram.js`: main's `list` now keys each row, holds the list
  still while the reader is in it (`hold`), and draws an inbox entry with `inboxBody`. All three are kept: the branch's
  shared `row` is now main's keyed row (`inboxBody` included), and main's `list(xs, none, cls)` runs `folded` and
  `foldRow` as before. `SPEC.md` §12o: main's paragraph on lists holding still, then the branch's sentences on folding.
  `tests/test_diagram_rendering.py`: both sides only added tests, and all are kept.
- **Tests changed, because of main's changes:** each fold member now holds main's "the command" `<details>`, so the
  acceptance test reads the fold's own summary (`> details.fold > summary`) and its members (`> details.fold >
  [data-inbox]`). Main's lists hold still while the pointer or focus is in them, so after typing and after Deny all
  both fold tests step out of the list (`leave_list`: pointer away, focus blurred) before they wait for a refresh or
  for the fold to go. They wait for "N denied" first. Checked again by hand: with folding off, the acceptance test
  fails (no fold entry); with the fold's key removed, the two-fold test fails (B's field reads ''). Both put back.
- **Runs:** ruff clean. `tests/test_inbox.py`: 34 passed. `tests/test_inbox_page.py`: 7 passed, rc 0. The acceptance
  test and `test_two_folds_each_keep_their_own_reason_across_a_refresh`: 2 passed, rc 0.
  `test_needs_attention_is_three_headed_groups_in_a_fixed_order` still fails, on the header's `/loops? off/`, as
  reported in round 4 (main's header, not this branch; lesson-13).
- **Refused:** a `python3 - <<EOF` script to resolve `diagram.js` (done with edits instead), and one `cat >> ... && git
  commit` command (done as an edit and a separate commit).
- **Not run:** the rest of `tests/test_diagram_rendering.py`, the other browser files, the unit suite.

Continued, round 2: the queue's finding (conflicts with main in `tests/test_diagram_rendering.py`), answered by
finishing the factory's merge of main (7cb97857, ff2a7daa). No code outside tests changed this round.

- **Merge:** both sides had added tests at the same place. The branch's two fold tests are kept whole, then main's
  `NO_UNIT` and `test_a_stock_with_no_unit_reads_unit_query_after_its_value_and_the_legend_explains_it`.
- **Main changed what the fold was first seen on:** main's `missing-unit-is-a-check-finding` made a stock's missing unit
  a check finding that raises no request (`requests.CHECK_ONLY`). So the 24 "no unit" requests in the problem no
  longer exist on big, and the acceptance's "'24' and 'no unit'" can't be met by any request. The fold is not tied to
  a code (it groups by code and asker), so nothing in the page changed. **Choice taken (nobody to ask; the most
  reversible):** the tests now use codes that are still requests. The acceptance test uses 24 stocks with a unit but
  no description over the six systems ("24 stocks: no description (api, billing, build, data, support, web)").
  Everything else it checks is as before. The two-fold test uses 3 undescribed stocks (`no-description`) and 3 flows
  with no equation (`no-equation`). Each test holds only its own parts' requests. The final check reads only the
  fold's code, because the same stocks have other open requests.
- **Seen to fail:** with `folded` made a pass-through by hand, both fold tests failed (the acceptance test timed out
  waiting for the `no-description` fold, and the two-fold test waiting for two folds). Put back.
- **Runs:** ruff clean. The two fold tests and main's no-unit browser test: 3 passed (the fold tests after the change
  above). `tests/test_inbox.py`: 34 passed. `tests/test_inbox_page.py`: 7 passed, rc 0.
- **Not run:** the rest of `tests/test_diagram_rendering.py` (its earlier failures on main's header and on timing
  bounds are as reported above), the other browser files, the unit suite.
