# repair-runlog: each run of a block writes to its own file, so a failure's standard error is that run's only, and the block log gets each run as one whole entry
depends-on: []

## Definition of done

The problem, as `docs/GAPS.md` (Repair, *Left*) states it: "two runs of one block at once share the block's log, so a
failure's stderr may hold the other's lines". Today `Engine.run_block` (`ergostat/spec/engine.py` ~919-1014) opens
`logs/<block>.log` for appending, writes the header at the start, hands that file to the child as `stderr=lf`, and
triage reads from the run's start offset (`pos`) to the end of the file. A run that overlaps it adds its own lines in
that range. When this branch is done, the following hold:

1. **A file for each run.** Each run of a `program` or `ai` block that `Engine.run_block` starts, daemon runs
   included, gets its own file `logs/runs/<block>/<seq>-<id12>.log`. `<seq>` is the `seq` of the run's
   `agent.started` event, in decimal with no padding. `<id12>` is the first 12 hex characters of the run id. When
   `ev.add` returns `seq: None` (the id was recorded before), the seq is read back with `events.get(id)`. If that
   lookup fails, the run does not start (note `could not start: its run log: no start seq`). It fails closed
   (lesson-3). The file holds the run's body and nothing more: the child's standard error and the non-JSON lines of
   its standard output, exactly the lines `take` writes today. It has no header. The new module
   `ergostat/runlog.py` holds all of this. `run_block` only calls it.
2. **Safe opening (lesson-11).** The block name is checked against `^[a-z0-9][a-z0-9._-]{0,127}$` with no `..`. A name
   that fails the check means the run does not start. `logs/` is opened as the owner's directory. `runs` and `<block>`
   are then each opened with `os.open(..., O_DIRECTORY|O_NOFOLLOW)` relative to their parent's descriptor (`dir_fd`),
   and created with `mkdir(dir_fd=...)` when missing. The run file is created with
   `O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW`, mode `0o600`, relative to the block directory's descriptor. If the name exists
   (any `EEXIST`, a link there included), the names tried next are `<seq>-<id12>-2.log` up to `-9.log`, then
   `run-<seq>-<fullid>.log`. If every name fails, the run does not start. When a component is a link or not a
   directory (`ELOOP`/`ENOTDIR`), or when any of these opens fails, the run does not start. It is recorded as
   `agent.failed` with the note `could not start: its run log: <why>` and nothing is written anywhere through the link.
   Because that note starts with "could not start", triage keeps such a failure as noted and does not open it for
   repair.
3. **Each run's entry in the block log is written in one locked append.** When the run ends, after the child has
   exited or the daemon has answered, `runlog.finish` takes an exclusive `fcntl.flock` on a separate lockfile,
   `logs/<block>.log.lock` (opened `O_NOFOLLOW`, with a fresh descriptor each time, so threads of one process exclude
   each other too). While it holds that lock it (a) runs `storage.trim` on the block log and (b) appends in one write
   the header `--- <start time> run <id8> (<why>)`, in today's format with the time taken from `begun["time"]`, followed
   by the body. The body is the run file's last `storage.logs.block` bytes, preceded when longer by
   `(N bytes earlier: logs/runs/<block>/<file>)`. Then it releases the lock. Nothing is written to the block log at run
   start. The block log therefore holds whole runs one after another, so a reader (web agent page, `library/trial.py`,
   CLI) sees a run once it has ended, and a run's live output is in its run file. SPEC says this.
4. **Triage reads only the run's own file.** `capture.failed` is given the run file's text: the last `TAIL`
   characters, read from the run's own descriptor, or `""` when there is no file. It is never given the block log. The
   `agent.ran`/`agent.failed` data and the failure's `ergostat.run.failed` data gain
   `"log": "logs/runs/<block>/<file>"`.
5. **Daemon runs (narrowed claim).** A daemon's standard error is one stream for all of its runs. It stays in
   `logs/daemon-<name>.log` and is never copied into a run's file. A daemon run's file holds only what `take` writes
   for that run: the non-JSON lines handed to it, which is usually nothing. So for a daemon run a failure's `stderr` is
   empty and the failure is triaged by how the run ended. It never holds another run's lines or the daemon's shared
   stderr. SPEC §12r and the daemons section say exactly this. No claim is made that a daemon's stderr is split by run.
