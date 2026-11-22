# dynamics-goals-and-loop-folding-proposal: Proposal: every goal drawn in Dynamics, and which feedback loops are drawn, named or folded (docs/proposals/dynamics-goals-and-loops.md)

depends-on: []

Problem (R5): the leaf notation is Sterman's and stays. But on software-factory's product, the demo's subject, none of its three goals is drawn (image-squeeze and big do draw 'desired' and 'gap': shots/sdxb-8797-api.png); all 18 elementary loops are drawn with path names ('all-live via regressions and churn and asks'), their markers and names piled on each other and on the users stock; '+1' on a marker is unexplained (story-6-g3-dyn-product.png, sdxb-annotated-product.png, story-6-g4-R2.png). Which goals get a desired level and gap, and which loops are worth drawing, are modelling decisions with layout cost.
Change: write docs/proposals/dynamics-goals-and-loops.md settling: (1) the rule by which every goal is drawn as a goal-seeking structure in its own system (desired level, gap, the link to the flow it drives, or the 'no feedback' mark when nothing closes it), why product's goals are not drawn today (ergostat/dynamics.py) and the port link when the actor is in another system; (2) which loops are drawn: named loops and one per goal; the rest listed as minor in the side list and drawn when selected; '+1' removed; the ranking (dominance now, /api/dominance) and the cap; (3) loop names: a `loops:` entry may name a loop in the model (SPEC §12a); the diagram shows the name, the panel the path; the names for software-factory product's loops; (4) what the loop count on a box and in the list then means (with filed Q22 and the heading of goals-and-loops-cross-referenced); (5) the layout cost of the added gap structures on :8797. It confirms or amends dynamics-every-goal-drawn and dynamics-minor-loops-folded-and-named.
Definition of done:
1. The proposal settles 1-5 with a before/after sketch of software-factory product.
2. Each rule cites Sterman's form.
3. The acceptance for each build gap is stated as counts on the demos' structure.
Files: docs/proposals/dynamics-goals-and-loops.md.
Acceptance tests: review only.
Budget: about 180 lines, no code.

Milestone: r5-dynamics-tells-the-story. Owner items: R5 (pieces 3-5). From the owner's list and the design review of 2026-11-22.

## Where it stopped

Round 2: the proposal is written and answers both round-1 findings. `users-won` now lists flows
only (`through: [flow.shipped, flow.signups]`). Rule 2 says a loop runs through a goal's gap when
it contains `goal.x`, or, for a goal whose serving block reads its stock, when it contains that
`stock.X` → `block.B` read, which is the link the gap is drawn on. Ties go to a named loop first,
then dominance, then the first flow, and the text no longer says that no rule picks a loop. The
acceptance adds counts that tie each `loops:` entry to exactly one loop and each product goal to
its named loop.
The loop membership was worked out by hand from the YAML because a scratch script to list the
causal loops was refused. The build gaps check it against `names()`, as the acceptance says.
Overrun reason: the proposal is about 230 lines against about 180, because round 1's fix needed the gap-matching rule and the hand check of each named loop written out; it is docs only, no code.
