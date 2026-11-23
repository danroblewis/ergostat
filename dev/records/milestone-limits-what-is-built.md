# Workers take only the work of active milestones

## What done means

- `milestones.py` keeps a derived field `waits_on_milestone` on each unfinished gap, the same way `waits_on_parked` works: empty when the gap's milestone is active, or the gap is pulled forward, or enforcement is off; otherwise the name of the milestone it waits for.
- The planner and the implementor take only gaps with `waits_on_milestone` empty (their `takes: where:`). Review and the merge queue are not limited: work already built keeps landing.
- `pull` is the owner's exception: a pulled gap in an inactive milestone is taken as if its milestone were active.
- A gap may not depend on a gap in a milestone that can only finish later, since both would wait forever. `assign` and `depends` refuse that unless the needed gap is pulled, and `status` lists any that exist.
- Enforcement is off until `[milestones] enforce = true`, so this can land before the backlog has been assigned. With it off nothing about dispatch changes.

## Tests

Enforcement off changes nothing. With it on: an inactive milestone's gap is held, a pulled one is taken, an active one is taken, review and the queue are unaffected, and the dependency refusal holds.
