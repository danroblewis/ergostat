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

## Where it stopped

Build step failure, answered (2026-11-23): its tail ends part way through the dots, with no FAILED line, no pytest
summary and no suite_watch JSON line. So the whole suite container was stopped from outside mid-run (a memory kill
or a Docker restart, like the one at 17:01). No test failed. Run again serially
(`scripts/named_tests.py tests/test_factory.py`), the file gives 190 passed and 2 skipped (both need Docker and the
agent image). ruff is clean on ergostat, tests and scripts, and on the three dev/bin files this gap touches. No code
changed: nothing in the tail points to the branch's code. The `-n 8` run was not reproduced here, because the
house rules allow only serial runs of named files.

## Where it stopped

Build step failure again, the same way (2026-11-23): `affected_tests` picks tests/test_factory.py, xdist prints
"bringing up nodes..." twice, then 13 dots, then nothing. There is no FAILED or ERROR line, no pytest summary and no
suite_watch JSON line, and the whole log is shorter than the 3000-character tail. So the suite container was
stopped from outside the pytest run. Had suite_watch's own limits killed it, or a worker been killed alone, it would
have printed a line. What was checked here:
- Run serially (`scripts/named_tests.py tests/test_factory.py`), the file passes: 190 passed, 2 skipped (both need
  Docker and the agent image), in 418 s. It used 323 MB of /tmp, so the suite container's 2 GB /tmp tmpfs is not
  filling up.
- None of this gap's changes in dev/bin (fac.stack_base, implement.stack, the merge, finish's held shas) sends a
  signal or kills a process or process group. Its five tests make small git repositories and run implement.py,
  nothing more.
- tests/test_factory.py, which comes from main and is not this gap's, has no test that runs the real build or unit
  command on the worktree, so there is no nested suite, and no test kills a PID it made up. The tests that kill
  `$PPID` kill only the queue.py they start themselves.
No code changed: no fault in the branch could be found, and a change made only to have something to show would be a
guess. Not checked: the `-n 8` run in the factory's suite container (4 CPUs, 12 GB, a 2 GB /tmp), because the house
rules allow the implementor only serial runs of named files. For the factory to look at: the build log's exit code
and the container's (137, or OOMKilled in `docker inspect`). A cut that happens twice in the same place points to
the container or the host, not to a test. This is very likely the first time tests/test_factory.py itself has run
under `[suites] build`, because only a gap that edits that file selects it.
