# searching-items-and-querying: land the item text search that was built on factory/item-text-search but parked, never merged, onto main
depends-on: []

## Definition of done
The graph and GAPS call search done, but none of its four commits on `origin/factory/item-text-search` are on main. The factory parked the branch on 2026-11-20 after its runs failed ("nack exited 1", attempts 4–6). That branch's own report says it never merged origin/main and never ran the full suites. This gap takes that work onto current main, makes it pass there, and nothing more. near, path and about stay in gap/item-graph-queries.

True when done:
1. Main has the search exactly as the parked definition (`docs/roadmap/overnight/item-text-search.md` on that branch) and its answered review notes describe it:
   - The words searched are the casefolded text of an item's fields, nested fields too, held on the item's own index row and rewritten whenever the item is folded again.
   - The index `VERSION` is raised above main's current value, so an older index file is rebuilt.
   - A row whose text is NULL makes the search rebuild the index first. It is never read as "no match".
   - Each word is matched as a plain substring (`instr`, no LIKE), and every word must match.
   - Only the first `TEXT_MOST` = 65,536 characters of an item's text are searched.
   - At most 8 words. An empty or blank search is refused: exit 2 in the CLI, HTTP 400 in the API.
   - The CLI's `-n` is clamped to 1..`items.LISTED`.
   - `--search` together with `--at` is refused with a message.
   - `--search` is in `goodmodel.READ_FLAGS`.
2. `ergostat item --search WORDS [--kind] [--state] [-n] [--json]` and `GET /api/items?search=WORDS` return the same ids, in the listing's usual shape.
3. Where main changed `itemindex.py`, `items.py`, `cli/record.py` or `web/server.py` since the branch was cut, main's behaviour is kept. Nothing main added is lost in the merge.
4. The docs say "contains every word", the 65,536-character limit, and no ranking or fuzzy matching. That means SPEC §5a *Search*, the AGENT-GUIDE's item commands and the `item --search` help. GAPS.md gets the entry for gap/item-search: search **done** with this branch's merge commit, near/path/about **open** under gap/item-graph-queries.
5. The parked definition file is brought over unchanged. This branch's own file appends "Where it stopped", saying why the earlier runs failed, if found, or that the cause was not found.
6. The unit suite and the four browser files pass with rc 0 on the branch after origin/main is merged in, run under `scripts/suite_watch.py`.

## Relation to other work
- gap/item-graph-queries: edits the same index, CLI, API and goodmodel files. It should land after this branch and build on the text column. This plan touches none of its new files (`ergostat/spec/itemgraph.py`).
- gap/item-text-search: the parked branch this one carries onto main. Its "merged" status in the graph is wrong.
- gap/a-set-chosen-in-a-snapshot, gap/a-kind-chosen-in-a-snapshot: they change the Items page. The page's own search box stays as it is, so their files are not touched.

## Files to touch
- `ergostat/spec/itemindex.py`
- `ergostat/spec/items.py`
- `ergostat/cli/__init__.py`
- `ergostat/cli/record.py`
- `ergostat/goodmodel.py`
- `ergostat/web/server.py`
- `docs/SPEC.md`
- `docs/AGENT-GUIDE.md`
- `docs/GAPS.md`
- `docs/roadmap/overnight/item-text-search.md` (new)
- `tests/test_item_search.py` (new)

## Risks
- lesson-7: the work passed alone on an old base. Main's later changes to the index, its VERSION, or the CLI's read-only flags can break it once merged. This is the most likely reason it was parked.
- lesson-5: an item folded again (a field replaced, a same-id `set`, a restored snapshot) keeps its old words after the merge resolution.
- lesson-3: an old index file, or a row with NULL text, read as no match instead of being rebuilt.

