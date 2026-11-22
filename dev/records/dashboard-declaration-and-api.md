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
