# item-text-search: find items by the words in their fields, kept in the item index
depends-on: []

## Definition of done
1. The item index (`ergostat/spec/itemindex.py`) stores each item's searchable text: the string values of its fields (nested ones too, lowercased, capped per item). The text is written in the same transaction as the item's row and replaced whenever the item is folded again, so words a changed field no longer holds stop matching. An item that `_reconcile` or prune forgets loses its text along with it. The index `VERSION` goes up, so an index file built before this change gets rebuilt; it is never read as having no text.
2. A search is one or more words. It finds the items whose text contains every word (case-insensitive substring), newest first, optionally narrowed by kind and state. It needs no SQLite extension: no FTS5, and no path that returns empty because something is missing.
3. CLI: `ergostat item --search WORDS [--kind K] [--state S] [-n N]` prints the usual listing table restricted to matches; `--json` gives the same shape as the listing. `--search` is classified in `goodmodel.READ_FLAGS`, so the last-good fallback serves it. API: `GET /api/items?search=WORDS` gives the listing shape filtered the same way, with `n` capped at `items.LISTED` as today.
4. Docs say what it matches and no more ("contains every word"; not "relevance" and not "fuzzy"): SPEC §5a, the AGENT-GUIDE's item commands, the `item` help text, and a GAPS.md entry for gap/item-search, marked done for search and open for near, path and about.
5. Out of scope: the Items tab UI (its client-side search box stays as it is), MCP, and `--at` time travel (`--search` with `--at` is refused with a message, not answered as of now).

## Files to touch
`ergostat/spec/itemindex.py`, `ergostat/spec/items.py`, `ergostat/cli/__init__.py`, `ergostat/cli/record.py`, `ergostat/goodmodel.py`, `ergostat/web/server.py`, `docs/SPEC.md`, `docs/AGENT-GUIDE.md`, `docs/GAPS.md`, `tests/test_item_search.py`

## Risks
- lesson-5: an item folded again (a field replaced, a snapshot restored) keeps its old words, so it still matches text it no longer holds.
- lesson-3: an index left from before the change, or an item whose text row is missing, is read as "no match" instead of being rebuilt.
- lesson-8: docs claim relevance ranking or fuzzy matching that the substring match does not do.

## Acceptance tests
- `tests/test_item_search.py::test_search_finds_by_every_word`: `alpha beta` finds only the item holding both words, including a word in a nested field, whatever the case; `--kind` narrows the result.
- `tests/test_item_search.py::test_changed_field_stops_matching` (lesson-5): replace an item's title, and the old word finds nothing while the new one finds it. Fails if the text is not rewritten on fold.
- `tests/test_item_search.py::test_forgotten_item_leaves_search`: an item whose events are all pruned is no longer found.
- `tests/test_item_search.py::test_old_index_rebuilt_and_searchable` (lesson-3): an index stamped with the previous VERSION is rebuilt, and items folded before the upgrade are found.
- `tests/test_item_search.py::test_search_cli_and_api_agree`: CLI `--json` and `/api/items?search=` return the same ids; the CLI also answers under the last-good fallback.
- `tests/test_item_search.py::test_search_with_at_refused`: `--search` with `--at` exits non-zero with a message.

## Size budget
120 net lines

## Notes from the plan review (answer each)

- The per-item text cap (DoD 1) makes the documented 'contains every word' (DoD 4) false for words past the cap: a silent miss and a docs claim wider than the code (lesson-8/lesson-3). Lesson-8 also has no test. State the cap's value and what happens when an item exceeds it (refuse, flag it, or make the docs state the limit), and add a test that puts a word past the cap and checks the documented behaviour.
- The lesson-3 risk names 'an item whose text row is missing', but only the old-VERSION case is tested. Either store the text on the item's own row (so a missing text row can't exist, and say so) or define rebuild/error for a missing row and test it by deleting the row; it must never read as 'no match'.
- Escape LIKE wildcards (% _ \) in search words; test that '50%' doesn't match everything.
- Lowercase query words with the same Python function used on the stored text; SQLite LIKE only folds ASCII. Add a non-ASCII test.
- lesson-5: also test a same-id remake or restored snapshot, not just a title replace.
- lesson-9: test_search_finds_by_every_word must include a decoy item holding only one of the words.
- lesson-4: set a hard maximum on the number of search words and on the CLI's -n, not only the API's n.
- Define the behaviour for an empty or whitespace-only --search (refuse it; don't list everything).
- A 120-line budget is very tight for this scope; don't let it push tests out.
