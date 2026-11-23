# sql-source-over-item-views: A read-only SQL data source over stable item views

depends-on: [data-source-model]

Owner's design, 2026-11-23. A dashboard data source is, as in Grafana, a connection, a query language and a typed result. Each panel query is text in its source's language. Visual query builders are not wanted. Metrics hold aggregates over bounded labels; anything with a generated ID stays in the event log. The event log remains the source of truth.

Change. For what PromQL cannot do (which items, per-item comparisons, exact medians, cohorts), a SQL source over documented, stable, read-only views such as `gaps`-style per-kind views, `transitions` and `item_fields`. The internal tables are never exposed. SQLite's authorizer allows only SELECT on those views, with time, row and memory limits. Provide `median` and percentile aggregates. The editor has SQL highlighting and autocomplete for views and columns.

Definition of done.
1. Writes, ATTACH, PRAGMA and any internal table are refused (tests).
2. A runaway query is stopped at its limit.
3. Views survive an index layout change.
4. Exact medians match a hand-worked record.

## Amendment from the chart catalog

See `docs/research/2026-11-23-charts/catalog.md` section 7.2. Add an `item_spans` view with open items, re-entry number and terminal reason, for survival, aging and exact Little's law.

## Where it stopped

Built, round 1. About 471 net lines outside tests and docs (budget 600). No size budget was written in the definition,
so the factory's 600 is the one used.

What was built:
- `ergostat/datasources/sql.py` is the `sql` type (`record: {type: sql}`, no keys, language `SQL`). Its connection is
  the asking project's own item index. The answer is typed by its columns:
  - a first column `time` makes series;
  - otherwise the leading non-number columns are a table's dims and the rest its measures;
  - numbers only get a `row` dim.
  It suggests views (`what=metrics`) and a view's columns (`what=labels&metric=VIEW`).
- `ergostat/datasources/_itemviews.py` has the views, the authorizer, the bounds and the aggregates.
  - The views are `transitions`, `item_fields`, `item_spans` (the amendment) and one per item kind (`ticket`, ...),
    each with fixed columns (SPEC §4e, *The SQL source*).
  - The aggregates are `median`, `percentile` (p 0 to 100) and `percentile_cont` (p 0 to 1), linear interpolation.
- `datasources.ASKING`: `query` and `suggest` take `project=`, and a type reads it while it answers. The engine and
  the server's suggest pass the project. No other type changed.
- `Index.reading()` (spec/itemindex.py) opens a read-only connection of its own to the index file, under the file's
  shared lock.
- `static/sql.js` (`queryEditors.SQL`) is the editor. It highlights, completes views after FROM/JOIN, and elsewhere
  completes the columns of the views the text names.
- SPEC §4e (*The SQL source*) and §11 describe it; the schema lists `sql`.

Choices taken without asking (the most reversible):
- **Copies, not SQLite views over the index.** The definition says "views". The first build used temp views and
  failed its own tests. SQLite reports a flattened view's reads of `main.items` with no view name, so the authorizer
  could not tell a view's read from a query's own.
  - Now the views a query's text names are copied into the connection's own temp tables. Then nothing of `main` is
    readable at all.
  - The cost: each query copies what it names, which is a full scan of those views.
  - Going back to real views needs a way to tell those reads apart. The views' names and columns would stay the same.
- **Per-kind views are named for the kind** (`gap`, not `gaps`): pluralising is not reliable. `-` is read as `_`, and a
  kind that is still not a plain word has no view.
- **`reason`** is the item's finished state now, on every span of the item (`finish_of`, as the Items listing reckons
  it). It is null while the item is open.
- **`item_spans` is raw**: one row per move into a state, so a lease's `leased` stay splits a span. Nothing is merged.
- **The memory limit is per connection**: an 8 MB page cache for main and temp, temp in a file, values at most 16 MB,
  8 MB of answer, at most 1,000,000 numbers in a median. SQLite's heap limit is for the whole process, so it is not
  used.
- **`:since`, `:until` and `:step`** are bound to the panel's window.

Acceptance tests, in `tests/test_sql_source.py` (8 tests, unit):
- `test_writes_attach_pragma_and_the_index_s_own_tables_are_refused` (done 1): 36 texts, and the index unchanged.
- `test_a_runaway_query_is_stopped_at_its_time_limit` (done 2): an endless recursive CTE and a 16^7 cross join, each
  stopped with `limit` within 3 s at a 1 s bound.
