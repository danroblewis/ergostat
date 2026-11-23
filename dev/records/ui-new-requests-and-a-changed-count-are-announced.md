# ui-new-requests-and-a-changed-count-are-announced: New requests and a changed count are announced

depends-on: [ui-what-waits-for-me-is-one-step-from-every-page-an]

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q77 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram side list; header counts

**The problem:** The page changed 21 times in 8 s with one polite live region in the whole product; a screen-reader user is never told a request is waiting.

**The change:** The header counts and the 'Waiting for you' heading sit in an aria-live='polite' region that announces only a change of count ('1 new request waits for you').

**User stories it serves:** H5, E1

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
The element holding 'N wait for you' has aria-live='polite' (or is inside one) and its text changes only when N changes.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
