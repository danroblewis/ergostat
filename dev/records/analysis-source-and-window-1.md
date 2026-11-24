# analysis-source-and-window-1: the `analysis` source and its call language, a raw re-read on one grid with a gap mask, the window ledger and the observable period band

depends-on: [result-frames-and-verdicts]

## Definition of done
1. A panel query `{"source": "analysis", "text": "raw(A)"}` is answered on the server over another query of the same request, named by its id. `analysis` is a reserved source name that never has to be declared under `sources:`. `datasources.listed` offers it, with its language, so the editor can pick it. The call language is small and closed: a call name, positional query ids, then `key=value` options. This gap ships only `raw`. `pair`, `psd`, `spectrogram` and `ccf` are the next sub-gap. An unknown call, an unknown option, a reference to a missing id, a reference to itself or to another analysis query, or text that does not parse is refused, with words and (for a parse error) the column. The request's other queries still answer.
2. `raw(A)`, where A is an ergostat `series` query, reads A's readings at their own spacing, never its roll-ups. It answers a `series` on one uniform grid whose step is the readings' median spacing, coarsened only to stay within a hard maximum of points. A hole longer than `frequency.GAP_SAMPLES` spacings stays empty, never filled, and is listed as `[from, to]` in the answer's gap mask. Where only roll-ups cover the window, the answer is refused: the roll-ups are not offered as raw. Where A is a source query (PromQL), it is asked again at the finest step the point bound allows. Its range windows are still in force, and the verdict says so; the claim is never that it is raw.
3. Every answer, analysis or not, carries `meta.sampling = {scrape_s, step_s, range_windows_s, observable_period_s: [lo, hi]}`:
   - `range_windows_s` comes from every `[d]` and `[d:r]` in a PromQL text.
   - `scrape_s` is the readings' spacing where they are read, and null where it is unknown.
   - `lo = 2 × max(scrape, step)` (G2) and `hi = window / 2`.
   - An unknown scrape interval never counts as fine: `lo` falls back to the step and the verdict warns that the scrape interval is not known.
   - Each period `W/k` of a range window that falls inside the band is listed as a null (G1).
4. A request whose answers differ in step or range windows warns on each of them, naming every window (G4). G3 (windows the controller consumes) needs loop roles and is left to `loop-roles-and-loop-panels`. The record says so.
5. The SPEC §4e data-source text, and the gap's `## Entry` in `dev/records/analysis-source-and-window-1.md`, describe exactly this.

## Relation to other work
- result-frames-and-verdicts: waits for it. The verdict codes and the envelope's `meta` come from it, and `meta.sampling` is added to that envelope.
- model-data-source: avoids its files (its `model` type lives in `ergostat/datasources/`). Both touch `datasources.listed`, so whichever merges second resolves that.
- loop-roles-and-loop-panels, item-spans-and-censored-delays, model-trust-panels: they build on this through the parent gap. Nothing here touches their files.
- retire-old-query-forms: avoids it. The ergostat `series` query form that `raw` reads stays.

## Files to touch
- `ergostat/query/analysis.py` (new): the call language, the references, and `raw` on one grid with its gap mask
- `ergostat/query/sampling.py` (new): the window ledger, the observable band and the mixed-window warning
- `ergostat/query/parse.py`
- `ergostat/query/engine.py`
- `ergostat/query/frames.py`
- `ergostat/datasources/__init__.py`
- `docs/SPEC.md`
- `dev/records/analysis-source-and-window-1.md` (new)
- `tests/test_analysis_source.py` (new)

## Risks
- lesson-3: these must refuse or warn, never pass silently:
  - raw readings that are missing, read as the roll-ups instead;
  - an unknown scrape interval, read as zero;
  - a referenced answer that failed, read as an empty series.
- lesson-4: there must be a hard maximum on the readings read and the points answered, and on analysis queries per request, enforced again at run time.
- lesson-9: the raw test must use roll-ups whose values differ from the readings, so that reading the roll-ups fails it.

