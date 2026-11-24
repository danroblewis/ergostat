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

### Round 5

Built. The review had one finding, and it was blocking: when a parent variable changed, a dependent's earlier choice
stayed in `DASH.sel` even though the new listing did not offer it. It is fixed. About 419 net lines of code outside
tests and docs (477 added, 58 removed, measured against main; budget 600).

- `dashboard.js` `dashLoadOptions`: when a variable's newest listing is stored, any chosen value that listing does not
  offer is dropped. If no chosen value is left, the choice is removed and the variable takes its default again (its
  first value, or every value when it takes several). Because the dependent's choice is updated before the variables
  that name it are listed, `$leaf` is listed from the new `$sub`, and its own stale choice is then dropped as well.
  The call reports whether it dropped anything. `dashSetVar` then writes the address again, and so does the first
  load, which puts right an address whose `var-sub` its `var-kind` does not offer.
- Choices taken without asking, the most reversible:
  - When some of the chosen values are still offered, they are kept (a multi-value choice is cut down, not reset).
  - A listing that fails offers nothing, so any choice of that variable is dropped (fail closed, lesson 3).
  - An empty multi-value choice stays empty, as before.
  - A custom list's choice is not checked against its list. The finding concerned listings only.
- New test, `tests/test_dashboard_variables_page.py::test_a_dependent_choice_not_in_its_new_listing_is_let_go_when_its_parent_changes`
  (browser). `$sub` is chosen as `z-2` and `$leaf` as `z-2-2` through the `<select>`s, then `$kind` is set to `b`.
  The test checks that `$sub` and `$leaf` show and take `b-1` and `b-1-1`, that only `b`'s values are offered, that the
  address holds neither old value, and that the panel is asked with `{sub: [b-1], leaf: [b-1-1]}`. A second page is
  then opened with `var-kind=b&var-sub=a-2&var-leaf=a-2-1`. It takes `b-1` and `b-1-1`, its address is put right, and
  no ask ever carries a `sub` from `a`.
- Seen to fail when the code it guards was broken:
  - No dropping in `dashLoadOptions`: the new test failed, because `$leaf` was listed from `z-2` and never from `b-1`.
  - No address rewrite in `dashSetVar`: the new test failed, because the address kept `var-sub=z-2` and
    `var-leaf=z-2-2`.
- SPEC §4e now says that a choice the newest listing does not offer is dropped.

Run here:
- ruff is clean.
- Under the watchdog, one file at a time, all with rc 0 and none skipped:
  - test_dashboard_variables_page: 5 passed.
  - test_dashboard_page: 35 passed.
  - test_dashboard_layout: 26 passed.
