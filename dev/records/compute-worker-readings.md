# compute-worker-readings: Per-run CPU and memory on the node, in beats and at the end

depends-on: [compute-worker-keeper]

Problem: a local run's CPU and memory come from the shared sampler and the wait status (ergostat/costs/sampler.py:1-24; engine.py:1082-1089) and go on agent.ran/agent.failed as `resources`; a node run has neither (compute-systems.md section 2.8). Change: new module ergostat/compute/worker/sampler.py (standard library only, so a small tree sampler of its own): each process-backend run's tree (its process group and descendants by parent), from /proc on Linux and one `ps -A -o pid=,ppid=,pgid=,rss=,utime=,stime=` elsewhere, sampled once a second for ten seconds then every ten; per run CPU seconds, peak resident memory and peak process count. The latest is in each beat and the whole in `ended.resources` with the same keys a local run's resources carry (sampler.Sampler.finish, sampler.py:235). One sampling thread for all runs; readings are measurements, never events. Done: a 2 s CPU burn reports at least 1.5 CPU seconds; a 100 MB allocation reports a peak at least that; the keys equal a local run's; one thread samples four runs. Files: ergostat/compute/worker/sampler.py, ergostat/compute/worker/serve.py (one registration), tests/test_compute_readings.py (four tests), docs/SPEC.md. Budget: 150 net lines.

Area: compute. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Built, round 1: all four acceptance tests are in tests/test_compute_readings.py, and they pass on Linux.

Decisions taken alone (the most reversible option each time):
- `ended` did not exist on the worker (SPEC 12s.3 listed it as still to come), and this gap's done needs
  `ended.resources`. So sampler.py says a minimal `ended` {run, code, how, resources}, read from the keeper's exit
  file, once per run in each worker session. The gap that builds the rest of `ended` (offsets, `done`, the runs
  in `hello`) can extend or move it.
- A beat carries `runs: {RUN: {"resources": ...}}`. Nesting the readings under `resources` leaves room for the run's
  state and offsets (compute-systems.md 2.1) without reshaping the beat.
- The sampler finds runs by looking at `runs/` every second, so it needs no hook in keeper.start. The one
  registration in serve.py is the thread, and the beat reads from it.
- On Linux, CPU also takes what the keeper reaped (`/proc/KEEPER/stat` cutime and cstime). A 1 Hz sample alone can
  miss up to the last second, so on its own it would give a 2 s burn 1.0 to 2.0 s. With the keeper read the ≥ 1.5 s
  claim holds every time. Off Linux the keeper's reaped CPU is not in `ps`, so the burn test is skipped there with
  that reason (SPEC says so).

Overrun reason: 217 net lines against 150. Four things the definition implies but did not count: the keeper's reaped CPU (what makes the 1.5 s claim hold, rather than depend on where a sample lands), the minimal `ended` frame that `ended.resources` needs, macOS `libproc` open files so the keys equal a local run's on macOS too, and `ps` reaped with `wait4` so `sampler_cpu` counts the listing's cost.
