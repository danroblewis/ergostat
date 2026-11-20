# warm2: warm processes for blocks, built on daemons

Branch `warm2`, from origin/main at dd91518. Gap (`docs/GAPS.md`, *Warm workers instead of a process per item*;
`docs/proposals/latency.md`): a process per item costs its start-up on every item (2.2x the latency of warm
processes, measured on branch `warm`). The first attempt (branch `warm`, definition in
`docs/roadmap/overnight/leasekill.md`) failed its gate twice: a child's CPU was not charged to its item, the
environment leaked between items, `done` was read loosely, the owner's stop was misattributed, and one item's state
could reach the next. This attempt builds on the daemons (SPEC §9.7), which already give a strict, run-tagged `done`,
an item's `env` in its line and never in the process's environment, per-run `cancel`, supervision and whole-group
kills; it adds what a daemon cannot give: one item at a time per process, so its CPU is the item's.

## Definition of done

**`warm: true` on a daemon** (a block's `daemon:` map or a top-level `daemons:` entry) is the owner's declared
promise that the program keeps no state between items. Such a daemon is `concurrency` processes of its command, each
holding **one run at a time**; the dispatcher's room is the sum of the idle ones. Everything else is the daemon
protocol unchanged (strict `{"done": EXIT, "run": ID}`, lines tagged with their run, `cancel`, `stop`, heartbeats,
restarts, back-off, given up, swaps). A warm daemon serves blocks only (a sensor naming one is an error), and
`recycle: M` (default 1,000; only with `warm`) is the most items one process serves.

1. **Per-item accounting.** Each run handed to a warm process is charged the CPU its process group used while it
   held the run: the process's own CPU and the CPU of every descendant it reaped (`RUSAGE_CHILDREN`, read from
   outside: `proc_pid_rusage` on macOS, `/proc/PID/stat` on Linux), as the difference between hand-over and `done`,
   plus the CPU of any member of its group still alive at `done`. The run's `resources` say `method: warm`. The
   charges of a process's runs never exceed its whole life's CPU, and what is left over is its start-up.
2. **A fresh environment per item.** The process's environment holds only what every item shares (as for any
   daemon); each item's `ERGOSTAT_*` values travel in its line, complete, including `ERGOSTAT_WORKDIR`. The guide's
   example passes `{**os.environ, **env}` to what it starts and never writes `os.environ`.
3. **Strict done,** from the daemon protocol: only `{"done": EXIT, "run": ID}` with a whole-number `EXIT` and the
   run it holds ends it.
4. **A process that misbehaves is recycled:** a line tagged with a run it does not hold (a late `done` from the item
   before), a line tagged with nothing, or a member of its group still alive at `done` (killed with the group). It is
   restarted as any daemon is (`ergostat.daemon.restarted`, counted toward giving up), after the run it held has
   ended, and is handed nothing in between. A process whose run was cancelled (lease expired, timeout, the owner's
   stop) is replaced once it says `done`, uncounted; one that served `recycle` items too. The owner's stop is said
   only on the run it stopped, and only when that run did not finish well.
5. **The promise is checked:** `ergostat block NAME --check-warm FILE` (FILE: the input of one run, as JSON) runs
   that input twice on one fresh process and once on each of two other fresh processes, and compares what each run
   printed and its exit (`daemons/warmcheck.py`): the same, the promise holds for that input; the second run on one
   process differing from a fresh process's run, state leaked; two fresh runs differing, the program is not
   deterministic and nothing is concluded. It says that it runs the program for real, four times.

The latency bench (`scripts/latency_bench.py synth 100 --warm N`, watchdogged at 1,500 threads and 6 GB) measures it
again against a process per item. SPEC §9.7 and the agent guide say all of the above; GAPS records it.

## Acceptance tests

- `tests/test_warm.py::test_warm_processes_hold_one_item_at_a_time_and_are_reused`
- `tests/test_warm.py::test_a_childs_cpu_is_charged_to_its_item`
- `tests/test_warm.py::test_no_items_environment_reaches_the_process_or_the_next_item`
- `tests/test_warm.py::test_a_late_or_loose_done_never_ends_the_next_item_and_recycles_the_process`
- `tests/test_warm.py::test_the_owners_stop_is_said_only_on_the_run_it_stopped`
- `tests/test_warm.py::test_a_process_leaving_a_child_running_is_recycled_with_its_group`
- `tests/test_warm.py::test_processes_are_recycled_after_m_items_uncounted`
- `tests/test_warm.py::test_the_check_finds_state_kept_between_items`
- `tests/test_warm.py::test_warm_is_checked`
- the four suites, rc 0; ruff.

## Size budget

400 net lines outside `tests/` and `docs/` (code, schema, scripts).

## Where it stopped

