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

## Where it stopped

Built, round 1 (net -33 lines of code: `panel-editor.js`, `panel-editor.css`). Acceptance tests, in
`tests/test_panel_editor.py`: 1 `test_the_sidebar_has_no_note_or_quick_starts_and_the_chart_list_keeps_its_height`,
2 `test_a_chart_that_cannot_show_the_result_is_disabled_with_why_in_its_tooltip`,
3 `test_the_chart_dialog_draws_only_applicable_charts_and_applies_the_one_clicked`,
4 `test_a_chart_error_appears_above_the_preview_once`.

Choices made alone, the most reversible way:
- With no query shown yet there is no result to judge, so every chart stays enabled and choosing one sets its
  queries up as before (phase and Bode from empty still work). Once a query is shown, a chart `formProblem` refuses
  is disabled, with that reason as its tooltip (`title`) and `aria-description`.
- A blocked chart can no longer be clicked to set the queries up for it (it used to be, e.g. Nyquist from two time
  queries). "Set it up" stays, beside the one chart error above the preview, for a panel whose chosen chart cannot
  draw its queries; `test_bode_from_two_queries_uses_them_and_keeps_them_hidden` now goes through it.
- When the chosen chart cannot draw the queries, the preview is drawn empty with no reason of its own, and a query's
  error stays beside its query only (the preview no longer repeats it), so each error is said once.
- The dialog ("Charts of this data…") draws each chart with the answer the preview already has (nothing asked
  again). It leaves out a chart whose required aggregation the queries do not ask for (candlestick's ohlc), and one
  whose own check draws it empty. Picking one closes the dialog and chooses it as clicking its tile would.
- The dialog opens over the editor; Escape closes only the dialog, and Tab stays in it.

Not run here: the break check of lesson 9. Running the new tests against the old editor (overwriting the two
files from `HEAD~1`, then a `git worktree` under /tmp) was refused in this session. By reading the old code: test 1
fails at the Note label, 2 because phase is not disabled, 3 because there is no dialog button, and 4 because the
guide sat in the sidebar. The height check in test 1 is not shown to fail on its own.
