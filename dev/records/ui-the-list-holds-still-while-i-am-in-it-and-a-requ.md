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

The fast suites' `build` failed again, the same way (rc 5, "2 skipped", read on 2026-11-22). Still no code changed:
- The tail shows the same thing as before: `affected_tests.py` picked `tests/test_agents_page.py` and
  `tests/test_inbox_page.py`, both skipped at import because the build has no Playwright, and pytest returned 5
  because nothing ran. No test failed. No change to the page code can make a browser file run without Playwright.
- I left two ways to make the build pass undone. Each is easy to do later in its own gap:
  (a) Change `scripts/affected_tests.py`, or the `[suites] build` command, so rc 5 counts as a pass, or so it runs
  `--collect-only` when every selected file is a browser file and the build has no Playwright. This is factory
  tooling, outside this gap (lesson 13).
  (b) Add a unit test only so that the build has something to run. That would be a test whose failure guards nothing
  in this change (lesson 9).
- What needs to happen: the factory runs this gap's two browser files with Playwright (`build_browser = true`, or the
  merge queue). They passed with rc 0 in the first session (above).

## Where it stopped (round 2)

No review findings came to this round, and no code changed. The branch is the round-1 build, with main (2468c59b) as
its base. main has not moved in the clone, so there was nothing to merge. Run again on 2026-11-22, each under
`scripts/suite_watch.py` with Playwright 1.63.0 through `scripts/named_tests.py`:
- `tests/test_inbox_page.py`: rc 0, 2 passed (116.9 s).
- `tests/test_agents_page.py`: rc 0, 4 passed (42.4 s).
- `uv run ruff check ergostat tests scripts`: clean.

The build without Playwright still selects only these two browser files. Both skip at import, so it returns rc 5, as
said above. That is factory tooling, so it was left alone (lesson 13). The gap needs its browser files run with
Playwright (`build_browser = true`, or the merge queue). The unit suite and the four browser files were not run here,
as the house rules say. Refused this round: a `cat >> … <<'EOF'` append to this file followed by the commit. The text
was added with the editor instead.

## Where it stopped (third build rc 5)

The build failed a third time, and the same way. `affected_tests.py` picked `tests/test_agents_page.py` and
`tests/test_inbox_page.py`. Both skipped at import because the build has no Playwright, and pytest returned 5 with
nothing run. No test failed. No code changed this time, for the reasons given above: no change to the page code can
make a browser file run without Playwright, and the fix belongs to the factory's tooling (lesson 13). Every later build
of this branch will fail the same way until one of these happens:
- the build treats a selection of only browser files as `--collect-only`, or counts rc 5 as a pass;
- `build_browser = true` is set for this gap;
- the gap goes to the merge queue.

The browser files passed with Playwright in rounds 1 and 2 (rc 0, above). Refused this time: a `cat >> … <<'EOF'`
append to this file followed by `git add dev/records && git commit …`. The text was added with the editor.

## Where it stopped (fourth build rc 5)

The fourth build failed the same way as the first three: the two browser files skipped at import ("No module named
'playwright'"), nothing ran, and pytest returned 5. No test failed, and again no code changed, for the reasons above
(lesson 13 and lesson 9). One new point: `dev/factory.toml` has `build_failures = 6`, so this is the fourth of six
failed builds that park the gap. Two more builds that fail this way will park a branch whose own tests pass. The way
out has to come from outside this gap. Any one of these is enough, and each is small and easy to undo: set
`build_browser = true` for this gap, or have `scripts/affected_tests.py` treat a browser-only selection as
`--collect-only` when Playwright is missing, or send the gap to the merge queue as it stands. Refused this time: a
`cat >> … <<'EOF'` append to this file chained with `git add dev/records && git commit …`. The text was added with the
editor.

## Where it stopped (round 3: main 277a9c6c merged)

The factory's merge of main (277a9c6c) conflicted in two files. Both are resolved so that main's change and the
branch's change both stay (merge commit e1dfdfa9):
- `ergostat/web/static/pages.js`: the Agents group heading is main's ("ai · 2", with the rung in small text, from
  ui-agents-a-group-heading-counts-its-rows). The agent rows keep the branch's `data-row` key, which the hold-still
  note counts. The heading row has no `data-row`, so it is not counted as an update.
- `tests/test_agents_page.py`: both tests are kept, main's
  `test_each_group_heading_counts_its_rows_as_the_summary_does` and the branch's
  `test_the_agents_table_holds_still_while_the_pointer_is_on_a_row`, each with its own close.

