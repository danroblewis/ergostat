# promql-editor: A PromQL editor with highlighting and autocomplete for metrics, labels and values

depends-on: [data-source-model]

Owner's design, 2026-11-23. A dashboard data source is, as in Grafana, a connection, a query language and a typed result. Each panel query is text in its source's language. Visual query builders are not wanted. Metrics hold aggregates over bounded labels; anything with a generated ID stays in the event log. The event log remains the source of truth.

Change.
- The query box for a Prometheus-compatible source is a code editor with PromQL syntax highlighting and autocomplete for functions, metric names, label names and label values, from the source's metadata APIs through our server.
- The owner's exploration pattern works and is shown as a starting hint: `count by(__name__)({__name__=~".+"})`.
- Run with a shortcut; errors appear at the position the server reports.
- Library code is vendored at a pinned version, with no build step added to the page.

Definition of done.
1. A browser test completes a metric name, a label and a label value against a stub source.
2. A syntax error is marked where it is.
3. Autocomplete stays bounded on a source with 100,000 series.

## Where it stopped

Built, round 1. About 347 net lines outside tests and docs (budget 600): 369 added, 22 removed.

- `ergostat/web/static/promql.js` (new, 190 lines) is the PromQL query box. It is a textarea whose own text is clear,
  over a `<pre>` that draws the same text highlighted: functions and aggregations, keywords, metrics, labels, strings,
  numbers and comments.
  - It completes PromQL's functions and aggregations and the source's names: metric names, a metric's label names
    (in `{...}` and in `by (...)` / `without (...)`) and a label's values (in a quoted matcher, closing the quote).
  - Keys: arrows, Enter or Tab to take a name, Escape to close the list, Ctrl+Space to open it. Ctrl+Enter (or Cmd+Enter)
    asks the preview again at once, even when nothing changed.
  - Its placeholder, and a line under it, is the owner's pattern `count by(__name__)({__name__=~".+"})`.
  - It marks the token at the place the server reports (`error_at`), with the source's words as its title and
    `aria-invalid`. The mark goes as soon as the text is edited.
- `panel-editor.js` picks an editor by the source's language (`window.queryEditors[language]`). It never names PromQL,
  so `test_a_new_type_is_one_module_and_panels_do_not_change` still holds. A language with no editor keeps the plain
  textarea. Moving a query to another source re-asks that source; a change of language builds that language's editor.
- `GET /api/query/suggest?source=&what=metrics|labels|values&prefix=&metric=&label=` answers `{suggestions, more}`
  (`server._suggest` → `datasources.suggest` → the type's optional `suggest`).
  - Bounded whatever the type: 100 names, each starting with the prefix; 3 s; `metric`/`label` must be names; prefix of
    200 characters at most.
  - The `prometheus` type GETs `/api/v1/label/__name__/values`, `/api/v1/labels` and `/api/v1/label/<l>/values`. The
    source narrows with `match[]` (the prefix as an escaped RE2 `=~"p.*"`) and `limit=101`. The answer is read one name
    at a time, to 256 KB at most, so a source that ignores `limit` and `match[]` costs no more.
  - A reader under an `open: read` name is refused, and nothing is sent.
  - The page keeps at most 200 answers. A refusal or a failure is not kept.
- `SourceError` carries `at`. Prometheus's `L:C: parse error` (or `at char N`) is read into it, and a query's result
  then has `error_at: [line, column]`.
- SPEC §4e (*Data sources*, *The query editor*) and §11 say so.

Choices taken without asking (the most reversible):
- No library. This session has no network, so no CodeMirror or Monaco could be fetched and pinned. The editor is
  ergostat's own plain JavaScript in one file, with no build step. The definition's "vendored at a pinned version" is
  met only in that no unpinned or unvendored code is added. A vendored editor can later replace `promql.js` behind the
  same `queryEditors.PromQL(...)` contract (`{el, area, set, mark}`), with no change to the panel editor.
- A data source type may now offer `suggest` beside `query` (`OFFERED`). `test_a_type_offers_query_and_nothing_else`
  now allows `{query, suggest}`. A type with any other public function is still refused.
- The preview still asks as text is typed (the data-source-model behaviour, debounced). Ctrl+Enter asks at once and
  again. Asking only on the shortcut would change what data-source-model's tests rely on.
- Errors are marked where the source said they are. The page does not parse PromQL to find errors itself.
- Suggestions are not limited to a time range, so the source's own default range is used.

Acceptance tests:
- `tests/test_promql_editor.py` (browser, real server, stub Prometheus sources, 6):
  - `test_a_metric_name_a_label_and_a_label_value_are_completed_against_the_source` (done 1; also the highlighting and
    a function).
  - `test_a_syntax_error_is_marked_where_the_source_says_it_is_and_ctrl_enter_runs` (done 2, multi-line, `2:3`).
  - `test_autocomplete_stays_bounded_on_a_source_of_100000_series[big|rude]` (done 3). `big` honours `limit` and
    `match[]`; `rude` ignores both and sends every one of 100,000 names. The list shows 100 and a "More" line.
  - `test_the_owners_exploration_pattern_is_the_starting_hint_and_runs`
  - `test_a_query_moved_to_another_source_completes_from_that_source`
- `tests/test_promql_suggest.py` (unit, 9):
  - `test_autocomplete_stays_bounded_on_a_source_of_100000_series[big|rude]` checks 100 names, `more`, bytes read of
    the source ≤ 256 KB + 1, and the answer under 30 KB.
  - `test_a_parse_error_says_where_the_source_said_it_is`
  - The time bound, the reader refusal, refused names (nothing sent), the escaping of the prefix, and a type that
    answers too many names.

Seen to fail when the code they guard was broken:
- The editor's mark call disabled: the syntax-error test failed (no `.pq-err`).
- `lastSig = null` taken out of the Ctrl+Enter path: the same test failed (no new request).
- The suggestion count slice ×1000 and the `_names` stop ×1000: both bounded tests failed (101 / 23,826 names), and so
  did the fake-type test (10,000).
- The 8 MB byte bound in place of 256 KB: the `rude` unit case failed (1,100,060 bytes read).
- The editor holding the source name it was built with: the moved-source test failed.
- Not seen to fail: the page dropping a failed suggestion from its cache has no test.

Run here, one file at a time:
- Unit: test_promql_suggest (9), test_data_sources (18), test_web_lanes and test_web_access all passed.
- test_query_engine: 51 passed, 1 failed:
  `test_a_factory_sized_record_answers_each_source_within_100_ms_without_the_log` took 0.106 s for a `counts` query.
  It is marked `serial`, a bound that holds only on a quiet machine, and it ran here beside other files. It passed run
  alone. It reads none of the changed code (the one engine change is in the data-source error branch).
- Browser, under the watchdog (rc 0, none skipped): test_promql_editor (6), test_data_source_panels (3),
  test_panel_editor (34) and test_dashboard_page (35).
- ruff is clean.
- Not run here: the whole unit suite and the four browser files (the factory's). No example was touched, so no
  `demo_check`. `main` has not moved since the clone, so there was nothing to merge.
