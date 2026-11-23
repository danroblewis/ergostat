# diagram-roving-focus-and-arrow-keys: The diagram is one tab stop with roving focus; arrow keys follow pipes, connectors and signals

depends-on: []

Problem (R9 piece 4): the diagram is the interface by the owner's decision, and filed Q74 makes its parts focusable. On big that is hundreds of tab stops before the side panel, and Tab order says nothing about structure (shots/a11y-8791-home.png, a11y-8797-stock-click.png). Story H5 failed.
Change: the SVG is one tab stop (roving tabindex: one part has tabindex 0, the rest -1; the last focused part is remembered per view). Arrow keys move along the structure: in Dynamics Right/Left follow the pipe downstream/upstream from a stock or valve, Up/Down step through the connectors into and out of the focused part (announcing the other end and the link's sign); in Blocks Right/Left follow the signal forward/back and Down takes the return path. On a closed box with goal rows, Down enters its rows. Enter opens the part's panel and moves focus into it; Escape returns focus to the part; I goes Into a focused system and Escape (or Backspace) back out; Home goes to the first part of the first chain. A visible focus ring uses the accent token (selection, by the colour rules). Works on the build Q74 lands (same focusable elements).
Definition of done:
1. On :8791 Tab reaches the diagram once and leaves it with the next Tab.
2. From a focused stock, Right moves focus to its outflow valve and again to the next stock, in Dynamics; in Blocks Right from a junction reaches C, then the actuator, then P.
3. Enter opens the panel with focus inside; Escape returns to the same part.
4. I on a system goes Into it and Escape returns with focus on that system.
5. The focus ring has at least 3:1 contrast in both themes.
Files: ergostat/web/static/interact.js, diagram.js, dynamics.js, blocks.js, style.css, tests/test_diagram_rendering.py.
Acceptance tests: keyboard-only browser tests for 1-4 on :8791 in both views.
Budget: 160 net lines.

Milestone: r9-diagram-without-a-mouse. Owner items: R9 piece 4 (pieces 1-3 are filed Q74, Q75, Q77). From the owner's list and the design review of 2026-11-22.
