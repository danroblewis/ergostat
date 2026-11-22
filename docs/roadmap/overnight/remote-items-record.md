# remote-items-record: a remote's items in the Items page and its events in the Record page, read in place, bounded and failing closed
depends-on: []

## Definition of done

What exists on main now: the remote API serves `/remote/v1/items`, `/remote/v1/items/ID`, `/remote/v1/counts` and `/remote/v1/events` (`ergostat/web/remote_api.py`). The cursor cache `ergostat/remote/events.py` is read only by `ergostat remote events NAME`. The Items and Record pages show local items and events only. GAPS.md lists this slice as *Left* ("the remote's events in the Items and Record pages") and the proposal says "(a later slice)". This branch builds that slice. It adds no new page or panel: the remote's items are shown in the Items tab, framed and marked *remote NAME* like the item systems there. Its events are shown in the Record page under a `remote=NAME` scope, the same way the page already scopes `machine=` and `item=`.

When it is done:

1. **The remote name is checked against an allowlist.** The `remote=NAME` parameter of `/api/items`, `/api/items/ID` and `/api/events` must be a key of `spec.remotes`. Any other name gets 400 `{"error": "no remote NAME (this model's: …)", "ok": false}`. The request is never answered with local items or events, and never with an empty list. Without `remote=`, all three routes behave exactly as on main.
2. **The item ID is checked before anything is sent.** `/api/items/ID?remote=NAME` refuses an ID that does not fully match `^[A-Za-z0-9_][A-Za-z0-9_.:@#+=-]{0,199}$`, or that contains `..`. The refusal is a 400 and no request goes to the remote. This is an allowlist, not a denylist: an ID with `/`, `%`, whitespace or `..` is refused. An accepted ID is still passed to `client.get` as `urllib.parse.quote(ID, safe="")`. SPEC says a remote item whose ID falls outside the pattern is listed but cannot be opened here.
3. **`/api/items?remote=NAME`** (optional `kind`, `state`, `n`, `offset`) answers `{"remote", "url", "ok", "why", "read", "age", "counts": {kind: {state: n}}, "total", "items": [...]}`.
   - `counts` comes from `/remote/v1/counts`.
   - `items` comes from `/remote/v1/items`, with `n` clamped to 1..500 and `offset` clamped to 0..100,000. Each item is marked `"remote": NAME`.
   - The page links each item to `/item/ID?remote=NAME`, and also to the remote's own page (`URL/item/ID`).
4. **`/api/items/ID?remote=NAME`** answers `{"remote", "ok", "why", "read", "age", "item": <the remote's detail>}`. When the remote says 404, this route says 404 `{"error": "no such item at NAME"}`. It never falls back to a local item with the same ID.
5. **`/api/events?remote=NAME`** (optional `n` ≤ 1,000 and `type` glob, both applied to the cache) answers `{"remote", "ok", "why", "read", "age", "events": [...]}` from `remote/events.py`'s cache. Events are ordered by `seq` and each is marked `"remote": NAME`.
6. **The items side has a hard limit on requests per remote per period.**
   - The period is the remote's `every`, clamped to [10 s, 600 s] when used.
   - `ergostat/remote/items.py` makes at most `ASKS = 8` requests to one remote in one period. This covers counts, listings and details together, whatever variety of `kind`, `state`, `n`, `offset` or ID is asked.
   - `/remote/v1/counts` is cached per remote and asked at most once a period.
   - A listing is cached by `(kind, state, n, offset)` and a detail by ID, at most 32 entries each per remote, oldest evicted first. A cached answer younger than the period is served without asking.
   - Once the budget is spent, a cached answer is served with its `age`. With nothing cached, the answer is 503 `{"error": "NAME asked 8 times this period; again in Ts", "ok": false}`, never an empty listing.
   - `ASKS`, the clamp and the 32-entry limits are module constants, not config.
7. **A failed ask is not repeated within its period.** After a remote fails to answer, more asks to it in the same period do not go out. The cached answer is served with `ok: false` and `why`, or there is an error if nothing is cached.
8. **Every cache decision is made inside one per-remote lock.** On the items side the lock is `items._lock(name)`. It is held across reading the cache, deciding whether to ask (freshness, budget, failure), calling `client.get`, writing the cache and evicting. In `events.follow` one per-remote lock is held across the once-per-period check, the status call, the pages, the cursor update and the window or count trim. The fields `cursor`, `asked`, `ok` and `why` are never read or written outside it.
   - Events are read from the remote at most once a period, with at most 1 status call and 5 pages.
   - The CLI's `ergostat remote events NAME` passes `force=True`, which skips the period check but still takes the lock.
   - A lock is per remote, so a remote that hangs blocks only callers of that remote. Each ask is bounded by the client's timeout (`cache.TIMEOUT`, 3 s).
