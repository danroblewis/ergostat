# result-frames-and-verdicts: The six shapes, the envelope, roles on fields, the tested family-by-shape table, verdict display in the panel

depends-on: [data-source-model, chart-result-shapes, panel-editor-sidebar-simplified]

From the chart catalog, `docs/research/2026-11-23-charts/catalog.md`: read section 7 for this item, and the sections it cites (result shapes in section 2, guardrails in section 6, workflows in section 5, and the source reports beside it).

The owner's decisions (2026-11-23): data sources are like Grafana's, each with its own text language; PromQL is primary and read-only SQL is only for what PromQL cannot do; metrics hold aggregates over bounded labels and anything with a generated ID stays in the event log; stocks are gauges, flows are counters, delays are histograms; no visual query builder; result shapes decide which charts apply. VictoriaMetrics is the default metrics store for new installs. Rework means an item repeated a step. The new diagram kinds named in the catalog are allowed (update `docs/proposals/diagram-options.md`), limited to those named kinds. The service map is built from caller and callee labels in metrics first. No new pages: charts are Dashboard panels or live on existing pages, and the Blocks and Dynamics views stay separate and true to their disciplines.

This is item B3.

Delivers: The six shapes, the envelope, roles on fields, the tested family-by-shape table, verdict display in the panel

Unlocks charts: 14, 16 (section 3.2).

Definition of done.
1. Everything this item delivers in the catalog works on a hand-worked record, with its numbers checked by a test.
2. Each guardrail the catalog assigns to this item refuses or warns as stated, with a test that tries the misuse.
3. A chart that cannot be trusted on its data says so, and does not draw as if it could.
4. Decision logic is in pure functions with fast in-memory tests. Anything the catalog marks `[unsure]` is measured or left visibly unsure, never assumed.
5. It works at factory size within the budgets the catalog states, and reads neither the event log per request nor a raw internal table from the page.

## Where it stopped

Built, round 1. About 313 net lines outside tests, docs and dev (budget 600; `git diff --shortstat main` counts 372
added and 59 removed).

What was built:
- `ergostat/query/verdicts.py` (new, pure): the closed list of reason codes, each with its level and its fix. `reason`
  raises on a code not in the list, and `verdict` takes the worst level.
- `ergostat/query/frames.py`: the sixth shape, `graph`. The envelope now holds `verdict` (each reason
  `{code, says, fix}`), `n`, `n_effective` and `sampling`. A refused answer keeps only `id`, `error`, `error_kind`,
  `error_at`, `read_log` and `meta`, so it has nothing to draw.
- `ergostat/datasources/_frames.py`:
  - Roles on series and on a graph's fields are checked against closed lists.
  - A histogram's cumulative buckets become a `distribution` of `bins` with `over_time` (chart 16).
  - A `graph` frame is checked: its kinds, ends, ids, `paths_real`, evidence and confidence, events with `t`, and
    `omitted`. `acyclic` is worked out on the server.
- `ergostat/datasources/prometheus.py`: an answer whose every series has `le` is sent as buckets.
- `ergostat/datasources/_lint.py` (new, pure): G22 read from PromQL text, giving `averaged-percentiles` and
  `quantile-in-bucket`.
- The panel (`panels.js`, `frames.js`, `plots-heat.js`, `plots-frame.js`):
  - A refused answer says "Refused" (when the source refused it), the reason, and "Fix: ...". No family draws it.
  - A warned answer is drawn, with each reason and its fix under the plot. A non-measured provenance says so.
  - The heatmap draws bins over time: a column per time, a row per bucket of equal height labelled by its bounds, and
    a gap where a time has no count.
  - The table family lists a graph's edges.
- The family-by-shape table now has the `graph` column and the bins-over-time row, both tested.
- SPEC §4e: *Result shapes*, *Histograms*, *A graph*, *Verdicts*, *Which charts apply*. `docs/proposals/diagram-options.md`
  has a dated note: the eight kinds are allowed, the shape names them, and none is drawn yet.

