# merge-pipeline-stacked-gap-builds-on-its-base: A gap whose dependencies are approved is built on their reviewed branches, not on main

depends-on: []

## Problem
agents.clone always starts a new branch from origin/main (agents.py:282-296). implement.py measures and merges against main: base_sha at implement.py:200, merge_main at 202, finish's also at 227, strays at 228, net_lines at 244, and onmain.check at 238. So a gap cannot start until each gap it depends on has merged. This gap makes the implementor able to build on a base. It stays inert until stacks-turned-on lets such a gap be taken.

## Change
fac.stack_base(cfg, gap) returns, for a gap whose unfinished dependencies are each in approved, queued or push-pending, their reviewed heads ({gap, sha}, rank order). For any other gap it returns none. implement.py, when there are bases:
- clones as now, then merges each base's reviewed head into the branch (`--no-ff`, by this program, like merge_main). Never a rebase or a squash.
- records `stacked_on: [{gap, sha}]` on gap.started and gap.built.
- uses, as the base for strays, net_lines, the check findings and onmain's main comparison, the merge of main and every base (a commit in the drop under refs/stack/<branch>, made by this program).
- has finish hold each base sha as well as main.
Bases that conflict with each other give the gap back uncounted, with the files named and after 30m. A base whose reviewed head is no longer its branch's tip waits for the merge-forward and is given back uncounted.

## Definition of done
1. A gap with one approved dependency starts from that dependency's reviewed head merged with main. Its net_lines and strays count only its own commits.
2. With two approved dependencies, both are merged in rank order. If they conflict with each other, the gap is given back uncounted, naming the files.
3. stacked_on is on the item after gap.built, with each base's sha.
4. finish refuses a head that no longer holds a base's sha.
5. A gap with no unfinished dependency builds exactly as today: a test pins it.
6. implement.py's docstring step 1 says so.

## Files to touch
dev/bin/fac.py, dev/bin/implement.py, dev/bin/agents.py (finish's held shas), tests/test_factory.py.

## Acceptance tests
- tests/test_factory.py::test_a_stacked_gap_starts_from_its_bases_reviewed_head
- tests/test_factory.py::test_a_stacked_gaps_net_lines_count_only_its_own_commits
- tests/test_factory.py::test_two_bases_that_conflict_give_the_gap_back_uncounted
- tests/test_factory.py::test_an_unstacked_gap_builds_as_before

## Size budget
130 net lines in dev/bin.

Area: merge-pipeline. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.
