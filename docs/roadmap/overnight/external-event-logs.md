# external-event-logs: mirror an outside event log (Kafka, a ticket history, an incident log) into the record, one event per entry, each event's id citing the entry's position. The cursor is confirmed against the record and recovered from it when the collector's memory is lost.
depends-on: []

## Definition of done

What exists on main and is not rebuilt: copying in works through the `collect` template (`ergostat/library/run/collect.py`). Its cursor lives only in its memory file (`library/<name>/collect.json`), it is moved before anything is known to be recorded, and it compares positions with `_key` (a float, else text). Reading in place exists for one kind of log: another ergostat, through `remotes:` and `/remote/v1/events?after=SEQ` (SPEC §4c). This branch adds the third way, **mirror with a cursor that cites the original**. Reading in place for other kinds of log (Kafka and the like) stays open in GAPS, and the entry says so.

Facts from main this plan builds on (checked in the code):
- A `run:` sensor is not a block. The engine runs it with `read_sensor` (`ergostat/spec/engine.py:2108`). Its event lines go through `observations()` (`engine.py:2064`) and `Engine._observer(name).observe` (`engine.py:1173`), which records each line with `p.events.add(..., source=name)`. `name` is `sensor_name(flow, sensor)` (`spec/legacy.py:16`), `"<flow>.<sensor>"`. If the command exits non-zero, none of its lines are recorded and a `sensor.failed` event is recorded with the first 200 characters of its stderr as `why`.
- Both stores already ignore an event whose `id` is already recorded. `store.Events.add` uses `insert or ignore` and returns `seq: None`. `segments.Events.add` checks `known([id])` when an id is given. `add_many(new=False)` skips known ids, and `add_many(new=True)` does not look. **This branch changes no store code.**

When done:

1. **`ergostat/mirror.py`** (new, the cite id and nothing else):
   - `PREFIX = "cite:"`. A cite id is `cite:<log>:<type>:<position>`. `<log>` has no `:` or whitespace and is 1–200 characters. `<type>` is `i` (a whole number) or `t` (text). The position comes after the third `:`, so text may contain `:` (ISO times).
   - `position(value, type) -> int | str`, which raises `MirrorError(reason)`. For `int`, it accepts a JSON integer (not a bool) ≥ 0, or a string matching `^(0|[1-9][0-9]{0,18})$`, and returns an `int`. So `"9"` and `9` are the same position, and `10 > 9` holds. Floats (`10.0`, `1.5`), negatives, `"09"` and empty values are refused, and the reason says what was wrong. For `text`, it accepts a string matching `^[A-Za-z0-9._:+-]{1,128}$` and returns it unchanged. Text positions are ordered as plain strings: the docs say a text position must sort as text in log order (zero-padded, fixed-width ISO times).
   - `cite(log, type, pos) -> str` and `parse(id) -> (log, type, pos)`. `parse` decodes through `position` again, so an id read back from the record has the same Python type and order as when it was written. It raises `MirrorError` on anything else.
   - `key(type, pos)`: the one ordering used by the collector's confirmed cursor, by lost memory and by rollup. It is `pos` itself (an `int` for `i`, a `str` for `t`). Comparing two different types raises `MirrorError("the record cites LOG both as whole numbers and as text")`. Nothing falls back to float or string conversion.
   - `valid(id, sensor) -> str | None`: the reason it is refused, or None. Refused when it does not parse, or when `<log>` ≠ `sensor`. **A log is bound to the one sensor whose name it carries.**
   - `recorded(events, sensor) -> (type, pos) | None`: the greatest cite of this sensor's log in the record. It takes the maximum by `key` over (a) events with `source == sensor` whose id parses with `log == sensor`, read newest first in pages of 5,000 using `before_seq` (bounded memory), and (b) the `data.rollup.cites[sensor]` of every `ergostat.item.snapshot` (also paged). It returns None only when it found none. A store error propagates; it is never turned into None.
