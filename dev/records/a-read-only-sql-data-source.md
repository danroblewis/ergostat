# a-read-only-sql-data-source: the SQL source reads real views over the item index, checked first on an empty stand-in, instead of copying each view per query

depends-on: [sql-source-over-item-views]

## Definition of done
What is already on main is not built again: the `sql` source, the views `transitions`, `item_fields`, `item_spans` and the per-kind views, exact `median`/`percentile`, the refusals, the bounds and the SQL editor (`sql-source-over-item-views`). This branch does only the entry's "Left" item: real views instead of copies.
1. A query no longer copies any view. On the query's own connection, each view is a temporary SQLite view over the index's tables (the definitions in `_itemviews.py` stay as they are), so a query reads only the rows it needs. After a query, that connection's temporary schema holds views and no tables.
2. SQLite does not tell the authorizer which view a read is for. So before the text runs on the index, it is checked on a connection of its own that has no index. There each view is an empty table with the same name and columns, with the same functions and aggregates, the same limits and the same authorizer as today: only SELECT, reads of those names and the query's own `WITH` names, and the function allowlist. The text then runs on the index only if that check passed. A refusal there is the answer, and the index is never asked.
3. The check runs under the query's own deadline. If it ends any way other than a pass (refused, stopped at the deadline, or any other error), the text is not run on the index and the answer is `refused` or `limit`. It never fails open.
4. On the index connection, the authorizer still refuses anything but SELECT and allowlisted functions, and allows reads only of the tables the view definitions use. So a text that resolves differently there than on the stand-in is still refused.
5. Every test in `tests/test_sql_source.py` and `tests/test_sql_editor.py` passes unchanged. That includes the 36 refusals, the layout-change test, the one-snapshot join test and the hand-worked medians. The finished states behind `reason` and the query are read in one read transaction.
6. SPEC §4e (*How a query is kept read only*) and the module docstrings describe the check-then-run design in place of the copies. The record's `## Entry` drops the "Left" clause.

## Relation to other work
- item-spans-and-censored-delays (ready): builds on the `item_spans` view in `_itemviews.py`. This branch changes how views are made, not what they hold. Whichever lands second merges the file.
- retire-old-query-forms (ready): avoids its files. The `sql` source's interface does not change.

## Files to touch
- `ergostat/datasources/_itemviews.py`
- `ergostat/datasources/sql.py`
- `docs/SPEC.md`
- `tests/test_sql_views.py` (new)
- `dev/records/a-read-only-sql-data-source.md` (new)

## Risks
- lesson-8: a name that only the index connection has (`items`, `moves`, `names`, `left`, `main.x`, `sqlite_master`, `sqlite_temp_master`, `pragma_table_info`, `_fields`) could resolve on the index and not on the stand-in, so "read only" would be claimed wider than it is.
- lesson-3: a check that errors, times out or is skipped could let the text run on the index anyway.
- lesson-9: the new refusal tests must fail with the check removed. Show it in the report.

