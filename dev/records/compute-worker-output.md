# compute-worker-output: A node run's output sent by offset, resumed by attach, capped

depends-on: [compute-worker-keeper]

Problem: the engine records a run's lines as it follows a local file (ergostat/spec/stream.py:27-62); over a session that can be cut, lines must be addressable so a resend is recorded once (compute-systems.md section 2.3; order by offset, never time). Change: new module ergostat/compute/worker/output.py: a follower over each run's out and err sends `out {run, stream, offset, text}` (offset of the first byte; at most 64 KiB a line, split at a line end where possible; whole lines only until the run ends). `attach {run, out, err}` resends from those offsets; beat carries each run's offsets taken. Flow control: at most 4 MiB sent ahead of the engine's acknowledged offsets across runs. A file past limits.log (default 64 MiB, at most 1 GiB) stops its run with how `log over its cap`. `ended` comes after the run's last out; `done {run}` writes runs/RUN/done. Done: 10,000 lines covered exactly once in order; attach from a middle offset resends only from there; a line over 64 KiB rejoins exactly by offset; with the reader stalled at most 4 MiB is unacknowledged and RSS stays bounded (measured); a run over its log cap is stopped. Files: ergostat/compute/worker/output.py, ergostat/compute/worker/serve.py (registrations), tests/compute_pipe.py, tests/test_compute_output.py (six tests), docs/SPEC.md. Budget: 220 net lines.

Area: compute. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Nothing built: this gap waits for compute-worker-keeper, which is not on main. The `depends-on` line says it should
have been merged before this branch began, but main (52c675fe) has none of it. `ergostat/compute/worker/serve.py`
registers only `ping`, there is no `keeper.py` and no `start` handler, and nothing makes a `runs/RUN/` folder.
Everything this gap does acts on a run that gap makes:
- the out and err files the follower reads (`runs/RUN/out`, `runs/RUN/err`);
- the run's `limits.log` (given in its `start`);
- the stop that `log over its cap` needs (the keeper's `runs/RUN/stop` and the exit it writes);
- the `ended` that must come after the run's last `out`.
The six acceptance tests can't start a run without that gap's `start`.

The most reversible option, taken: build nothing rather than guess at that gap's folder layout, stop file and
`ended`. A guess would conflict with it, or fix its interfaces from outside it (lesson-13). What is left: the whole
definition above, unchanged, once compute-worker-keeper is on main. Start this branch again from that main.

## Where it stopped

Parked by the factory (review/compute-worker-output-1, 2026-11-22 18:05).

Nothing built: only the definition of done and its 'Where it stopped' are committed (dev/records/compute-worker-output.md). On main, ergostat/compute/worker/serve.py:32 registers only `ping`, there is no keeper.py, no start/kill handler, no runs/RUN/ folder, and docs/SPEC.md §12s.3 is still 'To be filled'. Every part of this gap acts on a run made by compute-worker-keeper: the follower's out/err files, limits.log from `start`, the stop for 'log over its cap', and `ended` after the last out. Left: the whole definition (output.py, serve.py registrations, tests/compute_pipe.py, the six tests in tests/test_compute_output.py, SPEC text). Restart the branch from main once compute-worker-keeper has landed.

## Where it stopped

Round 1 continued (2026-11-23): built. compute-worker-keeper is on main (39c32ecc) and already merged into this
branch (abfd7fff), so the branch was continued, not restarted. Built: `ergostat/compute/worker/output.py` (one
follower thread for all runs; `out` by offset, `attach`, `ack`, `ended`, `done`, the 4 MiB window, the log cap), its
registration in `serve.py` (and the worker's `beat` now carries each run's taken offsets), SPEC §12s and §12s.3,
and the six tests in `tests/test_compute_output.py`, named as in the plan
(docs/research/2026-11-22-design-and-planning/plan/wave2-compute.md, compute-worker-output). 205 net lines.

Where the definition was silent, the most reversible option, taken and said in SPEC:
- The acknowledgement is `ack {run, out, err}`, a request of its own. The plan says the beat's taken offsets come
  "from the engine's last attach/ack", and `attach` can't also be the acknowledgement: it resends from its offsets.
  The worker's `beat` says those taken offsets per run.
- `attach`, `ack` and `done` are answered only when refused (`no such run`, `offset past the output`). An answer
  can be added later without changing what is sent now.
- `ended` is `{run, code, how}` from the keeper's exit, `how` being `log over its cap` when the worker's cap stop
  (the keeper's `stop` file, grace 1 s, that `why`) ended it with TERM or KILL. `resources` is left to
  compute-worker-readings.
- Text that is not UTF-8, and a character cut by a 64 KiB split, travel as surrogate escapes, so the bytes rejoin
  exactly by offset.
- A worker started again follows a run only once it is attached; runs listed in `hello` belong to
  compute-worker-restart-states.
- Outside the Files list, two small changes this needed: `keeper.py` accepts `limits.log` (at most 1 GiB, 2 lines:
  without them every `start` carrying `log` was refused `limits over the node`), and the keeper tests' `Node` helper
  moved into `tests/compute_pipe.py` (with `alive` and `until`), so `tests/test_compute_keeper.py` changes only in its
  imports. `compute_pipe.Taken` is the engine's drop-below-taken rule as a test helper, as the plan asks.

Left: nothing in this definition. The engine's own use of the frames comes with compute-remote-backend.
