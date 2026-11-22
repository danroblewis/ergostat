# conformance-diagrams-list: ergostat's first conformance list: diagrams, five cases with checks that can fail

depends-on: [conformance-list-files]

# conformance-diagrams-list: `dev/conformance/diagrams.yaml` and its checks



The proposal's first list for ergostat (docs/proposals/conformance-stock.md section 6, diagrams) has five cases:
- `stock-and-flow`, expected met (`ergostat/web/server.py:478-491`, `ergostat/dynamics.py:219`);
- `block-diagram`, expected met (`ergostat/web/server.py:469-474`, `ergostat/blockdiagram.py:1423`);
- `process-map`, expected met (`ergostat/web/server.py:460-468`, `ergostat/process.py:354`);
- `service-map`, expected unmet (no `map` view, `ergostat/web/server.py:460-478`; wanted at `docs/proposals/diagram-options.md:59-64`);
- `sequence-diagram`, expected unmet (◻ at `docs/DISCIPLINES.md:36`).

The owner holds new diagrams (`docs/proposals/diagram-options.md:3-7`), so both unmet cases are `asked: false`. Today the only count of what is drawn is a hand-kept "19 drawn today" (`docs/DISCIPLINES.md:57`), which nothing checks.

## Change
`dev/conformance/diagrams.yaml` (`list: diagrams`, each case with `from:` citing its doc line) and `dev/conformance/checks/diagrams.py CASE`. Each check:
- builds the graph answer for `examples/image-squeeze` in-process, through the same function the `/graph` route calls, with no server and no network;
- exits 0 only when the answer holds what the case says: a node per stock and flow; a block per block and a summing junction per goal served; a node per state entered and a line per move seen on a small record it writes to a temp state dir; for `service-map`, an edge per linked pair of blocks with rate, failures and median delay; for `sequence-diagram`, lifelines and ordered messages from `causedby`;
- exits 1 when the view or the field is missing, and 2 on its own error.

Checks live outside `tests/`, so pytest never collects them (`pyproject.toml:43-44`).

## Definition of done
1. `conformance_lists.read('dev/conformance', ['diagrams'])` accepts the file, and it declares exactly these 5 cases.
2. Each check run on main gives the result recorded in this gap's record. Any difference from the proposal's expectation is explained there.
3. Each check expected met is shown able to fail: run against a monkeypatched copy with that view's builder returning no nodes, it exits 1.
4. Each check finishes in under 60s on the factory machine, and its time is recorded.
5. `service-map` and `sequence-diagram` are `asked: false`.

## Files to touch
`dev/conformance/diagrams.yaml` (new), `dev/conformance/checks/diagrams.py` (new), `tests/test_conformance_lists_ergostat.py` (new; parses the file and runs the met checks' able-to-fail variants).

## Risks
- lesson-9: a check that cannot fail counts nothing. Point 3 proves each can.

## Acceptance tests
- test_diagrams_list_parses_with_five_cases
- test_diagrams_unmet_cases_not_asked
- test_each_met_diagram_check_fails_when_its_view_is_empty

## Size budget
At most 150 net lines outside `tests/` (dev/ counts).

Area: conformance. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Parked by the factory (implementor, 2026-11-22 14:22).

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
