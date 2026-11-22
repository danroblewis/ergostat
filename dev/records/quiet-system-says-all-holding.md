# quiet-system-says-all-holding: A quiet system says so: 'all goals holding, nothing being worked'

depends-on: [goal-state-says-its-system-and-upkeep]

Problem (R7 piece 8): when no goal of a system is off the page shows nothing about it: an empty attention group and rows without emphasis. A reader cannot tell 'healthy' from 'not loaded' or 'not measured' (shots/story-2-c4-located-worked.png). Needs each goal's system (goal-state-says-its-system-and-upkeep).
Change: one server function per system returns its quiet sentence: 'all N goals holding, nothing being worked' when none is off, open or unknown and no item is taken in it; 'all N goals holding, 3 items being worked' when leases are out; nothing otherwise. It is printed on the Goals page's system group heading (filed Q16's grouping), in the system's panel on the diagram, and on the closed box's title row when dynamics-box-goal-rows has landed (the box then folds its holding rows under the sentence). Unknown goals are never called holding.
Definition of done:
1. On a fixture whose system has 14 goals holding, its group on /goals and its panel read 'all 14 goals holding' with the count being worked from the leases.
2. A system with one unknown goal does not show the sentence.
3. The sentence disappears within one poll of a goal going off.
4. The count equals /api/loops filtered by system.
Files: ergostat/state.py or ergostat/web/server.py (the sentence), ergostat/web/static/pages.js, details.js, dynamics.js, tests.
Acceptance tests: a unit test of the sentence for quiet, being-worked, unknown and off fixtures; a browser check on the fixture.
Budget: 50 net lines.

Milestone: r7-evidence-is-a-runbook. Owner items: R7 piece 8. From the owner's list and the design review of 2026-11-22.
