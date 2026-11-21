# kb-about: an item can say which parts of the model it is about, and explain, check and status point at it
depends-on: []

## Definition of done
- An item kind may declare a field that names parts of the model (`goal.x`, `stock.x`, `flow.x`, `auxiliary.x`,
  `block.x`). The names use the text form claims already use for `about`. This is opt-in per kind and ergostat
  declares no kind of its own (invariant 12). A model where no kind declares the field does no lookup.
- The item index keeps these item→part links with its other links. "Items about goal.x" is one indexed lookup, not a
  scan of every item. Folding works like a relation field: an event that sets `about` to a new list replaces the old
  one, so a part dropped from an item, or an item made again under the same id, no longer points at that part.
- `ergostat explain <part>` (CLI and MCP), when given a project, ends with a line listing the open (not finished)
  items about that part: id, then title or first field, at most 5 with "and N more". Finished items (e.g. a
  `retired` knowledge entry) are not listed. If the index can't be read, it says the knowledge is unknown, not "none".
- A `check` finding whose `about` is a part that has open items about it carries their ids. An item that names a part
  not in the model is itself a finding (`about-missing-part`), never dropped silently.
- `ergostat status`: a loop that is off (the attention line or the loop row) lists the ids of open items about its
  goal or its measured value, at most 3 with "+N".
- The factory: each entry in `dev/knowledge/` may have an *About:* line naming parts of the root model.
  `knowledge.py sync` puts these names on the `knowledge/<id>` item, and the kind in `ergostat.yaml` declares the
  field. At least the lessons about the pipeline name the goals they bear on.
- SPEC §5a and §12 (findings), `docs/AGENT-GUIDE.md` and `dev/knowledge/README.md` say all of this.

