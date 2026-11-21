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

## Where it stopped

Built, round 1: every point of the definition, 64 net lines in `ergostat/` (90 added, 26 removed), within the
120-line budget. Tests: `tests/test_item_search.py`, 8 tests, the six named plus
`test_words_past_the_cap_are_not_searched` and `test_a_row_without_its_text_is_rebuilt_not_read_as_no_match`.

Not done here: merging origin/main. This clone has no `origin` remote and no network. The branch contains local
`main` (`git merge-base --is-ancestor main HEAD`). The factory's merge and suite run after this are still owed
(lesson-7).

Answers to the plan review's notes:
- **Cap.** `items.TEXT_MOST = 65_536` characters of an item's casefolded text (its fields' string values, nested ones
  too, in document order). A word past the cap is not found. I took the most reversible option: the docs state the
  limit instead of refusing or flagging (SPEC §5a *Search*, the AGENT-GUIDE, `item --search` help). Test:
  `test_words_past_the_cap_are_not_searched` (a word before a 65,536-character field is found, the word after it is not).
- **Missing text row.** The text is a column of the item's own row (`items.text`), written by the same insert or update
  as the row, so there is no separate text row to lose. If a row's text is NULL anyway (an older file given the column
  by `alter table`, or a hand edit), a search rebuilds the index before it reads (`Index._where`). Test: the text is
  set to NULL by hand and the item is still found.
- **Wildcards.** No LIKE: each word is matched with `instr(text, ?) > 0`, a plain substring, so `%`, `_` and `\` are
  only themselves. Test: `50%` finds only the item that holds it, and `_` finds nothing.
- **Non-ASCII.** The stored text and the words both go through `str.casefold` (not `lower`, which keeps `ß`). Nothing
  relies on SQLite's ASCII-only folding. Test: `ÄRGER strasse` finds `Ärger STRAẞE`.
- **lesson-5.** The test replaces a title, remakes the item under the same id with `set`, and restores a snapshot. After
  each, the old words are gone. It checks again after a cold start (read from disk).
- **lesson-9 decoy.** `ticket/2` holds only `alpha` and `ticket/3` only `beta`. Neither is found by `alpha beta`.
- **lesson-4.** At most `items.SEARCH_WORDS = 8` words, or the search is refused. The CLI's `-n` is clamped to 1 to
  `items.LISTED` (500). The API's `n` is capped as before.
- **Empty search.** An empty or whitespace-only search is refused: exit 2 in the CLI, HTTP 400 in the API. A blank
  `?search=` would otherwise be dropped by `parse_qs` and answered as the full listing, so the server keeps it, and the
  test checks it over HTTP.
- **Budget.** It held, with no test dropped.

Mutations tried (lesson-9). Each broke the test named here, and each was reverted:
- the update keeping the old text broke `test_changed_field_stops_matching`;
- the NULL-text guard turned off broke `test_a_row_without_its_text...`;
- `lower` in place of `casefold` broke `test_search_finds_by_every_word`;
- an old VERSION accepted broke `test_old_index_rebuilt_and_searchable`;
- the blank `?search=` no longer kept broke `test_search_cli_and_api_agree`;
- the `--at` refusal removed broke `test_search_with_at_refused`.

Run here, one file at a time: `test_item_search`, `test_item_index`, `test_cli_fallback`, `test_spec_items`,
`test_item_sets`, `test_graph_cli_web` and `test_rollup` all pass, and ruff is clean. Not run here: the full unit suite
and the four browser files, which the factory runs under the watchdog.
