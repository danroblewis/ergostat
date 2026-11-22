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

## Where it stopped

Built, round 1: dev/bin/prefixes.py (125 lines) and the per-prefix CPU limit in dev/bin/agents.py (+13 net): 138 net
lines in dev/bin, within the 140. The four acceptance tests pass, and each was seen to fail with the code broken
(lesson-9): no concurrency cap (peak 6, not 2); no stop handling (4 containers started, not 2); no sweep at the
start (the killed run's worktree kept); a sweep by denylist (the symlink and the non-pattern entry wrong); exit 125
read as a result (fail, not unknown); an earlier run's log left in place (read as pass).
Run here (serially, in the implementor's container): tests/test_factory.py 170 passed, 2 skipped (both for want of
Docker and the agent image, as on main); tests/test_agents.py 18 passed; ruff clean. Not run here: the unit suite, the
browser files and demo_check (no example touched); a prefix run against real Docker containers (the stop test
fakes docker itself and runs real fac.suite processes).

Choices made alone (nobody to ask), each the most reversible:
- Not wired into queue.py: the definition says the queue *can* run it and does not list queue.py, so bisection is
  still serial until a gap of its own calls run_all (under the queue's lock, which run_all's sweep relies on).
- check keeps the definition's signature check(i, worktree); the log it writes is prefixes.log_of(logs, tag, i)
  (logs/<tag>-<i>.txt), and prefixes.suite(cfg, name, logs, tag, **fmt) makes that check from fac.suite (box
  "queue", slot=False). A check that raised, an exit of 125-127 or of a signal, an empty or missing log, a worktree
  that could not be made: unknown, with its why. Pass is rc 0 with a log; reading a pass more strictly (every named
  test PASSED, as queue.named does) is left to the caller, which has the log and its tail.
- agents.queued gives a container prefix_cpus when its work is under run/queue-prefix/ (fac.py, not in the files to
  touch, is unchanged); prefix_cpus out of (0, 4] is refused at run_all's start, before any worktree is made.
  prefix_most out of 1..8 is refused by prefixes.prefix_most and again for a `most` given at run time; neither is
  checked in fac.config(), so a bad value is refused when a prefix run starts, not when the config is read.
- run_all starts a thread per head, so a run's heads are capped too: more than 64 refused (lesson-4; [pools]
  batch_max is at most 8).
- The sweep removes only entries of run/queue-prefix/ named <run tag>-<i> (a symlink of that name: the link only).

Round 1, a second pass: the stop test was not reliably passing. Run alone again it failed 1 run in 6
(a container's name left in fac.BOXES, its process group in fac.SUITES), so the "passes" above was one lucky run.
The cause: on Python 3.12, a SIGTERM handler raising while Thread.join waits (threading._wait_for_tstate_lock)
releases the live thread's lock and marks the thread stopped, so is_alive() says False while its suite runs. run_all
waited on is_alive, so it returned with that check's container and process still running (done item 3, lesson-6).
Fixed: each thread sets an Event of its own in a finally as it ends, and run_all waits on those Events, never on
join or is_alive. A stop waits on the Events of every thread that had started; one that had not started sees the stop
and makes nothing. After the fix the stop test passed 20 runs of 20. A new test,
test_a_prefix_run_waits_for_its_checks_whatever_a_join_says, fakes the broken state (is_alive False, join returning
at once) and fails on the old wait (run_all returned before any check ended), so it does not depend on timing.
To keep within 140 lines: [agents] prefix_cpus is now checked at every run_all start, also when queue_container is
false (stricter, and easy to undo). dev/bin: 140 net lines.
