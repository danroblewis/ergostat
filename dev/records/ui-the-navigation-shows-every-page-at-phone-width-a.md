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
