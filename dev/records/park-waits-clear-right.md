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

## Where it stopped

Built in round 1. Nothing the definition asks for is left. The code is 77 net lines in `dev/bin` (parks.py +68,
intake.py +4, watch.py +5). With dev/README.md, dev/prompts/pipeline_manager.md and dev/model/manager.yaml it is 86.
Nobody was there to ask, so the implementor made these choices, each the most reversible one it saw:

- **What "on pushed main" means.** A gap's work is on pushed main when the gap is `merged` and its `main_sha` (the
  queue's `gap.merged`) is an ancestor of the checkout's `refs/remotes/<remote>/<base>`. The queue's push and the
  upgrader's fetch move that ref. The resumer does no fetch of its own, so a stale ref only delays a resume. A gap
  with no `main_sha`, a sha that is not found, or a ref that cannot be read has not cleared (lesson-3). A
  `{"commits": [...]}` wait is now checked against the same pushed ref. It used to be checked against the drop's
  local main.
- **Through its continuation.** When the gap waited on is not on pushed main, its `resumed_as` is followed, at most
  20 hops (a hard ceiling, lesson-4). A split resumed as itself ends the walk. The resume says which gap landed
  ("gap/X merged as gap/X-continued, on origin/main"). A `closed` gap never clears a wait. Such a park raises
  `waiting` after `park_wait_hours`, as before.
- **Classifying the old parks.** `parks.py resume` first runs `classify()` on each pass, under the continue lock,
  over parked gaps with no `parked_for`. A park it classifies gets `parked_for`, so a second pass finds nothing to
  do. That is what "once" means here. The rules:
  - `kill-rule`, when the park was made by the implementor, plan-lint, merge-queue, dead-letters, join-judge or
    `queue run N`. These are the callers that now pass `kind="kill-rule"`.
  - `waits_on {"gap": Y}`, when the gap's branch in the drop has exactly one merge, in `<base>..branch`, whose subject
    is "Merge branch 'factory/NAME'". Y is the one gap with that branch that is not a continuation. This is the
    carried-merge park that motivated the gap.
  - `unknown` (added to KINDS) for everything else, a reviewer's park included. The watch now raises `parked` for an
    `unknown` park whatever its age, so it goes to the pipeline manager. The fingerprint makes that happen once.
  - Left alone, with nothing written: parks with `deferred` or `cancelled` set, and parks made by `plan-review` or
    `pipeline-manager` (today's code calls those cancelled and deferred). Writing a kind onto them is easy to add
    later and hard to take back.
- **Unfetchable continues.** When the checkout lacks the branch or the fetch into the drop fails, intake records
  `unfetched` on the gap with `gap.measured`, once per change, and clears it once the branch is fetched. The watch
  raises an `unfetched` trigger for an open gap that carries it. The fingerprint includes the cause, so a new cause
  is raised again. The stderr wording is unchanged, because tests/test_factory_knowledge.py checks it.
- **Tests changed.** In `test_a_park_waiting_on_a_gap_is_resumed_when_it_merges`, the merged gap now has a pushed
  `main_sha`, and the cleared text says where. In `test_a_split_park_is_resumed_when_its_stopped_sub_gaps_are`, the
  stopped sub-gap now has a kind, so classify leaves it alone.

Each acceptance test was broken on purpose and seen to fail: continuations not followed; the base checked instead
of the pushed ref; the coordinators' exclusion removed; the watch's `unknown` age bypass removed; the `unfetched`
trigger removed. Run here, one file at a time: tests/test_factory.py (130 passed, 2 skipped), test_factory_manager.py
(32 passed) and test_factory_knowledge.py (75 passed), with `ruff check ergostat tests scripts` clean. After the last
wording change only the continue/park/wait subset of test_factory.py was run again (28 passed). Not run here: the
whole unit suite and the four browser files under suite_watch.py (the factory runs those). This clone has no
origin/main; local `main` is an ancestor of HEAD. Not tested: the race between classify and a new park of the same
id. A parked gap cannot be parked again without leaving `parked`, and classify holds the continue lock.
