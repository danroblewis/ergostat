# data-source-model: Dashboard panels query named data sources in each source's own language

Owner's design, 2026-11-23. A dashboard data source is, as in Grafana, a connection, a query language and a typed result. Each panel query is text in its source's language. Visual query builders are not wanted. Metrics hold aggregates over bounded labels; anything with a generated ID stays in the event log. The event log remains the source of truth.

Problem. The panel editor's Sources (Metrics, Events, Items per state, Item moves, ...) are hand-made forms over internal stores, not data sources.

Change.
- A data source has a name, a type, its connection, a query language and a read-only `query` that returns a typed result. Types are pluggable, so SQL, Redis, Kafka or a cloud monitoring source can be added later without changing panels.
- Reuse the model's existing `sources:` (type prometheus) rather than a second configuration.
- A panel query is `{source, text}` plus display options. Results use the shapes of `chart-result-shapes`.
- Every query is bounded in time, points and series, read-only, and refused clearly when it exceeds them.
- The first type is Prometheus-compatible, through the server (the browser never holds a source's credentials).
- Old panels keep working until `retire-old-query-forms`.

Definition of done.
1. A panel runs a PromQL range query against a stub Prometheus and draws it.
2. Adding a data source type needs one module and no change to panels (a test adds a fake type).
3. A query over the limits, an unreachable source and a bad query each give a clear error in the panel.
4. No write path to any source exists.

## Where it stopped

Built, round 1. About 270 net lines outside tests and docs (budget 600).

- `ergostat/datasources/__init__.py`: the registry, the bounds and `query`. A type is one module in that package, found
  by its name. It has `TYPE`, `KEYS`, `LANGUAGE` and `query(source, text, window)`, which returns `(name, [(t, v)])` per
  series. A type offering any other public function or class is refused.
  Each query is bounded whatever its type: 4,000 characters of text, 50 series, 1,000 points (+1 for alignment), a
  400-day window, and 10 s or less (the request's remaining time). Each refusal is `error` plus `error_kind`
  (`limit`, `unreachable`, `refused`, `unknown`).
- `ergostat/datasources/prometheus.py`: PromQL as `GET /api/v1/query_range` from the server, capped at 8 MB. Errors never
  carry the source's address.
- `/api/query`: a query with `text` is `{source, text}` (no other key, never an X, input or output). It is answered in
  the existing `{times, step, series}` shape and never cached. `/api/query/fields` lists `datasources` by name, type and
  language only.
- `check` accepts any registered type's keys under `sources:`. They are kept in the new `Source.options`.
- The panel editor offers each data source under Source, with a text field labelled by its language. Nothing is built.
- Old panels are untouched (the old forms are still offered, until `retire-old-query-forms`).
- SPEC §4e (*Data sources*) and §11.

Choices taken without asking (the most reversible):
- `chart-result-shapes` is not on main, so results use the time-series shape every panel already draws.
- A data source named like a built-in source (`items`, `series`, ...) still answers on the server, because `text`
  decides. The editor does not offer it.
- The model's JSON schema lists source types by name. A new type adds its name there too. That is the only change
  besides its module; panels need none.
- The Prometheus sensor path (`spec/engine.prometheus`, instant queries) is left as it was.

Acceptance tests:
- `tests/test_data_source_panels.py` (browser, real server, stub Prometheus):
  `test_a_promql_panel_is_drawn_and_each_failure_says_so_in_its_panel` (done 1 and 3) and
  `test_the_editor_offers_the_source_and_a_text_in_its_language`.
- `tests/test_data_sources.py` (12): `test_a_new_type_is_one_module_and_panels_do_not_change` (done 2),
  `test_over_the_series_bound_unreachable_and_bad_each_say_so` (done 3), and
  `test_a_type_offers_query_and_nothing_else` and `test_prometheus_is_asked_by_get_on_query_range_only` (done 4).

Seen to fail when the code they guard was broken:
- Removing the series bound failed both series tests.
- Removing the offers-only-query check failed its test.
- Removing the editor's text slot failed the editor test.
- The 1,001-point test was written for a bug found here: a 1,000-point request was refused.

Run here, one file at a time:
- Unit files: test_data_sources, test_query_engine, test_query_fixes, test_spec_schema, test_remote,
  test_spec_structure and test_blockdiagram, all passed.
- Browser files under the watchdog: test_data_source_panels, test_panel_editor, test_dashboard_page and
  test_style_tokens, all passed, none skipped.
- ruff is clean.
- Not run here: the whole unit suite and the four browser files (the factory's). No example was touched, so no
  `demo_check`. `main` has not moved since the clone, so there was nothing to merge.

### Round 2

The one finding (blocking): an anonymous public reader (`web: open: read`) could make the server forward any PromQL to
every `prometheus` source. Fixed. About 15 net lines more, so about 285 (budget 600).
- The server's gate already knows who asks. It now passes `reader` (anyone under an `open: read` name) through `api` to
  `ergostat/query`. For a reader, each `{source, text}` query is refused in its own result (`error_kind: refused`,
  "a data source is not asked for anyone under a public name ..."), so the panel says so. Nothing is sent to the
  source. `/api/query/fields` lists `datasources` to them as `[]`. Their other queries are answered as before.
- The owner on this machine, and a Cloudflare Access login under a name with `access:` (an email the owner listed),
  may still ask. This is a choice taken without asking, and the most reversible one: the finding names only the
  anonymous reader.
- SPEC §4d (*open: read*) and §4e (*Data sources*, "Who may ask") say so.
- Test: `tests/test_data_sources.py::test_an_anonymous_public_reader_is_refused_a_source_and_nothing_is_sent`
  (a real server, a public `open: read` name, the stub Prometheus). It checks the refusal, that the stub saw no
  request, the empty `datasources`, and that the owner is still answered. I saw it fail with the gate's flag forced
  to `False`, and again with the empty `datasources` removed.
- `ergostat snapshot` (an owner's CLI that calls `api` itself) is unchanged: it is the owner asking.

Run here, round 2, one file at a time: test_data_sources, test_query_engine, test_web_access, test_query_fixes and
test_numbers all passed. test_data_source_panels passed under the watchdog, with none skipped. ruff is clean. Not
run here: the whole unit suite and the four browser files. `main` has still not moved.
