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

## Where it stopped

Built in full in round 1: `docs/proposals/regression-guarantees.md` (254 lines; no code changed). Nothing is left of
this definition. Choices taken without the owner, each the most reversible (the proposal's section 8): proposed, not
built; one new model file (`dev/model/guarantees.yaml`) in the milestone rather than edits across the existing ones;
every new loop closed by a person or an existing program; holding the queue while main is red left as a separate
question to the owner; users get an opt-in template, never a default; the setpoints are placeholders for the owner.

Round 2 (fix): the one blocking finding of round 1 is answered in the proposal. A `main-broken` flake now has a way
out: gap 2 adds `flake.main-fixed`, written after a landing when the test passes alone twice on the new main (checked
under the item's lock against the sha it broke on; a skipped or unreadable run leaves it broken), and stops
`flake.seen` from moving a `main-broken` item into the flakes. A person's `manage.py flake-fixed` clears what no run
can, such as a deleted test. Gap 5 now depends on gap 2, and its queue hold lifts when the stock empties.
`main-repair-hours` runs from `main-broken` to `main-fixed`, not to the intervention's hand-marked `remedied`. Gap 7's
goal is now `fixes-hold`, a 14-day window on the flow `fixes-regressed`, because a denied revert keeps the stock
`regressed-fixes` up for good (docs/SPEC.md:6293). Sections 3, 4, 6a, 6b, 7 and 8 changed; still no code.
