# remote-of-remotes: a remote's own imported parts are served with the chain of instances they came through, so a consumer composes parts two or three ergostats away, cuts cycles, caps depth and breadth, and reads them with the age they have at their origin
depends-on: []

## Definition of done

Today `serve.document` leaves out every part with a `RemoteVia` ("a remote of a remote is not composed"). When this branch is done, an ergostat M that composes a remote A serves A's parts to its own consumer L. L composes them as its own remote parts, for example `stock.m-a-open` in system `m-a` within `m`. The terms below have one meaning each:

**Instance id.** Every ergostat state folder has one file, `<state>/instance`, holding exactly 16 lowercase hex characters and a newline. This is the id of the instance. `ergostat/remote/instance.py: own(state) -> str` reads it, and raises `InstanceError` (with the reason) in these cases:
- the file is empty;
- after stripping one trailing newline, the content does not fully match `^[0-9a-f]{16}$`;
- the file can't be read (any `OSError` other than "not there", including when the path is a directory).

A bad file is never rewritten or replaced. Only a missing file is created, like this:
1. Write the id to a temp file in the same folder, named `instance.<pid>.<8 hex>.tmp`, through the step `_fill(path, text)`, then `fsync` it.
2. `os.link` the temp file to `instance`. If that raises `FileExistsError`, another process won and this is fine.
3. Unlink the temp file in all cases (`finally`).
4. Read `instance` again and validate it. Every racer returns what the file holds, so the file can never be seen empty or half-written.

There is no exclusive create followed by a write, and no check-then-create step.

