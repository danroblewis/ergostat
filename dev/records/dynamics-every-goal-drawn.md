# dynamics-every-goal-drawn: Dynamics: every goal is drawn as desired level and gap in its own system

depends-on: [dynamics-goals-and-loop-folding-proposal]

Problem (R5 piece 3): on :8796 ?system=product none of the three goals is drawn, while the users stock's panel names a goal on it: the diagram and the panel disagree (shots/story-6-g3-dyn-product.png, sdxb-8796-product.png). image-squeeze and big draw 'desired' and 'gap' correctly (sdxb-8797-api.png). Decision 2: in Dynamics a goal is a goal-seeking auxiliary.
Change, as the proposal settles: ergostat/dynamics.py emits for every goal, in the goal's own system, the desired-level auxiliary, the gap auxiliary and the connector from the gap to the flow its actor drives; when the actor's flow is in another system the link goes through the system's port; when nothing closes the goal (open loop, no actor) the gap carries a 'no feedback' mark and no link. Bounds are written as filed Q23. The stock's panel and the drawing use the same goal list. The legend and the Guide frame that shows a goal-seeking structure explain 'no feedback'.
Definition of done:
1. On :8796 ?system=product the three goals are drawn, each with desired level, gap and its link or the 'no feedback' mark.
2. For every demo, every goal in /api/loops has a gap node in /api/graph?view=dynamics&open=* (a test walks them).
3. The users panel and the diagram name the same goals.
4. Layout rules report no new critical violation; the legend explains 'no feedback'.
Files: ergostat/dynamics.py, ergostat/web/static/dynamics.js, ergostat/guide.py, tests/test_dynamics_view.py, tests/test_diagram_rendering.py.
Acceptance tests: unit: a goal with an actor in another system yields gap, desired and a port link; an open-loop goal yields the mark; the every-goal walk over the demos.
Budget: 130 net lines.

Milestone: r5-dynamics-tells-the-story. Owner items: R5 piece 3. From the owner's list and the design review of 2026-11-22.