Parked under the kill rule (the second failed gate: the final re-review, 2026-11-20). The first review's three
blocking findings are fixed (846ced4: the CPU charged as the group's total at `done` less its total at hand-over; the
caps of 32 per warm daemon and 64 in all; `--check-warm` strict about `done`), but moving the hand-over snapshot
outside the supervisor's lock opened a race:

- **Blocking: a run held but never handed over.** `daemons/work.py` holds the run under the lock (line 47), then
  takes the snapshot and calls `hand(line)` outside it (lines 61-62). A `_drain` in between (`daemons/supervise.py`
  144-152) queues `stop` and the sentinel, the writer thread exits, the run's line is never sent, and the tick's
  "ended while draining" fails the run uncounted (not requeued). Either fix closes it: `hand` refuses when `stop` was
  already queued, and the run is given back (requeued); or `stop()` requeues the runs it holds that were never
  handed over.
- **Non-blocking:** a failed hand-over snapshot (`before` empty) charges the group's whole life: guard when `pgid` is
  not in `before` (charge nothing, or say so). `revive` and `_restart` can briefly exceed the 64-process cap while the
  old processes die.
- **Tests needed:** the hold/hand gap with a drain in between (the run requeued, never failed); and revive at the cap
  (never more than 64 warm processes alive at once).

### Round 1 after parking (2026-11-20): every finding above fixed

