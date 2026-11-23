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

## Where it stopped

Built: items 1 to 6, in 68 net lines of dev/bin (fac.py 16, implement.py 51, agents.py 1). Choices made alone,
each the more reversible one:

- The bases are merged `--no-ff`, in rank order, by this program, into one commit in the drop
  (refs/stack/factory/<branch>), and that commit is merged into the branch once, after the definition. The branch
  does not get one merge per base. That way the branch holds the stack commit, so the three-dot measures (strays,
  net_lines) have one merge base. Separate merges per base would give two merge bases (main and the base), and git
  would pick either one. Each stack merge is dated as the base it adds, so a later round with the same main and
  bases makes the same commit and does not merge it again.
- A conflict with main counts the same as a conflict between bases: the gap is given back uncounted after 30m,
  with the files named. A base with no recorded reviewed head counts as one that is no longer its branch's tip, so
  it waits in the same way.
- fac.stack_base returns {gap, sha, branch}: the implementor needs the branch to check the tip. stacked_on records
  only {gap, sha}. A dependency that is not in the record makes stack_base return none, as the definition says. The
  gap then builds on main, which is today's behaviour, and the taking gate decides whether it is taken.
- When the stack's suites fail only on tests that also fail on the stack, built_main, waits_on_main and the
  main-broken record still name main's sha, not the stack's. The intake clears waits_on_main when it differs from
  main, so the stack's sha would release the gap at once. A test that fails on the stack may be a base's fault
  rather than main's, so stacks-turned-on should look at this.
- Not in this gap's files, so left alone: review.py's size gate and queue.py still measure against main. A stacked
  gap stays inert until stacks-turned-on.

Extra test, not named in the definition: test_finish_refuses_a_head_that_no_longer_holds_a_base (item 4).

## Where it stopped

Parked by the factory (reviewer, 2026-11-22 14:18).

Stopped on its last attempt by RuntimeError: claude: success: You've hit your weekly limit · resets Nov 24, 3am (UTC)

```
Traceback (most recent call last):
  File "/Users/user/ergostat-live/instance/dev/bin/review.py", line 143, in main
    return judge(cfg, given["item"], began)
  File "/Users/user/ergostat-live/instance/dev/bin/review.py", line 195, in judge
    got = fac.session(cfg, "reviewer", text, wt)
  File "/Users/user/ergostat-live/instance/dev/bin/fac.py", line 669, in session
    raise RuntimeError(f"claude: {out.get('subtype')}: {str(out.get('result'))[:300]}")
RuntimeError: claude: success: You've hit your weekly limit · resets Nov 24, 3am (UTC)

```

## Where it stopped

Parked by the factory (implementor, 2026-11-22 17:03).

Stopped on its last attempt by RuntimeError: docker network: failed to connect to the docker API at unix:///Users/user/.docker/run/docker.sock; check if the path is correct and if the daemon is running: dial unix /Users/user/.docker/run/docker.sock: connect: no such file or directory

```
Traceback (most recent call last):
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 166, in main
    return build(cfg, given, began)
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 221, in build
    got = fac.session(cfg, "implementor", prompt, work)
  File "/Users/user/ergostat-live/instance/dev/bin/fac.py", line 678, in session
    out = agents.session(cfg, role, brief, work, keep=kept)
  File "/Users/user/ergostat-live/instance/dev/bin/agents.py", line 204, in session
    egress(cfg)
    ~~~~~~^^^^^
  File "/Users/user/ergostat-live/instance/dev/bin/agents.py", line 117, in egress
    _egress(cfg)
    ~~~~~~~^^^^^
  File "/Users/user/ergostat-live/instance/dev/bin/agents.py", line 124, in _egress
    docker("network", "create", "--internal", NET)
    ~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/user/ergostat-live/instance/dev/bin/agents.py", line 106, in docker
    raise RuntimeError(f"docker {args[0]}: {r.stderr.strip()[-300:]}")
RuntimeError: docker network: failed to connect to the docker API at unix:///Users/user/.docker/run/docker.sock; check if the path is correct and if the daemon is running: dial unix /Users/user/.docker/run/docker.sock: connect: no such file or directory

```

## Where it stopped

Parked by the factory (dead-letters, 2026-11-22 17:03).

Its runs failed past their attempts (a dead letter):
- attempt 1: nack exited 1
- attempt 2: nack the implementor pool is full (run/pools.json): waits its turn
- attempt 3: nack the run ended with gap/merge-pipeline-stacked-gap-builds-on-continued still parked

## Where it stopped

Resumed 2026-11-23 after the two factory parks (the reviewer's weekly limit, then Docker restarting): neither was
this gap's fault, and nothing in the code changed. main (2a97eafb) is already merged in. The four acceptance tests
and test_finish_refuses_a_head_that_no_longer_holds_a_base pass again. `ruff check ergostat tests scripts` is clean.
Built, waiting for review.
