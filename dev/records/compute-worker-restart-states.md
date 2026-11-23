# compute-worker-restart-states: A starting worker lists its runs as running, gone or unknown, and sweeps by name

depends-on: [compute-worker-keeper]

Problem: a worker started again must say which runs it still holds and never call a run gone on a reading it did not make (compute-systems.md sections 2.4, 2.9); the local record decides alive by pid and start time only (ergostat/spec/runrecord.py:75-80). Change: new module ergostat/compute/worker/states.py: at start read every runs/RUN/ folder named ^[0-9a-f]{32}$; each run is `running` (pid alive with the recorded start time), `gone` only on an allowlisted reading (exit file written; or pid absent or restarted and its process group read as empty), else `unknown` (record unreadable, ps failed, group not read, run alive but keeper gone). hello.runs and beats carry the states. For unknown the worker at once stops the run by name (SIGTERM then SIGKILL to the recorded group) and keeps listing it unknown. A keeper gone with its run ended: the worker records the exit and cleans up. A sweep at start and hourly removes only run folders of that name form, resolved inside the root, when `done` exists or a day has passed since the end; never all-but-a-list. Done: the five cases in wave2-compute.md (running after restart; gone on exit file; ps failure is unknown and stopped; reused pid by group state; the sweep leaves other names, outward symlinks and young folders). Files: ergostat/compute/worker/states.py, ergostat/compute/worker/serve.py (hello and beat read it), tests/test_compute_restart_states.py (six tests), docs/SPEC.md. Budget: 200 net lines.

Area: compute. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Round 1: built. `ergostat/compute/worker/states.py` (the states, the stop by name, the sweep), `serve.py` (hello's
`runs`, each beat's states, the sweep after hello and hourly), SPEC §12s (the hello table, the beat, §12s.3's keeper,
§12s.6), and the six tests in `tests/test_compute_restart_states.py`, each of which a break of its code was seen to
fail (the group read as always empty; a failed ps read as not alive; the sweep's done/age test removed; the exit file
ignored).

Choices made alone, each the most reversible (no one to ask):

- **`keeper.py` changed (2 lines), outside the Files list.** Nothing on disk recorded the run's start time or its
  keeper's pid and start time, and the definition's `running` ("pid alive with the recorded start time") and "run
  alive but keeper gone" need both. The keeper is the only process that knows them at the fork, so it now calls
  `states.record`, which writes `runs/RUN/proc`; a failed write leaves the run `unknown`, never gone. The engine's own
  kept runs (`keeper.launch`) get the file too, unread there; `test_runs_outlive_engine.py` and
  `test_runs_adopted.py` pass.
- **The sweep also needs the run's `exit`**, beside `done` or a day since the end (the exit's mtime is the end). The
  definition says "when `done` exists"; `done` without an exit (a `launch` that timed out) may still have a keeper
  starting, so that folder is kept. This is stricter than the definition, never wider.
- **Beats read again only the runs listed in hello.** A run started in this session can be read the instant before
  its keeper writes `proc`, which would read `unknown` and be stopped; its state is its `started` and `ended`. The
  one race left is said in SPEC: a folder another worker on the same root is making as this one starts is stopped.
- **"Cleans up"** for a keeper gone with its run ended is: the exit written by the worker (`{"code": null, "how":
  "keeper gone"}`, read as 127, never success); the folder then goes by the engine's `done` or the day-old sweep.
  Nothing else is removed then, because the engine has not yet read the run's output.
- **The stop by name** writes the run's `stop` too (a live keeper acts on it), beside the worker's own SIGTERM, then
  SIGKILL 2 s later to the group in `pgid`, and never to the worker's own group.

Not tested: the macOS `ps` paths (this container is Linux), the hourly sweep's timer, the "keeper gone" unknown
(the run alive, its keeper not), and a beat's re-stop.

