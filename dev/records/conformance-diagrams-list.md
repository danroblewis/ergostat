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

## Where it stopped

Parked by the factory (dead-letters, 2026-11-22 14:22).

Its runs failed past their attempts (a dead letter):
- attempt 2: nack a switch drains the runs under way (run/drain.json): taken again after it
- attempt 3: nack given back
- attempt 4: nack exited 1
- attempt 5: nack the run ended with gap/conformance-diagrams-list still parked

## Where it stopped

Built, round 1 (continued): `dev/conformance/diagrams.yaml` (25 lines), `dev/conformance/checks/diagrams.py` (125
lines; 150 net together, the budget exactly) and `tests/test_conformance_lists_ergostat.py` (14 tests: the three named,
plus each met check failing with one part of its answer missing, a check error read as broken (2) not unmet, and each
check run on main as a process of its own with its result and time). Nothing is left in this gap.

Each check run on main (52c675fe, which the branch holds) as `python dev/conformance/checks/diagrams.py CASE`, in this
gap's container (24 CPUs), not on the factory machine, so these times are not the factory's; the test bounds each at
60s wherever it runs:

| Case | Proposal expected | Result | Time | What it said |
|---|---|---|---|---|
| `stock-and-flow` | met | met (0) | 0.9s | `met` |
| `block-diagram` | met | met (0) | 0.8s | `met` (a narrower reading, below) |
| `process-map` | met | met (0) | 0.8s | `met` |
| `service-map` | unmet | unmet (1) | 0.8s | `unmet: no map view: view=map answers kind 'control'` |
| `sequence-diagram` | unmet | unmet (1) | 0.9s | `unmet: the item's answer has no lifelines or no messages` |

No result differs from the proposal's expectation. Choices the definition left open, each taken the more reversible way:
- `block-diagram`, "a block per block": a block that reads nothing and only moves flows or auxiliaries is the world
  (`ergostat/blockdiagram.py:137-139`), drawn as a disturbance only where something reads what it moves, so it is not
  required as a block. In image-squeeze that is `owner` (`examples/image-squeeze/intent.yaml:81-85`: out
  `flow.decided` into `decisions`, which no loop reads); read strictly, the case would be unmet for it alone. Every
  other block needs its `blk:` node, and every goal with a controller or an actuator its `sum:` junction.
- `sequence-diagram` asks the item's answer (`items/case%2Fb`) through the same `web.server.api` the `/graph` route
  is answered by, not a `view=`: `docs/proposals/diagram-options.md:65-68` has it opened from an item's page, not as
  a view of its own. It wants a lifeline per item of the chain and its five messages in `seq` order.
- `service-map` asks `/graph?view=map` and wants `kind: map`, at least one edge, and `rate`, `failures` and `delay` on
  every edge.
- The record the checks write is five `case.*` events on `case/a` and `case/b` (unmet, met, unmet; unmet, met), each
  caused by the one before, in a fresh state dir with `ERGOSTAT_HOME` under a temp folder, all removed after.
- Any exception of the check's own (the example not loading, `ergostat` not importable, an unknown case) exits 2, so
  it reads as broken, never unmet (lesson-3). The check puts the repository first on `sys.path`, so the list's
  `python3 ...` command finds `ergostat` without the venv.

Able to fail (lesson-9): with each view's builder (`dynamics.dynamics`, `blockdiagram.diagram`, `process.process`)
monkeypatched to return no nodes and no edges, its check exits 1 (and 0 unpatched, in the same test). With only the
flow nodes, only the comparators, or only the process lines dropped, each exits 1 too.

Not run: the list's literal `python3` command (the tests run the check with the suite's own interpreter, since
`ergostat` needs Python 3.12+ and `python3` on a machine may be older); the unit suite and the browser files (left
to the factory, as the brief says).