The guardrails this item answers for. The catalog assigns none to B3 by ID, so I took these:
- the rules of §2.2 and §2.3: refuse holds no drawable data; an unknown graph kind is refused; edge ends are checked by
  the server; `paths_real` is required with no default; `acyclic` is checked by the server;
- G22, for chart 16 (histogram queries): averaged percentiles warned, a quantile read inside its bucket warned, and
  the bucket bounds shown on the heatmap's rows;
- G38's last sentence, because it is a check on the graph contract: a `wait_for` or `dependency` graph built from
  inferred edges is refused.

The guardrails left to the items that own them: G1 to G4 (B5), G17 (chart 14 draws no label, so it has nothing to
refuse), G19 to G21 (B8, B9), and G35 to G48 (B6 and later).

Choices taken without asking (the most reversible):
- The `graph` shape is the contract and its checks only. A data source may answer with one, and the table family lists
  its edges. Drawing it, the three producers, ELK in a worker and the budgets are `graph-result-and-panel` (B6).
- Prometheus buckets are drawn from 0. Prometheus's `le` counts everything at or below the bound, negative values
  included. A first bound at or below 0 is refused rather than given an invented lower edge. Counts above the highest
  finite bound are not drawn, and the answer warns with how many there are.
- Only `le` is read. VictoriaMetrics's `vmrange` buckets stay plain series, and SPEC says so.
- A count that falls from one bound to a higher one is refused (`not-cumulative`), with a tolerance of 1e-9 relative.
  This is not the `[unsure]` VictoriaMetrics `rate()` question: the check reads only what the store answers, and
  nothing here depends on how `rate()` is computed.
- `n_effective` and three of the four `sampling` fields are `null`, left visibly unknown (done 4): working them out
  needs the window ledger and an autocorrelation estimate (B5). `n` counts the values an answer holds.
- Bands (`lower`, `upper`, `level`) on series are not read here. No chart draws them yet, and a series frame that
  carries them is drawn without them, as before.
- The heading stays "Could not load" when the source could not be reached, and says "Refused" when it refused. The
  panel's `state` stays `error` in both cases, as before, so nothing that reads it changes.
- `stat` and `table` still take plain series only. The table family still takes no points or distributions, the
  heatmap takes no two-dimension table and no graph matrix, and survival, Marey and dotted are not built. These are
  the catalog §2.5 differences already recorded by `chart-result-shapes`, and are pinned in `TAKES`.

Acceptance tests:
- Done 1 (the hand-worked record, worked in the module docstring):
  - `tests/test_result_frames_and_verdicts.py::test_a_histograms_buckets_are_bins_over_time_on_the_hand_worked_record`
  - `::test_a_latency_heatmaps_query_through_prometheus_is_the_hand_worked_distribution` (a stub Prometheus, through
    `/api/query`)
  - `tests/test_result_frames_page.py::test_the_latency_heatmap_draws_the_hand_worked_histogram_with_its_warning`
    (cells `[[2,3,1],[0,4,5],[],[1,0,0]]`, top 5, total 16)
  - `::test_the_bucket_rows_are_labelled_by_their_bounds`
  - `::test_the_phase_portrait_draws_two_signals_and_nothing_refused` (chart 14)
  - `tests/test_result_shapes_page.py::test_every_chart_family_against_every_shape`, now with `graph` and bins over
    time (13 families against 19 answers).
- Done 2, each misuse tried:
  - `test_counts_that_fall_toward_a_higher_bound_are_refused`, `test_buckets_of_more_than_one_histogram_are_refused`,
    `test_buckets_with_no_bound_to_draw_from_are_refused`, `test_averaged_percentiles_and_a_quantile_inside_its_bucket_are_warned`
  - `test_a_graph_that_is_not_what_it_says_is_refused` (13 cases), `test_an_inferred_edge_needs_its_confidence_and_a_service_map_may_hold_one`
  - `test_a_role_on_a_series_or_a_graphs_field_is_from_a_closed_list`, `test_every_reason_is_from_the_closed_list_and_has_its_fix`
  - `test_through_prometheus_a_misused_histogram_is_refused_with_its_fix_and_nothing_to_draw`
