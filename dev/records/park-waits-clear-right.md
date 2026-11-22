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

### After the fast suites (round 1)

The factory's `unit` run stopped silently at 54%, partway through a progress line. It named no failed test and wrote
no suite_watch exit line. That matches the silent deaths recorded for the-module-map-is-read-and (28%, 74%, 90%), and
is not a failure this branch can point to. The change starts no thread or process beyond short git calls. Its one new
lock (`continue.lock` in `classify()`) is taken only by `parks.py resume` and is never held across a call that takes
it again. Every file that reaches the changed code was run again here, one at a time, and passed:
tests/test_factory.py (130 passed, 2 skipped), test_intake.py, test_backlog.py and test_factory_manager.py (72
passed), and test_factory_knowledge.py and test_factory_join.py (81 passed). No code was changed. The whole unit suite
was not run here. It needs another run under suite_watch.py, and a test it names would be the thing to fix.

### Round 2

Main (b4639301) was merged in. It conflicted only in tests/test_factory.py, where both sides had added a section at
the same place: this branch's four acceptance tests and main's pool-full-keeps-its-rank tests. Both were kept whole.
The findings of review park-waits-clear-right-1, each answered:

- *Not run by the reviewer (Bash refused).* Run here after the merge: tests/test_factory.py (139 passed, 2 skipped),
  test_factory_knowledge.py, test_factory_manager.py, test_intake.py and test_factory_join.py (142 passed together),
  and test_intake.py (21 passed) again after the last change. `ruff check ergostat tests scripts` is clean.
- *lesson-7, the unit run stopped at 54%.* Still not run here: the whole unit suite and the four browser files are the
  factory's to run under suite_watch.py. A test it names is this branch's to fix.
- *README: expect many `parked` triggers once.* dev/README.md now says the first session after this lands carries one
  `parked` trigger per old park classified `unknown`, once.
- *intake: a stale `unfetched` when another gap holds the branch.* Fixed. When continued() finds the branch held, it now
  clears `unfetched` before it returns False (dev/bin/intake.py, +2 lines). The gap waits on the holder, and the watch
  no longer raises the old cause. test_an_unfetchable_continue_raises_a_situation now covers this window. With the
  clear removed, the test was seen to fail ("'the checkout does not have' is None").

Size: 79 net lines in dev/bin (77 + 2), within the 90.

### Round 3

The findings of review park-waits-clear-right-2, each answered:

- *Blocking: classify() raised old continued parks.* Fixed in two places, each the smallest change. classify() now
  skips a park that has `resumed_as` and writes nothing on it (dev/bin/parks.py). Its work goes on in the
  continuation, so a kind can still be written on it later if wanted. The watch's `unknown` age bypass now leaves out
  a park with `resumed_as` (dev/bin/watch.py). That covers a park already classified `unknown` by an earlier pass and
  continued after that. A young continued park is raised within `parked_within_hours` as before this branch.
  test_existing_parks_are_classified_and_deferred_ones_left_alone now has two such old parks, each with a merged
  continuation: one unkinded and one already `unknown`. Neither is classified or raised. Each guard was removed on its
  own and the test failed: a fifth `gap.measured` without the classify skip, and `gap/was-unknown` raised without the
  watch's.
- *intake.py:140-142, a `continues` name that fails the branch rule was said only on stderr.* Fixed. It now records
  `unfetched: "fails the branch rule"`, once per change, and the watch raises it like the other two causes. Such a gap
  never becomes valid, so nothing clears the cause. It stays open, as before, and the manager can close it.
  test_an_unfetchable_continue_raises_a_situation covers this with `../warm`. With the record removed, the test was
  seen to fail (KeyError 'unfetched'). +2 lines.
- *Not run by the reviewer (Bash refused).* Run here: tests/test_factory.py (139 passed, 2 skipped),
  test_factory_manager.py (33 passed), test_factory_knowledge.py (75 passed) and test_intake.py (21 passed), each
  on its own. `ruff check ergostat tests scripts` is clean. test_factory_join.py was not run again this round. The
  command that ran three files in one shell loop was refused, so each file was run alone.
- *lesson-7, the whole unit suite and the four browser files.* Still not run here. They are the factory's to run
  under suite_watch.py after origin/main is merged in. This clone has no origin/main.

dev/README.md says continued parks are left alone. Size: 82 net lines in dev/bin (79 + 1 parks.py docstring + 0
for the changed condition, +1 watch.py, +2 intake.py, counting only lines added less lines removed), within the 90.

### After the fast suites (round 3)

The factory's `unit` run stopped after 13 dots, before its first progress mark. It named no test and wrote no
suite_watch exit line. suite_watch.py prints that line on every exit it controls, its own kills included, so the run
was stopped from outside the watchdog. That is the same silent stop as round 1 (54%) and the other branches recorded
there. No code was changed, because there is no failure to fix. Run here: tests/test_factory.py under the unit
suite's own `-n 8 --dist worksteal` (139 passed, 2 skipped, in 601 s). The continue/park/wait subset was run alone
with `--durations` (29 passed). Its slowest tests are test_fix_then_park (63 s) and
test_triage_waiting_on_load_does_not_block_the_queue (36 s). Neither reaches parks.py, intake.py or watch.py. Each
of this branch's tests takes about 2 s. Refused: a shell reading the container's cgroup memory and pids limits, and
`git worktree add -q /tmp/mainwt main` (to time those two tests on main). So whether this container is slow or short of
memory on main too was not checked. The whole unit suite still needs a run that finishes under suite_watch.py. A test
it names would be this branch's to fix.

### After the fast suites (round 3, second run)

The factory's `unit` run stopped again after 22 dots, before its first progress mark. It named no test and wrote no
suite_watch exit line. No code was changed, because there is no failure to fix. By reading only: the code this branch
adds starts no thread or process beyond short git calls, its continuation walk is bounded (HOPS = 20), and classify()
takes continue.lock once, without calling anything that takes it again. Refused this round: the first shell command,
`git log --oneline -4 --stat | head -40 && sed -n '/### Round 3/,$p' dev/records/park-waits-clear-right.md`. Every
shell command was refused after that, so no test, ruff or commit was run, and this section is left uncommitted in the
working tree. It needs a commit and a whole unit run under suite_watch.py. A test that run names would be this branch's
to fix.
