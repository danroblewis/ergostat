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
