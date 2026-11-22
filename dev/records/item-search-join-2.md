# item-search-join-2: mark gap/item-search done in docs/GAPS.md, naming both merge commits
depends-on: [item-text-search, item-graph-queries, item-search-join-1]

## Definition of done
Every feature is already on main and nothing is rebuilt. Search merged in `512f08ef` and near, path and about merged in `c5eb54e6`. Code, tests, SPEC §5a and the AGENT-GUIDE are already correct. Only the GAPS.md entry is behind, because item-search-join-1's commit 81e0a8c7 is only on `origin/factory/item-search-join-1` and not on main.
1. In `docs/GAPS.md` under `## Interface`, the bullet **Searching items and querying their graph** opens with a parenthetical whose first clause is `done`, for example `(done, both halves merged; `gap/item-search`)`. The words "split in two" are gone. `dev/bin/intake.py`'s `gaps_md` must read the entry as `gaps_says == "done"`. Copying 81e0a8c7's form `(`gap/item-search`): **done**` does not pass, because intake reads it as open.
2. The *near, path and about* sub-point names `c5eb54e6` in place of "the coordinator fills in the merge commit". The *Search* sub-point names `512f08ef`. Both are commits on main.
3. "Not the Items page's own box, not MCP, not `--at`." stays word for word. The rest of the entry's text is unchanged apart from rewrapping.
4. The entry appears exactly once in GAPS.md (`intake.twice` finds nothing for it). No other entry changes. Nothing outside `docs/GAPS.md`, the branch's record and the new test file changes.
5. The new tests, `tests/test_gaps_doc.py`, `tests/test_item_search.py` and `tests/test_item_graph_queries.py` pass. Ruff is clean. The branch has origin/main merged in before it is called built.

## Relation to other work
- item-text-search (merged): its merge commit `512f08ef` is the one cited. Nothing of it is rebuilt.
- item-graph-queries (merged): its merge commit `c5eb54e6` is the one cited. Nothing of it is rebuilt.
- item-search-join-1 (merged per the graph, but its commit is not on main): this redoes its one docs edit so that intake reads the entry as done.
- Other active gaps also edit `docs/GAPS.md` in other sections, so a merge of main can splice this entry (lesson-7).

## Files to touch
- `docs/GAPS.md`
- `dev/records/item-search-join-2.md` (new)
- `tests/test_item_search_gaps.py` (new)

## Risks
- lesson-7: a merge of main splices this entry with another one. The result can leave "split in two" and "done" side by side, or the entry listed twice. The tests read the merged file, and the uniqueness test catches a doubled entry.
- lesson-8: the entry could say done in a form intake reads as open, or cite a hash that is not on main. The tests use intake's own parser and `git merge-base --is-ancestor`.
- lesson-9: a doc test that checks only that a string is present passes on main today. Each test must be shown to fail on main's current entry before the edit (say so in the record).

## Acceptance tests
- `tests/test_item_search_gaps.py::test_item_search_entry_read_done_by_intake`: runs `intake.gaps_md` over GAPS.md (in a subprocess, as `tests/test_gaps_doc.py` does). Checks that the parse found many entries, and that the `## Interface` entry titled "Searching items and querying their graph" has `gaps_says == "done"` and no "split in two". It fails on main today.
- `tests/test_item_search_gaps.py::test_item_search_entry_names_both_merge_commits`: the *Search* sub-point contains `512f08ef` and the *near, path and about* sub-point contains `c5eb54e6`. Both hashes are ancestors of origin/main (else main, else HEAD). The entry no longer contains "the coordinator fills in". It fails on main today.
- `tests/test_item_search_gaps.py::test_item_search_entry_keeps_its_limits`: the entry's text, with its line breaks joined, contains "Not the Items page's own box, not MCP, not `--at`." exactly once. It fails if the limits are reworded or lost in a splice.
- `tests/test_item_search_gaps.py::test_item_search_entry_listed_once`: `intake.twice` reports nothing for this entry's gap id, and the title appears at exactly one `- **` bullet. It fails on a duplicated entry left by a merge.

## Size budget
40 net lines (the branch's record under `dev/`; no code changes)
size: S (confidence: medium)

## Where it stopped
Built; nothing left. No code changed: only `docs/GAPS.md`'s one entry, this record and `tests/test_item_search_gaps.py`.
- The entry now opens `(done, both halves merged; `gap/item-search`)`; intake reads it as `done`. *Search* names
  `512f08ef` and *near, path and about* names `c5eb54e6`. The limits sentence is unchanged.
- Seen failing (lesson-9). On main's entry, `..._read_done_by_intake` failed (intake read `open`) and
  `..._names_both_merge_commits` failed (no `512f08ef`). After the edit I broke the entry on purpose: I reworded the
  limits to "the Items page's box" and added a second `- **Searching items and querying their graph** (open)`
  bullet. All four tests failed, including `..._keeps_its_limits` (count 0) and `..._listed_once` (`intake.twice`
  named lines 372 and 378). Then I reverted the break.
- This clone has no `origin` remote and no `origin/main` ref, only local `main`, which is what the branch was made
  from. So there was nothing newer to merge in. The tests' ancestry check fell back to `main`, and both hashes are on
  it. This is the most reversible choice: the merge queue merges origin/main and runs the suites again.
- Not this gap's: `intake.twice` also reports `gap/external-event-logs` listed twice on main (GAPS.md lines 51 and
  60). I left it alone (lesson-13).

Round 2 (the queue's finding: all four tests failed alone after the merge of main, 97dc1327).
- Cause (lesson-7): main had since taken item-search-join-1's edit (its form, `(`gap/item-search`): **done**`, plus
  `512f08ef` and `c5eb54e6`). Merge 97dc1327 kept both versions, so there were two title bullets and the *near, path
  and about* sub-point's first three lines appeared twice, cut off mid-sentence. The tests caught it.
- Fix: one entry. It is main's text except for the opening line, which is back in the form intake reads as `done`.
  `git diff main -- docs/GAPS.md` now changes only that two-line opening.
- Seen failing: with main's opening line put back, `..._read_done_by_intake` fails (intake reads `open`). The other
  three pass on main's entry now, because main already names both hashes and lists the entry once. The spliced
  state the queue ran made all four fail. With the fix, all four pass, and so do `tests/test_gaps_doc.py`,
  `tests/test_item_search.py` and `tests/test_item_graph_queries.py`. Ruff is clean.
- This clone still has only local `main` (no `origin`); 97dc1327 merged it, and nothing on it is newer.
- Not this gap's (lesson-13): main's own GAPS.md has the architecture entry under *Model* spliced three ways by
  earlier merges (three "system's Dynamics panel" resumes, each with its own *Left* clause). It is the same on main,
  so I left it alone.
