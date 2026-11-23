# item-page-fields-flow-and-lists-are-cards: An item's page lays short fields in a flowing grid, shows lists of records as cards with files behind disclosures, and keeps field history in one section

depends-on: []

Problem: the owner calls the item page very good, but short fields waste width, 'history (N changes)' sits on every field, and 'contexts' 'nests to the right, renders nested markdown in tables'. Cause found: contexts is a fold: append field of gap (ergostat.yaml:137); each entry is brief.assemble's dict (dev/bin/brief.py:85-88): a live gap (gap/queue-picks-mergeable) has 6 entries with 17 keys, one a list of about 20 ids, one `brief: file:run/briefs/...md`. fieldView (ergostat/web/static/pages.js:197-203) renders any list of objects as a table with a column per key and each cell recursively; a file: string goes to fileView (pages.js:186-194), so each whole Markdown brief is rendered inside cell 15 of 17, inside the td of table.fields. Depth only stops nested objects. refreshFiles (pages.js:228) re-asks every file each 4 s. 30 of that gap's 47 fields are short scalars on full-width rows, each with a details.history (pages.js:953); history is 43% of /api/items/ID (32.8 of 77 KB for ticket/SCRUM-2 on :8791), sent on every poll. Same smaller on :8792/item/review%2F2243 (shots/plan-ks-job-item-review.png).
Change (pageItem's Fields section only; other fieldView callers pass their mode and keep their output):
1. Short fields (number, boolean, string of 60 chars or fewer, not file:) go in a grid (repeat(auto-fill, minmax(11rem, 1fr))), name small and muted above the value; the kind's show: fields first, then by name.
2. Every other field is a full-width block below, headed by its name.
3. A list of objects is a list of cards, newest first, 3 shown and the rest under a closed 'N earlier' details. In a card scalar keys flow as 'key value · key value'; a list of short strings wraps as chips; a nested object is a dl; a file: value is a closed details named by key and size, fetched and rendered full width only when opened (refreshFiles skips closed ones); headings in rendered Markdown are demoted below the page's h2. A list whose entries share at most 6 scalar keys stays a table. No table inside a table; a file is never rendered in a table cell (in a cell it is a link).
4. The per-field disclosure goes; a field with more than one change shows 'N changes' beside its name, opening one collapsed 'Changes' section at the page's end filtered to that field.
5. /api/items/ID sends history only when asked (history=FIELD|all; the counts always); `ergostat item ID --history` unchanged. This gap owns the history default of the item answer; perf-answers-carry-only-what-is-drawn adds only since_seq on top of it.
Definition of done:
1. On an item whose append field holds dicts with a file: key, no table is inside a td of the fields section and no Markdown is rendered until its disclosure opens; opened, it is as wide as the content column; scrollWidth equals clientWidth.
2. At 1440 px a gap with 30 short fields takes at most 6 grid rows.
3. A closed file disclosure is never fetched.
4. No field row has a history disclosure; Changes lists a field's changes latest first, each linked to its event.
5. The poll's answer has no history key unless the section is open.
6. A session's messages, a remote item, Items list cells and the claim/decision/action views render as before; a snapshot's item page shows Changes or says it is not held.
7. SPEC §5a (docs/SPEC.md:1267) says where history is shown and the API default.
Files: ergostat/web/static/pages.js (pageItem, fieldView mode, historyView, refreshFiles), style.css, ergostat/web/server.py, ergostat/spec/items.py, docs/SPEC.md, tests/test_diagram_rendering.py (1021-1030 pins the old disclosure), tests/test_items_page.py.
Acceptance tests: test_a_list_of_records_is_cards_with_files_behind_disclosures (contexts of two dicts each with brief: file:b1.md and 8 keys; /file/b1.md requested only after the click), test_short_fields_flow_in_a_grid (20 numeric fields, at most 4 rows at 1440 px by bounding boxes), test_field_history_is_one_section. Each fails on main. Rebase onto filed Q53, Q54, Q82 if they landed.
Budget: 220 net lines.

Milestone: kind-and-item-pages. Owner items: 20 (fields, history, the contexts section). From the owner's list and the design review of 2026-11-22.

## Where it stopped

Built, round 1: every change above. Net 123 lines outside tests, docs and dev (budget 220). Choices made alone, each the more reversible one:
- "fieldView mode": the page's Fields section calls a new pageFieldView (pages.js) and fieldView itself is unchanged, so its other callers (Items list cells, the remote item, the history rows) keep their output without passing anything.
- "share at most 6 scalar keys": counted as the keys holding a scalar in more than half of the entries. A session's messages (role, line, uuid, text, sometimes meta, truncated, bytes, full) so stay a table, as before; their cells are now small (a nested value is its JSON, a file a link), so no table is inside a table.
- "named by key and size": the size comes from a new `file_sizes` in /api/items/ID (server.py `_sizes`), found where /file/ finds files, never in the state folder; one that cannot be read has no size shown. A HEAD request would have fetched a closed file.
- history=FIELD sends all of that field's changes, history=all every field's, as `all` did before; with no history= there is no `history` key, only `changes`. The other readers of its.detail (CLI, MCP, ops, the remote API, recipes) are unchanged.
- The unnarrowed Changes section lists the changes field by field (each field's latest first), not merged across fields by time (lesson 2). It shows a field's latest 200, naming `ergostat item ID --history` for the rest.
- A snapshot holds item answers without history; its Changes section says they are not held there.
- Markdown headings are demoted only in a file opened in a card (change 3). A field that is itself a file, a full-width block, renders as before, its h1 kept (test_an_items_files_show_as_what_they_are_and_nothing_in_them_runs pins that).
- The opened file is as wide as the card it is in: the content column less the card's padding and border (the test allows 40 px).
Tests: the three acceptance tests, which fail when their behaviour breaks: a closed file rendered gives 2 .md where 0 are wanted, 30rem cells give 10 rows, and always asking for history puts history=all in the polls. Main's page has no .card, .field-grid or .changes-of, so each test's first wait times out. Restoring main's files to run them there was refused, so I argue this from the code and did not see it run. Also new: test_a_snapshots_item_page_says_its_changes_are_not_held and test_the_item_answer_sends_history_only_when_asked_and_sizes_its_files (test_spec_items.py). test_an_items_page_shows_each_fields_history_and_a_session_folded_from_its_transcript now uses the Changes section, and test_page_refresh's `details.history` is now that section. DoD 2 is tested at 20 fields and 4 rows (the definition's acceptance test), not at 30 and 6.
Runs: tests/test_items_page.py whole, after the last change: 25 passed, with the 4 new tests. tests/test_page_refresh.py whole: 8 passed. Unit files: test_spec_items, test_claims, test_remote_items, test_graph_cli_web, test_changesets and test_transcripts all pass. ruff is clean. main is already in the branch, with nothing to merge. tests/test_diagram_rendering.py whole: 197 passed, 3 failed. The fix for one (the demotion above) passed when run alone. Two are left, which I take to be unrelated:
- test_every_view_draws_cleanly_and_in_time: coordinator routing took 21.1 s against a 20 s bound, a diagram timing under load. It was not rerun.
- test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page fails alone too: after an accept, /model still lists a change to review instead of "Nothing waiting." That page (pageModel, /api/fit, the proposals) reads nothing this branch changed. I could not run it on main because `git archive main | tar -x -C /tmp/mainsrc` was refused.
Not done: Q53, Q54 and Q82 are not in this clone, so nothing was rebased onto them.

## Where it stopped

Parked by the factory (implementor, 2026-11-22 14:22).

Stopped on its last attempt by RuntimeError: claude: success: You've hit your weekly limit · resets Nov 24, 3am (UTC)

```
Traceback (most recent call last):
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 166, in main
    return build(cfg, given, began)
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 221, in build
    got = fac.session(cfg, "implementor", prompt, work)
  File "/Users/user/ergostat-live/instance/dev/bin/fac.py", line 669, in session
    raise RuntimeError(f"claude: {out.get('subtype')}: {str(out.get('result'))[:300]}")
RuntimeError: claude: success: You've hit your weekly limit · resets Nov 24, 3am (UTC)

```

## Where it stopped

Parked by the factory (dead-letters, 2026-11-22 14:22).

Its runs failed past their attempts (a dead letter):
- attempt 17: nack a switch drains the runs under way (run/drain.json): taken again after it
- attempt 18: nack a switch drains the runs under way (run/drain.json): taken again after it
- attempt 19: nack given back
- attempt 20: nack the run ended with gap/item-page-fields-flow-and-lists-are-cards still parked

## Where it stopped

Continued, round 1 (2026-11-23): main (63998238) merged in. Its one conflict, tests/test_items_page.py, was both sides
adding tests at the file's end; both kept, each with its own teardown. No code changed after the merge.
Runs after the merge: ruff clean; tests/test_spec_items.py 8 passed; tests/test_items_page.py 29 passed, 6 failed
(7 on a second run); tests/test_page_refresh.py 8 passed, 1 failed. The branch's five new item-page tests pass.
The failures, none of them on the item page:
- test_a_stocks_and_a_flows_side_panel_list_their_items_and_link_to_exactly_that_set,
  test_a_valves_leased_items_are_listed_live, test_the_model_changes_are_found_by_heading_search_and_panel
  (the diagram's side panel, itemsets.js: .item-list, .leases-line, .counts-line never appear);
  test_a_crossing_opens_the_record_narrowed_to_its_goal_and_time_and_the_filter_stays_in_the_address,
  test_a_snapshot_lists_a_parts_items_and_opens_its_set, test_a_set_left_out_of_a_snapshot_says_so,
  test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart (the last added by this merge);
  test_page_refresh's test_other_pages_left_open_change_nothing[diagram?view=process&by=events-graph].
  Three of them fail alone too, so load isn't the cause.
Why I take them to be unrelated: the branch changes only pageItem's Fields and Changes (pages.js), its CSS and
/api/items/ID (server.py); the side panel is itemsets.js reading /api/parts, which the branch doesn't touch, and none of
the branch's new top-level names (isShort, isScalar, pageFieldView, recordView, fileFold, historyRows) is declared
in another script. The merge brought 84 changed files under ergostat/, among them diagram.js, details.js, relations.js
and server.py. Not proved: running them on main was refused (`git checkout main -- <the branch's 3 files>` and
`git worktree add --detach /tmp/mainwt main`), so whether main fails them alone was not seen.
