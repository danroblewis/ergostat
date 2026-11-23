# ui-in-dynamics-a-goal-is-called-a-goal-loop-means-a: In Dynamics a goal is called a goal; 'loop' means an R or B loop

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q62 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram side list and Suggestions in Dynamics

**The problem:** The Dynamics side list says 'loop requests-handled' directly above 'Feedback loops 18: R2, R3 …'. One word names a controlled goal and a causal loop in one panel; counts (49 against 16) look like double counting. Suggestions speak of 'its decision (fixer, every 1m)' in the SD view.

**The change:** In Dynamics write 'goal requests-handled' and 'what serves it'. Keep 'Feedback loops' for R and B. In Blocks write 'control loop'. Where an R or B loop closes a goal, its row says 'serves goal model-fits'.

**User stories it serves:** G1

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8796/ in Dynamics no side-list entry or suggestion starts with 'loop '; the heading 'Feedback loops' remains; in Blocks the list heading reads 'Control loops'.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Built, round 1 (8 net lines outside tests: 14 added, 6 removed).

- Dynamics' cards: `ergostat/dynamics.py` `attention()` (the Dynamics view's words, which the page shows as given) now
  writes `goal NAME` for a controlled goal's card where it wrote `loop NAME`, also inside the text ("goal a keeps
  feeding x while goal b is off"), and `what serves it` where it wrote `its decision`. Only names of the model's
  goals are rewritten, whole, so "feedback loop q-x" is left alone. This file is outside "Files to touch"
  (`ergostat/web/`): it is where the Dynamics words are made, and the page has no other place to change them.
- Suggestions' "Evidence" link (`diagram.js`) reads `goal NAME` as well as `loop NAME`.
- Dynamics' Feedback loops list (`dynamics.js`): a loop whose parts include a goal's gap says
  `serves goal NAME` (`serves goals a, b` for several). The heading "Feedback loops" is unchanged.
