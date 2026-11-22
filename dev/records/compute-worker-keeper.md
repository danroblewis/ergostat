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
