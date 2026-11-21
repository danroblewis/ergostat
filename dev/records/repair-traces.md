# repair-traces: triage reads Node, Java and Go tracebacks, records errors a successful run swallowed without moving any failure, and closes old items the new signatures replace
depends-on: []

## Definition of done

Everything below is in a model that `use: repair` (SPEC §12r). "The tail" means the last 8,000 characters (`capture.TAIL`) of the run's output in the block's log, read from `max(run start, end - TAIL)`. If the tail does not begin at the run's start, its first partial line is dropped. Every trace is parsed from the tail only, for failed and good runs alike. The engine no longer reads a run's whole output (`ergostat/spec/engine.py`, the `lf.read()` at the `capture.failed` call).

1. **Other languages' tracebacks.** `ergostat/repair/traces.py` has `last(text, root) -> dict | None`. It returns the trace whose header line comes last in `text`, from any of these parsers, as `{"language", "type", "message", "file", "line", "function", "frames"}`. `frames` lists frames innermost first, each with `"project": bool`.
   - **python**: the existing `capture.traceback_of` rules, moved here unchanged. Its signature frame is still the innermost frame with no `LIBRARY` marker, else the innermost frame. Python failures signed before this branch keep their ids (test 1c pins one).
   - **node**: a header line `Name[ [CODE]]: message` (Name starts with a capital letter) directly followed by `    at fn (path:line:col)` or `    at path:line:col` lines. A `file://` prefix is stripped.
   - **java**: an outer line `[Exception in thread "T" ]a.b.SomeException[: message]` directly followed by `\tat pkg.Class.method(File.java:N)` lines, then zero or more `Caused by: TYPE[: message]` blocks. Indented `Suppressed:` blocks are ignored.
     - **Type and message come from the root cause**, meaning the last `Caused by:`, or the outer exception if there is no cause.
     - **The frame is the innermost project frame of the root cause's own frames.** If it has none, the search moves outward, one enclosing exception at a time, then falls back to the root cause's innermost frame.
     - A frame's file is `pkg/dirs/File.java`, built from its class's package. It is a project frame when a file under the model's folder ends with that relative path. The search is a walk of at most 5,000 entries that skips dot-folders and the folders listed in rule 2. If the cap is reached, no Java frame counts as the project's, and that is said in the trace (`"walk": "capped"`).
   - **go**: `panic: message`, then `goroutine N [running]:`, then pairs of a function line and a `\tpath.go:N +0x..` line. `type` is `"panic"`.
   - **A trace needs its header in the text.** A trace whose header line (Python's `Traceback (most recent call last)`, Node's error line, Java's outer exception line, Go's `panic:`) was cut off by the tail gives None, even when its frames and `Caused by:` lines are present. The failure is then signed by how it ended, as before.
2. **A project frame** (node, java, go, and the swallowed check for all four languages) is a frame whose file passes both checks:
   - Resolved, with relative paths taken against the model's folder, it lies under the model's folder (`Path.is_relative_to`).
   - None of its path parts under that folder is one of `site-packages`, `node_modules`, `.venv`, `venv`, `vendor`, and it is not a runtime path (`node:`, `<frozen`, `<string>`).

   For node, java and go, the signature frame is the innermost project frame, else the innermost frame. `capture.failed` signs a failure exactly as now, `(block, program, type, file, function)`, with `traceback` holding the parsed trace (now including `language`).
