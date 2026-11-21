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

**The parked branch was not available.** This clone holds only `main` and this branch: there is no
`origin/factory/item-text-search` (no remote ref, and no commit of it reachable by `git log --all`), and the network is
out of reach. So its four commits were not carried over. The search was **built again on current main from this
definition's own restatement of the parked one** (point 1's list). It was not checked against the parked file or its
review notes. For the same reason:
- **Point 5 is not met.** `docs/roadmap/overnight/item-text-search.md` is not on this branch. Writing it from memory
  would not be "unchanged", so it was left out. The factory, which has the ref, should copy it in from
  `origin/factory/item-text-search` unchanged (`git checkout origin/factory/item-text-search -- docs/roadmap/overnight/item-text-search.md`).
- **Why the earlier runs failed ("nack exited 1", attempts 4–6): not found.** Their logs and branch were not here to read.
- **Point 3:** there was no merge to resolve. Main's `itemindex.py`, `items.py`, `cli/record.py` and `web/server.py` are
  this branch's base, and each change is an addition next to them. The one change to main's own behaviour is
  `VERSION` 3 → 4: every index file is built again once, from the record.

**Done (commit a291d592):**
- `items.text_of`: an item's field values (nested dicts and lists too; numbers and booleans as JSON, null left out),
  one per line, the first `TEXT_MOST` = 65,536 characters, casefolded. It is stored as `items.text` on the index row,
  and every insert or update of the row writes it (each fold, a same-id `set`, a snapshot). A prune's reconcile deletes
  the row.
- `VERSION` 4. An index file without the `text` column gets it added on open. Its old version stamp then resets it.
- A search that finds any row with NULL text first rebuilds the whole index (`Index._rebuild`: version cleared, folded
  again). It never answers "no match" for that row.
- `_where(words=)`: one `instr(text, ?) > 0` per word, joined with AND. The listing's late items (the API's `until`)
  are matched in Python on the same text.
- `items.words_of`: casefolded, split on whitespace, 1 to `WORDS_MOST` = 8 words, otherwise `BadSearch`. In the CLI
  that is exit 2; in the API it is 400. The server reads `search=` with blanks kept, because `parse_qs` drops a blank
  `search=`, which would otherwise list everything.
- CLI `item --search`: refused with `--at` (exit 2, with a message); `-n` clamped to 1..`items.LISTED`; `search` added
  to `goodmodel.READ_FLAGS`.
- API: `listing(search=)` gives the listing's usual shape. `per_kind` padding is skipped while searching.
- Docs: SPEC §5a *Search*, the AGENT-GUIDE's tools, the `--search` help, and the GAPS entry.
- 78 net lines of code (107 added, 29 removed), within the 90 budget.

**Choices made without anyone to ask (the most reversible):**
- Field **keys** are not searched, only values.
- `search=` combined with a set's filters (`where`, `moved`, `alone`) is refused with 400, so neither filter is
  silently dropped.
- `ergostat item NAME --search ...` shows the item, as before. Search applies only to the listing.
- The GAPS entry says done "on `factory/searching-items-and-querying`". The merge commit is not known until the factory
  merges.

**Tests run:**
- `tests/test_item_search.py`: 8 passed.
- `test_cli_fallback`, `test_item_index`, `test_item_sets`, `test_graph_cli_web`, `test_spec_items`,
  `test_item_systems`, `test_web_access`, `test_daemon_docs`: all passed, run file by file and not under the watchdog.
- `ruff check ergostat tests scripts`: clean.
- Breaks seen to fail (lesson-9). Each was made, its test was watched fail, then it was undone:
  - no NULL rebuild → the NULL-text test failed;
  - `text=coalesce(text, ?)` on update → the changed-field test failed;
  - no cap → the cap test failed;
  - blank `search=` dropped → the CLI/API test failed;
  - no `alter table` → the old-index test failed;
  - no `--at` check → the `--at` test failed.

**Left, for the factory:**
1. Copy in the parked definition file (point 5).
2. Run the unit suite and the four browser files under `scripts/suite_watch.py` after merging origin/main (point 6).
   Neither was run here. No `origin` exists in this clone, and the brief leaves the full suites to the factory.
3. Correct the graph's wrong "merged" status for gap/item-text-search.
