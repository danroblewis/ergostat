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

## Where it stopped

Built, round 1. Every acceptance test exists in `tests/test_remote_chain.py` and passes, the slow three-instance
test included (24 s alone). `tests/test_remote.py`, `tests/test_remote_pair.py` and `tests/test_remote_box_measures.py`
pass unchanged. Ruff is clean. Size: 297 net lines outside `tests/` and `docs/`, within the 380 budget.

**The plan review's note, answered.** `/remote/v1/readings` now carries the answerer's `instance`. M writes into
`readings.json` the `instance` from A's answer, never the one in its cache. The test remakes A (its answer carries a
new id while M's cache holds the old model) and asserts M serves `value: null, time: null`, naming the new id. With
the instance taken from the cache instead, that test fails (`assert (5 is None)`), which was checked.

**Choices made with no one to ask** (each the more reversible or the more closed one):
- The box system M makes for remote A (system `a`) is served with `via: []`, since M declared it. It is never
  cut as a cycle; the parts in it are.
- `/remote/v1/readings` also answers 503 when the instance id is refused, as `/model` and `/status` do, since its
  answer now carries `instance`.
- The served model is also cached in the page by its instance id, so a remade state folder is served at once.
- A remote ergostat from before this change serves no `instance` or `via`, so it is refused as `remote-malformed`.
  Both ends must run this version.
- `test_a_composed_name_that_is_not_a_name_is_refused` names its remote `mm`, so a 62-character name composes to 65
  characters, over 64.
- The three-instance test reads "L never records a newer time after A stopped" as follows. Once L's sensor has
  failed (stale or unreachable) after A stopped, L records nothing newer, checked across a second failure of that
  sensor. Between A stopping and M's next read of A, M still holds A's last answer, not yet marked unreachable, and
  L may take it while its age is within the limit. The test does not claim that no reading is recorded in that
  window.

**Breaking the code to see the tests fail (lesson-9), checked by hand and then reverted:**
- An exclusive create followed by a write in `instance.own` fails the racer test ("instance is empty").
- Serving `got` instead of `got - age` fails both middle tests.
- Taking `readings.json`'s instance from the cache fails the upstream-down test, as above.
- Dropping the `doc.defined` check in `finish` fails the local-wins test (`defined-twice`).
- Dropping the chain-contains-L check fails the cycle test.

Not checked by hand: the reading-age tests. The definition says they fail on main's code, which took `time: None`
and fell back to the local clock. The other refusal tests assert on their own finding code.

**Not run here:**
- the whole unit suite and the four browser files (the factory runs them under the watchdog). Playwright is not
  installed in this container, so `test_diagram_rendering.py -k remote` skipped.
- `demo_check`: no example was touched.
- origin/main: this clone has no `origin`, and `main` holds nothing the branch lacks, so there was nothing to merge.
  The merge queue has to do it (lesson-7).

### Round 2

The review's one finding (blocking, lesson-3): a remote part whose name was taken was skipped, but the same
remote's kept parts that named it were put unchanged, so a served flow drained the local stock that won the name.
This is fixed in `compose.finish`. A taken name now counts as gone for that remote, and the remote's pending parts
are cut against it with `_cut` before any is put: a flow end becomes a cloud, and a cause or an equation is dropped.
This repeats until nothing changes, since a cut can leave a flow with no ends, which is then gone too. A system
named inside a taken system falls back to the remote's box. The `remote-name-taken` message now says that what
names the part is cut. SPEC §4c *Names taken* says the same.

`test_a_local_part_named_like_an_imported_one_wins` now serves `flow a-drain {from: a-open, to: other}` and an
auxiliary whose equation names `a-open`. It asserts that `m-a-drain` has no source (not the local `m-a-open`) and
that the equation is dropped. For m / m-a it serves `flow leak {from: open, to: pool}` from `m-a` and asserts that
`m-a-leak` has no source, so it does not attach to m's `m-a-open`. To show each half fails without the fix, the cut
was turned off by hand and then reverted. Turned off for every remote, the test fails with `'m-a-open' is None`.
Turned off only for `m-a`, the m / m-a assertion fails the same way.

