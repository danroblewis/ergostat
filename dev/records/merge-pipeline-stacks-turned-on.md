# merge-pipeline-stacks-turned-on: Stacking turned on: gaps start on approved dependencies, reviewed against their base

depends-on: [merge-pipeline-relation-starts-at, merge-pipeline-stacked-gap-builds-on-its-base, merge-pipeline-stacks-land-bottom-up, merge-pipeline-stacks-merged-forward]

## Problem
With the engine option, the implementor and the queue ready, the factory still waits for merges. ergostat.yaml:115 declares `depends_on: gap` as finish-to-start. The reviewer diffs against main (review.py:182-187), so a stacked gap would be reviewed and sized with its base's lines and sent back over budget. deps.py's blocked_reason (deps.py:165-166) would still say that the gap waits on an approved dependency.

## Change
- ergostat.yaml: `depends_on: {kind: gap, starts_at: [approved, queued, push-pending]}`.
- review.py: for a gap with stacked_on, the diff, net_lines and gate 1's main check use fac.stack_base's merged base (refs/stack/<branch>), never main. The brief says the gap is stacked and names its bases.
- deps.py: a dependency in a starts_at state is said as `stacked on X (approved)`, not as waiting.
- dev/model/building.yaml: a stock gaps-stacked (sensor: gaps with stacked_on not yet merged), so the Dynamics diagram shows stacked work.
- dev/README.md: a short section, Stacked gaps.

## Definition of done
1. On the factory's model, a ready gap whose only dependency is approved is taken by the implementor (an engine test on a copy of the model).
2. The reviewer of a stacked gap is given only the gap's own diff. Its net lines match the implementor's.
3. blocked_reason says stacked on, and the Items page shows it (no new UI).
4. `ergostat check` adds no finding on the factory's model.
5. dev/README.md says how a stack is built, reviewed and landed, and what happens when a base fails or parks (the descendant waits, waits_on_parked).

## Files to touch
ergostat.yaml, dev/bin/review.py, dev/bin/deps.py, dev/model/building.yaml, dev/README.md, tests/test_factory.py, tests/test_backlog.py.

## Acceptance tests
- tests/test_factory.py::test_the_factory_takes_a_gap_whose_dependency_is_approved
- tests/test_factory.py::test_a_stacked_gap_is_reviewed_against_its_base
- tests/test_backlog.py::test_a_dependency_in_a_starts_at_state_is_said_stacked_on

## Size budget
60 net lines.

Area: merge-pipeline. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Built: all five done items, and the three acceptance tests pass.

One departure from the Change list, taken as the most reversible option with nobody to ask: `gaps-stacked` is an
**auxiliary**, not a stock. As a stock it added `stock-without-flows@stock.gaps-stacked` to `ergostat check`, which
breaks done item 4. Its gaps are already counted in their own states' stocks, and a sensor `where:` cannot match
"stacked_on is not empty", so it has no flows. It is the same shape as `stale-stacks`, a `run:` sensor
(`deps.py stacked`), and the Dynamics diagram draws it (node `stock:gaps-stacked`, asserted in
test_ergostat_check_on_the_factory_model_reports_no_new_finding). To make it a stock later, give it flows.

A known limit, left for its own gap: when stack-forward merges a base's new head into a gap that is *built*, it does
not rewrite refs/stack/factory/<branch>. That gap's review diff then also shows the base's new commits, which are
reviewed already.

Size: 0 net lines of core code (fac.net_lines). Counting dev/bin, dev/model and ergostat.yaml, 40 net lines
(deps.py 11, review.py 22, building.yaml 5, ergostat.yaml 2), under the 60-line budget. dev/README.md adds 20 lines of
prose on top of that.

### Round 2

The known limit above is fixed, as round 1's review asked: it is no longer a limit. When stack-forward
(dev/bin/stack.py `restack`) moves a *built* stacked gap, it first merges the moved bases into
refs/stack/factory/<branch> (implement.stack, over the old ref), then merges that ref into the gap in their place. The
ref stays an ancestor of the head, and `ref...HEAD` holds only the gap's own commits. If the merge forward is refused,
the old ref is put back. Approved descendants are merged as before, since their review is done. review.py
`stacked_base` also fails closed: when the ref does not hold every `stacked_on` sha, that is a blocking finding and the
gap is judged against main. The round-1 test grew two cases (base approved again with 30 new lines, stack.py, review:
net lines 2, base2.py not in the diff; ref left stale: "does not hold them all"). Each case was seen to fail with its
code switched off (net lines 32 without the check). dev/README.md and review.py's docstring now say how the ref moves.

dev/bin/stack.py is not in Files to touch. The finding names it as the cause (stack.py:102), and it is the program
that moves the head, so the ref moves there too. The other way, rebuilding the ref inside the reviewer, would have
the reviewer write to the drop.

Size: still 0 net lines of core code. Counting dev/bin, dev/model and ergostat.yaml, 62 net lines (deps.py 11,
review.py 26, stack.py 18, building.yaml 5, ergostat.yaml 2).
Overrun reason: counted with dev/bin, the round-2 fix for the review's blocking finding (stack.py restack and the fail-closed check in review.py, 22 lines) brings 40 to 62, 2 over 60; the size gate's own count (outside tests/, docs/ and dev/) is 0.
