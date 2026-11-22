# Conformance lists as a stock

Status: a proposal, 2026-11-22, for the owner to accept, change or turn down. Nothing here is built. Every claim
about today's code cites a file and line on main; where a line says something *should* happen, it is proposed.

The owner's words (2026-11-21): for any application we can list the features we wish we had (supported file
formats, algorithms, diagram types), test each, and count how many pass, like a Jenkins graph of passing tests. That
count, as a stock, would be the signal for feedback loops that raise it.

## In short

- A **conformance list** is a file of named **cases**, each a wish ("draws a service map", "exports XMILE") with a
  command that says whether ergostat does it today.
- A **runner** runs the list, and reports each case as an item (`case/<list>/<name>`) in one of three states:
  `met`, `unmet`, or `broken` (the check itself could not say). It never fails because a case is unmet.
- The count of met cases is an ordinary **stock**, counted from those items by an `items:` sensor. Its readings
  are its history (the Jenkins line); the item kind's states over time are the stacked graph.
- A **goal** on the wanted cases (unmet and broken) is off while any is left. A block serving it is the loop that
  raises the count: for ergostat itself, a program that asks the factory for a gap per unmet case.
- Almost all of this is modelling on what ergostat already has. The one demo that does it today is
  `examples/image-squeeze/benchmark.yaml`. What is new is a template and a runner, so any project can declare a
  list without writing its own `bench.py`.

## What exists already

The image-squeeze demo already keeps a list of cases as a stock:

- an item kind `case` with states `[unmet, met]`, moved by `case.met` and `case.unmet`
  (`examples/image-squeeze/benchmark.yaml:9-16`);
- a stock `capabilities` counted from the `met` items (`examples/image-squeeze/benchmark.yaml:19-25`);
- flows `gained` and `lost`, the items entering and leaving `met` (`examples/image-squeeze/benchmark.yaml:57-72`);
- a goal `every-case`, `>= 30` (`examples/image-squeeze/benchmark.yaml:114-117`);
- a runner, `world/bench.py`, which measures again only when production's commit moved
  (`examples/image-squeeze/world/bench.py:43-46`) and prints one observation line per case whose result changed
  (`examples/image-squeeze/world/bench.py:58-60`).

The machinery it rests on:

- A `run` sensor's output is read for observation lines besides its number (`ergostat/spec/engine.py:2367-2369`).
  A line is kept only if its event type is not one of ergostat's own and it names an item with a `/`
  (`ergostat/spec/engine.py:2304-2313`); kept lines are recorded as events from that sensor
  (`ergostat/spec/engine.py:1331-1349`, the write at `:1348`).
- An item kind maps event types to states (`ergostat/spec/ir.py:867`), and plain data folds into its fields
  (`ergostat/spec/ir.py:873`).
- An `items:` sensor counts the items of a kind in a state (`ergostat/spec/items.py:451`, reached from
  `ergostat/spec/engine.py:2340-2345`).
- Readings are kept in the measurements store (`ergostat/store.py:558`, `:600`). A stock's chart takes its last
  reading in each bucket (`ergostat/series.py:52`). An item kind's states over time are worked out by
  `ergostat/series.py:342`.
- A goal is judged at each pass: its error and whether it is off, and a `loop.off` or `loop.holding` event with
  the value and setpoint when its status changes (`ergostat/spec/engine.py:326-365`, the event at `:360-362`).

And the hand-kept version of the idea: `docs/DISCIPLINES.md` marks some 34 diagrams and charts as drawn (✅) or
possible (◻), and counts "19 drawn today" (`docs/DISCIPLINES.md:57`). Nothing checks that count. A conformance
list is that table with a test behind each mark.

## 1. Declaring a list

A list is a YAML file in the project, read by the runner (never by the model loader):

```yaml
list: diagrams
description: the diagram types ergostat draws, from docs/proposals/diagram-options.md
cases:
  service-map:
    description: a service map (the Map view) of what passed between blocks, with rate, failures and delay per edge
    from: docs/proposals/diagram-options.md:59
    asked: false                     # recorded, but not yet open to the loop (the owner's decision, below)
    check: python3 dev/conformance/checks/diagrams.py service-map
    timeout: 2m
  stock-and-flow:
    description: the Dynamics view draws a model's stocks and flows
    check: python3 dev/conformance/checks/diagrams.py stock-and-flow
```