No other code changed. Run after the merge, each under `scripts/suite_watch.py` with Playwright 1.63.0 through
`scripts/named_tests.py`:
- `tests/test_agents_page.py`: rc 0, 5 passed (39.1 s).
- `tests/test_inbox_page.py`: rc 0, 2 passed (104.0 s).
- `uv run ruff check ergostat tests scripts`: clean.
Not run here, as the house rules say: the unit suite and the four browser files. The merge queue runs them. The
build without Playwright will still return rc 5 for the reason given above.

## Where it stopped (fifth build rc 5, after the round-3 merge)

The merge of main 277a9c6c was already done when this session began: merge commit e1dfdfa9 has both parents, there are
no conflict markers left in `pages.js` or `test_agents_page.py`, and the tree is clean. So nothing was left to resolve.
The fifth build failed the same way as the first four. `affected_tests.py` picked only `tests/test_agents_page.py` and
`tests/test_inbox_page.py`. Both skipped at import ("No module named 'playwright'"), and pytest returned 5 with nothing
run. No test failed. No code changed, for the reasons given above: the fix belongs to factory tooling (lesson 13), and a
filler unit test would be a test that cannot fail (lesson 9). `uv run ruff check ergostat tests scripts` is clean. This
is the fifth of the six failed builds (`build_failures = 6`) that park the gap. One more build of this branch without
Playwright will park it. Its own browser files passed with rc 0 after the merge (round 3, above). The way out is the
same as before. Any one of these is enough: `build_browser = true` for this gap, a browser-only selection treated as
`--collect-only` (or rc 5 counted as a pass) when Playwright is missing, or sending the gap to the merge queue.

## Where it stopped (sixth build rc 5)

Again the merge of main 277a9c6c was already done when this session began. `main` is an ancestor of HEAD, there are no
conflict markers, and the tree is clean, so nothing was left to resolve. The sixth build failed in the same way as the
other five: only the two browser files were selected, both skipped at import with no Playwright, and pytest returned 5.
No test failed. No code changed, for the same reasons (lesson 13, lesson 9). `uv run ruff check ergostat tests scripts`
is clean. The page code has been the same since round 1. Its own browser files passed with rc 0 after the merge
(round 3). If this build parks the gap, nothing in the gap is left to do. What is missing is a build that can run these
files: `build_browser = true` for this gap, a browser-only selection treated as `--collect-only` when Playwright is
missing, or the merge queue.

## Where it stopped (round 4: a unit test the build can run)

No review findings came to this round. `main` (277a9c6c) is still an ancestor of HEAD and has not moved, so there was
nothing to merge. The page code is unchanged since round 1.

What changed: one unit test in `tests/test_inbox.py`,
`test_a_request_answered_leaves_the_attention_list_the_side_list_keys_by_what`. It follows main's own way out of the
same rc 5 (ab17bb6e, from ui-agents-a-group-heading-counts-its-rows: a unit test of the contract the page reads). Now
that `tests/test_inbox.py` is in the branch's diff, `affected_tests.py` selects it, so the build without Playwright has
tests to run. It is not a filler test (lesson 9). It checks the server half of the side list's "no longer waiting"
mark: each of three held requests is in the attention list under its own `what` (`action/<short>`, the row's
`data-inbox` key) with its verbs. Once one is denied through the API, that one is gone and the others keep their order.
The mark goes on a row only when its `what` drops out of the answer. If answered requests stayed in it, or were keyed
some other way, the mark would never show, and the browser test is the only other check of that.
Choice made without asking (easy to undo: delete the test): adding this test instead of waiting for factory tooling to
change.

Tests run this round:
- The new test alone: passed. With `state.py`'s asks keyed by `e["summary"]` instead of `e["id"]` (a break, then
  reverted, so `git diff ergostat` is empty), it failed at the first assert.
- `uv run python scripts/named_tests.py tests/test_inbox.py`: 31 passed (15.8 s).
- `uv run ruff check ergostat tests scripts`: clean.
- Not run this round: the two browser files (they passed with rc 0 after the merge, round 3), the unit suite and the
  four browser files (the house rules leave those to the factory and the merge queue).
- Refused this round: `uv run python scripts/suite_watch.py -- uv run python scripts/named_tests.py
  tests/test_inbox.py::… 2>&1 | tail -15` and `uv run python scripts/suite_watch.py -- uv run python
  scripts/named_tests.py tests/test_inbox.py`. Both were run instead as plain `uv run python scripts/named_tests.py …`,
  with no watchdog (a single serial unit file).

