# observe-a-work-daemon-1: a `journal:` sensor. Ergostat follows a folder of JSONL journals that something it did not start writes, and records each complete line once, as that sensor's observations.
depends-on: []

## Definition of done
Ergostat can watch a work daemon it never starts, through the files that daemon writes. Today a sensor's lines come only from a command or daemon that ergostat runs itself (SPEC §6, §9.7).
1. **Declared.** A sensor may have `journal: FOLDER` as its kind, instead of `run:`, `query:`, `manual:`, `items:`, `changes:`, `builtin:` or `daemon:` (exactly one, as now). FOLDER is relative to the model's root and must resolve inside it. An absolute path, a `..` that leaves the root, or `journal:` combined with another kind is refused at compile, with its place and a code (`bad-journal` or `sensor-kind`). A journal sensor is never read on a schedule, and no process is started for it. A model with no journal sensor starts no thread for them.
2. **Read.** The engine's lead shard alone, on a thread of its own, looks at every `*.jsonl` file directly in each journal folder every few seconds (a constant). Each new complete line, ending in `\n`, goes through the same rules as a `run:` sensor's observation lines (`observations()` and the engine's observer). So an event about an item is recorded with `source` set to the sensor's name, and a line that breaks the rules is recorded as `sensor.refused` about the sensor, with its `why`. A partial last line waits until it is complete. A line `{"value": N}` (a finite number, not a bool) is the sensor's reading, at most one a second. A file reached through a symlink that leaves the folder is not read, and this is said once as `sensor.refused`.
3. **Once.** Each line is recorded under an id that ergostat makes from the sensor, the file's name, the line's byte offset and the line's bytes. So reading it again records nothing new, whether after a restart, a lost or unreadable read state, or a reload. The offsets read so far are kept in a state file under the project folder. If that file is missing or unreadable, every journal is read from the start, and nothing is skipped or recorded twice. A journal that shrinks (rewritten or rotated) is said once as `sensor.refused` ("FILE went back") and read again from its start; its new lines are recorded. A line identical to the old one at the same offset counts as the same entry, and SPEC says so.
4. **Bounded.** A constant cap limits the lines recorded per sensor per pass; the rest wait for the next pass and none are lost. A line over a constant byte limit is refused (its reason says so) and skipped. A constant cap limits the files read per folder; past it, the extra files are said once as `sensor.refused` and not read. No new config number is added.
5. **Stopped.** The thread ends with the engine's stop. After a reload, a removed journal sensor is no longer read and a new one is.
6. **Claimed no wider.** SPEC §6 adds a sensor-table row and a paragraph covering points 1 to 4 and the identical-line limit. If the record forgets lines (`keep`/`prune`) and the state file is also lost, those lines are recorded again, and SPEC says so. `docs/AGENT-GUIDE.md` says when to use a journal instead of a daemon (the process is not ergostat's to start).

## Relation to other work
- engine-adopts-runs-from-their-journals / daemons-reconnect-after-the-engine: those are about ergostat's own runs and daemons. This plan reads files written by outsiders, adopts no run and names its module so it does not clash with theirs.
- external-event-logs (merged): this keeps its `cite:` rule as it is. A journal line's own `id` is treated exactly as a `run:` sensor's.
- library-sandbox-sensors-proven (merged): the inside-the-root check applies to library sensors too. There are no new trust paths.

## Files to touch
- `ergostat/journal_source.py` (new)
- `ergostat/spec/compile.py`
- `ergostat/spec/ir.py`
- `ergostat/spec/engine.py`
- `tests/test_journal_source.py` (new)
- `docs/SPEC.md`
- `docs/AGENT-GUIDE.md`
- `dev/records/observe-a-work-daemon-1.md` (new)

## Risks
- lesson-3: an unreadable state file, a vanished file or a failed stat is treated as "nothing new" and lines are skipped. The worst case must instead be a re-read, with duplicates dropped by id.
- lesson-5: a rewritten journal reuses offsets. If ids were made from offsets alone, its new lines would be dropped as already recorded.
- lesson-4: a huge folder or a flood of lines with no cap per pass stalls the engine. Every cap must be a constant with a ceiling.
- lesson-6: the reader thread outlives the engine's stop, or keeps reading a sensor that a reload removed.

## Acceptance tests
- `tests/test_journal_source.py::test_lines_recorded_once_across_restart`: two journals are appended in pieces, including a partial line. Passes run, then a new reader with no state runs. Each complete line is recorded exactly once, with the sensor as its source, and the partial line is recorded only once it is complete.
- `tests/test_journal_source.py::test_unreadable_state_rereads_without_loss`: the state file is corrupted between passes. No line is recorded twice, and lines appended meanwhile are all recorded (fails if a bad state file reads as "at the end").
- `tests/test_journal_source.py::test_rewritten_journal_new_lines_recorded`: a journal is truncated and rewritten with different lines at the same offsets. The new lines are recorded, and "went back" is said once.
- `tests/test_journal_source.py::test_bad_lines_refused_with_why`: lines with an ergostat-own type, no item, or over the byte limit become `sensor.refused` with a reason, and are not recorded as events.
- `tests/test_journal_source.py::test_caps_spread_over_passes`: more lines than the cap per pass are all recorded over several passes, with none lost. Files past the folder cap are said once and not read.
- `tests/test_journal_source.py::test_compile_refuses_outside_root_and_two_kinds`: an absolute path, an escaping `..`, and `journal:` with `run:` are each refused with their code.
- `tests/test_journal_source.py::test_symlink_leaving_folder_not_read`: a `*.jsonl` symlink to a file outside the folder records nothing, and this is said once.
- `tests/test_journal_source.py::test_value_line_reading_and_stop_on_reload`: a `{"value": 3}` line becomes the sensor's reading. After a reload that removes the sensor, and after the engine stops, appended lines are not recorded and the thread has ended.

## Size budget
190 net lines
size: L (confidence: medium)

## Notes from the plan review (answer each)

- Point 3 ('reading it again records nothing new') fails for refused lines if the plan reuses the engine's observer as is. Engine._observer (ergostat/spec/engine.py:1378-1404) records each sensor.refused with a fresh uuid (line 1402: no id=), so after a restart, a lost or unreadable state file, or a reload, every refused journal line and the notices that are meant to be said once (FILE went back, symlink, folder cap) are recorded again. Also, it passes on only cite: ids (observations(), engine.py:2383) and refuses any other id through mirror.valid (engine.py:1392), so the reader cannot slip its own id into the object. Instead: give journal_source.py its own observer path that takes the reader's id for each seen line (a line's own cite: id still wins and is still checked by mirror.valid, as external-event-logs does). Give each refusal an id made from sensor + file + offset + line hash + 'refused', and each once-only notice an id made from sensor + file + kind (plus the file's identity for went-back). Make test_unreadable_state_rereads_without_loss and test_bad_lines_refused_with_why count sensor.refused events across the re-read too.
- 'The engine's lead shard alone' reads every journal folder, which breaks the per-sensor ownership the engine already uses (engine.py:1464 checks self.own(f"{s.of.kind}.{s.of.name}.{s.name}") before reading an items: sensor; follows()/own() at engine.py:239). A journal sensor on a part in another system's engine would have its reading written by the lead, while the owning engine never marks the series dirty or evaluates, and a reload in the owning engine would not start or stop it (the same kind of over-wide partition claim as lesson-8's daemon case). Instead: each engine (shard None, or its own shard) reads the journal sensors it owns, on one thread per engine that has any, started and stopped with that engine and refreshed in swap() (engine.py:1898). Drop 'lead' from point 2.
- A shrink is the only rewrite detected (point 3). A journal truncated and rewritten past its old size between passes (a daemon that rewrites its file at start, then logs quickly) is not seen to shrink: reading goes on from the old offset into the middle of the new content, so the new lines before that offset are never recorded and the first line read is a fragment. test_rewritten_journal_new_lines_recorded would pass while this loses lines. Instead: keep the file's (st_dev, st_ino) and a hash of the bytes just before the offset (say the last complete line read) in the state file; a change in either counts as went back and the file is read from 0, with ids deduplicating as planned. Add the grows-past-old-size case to that test.
- compile.py has an allowlist of sensor keys, SENSOR_KEYS (ergostat/spec/compile.py:67), and the kinds list and message at lines 499-501; both need journal. Other places branch on a sensor's kind and should be checked for a sensor with none of the old kinds: read_sensor (engine.py:2408-2420 says why a daemon: sensor is not read; a journal sensor needs the same so that nothing on a schedule reports it as sensor.failed), the pass at engine.py:1518-1534, cli/spec_cmds.py:351 and numbers/changeset.py:330.
- Library sensors: ergostat/library/trust.py:82-106 is an allowlist of sensor keys, so an untrusted library's journal: sensor is refused today, which is safe. The plan says 'no new trust paths', but an untrusted library that reads the owner's files into the record would be one. Add "journal": (NO, "reads files in the owner's folder into the record") explicitly, say so in SPEC, and do not claim library journal sensors work.
- Ids include the file's name, so a journal rotated by renaming to another *.jsonl name (x.jsonl -> x.1.jsonl) has every line recorded again. Either leave the file name out of the id when the identity (dev, inode) is unchanged, or say this limit in SPEC next to the identical-line limit (lesson-8).
- test_value_line_reading_and_stop_on_reload should assert thread.is_alive() is False after close(), within a bound. Put the thread's join in Engine.close() (engine.py:2008) before ergostat.stopped is recorded, using a stop Event the poll waits on (not time.sleep), so the stop is not delayed by up to one interval.
