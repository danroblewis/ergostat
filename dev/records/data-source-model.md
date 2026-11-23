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

### Round 3

The finding (blocking): eight tests in `tests/test_web_lanes.py` failed in the queue, and failed again with only this
gap applied. The cause was this branch. Round 2 added a `reader=` keyword to `web.server._answer`. That test's `site`
fixture swaps `_answer` for a stub that still has main's signature, `(live, path, q, project=None)`. So every `/api/`
call through the stub raised `TypeError`, and no worker was ever seen taking a request.

Fixed in the code. The test is unchanged.
- `_answer` has main's signature again.
- A new `_query(live, p, parts, q, reader=False)` answers `query` and `query/fields`. `_answer` calls it for everyone
  else, as before.
- `api` sends only a reader's `query` paths to `_query(..., reader=True)` itself. Everything else still goes through
  `_answer` with three arguments.
- This is the most reversible option: anything that replaces `_answer` keeps working.
- About 5 net lines more, so about 290 (budget 600).
- `tests/test_data_sources.py::test_an_anonymous_public_reader_is_refused_a_source_and_nothing_is_sent` still guards
  the reader path. I saw it fail with `api`'s reader branch forced off, then pass again with the branch back.

Run here, round 3, one file at a time: test_web_lanes (11, was 8 failed), test_data_sources (13), test_query_engine,
test_web_access and test_projects_header all passed. test_data_source_panels passed under the watchdog (rc 0, none
skipped). ruff is clean. Not run here: the whole unit suite and the four browser files. `main` (f086f76e) is already
merged in and has not moved.

### Round 4

The finding (blocking): the 10 s time bound was not enforced. `urlopen`'s timeout covers each socket read, not the
whole request, so a source that sent headers and then trickled its body held a web worker for as long as it kept
sending. Fixed in the code. About 50 net lines more, so about 340 (budget 600).
- `prometheus._get` now sends its one GET with `http.client`, not `urlopen`. One deadline covers the whole request:
  - Each address is connected with only the time left.
  - A `threading.Timer` shuts the socket down at the deadline, whatever is blocked on it (a stalled header, a
    trickled body, a TLS handshake).
  - The timer keeps its own handle on the socket, because the response takes the socket over from the connection.
  - It is cancelled, and the socket closed, when the GET ends.
- Past the deadline the query is refused with `error_kind: limit`: "source 'prom' did not answer within N s". A body
  cut short is never parsed.
- Not bounded: looking up the host name, which the system's resolver does and nothing here can interrupt. SPEC §4e
  (*Data sources*) now says so, which narrows the claim.
- Choices taken without asking (the most reversible):
  - `http.client` does not read `HTTP_PROXY` or follow redirects, where `urlopen` did. No test or doc relied on either.
  - A `url` that is not http or https is now refused as `unreachable` before anything is sent.
- Tests:
  - `tests/test_data_sources.py::test_a_source_that_is_slow_to_answer_is_cut_off_at_the_time_bound`, with the bound
    set to 1 s. Its three cases are `late` (no headers for 30 s), `stall` (headers, then nothing) and `trickle` (a byte
    every 0.1 s). Each must be refused with `limit` within 2.5 s.
  - `tests/test_data_source_panels.py::test_a_source_that_trickles_its_answer_says_so_in_its_panel_at_the_time_bound`
    (browser, real server, real 10 s bound). The panel must show the error within 16 s.
  - With the timer not started, `trickle` failed: it took the stub's full 30 s and ended as `unreachable`. `late` and
    `stall` still passed, because each socket read's timeout catches them. Only the trickle case is guarded by the
    deadline alone.
  - The first try at the fix cut `conn.sock`. The trickle test caught it (30 s), which is why the timer now keeps its
    own handle.

Run here, round 4, one file at a time: test_data_sources (16), test_query_engine (52), test_web_lanes (11) and
test_web_access (26) all passed. test_data_source_panels (3) passed under the watchdog (rc 0, none skipped). ruff is
clean. Not run here: the whole unit suite and the four browser files. `main` (28ad5c4a) is already merged in.

### Round 5

First, the factory's merge of main (8a27f9e3) conflicted in `ergostat/web/server.py`. Main added `pinned=` to `_answer`
(dashboards answer every panel from one snapshot); the branch added `_query` just above it. Both are kept. Main's
`dashboard_api` calls `_answer` only on its panels' paths (`series`, `items`, `loops`, ...), never `query`, so it gives an
anonymous reader no way to a data source.

The finding (blocking): the deadline did not hold for an https source. Round 4's record said the timer cuts "a TLS
handshake". It did not. Wrapping the socket in TLS takes the plain socket's file over, so the socket the timer held had
no file, and the cut did nothing. Fixed in the code. About 15 net lines more, so about 355 (budget 600).
- `prometheus._tls` replaces `HTTPSConnection.connect` for an https source. It connects as before, then wraps the
  socket with the handshake put off. It adds the TLS socket to the timer's handles, and only then does the handshake.
  So the cut reaches the socket actually being read: during the handshake, a stalled header or a trickled body.
- If the cut fires between the wrap and the hold, the check right after the hold sees it, and the query is refused with
  `limit`.
- Certificates are verified as before (the default context, with the host name checked).
- SPEC §4e (*Data sources*) now names the TLS handshake and https in the time bound.
- Test: `tests/test_data_sources.py::test_an_https_source_that_trickles_is_cut_off_at_the_time_bound` (`stall`,
  `trickle`). It uses the stub over https, with a certificate from a test CA (`tests/tlscerts.make`, the openssl CLI).
  The test trusts that CA by patching `ssl._create_default_https_context`. First an ordinary query must be answered, so
  TLS is really spoken. Then, with the bound at 1 s, each case must be refused with `limit` within 2.5 s.
- With `_tls` not installed, `trickle` failed (30.0 s, the stub's whole length) and `stall` passed (each read's timeout
  catches it). This is the finding as reviewed. With `_tls` back, both passed.
- Not tested: a handshake that trickles. No stub here sends a slow TLS handshake. A handshake that stalls is ended by
  each read's timeout anyway. The cut covers a trickling one by the construction above, but no test shows it.

Run here, round 5, one file at a time: test_data_sources (18), test_query_engine (52), test_web_lanes (11),
test_web_access (26) and test_dashboards (32) all passed. test_data_source_panels (3) passed under the watchdog (rc 0,
none skipped). ruff is clean. Not run here: the whole unit suite and the four browser files.