- Done 3: `test_a_refused_answer_holds_nothing_to_draw` and `test_result_frames_page.py::test_a_refused_answer_is_drawn_by_no_family_and_says_why_and_the_fix`
  (every family: state `error`, no canvas, "Refused", the reason, and "Fix:"). Also
  `::test_what_is_not_measured_says_so_and_a_graphs_edges_are_a_tables_rows`.
- Done 4: every decision is in pure functions (`verdicts`, `_frames._buckets`, `_frames._graph`, `_lint.warnings`),
  and the unit file runs in about 1.4 s. `test_the_envelope_says_n_and_step_and_leaves_what_it_does_not_know_unknown`.
- Done 5:
  - `test_a_histogram_of_more_buckets_than_series_allowed_is_a_limit` and `test_a_graph_over_its_bound_is_a_limit`.
  - `test_the_bucket_reading_is_quick_at_its_bound` (50 buckets at 1,001 times). Its time was not measured on its own,
    because ad-hoc Python was refused in this session. The whole unit file took 1.4 s, so it takes less. The test's
    5 s bound is loose on purpose.
  - The data source path reads no event log (`read_log: False`), and the page reads only `/api/query`.

Seen to fail when the code they guard was broken (then restored, and `git status` was clean):
- With the refused answer's data kept, `test_a_refused_answer_holds_nothing_to_draw` and the through-Prometheus
  refusal test failed.
- With the cumulative check off, both `test_counts_that_fall...` cases failed.
- With edge ends left unchecked, the `names 'z'` case failed.
- With the `avg` detection off, the G22 test failed.
- With the panel's fix line removed, the page refusal test failed.
- With the heatmap's buckets path off, both heatmap page tests failed.
- With the provenance note off, the not-measured test failed. With the graph's table rows off, it failed again on the
  rows.
- With the "Refused" heading off, the refusal and phase page tests failed.

Run here, one file at a time or up to three, browser files under the watchdog, none skipped:
- Unit, all passed: test_result_frames_and_verdicts with test_result_shapes (48); test_data_sources,
  test_query_engine and test_web_access (96); test_web_lanes, test_dashboards and test_promql_suggest (52).
- Browser, all passed with rc 0: test_result_frames_page with test_result_shapes_page (12); test_plot_forms,
  test_panels and test_data_source_panels (154); test_panel_editor, test_dashboard_page and test_dashboards_doc (104).
- ruff is clean. `git merge main` said "Already up to date".

