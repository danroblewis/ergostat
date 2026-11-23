# chart-result-shapes: Each query result has a shape, and the shape decides which charts apply

depends-on: [data-source-model, panel-editor-sidebar-simplified]

Owner's design, 2026-11-23. A dashboard data source is, as in Grafana, a connection, a query language and a typed result. Each panel query is text in its source's language. Visual query builders are not wanted. Metrics hold aggregates over bounded labels; anything with a generated ID stays in the event log. The event log remains the source of truth.

Change. Every result is one of a small set of typed frames: time series; dimensions to measures; points; distribution; two signals (input and output); and a transfer function from a model. Each chart family declares the shapes it takes. Charts that cannot show the current shape are disabled, and the chart dialog shows those that can, rendered on the data. A shape mismatch says how to reshape the data in one sentence. Add a few client-side transforms only where a query language cannot do it: pivot, join by field, group.

Definition of done.
1. A table of every chart family against every shape is tested.
2. Switching among applicable charts never re-asks the data source.
3. A PromQL and a SQL result of the same shape draw the same chart.

## Amendment from the chart catalog

See `docs/research/2026-11-23-charts/catalog.md` section 7.2. Use the five shapes and the result envelope in section 2 of the catalog. "Two signals" is a `series` with `input` and `output` roles. Client-side transforms are for reshaping only.

## Where it stopped

Built, round 1. About 385 net lines outside tests, docs and dev (budget 600; `git diff --stat main` counts 417 added and
33 removed).

- `ergostat/query/frames.py`: every `/api/query` answer gets its `shape` (`series`, `table`, `points`, `distribution`,
  `response`), what a chart checks of it (`roles`, `order`, `form`, `has`, `dims`, `measures`, `rows`) and the envelope
  `meta` (`source`, `query`, `provenance`, `verdict`). It is read off how the engine already builds each answer, in a new
  dict, so a kept answer is never changed.
- `ergostat/datasources/_frames.py`: a data source type may answer with a typed frame (`series` with roles, `table`,
  `points`). Each is checked (types, lengths, unique dims, finite numbers) and bounded (5,000 rows or points, the 50
  series). A bad frame is `error_kind: refused` and one over a bound is `limit`.
- `ergostat/web/static/frames.js`: the check of a family's declared `shapes` against an answer, the one-sentence
  mismatch ("Phase portrait needs ...; this result is ...: FIX."), a table laid out the way each family reads it, and the
  reshaping steps `pivot`, `join`, `group` (text on the panel, `reshape`, one step a line).
- Each family's registration declares `shapes` and `reshape` (panels.js, plots-*.js). Once an answer is in, its shape
  decides: the editor disables what does not fit (the sentence in its tooltip and above the preview), the dialog draws
  only what fits, and a saved panel that does not fit says the sentence instead of drawing.
- The editor's preview asks again only when the queries a chart would send (`askedOf`, its family's `ask` applied)
  differ. Before, any change of chart asked again. A Reshape text field sits under the queries.
- SPEC §4e: *Result shapes*, *Which charts apply*, *Reshaping*.

Choices taken without asking (the most reversible):
- The amendment says section 7.2, but the catalog's amendment for this gap is in §7.3 (§7.2 is the rework bug). I used
  §7.3 and §2. "Five shapes" leaves out `graph`, which is `graph-result-and-panel` (B6).
- Ergostat's own answers map as follows. A query X of another query is two signals (`series`, roles input and output).
  A field X is `points`. A category X is a `table`, and with `agg: none` it is a `distribution` of `samples`. Bins of a
  `count` are a `distribution` of `bins`, and bins of any other aggregate are a `table` over a numeric dimension. `ohlc`
  is a `series` with the four candle roles.
- The verdict is the smallest that holds: `ok`, `warn` (the answer's own note or truncation) or `refuse` (its error, or
  a frequency response without coherence), with `{code, says}` reasons. There is no `fix` and no closed list of codes, and
  the panel does not display it yet. That is `result-frames-and-verdicts` (B3). `meta.sampling` is not here
  (`analysis-source-and-window-guard`).
- The table built differs from catalog §2.5 where nothing on main can draw the cell yet. Each difference is pinned in
  `TAKES` of the test:
  - stat and table take only plain series (catalog: any series);
  - the table family takes no points or distribution;
  - heatmap takes no two-dimension table and no `over_time` distribution (it needs a weighted-cell drawing);
  - survival (a new option of line), Marey and dotted (new options of scatter) and the graph column are not built.
- Some charts that used to draw are now refused, as the catalog's table says: heatmap of a time series or of two
  signals, box of a time series, bar of points, histogram of a binned aggregate other than count, scatter of a plain
  time series. A panel saved that way says what it needs and how to reshape it.
