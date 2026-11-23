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