## Acceptance tests
- `tests/test_item_search.py::test_search_finds_by_every_word`: `alpha beta` finds only the item that holds both words, in a nested field and in any case. The decoys `ticket/2` (alpha only) and `ticket/3` (beta only) are not found. Non-ASCII casefolding works, and `50%` and `_` match only themselves.
- `tests/test_item_search.py::test_changed_field_stops_matching` (lesson-5): after a replaced title, a same-id `set` and a restored snapshot, old words find nothing, including after a cold start.
- `tests/test_item_search.py::test_forgotten_item_leaves_search`: an item whose events are all pruned is no longer found.
- `tests/test_item_search.py::test_old_index_rebuilt_and_searchable` (lesson-3, lesson-7): an index stamped with main's previous VERSION is rebuilt, and its items are found.
- `tests/test_item_search.py::test_a_row_without_its_text_is_rebuilt_not_read_as_no_match` (lesson-3): text set to NULL by hand, and the item is still found.
- `tests/test_item_search.py::test_words_past_the_cap_are_not_searched`: a word before 65,536 characters is found, a word after it is not.
- `tests/test_item_search.py::test_search_cli_and_api_agree` (lesson-7): CLI `--json` and `/api/items?search=` give the same ids. The CLI answers under the last-good fallback. A blank search gets exit 2 and HTTP 400, and 9 words are refused.
- `tests/test_item_search.py::test_search_with_at_refused`: `--search` with `--at` exits non-zero with a message.

## Size budget
90 net lines

## Where it stopped

**Correction (round 2): round 1's "the parked branch was not available" was wrong (lesson-8).** No ref names it
(`git branch -a` shows only `main` and this branch, and `git for-each-ref --contains 0261d96d` lists none), but its
four commits are in this clone's object store by hash: a7194e5b (definition), 590874f3 (code), bf82f148 (where it
stopped, and the plan review's notes answered), 0261d96d (where it stopped: parked), on base 3adf48a6. Round 1 did not
look them up by hash. Round 2 did:
- **Point 5:** `docs/roadmap/overnight/item-text-search.md` is brought over unchanged from 0261d96d (`git diff --cached
  0261d96d -- docs/roadmap/overnight/item-text-search.md` is empty).
- **Point 1, checked against the parked definition, its answered notes and 590874f3's code.** Three of round 1's own
  choices differed from what the parked branch settled. Each now follows the parked branch:
  - only the **string** values of the fields are searched (parked DoD 1, "the string values of its fields"). Round 1
    also searched numbers and booleans as JSON. Keys are not searched, the same as in the parked code;
  - `ergostat item NAME --search ...` is **refused** (exit 2, "leave out NAME and --at"), as 590874f3 did. Round 1 showed
    the item and silently ignored the search;
  - `GET /api/items?search=…&at=…` is **refused** with 400, as 590874f3 did (parked DoD 5: not answered as of a
    time). Round 1 answered as of `at`, which made SPEC's "as they are now" false (the review's SPEC finding).
  - One choice stays different: `search=` together with a set's filters (`where`, `moved`, `alone`) is refused with 400.
    590874f3 answered the search and silently dropped those filters. Refusing is the fail-closed choice (lesson-3), and
    it is the more reversible one: allowing the combination later breaks no caller.
- **Why the earlier runs failed ("nack exited 1", attempts 4–6): not found.** 0261d96d records only the outcome of each
  attempt (3: ack; 4–6: nack exited 1). It holds no log, no failing test and no traceback. bf82f148 says the full suites
  were never run there. Main's changes since 3adf48a6 to the files touched are `Index.stays(until=)`,
  `items.late_cap` and `items.fold_all`. Reading the diff, none of them overlaps the parked hunks, and main's
  `VERSION` was still 3, so a merge conflict does not look like the cause. A test merge (`git merge-tree`) was refused
  in this environment, so this rests on reading the diff alone.
- **Point 3:** main's `itemindex.py`, `items.py`, `cli/record.py` and `web/server.py` are this branch's base, and each
  change is an addition next to them. The one change to main's own behaviour is `VERSION` 3 → 4: every index file is
  built again once, from the record.

**Done (commit a291d592, then round 2):**
- `items.text_of`: an item's string field values (nested dicts and lists too), one per line, the first `TEXT_MOST` =
  65,536 characters, casefolded. It is stored as `items.text` on the index row,
  and every insert or update of the row writes it (each fold, a same-id `set`, a snapshot). A prune's reconcile deletes
  the row.
- `VERSION` 4. The index file's name hashes `VERSION` (`index_for`), so a VERSION-3 file is never opened as the new
  one: the new path is folded from the record. A file at the new path with an older stamp is reset by `_step`. Round
  1's `alter table … add column text` on open could not be reached by a real old file, so round 2 removed it (review
  finding).
- A search that finds any row with NULL text first rebuilds the whole index (`Index._rebuild`: version cleared, folded
  again). It never answers "no match" for that row. Round 2: the probe (`where text is null`) is served by a partial
  index (`items_untexted`, of the rows with NULL text only), so it no longer scans the table on each search. The test
  checks the query plan (review finding).
