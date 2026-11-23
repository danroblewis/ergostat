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

## Where it stopped

Built, round 1. The header's "N wait for you" link sits in a `<span class="waits-said" aria-live="polite"
aria-atomic="true">` (index.html) that is always present, so a count appearing from 0 is announced as well. Its text is
written only when N changes (setText), so a header poll with nothing new says nothing. At phone width the wrapper,
not the link, takes the header's first line, and only while the link shows (style.css).
Acceptance: tests/test_diagram_rendering.py::test_a_changed_count_of_what_waits_is_announced. It watches every write
into the polite region holding the link for two polls with nothing new, then for a second request. It was seen to
fail on two breaks: the text written on every poll, and the aria-live removed.
Not run here: the whole of tests/test_diagram_rendering.py. A serial run was stopped at the session's 20-minute
command limit before it reported, and a longer background run was refused. Only the new test and
test_what_waits_for_you_is_one_step_from_every_page were run (2 passed, rc 0). The rest of that file and the other
three browser files are left to the factory's runs.
Fast-suite fix: the build step ran only the browser file, which skips with no Playwright (rc 5, nothing run). A
unit half is added, tests/test_graph_cli_web.py::test_the_count_of_what_waits_sits_in_one_polite_live_region (the
link inside the polite, atomic region; its text written through setText, which writes only a changed text). It was
seen to fail with aria-live removed. That file passes whole (43 passed).

Choices made with nobody to ask (each easy to reverse):
- The words announced are the visible "N wait for you", the header's own words (Q43). No separate
  "1 new request waits for you" sentence is added: inside an atomic region it would be read together with the
  count, and a hidden extra span would change the header's first-thing order the Q43 test checks.
- The side list's "Waiting for you" heading is not made a second live region. Its count changes with the header's,
  so on /diagram the same change would be announced twice. The header's region is the one announcer, on every page.
- The other header counts (goals off, model upkeep, running) stay outside the region. The definition announces only
  a change in what waits for you.
