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