2. **The engine records a cite id from a sensor, only for that sensor's own log.** `observations()` carries an `id` field only when it is a string starting with `cite:`. Any other `id` is dropped as on main, so the event is recorded under a fresh uuid. `observe` checks `mirror.valid(id, name)`. When refused, it appends the reason to `refused` (so it is recorded as `sensor.refused` about the sensor, with `why`) and the line is not recorded. When valid, `p.events.add(..., source=name, id=id)`. `read_sensor` adds `ERGOSTAT_SENSOR=<flow>.<sensor>` to the command's environment.
3. **Nothing else can record a cite id.** `intake/envelope.check` refuses (`Refused`, nothing of the push recorded) an event whose `id` starts with `cite:`: "cite: ids are a mirror's own: only its sensor records them". Its docstring's "id is the caller's" is narrowed to match. Every path that takes a caller's id goes through `check`, and each has a test (see the acceptance tests):
   - (a) `POST /api/events` (`web/push_api.py` → `envelope.record`);
   - (b) webhooks (`intake/hooks.py`: a hook's `id:` template → `envelope.record(p, evs, source=hook name)`);
   - (c) the socket's `event` op (`calls/ops.py:event` → `envelope.record`), which is also what `ergostat event --add` sends when an engine listens.
   
   Paths that take no caller id, each tested to show a `cite:` id on its line is not recorded under that id:
   - (d) `ergostat event --add` without an engine (`cli/record.py`, which has no id option, `p.events.add` with no id);
   - (e) a block's event lines (`engine.py` `Lines.take`, which builds the row without `id`);
   - (f) a legacy agent's event lines (`runner.py` `Recorder`, `ev.add` without `id`).
   
   Paths that mint their own ids and take none from outside, listed for the reviewer and not tested here: transcripts (`event_id`, a sha1 hex), `repair/capture.py` (uuid), rollup snapshots (uuid), remote events (cached in `remote/cache.py`, never recorded). There is no import or replay command that writes events with given ids.
4. **The collector mirrors** with `--mirror` (template param `mirror: bool`, default false) and `--position int|text` (template param `position`, default `int`). `--mirror` needs `--cursor-field` (the position) and refuses `--changes`; both are argument errors, exit 2. In mirror mode, under the existing `kept()` flock, held for the whole poll:
   1. **Who it is.** `ERGOSTAT_SENSOR` unset or empty: exit 1, "a mirror cites as the sensor that runs it: ERGOSTAT_SENSOR is not set". The log is `ERGOSTAT_SENSOR`.
   2. **Confirm.** `mem["mirror"]` holds `{"type", "cursor", "said"}`. When `said` is non-empty, `p.events.known(said)` is checked against the record (opened as `common.project()` does). The cursor moves to the last id of the longest prefix of `said` (in position order) that is all recorded. When one is missing, the reason is the newest `sensor.refused` or `sensor.failed` about this sensor (its `why`), else "not in the record". `said` is cleared, memory is written, and the collector exits 1 with "position P of LOG was said but not recorded: REASON". So a refused or lost position is never silent, and the next poll re-reads from the confirmed cursor. Entries already recorded are skipped by id in the store.
   3. **Lost memory.** With no `mem["mirror"]` (no file, unreadable JSON, a new instance), the cursor is `mirror.recorded(events, sensor)`. When that is None, it starts from the beginning. When the record can't be read, it exits 1 and says why; it never starts from the beginning.
   4. **Read.** The source is read as now, with `ERGOSTAT_CURSOR`/`{cursor}` set to the confirmed cursor's position (as text).
   5. **Check every entry before saying any.** For each record: no `--cursor-field` value, or `mirror.position` raises, or `mirror.valid(cite)` is refused → exit 1 with the record's id and the reason, nothing said, cursor unchanged. Two different records at one position → exit 1. Entries at or before the cursor are skipped. When the poll returns entries but the greatest is strictly before the cursor, the log went back (restarted, or offsets reset): exit 1, "LOG went back: its newest entry P is before the cursor C", and nothing is skipped silently.
   6. **Say.** It says the lowest `MOST = 5000` new entries in position order (a constant, not configurable; the rest wait for the next poll). Each one is `{"event": KIND.<event-field or --event>, "item": KIND/<id>, "id": <cite>, "data": <fields>}`. `said` is set to their ids, memory is written, and it prints the rate as now (arrivals per hour over `--window`).
   
   The copy-in mode (no `--mirror`) is unchanged, its `_key`/`_le` included.
5. **Rollup keeps the cite.** `rollup.snapshot_of` adds `data.rollup.cites = {source: greatest cite id}` over the prefix events whose id parses with `log == source`, merged with the older snapshot's `cites` by `mirror.key`. So `recorded` still finds the cursor after an item's events are rolled up.
6. **What is claimed, and no more** (SPEC, the template's description, GAPS). An entry of the original log is recorded once, under the cite of its position:
   - across polls that failed, timed out or were refused;
   - across lost memory, while the record still holds that sensor's cites (or their snapshots);
   - and only the sensor named in a cite can record it.
   
   **Not claimed:** after the record forgets the log's entries (`keep`, `prune`) *and* the collector's memory is lost, those entries are mirrored again. A log that restarts its positions stops the mirror (exit 1) until the owner renames the sensor or clears its memory. Both limits are written in SPEC.
7. Docs: SPEC (the `collect` description near §2's library paragraph; the `cite:` id rule where pushed ids are described), `docs/AGENT-GUIDE.md` (when to copy, read in place, or mirror), and the `docs/GAPS.md` entry. The GAPS entry is moved to *done* for mirroring, with read-in-place for non-ergostat logs left open.

## Files to touch

- `ergostat/mirror.py` (new)
- `ergostat/library/run/collect.py`
- `ergostat/library/templates/collect.yaml`
- `ergostat/spec/engine.py` (`observations`, `_observer`, `read_sensor`)
- `ergostat/intake/envelope.py`
- `ergostat/rollup.py` (`snapshot_of`)
- `tests/test_mirror.py` (new)
- `docs/SPEC.md`, `docs/AGENT-GUIDE.md`, `docs/GAPS.md`
- `docs/roadmap/overnight/external-event-logs.md` (this definition)

## Risks

- **lesson-3 (failing open).** Every input that can be missing is listed with what happens:
  - no `ERGOSTAT_SENSOR`: exit 1;
  - a record without a position, or one that can't be typed: exit 1, nothing said;
  - a position the engine refuses: never said, because the collector runs `valid` first; if said anyway, the next poll exits 1 with the `sensor.refused` reason;
  - lines lost to a timeout or crash: the next poll exits 1 ("not in the record") and the one after re-reads;
  - unreadable memory: recovered from the record;
  - unreadable record while confirming or recovering: exit 1, never "start from the beginning";
  - mixed position types in the record: exit 1.
  
  The fall into it: treating a `known()` miss or a recovery error as "nothing recorded" and moving on.
- **lesson-8 (claim wider than code).** "No one else can claim a log" is supported only by (2) the engine's `log == sensor` binding and (3) the envelope refusal. A second sensor, or a push carrying `source: <our sensor>`, must be shown to fail. The duplicate claim is narrowed for prune plus lost memory and for a restarted log (point 6).
- **lesson-9 (tests that can't fail).** Each test below names the code change that makes it fail. The implementor breaks each one and says in the report that it failed.
- **lesson-1 (check, then write).** Confirm → recover → read → say → write memory is one read-decide-write, held under `kept()`'s flock for the whole poll. The engine never reads the same series twice at once (`self.reading`). No other writer can record a cite id (point 3), so nothing can slip a cite in between.
- **lesson-2 (wall time for order).** The cursor and recovery order by `mirror.key` on the position only, never by an event's `time`. Pages are read by `seq`.
- **lesson-4 (limit with no ceiling).** At most `MOST = 5000` entries per poll (a constant). Recovery pages are 5,000. There is no new config number.
- **lesson-5 (stale state under a reused id).** An entry said again carries the same cite id and is ignored by the store; it is not merged into anything. A log that restarts positions is a different entry under an old id, and is caught by the "went back" check.
- **lesson-6 (work after cancel).** A poll killed by the sensor's timeout writes no memory (the write follows the yield in `kept()`), so the next poll confirms against the record and re-reads.
- **lesson-7 (merged branches).** Merge origin/main and run the suites again before calling it built.
- **lesson-12 (answer every finding).** The five plan-review points are answered in points 1–5 and by the tests marked (P1)–(P5).
- **lesson-13 (stay inside the gap).** No store code changes. The copy-in mode's `_key` is left as it is.

## Acceptance tests

All in `tests/test_mirror.py` unless named otherwise. Each says what breaking it takes.

- `test_position_types_and_order` (P2): `position(9,"int") == position("9","int") == 9` and `< position("10","int")`. `10.0`, `-1`, `"09"`, `True` and `""` are refused with a reason. Text keeps `"2026-01-02T03:04:05Z"` as text. `parse(cite(...))` gives back the same type and value for both kinds. Fails if positions are compared as strings, or if `parse` returns a str for `i`.
- `test_the_confirmed_cursor_crosses_9_to_10` (P2): a source prints positions 8, 9, 10 (10 as an int, 9 as `"9"`), and the poll's lines are recorded through `engine.observations` and `Engine._observer`. The next poll gets `ERGOSTAT_CURSOR=10`, and 9 and 10 are not said again. Fails with string ordering (`"9" > "10"`).
- `test_lost_memory_resumes_after_10_not_9` (P2): after the poll above, the memory file is deleted (and, in a second case, made unreadable JSON). The next poll's cursor is 10, the same as the confirmed one. Fails if `recorded` orders by text or by event time.
- `test_lost_memory_after_rollup_keeps_the_cite`: entries 1–10 recorded, then `rollup.compact` with `now` past the horizon (cites now only in snapshots), then memory deleted → cursor 10. Fails without `rollup.cites`.
- `test_a_position_the_engine_would_refuse_fails_the_poll_with_its_reason` (P1): a record with position `1.5` (int type), and another poll with no cursor field. Each exits 1 with the reason on stderr, says no line, and leaves the cursor where it was. Fails if the collector skips `mirror.position`/`valid`.
- `test_a_said_position_not_recorded_fails_the_next_poll_then_is_read_again` (P1): poll 1's lines are dropped (not recorded). Poll 2 exits 1 naming the position and "not in the record". The engine records a `sensor.refused` reason in a second case, and poll 2's stderr carries that `why`. Poll 3 says them again and the cursor moves. Fails if confirmation is skipped (cursor advanced on saying) or if `said` is not cleared (stalls forever).
- `test_the_engine_refuses_a_cite_of_another_sensor_s_log` (P3): through `run_for` (the engine running), a second sensor `other.main` prints `{"event": "q.arrived", "item": "q/x", "id": "cite:<first sensor>:i:999"}`. It is not recorded, there is a `sensor.refused` about `other.main`, and the first sensor's lost-memory cursor is its own true position, not 999. Fails without the `log == sensor` check in `valid`.
- `test_lost_memory_reads_only_this_sensor_s_cites` (P3): the record holds a pushed event with `source: <first sensor>` and no id, and a second sensor's own cites at position 500. `recorded(events, first)` returns the first's own greatest. Fails if `recorded` drops the source filter or the log check.
- `test_push_refuses_a_cite_id` (P5a): `POST /api/events` with `id: "cite:a.main:i:1"` → refused, nothing of the batch recorded (with a second, valid event in the same batch). Fails without the envelope check.
- `test_a_webhook_refuses_a_cite_id` (P5b): a hook whose `id:` template makes `cite:...` → refused, not recorded.
- `test_the_socket_event_op_refuses_a_cite_id` (P5c): `calls/ops.event` with a cite id → refused, not recorded.
- `test_event_add_without_an_engine_takes_no_cite_id` (P5d): `ergostat event --add q.x --item q/1 --as a.main` records under a uuid, and the parser has no id option. Fails if an id option is added without the check.
- `test_a_block_line_with_a_cite_id_is_recorded_under_a_fresh_id` (P5e) and `test_a_legacy_agent_line_with_a_cite_id_is_recorded_under_a_fresh_id` (P5f): no event with the cite id exists afterwards. Fails if either path starts passing `id` through.
- `test_a_pushed_id_twice_is_still_recorded_once` (P4): on both backends (sqlite and segments), the same non-cite id pushed twice → one event, and the second answers `recorded: 0`. `tests/test_store_conformance.py::test_ids_get_prefix_dedup_and_causes` must pass unchanged.
- `test_a_sensor_line_with_a_plain_id_is_recorded_as_on_main` (P4): a sensor line with `id: "x"` is recorded under a fresh uuid, as before.
- `test_a_log_that_went_back_stops_the_mirror`: cursor 10, source returns positions 0–3 → exit 1, "went back", nothing said. A source that returns the whole log again (0–10) skips quietly. Fails if the check is dropped (new entries would be lost silently).
- `test_mixed_position_types_in_the_record_fail_closed`: the record holds `i` and `t` cites of one log and memory is lost → exit 1 naming both. Fails if `key` coerces.
- `test_at_most_5000_entries_a_poll`: 6,000 new entries → 5,000 said, the lowest, and the next poll says the rest.
- `test_mirror_end_to_end_through_the_engine`: a `collect` use with `mirror: true`, `cursor-field: n` and a command source, run by `run_for`. Events are recorded with `cite:<flow>.<sensor>:i:<n>` ids and `source` the sensor, and a second run with the memory deleted records nothing twice. Fails if `ERGOSTAT_SENSOR` isn't set by `read_sensor`.
- `tests/test_templates.py::test_every_built_in_template_checks_with_its_example` and `test_with_every_default_each_runs_on_stand_ins` still pass with the new params.

Also required: the unit suite and the four browser files pass with rc 0 (no page test skipped for want of a port), and ruff is clean. No example is touched, so `demo_check` is not needed; if an example is added, it runs. Merge origin/main, then run both suites again.

## Size budget

300 net lines of code outside `tests/` and `docs/`: about 120 in `mirror.py`, 100 in `collect.py`, 25 in `engine.py`, 5 in `envelope.py`, 15 in `rollup.py`, 10 in `collect.yaml`, with room for the rest.

## Notes from the plan review (answer each; not blocking)

- Point 6 / lesson-5: 'a log that restarts its positions stops the mirror' is false. The went-back check fires only when the source's newest entry is below the cursor. A restarted log that has already grown past the cursor (cursor 10, new log 0-15) loses entries 0-10 silently: they are skipped as at-or-before the cursor and their cite ids are already recorded. A source that reads after the cursor (Kafka offsets, {cursor}) returns nothing after a reset, so the check never runs. test_a_log_that_went_back_stops_the_mirror covers only the 0-3 case and cannot fail on this. Either detect it (keep a fingerprint of the cursor entry in memory and exit 1 when the source returns that position with different contents) or narrow SPEC, Risks and point 6 to say restarts past the cursor lose entries silently. Either way, add a test of the restart that has grown past the cursor.

## Where it stopped

Built, round 1: every point of the definition, every named acceptance test and a few more, in `tests/test_mirror.py`
(29 tests). 260 net lines of code outside `tests/` and `docs/` (budget 300): `mirror.py` 135, `collect.py` +101,
`collect.yaml` +7, `engine.py` +8, `envelope.py` +5, `rollup.py` +4. No store code changed.

**The plan-review note (point 6, lesson-5), answered both ways.** It is detected where the source shows it: when the
source returns the entry at the cursor's position and what it says (type, item, data) is not what the record holds
under that cite, the poll exits 1 ("LOG went back: its entry at the cursor C is not the one recorded there"). The
record is the fingerprint, so this also works after lost memory. `test_a_restarted_log_that_grew_past_the_cursor_stops_the_mirror`
(cursor 10, a new log 0-15) fails without the check. Where the source does not show it, the claim is narrowed in SPEC
§2 and GAPS: a source that reads only after the cursor (a Kafka offset in `{cursor}`) sees a restart as silence, or as
new entries past the cursor, and loses the restarted log's entries up to the cursor without a word. The check also
can't run when the cursor's event was rolled up or pruned (`get` finds no event under the cite). That case is left
open in GAPS, with what would close it: the source's own epoch in the cite.

**What I chose alone (nobody to ask; the most reversible option each time):**
- A mirror record with no `--id-field` value fails the poll (exit 1, nothing said), as a missing position does. On
  main, copy-in mode skips it with a note.
- When the memory's position type differs from `--position` (the owner changed it), the poll exits 1 and asks for a
  new sensor name or cleared memory. It never reinterprets the old cursor.
- `rollup.cites[source]` is one id, as the definition says. When a log was cited both as `i` and as `t`, it is a list
  of the greatest of each, so `recorded` still fails closed on the mix after a roll-up instead of picking one.
- Malformed `mirror` memory (missing keys) counts as lost and is recovered from the record. A cursor in memory that is
  not a position of its type fails the poll.
- The reason given for a missing said entry is the newest `sensor.refused`/`sensor.failed` about the sensor, as
  specified. It can be older than the poll that lost the entry.

**Breaking each guard (lesson-9).** Each change below made its test fail, and each was put back by hand:
- positions kept as text: position_types, crosses_9_to_10, resumes_after_10;
- `recorded` ordering by `str`: resumes_after_10 (both cases);
- the collector sorting by `str`: crosses_9_to_10, at_most_5000;
- no `rollup.cites`: after_rollup;
- the collector skipping `position` and `valid`: engine_would_refuse. Skipping `position` alone still passes,
  because `valid` refuses `1.5` too;
- the cursor moved on saying: not_recorded (both cases) and partly_recorded;
- `said` not cleared: not_recorded;
- `valid` without the `log == sensor` check: another_sensor;
- `recorded` without the source filter (in the query and in Python): reads_only. The Python filter alone is a
  backstop the query already covers;
- `greatest` without the log check: reads_only;
- no envelope check: push, webhook, socket;
- `observations` passing any id: plain_id;
- no went-back check: went_back;
- no restart check: restarted;
- `key` coercing to `str`: mixed;
- no 5,000 ceiling: at_most_5000;
- no `ERGOSTAT_SENSOR`: end_to_end;
- a recovery error taken as "nothing recorded": store_error;
- `Lines.take` and `Recorder` passing `id`: block_line, legacy_agent;
- an `--id` option on `ergostat event`: event_add.

**Not done here:**
- This clone has no `origin` remote. Local `main` (f7b93bea) is the branch's base and is already merged, so the
  origin/main merge is left to the factory.
- The whole unit suite and the four browser files were not run by me (the factory runs them under the watchdog).
  I ran these files one at a time: test_mirror, test_templates, test_intake, test_rollup, test_store_conformance,
  test_spec_engine, test_calls, test_runner_and_state, test_spec_auxiliaries and test_messages, all passing. Ruff
  is clean.
- ~~An untracked `.mut/` folder ... is in no commit.~~ This was false: see round 2 below.

## Where it stopped, round 2

The review's one finding: `.mut/mut.py`, a scratch mutation script, was committed in 1e563e30 ("work the session
left uncommitted"). The round 1 report said it was in no commit, and that was false. Its 55 lines are also the whole
size overrun: 260 counted + 55 = 315 lines, against a budget of 300.

- The report is corrected above. The round 1 line now says what was true.
- **Not removed yet.** This session's sandbox refused `git rm .mut/mut.py` (twice, in don't-ask mode), and I did not
  try to get around that with other commands. The one thing left before review is
  `git rm .mut/mut.py && git commit`, run by the factory or the owner. With it removed, the branch's code outside
  `tests/` and `docs/` is the 260 lines counted in round 1, within the 300 budget.
- The script is not needed to check the guards. What each change broke is listed under "Breaking each guard" above.
- Nothing else changed in this round: no code and no tests. The suites were not run again for this docs-only commit.

## Where it stopped, round 3 (the unit suite failed after round 2)

The tail the factory passed on has no failing test in it. It shows 64 dots, then nothing: no `[ N%]` at the end of
the line and no closing JSON line from `suite_watch`. So the run was stopped from outside about 64 tests in. It was
not a failing assertion, and not a watchdog kill, which would have printed its line. I could not find a cause in
this branch, so **no code changed in this round**:

- This sandbox refused a whole-suite run, even a serial one, and it refused shell loops. So I could not reproduce
  the stop.
- I ran these files one at a time, each with `-o faulthandler_timeout=200` (a stuck test would dump its stack), and
  all passed: test_mirror (29 tests, 12 s, the slowest 5 s), test_mirror with test_spec_engine under `-n 4` (39),
  test_templates with test_intake and test_rollup (103, 123 s), test_join, test_mended, test_spec_items and
  test_spec_mcp_explain. test_repair2 skipped all 32 of its tests here, for want of its sandbox. Ruff is clean.
- I read the branch's engine change for anything that could hang other tests. `read_sensor` now adds
  `ERGOSTAT_SENSOR`. Every `Sensor` has `of` (ir.py), and nothing else reads that variable. `observations` and
  `_observer` only add an id check, and the envelope change is one `Refused`. The collector's mirror mode runs only
  with `--mirror`, and its copy-in path is the same code moved into `source()`. The segments lock is held for each
  append only, so a mirror opening the record from inside a sensor cannot block the engine.
- `test_mirror.py`'s fixtures undo everything they change: environment and cwd through `monkeypatch`, and the web
  server through `shutdown()` and `server_close()`.
- `.mut/mut.py` is still committed. This session's sandbox refused `git rm` and `git rm --cached` again. It still
  needs `git rm .mut/mut.py && git commit` from the factory.

Left: run the unit suite again (with `-o faulthandler_timeout=180`, so a hang names its test) and remove `.mut/`. If
it stops again, the dump names the test. If that test is outside this branch's files, it is reported here, not fixed
here (lesson-13).

## Where it stopped, round 4 (the unit suite failed on a warm-daemon test)

The unit run that followed round 3 finished: 1971 passed, 69 skipped and 1 failed. The failure was
`tests/test_warm.py::test_the_owners_stop_is_said_only_on_the_run_it_stopped`, at line 181 ("the stopped run's
process replaced": `starts` never reached 3 within 5 s). **No code changed in this round** (lesson-13):

- The test is outside this branch's files. It runs no sensor, no collector, no intake and no rollup, and this branch
  changes nothing in `ergostat/daemons/` or `tests/test_warm.py`. The branch's engine changes are only in
  `observations`, `_observer` and `read_sensor`.
- It passes here when run alone, and so does its whole file (21 passed, 31 s).
- What is likely (read in the code, not reproduced): `daemons/proc.py:hand` (l. 232-250). When the owner's stop
  cancels a warm run after it is held but before its line is handed to the process, the run ends "stopped as the
  owner asked" and `recycle` is not set. That is by design ("the process not blamed"), so the process is not
  replaced and `starts` stays at 2. The test's `item(...).state == "doing"` can hold before the hand-over, and the
  hand-over happens outside the supervisor's lock. Under `-n 8` load that window can be open when `stop_run` is
  called. That would be a race between the test's wait and the hand-over (lesson-10). It would not be a fault of
  this branch. Running it with `Process.hand` delayed by 1 s would settle it, but this sandbox refused that run.
- The fix, whether it goes in the test's wait (wait for the run to be handed over) or in `hand` (replace the process
  anyway), belongs in its own gap about warm daemons, not here.
- `.mut/mut.py` is still committed. This sandbox refused `git rm .mut/mut.py` again. It still needs
  `git rm .mut/mut.py && git commit` from the factory or the owner.

## Where it stopped, round 5 (review 2 answered)

All four findings of review/external-event-logs-2 are answered here (lesson-12):

- **`.mut/mut.py` (blocking): still not removed.** This session's sandbox refused `git rm -q .mut/mut.py` in
  don't-ask mode, the same as in rounds 2 to 4. I did not get around the refusal with another command (emptying the
  file, `git update-index`), because that would go against what the refusal is for. **This is the only thing left
  before review: `git rm .mut/mut.py && git commit`, run by someone whose sandbox allows it.** Without the file the
  branch's code is within budget: 260 lines counted in round 1, plus 2 lines this round.
- **A stale reason for a lost position: fixed.** When the collector says its entries, it now keeps the record's
  `last_seq()` as `mirror.at` in memory. The reason for a missing position is read with `after_seq=at`, so only a
  `sensor.refused` or `sensor.failed` recorded after those entries were said is given, else "not in the record".
  Memory without `at` (written by an older poll) reads at any age, as before. New test:
  `test_an_older_refusal_is_not_given_as_the_reason_for_a_later_loss`. I broke the guard (`after_seq=None`) and it
  failed, then I put it back. `test_a_position_the_engine_would_refuse...` now compares only `type`, `cursor` and
  `said` of the memory, since `at` was added to it.
- **The restart check after compaction: the claim is narrowed.** SPEC §2's "Not claimed" now adds that a restart
  that grew past the cursor also goes unseen once the cursor's own event is rolled up or pruned. GAPS already left
  this open.
- **The reviewer could not run test_mirror.py.** I ran it here: 30 passed.

Ran: `tests/test_mirror.py` (30 passed), and ruff (clean). The whole unit suite and the browser files were not run by
me. origin/main was not merged: this clone has no `origin`.

## Where it stopped, round 6 (the unit suite failed on a reload test)

The unit run after round 5 finished: 1997 passed, 69 skipped and 1 failed. The failure was
`tests/test_reload_in_place.py::test_a_removed_blocks_run_still_takes_messages_while_it_goes`, at line 169:
after `e.close()`, `route.running` still listed the `sleep 30` run of `maker`, because no `agent.ran` was recorded
for it. **No code changed in this round** (lesson-13):

- The test is outside this branch's files. It runs no sensor, no collector, no intake and no rollup. The branch's
  engine change is only in `observations`, `_observer` and `read_sensor`, and none of them is in a block's run or in
  `close()`. The whole file passes here when run alone (11 passed, 28 s).
- What is likely (read in the code, not reproduced): `Engine.run_block` writes `agent.started` (engine.py:863)
  well before the process is spawned and added to `old.LIVE` (engine.py:949-954). Between them it places the run,
  builds its program, trims and opens its log. The test waits only for `agent.started`. When `close()` runs in that
  window (likely under `-n 8` load), `old.kill_all()` finds nothing to kill. The `sleep 30` then starts anyway,
  `close()` gives up after its 5 s wait, and `agent.ran` is never written. That is a shutdown race on main
  (lesson-1, lesson-10), not a fault of this branch.
- This is the same race as the parked lease-shutdown-race gap. Its fix in `run_block` (kill a run spawned after
  `close()` set stop) failed review/upkeep-index-files-3 because it sat in an unrelated branch. So it is reported
  here and not fixed. It belongs in that gap.
- `.mut/mut.py` is still committed. This session's sandbox refused `git rm .mut/mut.py` again (twice, in don't-ask
  mode). It still needs `git rm .mut/mut.py && git commit` from the factory or the owner. That is the one blocking
  finding left, and it needs no other change.

## Where it stopped, round 7 (the unit run stopped at 45%)

The tail the factory passed on has no failing test and no error. It runs to 45% (about 1,050 tests), then stops
mid-line, with no `[ N%]`, no summary and no line from `suite_watch`. So the run was stopped from outside, as in
round 3. It did not fail an assertion. **No code changed in this round**:

- No test of this branch is named. `tests/test_mirror.py` passes here with `-o faulthandler_timeout=120`
  (30 passed, 12 s), so none of its tests hangs. The two unit runs before this one (rounds 4 and 6) finished, with
  about 2,000 passed. Each failed one test outside this branch, reported in that round.
- I could not look further. This sandbox refused `ps`, a run that lists the processes the file leaves behind and
  (as before) a whole-suite run. Without a named test or a stack dump, a change here would be a guess, and a change
  outside the gap's files is out of bounds (lesson-13).
- **`.mut/mut.py` is still committed.** This session's sandbox refused `git rm -q .mut/mut.py` again (don't-ask
  mode). I did not get around the refusal another way. It is still the one blocking finding:
  `git rm .mut/mut.py && git commit`, run by the factory or the owner.

