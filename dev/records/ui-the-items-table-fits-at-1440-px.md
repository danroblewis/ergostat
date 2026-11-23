# ui-the-items-table-fits-at-1440-px: The Items table fits at 1440 px

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q52 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /items

**The problem:** The ticket table's 'latest', 'last' and 'in state' columns are cut at the right edge ('ergos…', 'in s') with no scroll cue; pr_url takes the width.

**The change:** Show pr_url as a short link ('PR #7'). If columns still overflow, wrap the row's secondary fields onto a second line. At phone width keep id, state and time in state.

**User stories it serves:** F1

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
At 1440x900 on :8791/items every th's right edge is within the table container's right edge and no cell's text is clipped (scrollWidth ≤ clientWidth).

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Built, round 1. 10 net lines outside tests (pages.js +3 net, style.css +5).

- `fieldView` in a table cell (small) shows a pull or merge request's address (`…/pull/N`, `…/pulls/N`,
  `…/merge_requests/N`) as a link `PR #N`, the full address in its title. Other URLs are unchanged.
- "Wrap the row's secondary fields onto a second line" was taken as the most reversible reading: in the kinds' lists
  (`table.kind-items`, a class added beside `items`) a field's cell wraps its text onto more lines instead of
  cutting it with an ellipsis, the headers may wrap, and 'latest' is no longer kept to one line. No row layout or
  markup was restructured. With the short link alone the ticket table still overflowed by 191 px, so the wrapping is
  needed.
- At 700 px or narrower the lists keep only the item, its state and 'in state' (`.keep`); the remote section's
  table, which also has class `items`, is not touched.
- The demo on :8791 is not reachable from this container; the test serves a copy of `examples/ticket-factory` with
  eight seeded tickets (long titles and repo names, GitHub-style pr_url, one lease, so the lease columns show).

Test: `tests/test_items_page.py::test_the_items_table_fits_at_1440_px`. It failed before the change (393 px over,
six headers past the edge, titles clipped) and fails with each piece broken in turn: no short link (no `PR #`
link), no wrapping (191 px over, `events`, `latest`, `last` out), no phone rule (times out waiting for three
columns). Run here: that test, `tests/test_items_page.py` whole (22 passed) and `tests/test_page_refresh.py` (8
passed), with Playwright under the watchdog; ruff clean. Not run here: the unit suite, the other two browser files,
demo_check (no example changed). Main was not merged again: local `main` is this branch's base.

Build step, round 1: `[suites] build` failed with rc 5. Its affected-test selection maps only `.py` changes to tests, so
it picked only `tests/test_items_page.py`, which skips whole without Playwright, and pytest returned "no tests ran". No
ergostat code changed. Added
`tests/test_style_tokens.py::test_the_items_lists_wrap_their_fields_and_keep_three_columns_on_a_phone`, a static check
that needs no browser: the kinds' lists' cells wrap and are not cut, the phone rule keeps `.keep`, and pages.js sets
the class and `.keep`. It was seen to fail with the wrap rule set back to nowrap/hidden and with `:not(.keep)` dropped
from the phone rule; it passes as built (6 passed). The browser acceptance test is unchanged.
`scripts/affected_tests.py` reads a browser-only selection as rc 5. That is a factory matter outside this gap and is
left alone (lesson 13).

Round 2: main (ead497d1) merged. The conflicts in `tests/test_items_page.py` and `tests/test_style_tokens.py` were
two sides each adding tests at the file's end; both are kept whole, no code changed. After the merge: ruff clean;
`tests/test_style_tokens.py` 11 passed; `tests/test_items_page.py` with Playwright under the watchdog 33 passed,
1 failed. The failure is main's
`test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart`: it times out waiting for the `#project`
switcher to list the other project, which it reads through the shared `ERGOSTAT_HOME`. Run alone it fails too, so load
is not the cause. This branch's diff (fieldView's PR link, the kinds' lists' `kind-items` class and `.keep`, five CSS
rules scoped to `table.kind-items`) does not touch the header, `#upkeep` or the switcher, so it is reported here
and left alone (lesson 13). Not confirmed on clean main here: a run with main's static files checked out was refused
in this session. The acceptance test `test_the_items_table_fits_at_1440_px` passes after the merge.

Round 3: main (7a905955) merged. In `pages.js`, main gave `table()` a fourth argument (a caption, `<kind> items`) and
kept 'latest' `nowrap`. The resolution keeps the branch's cells (`.keep` on 'in state', 'latest' allowed to wrap) and
class `items kind-items`, and passes main's caption. In `tests/test_items_page.py` both sides had added tests at the
same place; both are kept whole. `tests/test_style_tokens.py`'s static check looked for the literal
`"items kind-items")`, which stopped matching once the caption argument followed it, so it now looks for
`"items kind-items",`. No other change. After the merge: ruff clean; `tests/test_style_tokens.py` 12 passed;
`tests/test_items_page.py` with Playwright under the watchdog 57 passed, 2 failed, the same two in both full runs.
`test_the_items_table_fits_at_1440_px` passes. The failures:
- `test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart`: the same failure as round 2 (the
  `#project` switcher never lists the other project).
- `test_actions_say_per_class_asked_approved_denied_and_whether_held`: new with this merge, and it fails when run
  alone too. It times out waiting for `.action-classes li[data-class="jira-transition"]` to be visible. The test,
  `actionClasses` and `/api/actions?classes=1` all came from main, and this branch does not touch any of them.
  Main also brought `items-one-section-per-kind-closed` and "/items is an overview of the kinds" (06317712), and
  either could leave the Actions section closed or never draw it. That cause is a guess and was not traced. Reported,
  not fixed (lesson 13).
Neither failure has been confirmed on clean main here: `git worktree add --detach /tmp/mainwt main` was refused in
this session.
