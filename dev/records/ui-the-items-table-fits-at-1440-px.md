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
