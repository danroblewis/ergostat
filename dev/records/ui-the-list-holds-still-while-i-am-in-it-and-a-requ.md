# ui-the-list-holds-still-while-i-am-in-it-and-a-requ: The list holds still while I am in it, and a request stays until it is answered

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q47 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram side list; /agents table

**The problem:** With the pointer on the list the three requests were pushed out by new alarms within 24 s; a typed deny reason vanished with its request and focus fell to the body. On Agents a click opened a different agent because rows re-sorted between hover and click.

**The change:** While the pointer or focus is inside the side list (or the Agents table) do not reorder or remove rows; show '3 updates waiting' at its top and apply them on leave. A request stays in place until answered or withdrawn, and then says so in its row.

**User stories it serves:** E3

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
Hover the third request on :8792 for 40 s: its bounding box top changes by 0 px and it is still present; type in its reason box and wait 40 s: the text and focus remain. On /agents hovering a row for 20 s leaves the row order unchanged.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped (round 1: built)

What was built (about 33 net lines of code under `ergostat/web/static/`: util.js +16, diagram.js +11, style.css +4,
pages.js +2):
- `util.js`: `heldStill(el)` (the pointer over it, or focus in it, a disabled button not counting) and
  `holdStill(el, built, release)`. While a list is held, the refresh is built aside but not patched in. A note at the
  list's top says how many `[data-row]` rows it would add, take away, move or change ("3 updates waiting"). The note
  is placed absolutely, so it moves no row. `release` runs on `pointerleave`/`focusout` once neither still holds.
- `diagram.js` (the side panel's *Needs attention* list, now `.att.needs`): held while the reader is in it. A request
  that drops out of the answers while the list is held says "no longer waiting: answered or withdrawn" in its row,
  unless its own answer already says what happened. Requests are no longer cut by the six-row limit, so new alarms
  cannot push a request out even when the reader is not in the list. The limit still applies to the other rows.
- `pages.js` (the Agents table): held the same way, and released by drawing the page again.
- SPEC §12o (the page bullet): says the above.

Choices made without asking (each easy to undo):
- On /diagram only the *Needs attention* list is held, not the whole side panel. Holding the panel would also hold its
  live charts, and the problem named was in this list. The loop list below it is not held.
- An answered or withdrawn request stays, marked, until the reader leaves the list, and then goes.
- The count of waiting updates is the number of rows that differ. That includes a row whose text only changed (for
  example "waiting 3 min" becoming "4 min").
- The acceptance names the demo port :8792. The tests stand up their own server. New alarms, one more with each graph
  answer, are added to the real server's answers in the browser (`page.route`). The Agents order is reversed on every
  other `/api/agents` answer, the way a re-sort would.

Tests (each run under `scripts/suite_watch.py` with Playwright 1.63.0, through `scripts/named_tests.py`):
- `tests/test_inbox_page.py`, rc 0, 2 passed. It has the new
  `test_the_side_list_holds_still_while_the_reader_is_in_it_and_a_request_stays_until_answered`: a 40 s hover, then
  40 s with only the focus in the box, then leave, deny, withdraw. `test_approve_in_the_side_panel` now leaves the list
  before waiting for the answered row to go, since that row now stays while the reader is in the list.
- `tests/test_agents_page.py`, rc 0, 4 passed. It has the new
  `test_the_agents_table_holds_still_while_the_pointer_is_on_a_row` (a 20 s hover).
- Breaks seen to fail (lesson 9):
  - `heldStill` always false: both new tests fail (the row's top moved 415.6 → 447.9 px; the order became
    "writer reviewer tidy").
  - The focus part removed: the side-list test fails at the focus check.
  - The six-row cut put back: the side-list test fails because the request is gone after the leave.
- `uv run ruff check ergostat tests scripts`: clean.
- Not run here, as the house rules say: the unit suite and the four browser files. A grep finds no test in the four
  files that reads the side list or the Agents table. Not run: `demo_check` (no example touched) and a merge of
  `main` (`main` is this branch's base and has not moved in the clone).
- Refused in this session: `node --check ergostat/web/static/pages.js && …`, a `python3 - <<'EOF'` edit script and a
  `sed -i` on the test. The edits were made with the editor instead, and the browser runs above load the scripts.

The fast suites' `build` failure (rc 5), read and left alone (lesson 13):
- `scripts/affected_tests.py` chose only `tests/test_agents_page.py` and `tests/test_inbox_page.py`: the branch changes
  no `ergostat/**/*.py`, so no unit test file is mapped to it. The `build` command runs pytest without Playwright, so
  both files skip at import ("No module named 'playwright'"). Pytest then collects nothing and returns 5. No test
  failed, and no code in this gap can change that.
- The fix belongs to the factory's own tooling, in a gap of its own. Either `affected_tests.py` counts browser files
  as nothing to run (`--collect-only`) when the build has no Playwright, or the build counts rc 5 as a pass. Changing
  it here would be work outside this gap, and adding a unit test only to give the build something to run would be a
  test that cannot fail (lesson 9). So no code changed this round.
- The browser runs above (rc 0, with Playwright) still stand. The merge queue runs the browser files in full.
