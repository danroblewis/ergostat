# Every gap belongs to a milestone

## What done means

- A gap requested without a milestone joins the current upkeep milestone if the factory filed it itself (repairs, lessons, the pipeline manager). Otherwise it joins the first active milestone. It is never left without one once `[milestones] enforce` is on.
- A sub-gap of a split and a continued gap keep their parent's milestone. A continued gap whose milestone has completed joins the current upkeep milestone.
- A gap cannot be assigned to a completed milestone by any path.
- `milestones.py status` reports the number of unfinished gaps with no milestone, which must be 0 with enforcement on.

## Tests

Each path above: a request, a factory-filed gap, a split, a continuation, and a refusal on a completed milestone.
