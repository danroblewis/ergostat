# ui-everything-clickable-in-the-diagram-can-be-reach: Everything clickable in the diagram can be reached and acted on by keyboard

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q74 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram (all views); side panel 'Feedback loops' rows

**The problem:** Open, Into, stocks, flows, blocks and loop markers are SVG groups with no tabindex or role; Tab skips the diagram. The side panel's loop rows are divs. A keyboard or screen-reader user cannot open a system or read a block's definition.

**The change:** Give each system box's Open and Into, each stock, flow, block and loop marker tabindex=0, role=button and an aria-label ('stock api-q0, 13, desired ≤ 20, holding'); Enter and Space do what a click does. Side-panel loop rows become buttons. Opening a panel moves focus to its heading; Escape returns focus to the part.

**User stories it serves:** H5

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
Using only Tab, Enter and Escape on :8791/: focus reaches 'Open' on factory and opens it; reaches a stock and opens its panel with focus on the panel heading; Escape returns focus to that stock. Every element with cursor:pointer in the svg is focusable.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Built, round 1. 59 net lines in `ergostat/web/static`: `keys.js` (48, new, loaded from `index.html`), plus a
`partClick` factored out of `diagram.js`'s pointerup so Enter on a part does exactly what a click does, one call from
`markInteraction` (run after every drawing in every view), the heading focus in `showDetail`, the loop rows made
`button`s (Dynamics' 'Feedback loops' and the Blocks/control 'Loops' list) and one CSS rule for them.

- What is a button: every `.node` (except a cloud that leads nowhere), every `.edge`, every `[data-act]` control but
  the drag-only `hull-grip` (loop markers, measure rows, pins, the open/close/into marks), `.sys-btn` (Open, Into),
  `.sys-hull-label` and the Blocks `.bd-frame`. An allowlist, checked against the computed cursor by the test.
- The aria-label is the part's kind and the text drawn on it, then its status where it has one. The demo copy in
  the test is not run, so its stock reads 'stock backlog, – tickets'; a running model gives the definition's
  'stock api-q0, 13, desired ≤ 20, holding' form only as far as those words are drawn on the stock.
- Choices made alone, the most reversible: the lines (`.edge`) are focusable too, since their hit path has
  cursor:pointer and the acceptance says every such element. In DOM order they come before the parts, so Tab passes the
  lines first. The heading takes the focus only for a panel opened by keyboard (a press of Enter or Space, cleared by any
  pointer press), so a mouse click never moves the focus. A redraw puts the focus back on the part it was on, found by
  a `data-key`.
- Acceptance test: `tests/test_diagram_rendering.py::test_everything_clickable_in_the_diagram_is_reached_and_acted_on_by_keyboard`
  (software-factory served, as the other page tests serve it, not :8791). By Tab and Enter: Open factory, then Open
  intake (factory holds only systems, so it has no stock of its own), then a stock, whose panel opens with focus on its
  h2. Escape gives the focus back to that stock. In Dynamics (open and closed), Blocks and Process, nothing with
  cursor:pointer in the svg lies outside a named `tabindex=0` `role=button`, and the loop rows are buttons. Seen to fail
  under each of these breaks: no heading focus; no focus back on Escape; `.edge` left out of the allowlist; the
  Dynamics rows back to divs; the Blocks rows back to divs.
- Found on the way: existing page tests clicked `get_by_role("button", name="fit")`, a case-insensitive substring match,
  which now also matches diagram buttons such as 'loop B19, model-fits'. They now ask for `name="Fit", exact=True`
  (as one test already did). '+' and 'Times' are made exact for the same reason. Only the tests changed here.
- Run here: the new test; and in batches of three, the 21 other tests of `test_diagram_rendering.py` that click Fit,
  open panels, use Escape, open loop rows or modules, the split, a snapshot and the Process and Blocks views. All
  passed. ruff is clean.
- Not run here: the whole of `test_diagram_rendering.py` (it runs past the session's 10-minute command limit, and a
  background run was refused), the other three browser files, the unit suite. The merge queue must run them. `main`
  has no commits beyond the branch's base.
