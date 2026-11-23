# compute-worker-keeper: The worker starts a run under a detached keeper, which runs it in its own process group and records its exit

depends-on: [compute-worker-protocol]

Problem: a run started by an SSH-launched worker would die with the session; the local wrapper only writes the exit (ergostat/spec/runrecord.py:22-30). This gap is the keeper's process control; its deadlines are compute-worker-keeper-deadlines. Change: new module ergostat/compute/worker/keeper.py and a `start` handler: `start` (run id checked against ^[0-9a-f]{32}$; refusals `bad name`, `full`, `limits over the node`) makes runs/RUN/ with run.json, in and a cwd, then starts a detached keeper (`--keep RUN`, setsid, SIGHUP ignored) and answers started or `refused no keeper`. The keeper forks the run in its own process group (pgid file written before exec, rlimits from the limits, on Linux PDEATHSIG and oom_score_adj), execs `/bin/sh -c COMMAND` with out/err to files, waits, and writes exit with the code and how (exit, or the signal). `kill {run}` writes a stop file; the keeper, seeing it within a quarter second, sends SIGTERM then SIGKILL after the grace and records how. It then waits for `done` or a day, removes its folder by name under the root, and exits. Done: a run reports its exit code; closing the worker's stdin leaves the run going and its exit is still written; on Linux a killed keeper takes its run with it (death signal); kill is TERM then KILL to the whole group; each refusal makes no folder and no process. At most 8 processes a test. Files: ergostat/compute/worker/keeper.py, ergostat/compute/worker/serve.py (one registration), tests/test_compute_keeper.py (five tests), docs/SPEC.md. Full text: wave2-compute.md (compute-worker-keeper, the process half). Budget: 180 net lines.

Area: compute. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Round 1: nothing built; this gap waits for `compute-worker-protocol`. Its `depends-on` gap is not on `main` as of
the clone (bea24a23): there is no `ergostat/compute/` package, no `ergostat/compute/worker/serve.py` to hold the one
registration this gap's Files list names, and no commit of that gap in the history (the only compute commits are
`compute-systems-proposal`, which changed no code). That gap defines the `start` handler's shape: the request and
answer framing, the node's capacity behind `full` and `limits over the node`, and the run's limits. It also builds
the worker whose stdin the "closing the worker's stdin" test closes. Building them here would be work outside this
gap (lesson 13), and writing `keeper.py` against a guessed interface would likely conflict with the protocol when it
lands. The more reversible choice taken: build nothing, and resume this gap once `compute-worker-protocol` is merged
to `main`. Left: all of it (keeper.py, the `start` and `kill` handlers' registration, tests/test_compute_keeper.py
with its five tests, the docs/SPEC.md text). Nothing reached the network.

## Where it stopped

Parked by the factory (review/compute-worker-keeper-1, 2026-11-22 12:31).

Done: the definition of done and a Where-it-stopped note in dev/records/compute-worker-keeper.md. Left: all of the work (keeper.py, the start/kill handlers in serve.py, tests/test_compute_keeper.py with its five tests, the docs/SPEC.md text). It stops because the start handler's framing, the node capacity and limits, and the worker itself belong to compute-worker-protocol, which is not in this branch's base; building them here would be outside the gap (lesson-13).

## Where it stopped

Parked by the factory (implementor, 2026-11-22 14:16).

Stopped on its last attempt by RuntimeError: claude: success: You've hit your weekly limit · resets Nov 24, 3am (UTC)

```
Traceback (most recent call last):
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 166, in main
    return build(cfg, given, began)
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 221, in build
    got = fac.session(cfg, "implementor", prompt, work)
  File "/Users/user/ergostat-live/instance/dev/bin/fac.py", line 669, in session
    raise RuntimeError(f"claude: {out.get('subtype')}: {str(out.get('result'))[:300]}")
RuntimeError: claude: success: You've hit your weekly limit · resets Nov 24, 3am (UTC)

```

## Where it stopped

Parked by the factory (dead-letters, 2026-11-22 14:16).

