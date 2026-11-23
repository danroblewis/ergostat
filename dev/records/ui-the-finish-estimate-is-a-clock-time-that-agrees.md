# ui-the-finish-estimate-is-a-clock-time-that-agrees: The finish estimate is a clock time that agrees with the critical path

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q60 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /items Graph and Timeline (roadmap)

**The problem:** 'last of 1 epic done in about 1s (p90 1s)' appears seconds after the view, as a duration, beside 'critical path 5 items, done in about 15s'; the item page uses a third form. The Timeline lists 100+ epics oldest first, so the current one is three screens down.

**The change:** One sentence, present on first paint (or 'being worked out'): 'last epic (e100) expected 04:02, by 04:03 at worst (9 in 10)', not earlier than the critical path's end. The Timeline opens scrolled to 'now' with finished epics collapsed.

**User stories it serves:** F5, B4

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8794/items?view=graph the legend contains a clock time and 'at worst'; that time is ≥ now + the critical path's remaining duration; on Timeline the 'now' line is inside the viewport at load.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Round 1: built. 26 net lines of code (server.py +1, pages.js 0, relations.js +25), inside the budget.

- **The sentence** (`relations.js` `rgFinish`, `rgClock`): one legend key in place of the per-kind "last of N k
  done in about …" keys, e.g. "last epic (e100) expected 04:02, by 04:03 at worst (9 in 10)". It names the drawn open
  item with the latest p50 and uses its kind's last-finish p50 and p90. Both times are held to no earlier than
  the critical path's end (`d.end`) and rounded up to the minute, so the time shown is never earlier than the
  estimate. The date is added when it is not today. The critical path key no longer carries a duration; with no
  estimates and none pending (a moment travelled to), it says "ends about HH:MM" instead.
- **First paint:** the server's items-graph answer now carries `eta_pending` (live, and no estimate yet). The legend
  says "the last item's finish: being worked out" until the estimate comes. A snapshot never says pending.
  A failed estimate also reads as pending: the worker tries again every 30 s (`eta_api.EVERY`).
- **Timeline:** "Collapse done" is now on by default for the Timeline as well as the Graph, and the toggle still
  turns it off. At load, once, the page scrolls the first unfinished row into view if it is off screen.
- Decisions taken without the owner, the most reversible first: the item page's own form ("Expected done Nov 22,
  04:02 (p90 …)") was left alone, because the definition names only /items Graph and Timeline. The clamp to the critical
  path's end applies to the sentence only. The Timeline's bars and whiskers still show the simulation as it is.
- Tests (tests/test_items_page.py): `test_the_finish_is_a_clock_time_no_earlier_than_the_critical_paths_end`,
  `test_the_timeline_opens_at_now` are new. `test_the_timeline_draws_what_happened_and_what_is_projected` was changed
  for the new collapse default. Each guarded piece was broken once and seen to fail: no scroll (opens_at_now);
  no clamp (finish, synthetic answer); the old collapse default (timeline draws); `eta_pending` inverted (finish,
  first paint). The whole of tests/test_items_page.py passed (23, rc 0); ruff is clean. Not run here: the unit suite
  and the other three browser files (left to the factory and the queue). `node --check` was refused, but the
  page's JS ran in every browser test. `main` is already in the branch, so there was nothing to merge.