- `_where(words=)`: one `instr(text, ?) > 0` per word, joined with AND. The listing's late items (the API's `until`)
  are matched in Python on the same text.
- `items.words_of`: casefolded, split on whitespace, 1 to `WORDS_MOST` = 8 words, otherwise `BadSearch`. In the CLI
  that is exit 2; in the API it is 400. The server reads `search=` with blanks kept, because `parse_qs` drops a blank
  `search=`, which would otherwise list everything.
- CLI `item --search`: refused with `--at` or with an item's NAME (exit 2, with a message); `-n` clamped to
  1..`items.LISTED`; `search` added to `goodmodel.READ_FLAGS`.
- API: `listing(search=)` gives the listing's usual shape. `per_kind` padding is skipped while searching. `search=`
  with `at=` or with a set's filters is refused with 400.
- Docs: SPEC §5a *Search* (now naming string values only, and the refusals in both the CLI and the API, so "as they
  are now" holds for both), the AGENT-GUIDE's tools, the `--search` help, and the GAPS entry.
- 77 net lines of code (106 added, 29 removed), within the 90 budget.

**Choices made without anyone to ask (the most reversible):**
- `search=` combined with a set's filters is refused with 400 (see above: this differs from 590874f3).
- The GAPS entry says done "on `factory/searching-items-and-querying`". The merge commit is not known until the factory
  merges.

**Tests run, round 2** (one process at a time, not under the watchdog):
- `tests/test_item_search.py`: 8 passed. The old-index test now builds a real VERSION-3 file (the column dropped) and
  shows that the new VERSION opens another path, leaves the old file alone and finds the items. It also shows a
  new-path file with an old stamp being reset. The every-word test checks that numbers, booleans and keys are not
  searched. The CLI/API test checks `search=&at=` → 400. The `--at` test checks `item NAME --search` → exit 2.
- `test_item_index`, `test_cli_fallback`, `test_item_sets`, `test_spec_items` (96 passed together), then
  `test_graph_cli_web`, `test_web_access`, `test_rollup`, `test_item_systems`, `test_daemon_docs` (139 passed together).
  After the doc and help edits, `test_item_search`, `test_cli_fallback`, `test_daemon_docs` and `test_graph_cli_web`
  passed again (83).
- `ruff check ergostat tests scripts`: clean.
- Round 2's breaks, each watched fail, then undone: the partial index made `where text is not null` → the NULL-text test
  failed; `search=&at=` let through → the CLI/API test failed; numbers searched as JSON → the every-word test failed;
  NAME let through → the `--at` test failed; `VERSION` left out of the file name's hash → the old-index test failed
  (`no such column: text`).

**Tests run, round 1:**
- `tests/test_item_search.py`: 8 passed.
- `test_cli_fallback`, `test_item_index`, `test_item_sets`, `test_graph_cli_web`, `test_spec_items`,
  `test_item_systems`, `test_web_access`, `test_daemon_docs`: all passed, run file by file and not under the watchdog.
- `ruff check ergostat tests scripts`: clean.
- Breaks seen to fail (lesson-9). Each was made, its test was watched fail, then it was undone:
  - no NULL rebuild → the NULL-text test failed;
  - `text=coalesce(text, ?)` on update → the changed-field test failed;
  - no cap → the cap test failed;
  - blank `search=` dropped → the CLI/API test failed;
  - no `alter table` → the old-index test failed (that test and that path were replaced in round 2, see above);
  - no `--at` check → the `--at` test failed.

**Left, for the factory:**
1. Run the unit suite and the four browser files under `scripts/suite_watch.py` after merging origin/main (point 6).
   Neither was run here. No `origin` exists in this clone, and the brief leaves the full suites to the factory.
2. Correct the graph's wrong "merged" status for gap/item-text-search.

**After the factory's unit run failed (same round):** the tail handed back holds only progress dots. It names no
test and shows no traceback, so it looks like the run was cut off or killed. The fix round could not run a shell
(Bash was refused), so it could neither reproduce the failure, run a test, nor commit. Reading the changed paths for a
hang found no cause: `_where` → `_rebuild` takes `begin immediate` only under the index's lock and outside any open
transaction, `text_of` never gives NULL, so the rebuild cannot loop, and nothing else writes `items` rows. No code was
changed, because a guessed fix would break lesson-13. Left: run the unit suite again under `scripts/suite_watch.py`
with the failing test's name and traceback kept, then fix what it names.

**Round 2 still does not know the cause of that unit run's failure.** The full unit suite is not run here: the
brief leaves it to the factory, under the watchdog. The touched test files all pass, one process at a time (above).
Round 2 removed the `alter table` on open, and the probe now reads a partial index. Neither is known to be the cause.

**The review's findings, round 1 → round 2 (lesson-12):**
1. (blocking) Points 5 and 1: the parked commits were in the clone. → The parked file was brought over unchanged. The
   rebuild was checked against the parked definition, its notes and its code, and three choices were aligned (above).
   The cause of the nack runs was looked for in 0261d96d and is reported as not found. This section is corrected.
2. The NULL probe scanned the table twice per listing. → It is now served by a partial index, and the test checks the
   plan.
3. The `alter table` path was dead code, and the old-index test simulated a case that cannot arise. → The path is
   removed. The test now covers the real case (another path, the old file left alone) and the stamp reset.
4. SPEC's "as they are now" was false for the API's `at=`. → The API refuses `search=` with `at=` (400). The test is in
   `test_search_cli_and_api_agree`, and SPEC names both refusals.

**Round 3: main already holds the search; this branch's code gave way to it (merge c773dc6f).** The factory merged
main e1e778c1 into the branch. Main had meanwhile landed the parked branch itself: cbadc4cc (item-text-search,
round 2) is an ancestor of e1e778c1, and so are gap/item-graph-queries (near, path, about; `VERSION` 5, the `@about`
links) and `use: upkeep`'s index tidier. Keeping both sides would have put two implementations of one search in the
same files, so each conflict was resolved to main's side. After the merge, `git diff MERGE_HEAD` is empty for every
file in `ergostat/` and `tests/`, and for `docs/AGENT-GUIDE.md`, `docs/GAPS.md` and the parked
`docs/roadmap/overnight/item-text-search.md`. The branch's second SPEC §5a *Search* paragraph, which merged without a
conflict, was removed: main's own paragraph (SPEC line 799) stays. GAPS keeps main's one entry for gap/item-search,
with search and near/path/about both done. Leaving the branch's copy would have listed it twice, which intake reports
as a standing problem. So this branch now adds only this file. 0 net lines of code.

Against the definition of done, as main now has it (checked by reading main's code and by `tests/test_item_search.py`,
main's copy):
- Points 1 and 2 hold on main, which follows the parked branch's round 2. The names differ from this branch's earlier
  rounds (`items.SEARCH_WORDS`, `items.words`, refused with `BadSet`; the partial index `items_textless`; the CLI's
  blank-search message "1 to 8 words"). `--search` is in `goodmodel.READ_FLAGS`, next to main's `near`, `path_to` and
  `about_item`.
- Point 3: kept, because main's side was taken whole.
- Point 4: SPEC §5a *Search*, the AGENT-GUIDE's item commands, the `--search` help and the GAPS entry are main's. The
  GAPS entry names `factory/item-text-search`, not this branch's merge commit. It also says near/path/about are
  **done**, not open as this definition expected, because gap/item-graph-queries has landed.
- Point 5: the parked file is main's copy, which is the parked branch's own (its round-2 "Where it stopped" included).
- Point 6: not run here. The brief leaves the unit suite and the four browser files to the factory, under
  `scripts/suite_watch.py`.

Commands refused this round (Bash): `git checkout --theirs -- <the conflicted files>`, `git show MERGE_HEAD:<path> >
<path>`, and a `for` loop over `git merge-base --is-ancestor`. The conflicts were resolved with the editor instead,
and each file was compared with `git diff MERGE_HEAD`.

Tests run, round 3, after the merge (one command at a time): `tests/test_item_search.py` (8 passed);
`test_item_index`, `test_cli_fallback`, `test_item_graph_queries`, `test_item_about` (101 passed);
`test_graph_cli_web`, `test_spec_items`, `test_item_sets`, `test_daemon_docs` (76 passed). `ruff check ergostat tests
scripts`: clean. No break was made this round, since the branch changes no code (lesson-9 does not apply).

Left, for the factory: run the unit suite and the four browser files under the watchdog (point 6). If they pass, the
gap is closed by main as it stands. Landing this branch adds only this record.