## Acceptance tests
- `tests/test_analysis_source.py::test_raw_reads_readings_not_rollups`: readings 10 s apart under 600 s roll-ups with different values. `raw(A)` has a step of 10 s, the readings' values, and `scrape_s` 10.
- `tests/test_analysis_source.py::test_raw_masks_a_gap`: a 5-minute hole stays empty and is listed in the gap mask. A single missed reading does not make a gap.
- `tests/test_analysis_source.py::test_raw_refuses_when_only_rollups_remain`: once the readings are pruned, the answer is a refusal, not roll-up values.
- `tests/test_analysis_source.py::test_ledger_records_promql_range_windows`: against a fake Prometheus, `rate(x[5m]) + avg_over_time(y[1h:1m])` gives `range_windows_s` [300, 3600] and the step. A plain ergostat query carries `meta.sampling` too.
- `tests/test_analysis_source.py::test_observable_band_and_nulls`: lo is 2 × max(scrape, step) and hi is window/2. The W/k nulls inside the band are listed. An unknown scrape gives a warning and lo from the step.
- `tests/test_analysis_source.py::test_mixed_windows_warn`: two queries with different steps and windows each warn, naming both.
- `tests/test_analysis_source.py::test_bad_calls_refuse_alone`: an unknown call, an unknown id, a self reference, an analysis-of-analysis reference and bad syntax (with its column) are each refused, and a sibling query still answers.
- `tests/test_analysis_source.py::test_bounds_hold`: too many readings are coarsened to at most the ceiling. Analysis queries past the per-request maximum are refused.

## Size budget
240 net lines
size: L (confidence: medium)

## Where it stopped

Built: every item of the definition, with the eight named acceptance tests and one more
(`test_analysis_is_offered_and_reserved`) in `tests/test_analysis_source.py`, all passing.

Choices made alone (the most reversible, each easy to change):
- Four verdict codes added to the closed list in `ergostat/query/verdicts.py`, a file the definition does not name:
  `only-rollups` (refuse), `not-raw`, `scrape-unknown` and `mixed-windows` (warn). The verdicts need them.
