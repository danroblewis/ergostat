# daemons-left-over: a daemon's lines are taken in batches per run, a sensor daemon's observations are recorded (capped, with drops reported), and a new daemon's CPU is sampled early rather than only every 30 s
depends-on: []

## The gap (as found on main)

- **Lines one at a time.** `ergostat/daemons/proc.py::Process._read` iterates `self.proc.stdout` line by line and calls `self.line(text)` for each one. For a run's line, `line` calls `h.take([one line])`. Each call is a `Said.lines` transaction (`ergostat/spec/engine.py` around line 924). A daemon run that prints 1,200 lines therefore makes 1,200 record transactions. A `run:` block's process goes through `ergostat/spec/stream.py::pump` instead, which batches the lines of each read, up to `BATCH = 500`.
- **Observations not taken.** A `run:` sensor's event lines about items go through `engine.observations(text)` and then `Engine._observer(name)`, which records each as an event whose source is the sensor (SPEC §6, "A `run` sensor may also print what it observed about items"). `Process.line` passes on only `run`, `request` and push-`reading` lines. Any other line, including `{"event": ..., "item": ..., "sensor": ...}`, is logged as stray and dropped.
- **Sampled every 30 s.** `ergostat/daemons/supervise.py:28` creates `SAMPLER = Sampler(30.0, ...)`. `Sampler._loop` waits a whole interval before its first sample. A daemon that lives less than 30 s therefore has no samples, and `status()` (Agents page, `daemons.json`) shows its CPU and memory as nothing until it ends.

## Definition of done

### 1. A daemon's lines are taken per read, batched per run (`ergostat/daemons/lines.py`, new; `proc.py`)

- `lines.py` holds `BATCH = 500` and a pure function `plan(texts: list[str]) -> list[tuple]`. It turns the whole lines of one read into steps, in this order:
  - A **run line** is a JSON object with a string `run` and no `done` key. It is appended to that run's pending list. When the list reaches `BATCH` lines, it is emitted at once as `("take", run, [lines])`, each line with `run` removed, exactly as `line` does today.
  - Every **other line** is emitted as `("one", text)`: `done` lines, requests, push readings, observations, heartbeats, non-JSON lines, untagged lines, and lines whose `run` is not a string. A `done` line for run X emits X's pending lines first, then itself. Other kinds of line do not emit anything pending first.
  - At the end of the read, the runs' pending lists are emitted in the order of each run's first line in the read.
  - Within a run, lines are emitted in the order they were printed, and a run's `done` always comes after the run's earlier lines.
- `Process._read` reads with `os.read(fileno, 65536)` (blocking) instead of iterating lines:
  - It keeps a partial line until its newline arrives, and sets `last_out` on every read.
  - It runs `plan` on each read's whole lines. For `("take", run, lines)` it looks the run up under `self.lock`. If the run isn't held, each line goes to `stray`, as today. If it is held, it calls `h.take(lines)` once.
  - For `("one", text)` it calls `self.line(text)`. `line` stays the per-line path, so the strict-`done` rule, warm recycling and every existing stray rule are unchanged.
  - If `take` raises an exception, each line of that batch is written to the log as dropped with `fault=False` (today this happens per line). The reader never ends because of it.
  - At EOF, a non-empty partial line is handled as a last line. Then come `proc.wait()` and `ended.set()`, as today.
  - A partial line longer than `LINE_MAX = 1 MiB` is discarded up to its next newline and logged once as dropped ("a line over 1 MiB"). The buffer never grows past that (lesson-4).
- The reader's handling is exposed as `Process.chunk(data: bytes)` (one read's bytes) and `Process.chunk(b"", eof=True)`, so tests can give it a read whose contents are known.

### 2. A sensor daemon's observations are recorded (`ergostat/daemons/observe.py`, new; `proc.py`, `work.py`, `supervise.py`)

- **The line.** An observation is one of these, tagged with `"sensor": "STOCK.SENSOR"`:
  - an event line as a `run:` sensor prints it: `{"event": T, "item": I, "data": {...}, "sensor": S}`;
  - a relayed message: `{"message": {...}, "sensor": S}`.

  It has no `reading` key. A line with both `reading` and `event`/`message` is stray ("a reading or an observation, not both").
