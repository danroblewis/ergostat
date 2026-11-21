# park-waits-clear-right: A park's wait clears when its work is really on main

depends-on: []

Audit 2026-11-21 of `park-owns-resume`: a wait on a gap that was continued never clears, because the original stays parked (3 parked gaps already have a merged continuation). A gap merged locally but not pushed counts as cleared. None of the 92 existing parks has a kind, so the parks that motivated the gap are not resumed. A continued gap whose branch cannot be fetched is only said on stderr.

## Definition of done
- A wait clears when the named work is on pushed main, through its continuation if it has one, and not before.
- Existing parks are classified once by a program: unknown stays unknown and goes to the pipeline manager; `deferred` and `cancelled` are left alone.
- A continued gap that cannot be fetched raises a situation.

## Files to touch
`dev/bin/park.py` or wherever the resume lives, `dev/bin/watch.py`, `dev/bin/intake.py`, `tests/test_factory.py`.

## Risks
- lesson-3: an unreadable condition never counts as cleared.

## Acceptance tests
- `tests/test_factory.py::test_a_wait_on_a_continued_gap_clears_when_the_continuation_lands`
- `tests/test_factory.py::test_a_local_unpushed_merge_does_not_clear_a_wait`
- `tests/test_factory.py::test_existing_parks_are_classified_and_deferred_ones_left_alone`
- `tests/test_factory.py::test_an_unfetchable_continue_raises_a_situation`

## Size budget
90 net lines of code outside `tests/` and `docs/`.