6. **Prune, ordered by start seq and never touching a live run (lesson-1, lesson-2).** For its whole life a run holds
   a shared `flock` (`LOCK_SH`) on its own file's descriptor. The file is created and that lock taken while the run
   holds an exclusive flock on the block's directory lockfile, `logs/runs/<block>/.lock`. After its final append, each
   run prunes its block. While holding the directory lockfile exclusively, it lists the directory through its
   descriptor. It takes only names matching
   `^(\d+)-[0-9a-f]{12}(-[2-9])?\.log$|^run-(\d+)-[0-9a-f]+\.log$`, so it deletes only files ergostat named and never
   the lockfile or anything else. It orders them by the integer start seq parsed from the name, never by mtime, name
   order or id. For each file beyond the newest `storage.logs.runs`, oldest first, it tries `LOCK_EX|LOCK_NB` on a fresh
   `O_NOFOLLOW` descriptor and unlinks the file (`dir_fd=`) only when it gets that lock. A file still locked (a run in
   progress, or an orphaned child still holding the inherited stderr) is skipped and kept. A run that starts during a
   prune waits on the directory lockfile, so its file never appears in a listing it could lose. Pruning works across
   processes: `ergostat run` in another process uses the same locks.
7. **Configuration (lesson-4).** A new key `storage: logs: runs: N` sets the run files kept per block: default 50,
   allowed 1 to 1000. `check` reports a value outside that range, and `runlog` clamps it again with `min(max(n,1),1000)`
   when used. The storage docstring, SPEC §4b and the unknown-key message list it.
8. **Unchanged.** The legacy runner (`ergostat/runner.py` agents) and the daemon supervisor's own log keep writing as
   they do now; the report says so. `ergostat reset` removes `logs/` (and with it `runs/`) as it does now.
9. **Docs.** SPEC §12r (triage reads the run's own file; the daemon case as in point 5), SPEC §4b (`logs: runs:`, the
   block log written when each run ends), GAPS (the "share the block's log" sentence and "per-run logs" removed from
   Repair's *Left*; "log events" stays), and the agent guide's sentence on block logs if it has one.

Done also means the house rules hold: the unit suite and the four browser files pass with rc 0 and no page test is
skipped for want of a port; ruff is clean; origin/main has been merged in and the suites run again. For each new test,
the report says which code was broken to see it fail.

## Files to touch

- `ergostat/runlog.py` (new): validate the name, open with descriptors, create, the locks, `finish` (the locked
  append), `prune`
- `ergostat/spec/engine.py` (`run_block`: open the run file before the daemon/process branch, `stderr=` that file,
  `take` writes there, `finish`, give capture the run's text, `log` in the run data; refuse the run when `runlog`
  raises)
- `ergostat/repair/capture.py` (`log` in the failure data; the docstring)
- `ergostat/storage.py` (`LOGS["runs"]`, its parse, the 1 to 1000 range, the docstring)
- `docs/SPEC.md`, `docs/GAPS.md`, `docs/AGENT-GUIDE.md` (only if it describes block logs)
- `tests/test_runlog.py` (new)

## Risks

- **lesson-1**: (a) the header written at run start and the body at the end, or the trim done outside the append's
  lock, lets two runs interleave in the block log; (b) the prune lists the files, then a run creates one and the prune
  deletes it, or the prune deletes a file whose run is still writing. Guarded by the directory lockfile held over
  create+lock and over list+unlink, the per-run `LOCK_SH`, and the block log's lockfile held over trim+append.
- **lesson-2**: ordering by mtime, by name (lexically, "100" sorts before "20"), or by id. Guarded by parsing the
  integer seq.
- **lesson-3**: a missing seq, an unreadable run file or a failed open must not become an empty "fine" log that the run
  carries on with. Each of them stops the run (note `could not start: its run log: ...`). Capture with no file gets
  `""` and the run's real end note.
- **lesson-4**: `logs: runs:` without a ceiling. Range 1 to 1000, checked when the config is read and clamped when used.
- **lesson-6**: a child that leaves a process behind keeps the inherited stderr descriptor, and with it the `LOCK_SH`.
  The prune skips that file instead of deleting it under a live writer. It is documented, not treated as a leak.
- **lesson-8**: claiming that a daemon run's stderr is its own. The claim is narrowed (point 5) and tested both ways:
  the daemon's stderr is absent from run files and present in `daemon-<name>.log`.
- **lesson-9**: overlap tests that pass without real overlap. Runs are made to overlap with barrier files (each run
  waits until the other's marker file exists), not with sleeps, and the race tests put the competing step inside the
  window with monkeypatching.
- **lesson-10**: no fixed sleeps. The barriers have a generous deadline only so a hung test fails instead of hanging.
- **lesson-11**: a symlinked `runs/` or `runs/<block>`, an existing name or link at the file name, a hostile block name,
  and the prune deleting anything but ergostat's own names. Guarded by `O_NOFOLLOW`/`dir_fd`/`O_EXCL`, the name
  check, and the prune's allowlist regex.
- **lesson-7**: the branch changes `run_block`, which other branches also change often. Merge origin/main and run the
  suites again.

## Acceptance tests (`tests/test_runlog.py`)

- `test_two_overlapping_runs_of_one_block_each_have_their_own_file_and_failure`: a block that takes items, two items,
  runs that overlap through barrier files. Each writes `MARK-<item>` to stderr and one of them exits 1. Each run's
  `agent.*` data names a different `log` file holding only its own marker. The `ergostat.run.failed` data of the run
  that failed holds its own marker and not the other's. (It fails if the child's `stderr=` is pointed back at the block
  log, or if capture reads the block log.)
- `test_the_block_log_holds_each_run_whole_with_its_header`: the same two runs. In the block log, each `--- ... run
  <id8>` header is followed only by that run's lines until the next header, and there are exactly two headers. (It
  fails if the header is written at run start.)
