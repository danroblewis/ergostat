# merge-pipeline-gaps-briefs-read-records: The briefs, the planner and the knowledge block read the entries from dev/records/

depends-on: [merge-pipeline-gaps-md-regenerated-on-land]

Problem: dev/bin/brief.py:42-54, plan.py:133 and :422 and knowledge.py:231 read docs/GAPS.md on main for a gap's entry and its section, and tests/test_item_search_gaps.py pins live GAPS.md text. Change: all three read gapsdoc.entries over main's dev/records/ (added here if neither sibling reader gap has landed); the role prompts under dev/prompts/ and dev/README.md say the entry is in the record; test_item_search_gaps.py moves to a fixture. Done: an implementor's, a reviewer's and a planner's brief carry the same entry text from the records as from the rendered GAPS.md on the pinned fixture; an unreadable record is said in the brief by name, never read as no entry; a test asserts no file under tests/ opens docs/GAPS.md. Files: dev/bin/{brief,plan,knowledge}.py, dev/bin/gapsdoc.py, dev/prompts/, dev/README.md, tests/test_item_search_gaps.py, tests/test_factory.py. Budget: 60 net lines in dev/bin.

Area: merge-pipeline. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Built, round 1 (2026-11-24). Size: 35 net lines in dev/bin (61 added, 26 removed), within the 60.

What changed:
- `brief.records_at_main` reads GAPS.md's text as main's records render it (`gapsdoc.entries`, which deps.py already
  used: nothing was added to gapsdoc but its docstring). It is cached per main sha within a process.
  `brief.record_entry` gives the gap's entry, or, when there is none and some record could not be read, those records
  by name with why. `brief.assemble` (the implementor's, reviewer's and planner's briefs), `plan.join_brief` and
  `backlog.py` (through `gaps_entry`) put that text where the entry goes, never "no entry". `plan.entry_of` (the S
  definition) uses only a real entry, so with an unreadable record an S gap takes the planner's full path, and that
  brief names the record. `knowledge.related` takes each gap's section from the records' render, and falls back to
  intake's `section` field only for a gap whose title the render does not hold.
- The four role prompts and dev/README.md say the entry is the record's `## Entry`, as main's records render it.

Decisions taken alone (the most reversible ones):
- Before the split (main has no `dev/records/GAPS-head.md`), the entry is read from main's docs/GAPS.md, as
  `deps.from_main` does. If that read fails, the failure is named in the brief. The test fixtures' checkouts have no
  records, so reading GAPS.md is what keeps them working. On main today the split is done, so this path never runs.
- "No file under tests/ opens docs/GAPS.md" was false for two files outside this gap's Files list:
  `tests/test_gaps_doc.py` and `tests/test_daemon_yaml_review.py`. They now read the records' render of the tree
  (`test_gaps_doc.gaps_text`), not the file, and assert the same things. `tests/test_item_search_gaps.py` reads the
  pinned fixture (`tests/fixtures/gaps_md_pinned.md`), as the definition asks.
- The guard test (`test_no_test_reads_the_repositorys_own_docs_gaps_md`) matches text, so its claim is narrow. It
  catches a path built from `ROOT` or `parents[N]` joined to docs and GAPS.md, an `open("docs/GAPS.md")`, and a
  `HEAD:`, `main:` or `origin/main:` ref to docs/GAPS.md. It does not catch a path built some other way. A pinned
  commit's `<sha>:docs/GAPS.md` (tests/test_gapsdoc.py) is allowed.
- The record has no `## Entry` of its own: the gap came from the planned wave, not from a GAPS.md entry.

Acceptance tests (tests/test_factory.py):
- `test_the_briefs_carry_the_entry_from_the_records_as_the_rendered_gaps_md_has_it`: the pinned fixture is split into
  records on main, and the checkout's docs/GAPS.md holds none of the titles. The implementor's, reviewer's and
  planner's briefs, the join judge's and the S text each carry the block the pinned GAPS.md shows, for two entries.
- `test_an_unreadable_record_is_said_in_the_brief_by_name_never_read_as_no_entry`: a malformed `alpha-thing.md`
  record is named, with why, in all four briefs; the S text is empty. Once mended, the entry comes back. The related
  gaps follow the records' section when it moves. Before the split, the entry comes from docs/GAPS.md.
- `test_no_test_reads_the_repositorys_own_docs_gaps_md`: the guard test above. It failed on its own example lines
  until they were spelt so as not to match.

Breaks seen to fail the tests: dropping the unreadable note in `record_entry` failed the unreadable test at its first
assert. Reading intake's `section` field in `related` failed it at the related check.

Not fixed: ruff over dev/bin (outside the required `ergostat tests scripts`) reports B023 at plan.py:441 and E501 at
review.py:47. Both were there before this branch, and neither is in lines it changed.

Round 2 (2026-11-24). Size: 35 net lines in dev/bin, as before (the fix renames one variable).

The one finding of round 1 (blocking): `plan.join_brief` overwrote its `unread` list with `record_entry`'s note. The
note now has its own name (`note`). It goes only into the parent's entry text, and `unread` stays the list of
sub-gap points. Decision taken alone: when the parent's record cannot be read, that does not make the join short
with no session. Not reading a sub-gap does. The judge's brief names the unreadable record in the entry, as the other
briefs do. This is the more reversible choice: a later gap can add the note to `unread` with one line.

New test, `test_the_join_brief_with_sub_gaps_keeps_its_unread_points_apart_from_the_entry_note` (tests/test_factory.py):
the parent has a child missing from the record (`gap/ghost`) and a sub-gap that is there, with its records first
readable and then not. `unread` is a list. Its points are the ghost's and the sub-gap's, never the record's note.
`short_of` makes one point per item, and the entry names the unreadable record only when it is unreadable. With
round 1's code restored, the test failed: an AttributeError at `unread.append` (plan.py:436).

Round 3 (2026-11-24). Size: 37 net lines in dev/bin (65 added, 28 removed), within the 60.

The finding (the queue's): `tests/test_shell_rule.py`'s two brief tests failed alone. Round 1 had `brief.assemble`
call `record_entry` directly, so the test's stand-in for `brief.gaps_entry`, the seam on main, no longer applied.
The real read then ran, and its `import gapsdoc` failed: the file loads brief.py by path, with dev/bin not on
`sys.path`. In the full suite an earlier test had put it there, so the batch failed only when the file ran alone.
Fix: `assemble` reads the entry through `gaps_entry` again: the entry, or `record_entry`'s note of the records it
may be in. The brief's `gaps_entry` context flag is true only for a real entry (not one starting with `UNREAD`).
The shell-rule test file was not changed. The batch's other failures were not named to this gap, so nothing else
was changed for them.

Breaks seen to fail: with `gaps_entry` returning only the entry (no note), the unreadable test failed at its first
assert, with the brief saying "(no entry: not in main's records)".

Also: two docstring lines in brief.py over ruff's 140 were wrapped (ruff over dev/bin/brief.py is now clean).
