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

## Entry

section: Done recently

- **The analysis source and the window ledger** (analysis-source-and-window-1). A panel query `{"source": "analysis",
  "text": "raw(A)"}` is answered on the server over query A of the same request. `analysis` is reserved, never declared,
  and listed first among `datasources` with its language. The call language is closed: a call, the query ids, then
  `key=value` options. The only call is `raw`, with one option, `points`. A bad call, option or reference, or text that
  does not parse (with its column), is refused alone. `raw(A)` of an ergostat series reads the readings, never the
  roll-ups, on one grid at their median spacing, coarsened only to stay within the point bound. A hole longer than
  `GAP_SAMPLES` spacings stays empty and is listed in `gaps`. With only roll-ups left it is refused (`only-rollups`).
  `raw` of a data source's query asks it again at the finest step and warns `not-raw`. Every answer carries
  `meta.sampling`: step, scrape (null and warned `scrape-unknown` where not known), PromQL range windows, the observable
  band `[2 × max(scrape, step), window / 2]` and the nulls `W/k` inside it (G1, G2). A request whose answers differ in
  step or range windows warns on each (`mixed-windows`, G4). Left: G3 (windows the controller consumes) waits for
  `loop-roles-and-loop-panels`; `pair`, `psd`, `spectrogram` and `ccf` are the next sub-gap; the page's batching does
  not yet rewrite the ids inside an analysis text.

## Where it stopped

Built: every item of the definition, with the eight named acceptance tests and one more
(`test_analysis_is_offered_and_reserved`) in `tests/test_analysis_source.py`, all passing.

Choices made alone (the most reversible, each easy to change):
- Four verdict codes added to the closed list in `ergostat/query/verdicts.py`, a file the definition does not name:
  `only-rollups` (refuse), `not-raw`, `scrape-unknown` and `mixed-windows` (warn). The verdicts need them.
- `items`, `moves`, `counts` and `events` record each change at its time and are not sampled. Their `scrape_s` is null
  with no `scrape-unknown` warning: a warning on every item chart would say something false. Sampled answers (an
  ergostat `series`, `raw`, every data source's) do warn when the scrape is not known. A plain `series` reads its
  scrape from the raw readings in the window (the newest 500,000).
- `nulls_s` holds at most 50 periods, the longest first. SPEC says so.
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

Overrun reason: 335 lines added and 32 removed outside tests, docs and dev, about 303 net against 240. The call language with columns for its refusals, the reference checks (self, missing, analysis, failed), the per-request bound held at parse and again at run time, the readings bound and the four verdict codes are each asked for, and each costs a few lines. The rest is docstrings.
