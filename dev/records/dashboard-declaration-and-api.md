# dashboard-declaration-and-api: Named dashboards declared under dashboards: in the model, checked like show:, and served in one request

depends-on: [dashboard-proposal]

Problem: an arrangement in the address is personal; a shared dashboard needs a durable home whose references are checked, so a renamed stock is a finding instead of a blank panel. Fetching panels one by one would load a server that already stops answering on the factory. Precedent: systems.*.show is a display declared in the model, compiled with its references checked (ergostat/spec/compile.py:908-913, 1588; SPEC §4a). Built only if the proposal and the owner's answer keep declared dashboards.
Change (as the proposal decides): (1) a top-level dashboards: NAME: {description, window?, panels: [{type, title, size, params}]} in spec/compile.py and ir.py, schema/ergostat.schema.json and SPEC §4; unknown types or keys and references to unknown stocks, flows, auxiliaries, goals, kinds or states are errors with file and line; a dashboard in a system's file is namespaced by that system. (2) GET /api/dashboards lists name, description and panel count. (3) GET /api/dashboard/NAME returns each panel's declaration and answer, built by the functions the existing endpoints call (series plus add_to_series; the items listing through item_sets; items-flow; items-graph plus eta; the loops rows), all on one Live.snapshot with a per-panel time limit (over it: {pending: true}, computed for the next poll) and have= stamps so an unchanged panel is not re-sent. NAME=default gives the model-derived one (each top system's show: measures and its goals). (4) `ergostat snapshot` holds each dashboard's answer. (5) /dashboard lists the named dashboards beside the reader's own when dashboard-page-v1 is present; a declared one is read-only with 'Copy to mine'. (6) docs/AGENT-GUIDE.md says how an agent or the Supervisor adds one (people do not write it by hand); SPEC says whether a dashboards-only change skips the judge's replay.
Definition of done:
1. The key loads, validates and round-trips; a spec naming stock.nope fails `ergostat check` with unknown-ref at its line.
2. One request returns every panel, and its answers equal the separate endpoints' for the same snapshot.
3. A panel forced slow answers pending while the others answer.
4. On :8796 GET /api/dashboard/default takes under 0.5 s.
5. The page has no control that writes a declared dashboard.
Files: ergostat/spec/compile.py, ergostat/spec/ir.py, schema/ergostat.schema.json, ergostat/web/server.py, new ergostat/web/dashboard_api.py, ergostat/web/snapshot.py, docs/SPEC.md, docs/AGENT-GUIDE.md, a dashboards: block in the software-factory and ticket-factory demos, tests.
Acceptance tests: compile tests (parse, namespacing, bad reference), API tests (batched equals separate; slow panel pending), the timing check.
Budget: 400 net lines including tests; the Coordinator may split it as (a) the key, schema and check, (b) the batched API.

Milestone: dashboard. Owner items: 18, 2. From the owner's list and the design review of 2026-11-22.

## Where it stopped

Parked by the factory (implementor, 2026-11-22 14:17).

Stopped on its last attempt by RuntimeError: claude: success: You've hit your weekly limit · resets Nov 24, 3am (UTC)

```
Traceback (most recent call last):
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 166, in main
    return build(cfg, given, began)
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 221, in build
    got = fac.session(cfg, "implementor", prompt, work)
  File "/Users/user/ergostat-live/instance/dev/bin/fac.py", line 669, in session
    raise RuntimeError(f"claude: {out.get('subtype')}: {str(out.get('result'))[:300]}")
RuntimeError: claude: success: You've hit your weekly limit · resets Nov 24, 3am (UTC)

```

## Where it stopped

Parked by the factory (dead-letters, 2026-11-22 14:18).

Its runs failed past their attempts (a dead letter):
- attempt 2: nack a switch drains the runs under way (run/drain.json): taken again after it
- attempt 3: nack a switch drains the runs under way (run/drain.json): taken again after it
- attempt 4: nack exited 1
- attempt 5: nack the run ended with gap/dashboard-declaration-and-api still parked

## Where it stopped

Implementor, 2026-11-23 (continued, round 1). Built: changes 1 to 4 and 6. Not built: change 5 (the page), because
dashboard-page-v1 is not on main and the change only applies "when dashboard-page-v1 is present".

What is built:
- (1) `dashboards:` loads (`spec/load.py`: a top-level key, `SYSTEM.NAME` when the file's `defaults:` sets a system,
  `default` refused), compiles and is checked (new `spec/dashboards.py`, called from `compile.py`'s `references` with
  the `exists` check that `show:` uses), into `ir.Dashboard` and `ir.Panel`; the schema has `$defs/dashboard` and
  `$defs/panel`; SPEC §4 lists the key and the new §4e says the rest. It is in no version hash (tested).
- (2) `GET /api/dashboards`; (3) `GET /api/dashboard/NAME` in new `web/dashboard_api.py`. Each panel is answered by
  `server._answer` on its own endpoint's path and parameters (series with add_to_series, items with item_sets and
  eta, items-flow, items-graph with eta, loops, loop-scope), given the dashboard's one snapshot (`_answer(...,
  pinned=)`). `Live.moment` numbers each snapshot (`seq`); moments and jobs are compared by that number only. Per
  panel limit 0.3 s, batch 0.4 s, pool 2 threads and 16 waiting (constants in code); `have=` stamps; `default`.
- (4) `ergostat snapshot` holds `dashboards` and every `dashboard/NAME`, none pending. (6) AGENT-GUIDE §3k; SPEC §4e
  says that a dashboards-only change does **not** skip the judge's replay today (`improve.kind_of` reads it as a
  parameter change), and that the `display` kind that would skip it is dashboard-keep-display-proposal's.
- Demos: `week` in software-factory's factory.yaml, `delivery.review` in factory/delivery.yaml, `oversight.hours` in
  ticket-factory's factory/oversight.yaml (all appended at the end of their files, so no part's line moves).

Choices made without an answer (each the most reversible):
- The panel format is the proposal's (`panel:` for the kind, parameters flat beside it, `title`, `size`, `note`), not
  the definition's `{type, title, size, params}`: the definition says "as the proposal decides", and the proposal
  names it `panel` so `kind` stays the item kind. A dashboard takes both `title` and `description`.
- The proposal (section 9) moved the batched read to dashboard-page-v1; the definition of done still carries it, and
  dashboard-page-v1 is not on main, so it is built here, with the definition's per-panel limit and pending answer.
  The proposal's 0.8 s batch and late-pool rules are followed in their bounds (2 threads, 16 waiting, 6 s drop,
  30 s kept, results only for the same moment), with a 0.4 s batch to fit done item 4.
- Kinds are the ones that reuse an endpoint as it is (note, goals, chart, items, states, cycle-time, scope,
  items-graph, timeline). xy, heatmap and diagram are their own gaps, so they are refused as unknown kinds today.

Done items: 1, 2, 3 tested (below). 4: **not measured on :8796** (no such server reaches this container). The
timing test runs `GET /api/dashboard/default` on a copy of examples/software-factory with an empty record and
asserts under 0.5 s; that is a smaller claim than the definition's. 5: holds trivially, as there is no page.

Known limits: the snapshot itself is made on the request thread before the panels' clock starts, as for every other
endpoint, so a slow snapshot makes the whole answer slow. Two slow panels fill the pool, and the panels after them
then answer pending. A panel's job that has started runs to its end after its asker has gone (bounded to 2).

Tests (tests/test_dashboards.py, 30): parse and round trip, schema accepts and refuses, `ergostat check --json`
on stock.nope gives exactly unknown-ref at its file and line, 17 cases of unknown kinds, keys, references and bad
values each at their line, the 24-panel cap and the name default, namespacing, both demos compile, no version
change, batched equals separate (with a panel that asks for a snapshot of its own failing it), have= stamps, a slow
panel pending while the others answer and then answered at the same moment, the full pool, a moment named after the
model changed, the default and its timing, the snapshot. Broken on purpose and seen to fail: panels not pinned to
the snapshot (the equality test), no time limit (the slow-panel test), have= ignored (the stamps test), refs not
checked (the stock.nope and auxiliary.x tests).
Also run, passing: test_graph_cli_web, test_spec_schema, test_spec_compile, test_storage, test_scale_caches,
test_snapshot_sets, test_ticket_factory_links, test_architecture, test_shards, test_cli_fallback,
test_spec_structure, test_code_health_coverage. Not run: the whole unit suite, the browser files (no page changed),
demo_check (the commands to look for ~/ergostat-demos and run it were refused in this session).

Overrun reason: the definition's 400 lines including tests did not foresee the batched API's bounded pool, moments and stamps that the proposal's load rules require (about 220 lines in dashboard_api.py), nor a check per parameter kind with errors at their line (about 215 in spec/dashboards.py); outside tests, docs and dev the change is about 590 net lines (code 505, schema and demos 87), within the factory's 600, and the tests are about 330.

## Where it stopped

Implementor, 2026-11-23 (continued, round 2). The two review findings, both answered:
- dashboard_api.py's job key (lesson-5): a panel's job is now keyed `(moment, dashboard name, index, the panel's
  whole declaration)`, so the panel kind is in it. New test
  `test_two_dashboards_of_one_moment_each_answer_their_own_panels` asks `ops` and a second dashboard `other` at one
  `at=`, asserts both got the same moment, and checks every panel of both against its own endpoint. Index 0 is
  goals in one and timeline in the other, and index 3 is states and items of one kind. With the old key put back,
  it failed (the timeline panel was given the goals answer).
- The done-item-4 timing test (lesson-9, lesson-8) now also asserts that every panel has an answer, with none
  pending, busy or failed. With BATCH set to 0 it failed, as every panel answered pending.
Still as round 1 says: change 5 (the page) is not built, as dashboard-page-v1 is not on main. Done item 4 is not
measured on :8796. Code lines changed this round: +2 net.
Tests run: tests/test_dashboards.py (31 passed), ruff clean. Not run: the unit suite, the browser files, demo_check.

## Where it stopped

Implementor, 2026-11-23 (continued, round 3). The one finding was a conflict with main in ergostat/web/server.py. It
is resolved in the merge of main (5411f137): `_answer` keeps both main's `why` head and the branch's
`dashboards`/`dashboard` heads, ahead of the snapshot. No other code changed this round. Still as round 1 says:
change 5 (the page) is not built, because dashboard-page-v1 is not on main, and done item 4 is not measured on :8796.
Tests run after the merge: tests/test_dashboards.py (31 passed), tests/test_why.py (33 passed),
tests/test_graph_cli_web.py (42 passed), ruff clean. Not run: the unit suite, the browser files, demo_check.

## Where it stopped

Implementor, 2026-11-23 (continued, round 4). The one finding was that the pool's waiting bound was below the
checker's panel cap, and it is fixed: `dashboard_api.WAITING` is now `2 * MOST`, which is 48 (`spec/dashboards.MOST`
is 24). One request's own panels therefore always fit when the pool holds at most one other dashboard's worth of
waiting jobs, which includes an idle pool. Busy now means only that other requests have overloaded the pool. Threads
stay at 2, which is the bound that matters for the machine. Each waiting job is a closure over a kept moment's
snapshot, and at most 8 snapshots are kept. `default` is now cut at `MOST` instead of a literal 24. SPEC §4e says 48
and when busy happens. New test `test_a_dashboard_of_the_most_panels_answers_every_one_in_one_request`: a valid
24-panel dashboard on an idle server answers every panel, with none busy, pending or failed, and each answer equals
its own endpoint's at the same moment. With WAITING put back to 16 it failed (panels 18 to 23 answered busy). The
test raises the batch and panel time limits, so it pins the pool's room and not the timing (done item 4's test pins
the timing).
Still as round 1 says: change 5 (the page) is not built, because dashboard-page-v1 is not on main, and done item 4
is not measured on :8796. Code lines changed this round: +3 net.
Tests run: tests/test_dashboards.py (32 passed), ruff clean. Not run: the unit suite, the browser files, demo_check.
