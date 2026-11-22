# ui-open-into-and-every-panel-link-show-that-somethi: Open, Into and every panel link show that something is happening

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q11 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram (Open, Into, links that open a panel), /loops, /items

**The problem:** After Into the canvas and the side list stay fully blank for 1 to 5 s; the 'fixer' link takes 3 to 4 s with no cue; Loops and Items show only their heading while loading. All read as a crash.

**The change:** Keep the old diagram, dimmed, until the new one is ready, and draw 'Opening api…' on the canvas at once. Never blank the side list. A panel opening shows its title and 'Loading…'. Loops and Items show 'Loading…' under the heading.

**User stories it serves:** A5, H2

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
300 ms after clicking Into on api (:8797) the canvas contains visible text and the side list is not empty; 300 ms after clicking the 'fixer' link in a goal's evidence the panel region contains 'fixer'.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Round 1: built (net +30 lines in `ergostat/`, inside the budget).

- **Into, Open and every other move between diagrams** (`util.js` route, `diagram.js` pageDiagram): the diagram
  being left is kept: its canvas, dimmed and not clickable (`g.was`), with "Opening api…" in the middle of the canvas
  (or "Loading…" for a move that opens nothing, e.g. a view switch), and its side list, dimmed, until the new answer
  is drawn over both. While it is there `S.layout` is null, so nothing waits on or redraws the old layout. A first load
  (no diagram before) shows the "Loading…" it always showed.
- **A panel opening** (`details.js` `panelLoading`; used by openNode, openLoop, openAgent and openEdge's flow, and
  `dynamics.js` openNodeSD and openEdgeSD's flow): its kind, title and "Loading…" at once, then the panel as it was.
  Where the read fails, the note says "Could not be read." rather than staying "Loading…". Panels that read nothing
  first (a system, a process node) were already instant and are untouched.
- **Loops and Items**: "Loading…" under the heading, replaced by the first answer (Items: also removed when its
  first answer is a bad filter, said in the chip as before).

Choices made alone (the most reversible): the acceptance names the `:8797` demo, its `api` system and a `fixer` link;
neither the demo nor `fixer` is in the clone, so the test uses `examples/big` (it has a system `api` with goals) and
the agent link `api-q0-drain` in the goal `api-q0-low`'s panel (the loop's parts table, where a goal's agents are
linked). The server is made slow on purpose (an init script holds back the named API answers 2.5 s), so "300 ms
after" falls inside a slow answer on any machine.

Tests (tests/test_diagram_rendering.py):
`test_into_open_and_a_panel_link_show_at_once_that_something_is_happening` and
`test_loops_and_items_say_loading_under_their_heading_until_their_answer[loops|items]`: pass. Each was seen to fail
on a break: the diagram left not kept (no canvas text), the side list not carried (side blank), openAgent without
its loading panel (h2 is the loop's), and Loops/Items without "Loading…" (both params fail).
tests/test_items_page.py: 21 passed, rc 0. ruff clean. The whole of tests/test_diagram_rendering.py was started
under the watchdog but stopped unfinished at the session's 20-minute limit for a background command, so its result is
not known; of it, the three nearest the change pass (rc 0): every part opens its panel even mid-redraw, opening and
closing a system keeps it on the screen, pages are ordinary links walked back. Not run by me: the unit suite and the other browser files
(left to the factory and the merge queue, as the brief says); no origin/main ref in the clone (main is the base).

Round 1, the build's fast suites (rc 5): no code fault found, and none changed. `[suites] build` runs
`scripts/affected_tests.py`. It picks the test files the branch changed, plus `tests/test_<module>.py` for each changed
`ergostat/**/*.py`. This branch changes only JS and CSS, so the only file picked is `tests/test_diagram_rendering.py`.
That file skips itself whole without Playwright (`pytest.importorskip("playwright.sync_api")`), and the build runs
without Playwright, so pytest collected nothing and returned rc 5 ("1 skipped"). The page's own tests can pass only
where Playwright is installed (the four browser files' run, `--with playwright==1.63.0`).
I left this alone, the most reversible choice. Mapping the static files to their tests in `affected_tests.py`, or
treating an all-skipped browser file as a pass, is the factory's change, not this gap's (lesson 13). A unit test made
up only so the selection runs something would be a test that can't fail (lesson 9).
Checked here: `tests/test_style_tokens.py` (the unit file that checks style.css, which this branch touches): 5 passed;
ruff clean. Refused here: a command that ran the style-tokens tests, then
`uv run python -c "import playwright"`, then a grep of pyproject.toml and dev/factory.toml. So whether Playwright is
installed in this container was not seen.

Round 1, the build's second try: the fast suites now run something that can fail. The branch now changes
`tests/test_style_tokens.py` (a unit file, no Playwright), so `affected_tests.py` picks it along with the browser file.
Its new test, `test_the_diagram_left_while_another_opens_is_dimmed_and_cannot_be_clicked`, pins this branch's
style.css rule: the diagram left and its side list are dimmed (opacity < 1) and take no clicks
(`pointer-events: none`). It was seen to fail (1 failed, 5 passed) with `pointer-events` taken off the side list's
rule, and to pass again once the rule was restored. `tests/test_style_tokens.py tests/test_diagram_rendering.py`
without Playwright: 6 passed, 1 skipped, rc 0. ruff clean. The page's browser tests still need Playwright, which is
only in the four browser files' run.
Refused here: a command that wrote this test with a shell heredoc, ran it, broke and restored style.css with sed and
`git checkout`, then ran affected_tests.py and ruff (each step was then done on its own, with the edit tool). Also
refused: `git diff --stat; uv run python scripts/affected_tests.py -- uv run python -m pytest -q`. So the selection
was run by hand with the two files it picks, not through affected_tests.py.
