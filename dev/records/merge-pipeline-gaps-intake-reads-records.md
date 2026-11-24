# merge-pipeline-gaps-intake-reads-records: The intake reads the entries from dev/records/, and twice() is retired

depends-on: [merge-pipeline-gaps-md-regenerated-on-land]

Problem: the intake reads docs/GAPS.md on main (dev/bin/intake.py:218) and tolerates the union merge's duplicates with twice(); tests/test_gaps_doc.py pins live GAPS.md text and reds the queue when a merge moves it. Since GAPS.md is now the render of the records, reading the records gives the same answer without the file. Change: intake reads gapsdoc.parse over main's dev/records/ (one helper gapsdoc.entries(repo, ref) that later readers share); twice() goes; a record counts as a definition only with `## Definition of done`, so an Entry-only record never makes a gap ready; an unreadable record is said by name, never read as no entry. tests/test_gaps_doc.py moves to fixtures under tests/fixtures/. Done: on the pinned fixture the intake gives the same gaps, closes, links and sources from the records as from the GAPS.md rendered from them; an Entry-only record makes nothing ready; an unreadable record is reported and the pass goes on; tests/test_gaps_doc.py reads no live docs/GAPS.md. Files: dev/bin/intake.py, dev/bin/gapsdoc.py, tests/test_backlog.py, tests/test_gaps_doc.py. Budget: 50 net lines in dev/bin.

Area: merge-pipeline. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Round 1, built. What is in the branch:

- `gapsdoc.entries(repo, ref)`: every `dev/records/*.md` at `ref`, read with one `git cat-file --batch`, rendered by
  `render()` (which parses each with `parse()`), and the problems, each naming its record: one git cannot show (not
  a blob) or decode (not UTF-8), and render()'s own (a malformed Entry, two titles slugging to one branch). It returns
  None when `ref` has no `GAPS-head.md`; an unreadable GAPS-head.md raises.