Size: 324 net lines outside `tests/` and `docs/` (297 + 27), within 380. The tests in `test_remote_chain.py` (29),
`test_remote.py`, `test_remote_pair.py` and `test_remote_box_measures.py` pass, and ruff is clean. What round 1 says
was not run is still not run.

### Round 3

The queue's one finding, a conflict with main in `ergostat/remote/compose.py`, is resolved by merging main
(c9d3bab5). Main's remote-proposals-text added `info["served_parameters"]` and `info["names"]` (each composed part's
served name). Both were written where `one` put the remote parts, and this branch moved that `put` into `finish`.
`served_parameters` stays in `one`, since it lists every parameter served. `names` is now written in `finish`, next
to `info["parts"]`, for each part that is actually put, so a part cut or whose name was taken has no served name.

The merge broke one test: main's `test_ergostat_sends_nothing_for_a_for_remote_proposal` fakes `urlopen` with a
`read()` that takes no size, while `client.get` now reads `BODY_MOST + 1` bytes. The fake now takes an optional size.
That is the only line changed outside the files this definition names, and it changes test code only.

After the merge, these pass when run one file at a time: `test_remote_chain.py` (29), `test_remote.py` (12),
`test_remote_pair.py` (1), `test_remote_box_measures.py` (10) and `test_remote_proposals.py` (31). Ruff is clean. The
size is unchanged in substance (the `names` line moved). Still not run here: the whole unit suite, the four browser
files and `demo_check`.

### Round 4

Every finding of review 3, blocking and not:
- *Blocking, docs/GAPS.md:33-39 (the spliced Left).* The Remote systems entry now has one *Left* clause, with no
  mid-sentence resume. It no longer lists this gap, and no longer lists proposals text (done on
  `remote-proposals-text`). The same stale proposals item is gone from the "Left for later" line in
  `docs/proposals/remote-systems.md`, where main still had it. That line now says the two are built.
- *GAPS.md:27, the repeated "`examples/remote-pair/` and its two-instance test".* The repeat was main's. It is
  removed while the entry is reflowed.
- *SPEC §4c Names taken, the over-wide line.* Reflowed.
- *The three-instance test's narrower claim, not in SPEC.* SPEC §4c *Readings through a middle* now says it as
  the test shows it. Between A stopping and M's next read of A, M still serves A's last answer unmarked, and L
  may take it while its age is within the limit. Once L's reading has failed after A stopped, L records nothing
  newer for it.

This round changed docs only, and no code. The review of remote-mtls had a SPEC:722 wording note, but it is about
that branch's text, which this branch does not have.

### Round 5

Every finding of review 4:
- *Blocking, readings.py `_num` accepted NaN (lesson-3, lesson-2).* `_num` now also requires `math.isfinite`, so a
  `now` or `time` of NaN or Infinity counts as none. `read` refuses it ("has no time" / "without its own time"),
  `keep` stores `age: null` for it, and `relayed` then serves `value: null, time: null`. The two age tests in `read`
  are also written as `not age >= -FUTURE_LEAST` and `not age <= limit`, so an age that is not a number is
  refused even if it ever got past `_num`. `test_a_reading_with_no_time_or_no_now_is_stale` gains time NaN,
  now = time = Infinity, and now NaN. `test_a_middle_serves_the_origin_age_not_its_own_time` gains A answering
  time NaN, then now = time = Infinity: M refuses it, `readings.json` holds `age: null`, and M's `/readings`
  serves null. With `isfinite` removed by hand (comparisons kept), both tests fail (`human(NaN)` raises
  `ValueError`). The change was then put back. SPEC §4c (reading age) says a non-finite `now` or `time` counts as none.
