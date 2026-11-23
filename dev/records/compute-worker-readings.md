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

Round 2 (no review findings came to it). A self-review against the lessons hardened three fail-open spots (lesson 3), and SPEC
now says each one:
- the keeper's reaped CPU is read only while that pid's command line still says `--keep RUN`, so a reused pid
  cannot add a stranger's CPU;
- an exit file that is whole JSON but not an object is said as `ended` with `code` and `how` null, instead of keeping
  the run sampled every second and never ended;
- a look that raises is said on the worker's standard error rather than swallowed.
`libproc` is now loaded once. Each test was seen to fail with the code broken: the keeper never recognised (the burn
test's `method`), memory halved (the 100 MB test), `sampler_cpu` dropped (the keys test), `ended` not marked said
(the four-runs test says 12 frames, not 4).

Overrun reason: 225 net lines against 150 (round 2 added 8 lines for the three fail-closed reads above). Four things the definition implies but did not count: the keeper's reaped CPU (what makes the 1.5 s claim hold, rather than depend on where a sample lands), the minimal `ended` frame that `ended.resources` needs, macOS `libproc` open files so the keys equal a local run's on macOS too, and `ps` reaped with `wait4` so `sampler_cpu` counts the listing's cost.

Round 3 answers the one finding (the keeper found only through a live leader, so a run no sample saw read cpu 0,
`method` `none`). The keeper now reaps the run with `wait4` and writes its CPU to `runs/RUN/reaped`
`{"user", "system"}` just before `exit`; the sampler reads it with the exit, taking it only when both are finite
numbers from 0. This replaces the `/proc/KEEPER/stat` read of round 1 and the `--keep RUN` command-line check of
round 2 (no pid is looked up any more, so none can be reused), and it works off Linux too, so the burn test's
Linux-only skip is gone. Decisions taken alone (the most reversible): a file of its own rather than more keys in
`exit`, because the keeper's tests pin `exit` as exactly `{"code", "how"}`; a failed `reaped` write is said on the
keeper's log and the run still ends as it did (the CPU then the sampled sum, `method` without `keeper`), never
`not started`. keeper.py is outside the definition's Files list; the finding asked for the change there. A fifth
test, `test_a_sub_second_burn_still_has_the_keepers_cpu` (a 0.4 s burn: cpu ≥ 0.35, `method` naming the keeper), is
beyond the definition's four, as the finding asked. With the `reaped` write disabled it fails (cpu 0, `method`
`sampled`), and so does the 2 s burn test (`method` `sampled`). SPEC 12s.3 says the `reaped` file and narrows what
goes unseen: memory and processes of a run no sample saw, and the CPU only where `reaped` is unreadable.

Overrun reason: 224 net lines against 150 after round 3 (round 3 is net −1: the keeper's `reaped` write, 6 lines,
replaces the `/proc` keeper lookup). The four reasons above still stand, the first now the `reaped` file.

Round 3, after merging main (ead497d1): main's `output.py` now says `ended` `{run, code, how}` after a run's last
`out`, and lists "`ended`'s `resources`" as still to come. A second `ended` from the sampler would come before the
last `out` and break main's ordering. So the sampler's own `ended` is gone. The readings now go in as the
`resources` of output's `ended`: `Readings.ended(w)` wraps the follower's writer, so output.py is unchanged, and
`final` reads `reaped` again, so a run no look found still has its CPU. A run whose exit has been seen leaves the
beat's readings but is kept until its folder goes, so an `ended` said again after `attach` carries them too. The
beat's `runs` is one object per run, `{"out", "err", "resources"}` (compute-systems.md 2.1: offsets and the latest
reading per run). The decisions of rounds 1 and 2 about a minimal `ended`, and an exit that is not an object said
with null code, no longer apply: output.py waits for a readable exit. `test_one_thread_samples_four_runs` now checks
that the sampler sends nothing and that the wrapped writer's `ended` carries each run's readings. With output.py
given the plain writer, the sub-second test fails (`KeyError: 'resources'`).

Overrun reason: 248 net lines against 150 after the merge (+24: `final`, the `ended` writer and the beat's merged
`runs`, the integration with main's `ended` that the definition's "the whole in `ended.resources`" now needs). The
four reasons above still stand.

Round 4: the one finding was the conflict with main (e43046dc) in docs/SPEC.md, in 12s's opening paragraph. It is
resolved by keeping both sides: main's sentence that a model may declare `compute:` pools and `runs-on:` (checked
only), and the branch's "its CPU and memory read (12s.3)". Main's other change, to ergostat/compute/compile.py, does
not touch the worker, so no code changed this round. After the merge, the five readings tests pass, and so do the
keeper, output, worker-protocol and compile tests.

Round 5: the one finding was the conflict with main (dc47a763) in docs/SPEC.md and ergostat/compute/worker/keeper.py.
keeper.py keeps both sides: main's `wall` deadline (`timeout`, `WALL_GRACE`) and the branch's `reaped` write right
after `wait4`, so a run stopped at its deadline still has its keeper's CPU. Its docstring says both. SPEC 12s's
opening paragraph keeps main's text (the engine's session with each node, 12s.4; `runs-on:` checked only) with the
branch's "and its CPU and memory read (12s.3)". After the merge, the readings (5), keeper (5), output (6),
worker-protocol (8) and connection (6) tests pass, and ruff is clean.

Round 6: the one finding was a stranger on an ended run's pid (the keeper has reaped the leader, so whatever holds
that pid or group id later may be another process, and its memory, processes and CPU went into `ended.resources`).
Fixed by sampling a run only before its keeper has reaped it: a run whose `exit` was read is never sampled again
(no last sample), and after each listing any due run that now has `reaped` or `exit` has its sample dropped, so a
pid freed and reused between the look and the listing is not read either. Decision taken alone (the most
reversible): no last sample after the exit, rather than a group-only one, since a stranger that reused the pid and
made its own group has that same group id and nothing in a listing tells them apart. The cost, said in SPEC 12s.3:
what a run leaves running after its exit, and its last second before it, go unseen (its CPU then only `reaped`).
A sixth test, `test_a_stranger_on_an_ended_runs_pid_is_not_read`, puts a live unrelated process (its own group) on
the pid of two runs: one first found already ended (a restarted worker), and one whose `reaped` is written during
the listing. Both must read samples 0, memory 0, `method` `keeper` and exactly the `reaped` CPU. With the
after-listing drop disabled it fails (the stranger's memory read); the exclusion of an exit-read run is covered by
the same drop (that run has `exit` too), so it only saves a listing and no test fails without it alone.
After the change the readings (6), keeper (5) and output (6) tests pass, and ruff is clean.

Overrun reason: 251 net lines against 150 after round 6 (+3: the after-listing drop of a reaped run). The four reasons above still stand.