9. **Events are deduplicated and ordered by `seq`, never by time.** Only events with `seq` greater than the cursor are appended, so a page fetched twice adds nothing. If an answer's `last_seq` is less than the cursor (the remote's record was made again under the same name and URL), the kept events and cursor are cleared and the read starts again from `max(0, last_seq - 1000)`.
10. **Nothing that cannot be read is treated as empty.**
   - A token file that is missing, unreadable or empty gives `ok: false` with the token-file reason. With nothing cached it is a 502 with that reason.
   - A remote that does not answer, or answers 401/403/5xx, gives the same.
   - A 200 whose body is not the expected shape (no `events` list, no `items` list, `counts` not a dict) counts as a failure with "unexpected answer". It is never read as zero items.
   - A remote that has failed shows its cached events and items with their `age`, `ok: false` and `why`.
   - The Record page then says "NAME does not answer (why); these were read T ago", and the Items section says the same. Neither ever says "Nothing recorded yet." for a remote that failed.
11. **The pages.**
   - The Items page, unchanged for local items, adds one section per remote, framed and marked *remote NAME · URL*. It holds the remote's counts by kind and state and its newest items. It is fetched by its own call, so a slow remote never delays the local listing.
   - `/item/ID?remote=NAME` shows the remote item's fields and history read-only, marked remote, with no message box or actions.
   - The Record page's filter bar links to each remote's events (`/record?remote=NAME`). Under that scope it lists them with the same `eventsTable`, and item links carry `remote=NAME`.
12. **Docs are current.**
   - SPEC §4c and the Items and Record sections describe what is shown, the request budget, the ID pattern and the failure states.
   - The proposal's "(a later slice)" and "and, later, the Record page" sentences are updated.
   - The *Left* list for Remote systems in GAPS.md no longer lists this item.
   - AGENT-GUIDE §3 step 5 says the remote's items can be seen in the Items page but are still never folded or counted locally.
13. All the house "done" conditions hold:
   - acceptance tests pass;
   - the unit suite passes;
   - the four browser files pass with rc 0 and no page test skipped for want of a port;
   - ruff is clean;
   - `demo_check` passes on `examples/remote-pair` if it is touched;
   - origin/main is merged in and the suites are run again.

## Files to touch

- `ergostat/remote/items.py` (new): the per-remote lock, the period budget, the counts, listing and detail caches, the ID pattern, and `RemoteRefused(code, why)`.
- `ergostat/remote/events.py`: the per-remote lock across all of `follow`, the once-per-period check, `force`, ok/why/age state, dedupe by `seq`, reset when the remote's record is made again, and the shape check.
- `ergostat/web/server.py`: the `remote=` branches of `events` and `items` in `api()`, `RemoteRefused` mapped to its status code beside `BadSet`, and `remotes` (names and urls) added to the local `/api/items` answer.
- `ergostat/web/static/pages.js`: the Items page's remote sections, the read-only remote item view, and the Record page's `remote=` scope and links.
- `ergostat/cli/remote.py`: `events.newest(..., force=True)`.
- `tests/test_remote_items.py` (new), `tests/test_items_page.py` (one browser test).
- `docs/SPEC.md`, `docs/proposals/remote-systems.md`, `docs/GAPS.md`, `docs/AGENT-GUIDE.md`.

## Risks

- **lesson-1.** Three read-decide-write steps could be split from their writes. The once-per-period events check followed by the cursor write. The items cache: fresh? within budget? ask, then store and evict. The budget counter: read, compare to 8, increment. If any is done outside the per-remote lock, concurrent page polls (several tabs, the 3 s Record poll) each ask the remote and append duplicate pages. On main, `follow` already reads and writes `kept["cursor"]` outside `_lock`.
- **lesson-3.** Several inputs can be missing:
  - an unreadable token file;
  - a remote that does not answer;
  - a 401 after a token is revoked;
  - a malformed body;
  - an unknown remote name;
  - the remote's 404 for an item.

  Main's `follow` returns `None` with no cache, which a page could draw as "nothing recorded". Each case must produce `ok: false` or an error status, never an empty list, and never the local item.