- `items`, `moves`, `counts` and `events` record each change at its time and are not sampled. Their `scrape_s` is null
  with no `scrape-unknown` warning: a warning on every item chart would say something false. Sampled answers (an
  ergostat `series`, `raw`, every data source's, and since round 2 every answer built from series readings) do warn
  when the scrape is not known. A `series` reads its scrape from its newest 2,000 raw readings in the window (round 2).
- `nulls_s` holds at most 50 periods, the longest of all windows first. SPEC says so.
- A metrics store with no `_sources` (VictoriaMetrics) refuses `raw`. Its `range` stands roll-ups in for readings, so
  it cannot promise raw.
- A model that declares a source named `analysis` keeps it in its file, but it is not listed and never asked. Refusing
  that name at compile is left to a later change (`spec/compile.py` is not in this gap's files).
- G4 compares every answer of the request. The page sends all panels' queries in one request, so a dashboard with a
  PromQL panel and an item panel warns `mixed-windows` on both. That is what the definition asks. Narrowing the warning
  to one panel's queries needs the page to say which queries are one panel's. It is noted in SPEC.
- G3 (windows the controller consumes) needs loop roles and is left to `loop-roles-and-loop-panels`.

Left for other gaps:
- The page's batching (`panels.js`, `send`) renames query ids to `q0`, `q1`, ... and rewrites X, input and output
  references, but not the ids inside an analysis text. A saved panel's `raw(A)` therefore names an id the request no
  longer holds, and is refused ("no query 'A' in this request"). This is fail-closed, never wrong data. The page side
  belongs with the next sub-gap's panels; no UI was changed here.
- Pinned tests that the definition changes by design were updated: the envelope's `sampling` in
  `tests/test_result_frames_and_verdicts.py` and `tests/test_result_shapes.py`, the `scrape-unknown` (and, for two
  answers of different windows, `mixed-windows`) reasons on PromQL answers, and `datasources` listing `analysis` first in
  `tests/test_data_sources.py`.

Checked by breaking the code: reading the roll-up tier in place of the readings fails
`test_raw_reads_readings_not_rollups`, and filling holes of any length fails `test_raw_masks_a_gap`. Both were seen to
fail, then restored.

Tests run here: `tests/test_analysis_source.py`, `test_result_frames_and_verdicts.py`, `test_result_shapes.py`,
`test_data_sources.py`, `test_query_engine.py`, `test_query_fixes.py`, `test_query_axes.py`,
`test_query_frequency.py`, `test_query_spread.py`, `test_group_progress.py`, `test_dashboards_doc.py` and
`test_promql_suggest.py` all pass. These browser files also pass with Playwright under the watchdog, none skipped:
`test_panel_editor.py`, `test_result_frames_page.py`, `test_result_shapes_page.py`, `test_panels.py`,
`test_dashboard_page.py` and `test_plot_forms.py`. ruff is clean. The whole unit suite and the four browser files were
not run here (the factory runs them).

Round 2, answering every finding of the review:
- gate 1 (the record changed outside "Where it stopped"): round 1 put `## Entry` above this section, inside the text
  the gate compares. It is moved below, so the definition above this heading is again exactly its first commit.
- lesson-3, a shaped answer's scrape: `analysis.scrapes` gives `scrape_s` to every answer whose values come from series
  readings. A plain `series` gets it in `_one`. Candles, an X-paired or binned series, and a frequency response whose
  input or output is a series get it in `_shaped`, from the query, its input, its output and its X query. The value is
  the coarsest scrape of those series, and null (warned `scrape-unknown`) if any one is not known. A model's response
  reads no readings and is left out. `test_shaped_answers_carry_their_scrape` covers candles and a frequency response
  with the scrape known, and candles with the readings pruned (null, warned). A frequency response over pruned readings
  is refused for too few samples, so it has no sampling to check there.
- lesson-4, the scrape's cost: the scrape is now read from a series' newest `SCRAPE_READINGS` (2,000) raw readings in
  the window, not 500,000. With at most 64 queries, each reading a few series, that is a small fixed cost a request.
  `raw` still reads its whole window (at most `READINGS_MOST`, under the 8 analysis queries a request) for its grid.
  The same test pins the bound: with `SCRAPE_READINGS` at 30 and the newest 40 readings 30 s apart after 600 readings
  10 s apart, the `series` answer says 30 and `raw` says 10.
- lesson-8/9, nulls with two windows: each window's `W/k` in the band are collected, at most 50 a window, its longest.
  They are then sorted and cut to 50, so the longest of all windows come first. `test_observable_band_and_nulls` now
  checks windows [3600, 86400] in a band [20, 43200]: the list is the 50 longest of both, starting 43200, 28800.
- Checked by breaking the code, each seen to fail, then restored: with the `_shaped` scrape skipped, the
  shaped-answers test fails. With the old stop-at-50 walk restored, the nulls test fails. With the scrape read from
  `READINGS_MOST`, the bound check fails.
- Tests run in round 2: `test_analysis_source.py` (10 passed), `test_query_axes.py`, `test_query_frequency.py`,
  `test_result_shapes.py`, `test_result_frames_and_verdicts.py`, `test_query_engine.py`, `test_data_sources.py`,
  `test_query_fixes.py`, `test_query_spread.py` and `test_group_progress.py`, all passing. ruff is clean. No page
  changed, so no browser file was run in round 2. The whole unit suite and the four browser files were not run here.

Round 3, the merge of main (72ae37ea), conflicted in SPEC, `datasources/__init__.py`, `engine.py`, `frames.py` and
`tests/test_data_sources.py`. Each was resolved keeping both sides:
- `datasources.listed` lists `analysis` first, then main's sources (the built-in `ergostat` and the undeclared
  `model`). A public reader is offered `analysis` and `model`. `language()` now reads main's `sources()`, so the
  built-in `ergostat` source's PromQL range windows are read too.
- The engine keeps main's reader rule (a public reader may ask the `model` source, no other), and an analysis passes
  the reader on. A reader's `raw(X)` over a source query X they may not ask is refused, and nothing is sent. The
  refusal comes from the failed-reference rule (X itself was refused). Passing the reader on is a second guard, so
  removing it alone does not fail the new check in `test_an_anonymous_public_reader_is_refused_a_source_and_nothing_is_sent`.
- `frames.framed` keeps main's `provenance` from the answer, and the branch's verdict with the sampling reasons.
- Main's `model` source works its answer out from the model and reads no readings. It is left out of sampling like
  items: `scrape_s` null, `range_windows_s` [], and no `scrape-unknown`. Without that, every model response warned,
  and `test_model_data_source.py` failed. The `sql` source, new on main, is a data source like any other: its scrape is
  not known, so it warns. That fails closed. Whether its time-stamped item rows should count as not sampled is left
  for later.
- Tests main pinned that this gap changes by design were updated:
  - the listings in `test_model_data_source.py`, `test_data_sources.py` and `test_analysis_source.py` now hold
    `analysis` and `model`;
  - `test_dashboard_first_load.py` compares the split page load with one request of every query, leaving out the
    `mixed-windows` reason. G4 compares one request's answers, and main's page now asks the panels above the fold
    apart from the rest, so that one warning differs between the two by design. SPEC says so; its round-1 sentence
    that the page sends every panel in one request was no longer true.
- Tests run in round 3: `test_analysis_source.py`, `test_data_sources.py`, `test_model_data_source.py`,
  `test_result_frames_and_verdicts.py`, `test_result_shapes.py`, `test_sql_source.py`, `test_metrics_store_labels.py`
  (5 skipped: they need `ERGOSTAT_TEST_VM_URL`), `test_query_engine.py`, `test_query_fixes.py`, `test_query_axes.py`,
  `test_query_frequency.py`, `test_query_spread.py`, `test_group_progress.py`, `test_dashboard_first_load.py` and
  `test_dashboard_keep.py` all pass. These browser files pass with Playwright under the watchdog, none skipped:
  `test_panel_editor.py`, `test_sql_editor.py`, `test_result_frames_page.py`, `test_result_shapes_page.py`,
  `test_dashboard_page.py` and `test_panels.py`.
- One timing failure was seen: `test_query_engine.py::test_a_factory_sized_record_answers_each_source_within_100_ms_without_the_log`
  took 109 ms for `counts` in a run with two other files. Run alone it passed. A `counts` answer reads no scrape; it
  only gets the ledger, which is a few dict operations. The whole unit suite was not run here.

Round 4, answering the one finding of the review (the gap mask and the fill used different tests):
- `raw` used to list a hole when the two readings were more than `GAP_SAMPLES` spacings apart in seconds, but it
  filled by bucket distance (`frequency._filled`, reach `GAP_SAMPLES * each / step`). A 31 s hole whose readings sat
  1 s into their 10 s buckets was listed and also drawn over. Now there is one rule. `analysis._lines` draws straight
  lines between the readings' buckets except from the bucket where a hole of the mask starts, so a listed hole is never
  filled. Every hole over the threshold is cut, not only the first 200 listed: they are read in full (at most one per
  reading, under `READINGS_MOST`), and the `partial` warning still says that only the first 200 are listed. A shorter
  hole is still a straight line, whatever its width in buckets. One edge stays: when the grid is coarsened past a
  hole's length, the hole's two readings can share a bucket. Nothing is then empty, so nothing is cut.
- New test `test_raw_never_draws_over_a_listed_gap` puts every reading 1 s into its bucket. A 31 s hole is listed and
  its two buckets stay empty. A hole of exactly 30 s is not listed and is a line, also three buckets wide. With the old
  `_filled` call put back, the test fails (`v[101]` was 3.0, not None). It passes once the fix is restored.
- SPEC §4e says the threshold is seconds between the two readings, that holes past the first 200 also stay empty, and
  that the mask and the fill are one rule. The module docstring already said "stays empty".
- Tests run in round 4: `test_analysis_source.py` (11 passed), `test_query_frequency.py` and `test_result_shapes.py`,
  all passing. ruff is clean. No page changed, so no browser file was run. Main is already an ancestor of the branch,
  so there was nothing to merge. The whole unit suite and the four browser files were not run here.

Overrun reason: 373 lines added and 38 removed outside tests, docs and dev against main, 335 net against 240 (round 4 adds 13 net for one rule for the gap mask and its fill). The call language with columns for its refusals, the reference checks (self, missing, analysis, failed), the per-request bound held at parse and again at run time, the readings bound, the four verdict codes and (round 2) the scrape on every answer built from series readings are each asked for, and each costs a few lines. Round 3 adds the merge with main's reader rule and its model source. The rest is docstrings.

Round 5, the merge of main (4557d0d8), conflicted in `engine.py` and `verdicts.py`. Both were resolved keeping both
sides:
- `verdicts.py` holds the branch's four codes and main's three `graph-*` codes.
- `engine.answer` keeps the branch's two passes (analysis queries last, then the mixed-window warning) and main's
  `graph` source (`_graph`) in the first pass. A `graph` answer is a diagram of relations, not sampled: it gets the
  ledger with `scrape_s` null, no range windows and no `scrape-unknown`, like items. `raw(G)` over a graph query is
  refused like any non-series query ("raw reads a series query or a data source's query").
- Tests run in round 5: `test_analysis_source.py`, `test_graph_result_and_panel.py`,
  `test_result_frames_and_verdicts.py`, `test_result_shapes.py`, `test_data_sources.py`, `test_query_engine.py`,
  `test_graph_cli_web.py`, `test_model_data_source.py`, `test_sql_source.py` and `test_query_frequency.py` all pass.
  `test_graph_result_page.py` passes with Playwright under the watchdog, as do 3 of the 4 tests in
  `test_dashboard_first_load.py`.
- One failure is not this branch's: `test_dashboard_first_load.py::test_the_page_sends_what_the_replay_sends` fails at
  index 11. The page now asks `{"source": "graph", "diagram": "process"}`, from main's default dashboard
  (`dashboard-examples.js`), but main's `FIRST` list in that test does not hold it. The branch changes nothing under
  `ergostat/web`, and its one edit to that file is in another test (`test_a_cold_servers_first_dashboard_answer_is_within_budget`,
  which passes). So it is main's test against main's page, and it is left alone (lesson 13).
  The whole unit suite and the four browser files were not run here.

Round 6, the merge of main (d0f95413, dashboard variables), conflicted in `engine.py` only: main passes a source
query's variables (`q.given`) to `datasources.query`, and the branch had named `spec` and `store` there. Both kept.
- Since a PromQL range window may now be a variable (`rate(x[$w])`), the ledger reads `range_windows_s` from the text
  as sent (`_interpolate.interpolate`), not as written; read as written, a variable's window was silently missed
  (lesson 3). It is in the merge commit with the resolution. `test_ledger_records_promql_range_windows` now asks
  `rate(x[$w])` with `w = 10m` and expects [600]; with the text read as written it fails (`[] == [600]`), seen, then
  restored. Main's `[$__interval]`-style built-ins, if any, are read the same way, as their value once written in.
  This adds 2 net lines (the import and the line split) to the overrun stated above.
- Tests run in round 6: `test_analysis_source.py`, `test_dashboard_variables.py`, `test_data_sources.py`,
  `test_result_frames_and_verdicts.py`, `test_result_shapes.py`, `test_query_engine.py`, `test_model_data_source.py`
  and `test_sql_source.py` all pass; `test_dashboard_variables_page.py` passes with Playwright under the watchdog (9,
  none skipped). ruff is clean. The whole unit suite and the four browser files were not run here.

## Entry

section: Done recently

- **The analysis source and the window ledger** (analysis-source-and-window-1). A panel query `{"source": "analysis",
  "text": "raw(A)"}` is answered on the server over query A of the same request. `analysis` is reserved, never declared,
  and listed first among `datasources` with its language, to a public reader too. A reader's analysis of a source they
  may not ask is refused, and nothing is sent. The call language is closed: a call, the query ids, then
  `key=value` options. The only call is `raw`, with one option, `points`. A bad call, option or reference, or text that
  does not parse (with its column), is refused alone. `raw(A)` of an ergostat series reads the readings, never the
  roll-ups, on one grid at their median spacing, coarsened only to stay within the point bound. A hole longer than
  `GAP_SAMPLES` spacings stays empty and is listed in `gaps`. With only roll-ups left it is refused (`only-rollups`).
  `raw` of a data source's query asks it again at the finest step and warns `not-raw`. Every answer carries
  `meta.sampling`: step, scrape (null and warned `scrape-unknown` where not known, on every answer read from series
  readings), PromQL range windows, the observable band `[2 × max(scrape, step), window / 2]` and the nulls `W/k` inside
  it, the longest 50 of all windows (G1, G2). The `model` source's answers, like items, are not sampled. A request whose answers differ in step or range windows warns on each
  (`mixed-windows`, G4). Left: G3 (windows the controller consumes) waits for `loop-roles-and-loop-panels`; `pair`,
  `psd`, `spectrogram` and `ccf` are the next sub-gap; the page's batching does not yet rewrite the ids inside an
  analysis text.
