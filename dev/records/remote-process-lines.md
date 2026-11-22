# remote-process-lines: a relation may name a remote's item kind, and the process map draws a line from our item's step to the step the remote item was last at

depends-on: []

## The gap

The process map draws a remote's own map beside ours (`ergostat/remote/process.py`, SPEC §4c). It draws no line between our items and the remote's: "no event here names an item there" (docstring of `remote/process.py`; GAPS.md, *Remote systems*, *Left*: "lines in the process map between our items and theirs (needs an id both logs carry)"). The id both logs carry is a **relation** (SPEC §5a): a local kind declares `relations: {blocked_by: incidents-incident}`, its items hold the remote item's id in that field (an event's data, in our log), and the remote's log has that item's events. Today `spec/relations.py::check_relations` rejects `incidents-incident` as `unknown-ref`. `/remote/v1/process` also cannot say which step a named item was last at.

## Definition of done

1. **Compile: a relation may name a remote's kind.** In `check_relations`, a kind `T` in a relation's `kind:` that is not a local kind, and that starts with `R-` for a remote `R` in `spec.remotes`, is a **remote relation**. When more than one remote name fits, the longest one is used. `Relation` gains `remote: str = ""` (the remote's name) and `there: str = ""` (the kind's name at the remote).
   - **Local first.** If `T` is a local kind (`T in spec.items`), the relation is local even when `T` also starts with a remote's name. Nothing is asked of the remote for it.
   - **The remote serves the kind** (`there in spec.remotes[R]["kinds"]`, from its model as last read, cached or fresh): it compiles with no finding.
   - **The remote was read but no longer serves the kind**: the model still compiles. A finding `remote-reference-unresolved` says "item kind incidents-incident is not in remote incidents's model (version V): it has no item kind incident". The relation stays remote.
   - **The remote has never been read** (unreachable, no cache): the model still compiles. A finding `remote-reference-unresolved` says "(it has not been read)". The relation stays remote. An unreachable remote never makes the local model fail to compile.
   - **The remote is unreachable but cached**: the cached kinds are used, as for every other remote part (the `remote-unreachable` finding is already made by `compose.py`).
   - A remote relation whose `kind:` list also names any other kind, local or remote, is an error `bad-relation` ("a relation naming a remote's kind names only that kind").
   - A remote relation never gates. Its `precedence` is false whatever its name (`blocked_by`, `after` and `depends_on` included). An explicit `precedence: true` on it is an error `remote-relation-precedence` ("ergostat does not see when a remote's item is finished; it cannot gate on it"). `group: true` on it is the same kind of error (`bad-relation`).
   - So `precedence.py` needs no change: an item whose `blocked_by` holds only remote ids has the same status, readiness and `order_ready` place as one with no `blocked_by` at all.
2. **The remote answers where its items are.** `/remote/v1/process` accepts a repeated `at=ID` parameter. Ids are read from the list `parse_qs` gives, never split on `,`.
   - More than `AT_MOST = 200` distinct ids is a 400, like `readings`.
   - The reply gains `"at": {id: {"kind": K, "activity": A}}` for each asked id that has steps in the window. `A` is the step it was last at (`w.steps[id][-1][1]`, the same rule the local `related` lines use). An id without steps in the window is left out of `at`.
   - `ergostat/process.py::process` gains an optional `at` argument that returns this map from its `Window`.