- **lesson-4.** Without a ceiling, the listing cache could be paged past with distinct offsets so that every poll asks the remote. Other things that need a ceiling: `n`, `offset`, `every` (floor 10 s, no ceiling) and event pages. All are clamped by constants, and the asks per remote per period have a hard ceiling of 8.
- **lesson-11.** The ID goes into a URL path sent with our token. Without the allowlist, `../events` or `%2e%2e` would reach other remote routes. The allowlist runs before any request, and quoting is a second layer.
- **lesson-2.** Merging event pages by time, or keeping events by `time >= since`, could duplicate or reorder them. Order and dedupe are by `seq`. The window trim stays on time only because it is the documented day-long window, not a judgment of which event is newer.
- **lesson-5.** A remote whose record was made again under the same name and URL restarts its `seq`. The old cursor would then hide every new event, and the old events would be mixed in with the new ones.
- **lesson-6.** A hung remote holds its lock. Each ask must be bounded by the client's timeout, and the lock must be per remote so the local page and other remotes are not blocked.
- **lesson-8.** SPEC's claims ("at most 8 requests per remote per period", "events read at most once a period", "a traversal ID is refused before any request") each need a test that fails if the claim is false. A test is named for each below.
- **lesson-9.** Every test below must be shown failing with its guard broken. The report says how each was broken (lock removed, budget check removed, ID check removed, shape check removed).
- **lesson-7.** origin/main must be merged in and the suites run again. gap/remote-box-measures is leased and touches `remote/__init__.py` and the box.
- **lesson-10.** The concurrency tests synchronize with a `threading.Barrier` and a fake `client.get`, not sleeps. The browser test waits on page content, never on a fixed time.
- **lesson-13.** A failure in a suite this change did not touch is reported, not fixed here.

## Acceptance tests

All in `tests/test_remote_items.py` unless noted. `client.get` and `client.token_of` are monkeypatched with a counting fake, and `time.time` is monkeypatched to move between periods.

