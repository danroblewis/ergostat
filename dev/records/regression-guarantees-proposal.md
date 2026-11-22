# regression-guarantees-proposal: a reviewed proposal for encoding ergostat's regression guarantees in its own feedback model

depends-on: []

The owner, 2026-11-21: before ergostat is given to people, encode our regression guarantees in the feedback model itself. Today they live in tests, the merge gate (`dev/bin/queue.py`), the review lessons (`dev/knowledge/review-lessons.md`) and quarantine (`tests/quarantine.txt`), none of which the model shows as stocks, goals or loops.

## Definition of done
1. `docs/proposals/regression-guarantees.md`, written for the owner: the guarantees ergostat makes today (listed from SPEC, the gates and the tests), how each becomes a measured stock or goal in a model (passing counts, escapes, flake rate, time to repair), which loops act on each when it is off, and how a guarantee breaking shows on the diagrams.
2. How this applies to ergostat's own factory model (`ergostat.yaml`, `dev/model/`) first, and then to any user's model.
3. A milestone: an ordered list of gaps, each with a one-paragraph definition.
4. Every claim about today's code cites file:line on main. No code changes.

## Files to touch
`docs/proposals/regression-guarantees.md` only.

## Size budget
0 lines of code; the proposal under 500 lines.