- Blocks (and the control view): the list heading is "Control loops", its empty text "No control loops in view.".
  Choice, the most reversible one: in Blocks the cards keep `loop NAME` (no R or B loop is drawn there, and the same
  `what` is the CLI's, the Loops page's and other tests'); only the heading says "control loop".
- Tests: `tests/test_diagram_rendering.py::test_in_dynamics_a_goal_is_called_a_goal_and_loop_means_an_r_or_b_loop`
  (software-factory, one reading of backlog above its goal so `backlog-clear` is off: no card in Dynamics starts with
  `loop `, one starts with `goal `, "Feedback loops" stays, every loop through a goal says `serves goal`; in Blocks
  the heading is "Control loops"). Seen to fail with each change undone in turn (card `loop backlog-clear`; no
  `serves goal`; heading "Loops"). Not seeded in the browser: a suggestion (the ladder hints need 10 minutes of an
  off record); its words are pinned by the unit tests `test_the_attention_cards_speak_system_dynamics` (changed: it
  forbade the word goal, which this gap asks for) and `test_a_goal_s_suggestion_says_what_serves_it` in
  `tests/test_dynamics_view.py`.
- Runs: the new browser test passed (rc 0, under the watchdog); `tests/test_dynamics_view.py`,
  `tests/test_goal_per.py` and `tests/test_observer.py` passed (61); ruff clean. Not run to the end: the whole of
  `tests/test_diagram_rendering.py` (serial, started under the watchdog, stopped at the session's 20-minute
  background limit with no result; restarting it with a longer limit was refused). The unit suite and the other
  browser files were not run here, as the task said; the merge queue runs them. `main` is in the branch (nothing to
  merge).

Round 2: main (bf6dbebf) merged in; the queue's conflicts resolved, keeping both sides.

- `dynamics.py`: main's docstring ("off by 4") with the branch's goal wording. `diagram.js` Suggestions: main's
  `goalButton`/`showGoal` with the branch's `(?:loop|goal)` match. `dynamics.js`: main's `sdPol(c)` with the
  branch's `serves goal …`. `test_dynamics_view.py`: main's "off by 4" with the branch's goal assertions.
  `test_diagram_rendering.py`: both sides' new tests kept.
- A clash that merged cleanly but did not work (lesson 7): main made a goal's name in Needs attention a button only
  for `loop NAME` (`diagram.js`), so in Dynamics, which now says `goal NAME`, the button went missing. It now matches
  `loop` or `goal` (no net lines). Main's two tests that read the Dynamics card words now expect `goal NAME` in
  Dynamics and `loop NAME` in Blocks: `test_a_goal_name_opens_its_evidence_and_rings_its_stock_or_its_summing_junction`
  and `test_needs_attention_is_three_headed_groups_in_a_fixed_order`.
- Runs: ruff clean; `tests/test_dynamics_view.py` 16 passed; under the watchdog, the acceptance test and both
  parametrizations of `test_a_goal_name_opens_its_evidence…` passed. Failing, and not from this branch:
  `test_needs_attention_is_three_headed_groups_in_a_fixed_order` times out (twice, also alone) in its first wait,
  before any word this gap changes is read. That wait expects the header `#running` to match `/loops? off/`, but
  main's `util.js` writes `N off`, and this branch leaves `util.js`, `index.html` and `state.py` identical to main.
  So it fails on main too; left for main (lesson 13).

Round 3: the queue's conflicts (`diagram.js`, `dynamics.js`, `test_diagram_rendering.py`) were already resolved in
round 2, and main (63998238) was merged in at c8cdab2d with no conflict (it touched only `dev/bin/` and
`tests/test_ui_front.py`). `main` is an ancestor of HEAD and there is nothing newer to merge. No conflict markers are
left in the tree.

- Change: one missing space after the "Control loops" heading text in `diagram.js` (formatting, no net lines).
- Runs: ruff clean; `tests/test_dynamics_view.py` 16 passed; under the watchdog, the acceptance test and both
  parametrizations of `test_a_goal_name_opens_its_evidence…` passed (3 passed, rc 1 because of the next test).
  `test_needs_attention_is_three_headed_groups_in_a_fixed_order` still times out in its first wait (`/loops? off/` on
  `#running`, which main's unchanged `util.js` writes as `N off`). It fails on main too, so it is left for main
  (lesson 13). The whole of `tests/test_diagram_rendering.py`, the other browser files and the unit suite were not run
  here; the merge queue runs them.

Round 4: main (ead497d1) merged in at 80fc5a21. The conflicts are resolved and both sides are kept.

- `diagram.js` Suggestions: main now reads the goal's name from a hint's `what` (no longer from its `says`). The
  branch keeps its `(?:loop|goal)` match, now applied to `what`. `test_dynamics_view.py`: the branch's `goal NAME`
  and `what serves it` assertions, with main's new hint text (`was off 60% …`, which no longer starts with the
  name). `test_diagram_rendering.py`: the branch's acceptance test and main's two new tests are all kept.
- Runs: ruff clean; `tests/test_dynamics_view.py` 16 passed. Under the watchdog: the acceptance test,
  `test_a_one_sided_limit_is_drawn_and_named_as_a_limit` and the boxed parametrization of
  `test_a_goal_name_opens_its_evidence…` passed. Its unboxed parametrization failed three times out of three, at the
  Suggestions step main added (`.side .suggest .hint button.name` "not visible"). The button is there and reads
  `goal short-backlog`, but `#detail` is still open, so `.side` is `display: none`. This is a race in main's code:
  `openLoop` (`details.js`, the same as on main) draws a "Loading…" panel, waits for `/api/loops/NAME`, and then
  calls `showDetail` again. That answer lands after the test's `closeDetail()`, so the panel reopens. This branch does
  not touch that path. Not shown: that it fails on clean main too, because making a main worktree
  (`git worktree add … ead497d1`) and checking out main's files (`git checkout ead497d1 -- …`) were both refused
  here. So it is left for main (lesson 13). Not run here: `test_needs_attention_is_three_headed_groups_in_a_fixed_order`
  (it failed on main in rounds 2 and 3), the rest of `tests/test_diagram_rendering.py`, the other browser files and
  the unit suite.
