# ui-per-class-of-action-asked-approved-denied-and-wh: Per class of action: asked, approved, denied, and whether it is held

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q51 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /items › oversight › Actions

**The problem:** No page states per-class totals. The tallies '0 requested, 0 approved, 121 ran, 0 denied' count present state, so '0 approved' misleads; '11 asked, 0 approved' for the person ask contradicts 121 actions approved by the stand-in. The Items search does not match the action field.

**The change:** Above the Actions rows, one line per class: 'jira-transition: 24 asked, 24 approved (by the offline stand-in), 0 denied this week · held for approval'. The search matches class and command.

**User stories it serves:** E5

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8791/items the Actions section has a row starting 'jira-transition' with three numbers and either 'held for approval' or 'let through'; asked = approved + denied + waiting; typing 'jira-transition' in the search narrows the action rows.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Round 1: built. 35 net lines of code outside tests, docs and dev (record.py 21, pages.js 12, actions_api.py 2,
server.py 0), within the 60 budget.

- `ergostat/actions/record.py` `asked()`: per class, the actions asked this week, each counted once by where it ended
  (approved: ran, failed or still to run, and how many by the gate; denied: by the gate, the owner or at the act;
  waiting: held now), so asked = approved + denied + waiting by construction; the class's gate (the model's, else the
  newest asked's). Served at `GET /api/actions?classes=1`.
- `ergostat/web/static/pages.js` `actionClasses()`: above the Actions rows on /items, one line a class, e.g.
  `jira-transition: 5 asked, 3 approved (by the gate), 1 denied, 1 waiting this week · let through`. The search
  narrows the lines with the rows (a line stays if its class matches, or one of its actions is in the rows left).
- SPEC §12k: a paragraph on the line and the endpoint.

Choices made without asking (each easy to change):
- The line shows **waiting** as a fourth number. The acceptance asks for asked = approved + denied + waiting, which
  a reader can only check if waiting is shown.
- The approver is said as the record says it: "(by the gate)", "(by a person)", or "(N by the gate)" when mixed. The
  record has no "offline stand-in" approver for actions (auto approvals are `approved_by: gate`), so it is not said.
- A `deny` gate is said "never run" (neither "held for approval" nor "let through" is true of it).
- The rows' search: `_as_listed` already matched the search against every field (action, class, command). No change
  to it was needed. The new browser test shows it narrowing the action rows by class and by command. I did not find
  why the design review saw it fail on the demo.
- The test gets its own site (`acted` fixture: image-squeeze with two actions appended to its ergostat.yaml). The
  Actions kind exists only when the model declares actions, and image-squeeze declares none.

