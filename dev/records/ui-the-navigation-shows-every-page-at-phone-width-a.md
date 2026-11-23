# ui-the-navigation-shows-every-page-at-phone-width-a: The navigation shows every page at phone width and at 200% zoom

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q05 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** all pages, header

**The problem:** At 390 px and at 720 px the tab strip is cut at 'Mode…'; Check and Guide are off-screen with no cue. The Guide, the only explainer, cannot be found on a phone.

**The change:** Below 760 px wrap the tabs onto two rows (no sideways scroll). Keep the current page underlined.

**User stories it serves:** A3, H4, H5

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
At 390x844 and 720x450 every one of the eight nav links has its bounding box fully inside the viewport, and document.scrollingElement.scrollWidth equals its clientWidth.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Round 1: built (778d33cd). `ergostat/web/static/style.css` gets one rule below 760 px: the nav takes a row of its own
and wraps (no sideways scroll); `a.on` keeps its underline. 3 net lines of code, within the budget of 60.

Choices made with no one to ask (each reversible):
- The 700 px rule's sideways scroll and right-edge fade on the nav were removed, because nothing scrolls now.
- The acceptance test `tests/test_items_page.py::test_the_navigation_shows_every_page_at_phone_width_and_at_200_percent_zoom`
  (phone 390x844, zoom-200 720x450, all eight pages) serves its own unseeded copy of image-squeeze (`nav_site`).
  On the shared `site`, opening Loops/Model records ergostat's first offered model changes
  (ergostat/control/proposals.py), and that made `test_the_model_changes_are_found_by_heading_search_and_panel`
  (which counts exactly three) fail when it ran after the new test.

Tests: the new test was seen to fail with the rule switched off (both sizes: Loops…Guide past 390 px, Guide past 720 px)
and with `nowrap` (phone: Check and Guide off-screen). `tests/test_items_page.py` under the watchdog with Playwright:
23 passed, none skipped, rc 0. ruff clean. Not run here (by the factory's rules): the unit suite and the other three
browser files. No example touched, so no demo_check. main is an ancestor of the branch, so there was nothing to merge.

Round 1, after the build step failed (rc 5): the failure is in the factory's build step, not in the branch's code.
`[suites] build` runs `scripts/affected_tests.py` without Playwright. The branch changes one style sheet and one browser
test file, so the step picks only `tests/test_items_page.py`. That file skips whole without Playwright (line 24), and
pytest gives rc 5 because no test ran. With Playwright, under the watchdog, the same file passed again:
23 passed, none skipped, rc 0. The code is unchanged. Changing `affected_tests.py` (for example, to treat a selection
that is all skipped browser files as collection only) or setting `build_browser = true` is outside this gap (lesson-13).
It belongs in a gap of its own. Until then, a branch that touches only page styles and a browser test fails this step.

Round 1, the second build failure (rc 5, same cause). The branch now also tests the narrow-width rule in the style
sheet's own unit file, which runs without a browser:
`tests/test_style_tokens.py::test_below_760_px_the_tabs_wrap_and_never_scroll_sideways`. It checks that the 759 px
block wraps the nav with `overflow-x: visible`, that no narrower block gives the nav a sideways scroll again, and that
`a.on` keeps its underline. It is a static check of the sheet, not a stand-in for the browser acceptance test. The
build step now selects this file as well as `tests/test_items_page.py`. Run without Playwright, the pair gives
6 passed, 1 skipped, rc 0. I could not run `scripts/affected_tests.py` itself because the command was refused. I saw the
new test fail on two breaks: `flex-wrap: nowrap` in the 759 px block, and `.bar nav { overflow-x: auto; }` added to the
700 px block. Both breaks were then reverted, and `style.css` is unchanged in this commit. ruff is clean. No code
outside `tests/` changed, so the net code lines are still 3.