- *origin/main has moved (lesson-7).* This clone has no `origin`, and local `main` is already merged (bd17b43d), so
  there is nothing to merge here. The merge queue does it.
- *Non-blocking, a later remote's box beats an earlier remote's served system of the same name.* The code is
  unchanged, since it fails closed. SPEC §4c *Names taken* now says that boxes are put when `remotes:` is read,
  before any remote's parts. `test_a_local_part_named_like_an_imported_one_wins` now checks this: m serves system
  `a`, the box `m-a` of remote m-a keeps the name, and m gets `remote-name-taken`.

Size: about 4 net lines added in `readings.py`, within 380. After this round these pass: `test_remote_chain.py` (29),
and `test_remote.py`, `test_remote_pair.py` and `test_remote_box_measures.py` (23). Ruff is clean. Not run here:
the whole unit suite, the four browser files and `demo_check`.

### Round 6

The queue's finding was a conflict with main (48b1481a, which brings in `remote-mtls`) in three files. It is resolved
in the merge commit 78240625, keeping both sides:
- `client.get` opens the URL with main's TLS context (`context=` only when `tls:` is given) and still reads at most
  `BODY_MOST + 1` bytes, failing past that ("answer too large").
- `readings.answer` passes main's `tls=` to `client.get` and still refuses a body that is not a dict.
- The "Left for later" line in `docs/proposals/remote-systems.md` lists only the IR as left among those three, and
  says that proposals text, a remote composed of remotes and mutual TLS are built.

The merge also spliced GAPS.md's *Remote systems* entry cleanly but wrongly (lesson-7). It left a dangling
"(`remote-proposals-text`; …)" fragment, a repeated `examples/remote-pair/` line, a repeated closed-box paragraph and
two *Left* clauses: one said mutual TLS was left, and the other said a remote composed of remotes was left. The
entry now has one Done text, with mutual TLS added after this gap's sentence, and one *Left* clause that lists
neither.

After the merge, `test_remote_chain.py` failed twice. Its fake `client.get` (`_Upstream`) took no `tls` argument,
and `readings.answer` now passes one. The fake now takes `tls` and passes it on. That is a test-only change. After
it, these pass when run one file at a time: `test_remote_chain.py` (29), `test_remote_mtls.py` (23),
`test_remote.py`, `test_remote_pair.py` and `test_remote_box_measures.py` together (23), and
`test_remote_proposals.py` (31). Ruff is clean. No code changed in substance outside the merge, so the size is as in
round 5. Not run here: the whole unit suite, the four browser files and `demo_check`.

### Round 7

The review's one finding: M's box for remote A was served with the description "remote: run by the ergostat at
URL". So A's url, with any user and password in it, reached every consumer of M. This is fixed in `serve.py`
(`box`). If a remote's box (a `RemoteVia` with an empty chain) still has the generated description that names the
url, it is served as `remote: NAME, composed from another ergostat` instead. A `description:` the owner wrote in
`remotes:` is served as written, since the owner wrote it (the reversible choice; nothing looks for a url inside
it). M itself still shows the url-naming text locally, as before. The text is one constant, `compose.WHERE_TEXT`,
so the two cannot drift apart. SPEC §4c (*`via`*) says so.

The new `test_a_middle_never_serves_its_remotes_url` gives M a remote at
`https://user:secret@a.example.invalid:8443` and another with an owner's description. It asserts three things: no
url or password appears anywhere in M's served model, the owner's text is kept, and M's own loaded model still shows
the url. With the replacement turned off by hand, the test fails ("'secret' is contained here"). The change was
then put back.

Size: about 12 net lines added outside `tests/` and `docs/`, within 380. These pass: `test_remote_chain.py` (30),
and `test_remote.py`, `test_remote_pair.py` and `test_remote_box_measures.py` (23). Ruff is clean. Not run here:
the whole unit suite, the four browser files and `demo_check`. This clone has no `origin`, so there is nothing new
to merge.
