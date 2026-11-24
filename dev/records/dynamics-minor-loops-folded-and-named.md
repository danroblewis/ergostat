# dynamics-minor-loops-folded-and-named: Dynamics draws the named loops and one per goal; minor loops are listed and drawn when selected; a loop may be named in the model

depends-on: [dynamics-goals-and-loop-folding-proposal]

Problem (R5 pieces 4 and 5): on software-factory product all 18 elementary loops are drawn, named by their paths ('all-live via regressions and churn and asks'), markers and names piled on each other and on the users stock; '+1' on a marker is unexplained (shots/story-6-g4-R2.png, story-6-g4-B1.png, sdxb-annotated-product.png). A reader cannot find the two or three mechanisms that explain the system.
Change, as the proposal settles: (1) the drawing shows a marker only for loops named in the model and one loop per goal (the balancing loop through its gap); every other loop is 'minor': listed in the side list's folded 'minor loops (N)' and drawn (marker and lit path, in the accent as any trace) only while selected or hovered there. '+1' is removed. (2) a `loops:` entry in the model may name a loop by its parts (SPEC §12a); the diagram prints the name at the marker, the panel shows the path; an unnamed drawn loop is 'B3' with its goal's name. (3) the software-factory demo names product's main loops (e.g. 'word of mouth', 'support load'). (4) the loop that dominates now (/api/dominance) is named at the head of the list (R5 piece 8's second half).
Definition of done:
1. On :8796 ?system=product at most the named loops plus one per goal have markers (count asserted against the model), and no marker text contains '+'.
2. Selecting a minor loop in the list draws its marker and path; deselecting removes it.
3. A named loop shows its name on the diagram and its path in the panel.
4. The box's and list's loop counts agree (filed Q22) and say 'N named, M minor'.
Files: ergostat/dynamics.py, ergostat/spec/causal.py (names), ergostat/web/static/dynamics.js, demos/software-factory (loop names), docs/SPEC.md §12a, tests/test_dynamics_view.py, tests/test_diagram_rendering.py.
Acceptance tests: unit: naming and the minor flag; browser: 1-3 on :8796.
Budget: 150 net lines.

Milestone: r5-dynamics-tells-the-story. Owner items: R5 pieces 4, 5. From the owner's list and the design review of 2026-11-22.