- `test_an_unconfigured_remote_is_refused_never_answered_locally`: with a local item `t-1`, these all give 400 and make no `client.get` call: `/api/items?remote=nope`, `/api/items/t-1?remote=nope` and `/api/events?remote=nope`. None of them returns `t-1` or an empty list. (lesson-3)
- `test_a_traversal_id_is_refused_before_any_request`: each of these IDs gives 400 with zero calls to `client.get`: `../events`, `a/b`, `..`, `%2e%2e`, `x y` and a 201-character ID. A valid `t-1` reaches `client.get` with path `items/t-1`. (lesson-11; fails if the allowlist check is removed or moved after the call)
- `test_repeated_listings_in_one_period_ask_the_remote_once_each`: 20 identical `/api/items?remote=R` calls, then 20 `kind=K` calls, all in one period, make exactly one counts request, one listing request for the plain query and one for `kind=K`. After the period has passed, one more call asks again. (lesson-4)
- `test_paging_past_the_cache_is_bounded_per_period`: 50 calls with distinct `offset`s in one period make at most 8 requests to the remote. The calls beyond the budget that have no cached answer get 503 with "again in", not an empty list. (lesson-4, lesson-3; fails if the budget is removed or is counted per cache key)
- `test_a_remote_that_does_not_answer_is_asked_once_a_period`: with the fake returning status 0, 10 listings and 10 details in one period make 1 request. The answers are 502 with the reason, then the cached answer with `ok: false` once one has been cached. (lesson-3, lesson-4)
- `test_concurrent_item_listings_ask_once`: 8 threads behind a Barrier call `items.listing(spec, "R", …)` with the same query. The fake blocks the first caller until all threads have started. Exactly one request is made. (lesson-1; fails if the freshness check or the write is outside `items._lock`)
- `test_concurrent_record_polls_read_events_once_a_period`: 8 threads behind a Barrier call `events.follow(spec, "R")`. Exactly one status call and one events page go out, the cache holds each `seq` once, and the cursor equals the last `seq`. Also tested through the gap: `client.get` is monkeypatched so a second `follow` is started from inside the first one's events call, which must wait and then see the period as already read. (lesson-1; fails if the period check or cursor write is outside the lock)
- `test_events_are_merged_by_seq_and_a_remade_remote_restarts`: a page returned twice adds no events. An answer whose `last_seq` is below the cursor clears the kept events and restarts the cursor from the new `last_seq`. (lesson-2, lesson-5)
- `test_record_shows_cached_events_with_age_when_the_remote_stops`: after one good read, the remote stops answering, and the next period's `/api/events?remote=R` returns 200 with the cached events, `ok: false`, `why` saying "unreachable", and `age` > 0. Its `events` is not empty. (lesson-3)
- `test_an_unreadable_token_file_is_an_error_not_no_events`: when the token file is a directory, missing, or empty, `/api/events?remote=R` and `/api/items?remote=R` give 502 whose `error` names the token file. No `client.get` call is made and no `events: []` is returned. (lesson-3)
- `test_an_item_from_a_remote_that_does_not_answer`: `/api/items/t-1?remote=R` with the remote down gives 502 with the reason. With an earlier answer cached, it gives that answer with `ok: false` and `age`. A local `t-1` is never returned. When the remote says 404, the answer is 404 "no such item at R". (lesson-3)
- `test_an_unexpected_answer_is_a_failure`: 200 bodies `{"items": "x"}`, `[]` and `{"events": null}` each give `ok: false` with "unexpected answer", never zero items. (lesson-3)
- `test_a_hung_remote_blocks_only_its_own_callers`: the fake for remote A blocks on an Event. A call for remote B completes, and so does the local `/api/items`. A is released at the end of the test. (lesson-6)
- `test_local_routes_are_unchanged_without_remote`: `/api/items` and `/api/events` without `remote=` give the same answers as before. `/api/items` carries `remotes: [{name, url}]` and makes no remote request. (lesson-7 guard on the merged behaviour)
- `tests/test_items_page.py::test_a_remotes_items_and_events_are_shown_marked_remote`: an in-process stdlib fake remote serves `/remote/v1/counts`, `items`, `items/ID`, `status` and `events`.
  - The Items page shows a section marked "remote R" with the remote's kind counts and an item.
  - Opening it shows `/item/ID?remote=R` read-only, with no message box.
  - `/record?remote=R` lists the remote's event.
  - After the fake is stopped and the period has passed, the Record page says "R does not answer" with the age, and not "Nothing recorded yet.".

  This test waits on content, never on a sleep. (lesson-3, lesson-10)

## Size budget

420 net lines outside `tests/` and `docs/`:

- `remote/items.py`: about 150
- `events.py`: about +45
- `server.py`: about +45
- `pages.js`: about +150
- CLI: about +2

An overrun needs a written reason.

## Notes from the plan review (answer each)

- test_events_are_merged_by_seq_and_a_remade_remote_restarts says the cursor restarts from the new last_seq; the definition says max(0, last_seq - 1000). Assert the defined rule, including the case where last_seq < 1000.
- A remake is only detected when last_seq < cursor. A remade remote that has already passed the old cursor is missed (old events stay mixed in, new ones up to the cursor are skipped). Use a record identity from /remote/v1/status if it has one; otherwise state this limit in SPEC.
- test_concurrent_item_listings_ask_once (and the events concurrency test) can pass with the lock removed if the first caller is released before the others reach the check. Hold the first fake call until a second call arrives or a bounded Event timeout expires.
- The browser test must say how the period (at least 10 s) passes: monkeypatch the in-process clock or the clamp, not a real wait.
- Test 401, 403 and 500 answers too, not only status 0, as failures with ok:false or 502, never empty.
- Callers waiting on a hung remote's lock have no bound (up to 8 x 3 s asks in a row, plus queued threads). Take the lock with a timeout and answer 503, or document the worst case.
- Point 1's 'exactly as on main' contradicts the added `remotes` field on /api/items. Reword it.
- State that failed asks count against ASKS and that the counter goes up before client.get is called.
- Say whether force=True in the CLI counts against or resets the events period for page polls.

## Where it stopped

**Built**, in 315 net lines outside `tests/` and `docs/` (budget 420): `remote/items.py` (154), `events.py` (+44),
`server.py` (+34), `pages.js` (+81), `details.js` (+2), CLI (0: one line changed). All of points 1 to 12 are built
as written. Point 13 is not fully met (see *Not run*).

