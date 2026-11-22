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
