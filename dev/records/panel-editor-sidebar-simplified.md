# panel-editor-sidebar-simplified: the panel sidebar stops explaining and gets out of the way

Owner, 2026-11-23, on the editor's Panel sidebar.

Change.
- Remove the Note field from the editor (a saved note stays stored).
- Remove the Quick starts list.
- Chart types that cannot show the current result are grayed out and disabled, at their normal height, with the reason only in a tooltip. No added yellow text in the list.
- Errors about the chart appear in one place, beside the query or above the preview, never in the sidebar.
- A button opens a dialog of the applicable chart types, each rendered with the current data, and clicking one chooses it.

Definition of done.
1. The sidebar has no Note or Quick starts, and choosing any chart type does not change the height of the chart type list.
2. A result a chart cannot show disables that chart, with a tooltip saying why.
3. The dialog renders only applicable charts on the current result and applies the one clicked.
4. A chart error appears above the preview, once.
