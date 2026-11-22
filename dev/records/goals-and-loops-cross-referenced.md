# goals-and-loops-cross-referenced: Each feedback loop that closes a goal names it; each goal's evidence names its feedback loops and its control loop, each a link into its view

depends-on: []

Problem (R11 piece 4): with 'goal', 'feedback loop' and 'control loop' now three words for three things, the page never says how they relate: ticket-factory lists 49 feedback loops and 16 goals in one panel and the counts cannot be reconciled (shots/sdx-8791-loops.png, infod-tf-home.png, ceb-tf-blocks.png). After the rename Blocks' list is headed for control loops with goal names as rows. A reader of Dynamics cannot get from a balancing loop to the goal it serves, nor from a goal to its controller in Blocks.
Change: (1) server: each causal loop (ergostat/spec/causal.py:242 loops) that passes through a goal's gap carries `goal: NAME`; each goal's state carries `feedback_loops: [ids]` and its control loop's parts (sensor, controller, actuator), from the spec only. (2) the Dynamics loop list's heading states the reconciliation: '49 feedback loops, 14 close a goal'. The row text for a loop that closes a goal is filed Q62's ('serves goal X'): this gap supplies the field Q62 reads and the link on the goal's name, and does not write a second wording. (3) the goal's evidence panel gains one line: 'Feedback loops: B3 word of mouth, R1 … (Dynamics) · Control loop: keep-backlog-clear (Blocks)', each a link that switches view with that loop selected (filed Q36/Q63's address and selection). (4) the Blocks loop panel names the goal and links to its balancing loop in Dynamics. correspond.py already maps parts across views.
Definition of done:
1. On :8791 every goal's evidence names at least its control loop and, when one exists, its balancing loop, as links that land on the other view with the loop selected.
2. Every feedback loop passing through a gap carries its goal in the graph answer; loops through no gap carry none.
3. The numbers reconcile: the count of loops with a goal is shown in the list's heading and equals the count in the answer.
4. A unit test on a small spec covers the mapping.
Files: ergostat/spec/causal.py, ergostat/state.py or ergostat/web/server.py, ergostat/web/static/dynamics.js, details.js, blocks.js, tests/test_dynamics_view.py, a browser test.
Acceptance tests: the unit test; a browser round trip goal -> feedback loop -> goal on :8791 (structure only, independent of which goals are off).
Budget: 100 net lines.

Milestone: goals-not-loops. Owner items: R11 piece 4 (with the owner's decision: goal, feedback loop, control loop). From the owner's list and the design review of 2026-11-22.

## Where it stopped

Built (round 1), about 40 net lines of code, within the 100 budget:
- `CausalLoop.goal` (spec/causal.py): the goal whose gap the loop runs through, the first by name when it runs
  through several (as its name is read), else None. The graph answer's causal loops carry it (graph.py).
- `loops/NAME` (server.py, through `graph.goal_loops`) carries `feedback_loops` (each `{name, label, polarity}`:
  the ids plus the Dynamics label, so the line can say "B3 word of mouth" in either view) and `control_loop`
  (`{name, sensors, controllers, actuators}` from `spec.loop`), from the spec only.
- Dynamics' list heading: "34 feedback loops, 28 close a goal" (software-factory), counted over the same loops as
  the total.
- The goal's panel (`openLoop`, details.js) gains the one line "Feedback loops: … (Dynamics) · Control loop: …
  (Blocks)". Each link goes through `openTool` (review.js: the existing switch-view-and-choose). In Blocks it chooses
  the loop's controller block, or its comparator when no block fills the controller.

Choices made with no one to ask (the most reversible):
- Point (4): blocks.js is not changed. Blocks' loop rows and its blocks' "In the loop of" links already open
  `openLoop`, which is the Blocks loop panel. It names the goal (its heading) and now carries the line linking to the
  goal's feedback loops in Dynamics. Writing a second panel would be a new panel.
- Q62's row text ('serves goal X') is not written in the list rows. For the round trip, the feedback loop's own
  panel (openCausal) says "Serves goal X" (Q62's wording, not a second one), with the link on the goal's name.
- tests/test_diagram_rendering.py's SD_WORDS check, which bans "goal" from Dynamics' side and panels, now skips just
  these two phrases (`SD_GOAL_SAID`), since the definition asks for them; SPEC §12a says so.
- Q36/Q63's address is not on main, so the links use `openTool` (it opens `/diagram?view=…&open=*`).

Not done here: done 1 says ":8791" (the ticket-factory instance). That instance is not in this container, so it was
not checked. The browser test checks the same structure on software-factory: every goal's panel names its control
loop, and the round trip goal -> feedback loop (Dynamics, chosen) -> goal -> control loop (Blocks, chosen) works.

Tests run: tests/test_dynamics_view.py (11 passed), tests/test_graph_cli_web.py, tests/test_scale_caches.py, and
test_diagram_rendering.py's new test plus the two Dynamics tests it touches (passed, under suite_watch, rc 0).
Each new test was seen to fail on a planted break: a goal given to a loop through no gap (unit), the heading
counting B loops (browser), and the panel's goal link opening the loop's name instead of the goal's (browser; it
first passed, because the first loop shared its goal's name, so the test now picks a loop named apart from its goal).
Not run here: the whole unit suite and the four browser files (the factory's build and the merge queue run them).
`main` is the base, and merging it was "Already up to date".

Round 2 (answering the one finding of round 1's review):
- graph.py goal_loops: `feedback_loops` now keeps every loop with the goal in its `goals` (each goal whose gap it runs
  through), not only those whose single `goal` (the first by name) is it, as SPEC's paragraph says. A loop through
  two gaps still carries one `goal` (the first by name) in the graph answer, and the heading counts it once.
- tests/test_dynamics_view.py: `test_a_loop_through_two_gaps_closes_both_goals`, a two-goal spec (a -> few -> thin
  -> move -> b -> calm -> slow -> back -> a) where one loop runs through both gaps: both goals list it. It was seen to
  fail on the old filter (`{'calm via move'} <= {'few'}`).
- Tests run: tests/test_dynamics_view.py (14 passed), tests/test_graph_cli_web.py and tests/test_scale_caches.py
  (83 passed with it), the browser round trip in test_diagram_rendering.py (passed, suite_watch rc 0); ruff clean.
  Merging main: "Already up to date". Still not checked on :8791 (not in this container), as said above.