Tests: `tests/test_items_page.py::test_actions_say_per_class_asked_approved_denied_and_whether_held` (browser) and
`tests/test_gated_actions.py::test_each_class_says_asked_approved_denied_waiting_and_its_gate` (unit). I broke the
code twice and both tests failed as they should: with the lines' search filter removed, the browser test failed
(`['jira-transition', 'outward'] == ['jira-transition']`); with a denial counted as an approval, both failed. Whole
files run: tests/test_items_page.py 22 passed with none skipped (under suite_watch, rc 0), and
tests/test_gated_actions.py 11 passed. Ruff is clean. main has no commits beyond this branch's base, so there was
nothing to merge. Not run here: test_diagram_rendering.py and the other browser files (this change does not touch
the diagrams), and the whole unit suite (the factory's to run).

Round 2: the blocking finding is fixed. `record.asked()` now gives each class its strictest gate (deny > approve >
auto, read from `interventions.STRICT`, the same way SPEC §12p reads a class). With a model, it takes the strictest
of every action the model declares in the class. With no model, it takes the strictest of every action asked. An
unknown gate counts as the strictest, so it fails closed. When the model declares the class, its gate still comes
first, because the gate now is what holds the next request. I did not combine it with the gates of past requests:
a gate loosened on purpose would then still read as held. SPEC §12k says this in one sentence. There are now 41 net
lines of code outside tests, docs and dev (record.py +6), within the 60 budget.

Test: `tests/test_gated_actions.py::test_a_class_mixing_gates_is_said_by_its_strictest`. Its class `mixed` has an
approve action, then an auto one that is declared and asked last. I broke the code twice and the test failed both
times. With the model's gate set by the last-declared action, it failed (`'auto' != 'approve'`). With the fallback
taking the newest request's gate, it failed on the no-model assertion. Runs: tests/test_gated_actions.py 12 passed;
tests/test_items_page.py 22 passed with none skipped (under suite_watch, rc 0); ruff is clean. main (277a9c6c) is
already in the branch, so there was nothing to merge. Not run: the unit suite and the other browser files (the
factory and the queue run those).

Round 3: the blocking finding (a conflict with main in tests/test_items_page.py) is resolved. The merge of main
(bf6dbebf) keeps both sides. The branch's `acted` fixture and Actions test now come first, and main's `add_record`,
`record_rows`, crossing-to-record test and lifecycle-strip test follow. Compared with main, the file differs only by the
branch's fixture and test (85 added lines, none removed). No code changed this round, so the net count stays at 41.

Runs after the merge: ruff is clean. tests/test_gated_actions.py: 13 passed. tests/test_items_page.py (under
suite_watch): 26 passed and 6 failed, rc 1, run twice with the same result. The Actions acceptance test passed. The
six that fail are test_a_stocks_and_a_flows_side_panel_list_their_items_and_link_to_exactly_that_set,
test_the_model_changes_are_found_by_heading_search_and_panel, test_a_valves_leased_items_are_listed_live,
test_a_snapshot_lists_a_parts_items_and_opens_its_set, test_a_set_left_out_of_a_snapshot_says_so and
test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart. Five of them time out waiting for a diagram
part's side panel (`#detail .item-set`, `.counts-line`, `.leases-line`) after `openNode`, and one times out waiting
for the project switcher's entry. I believe these are unrelated to this gap. The branch changes none of that code:
its changes are record.py, the `classes=1` query, and one `actionClasses` line on /items that is drawn only when
Actions items exist, which the `site` example has none of. The merge of main brought large changes to details.js,
diagram.js, dynamics.js and pages.js (86 lines). In round 2, before this merge, the file passed with nothing failing.
I could not confirm it by running these tests on main: `git worktree add -q --detach /tmp/mainwt bf6dbebf` (to run
them there) was refused in this session. By lesson 13 they are reported here and not fixed in this branch. The
factory's rerun on clean main should show whether main has them too.

Round 4: the blocking finding (a conflict with main in tests/test_items_page.py) is resolved. The merge of main
(ead497d1) keeps both sides. Main's new `test_the_record_folds_runs_of_identical_events` and the branch's `acted`
fixture and Actions test had been added in the same place. The branch's fixture and test now come first and main's
test follows. Compared with main, the file differs only by the branch's fixture and test (85 added lines, none
removed). No code changed this round, so the net count stays at 41.

Runs after the merge: ruff is clean. tests/test_gated_actions.py: 13 passed. tests/test_items_page.py (under
suite_watch): 33 passed and 1 failed, rc 1, on each of the three runs. The Actions acceptance test passed in the file
and alone. The five side-panel failures of round 3 now pass. The one that fails is
`test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart`. It times out at tests/test_items_page.py:1538,
waiting for the other project's entry in the header's `#project` switcher. This branch does not touch the switcher,
and that test's sites declare no actions, so the branch's `actionClasses` line is never drawn there. It failed the
same way in round 3. By lesson 13 it is reported here and not fixed in this branch. The factory's rerun on clean main
should show whether main fails it too. Two reruns of the browser file with another output filter were refused in this
session: `... 2>&1 | grep -E '^(FAILED|ERROR)|^_{3,} test|passed|failed' | tail -8` and
`... > /tmp/items.log 2>&1; grep -E 'FAILED|passed|failed| test_' /tmp/items.log | tail -10`. A later run that was
allowed named the test.