- A data source frame may be a `series`, a `table` or `points`. A `distribution` or `response` from a source is refused
  for now. `prometheus.py` is unchanged: it answers series. There is no SQL type on main (`sql-source-over-item-views`),
  so done 3 uses a SQL type registered by the test, which answers rows made into series as such a type would.
- Reshaping applies to tables only, and a step that cannot apply is the result's error.

Acceptance tests:
- Done 1: `tests/test_result_shapes_page.py::test_every_chart_family_against_every_shape`. It covers 13 families
  against 17 answers of the five shapes and their forms. The answers come from the real engine and the real frame reader,
  except quartiles, survival and over-time, which nothing produces yet. Each cell is checked twice: by the declared table
  (`mismatch`), and drawn in a real panel (state drawn and painted, or empty with the one sentence). Table and stat
  cells are also checked for content (a row per table row). `test_a_mismatch_names_its_fix` checks the wording.
- Done 2: `test_switching_among_applicable_charts_never_asks_again` (a data source text query and an items field
  query). It clicks every enabled chart and uses the dialog, and one request answers all of them.
  `test_the_editors_reshaping_opens_the_charts_it_makes_fit_without_asking_again`.
- Done 3: `tests/test_result_shapes.py::test_a_promql_and_a_sql_answer_of_one_shape_are_the_same_answer` (a stub
  Prometheus and a registered SQL type, through `/api/query`). `test_result_shapes_page.py::test_a_promql_and_a_sql_result_of_one_shape_draw_the_same_chart`
  draws both in every family that applies and compares canvases and text.
- Also: `test_each_of_ergostats_own_answers_is_one_of_five_shapes`, `test_every_answer_carries_its_envelope`, the frame
  refusals and bound, and `test_pivot_join_and_group_reshape_a_table_on_the_page`.

Seen to fail when the code they guard was broken (then restored):
- The editor's preview keyed on the chart again: the done 2 test failed with 7 and 5 requests instead of 1.
- The panel's shape gate removed: the done 1 test failed (a mismatched family crashed drawing).
- The table adapter for stat and table removed: at first the done 1 test still passed. I added the content check, and
  it then failed ("1 rows drawn of 3").
- The SQL path's values reversed: both done 3 tests failed.

Run here, one file at a time or up to three:
- Unit: test_result_shapes, test_data_sources, test_query_engine, test_query_axes, test_query_fixes,
  test_dashboard_layout. All passed.
- Browser, under the watchdog, none skipped: test_result_shapes_page, test_plot_forms, test_panels, test_panel_editor,
  test_dashboard_page, test_data_source_panels, test_dashboards_doc. All passed.
- ruff is clean. `main` has not moved since the clone ("Already up to date").
- Not run here: the whole unit suite and the four browser files (the factory's). No example was touched, so no
  `demo_check`.

### Round 2

The review's one finding, and the only one: the default dashboard's worked heatmap example was a field's rate over time
(`series`), which the heatmap no longer takes, so every default dashboard with a numeric field showed the mismatch
sentence where that example should be.
- `dashboard-examples.js`: the heatmap example is now the scatter example's own query, one numeric field against
  another (`points`), titled "<kind>: <y> against <x>, heatmap". Like the scatter, it is made only when the kind has a
  second numeric field. I kept the heatmap's declared shapes as they were. Making it take a time series again would undo
  the catalog's table, and changing the example is the easier step to reverse.
- `tests/test_dashboard_page.py::test_every_worked_example_is_drawn_through_the_shape_gate`: the default dashboard
  built for a kind with two numeric fields, where every query is answered by the real engine (`api(Live(p), "query")`
  over `tests/test_result_shapes._p`), so each answer carries its real frame. No panel may be refused by shape, and the
  heatmap example must be `drawn`. The file's other tests use a fake answer with no `shape`, which skips the gate. That
  is why the regression passed before.
- Seen to fail when broken: I put the old rate-over-time query back in the heatmap example and the test failed with
  "Heatmap needs points; ...". Then I restored it.
- About 5 net lines of code added (the round total is still within the 600 budget).

Run here, one file at a time, browser files under the watchdog, none skipped: test_dashboard_page (36 passed),
test_result_shapes_page (7), test_dashboards_doc (34), test_panel_editor (34), test_panels (25), and the unit file
test_result_shapes (13). All passed. ruff is clean. `git merge main`: "Already up to date". On the first run of
test_dashboard_page, the three `test_entering_edit_mode_moves_no_panel_content` cases timed out. The cause was my new
test's module constant `SETTLED`, which replaced the file's own constant of that name. I renamed it `ANSWERED` and all 36
then passed. Not run here: the whole unit suite and the four browser files (the factory's).
