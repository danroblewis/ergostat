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
