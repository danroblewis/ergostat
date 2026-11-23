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

### Round 2

Built. The review's two findings were both blocking, and both are answered. About 405 net lines of code outside tests
and docs (round 1's 370, plus 35 more; budget 600).

- Finding 1 (`_interpolate.py`: `label_replace`'s regex and replacement): fixed. While it reads PromQL, the lexer now
  keeps track of each open `(`, `{` and `[` outside a string, with the function name before a `(` and how many commas
  have passed at that level. In `label_replace`, the 5th argument (the regex) is escaped as RE2 like a string after
  `=~`, and several values become `(?:a|b)`. The 3rd argument (the replacement) takes one value, with each `$` written
  as `$$`, so a value cannot name a capture group. `label_join` does not expand `$`, so it keeps the plain rule, and a
  test pins that. No other PromQL function takes a regular expression or expands `$`. SPEC §4e and the module
  docstring now say this.
- Finding 2 (the test could not fail): fixed. `expand()` in the test copies Go's `regexp.Expand` (`$$`, `$name`,
  `${name}`, an unknown group gives empty text, a stray `$` stays as it is). It runs on the replacement literal before
  the literal is compared with the value, so the hostile `$other` now has to come back as `$other`. The regex
  templates now include `label_replace`'s 5th argument three ways: plain, after a nested `sum by (a, b) (up)`, and
  after a selector with a comma (`up{c='1', e="2"}`). Each regex must match exactly the values chosen. The refusal
  test also checks that several values in the replacement are refused, and it pins one exact rewritten text.
- Seen to fail when the code they guard was broken:
  - No `$$` in the replacement: 2 failed.
  - The regex argument treated as a plain string (the round-1 behaviour): 16 failed.
  - Only `(` tracked, so a comma inside `{}` was counted as one of label_replace's: 15 failed. At first this break
    went unseen, because the commas sat inside an inner `rate(`. The template was then changed so that it fails.
- Choice taken without asking: a function name is matched without regard to case, so in doubt a value gets more
  escaping, not less.
- Run here:
  - Unit files, one at a time: test_dashboard_variables (19), test_data_sources (18) and test_query_engine (52), all
    passed.
  - Under the watchdog: test_dashboard_variables_page (3) passed, rc 0, none skipped.
  - ruff is clean.
  - `main` is already an ancestor of HEAD (merged at 8b336442), so there was nothing new to merge.
  - Not run: the whole unit suite and the four browser files (the factory's job). No JS or example was touched.
- Refused here:
  - A `grep`/`sed` chain over SPEC and the record. The Grep and Read tools were used instead.
  - `git -C /work log --oneline -1 main; git -C /work merge-base --is-ancestor main HEAD && echo merged`. It was
    run again without `-C` and without the `log`.
  - The watchdog command piped to `tail` with `echo rc=$?`. It was run again without the pipe.

### Round 3

The only finding was the conflicts with main (2f08c24e). It is answered by the merge at ce254dc0. Main had added
`suggest`, the names a PromQL editor completes, as a second operation a type may offer. The branch had added `values`.
Each conflict keeps both:
- `datasources/__init__.py`: `OFFERED` is `query`, `suggest` and `values`. The docstring and the refusal's words name
  all three. The branch's bounds and main's suggestion bounds both stay.
- `prometheus.py`: main's `_ask(src, path, params, seconds, most)` does the one bounded GET. The branch's `_get` takes
  `path` again (default `query_range`), so `values` still asks `/api/v1/label/NAME/values` through it.
- `web/server.py`: `/api/query/values` and main's `/api/query/suggest` both route.
- `tests/test_data_sources.py`: every type offers only `query`, `suggest` and `values`.
- SPEC §11: the paragraph names both the editor's metadata GETs and the variable's `label_values` GET, and all three
  operations.

No code changed beyond the merge, so the size stays at round 2's figure (about 405 net lines, budget 600).

Run here, after the merge:
- ruff is clean.
- Unit files, one at a time: test_data_sources (18), test_promql_suggest (9), test_dashboard_variables (19) and
  test_query_engine (52). All passed.
- Under the watchdog: test_dashboard_variables_page and test_promql_editor, 10 passed, rc 0, none skipped.
- Not run: the whole unit suite and the four browser files (the factory's job).

Refused here: a no-op heredoc (`cat > /tmp/fix_prom.py <<'EOF' ... EOF`), sent by mistake. Nothing depended on it.

### Round 4

Built. The review had one finding, and it was blocking: in `dashLoadOptions`, a chained variable's listing was stored
in the order the answers came (lesson 2). It is fixed. About 406 net lines of code outside tests and docs (464 added,
58 removed, measured against main; budget 600).

- `dashboard.js` `dashLoadOptions`: each listing is numbered from one counter that is never reset (`DASH.listed`,
  so no number is reused across pages, lesson 5). `DASH.listVer` holds the newest number for each variable. When an
  answer comes, it is stored only if its number is still that variable's newest. Otherwise it is dropped, and the
  later call that asked the newer listing stores that one.
- Choice taken without asking, the most reversible: a variable listed again now lists again the variables that name
  it in turn (`$kind` → `$sub` → `$leaf`). Before, only the variables that named the changed one directly were listed
  again. The record's "Chained variables" choice says a variable is listed again "when one of them changes", and a
  new listing can change a parent's default value. A stale listing does not carry the change down: the newer call
  does that.
- New test, `tests/test_dashboard_variables_page.py::test_a_chained_variable_keeps_its_newest_listing_when_an_earlier_one_answers_later`
  (browser). `$kind` is set to `a`, then to `b`, and the two listings of `$sub` are answered in reverse order. The
  test checks that `$sub` keeps `b`'s values, both stored and shown. It checks that `$leaf` is listed from `b-1`, and
  that the panel is asked with `b`'s values and never with `a-1`.
- Seen to fail when the code it guards was broken:
  - The sequence check removed: the new test failed, because `$sub` took `a`'s listing.
  - The change carried only to direct dependents: the new test failed, because `$leaf` kept `z-1`'s listing.
- SPEC §4e now describes chaining, the numbering, and the newest listing kept.

Run here:
- ruff is clean.
- Under the watchdog, one file at a time, all with rc 0 and none skipped:
  - test_dashboard_variables_page: 4 passed.
  - test_dashboard_page: 35 passed.
  - test_dashboard_layout: 26 passed.
- `main` (2f08c24e) is already an ancestor of HEAD, so there was nothing new to merge.
- Not run: the whole unit suite and the four browser files (the factory's job). No Python or example was touched.

Refused here: `for f in tests/test_dashboard_page.py tests/test_dashboard_layout.py; do uv run python
scripts/suite_watch.py -- ... $f 2>&1 | tail -2; done`. Each file was then run as its own command, with no pipe.