- **Routing.** `Process` takes a new `on_observe(sensor, obj) -> bool` callback beside `on_push`. `Process.line` tries it for such lines after `request` and before push.
  - The supervisor answers it through `Hands._observed(daemon, sensor, obj)`. A line is accepted only when `sensor` names a sensor whose `daemon` is this daemon.
  - That set is `self.observers` (a dict keyed by `(daemon, "STOCK.SENSOR")`), rebuilt in `sync` under the lock next to `self.push`.
  - Any other sensor name returns False, and the line is logged as stray. It is never recorded under some other source (lesson-3).
  - Warm daemons serve no sensors, so for them it is always stray.
- **Validation and recording.** The line, with `sensor` removed, is validated by `engine.observations(json line)`, the same function a `run:` sensor's output goes through. It is recorded by `Engine._observer(sensor_name(stock, sensor))`.
  - Accepted events go into the record with that sensor as their source and fold into their items.
  - A refused observation (own type, no `/` in the item, bad type name) gets one `sensor.refused`, `{why}`, as for a `run:` sensor.
- **The cap.** `observe.py` defines `OBSERVE_PER_S = 50`, a limit per sensor per one-second window, counting accepted and refused lines alike.
  - A sensor's window opens at its first observation line, at clock `t0`. `observe._now` is `time.monotonic`, a module attribute so tests can replace it.
  - A line at `now` with `now - t0 >= 1.0` closes the window and opens a new one at `now`.
  - Within a window, lines past the 50th are dropped and counted. They are not recorded and not logged one by one.
  - The window's state is read, decided and written under `observe.Observed.lock`. The record writes happen after the lock is released (lesson-1).