3. **The local map collects its remote links.** `process.process` collects every link from an item in the window, through a remote relation, to an id. For each one it records `{item, kind, activity (last step), relation, remote, there, target}` into `out["remote_links"]`, which is bounded by the items in the window it already reads. Local `related` lines are unchanged.
4. **Merge draws them** (`remote/process.py`).
   - For each remote in view, the distinct target ids of its links are filtered by an allowlist: a str of 1 to 128 characters with no whitespace or control characters. Any other id is unlinked with reason `bad-id`.
   - The ids are sorted by the id string, ascending (never by time).
   - The first ones are taken while the count stays ≤ `AT_MOST` and the url-encoded `at` query stays ≤ 32,000 bytes. The rest are unlinked with reason `capped`.
   - The ids taken are sent as `at=` in the same `process` GET that fetches the remote's map. The cache key includes a hash of the ids sent, and `_kept` stays capped at 32 entries.
   - A link is drawn as an edge `{"id": "x:R:REL:KIND:A>R-K:B", "kind": "related", "remote": R, "relation", "source": p:KIND:A, "target": p:R-K:B, "count", "items", "targets", "median": None}`, aggregated as local related lines are. It is drawn only when all of these hold: the reply's `at[target]` is a dict whose `kind` is a str equal to the relation's `there`, and whose `activity` is a str; the renamed node `p:R-there:activity` is among the remote's drawn nodes; and the local node `p:KIND:A` is among the local drawn nodes.
   - Otherwise the link is not dropped. It is counted in `out["remotes"][R]["unlinked"]`, a dict from reason to count. The reasons are:
     - `unreachable`: no body;
     - `bad-id`;
     - `capped`;
     - `not-answered`: the reply has no usable `at`, or leaves the id out, or its entry is malformed;
     - `other-kind`;
     - `not-drawn`: the remote node is not in its drawn map;
     - `not-drawn-here`: the local node was capped.
   - `out["remotes"][R]["linked"]` is the number drawn, so `linked + sum(unlinked) == number of remote links` always holds.
   - An unreachable remote gives `ok: false`, no remote nodes and no remote lines, and every link to it is counted `unreachable`.
   - A remote that predates `at` (its reply has no `at` key) gives `not-answered` for every link.
   - No timestamp from the remote is compared with a local one: where a line attaches depends only on the remote's last step and the local last step.
5. **Drawn.**
   - `process.js` draws a line whose edge has `remote` dashed, with class `pm-remote`.
   - Its detail panel (the existing `related` panel) says the named items are remote R's.
   - The remote's row in the side list (line ~447) says "N links to it not drawn (reasons)" when `unlinked` is non-empty.
   - There is no new page or panel.
6. **Docs.**
   - SPEC §4c: lines to a remote, `at=`, unlinked reasons, never gating.
   - SPEC §5a: a relation may name a remote's kind, local first, not precedence.
   - SPEC §5b: remote related lines are not subject to the `paths` slider.
   - `docs/proposals/remote-systems.md`: the "Left for later" line.
   - The GAPS.md *Remote systems* entry: move the item from *Left* to *Done*.
   - The `remote/process.py` docstring: drop "Lines … are not drawn".
   - The agent guide: one sentence on naming a remote's kind in `relations:`.
7. All suites pass, as the house rules say: the unit suite and the four browser files with rc 0 and no page test skipped for want of a port; ruff clean; `demo_check` on `examples/remote-pair/` if it is touched; origin/main merged in and the suites run again.

## Files to touch

- `ergostat/spec/ir.py` (`Relation.remote`, `Relation.there`)
- `ergostat/spec/relations.py` (`compile_relations` errors; `check_relations` remote resolution and findings)
- `ergostat/process.py` (`at=` reply; `remote_links`)
- `ergostat/web/remote_api.py` (`at` parameter, `AT_MOST`, the 400)
- `ergostat/remote/process.py` (id selection, request, drawing, `unlinked`/`linked`)
- `ergostat/web/static/process.js`
- `docs/SPEC.md`, `docs/proposals/remote-systems.md`, `docs/GAPS.md`, `docs/AGENT-GUIDE.md`
- `tests/test_remote_lines.py` (new), `tests/test_diagram_rendering.py` (one test)

## Risks

- **lesson-3 (failing open).** The inputs that can be missing are:
  - the remote is unreachable;
  - the remote has never been read at compile time;
  - the kind is no longer served;
  - the reply has no `at`, or `at` is not a dict;
  - an id is missing from the reply;
  - an entry is malformed;
  - the remote node is not drawn;
  - the local node is capped.

  Each one counts as unlinked with a named reason, and links are conserved. None is silently dropped, and none is drawn to a guessed node. At compile time, an unreadable remote is a finding, not an error, and not an empty pass either: the finding is asserted.