- `main` (2f08c24e) is already an ancestor of HEAD, so there was nothing new to merge.
- Not run: the whole unit suite and the four browser files (the factory's job). No Python or example was touched.

Refused here: the watchdog command with `; echo rc=$?` appended. It was run again without that.

### Round 6

The only finding was the conflicts with main (278f54a4) in `docs/SPEC.md` and `ergostat/datasources/__init__.py`. They
are answered by the merge at a9a9a9bc. Main had added result shapes: a type may answer with a typed frame
(`_frames.py`). Each conflict keeps both sides:
- `datasources/__init__.py`: only the module docstring conflicted. It now says a type answers with series or a typed
  frame (main), and that it may offer `suggest` and `values`, the only three operations (branch). The code merged
  cleanly: `query()` writes the variables in through `_text()` and then reads a typed frame as main does.
- SPEC §4e: the branch's *Variables* paragraph and main's *Result shapes*, *Which charts apply* and *Reshaping*
  paragraphs are all kept, in that order.

No code changed beyond the merge. The size is 418 net lines outside tests, docs and dev (477 added, 59 removed,
measured against main; budget 600).

Run here, after the merge:
- ruff is clean.
- Unit files: test_dashboard_variables, test_data_sources and test_query_engine (89 passed), test_result_shapes and
  test_promql_suggest (22 passed).
- Under the watchdog, all with rc 0 and none skipped: test_dashboard_variables_page and test_result_shapes_page
  (12 passed), test_dashboard_page and test_dashboard_layout (62 passed).
- Not run: the whole unit suite and the four browser files (the factory's job).

Refused here: a `grep -rn` over SPEC, ergostat and tests for stale wording and leftover conflict markers. The Grep tool
was used instead, and it found neither.

### Round 7

Built. The review had two findings, and both were blocking. Both are fixed in `dashboard.js`, with 4 lines changed. The
size is 420 net lines outside tests, docs and dev (482 added, 62 removed in `ergostat` and `scripts`, measured against
main; budget 600).

- Finding 1 (the 'still waiting' note was skipped on a partial ask, and so on the first draw): fixed. `dashRefresh`
  now calls `dashStill(n, held)` after every ask that answers, whether full or partial. `dashStill` makes notes only
  for the panels that ask held. A panel's note is dropped when the panel has been asked again since
  (`DASH.ver.get(id) !== n`), and the loop goes on to the next panel. Before, the whole loop stopped when any newer ask
  began (`n !== DASH.asked`), and a variable's partial ask counts as a newer ask. Main's dashboard did not need this
  guard because it never made a partial ask.
- Finding 2 (the leave-scoped guard was gone): fixed. `dashLeave` now clears `DASH.ver`. An ask still out when the page
  is left then holds no panel. Its answer, its failure, its 'late' note and its retry are all dropped, on a route to
  another Dashboard and on a route to another page alike. A new page's asks take new sequence numbers, so they are
  never mistaken for the old one. A check on `DASH.page` was tried as well, but it was not kept: with `DASH.ver`
  cleared, no test could fail without it.
- New tests in `tests/test_dashboard_variables_page.py` (browser):
  - `test_the_first_draw_says_who_is_still_waiting_with_the_poll_off`: the poll is Off (`DASH.timer` is null), the note
    must come within 5 s, and only one ask may be made.
  - `test_leaving_the_dashboard_mid_ask_schedules_nothing_and_says_nothing`: `/api/query` is never answered and the
    poll is Off. The test routes to a Dashboard with other panels, then to `/items`. No 10 s retry timer may be set, and
    the new page must not say 'asking again' or 'did not answer'.
- Seen to fail when the code they guard was broken:
  - `if (!only)` put back before `dashStill`: the first test timed out at 5 s.
  - `DASH.ver.clear()` removed: the second test failed. The new Dashboard's header read "No answer; asking again", and
    with that check skipped, a retry was set on `/items`. At first the test routed to the same Dashboard with the
    default poll, and so it could not fail. The new page re-asked the same panel ids, and the poll's timer hid the
    retry. The test was then changed to route to other panels with the poll Off.
- SPEC §4e now says that the note comes with the ask, the first draw's included, and that leaving the page drops any
  ask still out.
- Choice taken without asking: the note is kept to the panels the ask held. A panel asked again since gets its note
  from the newer ask.

Run here:
- ruff is clean.
- Under the watchdog, one file at a time, all with rc 0 and none skipped:
  - test_dashboard_variables_page: 7 passed.
  - test_dashboard_page: 36 passed. Its `still_waiting` test no longer waits for a 30 s poll.
  - test_dashboard_layout: 26 passed.
- `main` (278f54a4) is already an ancestor of HEAD, so there was nothing new to merge.
- Not run: the whole unit suite and the four browser files (the factory's job). No Python or example was touched.

Refused here:
- A no-op heredoc (`cat > /tmp/edit.txt <<'EOF' ... EOF`), sent by mistake. Nothing depended on it.
- `git diff --numstat main...HEAD -- . ':!tests' ':!docs' ':!dev' | awk ...; git diff --numstat -- ergostat`. It was
  replaced by `git diff --shortstat main -- ergostat scripts`.

### Round 8

Built. The review had one finding, and it was blocking. A query variable at its listing's maximum (200 values of 200
characters, all chosen by default) pushed `q` past `MOST_ENCODED` (48,000). Then the server refused the whole request,
so every panel failed and the page asked again every 10 s with no end. It is fixed in `panels.js`. The size is 426 net
lines outside tests, docs and dev (501 added, 75 removed in `ergostat` and `scripts`, measured against main; budget
600).

- `batched()` now splits a request by length as well as by count. Each request holds at most `MOST_SENT` = 35,000
  bytes of JSON (UTF-8, measured as sent). The 48,000 characters of base64 hold 36,000 bytes, and the rest leaves room
  for the window. A query still goes in the same request as the one it reads its X from.
- A query that is longer than `MOST_SENT` alone, counting what it reads from, is never sent. Its result is an error made
  in the page: "not asked: ... this query is N bytes, more than the 35000 one ask may carry. Choose fewer values". It is
  a result of that one query, not a failed ask, so no retry is made for it and the other panels answer. When every query
  is too long, nothing is sent and `meta` is null, as for a page with nothing to ask.
- Choice taken without asking, the most reversible: the bounds stay as they are on both sides, and the page keeps to the
  server's `q` bound. The protocol is unchanged. Sending each variable's values once per request was not chosen. It
  would change the server's request shape, and one variable at the maximum (about 41,000 bytes) would still not fit in
  one request. The server's listing bound (200 × 200) was not lowered either, since eight variables could still add up
  past the bound.
- Round 1's record says two limits are "said in SPEC": the 48,000 bound and an empty multi-value choice not kept in the
  address. Neither was in SPEC. SPEC §4e now says both: asks split by length, a query too long alone not sent and saying
  so, and an empty multi-value choice not kept. The first of these replaces round 1's "Not tested" limit.
- New tests in `tests/test_dashboard_variables_page.py` (browser). Their stub `/api/query` refuses `q` through the
  server's own `ergostat.query.parse.decode`, so it holds to the real bound:
  - `test_a_variable_at_its_listing_maximum_leaves_the_panels_not_using_it_answered`: a 200 × 200 listing, all chosen.
    No ask is refused. Only the two panels without the variable are sent, and both answer. The panel using the variable
    says "not asked ... Choose fewer values", and no 10 s retry is set.
  - `test_many_panels_using_a_long_variable_are_asked_in_asks_each_within_the_bound`: 12 panels use a 100 × 100
    variable and one uses none. They take several asks, each `q` is at most 48,000, none is refused, and all 13
    answer.
- Seen to fail when the code they guard was broken:
  - No length bound (`MOST_SENT = Infinity`): both tests failed. The asks were refused whole, and no panel answered.
  - Split by length, but a query too long alone still sent: the first test failed, because its ask was refused. The
    second passed, as expected: it has no query too long alone.
- Known limit, not changed (outside the finding): a chained listing whose parent's chosen values are too long for the
  `/api/query/values` `q` is refused by the server. It then offers nothing, as a failed listing does. Not tested.

Run here:
- ruff is clean.
- Under the watchdog, all with rc 0 and none skipped:
  - test_dashboard_variables_page: 9 passed.
  - test_dashboard_page and test_dashboard_layout: 62 passed.
  - test_data_source_panels and test_panel_editor: 37 passed. They also use `queryPanels`.
- `main` (278f54a4) is already an ancestor of HEAD, so there was nothing new to merge.
- Not run: the whole unit suite and the four browser files (the factory's job). No Python or example was touched.

Refused here: nothing.

## Where it stopped

Parked by the factory (merge-queue, 2026-11-23 16:12).

Failed its gates 8 times (the kill rule); the last, in the merge queue: conflicts with main: docs/SPEC.md ergostat/datasources/__init__.py ergostat/query/engine.py

### Continued, round 1

The park's only cause was the conflicts with main (b9341591). They are answered by the merge at ba6a1b85. Main had
added the `sql` source, which reads the project's own items through `ASKING`, so `datasources.query` takes the project
asking (`project=`). Each conflict keeps both sides:
- `datasources/__init__.py`: the branch's `_source`, `_text` and `values` are kept. `query` takes both the branch's
  `given` (the variables) and main's `project`, and sets `ASKING` around the type's call as main does.
- `query/engine.py`: `_from_source` passes both `q.given` and `project=p`.
- SPEC §4e: the branch's *Variables* paragraph and main's *The SQL source* paragraph are both kept, in that order.
- `sql` has no interpolation rules, so a variable used in a SQL query is refused (fail closed), as SPEC already says
  of a language with no rules. Adding SQL rules is not in this gap's definition.

No code changed beyond the merge. The size is 428 net lines outside tests, docs and dev (503 added, 75 removed in
`ergostat` and `scripts`, measured against main; budget 600).

Run here, after the merge:
- ruff is clean.
- Unit files: test_dashboard_variables, test_data_sources and test_query_engine (89 passed); test_sql_source,
  test_result_shapes and test_promql_suggest (31 passed).
- Under the watchdog, all with rc 0 and none skipped: test_dashboard_variables_page and test_sql_editor (11 passed);
  test_dashboard_page, test_dashboard_layout and test_data_source_panels (78 passed).
- Not run: the whole unit suite and the four browser files (the factory's job).

Refused here: nothing.

### Continued, round 2

The only finding was the conflicts with main (e8669794) in `docs/SPEC.md`, `ergostat/datasources/__init__.py`,
`ergostat/query/engine.py` and `ergostat/web/static/dashboard.js`. They are answered by the merge at e743f9e3. Main had
added the `model` source, which is the project's own model, with a `public` flag so that a reader under `open: read` may
ask it. It had also added a first draw that asks the panels above the fold first (`dashFirst`). Each conflict keeps both
sides:
- `datasources/__init__.py`: main's `own()` is kept. The branch's `_source` now finds a source through main's
  `_sources` (so the undeclared `model` source is found), and `query` takes both `given` and main's `public`.
- `query/engine.py`: `_from_source` passes `q.given`, `project=p` and `public=public`.
- `dashboard.js` `dashRefresh`: main's fold-first split is applied to the panels this ask holds (all of them, or only
  those a variable changed). Each of the two answers is kept only for the panels whose newest ask this still is
  (`DASH.ver`), as before. The rest are not asked once no panel is held.
- SPEC §4e: the branch's *Variables* paragraph is followed by main's *The model as a data source*. The reader sentence
  is main's (`datasources` lists only `model` to a reader). §11 names both the `label_values` GET and the `model` type.

After the merge, one change beyond it, in the same rule this gap owns. Round 1 wrote rules for `model` in the
catalog's call syntax and said they "must be checked against their parsers when they arrive". Main's `model` parser
(`datasources/model.py`) arrived in this merge, and the check failed: its one line of words has no strings, since a
quote is part of a word. So under the call rules, `goal "$g"` would have let a value like `x dt=1s` add a word.
- `_interpolate.py`: `model` has its own rules (`MODEL`): no quotes and no comment. A value is always placed bare, so it
  must be one plain name, number or duration, one word, or the query is refused. `analysis` keeps the call rules.
- New test, `tests/test_dashboard_variables.py::test_a_model_query_takes_a_value_only_as_one_word_its_parser_reads_as_written`.
  It tries 19 hostile values (the 15 HOSTILE ones and 4 that try to add a word), in five templates, quoted and not, and
  each must be refused. Three plain values must come out as written, and `model._parsed` must read them as the expected
  form, goal and numbers. The done-2 test's former `model` template is now run as `analysis`, the language of its syntax.
- Seen to fail: with `model` on the call rules again, the new test failed 19 times.
- `test_dashboard_variables_page.py::test_the_first_draw_says_who_is_still_waiting_with_the_poll_off` counted HTTP
  requests (`window.__queries == 1`). Main's first draw sends two, the above-the-fold panels and then the rest. It now
  checks one ask (`DASH.asked == 1`) and at most two requests. That is what it meant: one draw, with no poll.
- SPEC §4e says the `model` rule, and that `sql` has none.
- Choice taken without asking: a goal name in a `model` variable must be a plain identifier (letters, digits, `_`). A
  name with other characters is refused (fail closed).

The size is 434 net lines outside tests, docs and dev (517 added, 83 removed in `ergostat` and `scripts`, measured
against main; budget 600).

Run here, after the merge:
- ruff is clean.
- Unit files: test_dashboard_variables, test_data_sources and test_query_engine (108 passed); test_model_data_source,
  test_sql_source and test_result_shapes (58 passed).
- Under the watchdog, all with rc 0 and none skipped: test_dashboard_variables_page (9 passed, after the change above;
  before it, 1 failed as described); test_dashboard_page, test_dashboard_layout and test_data_source_panels (79
  passed). test_dashboard_first_load passed in the same run as the first.
- Not run: the whole unit suite and the four browser files (the factory's job).

Refused here: a Write of a scratch file to `/tmp` (the file tools are kept to `/work`). It was never needed.
