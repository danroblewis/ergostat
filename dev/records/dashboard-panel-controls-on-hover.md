# dashboard-panel-controls-on-hover: edit mode adds no bar; a panel shows grab, edit and delete on hover

Owner, 2026-11-23: clicking Edit shifts every panel's content down and adds a header with "a three-dot thing and a left arrow, right arrow, minus, plus, arrows, vertical arrows, the word Edit, and an x". "These should not be visible all the time, they should only be visible when the cursor hovers over it. Also, only the Edit and x buttons are worth including. ... we just need people to be able to: grab and move, edit, and delete."

Change.
- Entering edit mode moves no panel content by a single pixel.
- A panel's controls are only Edit and delete (x), overlaid in the header's corner on hover or keyboard focus, never over the plot area. The title itself is the drag handle.
- Remove the arrow, plus, minus and vertical-size buttons. Resizing stays on the panel's edges and corner. Keyboard move and resize stay available without visible buttons.
- On touch, where there is no hover, the controls appear once a panel is tapped in edit mode.

Definition of done.
1. A browser test measures every panel's plot position before and after entering edit mode: identical.
2. Controls are hidden until hover or focus, and only Edit and delete exist.
3. Drag, resize, keyboard move and delete still work.
