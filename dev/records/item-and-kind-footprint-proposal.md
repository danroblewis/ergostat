# item-and-kind-footprint-proposal: Proposal: how the diagrams draw what an item or kind touches, the item page's picture, and the kind's page (docs/proposals/item-and-kind-footprint.md)

depends-on: []

Problem: owner item 15 asks for 'the whole picture of an item type' and item 20 for 'the subset of the Dynamics and Blocks diagrams it passed through'. The data side is settled (kind-and-item-footprint-api); the drawing and the page are not. graph.select(..., around) (ergostat/graph.py:19; server.py:476-514) draws an explicit set only in Dynamics; blockdiagram.diagram (blockdiagram.py:1423) takes only open_ and focus; diagram.js runs on page-global state (S.graph, #detail, pins) so it cannot be mounted in another page without a refactor, and layout is slow (owner item 10). ?kind=K today only filters the Items page (pages.js:699), and intent decision 1 says no new pages. Two kind surfaces are planned (the kind's bar on the Items page and the kind's page) and need one rule between them.
Change: write docs/proposals/item-and-kind-footprint.md settling (defaults stated; the gaps proceed on them without an owner question):
1. How the diagrams draw a subset: Dynamics an explicit set as around= does, addressed /diagram?view=dynamics&item=ID or &kind=K; Blocks whole control loops touched (a partial loop is not a block diagram, docs/DISCIPLINES.md); how the path is marked (numbers on stocks, attempts on valves); how the subset coexists with the folded system tree and pins (pins keyed by item/kind, diagram.js:1032); its cost on the 800-part factory.
2. The item page: default, an inline drawing on demand, built last (item-page-draws-its-path), after the path strip and the links to the subset; the renderer refactor it needs and its cost.
3. The kind's page: default, the Items page with exactly one kind chosen, at /items/<kind> with /items?kind=K redirecting, no new nav entry (alternative /kind/K and why it loses); how that squares with decision 1 and R12; its sections in order (header with description and finishes/lives on; states now; its place in the model; definition; chart and cycle time; the list).
4. The one kind bar: one function kindBar(kind) in ergostat/web/static/kinds.js draws the kind's bar (title, description, finishes/lives on, state chips, counts) on both surfaces with the same markup. On the Items page the bar's disclosure opens the list in place and the kind's name in the bar is the link to /items/<kind>; on the kind's page the same bar sits above 'In the model' and its list is open. Filtering behaves the same on both.
5. Which filed fixes move: Q57 and Q58's content onto the kind page and path strip (Q61 is closed as superseded).
6. Confirm or amend the follow-on gaps: item-page-says-where-it-went, diagram-draws-what-an-item-or-kind-touches, the-kind-page, item-page-draws-its-path.
Definition of done:
1. The proposal exists and settles 1-6, each with a decision, the alternative and why it lost, citing code by file:line.
2. It is checked against docs/DISCIPLINES.md and docs/vocabulary.md (goal, feedback loop, control loop; taken, not held).
3. No code changes.
Files: docs/proposals/item-and-kind-footprint.md.
Acceptance tests: review only.
Budget: about 250 lines of proposal, 0 code.

Milestone: kind-and-item-pages. Owner items: 15, 20. From the owner's list and the design review of 2026-11-22.

## Where it stopped

Done: docs/proposals/item-and-kind-footprint.md settles 1-6 with a decision, an alternative and why it lost, and
code cited by file:line (checked against main at cc75b443). No code changed. No owner was asked; the most
reversible choices taken, and said in the proposal:
- The filed fixes Q57, Q58 and Q61, "R12" and "intent decision 1" are not in this clone. Decision 1 is read as the
  house rule "no new pages or panels". R12 is read as invariant 12, and the-kind-page checks it before building. Q57
  and Q58 move by content (a kind's content to the-kind-page, an item's travel to item-page-says-where-it-went).
- kind-and-item-footprint-api is not on main. The proposal treats the footprint as a set of part names (plus counts
  for an item), and its decisions do not depend on the shape.
- The cost on the 800-part dev/model was not measured (no code in this gap). The proposal makes measuring it, with a
  150-shape fallback, part of diagram-draws-what-an-item-or-kind-touches.
- Item page drawing: the proposal picks the smaller refactor (share the Guide's existing `guideDrawNow`) over a
  per-mount renderer, and amends item-page-draws-its-path to that.

Round 2 (the one finding of review 1, blocking): §1's Blocks part no longer uses diagram()'s per-loop `nodes`
(blockdiagram.py:1431-1438, drawn ids after fold, present only for goals with a reading). Touched goals now come
from the model alone: `spec.loop(g)` (spec/ir.py:1153-1160) in the footprint's own `kind.name` form, for every goal
in `spec.goals`. The drawn nodes are the unfolded `_Diagram` nodes that `mark_loops` (blockdiagram.py:1179-1204)
marks with a touched goal. The folded tree is now settled per view. Dynamics stays flat (server.py:501). Blocks
still folds (it returns at server.py:488-492, before that condition), through `blockdiagram.fold`
(blockdiagram.py:1230), with a new `keep` set (a node outside it is `"ext"`, so outside wires end at terminal ports)
and every system holding a kept node open, so no touched loop is hidden in a `sys:` box and the systems show as
frames. The two alternatives (unfolded with no frames, or closed systems as `Q(s)` boxes) and why they lose are
stated. The follow-on gap's tests in §6 are amended to match. The proposal is 254 lines. No code changed.