- `test_finish_writes_header_and_body_in_one_locked_append`: two threads call `runlog.finish` for different runs. The
  block log's write and `storage.trim` are monkeypatched so that the first call stops between trim and append and
  between header and body until the second thread has tried to write. The result is still two whole entries. (It fails
  with the lock removed, or with trim moved outside the lock.)
- `test_a_long_run_output_is_copied_capped_into_the_block_log`: a run whose file is 3x `logs.block` adds at most that
  cap plus the header and the `(N bytes earlier: ...)` line, and the run file is left whole.
- `test_two_concurrent_daemon_runs_keep_the_daemons_stderr_out_of_both_files`: a daemon with `concurrency: 2` that
  holds both runs until it has received both (it answers `done` only after it has seen two run ids), writing
  `DSTDERR-<run>` to stderr for each and failing one. There are two distinct run files, each named in its own run's
  data. Neither holds any `DSTDERR`. `logs/daemon-<name>.log` holds both. The failure's `stderr` holds no `DSTDERR`
  and nothing of the other run. Each block log entry is whole.
- `test_prune_keeps_the_newest_by_start_seq_not_mtime_or_name`: files with seqs 9, 10, 20, 100 (the mtimes reversed so
  that mtime order is wrong too) and `runs: 2`. 20 and 100 are kept. A stray `notes.txt` and the `.lock` are left
  alone. (It fails with sorting by name or by mtime.)
- `test_prune_skips_a_running_runs_file_among_the_oldest`: the oldest file is held under `LOCK_SH` by an open
  `runlog` handle, as a live run holds it. After the prune with `runs: 1` it still exists, and the other old files are
  gone.
- `test_a_run_starting_during_the_prune_is_not_pruned`: the prune's step between listing and unlinking is
  monkeypatched to start `runlog.open` for a new run on another thread and wait briefly. The new run's open blocks
  until the prune has released the directory lock, its file exists afterwards, and it is not deleted. (It fails if the
  file is created without the directory lockfile.)
- `test_an_existing_name_or_link_at_the_run_file_falls_back_and_writes_nothing_through_it`: the intended
  `<seq>-<id12>.log` is created beforehand as a link to a file outside. The run writes `<seq>-<id12>-2.log`, and the
  outside file is unchanged.
- `test_an_unsafe_run_log_path_refuses_the_run_and_writes_nothing_outside`: `logs/runs/<block>` is a link to a
  directory outside. The run records `agent.failed` with a note starting `could not start: its run log`, the program
  never runs (its marker file is absent), the outside directory stays empty, and a failure, when the model uses repair,
  stays `noted`.
- `test_storage_logs_runs_has_a_floor_and_a_ceiling`: `runs: 0` and `runs: 5000` are both refused by parse with a
  problem, and `runs: 10` is accepted. `runlog.keep()` clamps a value forced past the range.
- Existing tests that read block logs (`tests/test_streamed_output.py`, `tests/test_runner_and_state.py`,
  `tests/test_resilience.py::test_block_logs_threads_and_run_log_are_capped`, `tests/test_repair2.py`) pass unchanged,
  or with only the timing of the reads changed to after the run ends; the report lists every such change.

## Size budget

**240 net lines** of code outside `tests/` and `docs/`: `runlog.py` about 150, `engine.py` about 40 net, `storage.py`
about 12, `capture.py` about 5, plus room for review fixes.

## Notes from the plan review (answer each; not blocking)

- test_a_run_starting_during_the_prune_is_not_pruned cannot fail (lesson-9): a file created after the prune's listing is never in the listing, so it survives even with no directory lockfile. The race the lockfile guards is between O_EXCL create and LOCK_SH in runlog.open, for a run whose start seq is old enough to fall beyond runs: N. Rewrite the test to stop runlog.open between create and lock, with such a seq, while a prune runs on another thread, and show the file is deleted without the directory lockfile and kept with it. Replace the 'wait briefly' with a barrier (lesson-10).
