# timeline-shows-the-simulated-schedule-in-order: Timeline: rows in projected order, items not scheduled set apart with reasons, each block's capacity named

depends-on: [eta-works-out-on-the-factory-record]

Problem: the owner asks 'what finishes when and in what order'. Even with estimates, relTimeline's el.draw (ergostat/web/static/relations.js:222) orders rows by `segments[0][1] ?? es ?? first`: an open item's segments start at its creation, so rows follow creation order and the ranked backlog is scattered instead of a waterfall. Items the simulation leaves out (parked, or waiting on parked; the unscheduled flag from eta-works-out-on-the-factory-record) get no explanation, and nothing says which capacity the simulation used (the note at relations.js:362-366).
Change (no new page, panel or control): with estimates, unfinished rows are ordered by eta.start (p50), then eta.p50, then id; finished rows stay above as what happened. Unscheduled items go in a group at the end under 'Not scheduled (N)', each row showing its why ('parked', 'waits on gap/x, which is parked') and no bar ahead. The word 'held' is not used (it is a goal's word). The legend's per-kind sentence (filed Q60's form, times through filed Q34's formatter) adds the count: 'last of 40 gaps expected Tue 24 Nov 14:10, by Wed 09:00 at worst (9 in 10); 3 not scheduled'. The note names each block's simulated capacity and source: 'implementor 9 at once (pool stock.implementor-pool now), reviewer 6' (eta_api.merge passes capacity sources). Before the estimates are worked out the note says 'Working out the schedule: a simulation of N unfinished <kind> at each block's capacity' and any bars drawn from the forward pass are labelled as such. The item page's estimate line says 'not scheduled: <why>'. SPEC §5a Timeline row updated.
Definition of done:
1. Unfinished rows are in projected-start order: the projected bars' left edges are non-decreasing down the rows.
2. Unscheduled items are grouped last with reasons; no reader text on the Timeline contains 'held'.
3. The legend gives a clock time with its date and the count not scheduled.
4. The note names each block's capacity and source.
5. With the eta stubbed to None the note contains 'Working out the schedule'.
Files: ergostat/web/static/relations.js, ergostat/web/eta_api.py, ergostat/web/static/pages.js (item page line), docs/SPEC.md, tests/test_items_page.py.
Acceptance tests: browser on a fixture of 30 items with a 3-wide pool and ranks opposite to creation order (edges non-decreasing, at most 3 bars overlap at any x); a paused item and its dependent under 'Not scheduled (2)'; live check GET only on :8798/items?kind=gap&view=timeline: a staircase, not all at now. Rebase onto filed Q59/Q60 if they landed.
Budget: 90 net lines.

Milestone: timeline-real-schedule. Owner items: 17. From the owner's list and the design review of 2026-11-22.
