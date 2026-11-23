# Workers take only the work of active milestones

## What done means

- `milestones.py` keeps a derived field `waits_on_milestone` on each unfinished gap, the same way `waits_on_parked` works: empty when the gap's milestone is active, or the gap is pulled forward, or enforcement is off; otherwise the name of the milestone it waits for.
- The planner and the implementor take only gaps with `waits_on_milestone` empty (their `takes: where:`). Review and the merge queue are not limited: work already built keeps landing.
- `pull` is the owner's exception: a pulled gap in an inactive milestone is taken as if its milestone were active.
- A gap may not depend on a gap in a milestone that can only finish later, since both would wait forever. `assign` and `depends` refuse that unless the needed gap is pulled, and `status` lists any that exist.
- Enforcement is off until `[milestones] enforce = true`, so this can land before the backlog has been assigned. With it off nothing about dispatch changes.

## Tests

Enforcement off changes nothing. With it on: an inactive milestone's gap is held, a pulled one is taken, an active one is taken, review and the queue are unaffected, and the dependency refusal holds.

## Where it stopped

Built, with one point of done not built as written (the pull exception to the dependency refusal, below). Nobody was
there to ask, so each open question went the more reversible way; each is listed here.

- **The dependency refusal is not lifted for a pulled gap (done item 4 says it is).** A gap A in milestone MA that
  depends on a gap B in milestone MB, where MB depends on MA (at any depth), is already a cycle in the precedence graph
  the implementor's `unblocked` take reads (ergostat/precedence.py treats a milestone as a summary of its gaps). That
  take never takes an item on a cycle, and it knows nothing of `pulled`. So a pulled B would still never be taken, and
  A and B would wait forever anyway. Allowing the link for a pulled B would fail open (lesson 3). `assign` and `depends`
  therefore refuse it pulled or not. The message names the cycle and the later-milestone dependency, and adds
  "pulling ... does not lift it". Refusing is the reversible choice: a refused link can be made later, but a recorded
  link would hold both gaps. Lifting it needs the engine's take to drop a pulled member's summary edge. That is an
  engine change outside this gap, and the owner should decide whether a gap of its own should make it.
- **A gap with no milestone, under enforcement, is held** (`waits_on_milestone: unassigned`), and so is one whose
  milestone is an old free-text label (the label as written) or an id with no milestone in the record. A missing
  milestone counts as not active (lesson 3). Enforcement stays off until the backlog is assigned (done item 5).
- **A sub-gap of a split with no milestone of its own takes its nearest ancestor's milestone**, and is pulled when it or
  an ancestor up to that one is pulled. Without this, every sub-gap a planner splits off would be held as `unassigned`
  once enforcement is on.
- **The implementor's `fix` state is held too**, because its `takes: where` covers every state it takes from, as done
  item 2 says. A gap can only reach `fix` in an inactive milestone if it was unpulled or reassigned after it was built.
- `[milestones] enforce` that is not true or false is refused (ValueError), never read as either. Turning it off clears
  every gap's field on the next pass. The field is written by a new no-state event, `gap.milestone-held`.
- Tests (tests/test_milestones.py, all 39 pass; each new one was seen to fail with the code it guards broken):
  `test_the_planner_and_the_implementor_ask_waits_on_milestone_empty_and_review_and_the_queue_do_not`,
  `test_enforcement_off_changes_nothing`,
  `test_with_enforcement_an_inactive_milestones_gap_is_held_and_an_active_ones_is_taken`,
  `test_a_pulled_gap_in_an_inactive_milestone_is_taken_as_if_it_were_active`,
  `test_review_and_the_queue_are_not_held_by_an_inactive_milestone`,
  `test_a_dependency_on_a_gap_of_a_milestone_finishing_later_is_refused`,
  `test_an_enforce_not_true_or_false_is_refused`. tests/test_factory_knowledge.py pinned the planner's `where`
  exactly and was updated to the new value. Not run here: the whole unit suite and the four browser files (left to the
  factory, as the brief asks). No page is changed.
- **The build step (round 1) stopped with no failure named.** Its log ends after 48 of the 138 tests, with no FAILED
  line, no pytest summary and no suite_watch line. That reads as the run killed from outside, not as a failing test.
  I could not reproduce it, because this session may only run tests serially through `scripts/named_tests.py`.
  Serially, both files pass when run together: 138 passed in 441 s. Alone, test_milestones.py passes 39 in 124 s and
  test_factory_knowledge.py passes 99 in 417 s. A `read()` of the whole model costs 61 s, nearly all of it findings,
  and its peak RSS is 55 MB. So memory is not the cause.
  The test this gap changed in test_factory_knowledge.py now compiles the model without its findings, as the `blocks`
  fixture already does. That test still takes 63 s on its own, so the change saves little. The other whole-model reads
  belong to other gaps' tests and are left alone (lesson 13).
  If the build stops the same way again, look at the slot or the container's limits. Nothing these tests do points
  there, but nothing in them hangs either.
- **Round 2: no code changed.** No review findings came with this round, so I only checked the branch again. main
  (ead497d1) is still its merge base, so there was nothing to merge. Ruff is clean. tests/test_milestones.py passes
  39 in 125 s (serially), and the changed test
  `test_factory_knowledge.py::test_the_planner_never_takes_a_continued_gap` passes in 63 s. I could not look into
  why the round-1 build stopped. The build's suite container has `--cpus 4 --memory 12g` (dev/bin/agents.py LIMITS)
  and runs `-n 8`. To measure a whole-model `read()`'s time and RSS outside pytest, I tried
  `timeout 300 uv run python /tmp/rd.py`, and this session refused that command. So whether the container's memory
  limit is reached is still unmeasured. If the build stops again with no FAILED line and no suite_watch line, look at
  that container's OOM kills (`docker inspect` OOMKilled, or the VM's kernel log) first.
- **Round 2's build: one `F` at about the 64th of 138 tests, then the log ends.** It ends with no FAILED line, no
  pytest summary and no suite_watch JSON line, the same cut-off end as round 1, so the test that failed is not named
  anywhere I can read. I could not make it fail. Run serially through `scripts/named_tests.py`, test_milestones.py
  passes alone (39 in 124 s), and the two files pass together with test_milestones.py first (138 in 423 s), the
  reverse of round 1's order, so neither file leaves state that breaks the other. Timed with a throwaway test file
  (deleted, never committed): compiling the whole model, which is all that this gap's `blocks` fixture and its
  test_factory_knowledge.py change do, takes 0.1 s. A `read()` with findings takes 61 s, and `read(extremes=False)`
  takes 0.6 s. So this gap's tests add almost no load. The 61 s reads are main's tests (test_milestones.py's
  `test_the_factory_model_declares_milestones`, and five in test_factory_knowledge.py). No code is changed this
  round, since no failure points at it (lesson 13: an unnamed failure is not fixed by guessing).
  What I could not check: the build's container. `--dist worksteal -n 8` runs on 4 CPUs, and every suite
  container shares `suite_cpuset = "8-11"` with the other slots. Under that load a subprocess `timeout=60`/`120` in
  test_factory_knowledge.py, or the `t.join(30)` of the lock test, could run out, and an OOM kill or an outer kill
  would cut the log as it is cut here. This session refused `uv pip list`, a run of a /tmp script, a background run
  of the two files, and a heredoc append to this file, so xdist could not be run here. Next step: read that run's
  log on the host for the worker crash or FAILED line pytest never printed, or run the two files under `-n 8` in
  that container.
