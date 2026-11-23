# dashboard-variables: Dashboard variables, including repeated panels by a variable

depends-on: [data-source-model]

Owner's design, 2026-11-23. A dashboard data source is, as in Grafana, a connection, a query language and a typed result. Each panel query is text in its source's language. Visual query builders are not wanted. Metrics hold aggregates over bounded labels; anything with a generated ID stays in the event log. The event log remains the source of truth.

Change. A dashboard has variables, like `$kind`, from a query (`label_values(metric, label)`), a constant or a custom list, single or multi-value, shown at the top and kept in the address. Queries interpolate them safely for each language. Repeated panels (`dashboard-layout-like-grafana`) repeat by a variable.

Definition of done.
1. Changing a variable re-runs only panels that use it.
2. A value containing quotes or regex characters cannot change a query's meaning.
3. A panel repeated by a variable follows its selected values.

## Amendment from the chart catalog

See `docs/research/2026-11-23-charts/catalog.md` section 7.2. Safe interpolation also covers the `analysis` and `model` query languages when they exist.

## Where it stopped

Built, round 1. About 370 net lines of code outside tests and docs (426 added, 56 removed; budget 600).

What was built:
- `ergostat/datasources/_interpolate.py`: the server writes a variable's values into a data source query's text by
  its language's rules.
  - Inside a string literal, a value is escaped for that literal. A raw `` ` `` string refuses a backtick.
  - A PromQL string after `=~` or `!~` takes each value escaped as an RE2 literal, several as `(?:a|b)`. Any other
    string takes exactly one value.
  - Outside a string, a value must be one plain name, number or duration, and not a keyword; anything else is refused.
  - A comment is left as written.
  - `analysis` and `model` (the catalog's call syntax) have the same rules without regex. A language with no rules
    refuses every variable used in it (fail closed).
- `datasources.values` and `prometheus.values`: `label_values(label)` or `label_values(selector, label)`, sent as
  `GET /api/v1/label/NAME/values`. At most 200 values, each at most 200 characters. `values` joins `query` as the only
  operations a type may offer, both read-only.
- `GET /api/query/values?q=` (`ergostat/query/variables.py`), refused to a public reader as any data source query. A
  `{source, text}` query also takes `vars` (bounded: 8 names, 200 values, 200 characters each).
- `dashboard.js`:
  - The draft's `vars` may hold a custom list, a constant or a query, each single or multi. The old bare list still
    reads as a multi-value custom list.
  - Each variable but a constant is a `<select>` at the top. What is chosen is kept in the address as `var-NAME`.
  - Text queries are sent `vars` and are never written into in the browser. Old forms take a variable's one value.
  - A draw asks again only the panels whose asked queries changed. Each panel takes only the answer of the last ask
    it was in, by sequence (`DASH.ver`).
  - A repeat by a variable follows the values chosen.
- SPEC §4e (*Variables*), §11 (the second Prometheus GET and the `values` operation), and the repeat line in
  `docs/proposals/dashboard.md`.

Choices taken without asking (the most reversible):
- Variables are defined in the draft (the link) only. There is no editor form for them, and declared `dashboards:`
  do not take them. "Visual query builders are not wanted", and nothing asked for a form.
- Interpolation is done on the server, where each source's language is known, not in the browser.
- A variable not chosen takes its first value, or every value when it takes several.
- Chained variables: a query variable's text may name earlier variables, and its values are listed again when one
  of them changes.
- The rules for `analysis` and `model` are written for the catalog's call syntax. Those types do not exist yet, so the
  rules must be checked against their parsers when they arrive.

Known limits, said in SPEC:
- In the older query forms, a field with several values chosen is left as `$kind` and matches nothing.
- An empty multi-value choice is not kept in the address: a reload takes the default.
- A very large choice (many long values) can push a request past the 48,000-character `q` bound. Not tested.

Acceptance tests:
- Done 2, `tests/test_dashboard_variables.py`:
  - `test_a_value_with_quotes_or_regex_characters_cannot_change_a_querys_meaning`: 15 hostile values, five
    templates over PromQL, `analysis` and `model`, and three regex forms. What lies outside string literals must be
    unchanged, each literal must read back as the value, and each regex must match exactly the values chosen.
  - Also in that file: the refusals, a language with no rules, the text the stub Prometheus is sent, and
    `label_values` (bounds, a type with no `values`, a reader refused with nothing sent).
- Done 1, `tests/test_dashboard_variables_page.py::test_changing_a_variable_asks_again_only_the_panels_that_use_it`
  (browser).
- Done 3, `tests/test_dashboard_variables_page.py::test_a_panel_repeated_by_a_variable_follows_its_chosen_values`
  (browser).
- `tests/test_dashboard_variables_page.py::test_an_earlier_ask_answering_after_a_variable_changed_does_not_overwrite_the_panel`
  (lesson 2).

Seen to fail when the code they guard was broken:
- No quote escape: 6 failed.
- No regex escape: 16 failed.
- A draw that asks every panel: done 1 failed.
- A repeat over every value offered instead of those chosen: done 3 failed.
- Accepting any ask's answer instead of the last one's: the sequence test failed.

Run here, one file at a time:
- Unit files: test_dashboard_variables (19), test_data_sources, test_query_engine, test_web_lanes and
  test_query_fixes, all passed. One exception: in test_query_engine,
  `test_a_factory_sized_record_answers_each_source_within_100_ms_without_the_log` failed once at 0.111 s against
  its 0.1 s bound, on a built-in `counts` query this change does not reach. It passed when rerun alone (lesson 10:
  load; left alone).
- Browser files under the watchdog: test_dashboard_variables_page (3), test_dashboard_layout (26),
  test_dashboard_page (35), test_data_source_panels and test_panel_editor (37). All passed, rc 0, none skipped.
- ruff is clean.
- Not run here: the whole unit suite and the four browser files (the factory's). No example was touched, so no
  `demo_check`. `main` (a08e4b3e) has not moved since the clone, so there was nothing to merge.
- Refused here: inline `python -c`, heredocs and `sed -i` through the shell. Edits went through the editor, and checks
  went through test files.
