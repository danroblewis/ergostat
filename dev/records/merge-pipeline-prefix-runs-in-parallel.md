# merge-pipeline-prefix-runs-in-parallel: The queue can run one check on every prefix of a batch at once, each in its own worktree and container

depends-on: []

## Problem
The queue tests one tree at a time, its checkout (queue.py:91-169). Bisecting a batch is therefore serial: queue.py:705-709 halves the batch one step at a time and runs once per step. On 2026-11-22, operating-states-20261122T094631Z made 23 suite runs from 09:46 to 11:01. Four of them were full runs of about 9 minutes, and twelve were named runs of about 1 minute, one after another (run/queue/ log times). agents.queued (agents.py:434-450) already supports a worktree as the work, so trees can be tested side by side.

## Change
A new module, dev/bin/prefixes.py. Never name it after a stdlib module (queue.py:59). It provides run_all(cfg, repo, heads, check, tag, logs, most). For each commit in heads, it makes a detached worktree under run/queue-prefix/<tag>-<i>, named by this code and removed by name afterwards. Then it runs check(i, worktree) for each, at most `most` at a time, in threads. check is fac.suite with box "queue" for a given suite (rerun with tests, or ruff). The result per prefix is pass, fail or unknown, with its log. A stop (fac.stop_suites, SIGTERM) kills every container by name and removes every worktree it made. A worktree left by a SIGKILLed run is removed at the next run's start, under the queue's lock. `[suites] prefix_most` (default 4, at most 8) caps concurrency. `[agents]` gives each prefix container `prefix_cpus` CPUs (default 1.5), within queue_cpuset.

## Definition of done
1. run_all on 5 heads returns 5 results in heads' order, each read from its own log. A run that does not start is unknown, never pass (lesson-3).
2. At most prefix_most checks run at once.
3. Stopping a run part way leaves no container (by name) and no worktree under run/queue-prefix/.
4. A worktree from a killed run is removed at the next start, and only those under run/queue-prefix/ that match the run-tag pattern (deletes by allowlist).
5. The settings are in dev/factory.toml with comments. Values out of bounds are refused, with the reason given.

## Files to touch
dev/bin/prefixes.py (new), dev/bin/agents.py (the per-prefix CPU limit), dev/factory.toml, tests/test_factory.py.

## Acceptance tests
- tests/test_factory.py::test_prefix_runs_return_one_result_per_head_in_order
- tests/test_factory.py::test_prefix_runs_hold_to_prefix_most
- tests/test_factory.py::test_a_stopped_prefix_run_leaves_no_worktree_or_container
- tests/test_factory.py::test_a_prefix_run_that_did_not_start_is_unknown

## Size budget
140 net lines in dev/bin.

Area: merge-pipeline. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.
