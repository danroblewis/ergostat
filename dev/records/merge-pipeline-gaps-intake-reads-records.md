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