## Files to touch
ergostat/spec/ir.py, ergostat/spec/compile.py (the kind's declaration), ergostat/spec/itemindex.py,
ergostat/spec/explain.py, ergostat/spec/findings.py, ergostat/cli/status.py, ergostat/mcp.py (only if explain needs
the project passed), dev/bin/knowledge.py, dev/knowledge/*.md, ergostat.yaml, docs/SPEC.md, docs/AGENT-GUIDE.md,
dev/knowledge/README.md, tests/test_item_about.py, tests/test_factory_knowledge.py

## Risks
- lesson-5: an item remade under the same id, or with `about` changed, keeps pointing at its old part.
- lesson-3: an unreadable index, or a name for a missing part, reads as "no knowledge" or is dropped.
- lesson-8: the docs promise "every item about it is shown" but the output is capped or finished items are filtered.

## Acceptance tests
- `tests/test_item_about.py::test_explain_lists_open_items_about_a_goal`: two open items about `goal.a`, one retired
  one, and one about `stock.b`. explain of `goal.a` lists exactly the two open ones. Six items show 5 and "and 1 more".
- `tests/test_item_about.py::test_about_replaced_not_merged_on_remake`: an item moved from `goal.a` to `goal.b`, and
  an item retired then found again under the same id with a new `about`, each appear only under their current part.
  Fails if the field folds as add (lesson-5).
- `tests/test_item_about.py::test_lookup_is_indexed_not_a_scan`: with 5,000 unrelated items, the lookup reads only the
  link rows (patch the fold read and assert it is not called per item).
- `tests/test_item_about.py::test_unreadable_index_says_unknown`: a corrupt index file makes explain say the knowledge
  is unknown, not "none" (lesson-3).
- `tests/test_item_about.py::test_missing_part_is_a_finding_and_findings_carry_ids`: `about: goal.gone` gives
  `about-missing-part`. A `missing-feedback` finding on `goal.a` carries the ids of items about it.
- `tests/test_item_about.py::test_status_off_loop_points_at_knowledge`: an off loop's status line shows its item ids
  (at most 3, "+N"). A loop that holds shows none.
- `tests/test_factory_knowledge.py::test_sync_carries_about`: an *About:* line reaches the item. Removing it clears
  the field on the next sync.

## Size budget
220 net lines (outside tests/, docs/, dev/).

## Notes from the plan review (answer each)

- Index schema migration (lesson-3): an index built before this change has no item->part links, so lookups would wrongly say 'none'. Bump the index version or rebuild, and add a test that an old index does not report 'none'.
- Unreadable index in check and status (lesson-3): both must report the knowledge as unknown, not as no items, and check must not quietly skip about-missing-part. Test both.
- Malformed or unknown-prefix names (e.g. 'foo.x', 'goal.') and a missing block.x must also give about-missing-part. Add cases to test_missing_part_is_a_finding_and_findings_carry_ids.
- test_lookup_is_indexed_not_a_scan can pass on a scan that reads raw events without the fold. Count every item event/row read, and report that the test failed against a deliberate scan (lesson-9).
- 'A model where no kind declares the field does no lookup' has no test. Add one that patches the index read and asserts it is not called.
- MCP explain with a project is not tested. Add a test that it lists the same items as the CLI.
- Status test: cover an item about the loop's measured value (not only its goal) and both the attention line and the loop row.
- Docs (SPEC section 5a/section 12, AGENT-GUIDE, knowledge README) must state the caps (5 / 3) and that only open items are listed; no 'every item' wording (lesson-8).
- knowledge.py sync with an About: line naming a missing part must surface as a finding. Cover it in test_factory_knowledge.py.

## Where it stopped

Built, round 1: everything in the definition of done. 190 net lines outside tests/, docs/ and dev/ (budget 220).

Decisions taken alone (the most reversible option each time):
- The kind's key is `about: FIELD` (the name of the field holding the parts). It must fold by `replace`; any other
  `fold:` for it, or a relation's name, is the error `bad-about`. Also added to `schema/ergostat.schema.json`.
- The links are rows of the existing `links` table under the relation `@about` (never a relation's name). The links
  to items (`links_from`, `links_to`) leave them out, so precedence, joins and an item's page are unchanged.
- Only **open** items are checked for `about-missing-part`: a retired entry naming a goal since removed is not a
  finding. One finding per missing name, with the ids of the items that hold it.
- A corrupt index file is still healed from the record (as before), so explain answers correctly then. "unknown" is
  said when the index cannot be read even so (healing fails, the record cannot be read). Tests cover both.
- `knowledge.py sync`: an entry found again after it was retired without an *About:* line gets `about: []`, so the
  item does not keep its old parts (lesson-5).

Answers to the plan review's notes:
- Index migration: `VERSION` is 4 (and part of the file's hash, with each kind's `about`). An index of layout 3 is
  folded again: `test_an_index_built_before_the_about_links_is_rebuilt` (fails with VERSION left at 3: checked).
- Unreadable index in check and status: `test_unreadable_index_says_unknown` (explain, and check gives only
  `about-unknown`, no missing-part verdict) and `test_status_with_an_unreadable_index_says_unknown`.
- Malformed names: `foo.x`, `goal.`, `block.nowhere`, `stock.a.main` and `goal.gone` are each
  `about-missing-part` in `test_missing_part_is_a_finding_and_findings_carry_ids`.
- The lookup test counts `Index._item` rows and every raw-event read (`of_items`, `query`, ...), and fails on a fold.
  Run against two deliberate scans: one over the index's items (5002 rows read, failed) and one over the raw events
  with no fold (5001 events read, failed).
- No declaring kind, no lookup: `test_no_kind_declares_about_no_lookup` (index_for and Index.about patched to fail).
- MCP explain: `test_mcp_explain_lists_the_same_items_as_the_cli`.
- Status: an item about the measured value (`stock.a`) is listed; the attention line, the loop row and `--json` are
  checked; a holding loop names none.
- Docs state the caps (5, 3) and "open items only"; no "every item" wording.
- Sync with a missing part: `test_sync_carries_about` folds the synced item into a copy of the root model's record,
  and `check` gives `about-missing-part` for `goal.gone`. `test_every_about_line_names_a_part_of_the_root_model`
  holds the real *About:* lines to the root model.

Mutations run (lesson-9), each failed the test named and was reverted: links not deleted on refold
(`test_about_replaced_not_merged_on_remake`); the lookup made a scan, twice (`test_lookup_is_indexed_not_a_scan`); the
lookup failing open to `{}` (both unknown tests); VERSION left at 3; found-again without clearing `about`
(`test_sync_carries_about`).

Not run here: the whole unit suite and the browser files (the factory runs them after). This clone has no
origin/main to merge; main is already contained in the branch.