- **The hold/hand race (blocking): closed by the first fix.** `Process.stop()` sets `stopping` and queues `stop`
  under the process's own lock; `Process.hand(run, line)` checks under that lock, so a run's line is queued before
  `stop` or not at all. A run refused that way (or no longer held, after a restart's `fail_all`) is ended
  `requeue=True`: given back uncounted ("was stopping before the run was handed over"), never failed. I picked
  this fix over requeueing in `stop()` because it is the more local and reversible change: one method and one flag.
- **A failed hand-over snapshot:** `usage.charge` gives `None` when the leader is not in `before`. That run's
  `resources` have no `cpu`, only `unmeasured` (the cost rollups already treat a missing `cpu` as unknown).
  Elsewhere than macOS and Linux this now says unmeasured instead of charging 0.
- **The cap during revive and restart:** `revive` claims a fresh warm process only while `_warm_live() < WARM_ALL`.
  The rest are left `starting` for the tick, which keeps to the cap. A warm process killed by `_restart` stays in
  `Supervisor.dying` and counts toward the cap until its leader has ended.
- **Tests added** (`tests/test_warm.py`), each seen failing with its fix disabled:
  `test_a_run_held_but_drained_before_its_hand_over_is_given_back_never_failed`,
  `test_revive_never_has_more_warm_processes_alive_than_the_cap` (4 alive under a cap of 2 without the fix), and
  `test_a_hand_over_not_read_charges_nothing`.
- Size: about 364 net lines outside `tests/` and `docs/`, within the 400 budget. Still to do: the gate's review, and
  the four suites under the watchdog (the factory's).

### Round 2 (2026-11-20): a cancel before the hand-over

- **Blocking (the queue's finding): a cancel could reach a warm process before its run's line,** in the same gap
  between hold and hand-over, with cancel instead of the drain coming in between. Closed under the process's own
  lock. `Handle.sent` marks a run whose line was queued (`hold` sets it for a daemon that is not warm, `hand` for a
  warm one). `Hands.cancel` marks the run cancelled under `p.lock` and queues `cancel` only if the line was sent.
  `Process.hand` refuses a run already cancelled. That run ends without being sent and is not requeued: its note is
  "stopped as the owner asked" for the owner's stop, or "cancelled before it was handed over" (a lease kill's note
  is still its `killed: ...`). The process is not blamed, recycled or restarted. Neither its line nor a `cancel`
  ever reaches the process. I chose this over a requeue because a cancelled run is meant to end, and it is the more
  local change: one flag and two checks.
- **Test added:** `test_a_run_cancelled_before_its_hand_over_is_never_sent` (the owner's stop between hold and
  hand-over). It fails with the check disabled: the line is sent and the stop is not honoured.
- Size: about 10 more net lines, still within the 400 budget.

### The fast suites after round 2 (2026-11-20)

`unit` failed, but its tail was cut off before any failure was printed. Under load (`-n 8`), one warm test failed
every time: `test_an_unreaped_child_is_said_not_held_against_the_process`. Its test program dropped its `Popen` of
`true`, and CPython's `Popen.__del__` reaps a child that has already ended, which on a loaded machine it often has.
So no child was left unreaped, and ergostat was right to report none. The test program now keeps the `Popen`. No
ergostat code changed. The failure seen was in the test program, not the code; this is the only one found.

### Round 3 (2026-11-20): review warm2-1's remaining findings

- The round-2 blocking finding (a cancel before the hand-over) was already fixed in d5caff6, and its test passes.
- `scripts/latency_bench.py`'s usage example now uses `--warm 10`: 5 steps x 10 = 50 warm processes, within the cap
  of 64, which matches the recorded runs. `--warm 20` would fail the model's check.
- `tests/test_warm.py`: the block is named `triage`, no longer `worker`. The `envleak` mode is now used:
  `test_the_check_finds_state_kept_between_items` asserts that `--check-warm` reports state kept when a program
  writes an item's env into `os.environ`. The program writes it after it reports, so the next item sees the leak.
  Before that move, this assertion failed: the leak was written before the report, so every run printed the same
  output.
- `tests/test_warm.py`: 18 passed. Ruff is clean. No ergostat code changed.
- Not done: merging `main` into the branch (`main` is ahead by several merges). This session was not allowed to
  run `git merge`, so the factory's merge and a rerun of the suites remain.

## Where it stopped

Parked by the factory (review/warm2-2, 2026-11-20 05:20).

Failed its gates twice (the kill rule). Blocking findings:
- docs/roadmap/overnight/warm2.md:136-137 (lesson-7): origin/main, by the branch's own account ahead by several merges, was not merged in and the four suites were not run after it. The house rules need both before 'done'. The supervisor and daemon code this branch rewrites (supervise.py, work.py, proc.py) has already conflicted with main once (61cd918), so a merge that passes for each side alone is a real risk to the main people install.
- docs/SPEC.md:2325 and ergostat/daemons/usage.py:8 (lesson-8; warm2-1's finding, not addressed in round 3): both still say 'CPU used after done falls into the next run's charge'. Process.hand (proc.py) takes the next run's starting snapshot at its hand-over, so CPU used between one run's done and the next hand-over is charged to no run; only CPU still in use after that snapshot reaches the next run. The same SPEC sentence also says time outside a run is the process's own. Say what the code does: after done and while idle, the process's own (left over, with its start-up). No test backs the current claim.
- ergostat/cli/spec_cmds.py:197 (lesson-3; warm2-1's finding, not addressed): json.loads(Path(args.check_warm).read_text()) has no error handling. A missing or unreadable FILE, invalid JSON, or JSON that is not an object (warmcheck._run calls given.get) ends in a traceback instead of a message naming the file. Catch OSError/ValueError and check isinstance(given, dict), say what is wrong, and return a usage rc.

## Where it stopped (gap/warm-continued, round 1, 2026-11-20)

`main` (f158e00) is merged into the branch (2ca24c7, the factory's merge). No conflict markers are left. Since that
merge: `tests/test_warm.py` 21 passed, `tests/test_daemons.py` 26 passed, `tests/test_cli_fallback.py` 17 passed,
and ruff is clean. These were run one file at a time. **The four suites were not run here** (that is the factory's
job, under the watchdog). They are what is left before done.

Every finding of the reviews before this round:

- **review/warm2-2, merge `main` and rerun (lesson-7):** merged (2ca24c7). `--check-warm` is in main's
  `goodmodel.ACTS`, so the read-only fallback never runs it on the last good model, and `test_cli_fallback.py`
  passes. The four suites after the merge are still the factory's to run.
- **review/warm2-2 and warm2-1, the CPU-after-`done` sentence (lesson-8):** fixed in 056a0c6. SPEC §9.7 and
  `daemons/usage.py` say that CPU after `done` and before the next hand-over is no run's (the process's own, left
  over with its start-up), and that only CPU after the next hand-over's snapshot is that run's.
- **review/warm3-2, the sentence's second half untested:** a new test,
  `test_cpu_still_in_use_after_the_next_hand_over_is_that_runs`. The program starts a thread after its first
  `done` that waits for the next item, then spins 0.6 s. That run is charged at least 0.5 s, and the first run less
  than 0.4 s. It fails (`0.0 >= 0.5`) when the hand-over snapshot is taken 1 s after the line is sent; I made that
  change in `Process.hand` for the check and then took it out.
- **review/warm2-2 and warm2-1, `--check-warm FILE` errors (lesson-3):** fixed in 056a0c6
  (`test_the_check_says_what_is_wrong_with_its_file`). A FILE that is missing, unreadable, not JSON, or not an object
  is said on stderr with the file named, and the command returns rc 2.
- **review/warm2-2, rc 2 used for two things:** "nothing concluded" is rc 3, as SPEC §9.7 says (056a0c6).
- **review/warm3-1, GAPS stale:** the entry now names `factory/warm3`, says that `main` is merged, and says that
  only the four suites after the merge remain.
- **review/warm3-2, gate 1 (`warm3.md` not the first commit):** this gap's named definition is this file, `warm2.md`.
  `warm3.md` was a copy of it plus warm3's rounds, so it is now cut to a pointer here plus its own "Where it
  stopped" sections. The same was done for continue-branch2.md, which is already on main. History was not
  rewritten.
- **review/warm3-1 and warm3-2, the reviewers could not run tests:** the counts above are from this session's runs
  after the merge.

No ergostat code changed this round. The only code change was a new test (with its mode in the test program), so
the size outside `tests/` and `docs/` is unchanged and within the 400 budget.