- `intake.read()`: the text the records render, its entries (`gaps_md`), and the problems. `twice()` is gone. Two
  entries of one gap id (two records of one title: "External event logs" on main today) are neither found nor
  closed, said as `GAPS.md lists it N times, lines ...`. Each problem goes on the gap it names (by id, or its record
  name as the gap's branch) as a dependency problem, else on stderr. The pass goes on.
- `intake.definition()`: a `dev/records/` record (a `REF:dev/records/...`, the gap's field or main or its branch) is
  a definition only with a `## Definition of done` line. `run/defs/` and the old `docs/roadmap/overnight/` keep the
  old rule (not empty, not Entry-only).
- `tests/test_gaps_doc.py` reads `tests/fixtures/gaps_doc_entries.md`: the Remote systems, IR and upkeep entries,
  copied from docs/GAPS.md at 278f54a4. A test checks each fixture line against that commit's blob (via git, never
  the live file). The record test now checks the live `dev/records/remote-systems.md` Entry is whole
  (`remote_problems`) instead of equal to GAPS.md.
- Acceptance tests in `tests/test_backlog.py`:
  `test_intake_says_the_same_from_the_records_as_from_the_gaps_md_they_render` (the pinned fixture split into
  records, GAPS.md removed, against the rendered GAPS.md alone: every found, closed and dependencies line equal,
  timestamps left out; the External event logs pair said on both paths),
  `test_an_entry_only_record_makes_no_gap_ready` (an Entry alone, then an Entry and a Where it stopped, the old rule's
  hole; then a `## Definition of done` makes it ready),
  `test_an_unreadable_record_is_said_by_name_and_the_pass_goes_on` (a malformed Entry on its gap, a non-UTF-8 record
  on stderr, a new record still found), and `test_two_records_of_one_title_are_reported_never_one_picked` (replaces
  the twice() test, on records and on a GAPS.md before the split).

Choices taken alone (the most reversible):

- A main with no `dev/records/GAPS-head.md` (a tree before the split, and every factory fixture in
  `tests/test_factory.py`, which commits only a docs/GAPS.md) is read from docs/GAPS.md as before. The same rule as
  `rendered_at()`. On ergostat's main the head exists, so the records are what is read. This is a fallback for a
  tree that has no records, not for a record that fails: a missing or unreadable record is a problem, never this.
- The `## Definition of done` rule is held to `dev/records/` records only. Three records of this wave
  (`merge-pipeline-gaps-entries-in-records`, `-md-regenerated-on-land`, this one) have no such heading. A gap whose
  only definition is a heading-less record on main is no longer made ready by the intake. Its definition in
  `run/defs/` (where the coordinator writes) is still read as before.
- `tests/test_gapsdoc.py:333` and `tests/test_factory.py::test_two_gaps_editing_gaps_md_merge_cleanly` called
  `intake.twice()`. Both files are outside the Files list, but the retirement breaks them otherwise. The first
  clause is removed; the second counts repeated ids from `gaps_md`, as `intake.read()` does. `dev/README.md` (the agent guide) says what the intake now reads.

Each new test was seen to fail with its code broken: one record dropped by entries() (the pinned comparison
differs), the old entry_only rule put back (gap.defined on Entry + Where it stopped), a decode error swallowed (no
`zeta: unreadable` on stderr). Size: +37 net lines in dev/bin (budget 50).

Run here, each file alone: tests/test_backlog.py (29 passed), tests/test_gaps_doc.py (10), tests/test_gapsdoc.py
(39), tests/test_factory.py (238 passed, 2 skipped for Docker, 1 failed on `intake.twice`, since fixed and passing
alone). Ruff clean. Not run here: the whole unit suite and the four browser files (the factory's and the queue's;
no page is changed). `scripts/suite_watch.py` and background runs were refused in this session, so the files ran
under `scripts/named_tests.py` alone.

Round 2, the review's one finding (blocking): read() counted repeated ids with gaps_md(), which skips *Done recently*,
so an entry in an open section and again in Done recently was acted on from the open copy (a regression from twice()).

- Fixed in `intake.read()`: repeats are counted over every section (`gaps_md(text, done=True)`, a new keyword), and
  keyed by the gap's branch (`fac.slug(id, 32)`, what the intake gives a found gap), so two titles whose ids differ
  but that slug to one branch (render()'s `slug to one branch` problem, which named no gap) are caught too. Every
  gap of such a group is neither found nor closed, and each gets the problem `GAPS.md lists it N times, lines L
  (section), ...` on itself (or on stderr when no gap has it). dev/README.md and the module docstring say "two
  entries of one branch, in any section, Done recently too".
- New test `tests/test_backlog.py::test_one_copy_in_done_recently_is_counted_never_the_open_one_picked`: on records
  (`gamma` in Done recently and `gamma-2` open in Modelling: gap/gamma not found, said with both sections), and
  before the split (a GAPS.md with `Zeta` done in an open section and open in Done recently: the requested gap/zeta
  is not closed, and the problem is on it). With the count put back to skip Done recently, it fails (gap/gamma
  found). Only the records half was seen to fail that way, since the test stops at its first assert.
- The helper in `tests/test_factory.py::test_two_gaps_editing_gaps_md_merge_cleanly` counts over every section, as
  read() now does. The line asserted in `test_two_records_of_one_title_are_reported_never_one_picked` now names
  sections.

Size: +40 net lines in dev/bin (budget 50). Run here, each file alone: tests/test_backlog.py (30 passed),
tests/test_factory.py (239 passed, 2 skipped for Docker), tests/test_gaps_doc.py and tests/test_gapsdoc.py (50
together). `ruff check ergostat tests scripts` is clean, and so is dev/bin/intake.py. Ruff on all of dev/bin finds two
errors in plan.py and review.py, which this gap does not touch. Not run here: the whole unit suite and the four
browser files (no page is changed).

Round 3, the merge of main (b9341591). Its one finding was the conflict with main, in dev/README.md,
dev/bin/gapsdoc.py and dev/bin/intake.py. Main had landed `merge-pipeline-gaps-deps-read-records`, which adds its own
`gapsdoc.entries(repo, ref) -> (text, {record: why})`, read by `deps.from_main()`, and has `deps.plan(...,
unreadable)` hold a gap whose record cannot be read. The resolution keeps main's signature and contract (and its
tests in tests/test_backlog.py pass unchanged), and keeps what this branch adds:

- `entries()` reads with the branch's one `git cat-file --batch`. A record that is not a blob, or not UTF-8, is in
  `{record: why}` as `unreadable at REF: ...`, and a malformed Entry as `malformed Entry: ...`. An unreadable
  GAPS-head.md raises main's `dev/records/GAPS-head.md at REF cannot be read`. render()'s own problems are no longer
  returned, as on main. The one this gap used (two titles slugging to one branch) is caught by `intake.read()`'s
  count by branch.
- `intake.read()` returns `(text, entries, unreadable, problems)`. `dependencies()` takes the same text and
  `unreadable` and calls `deps.from_gaps(text)` and `deps.plan(..., unreadable)`. It does not call `deps.from_main()`,
  so main is read once per pass and the found/closed and dependency halves cannot see two different mains. A gap whose
  record cannot be read is now held (main's rule) and said on itself. A record no gap has is said on stderr by
  deps.plan (`deps: dev/records/NAME.md cannot be read (...)`). `deps.from_main()` is still main's, and only its tests
  call it now.
- Tests changed to fit: `test_an_unreadable_record_is_said_by_name_and_the_pass_goes_on` asserts deps' wording and
  that delta is held. `test_intake_says_the_same_from_the_records_as_from_the_gaps_md_they_render` drops its
  render-problem line, so the External event logs lines are the same on both paths. With the decode error swallowed
  again, the first test was seen to fail (no `zeta.md cannot be read` on stderr).

Size: +23 net lines in dev/bin against main (budget 50). Run here, each file alone after the merge:
tests/test_backlog.py (33 passed), tests/test_factory.py (243 passed, 2 skipped for Docker), tests/test_gaps_doc.py
with tests/test_gapsdoc.py (49 passed). `ruff check ergostat tests scripts` and the two changed dev/bin files are
clean. Not run here: the whole unit suite and the four browser files (no page is changed).

Round 4, the merge of main (b20756c7). Its one finding was the conflict with main in dev/bin/intake.py: main added
`import onmain` (for `main_moved()`, the release of gaps waiting on main) on the line where the branch added
`import gapsdoc`. Both imports are kept; main's onmain code and the branch's `read()` merged on their own and are
unchanged. Size: still +23 net lines in dev/bin against main (budget 50). Run here, after the merge:
tests/test_backlog.py, tests/test_gaps_doc.py and tests/test_gapsdoc.py together (82 passed), tests/test_factory.py
(247 passed, 2 skipped for Docker). `ruff check ergostat tests scripts` and the two changed dev/bin files are clean.
Not run here: the whole unit suite and the four browser files (no page is changed).

Round 5, the merge of main (666d65d6). Its one finding was the conflict with main in dev/README.md,
dev/bin/gapsdoc.py and tests/test_gaps_doc.py. Main had landed `merge-pipeline-gaps-briefs-read-records`: the briefs,
the planner and the knowledge block read main's records through `gapsdoc.entries` (`brief.records_at_main`), and
tests/test_gaps_doc.py reads the live dev/records/ as `gapsdoc.render` draws them (`gaps_text()`) instead of
docs/GAPS.md. The resolution:

- dev/README.md and gapsdoc.py's docstring say both: the intake and deps read main's records (this branch), and the
  briefs, planner and knowledge block too (main). "Intake still reads GAPS.md" (main's) is gone, as it is no longer
  true.
- tests/test_gaps_doc.py keeps main's `gaps_text()` for every live check (it reads no docs/GAPS.md), and keeps this
  branch's pinned fixture, now named `FIXTURE` (main uses `GAPS` as a label): the fixture's exact parse by the intake
  and its upkeep entry's `(done` are checked, and `test_the_fixture_is_docs_gaps_md_as_of_its_commit` stays. In
  `test_remote_systems_record_entry_is_whole` both asserts are kept (the branch's `remote_problems` and main's equality
  with the render).
- A merged-in interaction, found by running tests/test_factory.py after the merge: main's new
  `test_an_unreadable_record_is_said_in_the_brief_by_name_never_read_as_no_entry` pins `entries()`'s why for a
  malformed Entry as parse()'s own words, and this branch's `entries()` had prefixed `malformed Entry: `. Main's
  contract is kept (the prefix dropped); the branch's
  `test_an_unreadable_record_is_said_by_name_and_the_pass_goes_on` now asserts parse()'s words for delta
  (`cannot be read (bullet line 2 is blank`).

Size: +22 net lines in dev/bin against main 666d65d6 (budget 50). Run here, after the merge: tests/test_gaps_doc.py,
tests/test_gapsdoc.py and tests/test_backlog.py together (82 passed before the prefix fix); tests/test_factory.py
(250 passed, 1 failed: the brief test above, 2 skipped for Docker), then after the fix tests/test_backlog.py,
tests/test_gapsdoc.py and that brief test together (73 passed), and tests/test_factory.py with tests/test_gaps_doc.py
(261 passed, 2 skipped for Docker). `ruff check ergostat tests scripts` and the two changed dev/bin files are clean.
Not run here: the whole unit suite and the four browser files (no page is changed).

Round 6, the queue's finding: the batch of 26 failed, and alone
`tests/test_item_search_gaps.py::test_item_search_entry_listed_once` failed, since it called `intake.twice()`, which
this gap retires (the test came to main with `item-search-join-2` after this branch's grep for callers). It is a
third caller outside the Files list, changed as the other two were: it now counts the entry's gap id over
`intake.gaps_md(text, done=True)` (every section, Done recently too, as `intake.read()` counts) and asserts exactly
one. The helper `intake(fn, args)` takes the extra argument. No other `intake.twice` caller is left in tests/, dev/
or scripts (the mentions left are in other gaps' records, which say what they were). dev/bin is unchanged this round
(+22 net lines against main, budget 50). Not seen to fail with the code broken: the pinned fixture cannot be edited,
and the count is the same one the factory and backlog tests (seen to fail in rounds 1 and 2) use. Run here:
tests/test_item_search_gaps.py (4 passed), tests/test_backlog.py, tests/test_gaps_doc.py and tests/test_gapsdoc.py
together (82 passed), tests/test_factory.py (251 passed, 2 skipped for Docker). `ruff check ergostat tests scripts`
and the two changed dev/bin files are clean. Not run here: the whole unit suite and the four browser files (no page
is changed).
