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

Round 3 (fix): both findings of round 2 are answered in the proposal, still with no code. (1) Section 2's tables now
give file:line for each test: F8 cites tests/test_factory.py:484, :947 and :982, and says plainly that no test parks a
gap on `build_hours` (dev/bin/implement.py:190-192). F12 cites dev/bin/knowledge.py:268-272 and
tests/test_factory_knowledge.py:1373 and :1402. U2 cites tests/test_claims.py:234 and :217. U3 cites
tests/test_repair_verify.py:101, :117 and :227. U5 cites tests/test_runner_and_state.py:78 and :114 for residuals, and
says that no test checks that an empty install runs nothing. (2) Section 6a item 3 and gap 1 now say the queue keeps
`rc`, `seconds` and, for the browser suite only, a `skipped` count (dev/bin/queue.py:104-105).

Round 4 (fix): round 3 found two things, answered here, still with no code. (1) Blocking: the repair clock.
Section 4's `main-repair-hours` now runs from the first `flake.main-broken` on the item, by `seq`, since it was made or
last left `fixed`. It says why: dev/bin/onmain.py:92-94 writes a fresh `main_broken_at` each time a later gap hits the
same failure. Gap 2 has a new bullet. The writer re-reads the item under its lock. For an item already in
`main-broken`, it moves only `main`, and it sets `main_broken_at` and a new `main_broken_seq` only when the item
enters the state. Gap 2's acceptance adds a test: a second `main-broken` on a later main keeps the first start and
moves `main`. The remake clears `main_broken_seq` too. Round 3's record said "both findings of round 2", but the
review counts three, and this clock finding was the one left unanswered (lesson 12). (2) Not blocking: the reviewer could not run
anything and did not confirm tests/test_factory.py:947, tests/test_factory_knowledge.py:1402, tests/test_claims.py:217
or tests/test_runner_and_state.py:114. Each was re-read in this round, and each is the `def` of the test the
proposal names there. Nothing was run: the proposal is docs only, and the Bash command used to batch-check those
citations was refused, so they were read one by one instead.