Left: remove `.mut/mut.py`, then run the unit suite again with `-o faulthandler_timeout=180`, so a hang names its
test.

## Where it stopped, round 8

- **`.mut/mut.py` is still committed** (`git ls-files .mut` lists it). This session's sandbox refused
  `git rm -q .mut/mut.py` and `git rm .mut/mut.py` (don't-ask mode). I did not get around the refusal another way
  (a plain `rm` and `git add`, emptying the file), because that would defeat what the refusal is for. The branch
  cannot pass review until someone whose sandbox allows it runs `git rm .mut/mut.py && git commit`. Nothing else is
  needed: with the file removed, the code outside `tests/` and `docs/` is 262 lines, within the 300 budget.
- No code and no tests changed. Ran: `tests/test_mirror.py` with `-o faulthandler_timeout=120` (30 passed, 12 s) and
  ruff (clean). The whole unit suite and the browser files were not run by me. origin/main was not merged: this
  clone has no `origin`.

## Where it stopped, round 9

Each finding of review/external-event-logs-3 is answered here (lesson-12):

- **`.mut/mut.py` (blocking): still committed.** This session's sandbox refused `git rm -q .mut/mut.py` again (in
  don't-ask mode). I did not get around the refusal with another command. It is still the one thing left before
  review: `git rm .mut/mut.py && git commit`, run by the factory or the owner. Without it, the code outside `tests/`
  and `docs/` is 262 lines, within the 300 budget.
- **The `except Exception` message could point the owner the wrong way: reworded.** The catch-all stays. Any failure
  during the poll must stop it (fail closed, lesson-3), and the source's errors can't all be listed in advance. A
  narrowed list would let an unlisted error escape as a bare traceback. Its message no longer guesses the cause. It
  now reads "cannot mirror LOG, nothing said: TYPE: MESSAGE", so the exception's own type and text say what failed.
  The line count is unchanged.
- **The restart check after roll-up:** the review accepts it as a stated limit (SPEC's "Not claimed", round 5). No
  change.
- **The reviewer could not run test_mirror.py:** I ran it here, and all 30 passed.

Ran: `tests/test_mirror.py` with `-o faulthandler_timeout=120` (30 passed, 12 s) and ruff (clean). The whole unit
suite and the browser files were not run by me. origin/main was not merged: this clone has no `origin`.

## Where it stopped, round 10

- **`.mut/mut.py` (blocking, review/external-event-logs-4): still committed.** `git ls-files .mut` still lists it.
  This session's sandbox refused `git rm -q .mut/mut.py` again (don't-ask mode), and I did not get around it with
  another command. The one thing left is `git rm .mut/mut.py && git commit`, run by the factory or the owner. Nothing
  else is needed: without the file the code outside `tests/` and `docs/` is 262 lines, within the 300 budget.
- **The review could not run test_mirror.py:** run here again, 30 passed.
- No code and no tests changed. Ran: `tests/test_mirror.py` with `-o faulthandler_timeout=120` (30 passed, 12 s) and
  ruff (clean). The whole unit suite and the browser files were not run by me. origin/main was not merged here: the
  branch head already carries main (merge 7149d8c1), and the merge queue runs both suites after merging.

## Where it stopped, round 11

- **`.mut/mut.py` (blocking, review/external-event-logs-5): still committed.** This session's sandbox refused
  `git rm -q .mut/mut.py` again (don't-ask mode). Other git commands and the test runs were allowed. I did not get
  around the refusal another way (a plain `rm` then `git add`, emptying the file, `git update-index`), because that
  would defeat what the refusal is for. Eleven rounds have now stopped on this one step. It needs a person or a
  factory step whose sandbox allows `git rm .mut/mut.py && git commit`. No other change is needed: without the file,
  the code outside `tests/` and `docs/` is 262 lines, within the 300 budget.
- The two non-blocking findings of review 5 were answered in round 9 (the `except Exception` message now gives the
  exception's own type and text) and round 5 (`mirror.at` limits the reason to refusals recorded after the entries
  were said). After lost memory there is no `at`, so an older refusal can still be given as the reason. That is the
  rare case the review names. It stays as it is: the poll still fails closed, and only the reason it gives can be
  stale.
- Main was merged in since round 10 (4b243a59), so I ran the files this branch touches again: `tests/test_mirror.py`
  with `-o faulthandler_timeout=120` (30 passed, 12 s), and `tests/test_templates.py` with
  `tests/test_store_conformance.py` (69 passed, 7 skipped). Ruff is clean. The whole unit suite and the browser files
  were not run by me.

## Where it stopped

Parked by the factory (review/external-event-logs-6, 2026-11-21 00:49).

Failed its gates 6 times (the kill rule). Blocking findings:
- .mut/mut.py (tracked, still in `git diff origin/main...HEAD` at df9b0f9a): a scratch mutation script that rewrites ergostat source files, whose own docstring says '(Not committed.)'. It is a stray file headed for an installable main, and its 55 lines are the whole size overrun (316 against 300; about 261 without it). The factory's agent says it can't remove it (df9b0f9a), so the owner or the coordinator must run `git rm .mut/mut.py` and commit. Nothing else needs to change.