Not run here:
- the whole unit suite and the four browser files (the factory's);
- `demo_check`, since no example was touched;
- a demo walk with screenshots, since no demo has a Prometheus histogram to draw.

Refused in this session, and worked around only with the tools offered:
- a `python3 - <<'EOF'` edit script (I used the Edit tool instead);
- `uv run python -c ...` to print a grid (I read `query/buckets.py` instead);
- a `uv run python -m pytest ... | cut` and a `named_tests.py ... | cut` (the same run without `cut` was allowed);
- `git checkout -- FILES` to undo the deliberate breaks (I undid them by hand, then checked `git status` was clean).

### Round 2

Built. About 329 net lines outside tests, docs and dev (budget 600; `git diff --shortstat main` counts 388 added and
59 removed there).

The two findings of round 1's review, both blocking, both answered:
- *A bucket query at one bound was read as a histogram* (`prometheus.py`). An answer is now read as buckets only when
  every series has a numeric `le` and they span two bounds or more, with a finite one (`_histogram`). Otherwise it
  stays plain series, as on main, so `rate(x_bucket{le="0.3"}[5m])` by instance draws lines again. A non-numeric or
  NaN `le` also stays plain series (the most reversible choice: main drew those as series). One finite bound with
  `+Inf` is still buckets. Test: `tests/test_result_frames_and_verdicts.py::test_a_bucket_query_at_one_bound_stays_plain_series_and_two_bounds_are_buckets`
  (one bound by two jobs gives two series, `ok`; `0.5` with `+Inf` gives one bin). With the old check put back, it
  failed (`many-histograms`).
- *A heatmap with two bucket answers, or a points answer and then a bucket answer, drew only the first* (`panels.js`).
  When a panel has more than one answer and any of them is buckets over time, it now draws nothing. It is left `empty`
  and says "Heatmap draws one histogram's buckets over time, and this panel has N answers: show one query, or give
  each its own panel." Test: `tests/test_result_frames_page.py::test_a_heatmap_of_buckets_beside_another_answer_says_so_and_draws_nothing`
  (both pairs: state `empty`, no canvas, the sentence; one bucket answer alone is still drawn). With the check
  disabled, it failed (`drawn`, not `empty`).
- SPEC §4e *Histograms* now says both.

Run here, none skipped:
- Unit, all passed: test_result_frames_and_verdicts, test_result_shapes and test_data_sources (67); test_query_engine,
  test_web_access and test_promql_suggest (87).
- Browser, all passed with rc 0: test_result_frames_page with test_result_shapes_page (13); test_plot_forms,
  test_panels and test_data_source_panels (154); test_panel_editor, test_dashboard_page and test_dashboards_doc (104).
- ruff is clean. `git merge main` said "Already up to date".

Not run here: the whole unit suite and the four browser files (the factory's), `demo_check` (no example touched).

Refused in this session: a stray `python3 - <<'EOF'` with an empty body (nothing depended on it).

### Round 3

The only finding was the conflicts with main (fa51005d, the `sql` data source) in `docs/SPEC.md` and
`ergostat/datasources/__init__.py`. Both are resolved, keeping both sides:
- `__init__.py`: main's `ASKING` context around `mod.query`, then the branch's `_lint.warnings` (G22 reads PromQL
  only, so SQL text gets no warnings).
- SPEC §4e: main's *The SQL source* is kept, followed by the branch's *Result shapes*, which says six shapes.

No code changed besides the merge. Outside tests, docs and dev the branch is still 388 lines added and 59 removed.
SQL answers go through the branch's envelope: `tests/test_sql_source.py` passed.

Run here, none skipped:
- Unit: test_result_frames_and_verdicts, test_sql_source and test_data_sources (62) all passed. test_result_shapes,
  test_query_engine and test_web_access (92) had 91 pass and 1 fail (below). test_query_engine, test_web_access and
  test_dashboards (110) had 109 pass and the same 1 fail.
- Browser, all rc 0: test_result_frames_page with test_result_shapes_page (13); test_data_source_panels,
  test_panel_editor and test_panels (62); test_sql_editor, test_plot_forms and test_promql_suggest (137).
- ruff is clean.

`test_query_engine.py::test_a_factory_sized_record_answers_each_source_within_100_ms_without_the_log` failed 4 of 6
runs. Each time it was the `counts` source, at a best of 104 to 109 ms against its 100 ms bound. It passed in round 2.
- I don't think the branch caused it. With the branch's `n`/`sampling` line in `frames.framed` turned off, it passed
  once. With it on, it also passed once. The answer holds about 120 values per series, so that line costs microseconds.
  The two runs were then restored, and `git status` was clean.
- Main also changed this path since the branch's base (`spec/itemindex.py`, +17 lines, in `fde8110a`).
- I could not compare with main on this machine. The commands that would have done it were refused (below). It is
  reported, not fixed (lesson 13), and the bound was left as it is.

Refused in this session: `git worktree add --detach /tmp/mainwt main` (to time the test on main), and
`ps -A -o pcpu=,command= --sort=-pcpu` (to see the load).

### Round 4

The only finding was the conflicts with main in `docs/SPEC.md` and `ergostat/datasources/__init__.py`. Round 3's
merge (097de0eb) had already resolved them. Main has not moved since: it is still fa51005d, which is the merge-base,
`git merge main` says "Already up to date", and no conflict markers are left in the tree. No code changed in this
round. Outside tests, docs and dev the branch is still 388 lines added and 59 removed.

Run here, none skipped:
- Unit, all passed: test_result_frames_and_verdicts, test_sql_source and test_data_sources (62). test_result_shapes,
  test_query_engine and test_web_access (92), including
  `test_a_factory_sized_record_answers_each_source_within_100_ms_without_the_log`, which failed 4 of 6 runs in round 3
  and passed on its single run here. One pass doesn't make it reliable, so round 3's note on it still stands.
- Browser, all rc 0: test_result_frames_page with test_result_shapes_page (13); test_data_source_panels, test_panels
  and test_sql_editor (30).
- ruff is clean.

Not run here: the whole unit suite and the four browser files (the factory's), `demo_check` (no example touched).

### Round 5

The finding is the same as in rounds 3 and 4: conflicts with main in `docs/SPEC.md` and
`ergostat/datasources/__init__.py`. In this clone there are none to resolve:
- local `main` is still fa51005d, which is the merge-base;
- `git merge main` says "Already up to date";
- no conflict markers are left in the tree.

If the queue's main has moved past fa51005d, this clone cannot see that commit, so the conflict can't be reproduced or
resolved here. The branch's whole change to those two files against main is small: in `__init__.py`, the `_lint`
import, `SourceError.code`, and the `warnings` added to the two returns of `query`; in SPEC §4e, the *Result shapes*
paragraph rewritten, and *Histograms*, *A graph*, *Verdicts* and *Which charts apply* added or changed. Whoever merges
a newer main should keep both sides, as round 3 did. The one change in this round is a SPEC line in *Histograms*
rewrapped to the file's width, with no words changed. No code changed. Outside tests, docs and dev, the branch is still
388 lines added and 59 removed.

Run here, none skipped:
- Unit, all passed: test_result_frames_and_verdicts, test_sql_source and test_data_sources (62).
- Browser, rc 0: test_result_frames_page with test_result_shapes_page (13).
- ruff is clean.

Not run here: the whole unit suite and the four browser files (the factory's), and `demo_check` (no example touched).

### Round 6

The finding was the same as before: conflicts with main in `docs/SPEC.md` and `ergostat/datasources/__init__.py`.
Main had moved to b9341591, and the factory's merge 6ef14e49 brought it into the branch before this session. That
merge left no conflict markers in the tree, and `git merge main` says "Already up to date". Against main, the branch's
change to `__init__.py` is still only the `_lint` import, `SourceError.code`, and the `warnings` on the two returns of
`query`. Its change to SPEC §4e is still only the *Result shapes*, *Histograms*, *A graph*, *Verdicts* and *Which
charts apply* paragraphs. Main's new SPEC text, 96 lines elsewhere, is kept whole. In this round I rewrapped one line
of *Histograms* that was over the file's width. No words changed and no code changed.

In that merge main changed `panels.js` by 107 lines, so I ran the page tests again:
- Unit, all passed: test_result_frames_and_verdicts, test_sql_source and test_data_sources (62); test_result_shapes,
  test_query_engine and test_dashboards (98), which includes the 100 ms factory-sized test from round 3.
- Browser, rc 0: test_result_frames_page, test_result_shapes_page and test_dashboard_page (62); test_panels,
  test_data_source_panels and test_dashboard_keep_page (29).
- ruff is clean.

Not run here: the whole unit suite and the four browser files (the factory's), and `demo_check` (no example touched).

### Round 7

The finding was the same as before: conflicts with main in `docs/SPEC.md` and `ergostat/datasources/__init__.py`. In
this clone there are none to resolve. Local `main` is b9341591, which is the merge-base, `git merge main` says "Already
up to date", and no conflict markers are left in the tree. If the queue's main has moved past b9341591, this clone
can't see that commit. Whoever merges it should keep both sides, as round 3 did. The branch's change to the two files
is still the one recorded in round 6.

Round 6 said it rewrapped a line of *Histograms*, but one line there was still over the paragraph's width. In this
round it is rewrapped, with no words changed. No code changed. Outside tests, docs and dev the branch is still 388
lines added and 59 removed.

Run here, none skipped:
- Unit, all passed: test_result_frames_and_verdicts, test_sql_source and test_data_sources (62).
- Browser, rc 0: test_result_frames_page with test_result_shapes_page (13).
- ruff is clean.

Not run here: the whole unit suite and the four browser files (the factory's), and `demo_check` (no example touched).

### Round 8

The finding was the same again: conflicts with main in `docs/SPEC.md` and `ergostat/datasources/__init__.py`. This
clone has none to resolve:
- local `main` is still b9341591, the merge-base;
- `git merge main` says "Already up to date";
- neither file has a conflict marker.

The branch's change to `__init__.py` against main is still 4 hunks: the `_lint` import, `SourceError.code`, and the
`warnings` on the two returns of `query`. If the queue's main has moved past b9341591, that commit can't be seen here,
and this branch waits for a merge of it. Whoever merges should keep both sides, as round 3 did. Nothing changed in
this round apart from this note: no code, and no SPEC rewrap.

Run here, none skipped:
- Unit, all passed: test_result_frames_and_verdicts, test_sql_source and test_data_sources (62).
- Browser, rc 0: test_result_frames_page with test_result_shapes_page (13).
- ruff is clean.

Not run here: the whole unit suite and the four browser files (the factory's), and `demo_check` (no example touched).

### Round 9

The factory merged main (e8669794) into the branch, and it conflicted in three files. I resolved each one in d483a580,
keeping both sides:
- `ergostat/datasources/_frames.py`: main's `response` frame (`_response`, `_pairs`, `_plain`, and its docstring line)
  sits beside the branch's `_buckets` and `_graph`. `answer` takes all six, and its refusal names them all.
- `ergostat/query/engine.py`: a reader's refusal keeps the branch's `error_code: "reader"`, under main's new condition
  (a reader may still ask the model's own source, `datasources.own`). It also passes main's `reader` on to
  `_from_source`.
- SPEC §4e *Result shapes*: the branch's paragraph, with main's `response` frame (poles and zeros as `[re, im]`, and
  `supported: false` carrying no curve) added to the list of typed frames.

The auto-merged `query/frames.py` already gives a `supported: false` response the branch's `no-coherence` reason. No
other code changed. Outside tests, docs and dev the branch is 389 lines added and 59 removed: one more line than
before, because the engine's condition is now split over two lines.

Run here, none skipped:
- Unit, all passed: test_result_frames_and_verdicts, test_sql_source and test_data_sources (62); test_model_data_source,
  test_query_engine and test_result_shapes (102), which include main's response frames; test_web_access,
  test_dashboards and test_web_lanes (69).
- Browser, rc 0: test_result_frames_page, test_result_shapes_page and test_data_source_panels (16).
- ruff is clean.

Not run here: the whole unit suite and the four browser files (the factory's), and `demo_check` (no example touched).

### Round 10

The finding was the same as before: conflicts with main in `docs/SPEC.md` and `ergostat/datasources/__init__.py`.
Round 9's merge (d483a580) resolved them against e8669794, and this clone has nothing left to resolve:
- local `main` is still e8669794, which is the merge-base;
- `git merge main` says "Already up to date";
- no conflict markers are in `docs/SPEC.md` or in any file under `ergostat/`.

Against main, the branch's change to `__init__.py` is still 4 hunks: the `_lint` import, `SourceError.code`, and the
`warnings` on the two returns of `query`. If the queue's main has moved past e8669794, this clone can't see that
commit, and this branch waits for a merge of it. Whoever merges it should keep both sides, as rounds 3 and 9 did.
Nothing changed in this round apart from this note.

Run here, none skipped:
- Unit, all passed: test_result_frames_and_verdicts, test_sql_source and test_data_sources (62); test_model_data_source,
  test_query_engine and test_result_shapes (102).
- Browser, rc 0: test_result_frames_page, test_result_shapes_page and test_data_source_panels (16).
- ruff is clean.

Not run here: the whole unit suite and the four browser files (the factory's), and `demo_check` (no example touched).

### Round 11

The finding was the same again: conflicts with main in `docs/SPEC.md` and `ergostat/datasources/__init__.py`. This
clone has none to resolve:
- local `main` is still e8669794, the merge-base;
- `git merge main` says "Already up to date";
- no conflict markers are in `docs/SPEC.md` or in any file under `ergostat/`.

Against main the two files differ by 55 lines added and 17 removed, the same change rounds 9 and 10 recorded. The
conflict the queue reports must be with a main newer than e8669794, which this clone cannot see. This branch waits for
the factory to merge that main in. Whoever does should keep both sides, as rounds 3 and 9 did. Nothing changed in this
round apart from this note.

Run here, none skipped:
- Unit, all passed: test_result_frames_and_verdicts, test_sql_source and test_data_sources (62).
- Browser, rc 0: test_result_frames_page, test_result_shapes_page and test_data_source_panels (16).
- ruff is clean.

Not run here: the whole unit suite and the four browser files (the factory's), and `demo_check` (no example touched).

### Round 12

The finding was the same again: conflicts with main in `docs/SPEC.md` and `ergostat/datasources/__init__.py`. Main
had moved to b20756c7, and the factory's merge 043d975f brought it into the branch before this session:
- `git merge main` says "Already up to date";
- no conflict markers are anywhere in the tree;
- against main the two files still differ by 55 lines added and 17 removed. That is the change rounds 9 to 11
  recorded, with main's new SPEC text (98 lines, elsewhere) kept whole.

In this round I rewrapped one line of SPEC §4e *Result shapes* that was over the file's width. No words changed and no
code changed. Main's merge also changed `tests/test_result_shapes.py`, so I ran it again.

Run here, none skipped:
- Unit, all passed: test_result_frames_and_verdicts, test_result_shapes and test_data_sources (67); test_sql_source,
  test_query_engine and test_model_data_source (97).
- Browser, rc 0: test_result_frames_page, test_result_shapes_page and test_data_source_panels (16).
- ruff is clean.

Not run here: the whole unit suite and the four browser files (the factory's), and `demo_check` (no example touched).

### Round 13

The one finding, blocking, is answered: *a typed table's `meta.n` was 0* (`query/frames.py`, `_n`). `n` was counted
only from `series`, so a data source's table, every SQL table answer among them, said `n = 0` however many rows it
held. A typed table's `n` now counts its measure cells, and a missing or non-finite cell is not counted. Its dims are
keys, not values, so they are not counted either. An engine-built table still counts its series' values, as before.
The docstring and SPEC §4e say so.

Test: `tests/test_result_frames_and_verdicts.py::test_a_typed_tables_n_counts_its_measure_cells_and_not_its_dims_or_missing_ones`
(three rows of two measures through `_frames.answer`, one cell `None` and one NaN, give `n = 4`). With the table branch
of `_n` turned off, it failed (`assert 0 == 4`). Then the branch was restored.

Outside tests, docs and dev the branch is 392 lines added and 59 removed. `git merge main` says "Already up to date".

Run here, none skipped:
- Unit, all passed: test_result_frames_and_verdicts, test_sql_source and test_result_shapes (59);
  test_result_frames_and_verdicts, test_query_engine and test_data_sources (106).
- Browser, rc 0: test_result_frames_page with test_result_shapes_page (13).
- ruff is clean.

Not run here: the whole unit suite and the four browser files (the factory's), and `demo_check` (no example touched).

## Entry

section: Done recently

- **Result frames and verdicts** (B3 of the chart catalog). This adds the sixth shape, `graph`, checked as a contract
  for the eight named kinds. Every answer's envelope now holds a verdict from a closed list of reasons, each with its
  fix, and also `n` and `sampling`. Roles on fields come from closed lists. The panel shows the verdict: a refused
  answer is never drawn and says why and the fix, and a warned one is drawn with its warning. A Prometheus histogram
  (`_bucket` by `le`) is drawn as a latency heatmap of its buckets, with G22's warnings (chart 16). The phase portrait
  (chart 14) is held to the same verdicts.
