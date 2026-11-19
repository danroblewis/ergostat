# `causes-join`: causes for scheduled runs, built-in join

Split from `triggers` by the kill rule (event triggers failed their gate twice; they are parked on `triggers`). Two
gaps from `docs/GAPS.md` (*Modelling*):

1. **A cause for a scheduled run's events**: a block on `every:` runs caused by nothing, so a sweep that opens
   sub-items draws no fan-out in the Process view.
2. **Built-in join**: move a parent item once all its children reach a state, as a rule on the kind over its
   relations.

## Definition of done

A scheduled run (`every:`, `cron:`) needs no new event: its `agent.started` is the run, and the events it prints cite
it (`causedby`); the Process view follows a cause up to a scheduled run and draws the block's schedule as a source (a
frame of schedules, one node per block, with how often), with the dashed fan-out lines to what its runs did, and its
items filterable (`caused=ergostat.schedule:BLOCK>A`). A kind may declare `join:` (a rule or a list),
`{children: REL, all: STATE(s), to: STATE}` or `any:` in place of `all:`: on each move of an item of a kind whose
relation `REL` names the parent kind, read from the item index, the parent is moved to `to` (an
`ergostat.item.joined` event, caused by the child's move) when all (or any) of its children are in those states and
the parent is in a state before `to`; folded only forward; a side state before `to` is a `check` finding; the move
counts like any other (`entering`). `examples/roadmap` drops `bin/epics.py` and its block for two join rules and
behaves as before; `demo_check` fails a demo whose joins moved nothing. SPEC (§5b, §5a), the agent guide and GAPS say
so; every suite passes.

## Acceptance tests

- `tests/test_process.py`
  - `test_a_scheduled_runs_events_fan_out_from_its_schedule`
  - `test_a_real_scheduled_runs_events_cite_it`
- `tests/test_join.py`
  - `test_a_parent_moves_once_all_its_children_reach_the_state`
  - `test_any_moves_it_on_the_first_child_and_never_back`
  - `test_the_parents_move_is_counted_entering`
  - `test_a_join_is_checked`
  - `test_joined_folds_only_forward_and_a_side_state_before_it_is_said`
- `scripts/demo_check.py roadmap` (fails unless epics are moved by the join)

## Size budget

600 net lines of code outside `tests/` and `docs/`.
