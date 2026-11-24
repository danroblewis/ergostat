# result-shapes-test-owns-its-fake-source: the result-shapes test no longer collides with the real SQL source

`tests/test_result_shapes.py::test_a_promql_and_a_sql_answer_of_one_shape_are_the_same_answer` fails on main when run alone (`source warehouse: unknown key 'database' (known: type)`). Its fixture registers a fake data source of type `sql`, and the real `ergostat/datasources/sql.py` has now landed with the same type name, so which module wins depends on test order. The factory reads this as "main is broken" and holds `result-frames-and-verdicts`, which most new chart work depends on.

Change. Give the fixture's fake source a type name of its own, and use it in the test's model. Test-only. Do not change `ergostat/datasources/`.

Definition of done.
1. The test passes alone and in its whole file.
2. Removing the fixture's registration makes it fail, proving it uses the fake source.
3. Do not measure or change the live instance in the session.

## Where it stopped

Built. The fixture registers its fake as type `fake-sql` (`FAKE_SQL`), and the model uses that type. The fixture first calls `datasources.types()` so the package types are already found and the lazy discovery cannot replace the fake later. Its `unregister` now removes only the fake: before, `unregister("sql")` also removed the real SQL type for every later test in the process. Test-only. `ergostat/datasources/` is unchanged. Done 2 was checked by hand: with the registration disabled, the test fails with `source warehouse.type: one of command, ergostat, prometheus, sql`.
