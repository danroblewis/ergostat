# Milestones: the kind and its lifecycle

The factory moves to development by milestones (the owner, 2026-11-22). A milestone is a group of gaps that is finished together.

## What done means

- A new item kind `milestone` in the factory's model, with the states `waiting`, `active` and `completed`. `completed` is final: no event moves a milestone out of it.
- A milestone may depend on other milestones (`depends_on: milestone`, a precedence relation). A gap names its milestone by a `milestone` relation declared with `group: true`, so the Items page's Graph can group by it. The existing free-text `milestone` field on gaps holds names of the 21 old labels; keep those values readable until the coordinator has moved them.
- A small block, `dev/bin/milestones.py`, runs every minute and applies these rules:
  - A `waiting` milestone becomes `active` when every milestone it depends on is `completed`, while fewer than 3 milestones are active. Past that limit the rest wait in rank order. The limit is read from `[milestones] active_max` (default 3).
  - An `active` milestone with at least one gap, all of them `merged` or `closed`, becomes `completed`. A `parked` gap keeps it open. An empty milestone never completes.
  - A milestone marked `upkeep: true` is for the factory's own repairs: it is always active and does not count toward the limit. It completes at the end of its cycle (`[milestones] upkeep_days`, default 7), its unfinished gaps move to a new upkeep milestone, and that one becomes active.
- `milestones.py` has the coordinator's commands: `add`, `depends`, `assign GAP MILESTONE`, `pull GAP`, `unpull GAP` and `status`. `assign` refuses a completed milestone. `depends` refuses a cycle.
- `status` prints each milestone with its state, what it waits on, and its gaps by state.

Do not change which gaps the implementor takes: that is `milestone-limits-what-is-built`. Do not add a page or panel.

## Tests

Each rule above: activation, the limit, completion, a parked gap holding it open, an empty one, no way out of `completed`, the upkeep cycle, and the refusals.