- **lesson-4 (a limit with no ceiling).** The number of ids sent is a hard 200 on the client, counted after making them distinct. The server enforces 200 again (400 past it). The encoded query is capped at 32,000 bytes, and ids are capped at 128 characters each. The `_kept` cache keeps its cap of 32.
- **lesson-2 (wall time instead of sequence).** Which 200 ids are sent is decided by sorting on the id string, never by time. Where a line attaches never compares remote times with local times.
- **lesson-9 (a test that can't fail).**
  - The never-gates test uses `blocked_by`, which `PRECEDENCE` would gate on, and shows that the same relation pointed at a local unfinished kind does block.
  - The line tests' fixture has no local `incidents-incident` kind (asserted). A negative case adds a local kind of that name and shows the link is local.
  - Each test is broken on purpose and seen to fail; the report says so.
- **lesson-8 (a claim wider than the code).**
  - "Never gates" is backed by the precedence test and by the `precedence: true` error test.
  - "Links are never dropped" is backed by the conservation assertion in every unlinked test.
- **lesson-1 (check then write without the lock).** `fetched` reads the cache under `_lock`, then fetches and writes outside it. Two concurrent fetches with the same key both GET, and the last write wins with an answer of equal standing. Nothing is decided from a stale read (the cache is a read-through of an idempotent GET), so no lock is held across the GET, on purpose. The docstring says so.
- **lesson-5 (stale state under a reused id).** A remote item id made again at the remote is answered fresh on each fetch. The cache key holds the set of ids sent, so a changed set never reuses an answer for other ids.
- **lesson-7 (merged branches conflict).** `remote-items-record` and `remote-box-measures` are leased and touch `remote/` and `remote_api.py`. Merge origin/main and run the suites again before saying built.
- **lesson-13 (stay inside the gap).** A dangling remote id in the Graph view or item index is not this gap's to fix. A failure there is reported, not fixed in this branch.

## Acceptance tests

All in `tests/test_remote_lines.py` unless named otherwise.

The fixture:
- The remote is `incidents`: the `REMOTE` model of `tests/test_remote.py`, plus `items: incident: {id: incident/*, states: [open, fixing, closed]}`.
- The local project names it under `remotes:`. Its kind `ticket` (`id: ticket/*`, states `[todo, doing, done]`) has `relations: {blocked_by: incidents-incident}`.
- The fixture asserts `"incidents-incident" not in spec.items`.
- The remote's map comes in one of two ways:
  - Through a fake `client.get` that calls `ergostat.web.remote_api.answer` on a real remote project. These tests record each call's params.
  - Through a scripted reply, for the malformed cases.

Each test and what it shows:

- `test_a_relation_may_name_a_remotes_kind`: it compiles with no error and no finding. `Relation.remote == "incidents"`, `there == "incident"`, `precedence is False`.
- `test_a_remote_relation_never_gates_but_the_same_relation_does_on_a_local_kind`:
  - A `ticket` whose `blocked_by` names an `incident/...` id that is open at the remote has `precedence.build` status equal to a ticket with no `blocked_by` (not `blocked`), and it is in `order_ready`.
  - The same model with `blocked_by: epic`, a local kind whose item is unfinished, gives `blocked` and leaves it out of `order_ready`.
  - Fails if remote relations keep the default `PRECEDENCE`.
- `test_precedence_true_on_a_remote_relation_is_an_error`: an error with code `remote-relation-precedence`. Also: a mixed `[epic, incidents-incident]` is an error `bad-relation`.
- `test_a_kind_the_remote_no_longer_serves_is_a_finding_and_draws_no_line`:
  - The cached model has no `incident` kind. The model compiles, with a finding `remote-reference-unresolved` naming `incident`.
  - In the map, no edge has `remote`, and the links are counted `unlinked` (`not-drawn`, or `not-answered`), with conservation.
- `test_compile_with_the_remote_never_read_is_a_finding_not_an_error`: the url is `127.0.0.1:1` and there is no cache. It compiles, with a finding `remote-reference-unresolved` that says "has not been read".
- `test_a_line_is_drawn_from_our_step_to_the_step_their_item_was_last_at`:
  - Ticket `ticket/1` is at `doing` and names `incident/7`, which is at `fixing` at the remote.
  - There is exactly one edge with `kind == "related"` and `remote == "incidents"`, `source == "p:ticket:doing"`, `target == "p:incidents-incident:fixing"`, `count == 1`.
  - `remotes.incidents.linked == 1`, and `unlinked == {}`.
- `test_a_local_kind_of_the_same_name_is_not_taken_for_a_remote_line`:
  - A local kind `incidents-incident` is added. The relation compiles with `remote == ""`.
  - No `process` call to the remote carries `at`, and the edge drawn has no `remote` key.
- `test_an_activity_not_in_the_remotes_drawn_map_is_unlinked`: the remote's map is capped (MOST_NODES monkeypatched to drop `fixing`). There is no remote edge, `unlinked == {"not-drawn": 1}`, and links are conserved.
- `test_a_reply_that_leaves_out_an_id_or_is_malformed_is_unlinked_not_dropped`: the scripted replies are:
  - `at` missing;
  - `at` a list;
  - the id left out;
  - an entry with `activity: 5`;
  - an entry with `kind: "other"`.

  Each gives no remote edge, the right reason (`not-answered`, or `other-kind` for the last), and `linked + sum(unlinked) == links`.
- `test_an_unreachable_remote_is_ok_false_with_no_lines`: the fake get returns status 0. `remotes.incidents.ok is False`, there are no nodes or edges with `remote`, and `unlinked == {"unreachable": n}`.
- `test_the_ids_sent_are_distinct_capped_at_200_and_chosen_by_id`:
  - 250 tickets name 230 distinct incident ids, made in shuffled order and stamped in reverse id order, plus one id `"bad id"` with a space and one 129 characters long.
  - The recorded `at` params are exactly `sorted(valid_distinct)[:200]`, each once.
  - `unlinked` counts the rest as `capped` (by link) and the two as `bad-id`.
  - An id containing `,` (`incident/a,b`) is sent whole as one `at` value and answered by the real `remote_api` as one id.
- `test_the_remote_refuses_more_than_200_ids`: `remote_api.answer` with 201 `at` gives 400. With 200 it gives 200, and `at` holds only ids with steps.
- `test_remote_times_before_or_after_ours_draw_the_same_lines`: the remote's events are stamped 3,000 s before the local events in one run and 100 s after them in another (both inside the window). The remote-edge lists are identical, compared on id, source, target and count.
- `tests/test_diagram_rendering.py::test_a_line_to_a_remote_is_drawn_dashed_between_the_frames`: a page with the line fixture's `/api/graph?view=process` answer shows one `pm-remote` edge path between the `ticket` frame and the `remote incidents: incidents-incident` frame. The side list shows the "not drawn" text when `unlinked` is non-empty.

For every test: break the code it guards, record the failure, and say so in the report. The breaks:
- drop the remote check in `check_relations`;
- keep the precedence default;
- skip the `other-kind` check;
- split `at` on `,`;
- sort ids by time;
- drop the unlinked counting;
- skip the local-first rule.

## Size budget

260 net lines of code outside `tests/` and `docs/`. The estimate by file:

| File | Net lines |
|---|---|
| `relations.py` | 45 |
| `ir.py` | 2 |
| `process.py` | 30 |
| `remote_api.py` | 15 |
| `remote/process.py` | 110 |
| `process.js` | 20 |
| slack | 38 |

An overrun needs a written reason in "Where it stopped".

## Notes from the plan review (answer each)

- Cached map when ids change: the process cache key now includes a hash of the ids sent. If the remote is unreachable and the id set has changed since the last fetch, no cached map matches, so the remote's map vanishes where it used to show cached. The 32-entry `_kept` cap will also push out older entries as id sets change. Keep the cached-map fallback per remote, independent of the ids (an `at` answer taken from the cache must still be for exactly the ids sent, or every link counts `not-answered`). Add a test: unreachable, cached, id set changed, the remote's map is still drawn and marked as cached.
- Pin one reason in the no-longer-served test: it accepts `not-drawn` or `not-answered`, which is the `A or B` pattern from lesson-9. Since the remote has no such kind, `at` leaves the id out, so assert exactly `{"not-answered": n}`.
- Byte cap: 200 ids of up to 128 characters, url-encoded, can reach about 77 KB, so the 32,000-byte cap can apply before the count of 200 does. Add a case with long ids where the byte cap applies first (taken ids and `capped` counts asserted). Also show that the real remote server stack accepts a query close to 32,000 bytes: many HTTP servers limit the request line to 8 KB, and a refused query would make the remote look unreachable.
- Say what an unreachable remote does with `bad-id` links: are they counted `bad-id` or `unreachable`? The unreachable test expects only `{unreachable: n}`; pick one rule (ids checked first, so `bad-id` wins, seems right) and state it in the definition of done and in the test.
- Only one reply at a time: the `other-kind` check compares against the relation's `there`. If several local relations name different kinds at the same remote and share a target id, say how they are aggregated, and make sure `at` is asked once per id and the reply checked per link.
- Give `test_a_local_kind_of_the_same_name_is_not_taken_for_a_remote_line` a fixture where the remote does serve `incident`, so the test fails if the local-first rule is skipped rather than passing because nothing resolved.

## Where it stopped

Built, round 1. Every item of the definition of done is in place. The net code outside tests, docs and dev is 159
lines (budget 260). Nobody was there to ask, so where the text left a choice, the more reversible option was
taken:

- **Where the errors are made.** `compile_relations` makes the `bad-relation` and `remote-relation-precedence`
  errors and sets `precedence = group = False`, since only it sees whether `precedence:` or `group:` was written.
  It resolves the remote from the document's remotes and its local item kinds, so the rule is still local first and
  the longest name wins. `check_relations` makes the `remote-reference-unresolved` finding and skips `unknown-ref`
  for a remote relation. `parent: incidents-incident` without `group:` compiles as a plain, non-group relation;
  only an explicit `group: true` is an error.
- **The plan review's notes, each answered:**
  - *Cached map when ids change.* `fetched` keeps two entries: one by the ids sent (its hash in the key), and one by
    the remote alone, holding the last good map in the same window. When the remote does not answer, the last good
    map is drawn, with `cached: true` and `ok: false`. Its `at` is used only when it was for exactly the ids sent
    now; otherwise `at` is dropped and every link counts `not-answered`. `_kept` is cleared past 30 entries and
    gets two writes a call, so it never holds more than 32. Tested by
    `test_an_unreachable_remote_with_a_changed_id_set_still_draws_its_map_as_cached`.
  - *One reason pinned.* The no-longer-served test asserts exactly `{"not-answered": 1}`.
  - *Byte cap.* Tested by `test_the_byte_cap_applies_before_the_count_and_the_remote_server_takes_such_a_query`.
    It uses 150 ids of 128 characters, each `:` sent as `%3A`. Fewer than 150 are taken, the query stays within
    32,000 bytes (and over 31,000), and one more id would pass the cap. The rest count as `capped`. The real page
    server takes that query over HTTP and answers it (200, with `at`). Python's `http.server` refuses a request
    line only past 65,536 bytes.
  - *Bad ids when the remote is unreachable.* `bad-id` and `capped` are decided before the request, so they win
    over `unreachable`. SPEC §4c says so, and `test_an_unreachable_remote_is_ok_false_with_no_lines` asserts
    `{"unreachable": 2, "bad-id": 1}`.
  - *Several relations, one id.* Each id is asked once (the ids are made distinct before sending). The answer is
    checked against each link's own `there`. Lines are aggregated by relation, our kind and step, and their step.
    Tested by `test_two_relations_sharing_an_id_ask_it_once_and_are_checked_each`: `blocked_by` is drawn, and
    `relates_to: incidents-page` counts `other-kind`.
  - *Local-first fixture.* The remote does serve `incident`, and the test asserts it.
- **Other choices:**
  - The remote's reply drops its own `remote_links`, since a remote of a remote is not composed.
  - Every edge with `remote` (the remote's own lines too) gets the class `pm-remote`. Only the related line to a
    remote is restyled, to a 9/5 dash like the remote's frame.
  - The ids-by-id test also stamps the items in forward id order. With reverse order alone, a "newest first" order
    gives the same ids and passes.
- **Breaks, each seen to fail:**
  - The remote check in `check_relations` dropped: 17 tests failed.
  - The precedence default kept: the relation test and the never-gates test failed.
  - The `other-kind` check skipped: the malformed-reply case and the two-relations test failed.
  - `at` split on `,`: the ids test failed.
  - Ids sorted by time, oldest first and newest first: the ids test failed both times.
  - The unlinked counting dropped: 12 tests failed.
  - The local-first rule skipped: the local-kind test failed.
  - The page: without the `pm-remote` class, or without the "not drawn" text, the page test failed.
- **Not done here:**
  - This clone has no `origin` remote, and `git fetch` was refused (network). `main` is already an ancestor of the
    branch, so there was nothing to merge.
  - The full unit suite and the four browser files were not run here; the house process leaves them to the
    factory and the merge queue.
  - `examples/remote-pair/` was not touched, so `demo_check` was not run.

Round 2: the factory merged main (48b1481a) and `ergostat/remote/process.py` conflicted in `fetched`. Main had
added mutual TLS: the `process` GET passes `tls=r.get("tls")`. The resolution keeps the branch's `fetched` (the `at`
ids, the key by ids, the last good map per remote, `_kept` cleared past 30) and adds main's `tls=` argument to its
GET. The fake `client.get` in `tests/test_remote_lines.py` now takes `tls=None`. After the merge, ruff is clean, and
these pass: `tests/test_remote_lines.py`, `tests/test_remote.py`, `tests/test_remote_mtls.py`, and
`tests/test_diagram_rendering.py::test_a_line_to_a_remote_is_drawn_dashed_between_the_frames` (Playwright, under
the watchdog, rc 0). The full unit suite and the four browser files were not run here; they are left to the
factory and the merge queue.
