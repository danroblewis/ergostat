# merge-pipeline-stacks-merged-forward: When a stacked gap's base moves, the new base is merged forward into it; a conflict goes back to its implementor

depends-on: [merge-pipeline-stacked-gap-builds-on-its-base]

## Problem
A base can change after its descendant started. It may go back to fix and be approved at a new head, or triage may send it back and a fix round add commits. The descendant still holds the old reviewed sha. The queue then refuses it, or (stacks-land-bottom-up) brings in a base whose reviewed head the descendant does not hold. Nothing carries the base's new commits forward. Rebasing or squashing would discard the review history, so the owner's direction is to merge them forward.

## Change
A new program, dev/bin/stack.py, run as a block stack-forward in dev/model/building.yaml (every 5m, commanded by a sensor counting stale stacks). For each gap with stacked_on whose base's reviewed head has moved and is approved again (or whose base has landed, when there is nothing to do but update stacked_on):
- if the gap is leased, building or in review, skip it. The next implementor round merges the base itself.
- otherwise merge the new base head into the gap's branch in a scratch clone of the drop, `--no-ff`, by the factory (never a rebase or a squash), and move the drop's branch from its old tip only (update-ref old value).
- clean, on an approved gap: record the new reviewed_head with `reviewed_by: stack-forward` and the new stacked_on. The merge brings only reviewed commits, and the queue tests the result.
- clean, on a built or fix gap: move the branch, and leave the next round or review to run.
- conflict: abort and send the gap back to fix with the files (`stack_conflict`), uncounted as a failed gate. implement.py's next round merges the base again and hands the conflict to the session (its conflict brief, implement.py:147-151).
Descendants are processed bottom-up, so a stack of three moves in one pass.

## Definition of done
1. Base A re-approved at a new head: an approved descendant B gets a merge commit of A's new head, keeps approved, and its reviewed_head and stacked_on are updated.
2. A conflicting merge-forward sends B to fix with the files and is not counted as a failed gate.
3. A leased or in-review descendant is never touched.
4. A stack of three moves forward in one pass, bottom-up.
5. A drop branch that moved during the merge is refused, and theirs is kept.
6. The block and its sensor are in the model. `ergostat check` adds no finding.

## Files to touch
dev/bin/stack.py (new), dev/model/building.yaml, dev/README.md (Stacked gaps), tests/test_factory.py.

## Acceptance tests
- tests/test_factory.py::test_a_moved_base_is_merged_forward_into_an_approved_descendant
- tests/test_factory.py::test_a_conflicting_merge_forward_sends_the_descendant_to_fix
- tests/test_factory.py::test_a_leased_descendant_is_not_merged_forward
- tests/test_factory.py::test_a_stack_of_three_moves_forward_in_one_pass

## Size budget
150 net lines in dev/bin.

Area: merge-pipeline. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.
