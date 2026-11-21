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
