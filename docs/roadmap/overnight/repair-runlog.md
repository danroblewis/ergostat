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

## Where it stopped

Built, round 1. All eleven acceptance tests are in `tests/test_runlog.py` and pass. 228 net lines of code outside
tests and docs (budget 240). Decisions taken alone (the most reversible choice in each case):

- **The plan review's note.** `test_a_run_starting_during_the_prune_is_not_pruned` is rewritten as asked. A seam
  (`runlog._created`) stops `open_run` between the `O_EXCL` create and the `LOCK_SH`, for a run with start seq 5 when
  files with seqs 50 and 60 exist and `runs: 1` applies. A prune starts on another thread. The test waits on a barrier
  (the prune reaching its directory lock, or finishing), not on a sleep. With the directory lock the new file is kept
  and only 50 goes. With the lock removed from `open_run`, the prune deletes the new file and the test fails.
- **O_RDWR, not O_WRONLY.** The run file is opened `O_RDWR|O_APPEND|O_CREAT|O_EXCL|O_NOFOLLOW`, so that triage's tail
  can be read from the run's own descriptor (point 4) without opening the name again. `O_APPEND` keeps `take`'s
  writes and the child's writes in order.
- **A run id that is not hex.** Ergostat's run ids are uuid hex, but `run_block(run_id=...)` accepts any string, and
  `tests/test_daemons.py` passes `"r2"`. Such an id names its file by the first 12 hex characters of its sha1. That
  keeps the name safe and still matched by the prune's allowlist. The run is not refused.
- **One write, split in the test.** `finish` calls `_append(fd, header + body)` once. The finish test splits that call
  at the header, so the run stops between its header and its body. It shows trim happens under the lock with a probe:
  a non-blocking `flock` on the lockfile from inside `trim` must fail.
- **`origin/main`.** This clone has no `origin` remote and fetching is not allowed here. The local `main` (dc0d5ac)
  is an ancestor of the branch. The factory's merge step must still merge the real `origin/main` and run the suites
  again.

Existing tests changed: only `tests/test_resilience.py::test_block_logs_threads_and_run_log_are_capped`. Its literal
`cfg.logs == {...}` now includes `"runs": 50`, the new default. `test_streamed_output.py`, `test_runner_and_state.py`,
`test_daemons.py`, `test_leases.py`, `test_ticket_factory_daemons.py`, `test_daemon_docs.py`, `test_warm.py`,
`test_inbox.py`, `test_storage.py` and `test_trial_stops.py` pass unchanged. `test_repair2.py` skips here: the
container has no OS sandbox (bwrap cannot make namespaces).

Not changed (point 8): the legacy runner (`ergostat/runner.py` agents) and the daemon supervisor's own
`logs/daemon-<name>.log` write as before, and `ergostat reset` still removes `logs/` along with `runs/`.
`docs/AGENT-GUIDE.md` does not describe block logs, so it is left alone.