- **When drops are reported (answers the plan review's point 3).** A window with drops is reported as exactly one `sensor.refused` with `data: {why: "N observations dropped: more than 50 a second", dropped: N}`, where N is that window's full count. It is reported at whichever comes first:
  - (a) the sensor's next observation line after the window closes;
  - (b) the supervisor's next `tick` (every `TICK = 0.2` s) at which `_now() - t0 >= 1.0`: `Supervisor.tick` calls `Observed.flush(now)`;
  - (c) `Supervisor.close()`, which flushes every window, open or not.

  So a burst with nothing after it is reported within about 1.2 s, or when ergostat stops. Each window's count is popped under the lock, so it is reported once only.
- A daemon's push readings (`PUSH_EVERY`) are unchanged.

### 3. A daemon is sampled soon after it starts (`ergostat/costs/sampler.py`, `supervise.py`)

- `Sampler(interval=INTERVAL, name=..., floor=FLOOR, thread=True)`, where `FLOOR = 1.0` is a named parameter (review point 1).
- Each `Tracker` has `gap` and `due`. `track(proc, now=None)` sets `gap = min(floor, interval)` and `due = now + gap`, then sets `self.wake`.
- `Sampler.wait(now)` returns `max(0, max(self.last + self.floor, min(t.due for t in runs)) - now)`. `self.last` starts at `-inf`.
- The loop computes `wait(now)`. While that is above 0, it waits on `wake` for that long, clears it and computes again. A wake recomputes the wait but never samples by itself. The loop samples only when `wait(now) == 0`.
- `sample(now=None)` sets `self.last = now`. For every tracked run it sets `gap = min(2 * gap, interval)` and `due = now + gap`.
- The result: a new daemon is sampled at about 1, 3, 7, 15 and 31 s, then every 30 s. Samples are never closer than `floor` apart, however many processes start.
- The daemons' sampler is `Sampler(30.0, "ergostat-daemon-sampler", floor=1.0)`. The runs' sampler stays `Sampler()` (interval 1.0, floor 1.0). Its gap starts at 1 and stays at 1, so runs are sampled as before: one listing per second at most, the first about 1 s after a run starts.
- `thread=False` builds a sampler that never starts its thread (for deterministic tests). Callers of `track(proc)`, `finish`, `stats` and `Tracker(proc)` are unchanged.

### 4. Docs

- **SPEC §9.7, protocol "Out" table.** Add the observation line (both forms), what makes it stray, and the 50-a-second cap with how drops are reported (the three triggers above).
- **SPEC §9.7, "Each item is still a run".** "sampled every 30 s" becomes "sampled about 1 s after it starts, then at doubling gaps up to every 30 s (never two samples within 1 s)". Add one sentence: lines that arrive together are taken together, per run, up to 500 at once, in the order printed.
- **SPEC §6, the `run` sensor observations paragraph.** One sentence: a daemon's sensor may print the same lines tagged with `sensor` (§9.7).
- **`docs/RUNTIME.md`.** Line 209's "every 30 seconds" is changed to say the same as SPEC. Nothing else there changes.
- **The `ergostat/costs/sampler.py` docstring.** It describes the ramp and the floor.
- **`docs/GAPS.md`.** The "Daemons, left over" bullet leaves its open section. One entry, first under `## Done recently`, says what was done and cites this branch's definition file.
- No sentence anywhere claims observations are "never" lost. The docs say over-cap ones are dropped and counted (lesson-8).

## Files to touch

- `ergostat/daemons/lines.py` (new)
- `ergostat/daemons/observe.py` (new)
- `ergostat/daemons/proc.py`
- `ergostat/daemons/work.py`
- `ergostat/daemons/supervise.py`
- `ergostat/costs/sampler.py`
- `docs/SPEC.md`
- `docs/RUNTIME.md`
- `docs/GAPS.md`
- `tests/test_daemon_lines.py` (new)
- `tests/test_daemon_observations.py` (new)
- `tests/test_sampler_ramp.py` (new)
- `tests/test_daemons.py`
- `docs/roadmap/overnight/daemons-left-over.md`

## Risks

- **lesson-9 (a test that can't fail).** A cap test run through a real pipe could see 1,200 lines arrive in several reads of fewer than 500, and then it passes with `BATCH` removed. The cap is therefore tested on `plan` directly and on `Process.chunk` with all 1,200 lines in one call, asserting sizes `[500, 500, 200]`. The ramp is tested deterministically on `wait`/`sample` with explicit clocks. The report must say, for each new test, which break was tried and that the test failed.
- **lesson-10 (load flakes).** The observation cap test fixes `observe._now`, so 60 lines can't cross a second boundary. The floor test asserts only lower bounds on the gaps between samples, which load can only widen. The burst-reporting test waits on a condition with a deadline (≥ 5 s) and never uses a fixed sleep.
- **lesson-3 (failing open).** Two cases:
  - an observation tagged with a sensor this daemon doesn't serve, or with an unknown one, could be recorded under the wrong source or dropped silently. It must be stray-logged and not recorded.
  - a drop count recorded only on the next observation would never report a burst with nothing after it. Reporting is also done by the supervisor's tick and by close.
- **lesson-4 (no ceiling).** The observation rate is capped per sensor (50/s). Each batch is capped (500). The sampler is floored (≥ 1 s between samples, however many processes are tracked or wakes arrive). A partial line is capped (1 MiB).
- **lesson-1 (check, then write).** The window check (open/close, count, drop) and the pop of a drop count happen under `Observed.lock`. A reader thread and the supervisor's tick can then never both report one window, or both pass the 50th line.
- **lesson-8 (claims wider than the code).** Docs must not claim "every line taken in one transaction" or "never sampled late". The claims are "up to 500 at once, of what arrives together" and "about 1 s after it starts".
- **lesson-7 (two things merged).** `supervise.py` is being touched by the in-review gap `daemons-across-the-engine-s-own-restarts`. Merge origin/main and run the suites again before calling the branch built.
- **lesson-13 (stay inside the gap).** `tests/test_daemon_docs.py` and existing daemon tests that fail for reasons unrelated to this change are reported, not fixed here.

## Acceptance tests

`tests/test_daemon_lines.py`:
- `test_one_reads_1200_lines_of_a_run_are_taken_as_500_500_200`
  - Runs `plan` on 1,200 lines tagged `A`. The `take` step sizes are exactly `[500, 500, 200]`, in printed order.
  - Then it gives the same 1,200 lines as one `Process.chunk` to a real `Process` (a `python3 -c "import time; time.sleep(30)"` daemon) holding run A. The recorded `take` calls have sizes `[500, 500, 200]`.
  - Fails with `BATCH` removed (`[1200]`) or with per-line taking (1,200 calls).
- `test_interleaved_runs_lines_are_batched_per_run_in_order`
  - A, B, A, B, ... (10 each) in one read become one take for A and then one for B, each in printed order.
  - Fails if the code groups consecutive runs only (20 takes) or reorders lines.
- `test_a_runs_done_comes_after_its_lines_in_the_same_read`
  - The chunk is `A1, B1, A done, A2-late`.
  - A's take `[A1]` is called while `h.done` is not yet set. A is then ended with code 0. `A2-late` is stray (logged "no run of that id held"). B's take is `[B1]`.
  - Fails if pending lines are flushed only at the end of the read.
- `test_a_partial_line_waits_for_the_rest_and_eof_takes_the_last`
  - A line split over two chunks is taken once, whole.
  - A last line with no newline is handled at `chunk(b"", eof=True)`.
- `test_an_overlong_line_is_dropped_and_the_reader_goes_on`
  - 2 MiB with no newline, then a valid run line: the valid line is taken, the log says "a line over 1 MiB", and the partial buffer never exceeds `LINE_MAX`.
- `test_a_take_that_raises_drops_its_batch_and_the_reader_goes_on`
  - The first batch's take raises. Its lines are logged as dropped. The next chunk's lines are taken.

`tests/test_daemon_observations.py`:
- `test_a_sensor_daemons_observations_are_recorded_from_its_sensor` (real engine)
  - A `{daemon: ..., push: true}` sensor's daemon prints a reading and `{"event": "case.met", "item": "case/a", "data": {"x": 1}, "sensor": "q.main"}`.
  - One `case.met` event is recorded with source `q.main`, and item `case/a` folds with `x == 1`.
  - A relayed `{"message": ..., "sensor": "q.main"}` is routed as a `run:` sensor's would be.
  - Fails on main (the line is stray).
- `test_an_observation_for_a_sensor_not_of_this_daemon_is_stray_not_recorded`
  - Lines tagged `nope.main`, and lines tagged with a sensor of another daemon: nothing is recorded and the log says dropped.
  - Lesson-3: fails if routing falls back to any source.
- `test_a_refused_observation_is_said_as_for_a_run_sensor`
  - An item without `/`, and type `agent.ran`: one `sensor.refused` each with the same `why` that `observations()` gives. No event is recorded.
- `test_more_than_50_observations_a_second_are_capped_and_the_drop_reported_once`
  - `observe._now` is fixed at 100.0, and 60 valid lines are fed through `Hands._observed`.
  - Exactly 50 events are recorded, and no `sensor.refused` yet.
  - With the clock at 101.0 and `flush` called, exactly one `sensor.refused` with `dropped == 10`. A second `flush` still gives exactly one.
  - Then 50 more lines are all recorded.
  - Fails with the cap removed (60), with a report at the first drop (a count ≠ 10), or with a double report.
- `test_a_burst_with_nothing_after_it_is_reported_by_the_supervisor` (real engine and loop)
  - The daemon prints 60 observation lines in one write, then only heartbeats.
  - A `sensor.refused` with `dropped == 10` appears within a 5 s `wait_for`.
  - Fails if the report is triggered only by the next observation.
- `test_a_burst_just_before_ergostat_stops_is_reported_at_close`
  - The clock is fixed, so the window is still open. 60 lines, then `Supervisor.close()`: exactly one `sensor.refused` with `dropped == 10`.

`tests/test_sampler_ramp.py`:
- `test_a_ramped_sampler_samples_early_then_at_its_interval`
  - `Sampler(interval=0.8, floor=0.2, thread=False)` tracks a live process at now = 0. Successive `wait()`/`sample(now)` give waits of exactly `[0.2, 0.4, 0.8, 0.8]` (±1e-9).
  - Fails with a flat interval (`[0.8, ...]`) or with no ramp cap (`1.6`).
- `test_the_sampler_never_samples_sooner_than_its_floor`
  - Deterministic part: with `floor=1.0`, after `sample(10.0)`, a run tracked at 10.1 with its `gap` forced to 0.1 gives `wait(10.1) == 0.9`.
  - Real-thread part: `Sampler(30.0, floor=1.0)` with `sample` wrapped to record times. 20 short `sleep` processes are tracked 0.05 s apart (each `track` sets `wake`). Every gap between consecutive samples is ≥ 0.95 s, and at least one sample is taken within 3 s.
  - Fails if a wake samples at once.
- `test_the_samplers_keep_their_intervals_and_floor`
  - `costs.sampler.SAMPLER` has interval 1.0 and floor 1.0. `daemons.supervise.SAMPLER` has interval 30.0 and floor 1.0.
  - A tracker of the runs' sampler keeps `gap == 1.0` after three samples.

`tests/test_daemons.py`:
- `test_a_short_lived_daemon_is_sampled_before_it_ends`
  - A sensor daemon that exits after about 4 s. Within 3 s of `ergostat.daemon.started`, `slot.tracked.samples >= 1` while its process is still alive (polled with `wait_for`).
  - Fails on main (the first sample is at 30 s).
- `test_a_daemon_runs_1200_lines_are_all_recorded_in_order`
  - A program block's daemon prints 1,200 `{"event": "x.seen", "item": ..., "data": {"i": n}, "run": ID}` lines in one write, then `done`.
  - All 1,200 are recorded for that run, in order of `i`, and the run ends `agent.ran`.

The existing `tests/test_daemons.py` and `tests/test_warm.py` pass unchanged. They cover strict `done`, stray lines, push and warm recycling through the new reader.

## Size budget

260 net lines outside `tests/` and `docs/`:
- `lines.py`: about 45
- `observe.py`: about 60
- `proc.py`: about +50
- `work.py` and `supervise.py`: about +35
- `sampler.py`: about +40
- the rest is margin

An overrun needs a written reason in "Where it stopped".

## Notes from the plan review (answer each)

- lesson-1 is named under Risks but has no test that can fail. The window check, the drop count and the pop of the drop count are meant to be atomic under Observed.lock, yet every listed observation test is single-threaded, so a version that reads, decides and writes without the lock passes them all. Add a test that monkeypatches the step between deciding and writing (for example, wrap the window update) to run a competing Observed.flush(now) or a second observation inside the gap. Assert exactly 50 recorded and exactly one sensor.refused with dropped == 10. The test must fail when the lock is removed.
- test_the_sampler_never_samples_sooner_than_its_floor cannot fail with the floor removed. Its deterministic part forces gap = 0.1 but leaves due = 11.1 (set by track at 10.1), so wait(10.1) is 1.0 with or without the floor, not 0.9. Its real-thread part also passes without a floor, because after the first sample every tracker's gap doubles to 2 and they fall due together. Force due = 10.2 explicitly, keep the assertion wait(10.1) == 0.9, and state that the test fails (0.1) with the floor removed. Without that, the SPEC claim 'never two samples within 1 s' has no guarding test (lesson-8, lesson-9).
- A run line in plan() must be exactly what Process.line would hand to take() today. If requests, readings or observations can carry a string `run` field, say which key wins, so that a request tagged with a run is not swallowed into a batch. Add one plan() case for it.
- One bad line in a take now drops up to 499 good lines, where today it drops one. Either fall back to taking the batch line by line when take raises (take is one transaction, so a retry can't double-record), or state the wider loss in the definition and the docs.
- Say how bytes are decoded now that _read uses os.read (utf-8 per line with errors='replace', or invalid lines go to stray) and test a non-UTF-8 line. Today a decode error in text mode may end the reader.
- LINE_MAX newly drops legitimate lines over 1 MiB. State that in SPEC §9.7 (lesson-8).
- Sampler.wait with no tracked runs: min() of an empty set must mean 'wait on wake with no timeout', not raise. Test it.
- Hands._observed must read self.observers under the same lock sync uses to rebuild it. Apply the cap only after routing succeeds, so stray sensor names can never create windows (the dict stays bounded by the configured sensors).
- Supervisor.close() must flush the observation windows before the engine or record is closed. Assert the order in the close test.
- test_a_short_lived_daemon_is_sampled_before_it_ends: assert the process is still alive at the moment the sample count is read, not only that samples >= 1.

## Where it stopped

Round 1: built. Every point of the definition is in, every acceptance test exists and passes, and so do the existing
`tests/test_daemons.py`, `tests/test_warm.py`, `tests/test_daemon_docs.py` and `tests/test_run_costs.py`. Size:
218 net lines under `ergostat/` (budget 260).

**What is not done here.** There is no `origin` remote in this container and no network, so origin/main could not be
merged in (lesson-7). Local `main` has no commit the branch lacks. The in-review gap
`daemons-across-the-engine-s-own-restarts` also touches `supervise.py`, so the coordinator should merge origin/main
and run the suites again before calling the branch built. The full unit suite and the four browser files were not
run here; the factory runs them under the watchdog. The test files touched were run one at a time.

**Answers to the plan review.**
1. *lesson-1 has no test that can fail.* Added `test_the_window_is_judged_and_written_under_its_lock`
   (tests/test_daemon_observations.py). It wraps `Observed._decide`, the step between reading the window and writing
   it, and runs two rivals in that gap: a competing line at the 50th line, and a competing `flush` at the line that
   closes the window. It asserts exactly 50 recorded and exactly one `sensor.refused` with `dropped == 10`. The lock
   was removed from `admit` and `flush`: 51 recorded. It was then removed from `flush` only: `[10, 10]`, a double
   report. The supervisor's tick is disabled for that test, so its own flush can't hide the race.
2. *The floor test can't fail.* Its deterministic part forces `gap = 0.1` and `due = 10.2` and asserts
   `wait(10.1) == 0.9`. With the floor removed it gives 0.1 and fails (tried).
3. *Which key wins in `plan`.* `run` wins, as in `Process.line` today: a request or a reading that carries a string
   `run` is that run's line. The case is `test_a_run_line_is_what_line_takes_and_every_other_line_is_one`.
4. *One bad line in a take drops the batch.* Kept as the definition says, and stated in SPEC §9.7 ("should taking a
   batch fail as a whole, each of its lines is said dropped in the log"). This is the more reversible choice: retrying
   line by line could record a line twice if a take failed after part of its batch was written. Also,
   `Said.lines` already catches each line's own failure and refuses only that line, so a take that raises has failed
   as a whole (for example, its run's log is closed).
5. *Decoding.* Each whole line is decoded as UTF-8 with `errors="replace"`, as before. A non-UTF-8 line is tested in
   `test_a_partial_line_waits_for_the_rest_and_eof_takes_the_last`: it is taken, with U+FFFD in place of the bad byte.
6. *LINE_MAX in SPEC.* SPEC §9.7 says a line over 1 MiB is dropped, said once in the log, and never held.
7. *`wait` with no runs.* It returns None, and the loop then waits on `wake` with no timeout. Tested in
   `test_a_ramped_sampler_samples_early_then_at_its_interval`.
8. *`_observed` and the lock; the cap after routing.* `self.observers` is read under `self.lock`, the lock `sync`
   rebuilds it under. A window is made only after routing succeeds, so its keys are only configured sensors.
9. *close before the record.* `Supervisor.close` flushes every window after its processes are stopped, so lines read
   while they stop are counted too. That is before `Engine.close` records `ergostat.stopped`.
   `test_a_burst_just_before_ergostat_stops_is_reported_at_close` asserts the report's `seq` is before that event's.
10. *Alive when sampled.* The short-lived test reads `proc.poll() is None` in the same check that reads
    `samples >= 1`.

**Break checks (lesson-9): each break tried, the test run, and the test failed.**
- `BATCH` removed: `test_one_reads_1200_...` fails. Per-line taking (a batch of 1): 5 line tests fail.
- Grouping only consecutive lines of a run: `test_interleaved_...` fails. `done` not taking its run's pending lines
  first: `test_a_runs_done_comes_after_...` fails.
- No ceiling on the partial line: `test_an_overlong_line_...` fails. Last line not taken at EOF:
  `test_a_partial_line_...` fails. A take's exception not caught: `test_a_take_that_raises_...` fails.
- Routing falls back to a configured sensor: `test_an_observation_for_a_sensor_not_of_this_daemon_...` fails.
- Cap removed: the cap, lock, burst and close tests fail. Drops said at the first drop: the cap test fails. Drop count
  not popped (said twice): the cap test fails.
- Lock removed: the lock test fails (see 1). No flush at tick: the burst test fails. No flush at close: the close
  test fails.
- Sampler floor removed: the floor test fails (0.1). Flat interval (no ramp): the ramp test, the floor test and
  `test_a_short_lived_daemon_is_sampled_before_it_ends` fail. No cap on the ramp: the ramp test and the intervals test
  fail. A wake that samples at once: the floor test's real-thread part fails.
- `test_a_sensor_daemons_observations_are_recorded_...` fails on main by construction: the line is stray there, and
  no `case.met` is recorded.
- `test_a_daemon_runs_1200_lines_are_all_recorded_in_order` guards the integration: all 1,200 lines, in order, then
  `agent.ran`. It would also pass with per-line taking. The batching itself is guarded by the `chunk`/`plan` tests.

**Load (lesson-10).** `test_a_burst_with_nothing_after_it_is_reported_by_the_supervisor` assumes 60 lines of one
write are judged within one second of the first. The lines are admitted in the reader thread before each is recorded,
so this holds unless 50 record writes take longer than a second. If it ever fails under load, look there first.

**After the factory's unit suite failed (one F at 42%).** The tail it gave doesn't name the test. Every file that
imports the changed modules or reads the changed docs passes alone, and the touched files also pass under `-n 4`. One
real race was found and fixed in `Sampler._loop`, and it fits a failure seen only under load. The loop checked that a
run was tracked and computed its wait under two separate holds of the lock. A run that finished between them left
`wait` None, and the thread then waited on `wake` with no timeout and never ended
(`tests/test_run_costs.py::test_fifty_short_runs_...` asserts that it ends). The check and the wait are now one hold,
and `finish` sets `wake` when the last run leaves, so the thread ends at once. If the suite's failure was another
test, it is still unknown here.

**After the factory's unit suite failed again (output stopped at about 962 of 2,013 tests).** The tail shows no F and
no summary: neither pytest's nor `suite_watch.py`'s closing JSON line. `fac.suite` has no timeout, so the container's
command ended by itself with a non-zero code before the watchdog could print. That points to the container (its
12 GB or 4,096-process limit, or a kill from outside) rather than a failing assertion. The cause could not be
reproduced here. The whole suite was run in three slices, each under `-n 8 --dist worksteal`:
- `tests/test_[a-f]*.py`: 656 passed, 4 skipped, in 210 s.
- `tests/test_[g-o]*.py`: 531 passed and 3 skipped. One failed: `test_leases.py::test_the_watchdog_renews_from_what_the_holder_does_elsewhere`.
- `tests/test_[p-z]*.py`: 762 passed, 62 skipped, in 138 s.

None hung. The two daemon-related files lists, run alone, all pass.

The two failures seen under load are both in `tests/test_leases.py`:
- `test_the_watchdog_renews_from_what_the_holder_does_elsewhere`, as above.
- `test_leases_survive_a_restart_the_fold_is_the_truth`, in one of two runs of the daemon-related files under `-n 8`.

Each passes alone, and the second passed on a rerun. Both run a process per item with a TTL of 1 to 1.5 s, renewed by
`ergostat event` calls that load can slow past the TTL. They don't go through the daemons, `lines.py`, `observe.py` or
the daemons' sampler, so they are reported here and not fixed (lesson-13). Read again for a hang, the new code shows:
- no lock order that can deadlock. The supervisor's lock is never taken while a process's lock is held, and
  `Observed.lock` and the sampler's lock call nothing outside themselves.
- no wait without a deadline in the new tests.
- no read loop that can spin.

No code was changed for this round, because nothing found could be shown to be the cause. A fix made without one
would be a guess. If the factory's next run stops again, its full log (beyond the 3,000-character tail) and the
container's exit reason (OOM or not) are what is needed.

**Round 2.** There were no review findings to answer. The branch has local `main` (7b39bc94) merged in as
5985495d, and local `main` has no commit the branch lacks. `daemons-across-the-engine-s-own-restarts` is not on that
`main` yet (no `GROUPS` or `CLOSING` in `ergostat/daemons/`). Once it lands, merge it and run the suites again
(lesson-7). The branch's code under `ergostat/` was read again against the stopped suite, looking for:
- a reader that spins: `_read` breaks on an empty read and on `OSError`;
- a sampler loop that spins or never ends: `wait` and the check for tracked runs happen in one hold of the lock,
  `sample` moves every `due` forward before it lists, and nothing replaces `sample`;
- processes or threads left behind by the new tests: each `sleep` and daemon is killed and waited for, and the
  real-thread sampler's runs are finished, so its thread ends.

None was found, and no code was changed. In this round the shell did not allow listing processes, so leftover
processes could not be counted after a run. Run here, one command each: the three new test files (17 passed),
`tests/test_daemons.py`, `tests/test_warm.py`, `tests/test_run_costs.py` and `tests/test_daemon_docs.py` (92 passed),
and `ruff check ergostat tests scripts` (clean). The cause of the stopped unit suite is still unknown. The same
things as before are needed to find it: the full log and the container's exit reason.

**Round 3: the unit suite ran to its end, with one failure.** The result was 1 failed, 1961 passed and 69 skipped, in
326 s. The failure was `tests/test_leases.py::test_leases_survive_a_restart_the_fold_is_the_truth`, at line 434: after
`second.close()`, one ticket's lease still has a holder. The factory asked for the code to be fixed. **No code was
changed in this round.** This failure is outside this gap, and the definition says so (Risks, lesson-13). The reasons:
- *What the test runs.* A `program` block with `sleep 30` and leases, through `leases/dispatch.py`,
  `Engine.run_block` and `Engine.close`. It uses no daemon, so `lines.py`, `observe.py`, `proc.py`, `work.py` and the
  daemons' sampler are never reached. `Supervisor.close` has no slots, so its new `flush_observed` loops over an empty
  dict. The only changed code on its path is the runs' sampler (`Sampler()`, interval 1 and floor 1). For a run, it
  samples on the same schedule as before (one listing a second at most, the first about 1 s after the start). It
  takes the same lock in `finish`, and no lease or record code calls it.
- *The race on main that fits.* `Dispatch.tick` checks `e.stop` and then calls `take`. `take` records the lease and
  starts a thread, and that thread's `Engine.run_block` spawns the process with no second look at `stop` or
  `old.STOPPING` (`ergostat/spec/engine.py:846`–952; the only stop check is at line 723, which is another path). If
  `second.close()` runs `kill_all()` between the lease and the spawn, the new `sleep 30` is never killed. `close`
  waits 5 s for `running` to drain, gives up, and the lease is still held when the test reads it. A run whose teardown
  takes more than 5 s under load fails the same way. Either way, the cause is in main's lease and shutdown code.
- *It is already a known flake, with a gap of its own.* In earlier rounds this same test failed under load, then
  passed alone and on a rerun (see above). `review/code-health-1` records it as a main-side failure that was
  correctly reported. The fix it needs (kill a run spawned after `close()` set `stop`, and note it as
  `STOPPED_WITH_US`) is the parked lease-shutdown-race gap. The same change, made inside `upkeep-index-files` in
  `engine.py`, failed that gap's review on scope (`review/upkeep-index-files-3`).
- *Why it is not fixed here.* The fix is in `engine.py` and `dispatch.py`, which are not in this gap's files to touch.
  It would be a lease fix inside a daemons gap, which is the lesson-13 case word for word. Leaving the branch as it is
  can be undone; a lease fix in this branch has already failed one review.

Not verified here: a run of this test on plain `main` under the same load. In this round the shell refused to unpack
`main` beside the branch, so the claim that the test is unrelated rests on the reading above. The coordinator should
run the lease-shutdown-race gap, or rerun the unit suite. If this test fails on `main` under `-n 8` as well, the
branch is clear of it.

**Round 4: main (a0dc0ec9) merged in, and a flake in this gap's own test fixed.**
- *The merge.* It conflicted only in `docs/GAPS.md`. Main had moved "A renewing run killed because the engine was
  busy recording its renewal" from the open list to *Done recently*, and this branch had done the same with "Daemons,
  left over". Both open bullets are gone. Both done entries are kept, with this gap's first, as point 4 asks. Main
  changed nothing under `ergostat/daemons/` or `ergostat/costs/`. Its code changes since round 3 are the take order
  (`leases/ready.py`, `dispatch.py`) and `mode: advise` with `takes:` refused (`leases/compile.py`).
  `daemons-across-the-engine-s-own-restarts` is still not on main (no `GROUPS` or `CLOSING` in
  `ergostat/daemons/`). When it lands, the daemon suites must be run again (lesson-7).
- *The flake (lesson-10: the test, not ergostat).* After the merge,
  `tests/test_daemons.py::test_a_daemon_runs_1200_lines_are_all_recorded_in_order` failed once, when it ran in one
  command with `test_warm.py`, `test_run_costs.py` and `test_daemon_docs.py`. It recorded 2,400 `x.seen`, not 1,200.
  Alone, it passed. The cause is in the test's own daemon (`MANY`), which never moved its item out of `ready`. After
  the run's `agent.ran`, the dispatcher could take `ticket/1` again. Under load, a second run's 1,200 lines were
  recorded before `e.close()`. The reader takes each buffer once (`Process.chunk` splits the buffer and plans each
  line once), so no line was taken twice. The fix is in the test only. `MANY` prints `ticket.done` for its run before
  `done`, so the item reaches `done`. The test also asserts exactly one `agent.started`, so a second take fails as
  its own assertion and doesn't look like a line counted twice. This assertion was not shown to fail on purpose: a
  second take happens only under load. No code under `ergostat/` changed in this round.
- *Run here, after the merge, one command each:* the three new test files (17 passed); `tests/test_daemons.py`,
  `tests/test_warm.py`, `tests/test_run_costs.py` and `tests/test_daemon_docs.py` (92 passed, after the fix);
  `ruff check ergostat tests scripts` (clean). The full unit suite and the four browser files were not run here. The
  factory runs them under the watchdog. Round 3's lease failure (`test_leases_survive_a_restart_the_fold_is_the_truth`)
  is outside this gap, as said above.