## Acceptance tests
- `tests/test_sql_views.py::test_a_query_reads_real_views_and_copies_nothing`: after a query, the connection's temporary schema holds only views, and the answer equals the hand-worked record.
- `tests/test_sql_views.py::test_a_name_only_the_index_has_is_refused_before_the_text_reaches_the_index`: each of the names in lesson-8, plain and qualified, is refused. A spy shows the index connection never ran the text. With the check removed, this test fails.
- `tests/test_sql_views.py::test_a_check_that_fails_or_runs_out_of_time_does_not_run_the_query`: the check is made to raise an unexpected error, and in a second case a recursive CTE outruns a 1 s bound. Both answer `refused` or `limit`, and the index connection never ran the text.
- `tests/test_sql_views.py::test_the_index_connection_refuses_a_read_outside_the_view_tables`: the check is passed by force, and a read of a table the views don't use (`sqlite_master`, an extra table) is still refused on the index.
- `tests/test_sql_source.py::test_writes_attach_pragma_and_the_index_s_own_tables_are_refused`: unchanged, still passes.
- `tests/test_sql_source.py::test_a_query_joining_views_reads_one_state_of_the_index_while_it_is_caught_up_between_copies`: unchanged (only the name's wording may change), still passes with views.

## Size budget
60 net lines
size: M (confidence: medium)

## Notes from the plan review (answer each)

- Done item 4's index-connection allowlist ('tables the view definitions use' + 'allowlisted functions') refuses the views' own reads once they are real views rather than copies made before set_authorizer: `_fields` (not in FUNCTIONS) used by item_fields and every kind view with show: fields (_itemviews.py:92,98), the table-valued `json_each` (main.json_each) in item_fields, and, for views SQLite does not flatten (item_spans has window functions), reads reported as temp.<view> (see the docstring at _itemviews.py:155). State the index allowlist exactly: main.items/moves/names, json_each, the temp view names, and FUNCTIONS plus `_fields`; the stand-in keeps refusing `_fields`, json_each and main.* when the query's own text names them (an existing refusal is `select _fields(body), 1 as n from main.items`).
- SQLite runs the authorizer at prepare time, so the stand-in check only needs to prepare the text (e.g. `explain <text>`), not execute it; executing runs recursive CTEs, generated strings and row limits twice against the one deadline. If the check only prepares, acceptance test 3's 'recursive CTE outruns 1 s in the check' case must be forced by a monkeypatch.
- test_a_query_joining_views_reads_one_state_..._between_copies hooks into iterating _definitions(...).items(); it passes only if `begin` + _finished come before that loop and the query runs inside the same transaction, committed when opened() exits (today the commit at _itemviews.py:184 comes before the yield). Set `pragma query_only = 1` after the views are made (test_a_query_s_connection_holds_its_memory checks it).
- The raw() helper (tests/test_sql_source.py:150) calls opened(ix, spec, deadline) with no text and runs the text directly; put the check in sql.query, or make opened(text=None) skip it, so these tests pass unchanged.
- Say whether the stand-in's empty tables live in its main or its temp; main.transitions and temp.transitions may then resolve differently on the two connections (it fails closed, but document it in SPEC §4e).
- A refusal recorded in `why` during the check must be the answer; a pass must leave `why` empty; and any non-sqlite3.Error exception from the check must also stop the index from being asked (_refusal catches only sqlite3.Error).

## Where it stopped

Built, round 1: every point of the definition. `_itemviews.check` prepares the text on the stand-in. `_itemviews.opened`
now makes temp views. `sql.query` runs the check, then the query. SPEC §4e (*How a query is kept read only*) and both
module docstrings describe check-then-run.

Found while building (lesson-8), and closed here: SQLite reports a name read for no column (`select count(*) from
items`) to the authorizer with **no database**, the same as a `WITH` name. The old rule "no database means a `WITH`
name" therefore let `select count(*) as n from items` through. That was already so on main, where it answered from the
index's own `items`. The 36 refusals never tried it, though they did try `count(*) from main.items`. Now, on the stand-in, such
a name is held back and refused once the text is prepared, unless it is a view or a `WITH` name the text declares (a
SELECT inside it names it). The check returns those names. On the index, a no-database read is allowed only for the
views and those names (none, if the check is skipped).

Answers to the plan review:
- The index allowlist exactly: reads of `main.items`, `main.moves`, `main.names`, `json_each` (as `main.json_each`) and
  `temp.<view>` (views and, when named, the stages' tables). No-database reads: those view names and the check's `WITH`
  names. Functions: FUNCTIONS plus `_fields` and `json_each`. The stand-in allows `temp.<view>` reads and FUNCTIONS
  only, so `_fields`, `json_each` and every `main.*` that the text itself names are refused there (tested).
- The check only prepares: its progress handler (`_prepared`) stops the first step, since the authorizer has already
  run. A pass is "interrupted" (or done) with `why` empty and the deadline not passed. Anything else re-raises. For
  the 1 s case, `test_a_check_that_fails_...` monkeypatches `_prepared` so the check runs the recursive CTE to the
  deadline. It answers `limit` and the index is never opened.
- The one-snapshot join: `begin` and `_finished` come before the `_definitions` loop. The query runs inside the same
  transaction, committed when `opened()` exits (the authorizer is taken off for the commit). `pragma query_only = 1` is
  set after the views are made. The test passes unchanged, its name too.
- `raw()`: the check lives in `sql.query`, so `opened()` with no text (the helper's) does no check. The tests pass
  unchanged.
- The stand-in's empty view tables are in its **temp**, as the views are on the index, so `temp.transitions` resolves on
  both and `main.transitions` on neither (refused; said in SPEC §4e). Its **main** holds the index's own tables, empty
  (`itemindex.SCHEMA` + `projections.SCHEMA`). So `items` or `main.items` resolve there as on the index and are
  refused with the same words ("reads main.items"), which `tests/test_sql_editor.py` checks. Without them the answer
  was "no such table", and that test failed.
- `why`: a refusal recorded in the check is the answer (`_refusal` reads `why[0]` first), and a pass leaves it empty.
  Any exception from the check that is not a `sqlite3.Error` is answered `refused` ("could not be checked (KeyError)").
  The index is not opened (tested).

Choices made alone (the most reversible):
- The stages' views (`item_stages`, `stage_estimates`, `item_progress`) are made in Python (stages.rows), not by SQL
  over the index, so they cannot be SQLite views. They are still copied into temp tables, as before, and only when the
  text names one. Done item 1's "the temporary schema holds views and no tables" therefore holds for every query that
  names no stage view. The acceptance test checks it for an `item_spans` query.
- The `## Entry` below is a sub-gap's (`entry-of: sql-source-over-item-views`). I removed the "Left" line from the
  umbrella's bullet in `dev/records/sql-source-over-item-views.md`, the only place the clause lives. That file is not
  in "Files to touch", but done item 6 cannot be met without that edit.

Lesson-9, each seen to fail with the code broken:
- With the check call in `sql.query` replaced by `own = None`, `test_a_name_only_the_index_has_...` failed
  (`select count(*) as n from main.items` answered rows). So did `test_a_check_that_fails_...` (the broken check's
  query answered).
- With the stand-in's no-database resolution removed, `test_a_name_only_...` failed: 8 texts, `count(*) from items`
  among them, reached the index. The index authorizer still refused them.
- `test_the_index_connection_refuses_...` passes the check by force. It shows that `sqlite_master`, `temp.sqlite_master`,
  an added table, `meta`, `links`, `numbers`, `left` and `load_extension` are refused on the index. It also shows that
  `main.items` is then readable there, which is why the check comes first.

Overrun reason: 65 net lines against 60. The 5 over are the no-database read handling (held back on the stand-in, and
the `own` names passed to the index's authorizer), a read-only hole found while building and not in the plan.

Run here, each passing: `tests/test_sql_views.py` (4), `tests/test_sql_source.py` (9), `tests/test_stages.py`, and
`tests/test_sql_editor.py` (2, with Playwright under the watchdog, nothing skipped). ruff is clean. Local `main` is
this branch's base, so there was nothing to merge. Not run: the whole unit suite and the four browser files (the
factory runs them). No example was touched, so demo_check was not needed.

## Entry

entry-of: sql-source-over-item-views
done: 2026-11-24 a query's text is checked first on an empty stand-in of the index, then run on real temp views over the index's tables, with no per-query copies; a name read for no column (`count(*) from items`) is refused too.