Overrun reason: about 255 net lines against 200, because the definition assumes a recorded start time that did not exist (the keeper's `proc` record and the reading of both start times) and the allowlisted readings need a second platform's form (`ps` on macOS) beside `/proc`, each failure read as Unread rather than gone.

Round 2: the one review finding (states.py:142-147 with `States.stop`: a reused pid's recorded group signalled, and
the SIGKILL sent without reading again), answered as the review asked, all three parts:

- **A reused pid reads gone.** The run leads its own group (pgid == pid), and the kernel gives a pid number again
  only when no process has it as pid or group, so a pid now another process's (start time differs) means the run's
  group is empty: `gone`, never signalled. The `pgid` file is no longer read by the states; the group is the pid.
  Only an absent (or zombie) pid reads the group table: empty is gone, else `unknown` "group not empty".
- **A boot id in `proc`** (`/proc/sys/kernel/random/boot_id`; `sysctl -n kern.boottime` on macOS); another boot is
  `gone` with the exit written `{"code": null, "how": "rebooted"}`. The boot not read is `unknown` "ps failed".
- **Each signal is sent only when `shown`**, read just before it (SIGTERM, and again before the SIGKILL 2 s later):
  the record's boot is this one and its pid alive with the recorded start time. Otherwise no signal at all; the
  run's `stop` is still written, so a keeper that is there stops its own run. So a `group not empty`, an unreadable
  record or a ps still failing is never signalled by the worker; it stays listed unknown. Narrower than the
  definition's "SIGTERM then SIGKILL to the recorded group" for those cases, by the review's ruling; the most
  reversible choice (a missed stop leaves a run going and listed unknown; a wrong one kills a stranger).
- **Tests:** `test_reused_pid_group_alive_unknown` (which locked the bug in) is replaced by
  `test_reused_pid_stranger_survives`: a setsid stranger on the run's old pid, with one folder of another start time
  and one of the stranger's own start time but another boot, both gone, nothing signalled, the stranger alive.
  `test_reused_pid_group_empty_gone` became `test_absent_pid_by_group_state`: an absent pid with an empty group is
  gone; an absent leader whose group still holds a process is unknown, its `stop` written, nothing signalled, the
  process alive. `test_ps_failure_is_unknown_and_stopped` now fails ps for the look only and shows the worker's
  SIGTERM goes to that group alone once the leader is read again. Still six tests. Each break was seen to fail a
  test: `shown` always true (absent-pid test), always false (ps-failure test), the group read for a reused pid
  (stranger test), the boot check removed (stranger test).
- Left open, said in SPEC: the leader ending and its number taken again between `shown`'s reading and the signal.
  Not tested: the macOS `sysctl`/`ps` paths, the hourly sweep's timer.

Overrun reason: about 290 net lines against 200 (round 1's reasons, plus the boot record and reading, and the reading again of the leader before each signal that the review's fix requires).

Round 3: the one review finding (states.py:68-72 with :164-165: off Linux the boot read as `kern.boottime`, a time
of day the clock moves, so a clock step read every live run as `rebooted`, a false exit written), answered both
ways the review offered, together:

- **A real per-boot id off Linux:** `sysctl -n kern.bootsessionuuid`, a UUID made at each boot.
- **A boot reading is a UUID or no reading.** `boot()` accepts only the UUID form (8-4-4-4-12 hex), else Unread, so
  the run is `unknown` "ps failed", never gone, and nothing is signalled (`shown` is false). A recorded `proc` whose
  boot is not a UUID is `record unreadable`. So `rebooted` is said only when two UUIDs, each read, differ. If
  `kern.bootsessionuuid` is absent or of another form on some macOS, runs read `unknown` there (the reversible side:
  a run left going and listed, never a false exit).
- SPEC §12s.3 (the keeper's `proc`) and §12s.6 (gone, unknown) say so.
- **Test:** `test_reused_pid_stranger_survives` (still six tests) now also stubs the macOS path: `boot()` asks
  `sysctl -n kern.bootsessionuuid` and takes its UUID; a `kern.boottime`-form answer raises Unread and a live run's
  record of another boot reads `unknown` "ps failed", no exit written, nothing signalled; a recorded boot "old" reads
  `record unreadable`. Each break was seen to fail it: `boot()` accepting any non-empty reading; `_proc` not checking
  the recorded boot's form.
- Not tested: a real macOS (this container is Linux; `kern.bootsessionuuid` is taken on knowledge, not checked
  here), the hourly sweep's timer.

Overrun reason: about 295 net lines against 200 (round 2's reasons, plus the UUID form check on both boot readings that round 3's finding needs).

Round 4: main (ee43cf605696) merged first. The conflicts were in `keeper.py`, where the keeper now calls both
`states.record` and main's `keep(..., held, ...)` with its deadlines, and in SPEC §12s.3's "Built so far", which now
lists main's deadlines (§12s.5) and points to §12s.6 for the runs in `hello`. The one review finding was states.py
`_stat` off Linux: `ps -o lstart=` text depends on LANG/LC_TIME and TZ, so a record made in one environment and read
in another reads as another process, and a live run is written gone. Answered both ways the review offered:

- **Every `ps` and `sysctl` in states.py runs with `LC_ALL=C`, `LANG=C` and `TZ=UTC` set over the caller's
  environment** (`_ps`, used by `_stat` for both `record` and `state`, by `groups()` and by `boot()`). So the keeper's
  record and a later worker's reading print in one form.
- **A start time is of one form or it is no reading:** on Linux, `/proc` field 22 must be digits; elsewhere, lstart's
  C form (`Mon Nov 23 10:00:00 2026`). A read text of another form raises Unread (`unknown` "ps failed", not
  signalled), and a recorded one of another form is `record unreadable`. A record left by a keeper running before this
  fix, in another locale, therefore reads unknown and is never written gone. One case is left, said here: a record
  in the C form but under a different TZ (made before this fix) would still differ. Such records don't exist, because
  the branch has not landed.
- `sampler.py`'s `ps` (outside this gap) is not changed; it reads no start times.
- SPEC §12s.3 (the keeper's `proc`) and §12s.6 (`record unreadable`, `ps failed`) say so.
- **Test:** `test_reused_pid_stranger_survives` (still six tests) stubs the macOS path with the caller's
  `LC_ALL=fr_FR.UTF-8` and `TZ=Europe/Paris`. Every ps/sysctl call carries `LC_ALL=C` and `TZ=UTC`. A live run whose
  C-form record matches reads `running`. The same start read in a French form reads `unknown` "ps failed", with no
  exit written and nothing signalled. A record in that form reads `record unreadable`. Each break was seen to fail it:
  the env pin removed (the env assertion); the read form check removed (reads gone "keeper gone", the bug itself);
  the record form check removed.
- Ran: tests/test_compute_restart_states.py (6), test_compute_keeper.py with test_compute_keeper_deadlines.py (12),
  test_runs_outlive_engine.py with test_runs_adopted.py (32), all passing; ruff clean. Not tested: a real macOS.

Overrun reason: about 315 net lines against 200 (round 3's reasons, plus the pinned ps environment and the start-time form check on both the reading and the record that round 4's finding needs).

Round 5: main (2f08c24e05a8) merged. The only conflict was SPEC §12s.3's "Built so far". Main added the node's side
of the lease's renewals (`leaseclock.py`, §12s.5) and still listed "the runs listed in `hello`" as to come. The
resolution keeps main's lease-clock text and points to §12s.6 for the runs in `hello`, which this branch builds
(`backends` stays `[]`). `keeper.py` and `serve.py` merged cleanly: `serve` installs `leaseclock`'s handlers beside
the states, the sweep after hello and the hourly sweep. There was no review finding to answer this round besides the
conflict. Ran after the merge: tests/test_compute_restart_states.py (6), test_compute_lease_clock.py with the keeper
and keeper-deadline tests (17), the worker protocol, output and readings tests (20), test_runs_outlive_engine.py with
test_runs_adopted.py (32), all passing; ruff clean. Not tested: a real macOS, the hourly sweep's timer.

Overrun reason: about 315 net lines against 200 (round 4's reasons; the merge adds none).
