# ui-every-goal-name-is-a-link-to-its-evidence-and-th: Every goal name is a link to its evidence, and the part is marked

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q26 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram side list and Suggestions; /loops

**The problem:** The red bold goal name in Needs attention, the bold name under Suggestions and (by keyboard) the Loops rows do nothing; only a small 'Evidence' link works. Opening evidence marks nothing in the diagram.

**The change:** Every goal name is a button that opens the same evidence panel 'Evidence' opens, and rings the goal's stock (Dynamics) or its summing junction (Blocks), opening the system that holds it if needed. On Loops the name is a button.

**User stories it serves:** C1, H3, H5

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8791/ clicking the name of an off goal in the side list opens a panel whose title is that goal, and one diagram element gains the selection ring; on /loops the first cell of each row is a focusable button and Enter opens the panel.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Built, round 1. 15 net lines of code (diagram.js +11 net, style.css +3, pages.js +1 changed line), within the 60-line budget.

- `diagram.js`: `goalButton`/`showGoal`. The goal name in Needs attention (an attention entry `loop NAME`) and the bold
  name of a Suggestion that begins `loop NAME` are now `button.name`. The button, and the existing 'Evidence' link
  (which used to mark nothing), choose the goal's stock (`stock.X`, else `auxiliary.X`) in Dynamics or `goal.NAME`
  (its summing junction) in Blocks, so the shape gets the existing `.selected` ring. Then they call `openLoop`, the
  panel 'Evidence' opened before. If the only shape for the part is a closed system's box (a region with a `system`),
  that system is opened first through `S.toggleSystem`. This goes one level deep: a goal inside a closed system inside
  another closed system opens only the outer box, and the inner box is ringed. That is the most reversible choice;
  nested opening is not built.
- `pages.js`: on /loops the first cell holds a `button.name` (focusable, and Enter presses it) that opens the panel.
  The row's click is unchanged.
- `style.css`: `button.name` looks like the name it wraps (colour and weight inherited), with an underline on hover
  and the existing focus ring.
- The Blocks side list's own Loops rows (clickable `div`s, not focusable) were not changed: the change names /loops for
  "On Loops".
- Nothing new in the UI. No page, panel or view was added.

Acceptance test: `tests/test_diagram_rendering.py::test_a_goal_name_opens_its_evidence_and_rings_its_stock_or_its_summing_junction`
(the goal unboxed, and inside the closed system `desk`). It checks, in Dynamics and in Blocks, that the panel title is
the goal and that exactly one node is ringed (`stock:backlog`, `sum:short-backlog`), that `desk` is opened in the
boxed case, and that the Suggestions name does the same. On /loops it checks that every row's first cell is a button,
then focuses it, presses Enter and checks the panel title. Five breaks, each seen to fail it: no `choose`; the box not
opened (boxed case fails); the Needs-attention name plain; the Suggestion name plain; the /loops name plain.

Run: the new test (2 passed); test_charts_draw_beside_the_model_with_one_cursor_and_in_a_snapshot,
test_a_selection_is_model_parts_and_survives_switching_view and
test_a_loop_lit_from_its_marker_lets_go_the_way_everything_else_does (3 passed); tests/test_page_polling.py (17
passed); ruff clean. Not run: the rest of tests/test_diagram_rendering.py (a serial run is longer than the session's
10-minute command limit, and a background run was refused), tests/test_items_page.py, tests/test_page_refresh.py, the
unit suite. The merge queue runs those. Local `main` merged in: already up to date.
