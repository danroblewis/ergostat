# Every gap belongs to a milestone

## What done means

- A gap requested without a milestone joins the current upkeep milestone if the factory filed it itself (repairs, lessons, the pipeline manager). Otherwise it joins the first active milestone. It is never left without one once `[milestones] enforce` is on.
- A sub-gap of a split and a continued gap keep their parent's milestone. A continued gap whose milestone has completed joins the current upkeep milestone.
- A gap cannot be assigned to a completed milestone by any path.
- `milestones.py status` reports the number of unfinished gaps with no milestone, which must be 0 with enforcement on.

## Tests

Each path above: a request, a factory-filed gap, a split, a continuation, and a refusal on a completed milestone.

## Where it stopped

Built, in `dev/bin/milestones.py` (about 105 net lines; the budget is 600), with the tests in `tests/test_milestones.py`
(`test_a_requested_gap_joins_the_first_active_milestone`, `test_a_gap_the_factory_filed_joins_the_current_upkeep_milestone`,
`test_a_sub_gap_of_a_split_keeps_its_parents_milestone`,
`test_a_continued_gap_keeps_its_parents_milestone_or_joins_upkeep_once_it_completed`,
`test_no_path_assigns_a_completed_milestone`, `test_with_no_milestone_to_go_to_a_gap_is_left_and_counted`,
`test_enforce_is_true_or_false`). Decisions taken alone, with no one to ask (each the most reversible I could see):

- Gaps come from many paths (intake, request.py, manage.py, the planner, the groomer, the join, the simplifier, live.py,
  and raw `ergostat event --add`), so one place places them all: the milestones pass (every minute), under
  run/milestones.lock with its other writes. So "never left without one" means placed by the next pass, not in the
  request's own event. `status` counts any gap between the two.
- `[milestones] enforce` defaults to false, and dev/factory.toml sets it false. When it is on, the first pass moves
  every unfinished gap with an old free-text label (kept in `milestone_was`), and events cannot be taken back, so the
  owner turns it on.
- "Filed by the factory" is an allowlist: `source: simplifier`, `requested_by: pipeline-manager` (manage.py file-gap
  from the manager's run), and `gap/knowledge-*` (lessons once filed as gaps). I found no repair path that files gaps
  of its own. Any other gap, the coordinator's included, counts as a request.
- "The current upkeep milestone" is the active upkeep one whose pinned `upkeep_ends` is latest (not the time an event
  was stamped). "The first active milestone" is the first active non-upkeep one by rank. With none active, a request
  joins the upkeep one. With no milestone to go to at all, the gap is left and counted.
- A gap in a completed milestone (written by a raw event) is moved out by the pass when enforcement is on, to its
  parent's live milestone or else the upkeep one. An upkeep cycle no longer carries its gaps to a successor that has
  completed: it makes a new one instead (this was a path that could assign a completed milestone). A raw event can
  still write the field. The engine does not refuse it, and the next pass undoes it.