## Where it stopped (round 5: a keyboard answer keeps the hold)

The findings of review 1 (fix), each answered:
- Blocking (util.js:81 with diagram.js:1323): a request answered from the keyboard, with the pointer off the list,
  ended the hold. Its button was disabled while it had focus, `heldStill` does not count a disabled focused element, and
  the row and its reply went at the next refresh with focus on the body. Fixed in `diagram.js` (+2 net lines): the
  reply text is focusable (`tabindex="-1"`). When the button that answers has keyboard focus (`:focus-visible`), focus
  moves to the reply before the buttons are disabled. So the focus stays in the row, the list holds, and the answered
  row stays in its place, saying so, until the reader leaves.
  Choice made without asking (easy to undo): this applies only to a keyboard answer. After a mouse click the focus stays
  on the disabled button and does not hold the list, as before, so the row still goes when the pointer leaves. That is
  what `test_approve_in_the_side_panel` checks.
  New test `tests/test_inbox_page.py::test_a_request_answered_from_the_keyboard_holds_the_list_with_the_pointer_off_it`:
  with the pointer off the list, it types a reason, presses Shift+Tab to Deny and then Enter. It checks the request is
  denied, then for 8 s (with alarms coming) that the row is still there, has not moved, and holds the focus. Then it
  leaves and the row goes. Break seen to fail (lesson 9): with the `said.focus()` call removed, it fails at the focus
  check ("el.contains(document.activeElement)" False).
- Non-blocking (tests/test_inbox.py, the round-4 unit test covers server behaviour that was already there): it stays.
  It pins the contract the side list's "no longer waiting" mark reads (`what` keys, and an answered request leaving the
  answer), and it gives the build without Playwright tests to run. Delete it if that is not wanted.

Tests run this round (Playwright 1.63.0, under `scripts/suite_watch.py`, through `scripts/named_tests.py`):
- `tests/test_inbox_page.py`: rc 0, 3 passed (109.8 s).
- `uv run ruff check ergostat tests scripts`: clean.
- Not run, as the house rules say: the unit suite, the four browser files, and `tests/test_agents_page.py` (the Agents
  code did not change). `main` has not moved in the clone, so there was nothing to merge.
- Refused this round: a `python3 - <<'EOF'` edit script on `diagram.js`. The edit was made with the editor instead.

## Where it stopped (round 6: the answer handler reads the row on the page)

The one finding of the review (blocking, diagram.js:1322-1330 with util.js:146-151, lesson 5 and lesson 9), answered:
- The cause is as the review says. A refresh patched in keeps the old row's nodes but hands them the new build's
  onclick, whose `row`, `said`, `why` and `n` were then detached. So after the first refresh a keyboard answer did not
  keep the focus, the typed reason was not sent, and the reply went to a detached span.
- Fixed in `diagram.js` (net +2 lines): the Approve/Deny/Done handler finds its row from the button pressed
  (`ev.currentTarget.closest(".inbox-act")`), and the row's `.note`, `Why` and number inputs inside it. The keyboard
  check is `ev.currentTarget.matches(":focus-visible")`.
- `tests/test_inbox_page.py::test_a_request_answered_from_the_keyboard_holds_the_list_with_the_pointer_off_it` now
  waits until three alarms have been patched in (several refreshes, the reader not in the list) before it focuses the
  reason box. It asserts the stored deny note equals the typed text ("not this week") and that the reply shows in the
  visible row. The side-list test now asserts that the one denied request's stored note is the typed reason.
- Break seen to fail (lesson 9): with the handler bound to the build-time row again, the keyboard test fails (the reply
  never appears in the row on the page: wait_for_function timed out after 20 s). Reverted, and the file was run again.

Tests run this round (Playwright 1.63.0, under `scripts/suite_watch.py`, through `scripts/named_tests.py`):
- `tests/test_inbox_page.py`: rc 0, 3 passed (117.9 s), after the break was reverted.
- `uv run ruff check ergostat tests scripts`: clean.
- Not run, as the house rules say: the unit suite, the four browser files, and `tests/test_agents_page.py` (the Agents
  code did not change). `main` has not moved in the clone, so there was nothing to merge.
- Refused this round: a no-op `python3 - <<'EOF'` command. It changed nothing.