- `test_rows_bytes_values_and_a_median_s_numbers_are_bounded` and
  `test_a_query_s_connection_holds_its_memory_and_attaches_nothing`: the other bounds.
- `test_the_views_survive_an_index_layout_change` (done 3): the views' columns and rows before and after three
  changes are the same:
  - the `items` table rebuilt with its columns reordered plus an extra one;
  - a column added to `moves`, and a table added;
  - the file built again under a new `VERSION`.
- `test_exact_medians_and_percentiles_match_the_hand_worked_record` (done 4): the record is worked in the file's
  comment. The answers are median 30, p90 62, an even median of 25, per-item 40 and arrival-to-done 60.
- `test_the_views_answer_as_the_record_was_worked_by_hand`: `item_spans` row by row, including the open span and the
  re-entry.
- `test_an_answer_with_a_time_column_is_series_and_the_editor_is_offered_views_and_columns`.

Browser tests, in `tests/test_sql_editor.py` (real server):
- `test_a_sql_panel_draws_its_answer_and_a_read_of_the_index_says_why_it_is_refused`.
- `test_the_query_box_highlights_sql_and_completes_views_and_their_columns`.

Seen to fail when the code they guard was broken:
- With the authorizer off, done 1 failed (`select count(*) from main.items` was answered).
- With the deadline 5 s late, done 2 failed (6.0 s).
- With the interpolation dropped, done 4 failed (p90 50, not 62).
- With the per-kind view written `i.*`, done 3 failed on its pinned columns. With that pin also removed, it failed at
  the layout change itself.
- With `queryEditors.SQL` not registered, the editor test failed.

Not tested:
- The time bound during the copies, before the query runs. The progress handler is set before the copies, but no test
  makes a copy slow, so SPEC does not claim it.
- Catching the index up with the record before a query is not bounded. Every item panel does that too.

Run here, one file at a time:
- Unit files: test_sql_source (8), test_data_sources, test_spec_schema, test_item_index (116 together),
  test_promql_suggest, test_query_engine and test_result_shapes (74 together). All passed.
- Browser files under the watchdog: test_sql_editor (2), test_promql_editor, test_data_source_panels and
  test_panel_editor (44). All passed, rc 0, none skipped.
- ruff is clean.
- Not run here: the whole unit suite and the four browser files (the factory's). No example was touched, so no
  `demo_check`. `main` (278f54a4) has not moved since the clone, so there was nothing to merge.

Round 2: the review's one finding, answered.
- **Copies read in separate snapshots (blocking, lesson-1).** `_itemviews.opened` now runs `begin` before the copies
  and `commit` after them, before the authorizer is set. Each kind's finished states (what `reason` is made from) are
  now read inside that same transaction, from the index's `left` table (`_finished`), not from `ix.left` before it.
  `sql._index` no longer reads them, and `opened` no longer takes them.
- New test `test_a_query_joining_views_reads_one_state_of_the_index_while_it_is_caught_up_between_copies`. It
  monkeypatches `_definitions`, so that after `item_spans` is copied and before `ticket` is, ticket/5 is made done and
  the index caught up (a committed write). The join still sees ticket/5 `doing` in both views. The next query sees it
  `done` in both.
- Seen to fail: with `begin`/`commit` removed, the `ticket` view had ticket/5 as `done` and `item_spans` had it as
  `doing`.
- SPEC §4e (*How a query is kept read only*) says so.
- Run: test_sql_source (9), test_data_sources, test_query_engine. ruff is clean. `main` (278f54a4) has not moved, so
  there was nothing to merge. Not run here: the whole unit suite and the four browser files.
- Once, with test_data_sources and test_query_engine run together, a timing bound failed. It was
  test_query_engine.py:343, `best < 0.100` s for an items/moves/counts/series query on a 100,000-event record, which
  does not go through the sql source. It passed when that file was run alone, and twice more with the pair (70
  passed). It is a load-dependent bound outside this gap, so it is left alone (lesson-13).

## Entry

section: Interface

- **A read-only SQL data source over stable item views** (`sql-source-over-item-views`): a `sql` source answers
  SQLite SELECTs over the views `transitions`, `item_fields`, `item_spans` and one per item kind.
  - It has exact `median` and `percentile`.
  - Writes, ATTACH, PRAGMA and the index's own tables are refused.
  - Each query is bounded in time, rows, bytes and memory.
  - Its editor highlights SQL and completes views and columns.
  - Left: real views in place of per-query copies, if the authorizer can be made to tell a view's reads apart.
