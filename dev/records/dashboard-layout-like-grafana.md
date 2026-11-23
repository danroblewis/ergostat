# dashboard-layout-like-grafana: a panel stays where it was put; rows and repeated panels organize the rest

Owner, 2026-11-23: "if I place them somewhere I want them to stay there, so if I have a 3x3 grid and remove (1,2) then (2,2) moves up, which I don't want. We want grafana-like rules, where there are some 'repeated panels' that have the auto-add and auto-layout behavior, and there are 'rows' to organize panels and guarantee a horizontal break, and the ability to move things to certain offsets."

Change (in ergostat/web/static/dashboard.js and its layout tests).
- **No upward compaction.** Removing, shrinking or moving a panel never moves another panel. Gaps stay. A panel dragged onto others pushes only the panels it would overlap, downward, and nothing else.
- Panels may be placed at any free grid offset.
- **Rows:** a full-width titled row is a guaranteed horizontal break. Panels belong to the row they sit under. A row can be collapsed and dragged, carrying its panels. Editing a panel inside a row never moves the next row up.
- **Repeated panels:** a panel may repeat by a variable or by a query's label (one panel per value). The copies lay themselves out in the panel's row, and are added and removed as the values change. Only repeated panels auto-lay out.
- Existing drafts keep their positions.

Definition of done.
1. A 3x3 grid with the panel at (1,2) removed: every other panel keeps its exact position.
2. Resizing a panel smaller moves nothing else.
3. A drop that overlaps pushes only what it overlaps, with no overlap afterwards.
4. Rows: collapse, expand, drag with their panels, and a guaranteed break.
5. A panel repeated by a label with 5 values shows 5 panels, and 3 after two values disappear, without moving the panels outside its row.

## Where it stopped

Built, round 1. Net code outside tests and docs: +256 lines (dashboard.js +230, dashboard.css +9, panel-editor.js +17).

Acceptance tests, in tests/test_dashboard_layout.py: done 1 `test_removing_a_panel_from_a_3x3_grid_moves_no_other`;
done 2 `test_resizing_a_panel_smaller_moves_nothing_else`; done 3 `test_a_drop_that_overlaps_pushes_only_what_it_overlaps`
and the engine property test `test_the_engine_never_overlaps_moves_only_what_is_hit_and_only_down` (2,400 random moves and
resizes, half with rows: no overlap, nothing moves but down, each that moved was covered, no panel changes row);
done 4 `test_rows_fold_open_drag_with_their_panels_and_are_a_break`; done 5
`test_a_panel_repeated_by_a_label_follows_its_values_within_its_row`. Also
`test_a_panel_repeated_by_a_variable_asks_once_per_value_and_keeps_its_room`,
`test_crafted_rows_variables_and_repeats_are_bounded`, and in tests/test_panel_editor.py
`test_repeat_is_chosen_from_the_panels_queries_and_saved`. Seen to fail: putting upward compaction back into `arrange`
fails done 1 to 5; dropping the kept lines in `spread` fails the variable test; pushing everything below a dropped panel
fails done 2 and 3. Before the fix it found, the property test failed on two real faults (rows swapping order when
pushed together; a panel carried down a long way leaping the next row).

Run here: those three files (25, 28 and 34 passed), ruff clean, main merged (already up to date). Not run here: the unit
suite and the four browser files (the factory's and the queue's).

Choices made alone, each the easier one to undo:
- Dropping a panel onto one of its own size no longer swaps them: a swap moves a panel the drop did not cover, against
  "pushes only what it overlaps". The toolbar's ← and → and Alt+arrows now move a panel a column or a line (they
  reordered and repacked everything before); the page test for them was changed to match.
- On a phone (one column), dragging a panel to a new place in the order gives the panels, in that order, the places held
  in reading order on the desktop grid, then pushes down any overlap; the old way repacked the whole grid.
- Variables: the dashboard had none. A draft may now hold `vars` (name to values, at most 8 names of 24 values), and a
  panel repeated by one gets `$name` replaced in its queries for each value. There is no control to define a variable
  (the rule against new panels in the UI); the editor's Repeat offers the panel's queries, and keeps a variable repeat
  it is given.
- The lines a repeat has taken are kept while the page is open, not in the draft, so a reload with fewer values closes
  that room; the draft is never written from data.
- Limits: 24 panels per repeat, 64 charts on the page in all, 16 rows.
- A crafted draft's far-down place is kept (bounded at line 2000) rather than raised, since nothing rises now.

Known limits, not in the definition: while a drag is in progress, a repeat's values changing redraws the page and drops
the drag; below a repeat whose copies pushed things down, a drag's drop point is worked out on the draft's own places,
so it can land a few lines from the pointer; rows are moved by keyboard with their ↑ and ↓ buttons, not lifted with
Enter like panels.
