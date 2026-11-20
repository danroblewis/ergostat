# `triggers2`: blocks started by an event type, without loops, scans or a way round advise

The gap from `docs/GAPS.md` (*Modelling*): **triggers on an event type**, a block started by an event type alone, not
only by a state change. Parked on `triggers` after two failed gates (`docs/roadmap/overnight/triggers.md`, *Where it
stopped*): an event trigger bypassed `mode: advise`; blocks triggering each other ran forever (a loop of five or more
escaped the 8-hop walk that looked for the block's own runs); and each hop's `Events.get` scanned the whole record.
This branch starts again from main and takes from `triggers` what held: the `on:` key, its compile, the run given the
event, its cause, the cursor and resume.

## Definition of done

A `program` or `ai` block written `on: {event: TYPE, where: {...}, emits: [TYPES]}` runs once for each recorded event
of that type (a type, a list, or a `prefix.*`) whose data matches `where`, one run at a time, in the record's order,
woken by the write (no clock of its own); its run is given the event (`"trigger": "event"`, `event`,
`ERGOSTAT_EVENT`) and its `agent.started` is caused by the event, so what it says names the event through the run.
**Loops are refused when the model is read:** `emits:` declares the event types its runs say; the trigger graph (an
edge from each triggered block to every triggered block whose `on:` one of its `emits:` types matches, `where:`
ignored, so the check over-approximates) is searched for cycles of any length, and a cycle is an error naming it
(`trigger-loop`: `a → b → c → a`), as is `on:` on ergostat's own types (`agent.*`, `block.*`, `trigger.*`,
`ergostat.*`) and `on:` beside `every:`, `cron:` or `takes:`. A triggered run's event lines of a type it did not
declare are refused (`agent.refused`), so the graph check holds for what it prints. **What still loops at run time is
stopped by a budget carried on the record, never by a scan:** each triggered run's `agent.started` carries its
`depth` (one more than the run that caused its event, found by an exact, indexed id lookup of at most four causes)
and its `chain` of blocks; an event at depth 8 or more starts nothing and is recorded once (`trigger.stopped`, with
the chain), so an undeclared loop (`$ERGOSTAT_CMD event --add` from a run) of any length runs at most 8 hops.
**`mode: advise` holds on every path:** a triggered block in advise mode asks before each run (`block.advised`,
caused by the event, naming it), its events wait behind the ask, and it runs that event only when approved
(`block.approved`); denied (`block.denied`), it goes on to the next. **The cost of a hop does not grow with the
record:** event lookups by id are exact and indexed (`Events.get` tries the exact id before a prefix), a `prefix.*`
type is read as an indexed range, and one look reads at most a window of new events. SPEC §9.3, the agent guide, the
schema, `explain` and GAPS say so; every suite passes.

## Acceptance tests

- `tests/test_triggers2.py`
  - `test_a_block_on_an_event_type_runs_once_per_matching_event`
  - `test_its_run_and_what_it_says_are_caused_by_the_event`
  - `test_where_narrows_and_undeclared_lines_are_refused`
  - `test_on_is_refused_beside_every_cron_or_takes_and_on_ergostats_own_types`
  - `test_a_declared_loop_is_refused_by_check[2]`, `[5]`, `[9]`
  - `test_an_undeclared_loop_stops_at_the_depth_budget[2]`, `[5]`, `[9]`
  - `test_advise_asks_before_each_triggered_run`
  - `test_a_hop_costs_the_same_at_10k_events`
  - `test_started_again_it_resumes_after_its_last_event`

## Size budget

500 net lines of code outside `tests/` and `docs/`.