3. **Swallowed errors.** After a run of a `program` or `ai` block that ended well (exit 0, no note, not `guarded`, its block runs a program of the project's per `program_of`), the engine calls `capture.swallowed(p, spec, b, begun, tail)`.
   - If `traces.last` finds no trace, or a trace with **no project frame** (only library or runtime frames), nothing is recorded: no event, no file.
   - Otherwise one `ergostat.run.swallowed` event is written about `ergostat.failure/<block>-<sig>`, with the same signature a failure with that trace would get.
     - **If the item does not exist,** it is made. It arrives `noted`, the kind's first state, with the full fields a failure gets (error, traceback, stderr, program, input file, `swallowed: 1`, `count: 0`) and is never opened.
     - **If the item exists,** in any state, the event's data holds only `{"swallowed": 1, "last_swallowed": RUN}`. `swallowed` folds as `sum`.
   - **A swallowed record changes no existing failure's state.** `ergostat.run.swallowed` is in no move of the kind. Its data never names `error`, `traceback`, `stderr`, `input`, `count` or `lease`. It never writes `repair/NAME.input` for an existing item, and it is never accompanied by `opened`. An open, leased, awaiting-approval or applied failure stays in its state, keeps its lease (holder and fence) and keeps the fields the fixer reads.
4. **Opening is decided by the fold, in sequence.** `ItemKind` gains `moves_from: dict[event_type, tuple[states]]`.
   - In `spec/items.fold`, an event whose type has an entry there moves the item only when its state at that point in the fold (event order, `seq`) is in the tuple. Otherwise the move is refused and listed in `refused` with `form: "from"`.
   - The failure kind sets `opened: ("noted", "applied")` and `superseded: ("noted", "open")`.
   - `capture.failed` no longer reads the item's state to decide whether to write `opened`. It writes `opened` whenever the run's own facts allow it (a program of the project's, not ended by a timeout, kill, signal or failure to start). The fold then decides against the state at that event's seq, which SQLite's write lock (`begin immediate` in `Events.add_many`) fixes.
5. **The lock for the remaining read-decide-writes.** Inside `capture`, three things are decided from a read of the record:
   - whether the item exists (full fields or counts only, for `swallowed`);
   - `began` (kept only for a new or applied item);
   - which old item to supersede (rule 6).

   Each read happens through `capture.current(p, spec, fid)`. The read, the decision, the `.input` write and the `add_many` all happen while holding an exclusive `fcntl.flock` on `<state dir>/repair/capture.lock`, the same pattern as `fix.ledger`'s `spend.lock`. This holds whether or not `repair-verify` has landed. Writers that do not take the lock (the dispatcher's lease, `fix.record`, `apply`, and `repair-verify`'s events) can only change state, and state is decided by rule 4 in the fold, not by the read.
6. **Old items the new signatures replace (lesson-5).** When `capture.failed` signs a run by a node, java or go trace, it computes the signature the run had before this branch: `(block, program, how)`. If that item exists, its kept `stderr` is parsed with `traces.last`. Only if that gives the **same** new signature does capture write `ergostat.failure.superseded` about the old item, with data `{"by": NEW_FID}`. That event moves it to `dismissed`, only from `noted` or `open` (rule 4).
   - A leased, awaiting-approval, applied, dismissed or dead old item is not moved; the refusal is listed.
   - A later failure tries again, so an old item given back to `open` is superseded then.
   - An old item whose stderr does not parse to the same signature (another bug that ended the same way) is left alone.
   - Python failures are never superseded (their signatures do not change). A dismissed item does not reopen, which is the rule already in place for denied fixes and is unchanged here.
7. **Docs.**
   - SPEC §12r *Triage* says the languages read, the header rule, the project-frame rule, Java's root-cause rule, swallowed records (noted, never opened, no existing failure moved) and superseding. The "does not do yet" sentence drops the swallowed-errors check.
   - SPEC §5a documents `moves_from`.
   - `docs/GAPS.md`'s Repair entry drops "the swallowed-errors check (M5)" and "failures from tracebacks of other languages" from *Left*, and adds:
     - two runs of one block at once share the block's log, so a good run's swallowed record can come from the other run's trace (until `repair-runlog`);
     - a Python traceback more than 8,000 characters before the end of a failed run's output is now signed by how the run ended;
     - Ruby and other languages are not read.
   - `docs/AGENT-GUIDE.md`'s repair paragraph says the same in one sentence.
   - `ergostat/repair/fixer.md` says "the program's language" where it implies Python.

## Files to touch

- `ergostat/repair/traces.py` (new): the four parsers, `last`, the project-frame rule, the bounded Java file walk.
- `ergostat/repair/capture.py`: `traceback_of` delegates to `traces.last`; adds `current`, `swallowed`, the `capture.lock` flock, the decision moved to the fold, superseding.
- `ergostat/repair/__init__.py`: `MOVES` gains `superseded: dismissed`; `moves_from`; `fold={"swallowed": "sum"}`; the kind's description.
- `ergostat/repair/fixer.md`: one wording change.
- `ergostat/spec/ir.py`: `ItemKind.moves_from`.
- `ergostat/spec/items.py`: the `moves_from` check in `fold`, before the `final` check.
- `ergostat/spec/engine.py`: tail-only read for `capture.failed`; the `capture.swallowed` call on a run that ended well.
- `tests/test_repair_traces.py` (new).
- `docs/SPEC.md`, `docs/GAPS.md`, `docs/AGENT-GUIDE.md`.

## Risks

- **lesson-1:** today `capture.failed` reads the state, decides `opened` and writes it with nothing held. A lease taken or a fix applied in between can be overwritten, taking a leased item from the fixer. The new `exists?`, `began` and supersede decisions have the same shape. Answer: state moves are decided in the fold at the event's seq (rule 4). The remaining reads sit under `repair/capture.lock` (rule 5). Tests 4a, 4b and 6c put the competing write in the gap.
- **lesson-5:** non-Python failures signed `(block, program, how)` get new ids, so their old items are stranded `open` and the fixer works on two items for one bug. Answer: rule 6. Tests 6a, 6b and 6c cover it. Python ids must not change: test 1c pins one.
- **lesson-3:** a header cut by the tail, an unreadable log, or a Java walk that hits its cap must not pass for a trace or a project frame. Answer: no header gives None (test 1d); a capped walk gives no project frame and records nothing (test 2c). If the log cannot be read, the engine says so (`self.say`) and records nothing, as for failures now.
- **lesson-4:** the Java walk is bounded (5,000 entries, test 2c) and the read is bounded (8,000 characters).
- **lesson-7:** `repair-verify` (leased) may add failure states. The table in test 4c covers every state of the compiled kind, so a merge that adds a state fails until it is given a row.
- **lesson-8:** "changes no existing failure's state", "the root cause's frame" and "Python ids unchanged" are each backed by a test below. The documented limits are the shared log and the 8,000-character Python case.
- **lesson-9:** each test below names the change that makes it fail. The implementor breaks each one and says in the report that it failed.
- **lesson-10:** the lock test (4b) orders steps with `threading.Event` and a bounded wait. It does not sleep to create the race.
- **lesson-13:** a suite failure outside repair, items or engine triage is reported, not fixed.

## Acceptance tests

All in `tests/test_repair_traces.py`.

**Parsing (1)**
- `test_each_language_is_read[python|node|java|go]`: a real-looking trace per language gives the expected `language`, `type`, `message`, `file`, `line`, `function`. Fails if a parser is missing or reads the wrong frame.
- `test_java_takes_type_from_the_root_cause_and_its_innermost_project_frame[no-cause|one-cause|two-causes|root-frames-all-library]`:
  - no-cause: type and frame come from the outer exception;
  - one-cause and two-causes: type, message and frame come from the last `Caused by:`;
  - root-frames-all-library: type comes from the root, the frame from the enclosing exception's innermost project frame.

  Fails if the outer type or an outer frame is used where the root cause's should be.
- `test_python_signatures_are_unchanged` (1c): a fixed Python traceback, with a library frame innermost, signs to a pinned 8-hex signature and file. Fails if the Python frame choice or the signature tuple changes.
- `test_a_trace_whose_header_the_tail_cut_off_gives_none[python|node|java|go]` (1d):
  - a trace padded so its header falls before the last 8,000 characters gives `traces.last(...) is None`;
  - for Java, a tail holding only `Caused by:` and frames also gives None;
  - through `capture.failed`, the failure is signed `(block, program, how)`.

  Fails if a parser accepts frames without a header.
- `test_the_last_trace_in_the_text_is_taken`: a Java trace followed by a Node trace gives the Node trace.

**Project frames (2)**
- `test_a_project_frame_is_under_the_models_folder_and_outside_library_folders[...]`: frames under the folder count; frames under `node_modules`, `.venv`, `vendor` or `site-packages` inside the folder do not; frames under `/usr/lib`, `node:internal` or GOROOT do not.
- `test_a_java_frame_is_the_projects_when_its_package_path_is_a_file_under_the_folder`.
- `test_a_capped_java_walk_finds_no_project_frame` (2c): 5,001 entries are put before the source, with `capture.WALK` (or `traces.WALK`) monkeypatched small. The result is no project frame, `walk: capped`, and a good run's swallowed check records nothing. Fails without the cap.

**Swallowed (3)**
- `test_a_good_run_that_swallowed_a_project_error_records_a_noted_failure`: a program that catches a `KeyError`, prints its traceback and exits 0 gives one new item, `noted`, `swallowed == 1`, `count == 0`, and no `opened` event.
- `test_a_good_run_with_only_library_frames_records_nothing`: a trace whose frames all lie under a `site-packages` or `node_modules` folder, on a run that exits 0, gives no event of any `ergostat.failure*` or `ergostat.run.swallowed` type and no file under `repair/`.
- `test_a_swallowed_record_moves_no_existing_failure[noted|open|leased|awaiting-approval|applied]`: the failure is put in each state (leased via a real `ergostat.lease.taken`). A good run then swallows the same trace. Afterwards:
  - state is unchanged;
  - `lease.holder` and `lease.fence` are unchanged;
  - `error`, `traceback`, `stderr` and `count` are unchanged;
  - `repair/NAME.input` has the same bytes;
  - `swallowed` went up by 1.

  Fails if `swallowed` maps to a state, if it writes `opened`, or if its data carries the failure fields.
- `test_a_failed_run_still_opens_a_noted_swallowed_failure`: after a swallowed record (noted), a failing run with the same signature opens it.

**Opening and the lock (4)**
- `test_opened_after_a_lease_taken_between_triages_read_and_write_leaves_it_leased` (4a): `capture.current` is monkeypatched to return the item as `noted`/`applied`, then insert `opened` + `ergostat.lease.taken` (another triage and the dispatcher) before returning. Afterwards the item is `leased`, the holder is the inserted run, and the `opened` refusal is listed with form `from`. Fails if `moves_from` is removed from the fold or the kind.
- `test_two_triages_of_one_new_signature_are_serialised_by_the_capture_lock` (4b):
  - call 1's patched `current` starts call 2 in a thread, then waits up to 2 s on an Event that call 2's `current` would set;
  - with the lock, the order is read 1, write 1, read 2, write 2;
  - the item has `count == 2` and one `first_seen`, and the second call wrote counts-only data for a swallowed record.

  Fails if the flock is removed.
- `test_opened_moves_only_from_noted_or_applied[every state of the compiled failure kind]` (4c): a table of expected outcomes keyed by state. The test asserts the table's keys equal the compiled kind's states.

**Superseding (6)**
- `test_an_old_how_signed_failure_is_superseded_by_its_trace_signature[noted|open]` (6a): an item at the old `(block, program, "exited 1")` signature, whose `stderr` holds a Node trace, moves to `dismissed` with `by` naming the new item after a failure of the same program. The new item is open.
- `test_an_old_failure_being_worked_or_of_another_bug_is_not_superseded[leased|awaiting-approval|applied|other-trace]` (6b): the state is unchanged and the lease is held. Once the leased one is given back to `open` (nack), the next failure supersedes it.
- `test_a_lease_taken_between_the_supersede_read_and_write_keeps_the_old_item_leased` (6c): `capture.current` inserts `ergostat.lease.taken` on the old item after reading it `open`. The old item stays `leased` and the `superseded` refusal is listed.

**Existing and full suites**
- The existing `tests/test_repair2.py` triage tests pass unchanged.
- Unit suite, the four browser files, and ruff clean. origin/main is merged in and the suites run again.

## Size budget

320 net lines of code outside `tests/` and `docs/`, made up of:
- `traces.py` about 170;
- `capture.py` about +70;
- `engine.py` about +15;
- `ir.py` and `items.py` about +12;
- `__init__.py` about +5;
- `fixer.md`, one line.

## Notes from the plan review (answer each; not blocking)

- Rule 6 sends superseded old (block, program, how) items to `dismissed`, which never reopens, but that signature is still live: later failures of the block/program that end the same way with no readable trace (incl. rule 1d's header-cut traces) are counted into the dismissed item and never opened, hiding real failures (lesson-5). Use a distinct `superseded` state that `opened` may leave (moves_from opened includes it), add it to test 4c's table, and add test 6d: after superseding, a traceless failure with the same ending opens the old-signature item again.