**Not run, so not done by the house rules:**
- **The four browser files.** Playwright is not in this container's environment. Installing it (`uv run --with
  playwright==1.63.0`) needs the network, which this run may not reach, and the command was refused. The new
  `test_a_remotes_items_and_events_are_shown_marked_remote` and the page code (`pages.js`, `details.js`,
  `util.js`) have therefore **never been executed**. I checked them only by reading; `node --check` was refused
  too. This is the first thing the factory's browser run must look at.
- **The merge of origin/main.** There is no `origin/main` ref in this clone, and fetching one needs the network.
  Local `main` is the branch's base (05c6dc9). The merge (lesson-7) and the suites after it are left to the
  factory.
- **The whole unit suite.** Per the instructions it was not run here. Run one file at a time, all passing:
  `tests/test_remote_items.py` (21), `tests/test_remote.py` with `tests/test_remote_pair.py` (13),
  `tests/test_graph_cli_web.py` (28), `tests/test_web_access.py` (26), `tests/test_spec_items.py` (6).
  `ruff check ergostat tests scripts` is clean. `examples/remote-pair` is not touched, so `demo_check` was not run.

**A finding against point 2 (left as defined, the reversible choice).** Every item kind's `id:` must hold a `/`
(`item kind thing.id: … a pattern with a / in it`), so every real remote item id (`incident/3`) falls outside
the allowlist, which refuses `/`. As built, such items are listed in the remote's section and linked to the
remote's own page, but none can be opened here. Only ids without a `/` can be opened, as in the tests. SPEC §4c says
so. Widening the pattern, for example to `/`-separated segments each matching it (the remote API already joins
the path's segments with `/`), is a change to the definition and belongs in its own gap or a revised definition.

**The plan review's notes, answered:**
- *Remake rule.* The test asserts `max(0, last_seq - 1000)` in both cases. With `last_seq` 2 and the cursor 3,
  the next ask is `after=0`. With the cursor 5000 and `last_seq` 1500, the next ask is `after=500`, and 501..1500
  are kept.
- *A remake past the old cursor.* `/remote/v1/status` carries no identity of the record (name, version, now,
  running, last_seq only), so this case is not detected. SPEC §4c states the limit: old events stay until the day's
  window drops them, and new events up to the old cursor are not read.
- *Concurrency tests that pass without the lock.* In both tests the first fake call is held until a second call
  arrives, or for 1 s at most (a bounded `Event.wait`). Both fail with the lock removed (below).
- *The browser test's period.* It runs the page and a stdlib fake remote in-process and monkeypatches the clamp,
  `items.MOST = 1.0`, so the period is one second. It waits on page content only (`wait_for_function`), never a sleep.
- *401, 403, 500.* `test_a_remote_that_does_not_answer_is_asked_once_a_period` is parametrized over status 0,
  401, 403 and 500. Each is a 502 with the reason, one request a period, then the kept answer with `ok: false`.
- *Waiting on a hung remote's lock.* Locks are taken with a timeout. An items lock is held for at most two asks
  of 3 s, and a caller waits `WAIT` = 7 s, then gets 503. The events lock's holder makes at most 6 asks, and a
  caller waits 19 s, then gets 502 *busy*. A remote that failed is not asked again that period, so after one
  timeout its later callers are answered from the cache at once. SPEC §4c states both bounds.
- *Point 1's "exactly as on main".* Without `remote=`, the three routes answer as on main, except that
  `/api/items` gains `remotes: [{name, url}]`, and only when the model declares remotes. A model without remotes
  gets byte-for-byte main's answer. SPEC says this. (The definition itself may only be appended to, so it is
  answered here.)
- *Failed asks and the counter.* The counter goes up before `client.get` is called, and a failed ask counts
  against `ASKS`. This is stated in `items.py`'s docstring and in SPEC §4c.
- *`force=True`.* The CLI's read takes the lock and sets the period's `asked`, so it counts as the period's read
  for page polls. It does not reset the period, and polls after it wait for the period to pass.

**Each guard broken, and the test that then failed (lesson-9).** Each guard was restored afterwards, and the
Python files were checked identical to the commit.
- ID allowlist skipped (`if False and not openable`): `test_a_traversal_id_is_refused_before_any_request` fails
  (`../events` answered 200).
- Budget check skipped: `test_paging_past_the_cache_is_bounded_per_period` fails (51 requests, not 8).
- `items.held` made a no-op (no lock): `test_concurrent_item_listings_ask_once` fails (the other threads asked,
  spent the budget and got 503).
- `events.follow` given a fresh lock per call (no per-remote lock):
  `test_concurrent_record_polls_read_events_once_a_period` fails (seven of eight threads returned before the
  read). The test's second half (a poll started inside the first one's events call) was not separately shown
  failing, because the first half fails before it.
- The once-per-period failure check skipped: `test_a_remote_that_does_not_answer_is_asked_once_a_period` fails
  for all four statuses (503 once the budget is spent, not 502 after one ask).
- The shape checks skipped (items and events): `test_an_unexpected_answer_is_a_failure` fails for all three bodies.
- The name allowlist skipped: `test_an_unconfigured_remote_is_refused_never_answered_locally` fails (500).
- Dedupe by `seq` skipped: `test_events_are_merged_by_seq_and_a_remade_remote_restarts` fails (`[1, 2, 3, 1, 2, 3]`).
  The remake reset skipped: the same test fails (old events mixed in).
- One lock for all remotes: `test_a_hung_remote_blocks_only_its_own_callers` fails (503 for remote s).

**Notes.** SPEC has no Record page section of its own, so the Record page's `remote=` scope is described in §4c
(*Its items and events in the pages*). The Items section's filter table gains a `remote=NAME` row. The API tests
run the page in-process over HTTP. Only `items.time` and `events.time` are replaced by a fake clock, never the
process's `time.time`.

## Where it stopped (round 2)

The round-1 review's four findings, each answered (lesson-12):

- **The id allowlist refused every real remote item (blocking).** Fixed as the review asked. This departs from
  point 2's text ("an ID with `/` … is refused") and from the acceptance test's `a/b` in the refused list. The
  definition is not edited, so the departure is recorded here. `items.openable` now accepts at most 200
  characters of `/`-separated segments. Each segment fully matches `[A-Za-z0-9_][A-Za-z0-9_.:@#+=-]{0,199}`, so
  none is empty and none starts with `.`, and there is no `..` anywhere. It is still an allowlist, and still
  checked before any request. The id is still sent as `quote(ID, safe="")` (`items/incident%2F3`), which
  `remote_api.answer` unquotes after splitting. The page's `REMOTE_ID` (`pages.js`) matches it.
  `test_a_traversal_id_is_refused_before_any_request` now refuses `../events`, `incident/../events`,
  `incident/..`, `a//b`, `/a`, `a/`, `a/.b`, `a/%2e%2e`, `a/b c`, `a\b`, a 201-character id with a `/`, `a/-x`
  and the empty id. It opens `incident/3`, `a/b` and `ergostat.model-change/x:1`, and each reaches `client.get` as
  one encoded segment. The browser test uses `incident/3` for kind `incident`, and its fake remote parses paths
  as `remote_api` does. Broken and shown failing: with the `..` check dropped it fails on `a..b`; with no split
  on `/` it fails on `incident/3`.
- **The browser test's period was not shortened (blocking).** `items.MOST = 1.0` did nothing, since `LEAST` is
  10 s, and the round-1 answer ("the period is one second") was false. The test now replaces `items.time` and
  `events.time` with a fake clock and moves it on 60 s after the fake remote is stopped. There is no real wait,
  and the test waits only on page content.
- **The CLI's `force=True` (blocking, a doc claim).** The round-1 answer was wrong. The CLI reads in its own
  process, and `events._kept` is that process's memory, so the CLI's read never reaches the page server's cache.
  SPEC §4c now says the CLI reads every time it is run, whatever the period, and leaves the pages' period
  unaffected. No code changed.
- **origin/main not merged (blocking).** This clone still has no `origin/main` ref, and the network is out of
  reach. The factory merged local `main` (8eb0fc0) into the branch (81055a5). The review's origin/main dc0d5ac is
  not in this clone, so that merge, and the suites after it, remain for the factory.

**Still not run: the browser files.** Playwright is still not importable here (`could not import
'playwright.sync_api'`). So `test_a_remotes_items_and_events_are_shown_marked_remote` and the page code have still
never been executed, and by the house rules the gap is not done until they are. The whole unit suite was not run
either.

**Run here:** `tests/test_remote_items.py` (21 passed) and `ruff check ergostat tests scripts` (clean).

**Size:** about 319 net lines under `ergostat/`, within 420.

## Where it stopped (round 3)

**The finding: the branch was 636 commits behind main and conflicted in docs/GAPS.md.** Fixed. The factory's merge
of main (e1e778c) was finished in c6a4433. The only conflict was the *Remote systems* entry. Main's addition there
(the done `remote-box-measures` slice and its sentence) is kept. This branch's done sentence is placed after it.
The *Left* list keeps main's other items and still leaves out "the remote's events in the Items and Record pages".
No code changed in this round.

**Run after the merge, one file at a time:** `tests/test_remote_items.py` (21 passed), `tests/test_remote.py` with
`tests/test_remote_pair.py` (13 passed), `tests/test_graph_cli_web.py` (31 passed), `tests/test_web_access.py`
(26 passed), `tests/test_spec_items.py` (6 passed). `ruff check ergostat tests scripts` is clean.

**Still not run: the browser files.** `tests/test_items_page.py` is skipped here: "could not import
'playwright.sync_api': No module named 'playwright'". So `test_a_remotes_items_and_events_are_shown_marked_remote`
and the page code have never been executed, and by the house rules the gap is not done until they pass. Also not
run here: the whole unit suite, which the factory runs. The merged ref is local `main` (e1e778c), because this
clone has no `origin/main`.

## Where it stopped (round 4)

**The finding: a remote item's `file:` field was drawn as a local file (blocking).** Fixed. `fieldView`
(`pages.js`) takes a last argument `there`, the remote's name, and passes it down through lists and records.
When it is set, a `file:PATH` value is shown as its text, titled "a file at remote NAME, not read here". It is
never turned into `/file/PATH`, never fetched, and never drawn as an image or a file view. `pageRemoteItem` passes
the remote's name, so this holds for every field of a remote item, nested ones too. Local items are drawn as
before. SPEC §4c says so. The item page's answer carries no URL for the remote, so the value is not linked there;
the Items page's link to `URL/item/ID` stays. This was the only finding listed, and it is answered (lesson-12).

**The test:** `tests/test_items_page.py::test_a_remote_items_file_field_never_reads_a_local_file`. The fake
remote's item now has `notes: file:notes.md` and `shots: [{pic: file:shot.png}]`, and the local project has its
own `notes.md`. The test opens `/item/incident%2F3?remote=r` and waits until both `file:` texts are shown. It
checks that the local file's text is not on the page and that the page has no `img` or `.file-view`. It then loads
`/record?remote=r` and checks that no request the browser made went to `/file/`. It waits only on page content.

**Not run, and not shown failing (lesson-9).** Playwright is still not importable here (`could not import
'playwright.sync_api'`). The new test, the rest of the browser tests and the page code have **never been
executed**. The test was not shown failing with the guard removed. It should fail if the `there` branch in
`fieldView` is removed, because the local `notes.md` would then be fetched and drawn. That is reasoned, not seen.
`node --check ergostat/web/static/pages.js` was refused, so nothing has checked the JS syntax either. The factory's
browser run must run both remote tests in `tests/test_items_page.py`.

**Run here:** `ruff check ergostat tests scripts` (clean). `tests/test_items_page.py -k remote` was skipped because
Playwright is missing. No Python under `ergostat/` changed this round.

**Size:** +3 net lines in `pages.js`, about 322 under `ergostat/` (budget 420).

## Where it stopped (round 5)

**The finding: the merge of main conflicted in docs/AGENT-GUIDE.md.** Fixed. The factory's merge of main
(c9d3bab) was finished in cde4cb9. The one conflict was in §3, the remote systems steps. This branch's step 5 is
kept: the remote's items can be seen in the Items page and its events in the Record page, but they are never
folded or counted locally (point 12). Main's new step 6 (`ergostat remote proposals`) is kept after it. No code
changed in this round.

**Run after the merge, one file at a time:** `tests/test_remote_items.py` (21 passed), `tests/test_remote.py` with
`tests/test_remote_pair.py` (13 passed), `tests/test_graph_cli_web.py` (31 passed), `tests/test_web_access.py`
(26 passed), `tests/test_spec_items.py` (6 passed). `ruff check ergostat tests scripts` is clean.

**Still not run: the browser files.** `tests/test_items_page.py -k remote` is skipped here: "could not import
'playwright.sync_api': No module named 'playwright'". The two remote browser tests and the page code have still
never been executed, and they have never been shown failing with their guards broken (lesson-9). By the house
rules the gap is not done until they pass. The whole unit suite was not run here either; the factory runs it.