Its runs failed past their attempts (a dead letter):
- attempt 16: nack a switch drains the runs under way (run/drain.json): taken again after it
- attempt 17: nack a switch drains the runs under way (run/drain.json): taken again after it
- attempt 18: nack exited 1
- attempt 19: nack the run ended with gap/compute-worker-keeper-continued still parked

## Where it stopped

Parked by the factory (implementor, 2026-11-22 17:07).

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

Parked by the factory (dead-letters, 2026-11-22 17:07).

Its runs failed past their attempts (a dead letter):
- attempt 3: nack the implementor pool is full (run/pools.json): waits its turn
- attempt 4: nack the implementor pool is full (run/pools.json): waits its turn
- attempt 5: nack the implementor pool is full (run/pools.json): waits its turn
- attempt 6: nack the run ended with gap/compute-worker-keeper-continued-continued still parked

## Where it stopped

Round 1 (continued, continued), 2026-11-23: built. `compute-worker-protocol` is on `main` now (6e9eee4a), and
`main` (2a97eafb) was already merged into the branch (41c6c2f4).

Done: `ergostat/compute/worker/keeper.py` (`start`, `kill`, the keeper); its registration in `serve.py` (one
line after `hello`, `HANDLERS.update(keeper.handlers(root, said))`, plus its import); docs/SPEC.md §12s.3;
tests/test_compute_keeper.py with five tests: `test_a_run_reports_its_exit_code`,
`test_closing_the_workers_stdin_leaves_the_run_going`, `test_a_killed_keeper_takes_its_run_with_it` (Linux),
`test_kill_is_term_then_kill_to_the_whole_group`, `test_each_refusal_makes_no_folder_and_no_process`. Each was
seen to fail when the code it covers was broken: the keeper started without `setsid` (the stdin test, which also
hangs up and kills the worker's session); the death signal not set; SIGTERM to the run's leader only, not its
group; SIGKILL never sent; the folder made before the slot count.

Choices made with nobody to ask (each the more reversible one):
- Outside the Files list, `ergostat/compute/worker/__main__.py` gains two lines that send `--keep` to
  `keeper.main`. The keeper has to be started as the same folder or zipapp (`python3 -I WORKER --keep RUN`), and
  `serve.main`'s parser requires `--stdio`. Routing it in `__main__` leaves `serve.py` with only the registration.
- `kill` is answered `stopping`, or `refused` `no such run`; a malformed `start` (no command, env not strings) or
  `kill` (a grace outside 0 to 600 s) gets an `error` and makes nothing. A limit that is unknown or not a positive
  number counts as `limits over the node` (an allowlist: `cpus`, `memory`, `pids` at most 32768, `wall` at most a
  day). A run id whose folder exists is refused `bad name`.
- `full` counts every run folder that has no `exit` yet, whatever its keeper's state. That is the worst case: a
  folder whose keeper was killed holds its slot until a later gap (restart states) reads it as gone.
- After a stop, the keeper SIGKILLs the group past the grace if any process of it is left, even when the first
  process has ended at the TERM. A run that ends on its own is not swept.
- `oom_score_adj` is best effort (a failed write is ignored: it only orders the OOM killer's choice);
  PR_SET_PDEATHSIG is not best effort (if it fails, the run is not started).
- `hello`'s `backends` stays `[]`: the protocol's test pins it, and the run listing comes with later gaps.

Left for later gaps (not this one's): the keeper's wall and lease deadlines (compute-worker-keeper-deadlines); a
`done` message from the engine (the keeper waits for `runs/RUN/done`, but only the tests write it so far, and
otherwise it removes the folder after a day); `ended` and `out`; the runs listed in `hello` and `beat`.

Overrun reason: keeper.py has 212 lines with its docstrings and blank lines (186 not blank), plus 5 in serve.py and __main__.py, against a 180-line budget; the extra lines are the fail-closed checks the review lessons ask for (the slot count and folder made under one lock, the allowlisted limits, the path resolved under the root before removal, the exit written whole), not features beyond the definition.