| Key | Meaning |
|---|---|
| `list` | the list's name: lowercase words and hyphens (`^[a-z0-9][a-z0-9-]{0,63}$`), part of each case's id |
| `cases` | case name (same pattern) to case; at most 500 cases in a list |
| `check` | the command that says. Exit 0: met. Exit 1: unmet. Anything else, a timeout, or a missing command: `broken` |
| `timeout` | per case, default 1m, at most 10m |
| `asked` | default true. A case with `asked: false` is counted, but the loop does not take it |
| `from` | where the wish came from (a doc line, a decision): shown on the item |
| `description` | what the feature is, in a sentence |

A case is a wish, not a test of a wish's details: one case per feature, and a check that passes only when the
feature really works on a real model (the image-squeeze cases are measured, not asserted).

## 2. Running and counting

The runner (proposed: `ergostat/library/run/conformance.py`, reached as `${lib} conformance`, beside the
library's other programs such as `ergostat/library/run/each.py:1-19`):

1. Reads the list. A list it cannot read, or one that breaks the table above, exits non-zero. A sensor whose
   command exits non-zero records no reading and none of its observations (`ergostat/spec/engine.py:2365-2368`),
   so a broken list stops the count instead of reading as zero.
2. Decides whether to run. Like `bench.py`, it runs the cases only when what they check has changed: for
   ergostat, when main's head moved; else it prints the last result again.
3. Runs each case's check, one at a time, in its own process group. At the case's timeout it kills the group, not
   only the process. The engine's own timeout on a sensor kills only the process it started and returns
   (`ergostat/spec/engine.py:2361-2364`), so whatever a check started would otherwise keep running (lesson 6). The
   whole run must also end inside the sensor's `timeout`, so the runner stops starting cases once the time it has
   left is less than the next case's timeout; the cases not run keep their last state and are named on stderr.
4. Prints, for every case run (not only those that changed), one observation:
   `{"event": "case.met", "item": "case/diagrams/stock-and-flow", "data": {"list": "diagrams", "asked": true,
   "commit": "…", "run": 41, …}}` (the case's `description` and `from` too, so the item shows them), or
   `case.unmet` / `case.broken` with the check's last lines of output in `data.said`. The run number comes from
   the runner's own counter, so "which result is newer" is read by sequence, never by time (lesson 2).
5. Prints `case.withdrawn` for each case item the record holds that the list no longer names. It reads them with
   `$ERGOSTAT_CMD item --kind case --json` (`docs/SPEC.md:1729`, the `run` row). Without this a case taken off the
   list would stay `met` and keep counting (lesson 5).
6. Prints its number: how many cases the list declares.
7. Exits 0 whatever the cases said. An unmet case is a result, not a failure of the runner.

The model it feeds (proposed as a built-in template, `use: conformance`, beside
`ergostat/library/templates/keep-under.yaml`; the parts below are what a use makes):

```yaml
items:
  case:
    id: case/*
    states: [unmet, met, broken, withdrawn]
    on: {case.unmet: unmet, case.met: met, case.broken: broken, case.withdrawn: withdrawn}
    show: [list, description, from, asked, commit, run, said]
stocks:
  conformance-declared:              # the runner's number: what the list asks for
    unit: cases
    sensor: {run: "${lib} conformance --list ${list}", every: 10m, timeout: 30m}
  conformance-met:                   # the count: the Jenkins line
    unit: cases
    sensor: {items: case, state: met, every: 1m}
  conformance-wanted:                # what is left: unmet and broken
    unit: cases
    sensor: {items: case, state: [unmet, broken], every: 1m}
auxiliaries:
  conformance-unaccounted:           # declared, but not yet in any state: never seen by a run
    unit: cases
    equation: stock.conformance-declared - stock.conformance-met - stock.conformance-wanted
flows:
  conformance-gained: {to: conformance-met, sensor: {items: case, entering: met, over: 1d}}
  conformance-lost:   {from: conformance-met, sensor: {items: case, leaving: met, over: 1d}}
goals:
  every-wish: {stock: conformance-wanted, hold: "<= 0"}
  nothing-lost: {flow: conformance-lost, hold: "<= 0"}
  every-case-run: {auxiliary: conformance-unaccounted, hold: "<= 0"}
```

What can be missing, and how each counts (lesson 3):

| Missing | Counts as |
|---|---|
| the list file, or a bad one | no reading of `conformance-declared` (step 1); its goal's input goes stale |
| a check's command, or its exit other than 0 or 1 | `broken`: wanted, never met |
| a check that hangs | killed at its timeout, `broken` |
| a case never run (new, or the run out of time) | not an item yet, so `conformance-unaccounted` is above 0 and `every-case-run` is off |
| a case taken off the list | `withdrawn` (step 5): neither met nor wanted |
| the runner refused an observation line (`ergostat/spec/engine.py:2305-2308`) | that case is not moved, so it shows as unaccounted or keeps its last state; the run is named on stderr |

## 3. The count as a stock, with its own sensor and history

Why a stock and not an auxiliary: the count keeps its value when nothing happens, and changes only when a case is
met or lost. Those are its two flows (`docs/SPEC.md:972-976`: "a quantity with memory … changes only through its
flows"). This is the same reading the image-squeeze demo gives its `capabilities` stock
(`examples/image-squeeze/benchmark.yaml:19-25`).

- **Its sensor** is the `items:` count, not the runner. So the count holds its last value while the runner is
  down, and is never set to 0 by a failed run.
- **Its history** is the stock's readings in the measurements store (`ergostat/store.py:600`), drawn in the causes
  strip like any stock's (`ergostat/series.py:52`): the Jenkins "passing tests" line, with the setpoint band of
  its goal. Each case's own history is its item's events: which run and commit met it, which lost it.
- **The stacked graph** (met, unmet, broken over time, the Jenkins test-result trend) is the item kind's states
  over time (`ergostat/series.py:342`), which the Items tab draws as a kind's cumulative flow diagram
  (`docs/DISCIPLINES.md:31`). No new chart and no new page.
- **Per list**: a stock per list where wanted, with `where: {list: diagrams}` on its sensor (`docs/SPEC.md:1743`,
  the `where` row).

## 4. How a loop's goal reads it

`every-wish` is off while any case is wanted. Its error is worked out from the count and the setpoint, and its `.off`
is set, at each pass (`ergostat/spec/engine.py:352-357`). A goal
that is always off is meant here: the wish list is open-ended, so the loop raising it is paced by its pool and the
AI budget, not by the goal turning off.

The loop, in a project of the owner's: an `ai` block that takes the unmet, asked cases, one at a time:

```yaml
blocks:
  build-a-wish:
    type: ai
    goal: every-wish
    takes: {kind: case, at: unmet, to: [met], where: {asked: true}}
    pool: 1
    prompt: prompts/build-a-wish.md
```

This uses only what leases already do (`docs/SPEC.md:2584-2620`): a run per item, held until the item moves on.
Here the item moves only when the next run of the list says `met`, so a run that claims done without meeting the
check is not counted.

For ergostat itself, the factory does not let an AI change main directly. Its loop asks for a **gap**, the same
way the code-health simplifier does: an `expr` block computes "wanted, and nothing in flight, and the AI budget not
spent" (`dev/model/code-health.yaml:143-152`, the budget at `:149`), and a program asks for one gap and records its
source (`dev/model/code-health.yaml:173-180`). Those gaps are then counted by their source
(`dev/model/code-health.yaml:132-136`). The gap's definition of done names the case's check as its acceptance.

`nothing-lost` is the regression signal: a met case that stops being met is a flow out of the stock, and its goal is
off for a day.

## 5. How it differs from the unit suite

| | Unit suite | Conformance list |
|---|---|---|
| What a case says | "this works, and must keep working" | "we wish this worked; does it yet?" |
| A failing case | a red build: the suite runs before every commit (`CLAUDE.md:63`), and a branch with a failing test is not done | expected, counted as unmet; the runner exits 0 |
| Where it lives | `tests/`, the only path pytest collects (`pyproject.toml:43-44`) | outside `tests/`, so the suite never collects a case |
| A case that cannot run | an error, red | `broken`, counted as wanted |
| Flaky cases | quarantined by hand, run beside the suite (`tests/quarantine.txt:1-2`) | none: a case that flips is two moves on its item, and shows as `gained` and `lost` |
| Its result | a return code, at the end of a run | events on items, a stock with a history, a goal |
| Who runs it | the implementor, the build step, the merge queue | the runner, as a sensor, on each new main |

The two meet at one point. Once a gap meets a case, that gap's acceptance test guards the feature in the unit
suite from then on. The case stays on the list and keeps counting. A regression then shows both as a red test and
as `conformance-lost`.

A name clash to know about: "conformance suite" already means something on main, a unit-suite file that holds every
storage backend to one interface (`ergostat/storage.py:4-5`, `tests/test_store_conformance.py:1-6`). Every one of its
cases must pass. The template and the item kind are named `conformance` and `case`, and the docs should say
"conformance list" each time, never "conformance suite", for the new thing.

## 6. A first list for ergostat

Chosen from what the repository already says it wants. The expected result of each case is **expected from reading
the code on main**: no case has been run, and the check commands named below do not exist yet (gap 2 writes and
runs them, and corrects any expectation that is wrong). Where a unit test already shows the feature works, the
check may run that test; it is named.

### diagrams (from `docs/proposals/diagram-options.md` and `docs/DISCIPLINES.md`)

The owner decided on 2026-11-16 not to start any new diagram yet (`docs/proposals/diagram-options.md:3-7`). So
this list's unmet cases are `asked: false`: counted, and not taken by the loop until the owner opens them. That is
the reversible choice: a field changed back, and no UI built in the meantime.

| Case | What the check does | Today | Why |
|---|---|---|---|
| `stock-and-flow` | `/graph?view=dynamics` on `examples/image-squeeze` returns a node for each stock and flow | met | `ergostat/web/server.py:478-491`, `ergostat/dynamics.py:219`; `tests/test_dynamics_view.py` |
| `block-diagram` | `/graph?view=blocks` returns a block per block, and a summing junction per goal served | met | `ergostat/web/server.py:469-474`, `ergostat/blockdiagram.py:1423`; `tests/test_blockdiagram.py` |
| `process-map` | `/graph?view=process` returns a node per state entered and a line per move seen | met | `ergostat/web/server.py:460-468`, `ergostat/process.py:1-5`, `:354`; `tests/test_process.py` |
| `service-map` | `/graph?view=map` returns an edge per pair of blocks the record links, each with a rate, failures and a median delay | unmet (`asked: false`) | no `map` view: `ergostat/web/server.py:460-478` serves process (and `wiring` as its alias), blocks and dynamics only; wanted first, `docs/proposals/diagram-options.md:59-64` |
| `sequence-diagram` | an item's page answers its chain as lifelines and ordered messages, from `causedby` | unmet (`asked: false`) | ◻ at `docs/DISCIPLINES.md:36`; wanted, `docs/proposals/diagram-options.md:65-68` |

Not on the list, and why (each with its line): the Petri net (the process map is preferred, built on the same data,
`docs/proposals/diagram-options.md:69-70`); event graphs, activity cycle and DEVS diagrams (argued against,
`:71-72`); flow charts and BPMN (against, `:73`). The causal loop diagram, signal-flow graph, SysML diagrams and
the item state machine are marked possible (`docs/DISCIPLINES.md:13`, `:16`, `:18`, `:19`), but nothing in the
repository asks for them. They are the owner's to add.

### model formats

| Case | What the check does | Today | Why |
|---|---|---|---|
| `ergostat-yaml` | `ergostat check` on each example's `ergostat.yaml` exits 0 | met | `ergostat/spec/load.py:171` |
| `ergostat-toml` | `ergostat convert` writes a model that compiles, for every old example | met | `ergostat/spec/convert.py:1-9`, `ergostat/cli/__init__.py:153`; `tests/test_spec_compile.py:183` |
| `served-model` | the remote API's model answer says `ergostat-model/1` and holds every stock | met | `ergostat/remote/serve.py:12`; `tests/test_remote.py` |
| `xmile-export` | the export of `examples/image-squeeze` parses as XMILE 1.0, with one `<stock>` per stock and one `<flow>` per flow, equations in XMILE's syntax | unmet | ◻ at `docs/DISCIPLINES.md:21`; recommended, `docs/research/sre-control-systems.md:1279-1280`; nothing under `ergostat/` names XMILE on main |
| `xmile-import` | a small XMILE file becomes a draft model whose stocks, flows, auxiliaries and causes' signs match | unmet | proposed as one-way, `docs/research/sre-control-systems.md:1281-1282`; not built |

Not on the list: Vensim `.mdl` (the research points to PySD for that, if ever wanted,
`docs/research/sre-control-systems.md:1250`), and outside event-log formats such as OCEL. The repository names
OCEL only as the method the Process view follows (`ergostat/process.py:3`), not as a file to read.

### discovery algorithms

| Case | What the check does | Today | Why |
|---|---|---|---|
| `prometheus-draft` | a fake Prometheus on 127.0.0.1 serving a gauge and a counter with one stem; the draft holds a stock and a flow into it | met | `ergostat/spec/discover.py:60`; `tests/test_spec_discover.py:61` |
| `unwritten-loop` | a record where an outflow follows its stock after a delay; `discover loops` proposes a goal and an external block | met | `ergostat/spec/discover.py:154`; `tests/test_spec_discover.py:40` |
| `process-fopdt` | a simulated first-order process with dead time; identification gives K and τ within 5% and 15% | met | `ergostat/control/ident.py:1-6`, `:310`; `tests/test_control.py:211-212` |
| `process-integrating` | a simulated integrator; identified as integrating, k within 10% | met | `ergostat/control/ident.py:5-6`; `tests/test_control.py:248` |
| `law-onoff`, `law-proportional`, `law-pi`, `law-stepper` | each law simulated; the law kept is the right family (four cases) | met | `ergostat/numbers/extlaw.py:26`; `tests/test_extlaw.py:106` |
| `law-changed` | a controller retuned halfway; said so, with at most 1 false alarm in 30 unchanged seeds | unmet | dropped for false alarms, `docs/GAPS.md:79-82` |
| `law-kubernetes-hpa` | `law: kubernetes-hpa` declared and tested against the record | unmet | asked for, `docs/GAPS.md:82-83` |
| `structure-from-residuals` | a model missing a stock; the residuals propose it | unmet | open, `docs/GAPS.md:293-294` |

The process map is a discovery algorithm too (a directly-follows graph, `ergostat/process.py:1-5`). It is counted
once, under diagrams.

### Expected totals

21 cases: 14 expected met (3 diagrams, 3 formats, 8 discovery), 7 expected unmet (2, 2 and 3; the 2 diagrams not
asked). So `conformance-met` would start near 14, and `every-wish` would be off with 7 wanted, 5 of them open to the
loop. These are expectations, not measurements.

## 7. The milestone

Four gaps, in order. Each builds only what its paragraph says.

1. **conformance-template**: the runner and the `use: conformance` template, for any project. The runner
   (`ergostat/library/run/conformance.py`) does what section 2 says: it reads and validates the list (names by the
   pattern, at most 500 cases, timeouts at most 10m, all checked when the list is read and again when a run starts),
   runs the cases one at a time in their own process groups and kills each group at its timeout, stops starting
   cases before the sensor's timeout, prints one observation per case run and one `case.withdrawn` per item the list
   dropped, prints the declared count, and exits 0 whatever the cases said. The template makes section 2's kind,
   stocks, auxiliary, flows and goals, and a stand-in list for a project that has none. Acceptance tests by name,
   among them: a hung check killed with its children; a check that exits 2 counted as broken; a removed case
   withdrawn and no longer counted; a list over 500 cases refused; a run that runs out of time names the cases it
   skipped and never counts them as met. SPEC §2a and the agent guide say how to use it.
2. **ergostat-conformance-list**: ergostat's own list, section 6, as `dev/conformance/*.yaml`, with its checks in
   `dev/conformance/checks/` (outside `tests/`, so the unit suite never collects them), and `use: conformance` in a
   new `dev/model/conformance.yaml`. Each check written, and each shown able to fail: a check expected met is run
   once against a copy with the feature broken, and seen unmet (lesson 9). The list run once on main, and its real
   counts recorded in the gap's record beside section 6's expectations, each difference explained. No loop yet: the
   count is only watched.
3. **conformance-loop**: the factory's loop that raises the count. An `expr` block, wanted and none in flight and
   the AI budget not spent, and a program that asks for one gap per unmet, asked case (pool 1, under a lock, as the
   simplifier does). Its gap's definition names the case's check as its acceptance and cites the case's `from`. The
   gaps asked for are counted by their source, and the case item is related to its gap. Tests: no gap asked while
   one is in flight, or while the budget is spent, or for a case with `asked: false`, or for a broken case (a
   broken check is fixed first, by hand).
4. **conformance-regressions**: what a lost case does. `nothing-lost` off asks the coordinator, through the measures'
   existing commander, as `code-health-off` does (`dev/model/code-health.yaml:163-172`). Whether the merge queue
   should also refuse a merge that loses a met case (as the image-squeeze rollout refuses a candidate that loses
   one, `examples/image-squeeze/benchmark.yaml:67-68`) is a question for the owner, asked in the gap's record and
   not built in it.

## Questions for the owner

- **Diagrams not asked.** Keep the diagram cases counted but closed to the loop (`asked: false`) until the user
  flows are decided? This proposal assumes yes.
- **The goal's form.** A goal of "nothing wanted" (`<= 0`, off as long as the list is open) or a floor that rises by
  hand (`>= 14`, then `>= 16`)? The first needs no edit as the list grows. The second makes the stock's goal band say
  where the owner wants it next. This proposal assumes the first.
- **Regressions.** Should a lost case only ask the coordinator (gap 4 as written), or also hold the merge queue?
- **Where the lists live.** In `dev/conformance/`, as factory material (this proposal), or beside the docs for human
  readers, as `docs/DISCIPLINES.md` is?