Not run by the implementor: the whole unit suite and the four browser files (left to the factory's watched run).

Each new test was seen to fail with this code broken:
- overlapping runs: the child's `stderr=` pointed back at the block log, and capture given the block log;
- block log whole: the header written at run start;
- finish: the block log's lock removed; trim moved outside the lock;
- long output: the whole run file copied with no cap; the header dropped;
- daemons: the daemon's log added to the failure's text;
- prune by seq: sorted by name; sorted by mtime;
- prune skips a live run: the `LOCK_NB` check removed;
- run during prune: the directory lock removed from `open_run`;
- existing name or link: `O_EXCL|O_NOFOLLOW` removed from the file's open;
- unsafe path: `O_NOFOLLOW` removed from the directories' opens; capture given the block log;
- runs range: the ceiling removed from parse.

### Round 3: main merged, the previous review's findings answered

**The merge of main (7b39bc9).** Committed as 825696ef. It conflicted only in factory files this gap does not touch
(`dev/bin/agents.py`, `dev/bin/fac.py`, `dev/factory.toml`, `dev/model/knowledge.yaml`, `ergostat.yaml`,
`tests/test_factory_knowledge.py`). Each conflict is resolved by keeping both sides: the backlog's `groomer` role,
`[backlog]`, `rank/value/size` and `paused`, all from this clone's base, and main's `pipeline_manager` role, its
`situation` kind and `[plan] review = "all"`. The planner's `takes.to` follows main and no longer lists `planned`. It
keeps the backlog's `unblocked: true, order: rank`. `test_factory_knowledge.py`, `test_factory_manager.py`,
`test_factory_sessions.py` and `test_backlog.py` pass after the merge.

Each finding, what changed:

1. **engine.py, the tail read in the same try as `finish` (lesson-3, point 4).** Fixed. `run_block` now reads
   `rl.tail(TAIL)` in its own try, before `runlog.finish`. A failing append or trim therefore no longer empties what
   triage gets. If the run's own file cannot be read, the tail is not `""`. It says so:
   `(its run log <rel> could not be read: ...)`. New test:
   `test_a_failed_block_log_append_still_gives_triage_the_runs_own_lines`. `runlog.finish` is monkeypatched to raise
   `OSError(ENOSPC)` for a program that writes `MARK-own boom` and exits 1. The failure's `stderr` must still hold
   that line, and the engine must say the log error. Seen to fail with the old order (the tail read after `finish`,
   inside its try).
2. **The suites not run; test_repair2 never run against the branch (lesson-7, lesson-9).** Partly answered. This
   container has no OS sandbox, so `tests/test_repair2.py` skips as a module. Its three triage tests
   (`test_a_failed_run_is_triaged_into_one_failure_a_signature_and_counted`, the one at :173 that pushes a real
   `KeyError` traceback through `run_block` into triage; `..._timeout_or_a_failure_with_no_program_is_noted_not_opened`;
   `..._repair_loops_own_runs_record_no_failures`) need no sandbox. I ran them here from a scratch file (git-ignored,
   not committed) that imports them without the module's skip. All 3 pass: the traceback's type and file are parsed
   from the run's own tail, and `KeyError: 'issues'` is in its `stderr`. `test_a_fix_that_fails_its_test_...` (:285)
   tests the fix inside the sandbox and still has not run. It, the whole unit suite and the four browser files must be
   run by the factory's watched run on a host with the sandbox. The implementor's brief forbids running the whole
   suite itself. Run here after the merge, one file at a time, all passing: `test_runlog.py` (12),
   `test_streamed_output.py`, `test_runner_and_state.py`, `test_resilience.py`, `test_daemons.py`,
   `test_spec_engine.py`, `test_leases.py`, `test_storage.py`, `test_trial_stops.py`, `test_warm.py`,
   `test_inbox.py`.
3. **test_a_run_starting_during_the_prune_is_not_pruned could pass without the lock (lesson-9, lesson-10).** Fixed. The
   window is now held for as long as the prune could get anywhere. If the run took the block directory's lock (seen
   by the test's `_lock` wrapper), it waits only for the prune to reach that lock: the prune can go no further until the
   run lets go. If the run did not, it waits until the prune has finished, so the prune's listing, its `LOCK_NB` and
   its unlink all fall before the run's `LOCK_SH`. Both waits are on events with only a deadline, with no polling or
   sleeps. With `_lock(dl, LOCK_EX)` removed from `open_run`, the test fails every time ("the new run's file was
   pruned while it was being made"). With the lock in place it passes.
4. **Where it stopped not updated (lesson-12).** This section.

**Found, not fixed (lesson-13, lesson-7).** `tests/test_relations_asof.py::test_an_item_of_no_kind_changed_since_has_no_links_and_the_rest_answers`
(both parameters) fails after the merge: it expects the derived status `"ready"`, and `ergostat/precedence.py` says
`"unblocked"`. That rename is the backlog's (600535dc), which is in this clone's base `main` (dc0d5ac) but not in the
merged main (7b39bc9). The test comes from main's relations-as-of. This branch does not touch `precedence.py`. It is
a conflict between the backlog and relations-as-of. It belongs to whichever of them lands second, not to this gap.
The same base also makes `git diff 7b39bc9...` show the backlog's files (precedence, eta, leases/ready, pages.js, ...).
None of those files is this gap's.

Size: 231 net lines of code outside tests and docs (runlog.py 201, engine.py +20, storage.py +7, capture.py +3),
budget 240.

### Round 3, after the factory's unit run (3 failed, 1969 passed, 69 skipped)

The merge of main was already committed (825696ef). There was nothing left to resolve.

- **`tests/test_relations_asof.py::test_an_item_of_no_kind_changed_since_has_no_links_and_the_rest_answers`
  (both parameters).** Fixed in the test, at the factory's request. Its two `"ready"` expectations are now
  `"unblocked"`. That is the derived status's name in this branch's base: the backlog's rename (600535dc) changed
  `precedence.status` and `tests/test_relations.py` the same way, but main's relations-as-of test came later and was
  never updated. No code changed: precedence's vocabulary is the backlog's, and the web page (`relations.js`) already
  draws `unblocked`. This is the most reversible choice. If the backlog lands with the old name restored, these two
  words go back too. `test_relations_asof.py` and `test_relations.py` pass (27).
- **`tests/test_leases.py::test_the_watchdog_renews_from_what_the_holder_does_elsewhere`.** Not fixed (lesson-13).
  It passes alone. `tests/test_leases.py` run whole twice here: once 20 passed; once
  `test_leases_survive_a_restart_the_fold_is_the_truth` failed and then passed alone and in the next whole-file run.
  So the lease tests are intermittent in this container too. The failing test has a 1 s TTL renewed by
  `$ERGOSTAT_CMD event` processes, and under the suite's load (115 processes) the first of them can take over a
  second to start, so the lease expires (`['expired', 'ack']`). Nothing this branch changed is on that path:
  `runlog.open_run`/`finish`/`prune` add only a few uncontended per-block `flock`s and small writes, with no fsync and
  no sleep. Neither lease test changed since 6b7e258e. I could not run main's own copy of the file to compare (not
  allowed in this session), so "unrelated" rests on that reading, not on a run.

ruff is clean.

### Round 4: the branch base is still wrong. Rebuilding the branch was refused in this session.

The blocking finding is not fixed. It is right: the branch holds the backlog's commits c66dc8a5, 67c673ec and
600535dc, which main (7b39bc94, the only main in this clone; there is no `origin` remote) does not have. The fix is to
rebuild the branch on main from the gap's own commits only. In this session every command that makes or moves a
branch was refused: `git branch <name> <commit>`, `git switch -c ... main` and `git checkout -B ... main`. I did not
get around that with a forward commit that undoes the backlog's files in the tree, for this reason: the backlog's
commits would still be in the branch's history. Once this branch is merged, git would count the backlog as merged
while its content was undone, and a later merge of the real backlog branch would bring in nothing. That is harder to
undo than leaving the branch as it is.

What the factory (or a session allowed to move branches) must run, in `/work`:

```
git branch factory/repair-runlog-old-base HEAD          # keep the old head, so nothing is lost
git checkout -B factory/repair-runlog main              # main = 7b39bc94 or a newer origin/main
git cherry-pick 98d0af91 3b2a7396 e5d4b907 8becff97 f3498374 4c354b23 <this round's commit>
```

Leave out e3bda351. Its only code change is `tests/test_relations_asof.py` ('ready' -> 'unblocked'), which is right only
on the backlog base. Its "Where it stopped" text (round 3, after the factory's unit run) has to be carried over by hand,
or that commit cherry-picked with `-n` and the test file restored from main. The gap's own commits touch only
`ergostat/{runlog,storage}.py`, `ergostat/spec/engine.py`, `ergostat/repair/capture.py`, `docs/{SPEC,GAPS}.md`, this
file, `tests/test_runlog.py` and `tests/test_resilience.py`. None of the backlog's files are in them. Conflicts are
possible only in `engine.py`, `storage.py` or the docs, if main changed them after 7b39bc94. Then run
`test_runlog.py`, `test_streamed_output.py`, `test_runner_and_state.py`, `test_resilience.py`, `test_daemons.py`,
`test_repair2.py`, `test_relations_asof.py` (which must then pass unchanged with 'ready'), the unit suite and the four
browser files.

**Size.** The gap's own code against main (`git diff --stat 7b39bc94 HEAD` on the four ergostat files) is +249/-17,
which is 232 net lines (budget 240). The 372 the factory counts includes the backlog's code, which goes away with the
rebuild.

The other findings of review 3:

- **runlog.keep() did not clamp its fallback.** Fixed. An unreadable value now falls back to `LOGS["runs"]` and is then
  held to 1 to 1000 like any other value. `test_storage_logs_runs_has_a_floor_and_a_ceiling` now forces the default
  to 5000 and asks `keep("lots")`, which must give 1000. I saw it fail with the old fallback put back.
- **Suites, and the lease test called unrelated by reading only.** Still open. The unit suite, the four browser files
  and main's copy of `test_leases.py` were not run in this session. They must be run on the rebuilt branch. The lease
  test can be compared fairly only there, against main with only this gap on top.
- **The reviewer could not run the tests.** Run here: `tests/test_runlog.py` 12 passed. ruff is clean.

## Where it stopped

Parked by the factory (review/repair-runlog-4, 2026-11-20 20:29).

Done, by reading: the gap's own code (ergostat/runlog.py: per-run files opened by descriptor without following links, created with O_EXCL and fallback names, the shared run lock taken under the directory lock, the prune ordered by start seq with an allowlist that skips locked files, the trim and append done in one write under the block log's lockfile, keep() clamped including its fallback; engine.run_block refuses a run whose log can't be made and gives triage the run's own tail before finish; storage logs: runs: 1-1000) and the tests in tests/test_runlog.py, which the implementor reports passing (12) and seen failing with each guard broken. Left: the branch must be rebuilt on origin/main from the gap's own commits only (98d0af91 3b2a7396 e5d4b907 8becff97 f3498374 4c354b23 01a44bad; leave out e3bda351's test_relations_asof.py edit and carry its notes over by hand), as written at docs/roadmap/overnight/repair-runlog.md:300-316. Then run test_runlog.py, test_streamed_output.py, test_runner_and_state.py, test_resilience.py, test_daemons.py, test_repair2.py (on a host with the sandbox), test_relations_asof.py unchanged with 'ready', the unit suite and the four browser files, and compare test_leases.py with main. Why stop: two reviews in a row failed on the branch base, and the implementor's session cannot move branches, so a third fix round would end the same way. The rebuild needs a session allowed to make branches, or the coordinator.