**What a server serves.**
- `/remote/v1/model` gains a top-level `instance` (the server's id) and `/remote/v1/status` gains `instance`.
- `version_of` hashes `format`, `instance` and `sections`, so a new instance id is a new version and a new ETag.
- Every served part, in every served section, carries `via`: a list of instance ids.
- **`via` is defined as:** the ids of the ergostats the part passed through before reaching the server, origin first. It never includes the server itself. A part the server declares has `via: []`. A part the server imported from remote A has `via` = A's served `via` for that part plus A's `instance`.
- Stand-ins for missing references (`_stand_in`, and `REMOTE-gone`) are marked as stand-ins and are not served.
- If the server's own instance id raises `InstanceError`, `/model` and `/status` answer 503 with `{"error": "this ergostat's instance id: WHY"}` and serve no model.

**Chain and depth.** At consumer L, the chain of a part served by remote M is `via + [M.instance]`. Its depth is the length of that chain: 1 for M's own parts, 2 for A's parts through M. `DEPTH_MOST = 3` is a module constant, not configurable.

**What `compose.one` checks.** It checks the served model before composing anything, in this order:

1. **L's own id.** If L's own `instance.own` raises, no remote is composed. Each remote gets the finding `remote-instance`, and its system box and source are still put, as for a remote never read.
2. **Malformed: the whole remote is refused.** No part of it is composed and the finding is `remote-malformed`, naming what was wrong. This happens when any of these is true:
   - `instance` is missing, or is not 16 hex;
   - any served part has no `via`, or its `via` is not a list;
   - any id in a `via` is not 16 hex;
   - a `via` holds more than `VIA_MOST = 8` ids;
   - a chain repeats an id.
3. **Too big: the whole remote is refused.** If the served sections hold more than `PARTS_MOST = 2000` parts in total, nothing is composed and the finding is `remote-too-big`. Depth is capped by `DEPTH_MOST` and breadth by this.
4. **Cycle.** If `M.instance` equals L's id, the whole remote is refused (`remote-cycle`). Otherwise, any part whose chain contains L's id is cut (`remote-cycle`, one finding per remote, with the count).
5. **Too deep.** A part whose chain is longer than `DEPTH_MOST` is cut (`remote-too-deep`, one finding per remote, with the count).
6. **Bad names.** A part whose served name, composed name `f"{remote}-{name}"`, or sensor name does not fully match `^[a-z0-9][a-z0-9-]{0,63}$` is cut (`remote-bad-name`, naming the first offending name in full). The composed name must also match the local `NAME`.

Cut parts join the existing `gone` set in `parts()`, so `_cut` removes references to them from the parts that are kept: a flow end becomes a cloud, and a cause or an equation is dropped. Each composed part's `RemoteVia` keeps its chain, which is what serving it on to the next consumer uses.

**Name collisions.** Remote parts are no longer `put` while each file is read. `compose.one` keeps them in `info["pending"]`, and `compose.finish` puts them first, after every file and include has been read:
- A local part always wins. A remote part whose `(section, name)` is already defined is not put, and gets the finding `remote-name-taken`, naming both. It is never a `defined-twice` error.
- Between remotes, the first one declared wins and the later one gets `remote-name-taken`. Example: remote `m`'s `a-open` and remote `m-a`'s `open` both make `m-a-open`.
- `finish` finds the remote behind a reference by the longest matching `REMOTE-` prefix.

**Reading age.** In `readings.read`, a reading is taken only if all of these hold:
- the answer has a numeric `now`; with none, it is refused and the reading is not taken;
- the entry has a numeric `time`; a reading with no time is stale;
- the entry carries no `unreachable`; an entry with `unreachable` is refused, giving the upstream's reason.

The age is computed as `now - time`, both in the answering server's clock, so clocks are never compared across machines. The reading is stale when the age is greater than `max(STALE_LEAST, STALE_RUNS * period)`, or when the age is less than `-FUTURE_LEAST` (5 s). A time more than 5 s in the answerer's future is stale, never fresh.

**What a middle serves for an imported series.**
- When `readings.answer` gets a body from A, it writes `<state>/remotes/a/readings.json`. It writes the whole answer each time, replacing the file atomically, never merging. The file holds A's `instance`, M's receive time `got`, and, per series and ref, `value`, `age` (A's `now` minus A's `time`) and `unreachable` if A said so.
- When A does not answer, the file is not rewritten. Instead `unreachable: WHY` is added through the same whole-file replace, with the old ages and `got` kept.
- In M's `/remote/v1/readings`, a requested series or ref that belongs to an imported part is answered from that file. The series or ref is mapped to the sensor's `query` (for a ref, the part's `main` sensor, else its only sensor).
- The answer's `time` is `got - age`. This is the origin's age carried into M's clock, never M's own record time, so a hop adds no freshness.
- If A is unreachable, the answer keeps the old time, so its age grows, and carries `unreachable`.
- If the file is missing, unreadable, lacks the entry, or holds an `instance` other than the one M's cached model of A names, the answer is `{"value": null, "time": null, "why": ...}`. L treats that as stale.
- A ref to an imported goal answers `value: null, time: null` with a reason.

**Body size.** `client.get` reads at most `BODY_MOST = 16 MB` and fails the call ("answer too large") past that.

**Docs.** SPEC §4c gains a paragraph, *A remote composed of remotes*, stating each rule above, the constants and the new finding codes. The §4c address table notes `instance` and `via`. The "Left" line in GAPS.md, the "Left for later" line in `docs/proposals/remote-systems.md`, and the docstrings of `serve.py`, `compose.py` and `readings.py` are updated. The remote section of `docs/AGENT-GUIDE.md` gains one sentence.

## Files to touch

- `ergostat/remote/instance.py` (new)
- `ergostat/remote/serve.py`
- `ergostat/remote/compose.py`
- `ergostat/remote/readings.py`
- `ergostat/remote/client.py`
- `ergostat/web/remote_api.py`
- `tests/test_remote_chain.py` (new)
- `tests/test_remote.py` (only where an existing test's served model now has `instance`/`via`)
- `docs/SPEC.md`, `docs/GAPS.md`, `docs/proposals/remote-systems.md`, `docs/AGENT-GUIDE.md`

## Risks

- **lesson-1.** Two ways in:
  - Two processes (the runner and the page server) make the instance id at once. An exclusive create followed by a write lets the loser read an empty file. Prevented by the temp-file-plus-`os.link` publish and the re-read after it.
  - `readings.json` written by read-merge-write in two processes would lose entries. Prevented by writing the whole answer, never merging. The one exception is the `unreachable` annotation, which re-reads and replaces the file in one step. A lost race there leaves either the old file, which ages, or the marked one, and neither looks fresh.
- **lesson-2.** Age compared across two machines' clocks, or a hop re-stamping a reading with its own time. Prevented because age is only ever `now - time` within one answerer's clock, carried as `age` across hops, and a future time is refused.
- **lesson-3.** Cases that could fail open:
  - a missing or malformed `instance` or `via`;
  - an unreadable own instance file;
  - a reading with no `time` or no `now`;
  - a missing `readings.json` or entry;
  - an upstream that is down.

  Each refuses or counts as stale. Today's code accepts a reading with `time: None` and falls back to the local clock when `now` is missing. Both are changed.
- **lesson-4.** Depth is capped, but breadth, the via length and the body size would not be. `DEPTH_MOST`, `VIA_MOST`, `PARTS_MOST` and `BODY_MOST` are fixed constants, checked on every load and on every call.
- **lesson-5.** A's state folder is remade with a new instance id, while M's `readings.json` still holds ages from the old one. The file's `instance` is checked against the cached model. `instance` is in the version, so consumers refetch.
- **lesson-7.** The deferred `put` of remote parts changes the load order that `uses:` and `finish` see. Merge origin/main in and run both suites again.
- **lesson-8.** Claims to keep true:
  - "a hop adds no freshness": tested by the skew test and the upstream-down test;
  - "local always wins": tested with the local part in an include read after `remotes:`.

  SPEC must not say "never stale" or claim more than these tests show.
- **lesson-9.** The race tests must put the competitor in the window. The report says, for each test below, which change to the code made it fail.
- **lesson-10.** The three-instance test waits with polling until the state is reached, never a fixed sleep, and is marked `slow`.
- **lesson-11.** Composed names and sensor names come from remote input and become part names and series names. They are checked against `^[a-z0-9][a-z0-9-]{0,63}$`. The only path built here, the cache folder, uses the local remote name, which is already checked. The temp files are deleted by their own names only.
- **lesson-13.** An unrelated failure is named in the report, not fixed here.

## Acceptance tests

All tests are in `tests/test_remote_chain.py`.

**Instance id**
- `test_the_instance_id_is_made_once_and_kept`: the first `own` makes 16 hex and the second returns the same. Fails if regenerated.
- `test_a_racer_in_the_gap_before_the_id_is_written_reads_a_whole_id` (lesson-1, lesson-9): monkeypatches `instance._fill` so a competing `own()` runs to completion before the first caller's text is written. Both callers return the same 16-hex id, and no `InstanceError` is raised. Fails under an exclusive create followed by a write, because the competitor reads an empty file.
- `test_an_empty_malformed_or_unreadable_instance_file_is_refused_not_replaced` (lesson-3): parametrized over `""`, `"xyz\n"`, 17 hex, and a directory at the path.
  - `own` raises and the file is unchanged;
  - `/remote/v1/model` answers 503;
  - L composing any remote gets `remote-instance` with no remote parts.

**Serving and composing**
- `test_a_middle_serves_its_imported_parts_with_their_chain`: M, with A's model in its cache, serves `a-open` with `via == [A]` and its own parts with `via == []`. It serves `instance == M` and no stand-ins. The version changes when only the instance changes.
- `test_parts_two_hops_away_are_composed_and_read_through_the_middle`: L composes `stock.m-a-open` in `m-a` within `m`, and its sensor queries `{source: m, series: sensor/a-open.main}`.
- `test_a_part_coming_back_is_cut_as_a_cycle` (lesson-3): a part whose `via` holds L's id is cut with `remote-cycle`, and a kept flow to it becomes a cloud. With `M.instance == L`, nothing is composed.
- `test_a_chain_longer_than_the_most_is_cut` (lesson-4): a chain of 3 is kept, and a chain of 4 is cut with `remote-too-deep`.
- `test_a_remote_with_missing_or_malformed_instance_or_via_is_refused` (lesson-3): parametrized over these cases:
  - no `instance`;
  - instance `"XYZ"`;
  - a part without `via`;
  - `via` given as a string;
  - an id of `"abc"`;
  - a repeated id;
  - `VIA_MOST + 1` ids.

  Each case composes no part of m, gives `remote-malformed`, and the model still loads.
- `test_a_remote_serving_more_parts_than_the_most_is_refused` (lesson-4): `PARTS_MOST + 1` parts gives `remote-too-big` and nothing composed; exactly `PARTS_MOST` is composed. `PARTS_MOST` may be monkeypatched small for speed, plus an assertion that the shipped value is 2000 and that `remotes:` accepts no key for it.
- `test_a_composed_name_that_is_not_a_name_is_refused` (lesson-11): served names `Open`, `a_b`, and a 62-character name (composed length over 64), plus a bad sensor name. Each is cut with `remote-bad-name`, and the other parts are composed.
- `test_a_local_part_named_like_an_imported_one_wins`: a local `stock.m-a-open`, defined in an include read after `remotes:`, is kept, with no `defined-twice` and with `remote-name-taken`. Remotes `m` and `m-a` colliding: the first declared wins and the second gets `remote-name-taken`.

**Reading age**
- `test_a_reading_with_no_time_or_no_now_is_stale` (lesson-3): `time: None` with a value is refused, and a body with no `now` is refused. Fails on today's code.
- `test_a_reading_from_the_future_is_refused` (lesson-2): `time = now + 60` is refused and `time = now + 2` is taken.
- `test_a_middle_serves_the_origin_age_not_its_own_time` (lesson-2): A's clock is 1,000 s ahead and its reading is 50 s old. M's `/readings` for `sensor/a-open.main` answers `time` ≈ M's `now - 50` (within 1 s), even after M has just recorded the value. Fails if M serves its own record time, or A's raw time.
- `test_a_middle_with_its_upstream_down_never_serves_fresh_looking_data` (lesson-3): after one good answer, A fails. M serves the old time with `unreachable`, and L's `readings.read` refuses it with a reason naming a.
  - With no `readings.json` at all, M serves `value: null, time: null`, and L refuses.
  - With a `readings.json` whose `instance` differs from the cached model, M also serves null (lesson-5).
- `test_a_larger_answer_than_the_most_fails_the_call` (lesson-4): a local server sends `BODY_MOST + 1` bytes and `client.get` returns status 0 with "too large".

**End to end**
- `test_three_instances_read_a_part_two_hops_away_and_mark_it_stale_when_the_origin_stops` (marked `slow`; three `ergostat run` processes, killed by process group in `finally`):
  1. L's reading of `m-a-open` reaches A's value.
  2. A is stopped.
  3. Polling until the state is reached, L's sensor fails with a stale or unreachable reason, and L never records a newer time for that series after A stopped.

**Existing suites**
- `tests/test_remote.py` and `tests/test_remote_pair.py` still pass.

## Size budget

380 net lines of code outside `tests/` and `docs/`.

## Notes from the plan review (answer each; not blocking)

- readings.json's `instance` has no defined source: /remote/v1/readings does not carry `instance`, so the implementor can only copy it from M's cached model, which makes the lesson-5 remake check vacuous. The planned test plants a mismatched file and passes either way (lesson-9). Require A's /readings answer to carry `instance`, have M write that value, and add a test that remakes A's state (new id) while M's cache holds the old model, asserting M serves value/time null. The test must fail if the instance is taken from the cache.
