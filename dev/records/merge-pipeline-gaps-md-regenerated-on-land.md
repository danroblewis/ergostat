# merge-pipeline-gaps-md-regenerated-on-land: The entries move to the records and the merge queue writes docs/GAPS.md from them inside each landing; every reader still reads GAPS.md

depends-on: [merge-pipeline-gaps-entries-in-records]

Problem: the entries must move to dev/records/ without a window in which a branch's GAPS.md edit is read by nothing or overwritten. So the writing is cut over first and the readers later: after this gap GAPS.md is always the render of the records, and every reader (intake, deps, brief, plan, knowledge) still reads it, unchanged. Change: (1) run `gapsdoc.py split` once and commit it: each entry appended as `## Entry` at the end of dev/records/<branch>.md, never overwriting, head to dev/records/GAPS-head.md; GAPS.md itself does not change in that commit. (2) Old definitions stay findable: fac.definition_file (dev/bin/fac.py:224-233) counts dev/records/<branch>.md as the definition only when it has a `## Definition of done` section, otherwise it returns docs/roadmap/overnight/<branch>.md when that exists; implement.definition_first (implement.py:44-58) appends to an Entry-only record and never writes a second definition for a gap whose old-folder file exists. (3) queue.py renders inside the landing: after land() returns and before the point of no return (before `done = True`, the saved `landing` state and gap.merged, queue.py:835-842), it first carries the batch's own GAPS.md edits into the records (gapsdoc.carry(pre, head): entry text and done lines the batch added to GAPS.md that the records lack are appended to the named records and said by name; one it cannot place is said on the run as `gaps_md_unplaced` and kept in dev/records/GAPS-unplaced.md, never dropped), then renders and commits a differing result as `docs/GAPS.md from the records`; `merged` is reassigned to that commit, so main_sha on every landed gap and the sha ask() pushes are the same head, and recover() treats it as part of the landing. A render failure lands the batch without the commit and says `gaps_md: why` on the run, never blocking a merge. (4) implement.py refuses, uncounted and before the suites (next to strays, implement.py:228-231), a branch whose own new commits touch docs/GAPS.md, with a brief pointing at the record's Entry; branches already approved are carried by (3). house-rules.md:33-34 and dev/README.md say the entry is written in the record. The union merge stays until merge-pipeline-gaps-md-edits-retired. Done: intake and deps give the same gaps, closes, links and sources after the migration commit as before it; an approved branch that edited GAPS.md lands and its text is in a record and on the pushed head; main_sha equals the pushed sha (tested); no record change makes no commit; a malformed record lands the batch and leaves GAPS.md as it was; a gap defined only in the old folder still resolves to that file after the split (tested for a continued gap's REF too); a new GAPS.md edit is refused uncounted. Files: dev/bin/queue.py, dev/bin/gapsdoc.py, dev/bin/implement.py, dev/bin/fac.py, dev/records/, dev/knowledge/house-rules.md, dev/README.md, tests/test_factory.py, tests/test_gapsdoc.py. Budget: 130 net lines in dev/bin.

Area: merge-pipeline. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Round 1 stopped before any code: this gap waits on its dependency, merge-pipeline-gaps-entries-in-records, which is not on main.

- What is missing: there is no `dev/bin/gapsdoc.py`, no `tests/test_gapsdoc.py`, no `dev/records/merge-pipeline-gaps-entries-in-records.md`, and no commit on main that names that gap (checked with `git log`, a grep of the tree for `gapsdoc` and a listing of dev/records/). Every step of this definition calls that module (`gapsdoc.py split`, `gapsdoc.carry(pre, head)`, the render), and its record format (`## Entry`, `dev/records/GAPS-head.md`).
- Why not build it here: writing gapsdoc's split, render and carry would be building the dependency inside this gap (house rule: build only what was asked; lesson-13), and it would not fit the 130-line budget. Stopping is the most reversible choice. Nothing in dev/bin, tests or docs was changed.
- What is left: all of it, (1) through (4) and the Done tests, once the dependency lands and main is merged in. Notes for that round: the anchors have moved. fac.definition_file is still dev/bin/fac.py:224-233; it already falls back to the old folder, but only when the new file is missing, so it still needs the `## Definition of done` check. implement.definition_first is implement.py:44-58. The strays refusal is implement.py:228-231. In queue.py the point of no return is now `done = True` at queue.py:918, with the `landing` state saved at :920, land() at :641, recover() at :812 and ask() at :949.

## Where it stopped

Parked by the factory (review/merge-pipeline-gaps-md-regenerated-on-land-1, 2026-11-22 10:53).

Done: the definition of done is committed first and a 'Where it stopped' section was added after it; no code, tests or docs changed. Left: all of (1)-(4) (the gapsdoc split migration commit, the fac.definition_file '## Definition of done' check and the implement.definition_first guard, carry and render inside the queue landing with merged reassigned before done = True, refusing new GAPS.md edits uncounted in implement.py, the house-rules and README wording) and every Done test. Why stop: every step calls dev/bin/gapsdoc.py (split, carry, render) and its record format, which belong to the dependency merge-pipeline-gaps-entries-in-records. That gap is not in this tree; building it here would be outside this gap and over its budget.

## Where it stopped

Built, in the continued gap's round 1. The dependency is on main now (962ccf13) and is merged into the branch (45718e4f). main has not moved since, so
there was nothing more to merge. All of (1) to (4) is built:

- 39758fc4 has the code, tests and docs. b8334bfc is the split commit: 67 files under dev/records/ (GAPS-head.md,
  64 new records, and an Entry appended to the two that existed: finding-structure-from-residuals and
  from-upkeep-s-fault-injection). docs/GAPS.md is unchanged in that commit. c3a03e9c pins that commit in a test.
- (2) `fac.definition_file` returns the old-folder file when it exists and the new record has no
  `## Definition of done` (`fac.defines`). A continued gap's `REF:dev/records/X.md` gets the same rule.
  `implement.definition_first` writes nothing when the old file is named. It gives a record that holds only its
  Entry the definition.
- (3) `queue.gaps_md()` runs between land() and `done = True`. It calls `gapsdoc.regenerate()`: carry, then render,
  then write. It commits only when the files differ, with the message `docs/GAPS.md from the records`, and `merged`
  is reassigned to that commit. The run says `gaps_md_carried`, `gaps_md_unplaced`, or `gaps_md: why`.
- (4) `implement.py` refuses a branch whose diff from main changes docs/GAPS.md (`gaps_md_edited`). The refusal is
  uncounted, comes after the strays check and before the suites, and its brief names `dev/records/<branch>.md`.
  The next try's brief starts with that same message. The wording is in house-rules.md and dev/README.md.

Choices made alone, each the more reversible one:

- **The split commit was written by hand, not by running the program.** Running `dev/bin/gapsdoc.py` directly was
  refused in this session, and so was every other way of running Python except `scripts/named_tests.py`. So the 67
  files were written from GAPS.md by hand. The pinned test
  (`test_the_split_commit_moves_every_entry_into_the_records_and_every_reader_sees_the_same`) checks them against
  `split(GAPS.md at b8334bfc^)` line for line. It checks the head, each record (new, or the old text with the Entry
  appended), that nothing else was made, `render == GAPS.md`, and that intake's `gaps_md`/`twice` and
  `deps.from_gaps` give the same result. It passes, so the commit is what `gapsdoc.py split` writes. `split` itself
  (no FILE) now writes, and it refuses to overwrite: tested on the pinned fixture.
- **Records are named by branch.** split now names each record by the gap id cut to 32 (intake's branch), as the
  definition says (`dev/records/<branch>.md`). Before, it used the 60-character gap id.
- **What carry counts as the batch's own edit.** It is an entry block in GAPS.md at the batch's head that neither
  the records at `pre` rendered (`gapsdoc.rendered_at`) nor the records at head render. GAPS.md at `pre` is not the
  baseline. This way the first landing after the split also carries GAPS.md edits that main gained after b8334bfc:
  there is no GAPS-head.md at `pre`, so every block the records do not render is carried. An edit left behind by an
  earlier failed render is carried at the next landing.
- **Where carry puts an entry.** The record whose Entry has that title, or else the record its branch names. The
  block's section and bullet replace that Entry's. Each rendered done line (``  - *Done DATE* (`name`): ...``) goes
  to the record it names. A named record with no Entry gets `entry-of:` the umbrella. An entry with any part that
  cannot be placed is placed in no part: it is kept whole in dev/records/GAPS-unplaced.md and named on the run. An
  entry a batch deletes from GAPS.md is not carried, and the render puts it back. Removing an entry means removing
  its record's Entry.
- **What counts as a render failure.** Any render() problem except four that lose no text (`gapsdoc.BENIGN`): two
  titles on one branch, a slot listed twice, an entry listed under another section, and a section missing from the
  head. A malformed Entry, a sub-gap with no umbrella, or a slot with no entry fails the render. Then nothing is
  written, and main stays at the batch's merge. The live tree has one benign problem: the two *External event logs*
  entries share a branch. `render --check` still exits 1 on it, as it did before.
- **Where the definition goes in an Entry-only record.** It goes before the Entry, not after it. An Entry runs to the
  next `## ` heading, so the Entry has to stay the last section for parse() to read it.
- **Outside the Files list.** First, `dev/bin/intake.py` (2 lines): `intake.definition` skips a record that holds
  only its Entry (`fac.entry_only`). Without that, every open GAPS.md entry would read as defined by its own Entry
  after the split, and would be taken as ready. Second, `dev/prompts/definition.md` told sessions to edit
  docs/GAPS.md as well, which this gap now refuses. Its note now says the queue writes GAPS.md.
- **A failure while the render commits.** main goes back to the batch's merge (`reset --hard` on the queue's own
  checkout), and the files it wrote that the merge lacks are removed. recover() is unchanged: the commit is made
  before `done = True`. A stop or a SIGKILL before that point undoes it with the merges. After that point, the
  `landing` block names HEAD, which is the render commit.

Tests: tests/test_gapsdoc.py, 28 passed. Of the new tests in tests/test_factory.py, six were run and passed:
`test_a_definition_in_the_old_folder_resolves_past_a_record_that_is_only_its_entry` (a continued gap's REF too),
`test_a_record_that_is_only_its_entry_is_given_the_definition_before_it`,
`test_a_branch_that_edits_gaps_md_is_refused_uncounted_before_the_suites`,
`test_an_approved_branch_that_edited_gaps_md_lands_with_its_text_in_a_record` (main_sha equals the pushed sha, and
both equal the head with the render commit),
`test_no_record_change_makes_no_commit_and_a_malformed_record_lands_without_one`, and the pinned split test. Each
break below was seen to fail its test: BENIGN made to match everything (the malformed-record test); `merged` not
reassigned (main_sha differs from the head); intake's Entry-only check removed (the old-folder test reads
`main:dev/records/warm.md`). The existing old-path, new-path-wins and scratch-refusal tests were run again. Not run
here: the whole unit suite and the browser files (the factory and the queue run them). ruff is clean on ergostat,
tests and scripts.

Overrun reason: dev/bin is about 184 net lines against 130. The extra comes from three needs the definition did not
size: intake's guard against Entry-only records being read as definitions, carrying against the records' render at
`pre` (rendered_at) so main's GAPS.md edits since the split are not lost at the first landing, and carry placing done
lines under an umbrella (entry-of) with all-or-nothing placement and GAPS-unplaced.md.

## Where it stopped

Built, in round 2 of the continued gap (70bb4328). Both blocking findings of the review are answered. That review
listed no other findings.

- **A new entry was always unplaced.** It is placed now. When no record holds the entry's title and the record its
  branch names does not exist, `gapsdoc.carry` makes `dev/records/<branch>.md` holding only that Entry, as split()
  writes one. A done line naming a missing record makes that record too, as `entry-of:` the entry. Only three things
  are still unplaced: an entry whose branch names a record whose Entry has another title (it is never written over),
  a done line under an entry that is not its own nor its umbrella, and a name that fails `fac.SAFE`. The test that
  pinned the loss now says the opposite:
  `test_an_approved_branch_that_edited_gaps_md_lands_with_its_text_in_a_record` checks that EPSILON is in
  `dev/records/epsilon.md`, has its slot in GAPS-head.md, and is on the pushed head's GAPS.md, with nothing unplaced.
  New: `test_an_entry_whose_branch_names_another_titles_record_is_kept_unplaced`.
- **An edit outside the entries was reverted with nothing said.** It is carried now. If the head that split() cuts
  from the batch's GAPS.md differs from the head of `pre`'s render, GAPS-head.md becomes the batch's head. Each
  `@entry` slot names the record that draws that block (render's new `drawn` map), or the record carry put it in, or
  the record with its title. A slot no record holds is dropped, and that text is in GAPS-unplaced.md. The run says
  `GAPS-head.md: the batch's GAPS.md text outside the entries` in `gaps_md_carried`. New:
  `test_a_batchs_edit_outside_the_entries_is_carried_into_the_head`, which edits the preamble, a section's prose and
  adds a section heading.

Choices made alone, each the more reversible one:

- **When GAPS-head.md is rebuilt.** Only when the batch's GAPS.md changed outside the entries, which includes adding,
  removing or moving an entry. A batch that edits GAPS-head.md directly and also edits GAPS.md's head has its
  GAPS-head.md edit replaced by the GAPS.md one.
- **An entry the batch deleted from GAPS.md.** It loses its slot, and render puts it back at the end of its
  section, as before.
- **A retitled entry.** A batch that changes an entry's title in GAPS.md gets a new record under the new title's
  branch. The old record's Entry stays and still renders, so the entry shows twice in GAPS.md, never once lost.
  Both are said by name in `gaps_md_carried`.

Tests run (through `scripts/named_tests.py`; running Python any other way was refused again):
tests/test_gapsdoc.py, 30 passed; `test_an_approved_branch_that_edited_gaps_md_lands_with_its_text_in_a_record` and
`test_no_record_change_makes_no_commit_and_a_malformed_record_lands_without_one`, 2 passed. Each fix was broken and
seen to fail its tests. Refusing a record that does not exist failed 2 tests. Never rebuilding GAPS-head.md failed 3,
the prose test among them. Removing the other-title guard failed the unplaced test. ruff is clean on ergostat, tests
and scripts. Not run here: the whole unit suite and the browser files.

Overrun reason: dev/bin is 208 net lines against 130 (184 after round 1). Beyond round 1's three reasons, round 2's review asked for two more things the definition did not size: placing new entries in records made for them (with the guard against writing over another title's Entry), and carrying GAPS.md's text outside the entries into GAPS-head.md with each slot mapped to its record.

## Where it stopped

Parked by the factory (implementor, 2026-11-22 14:16).

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

Parked by the factory (dead-letters, 2026-11-22 14:17).

Its runs failed past their attempts (a dead letter):
- attempt 26: nack a switch drains the runs under way (run/drain.json): taken again after it
- attempt 27: nack a switch drains the runs under way (run/drain.json): taken again after it
- attempt 28: nack exited 1
- attempt 29: nack the run ended with gap/merge-pipeline-gaps-md-regenerated-on-continued still parked

## Where it stopped

Built, in round 1 of the second continuation (merge 2f4ba207). This round only finished the factory's merge of main
(63998238). No review findings were open. Nothing new was built.

- `dev/bin/queue.py`: main added the run's summed suite counts (`summed(...)`) to the run record, and the branch added
  the GAPS.md notes (`**notes`) to the same line. Both are kept. Their keys (`counts`, `suites` and `gaps_md*`) do not
  collide.
- `dev/records/ergostat-s-upkeep-as-a-modelled.md`: main made this record for its gap, and the branch's split had made
  it as an Entry-only record. Both are kept: main's definition comes first and the Entry comes last, so parse() still
  reads it. The Entry's Left clause is main's GAPS.md text ("the loops are drawn, not closed by ergostat (their
  controllers are its code)"), so the render matches main's GAPS.md for that entry.
- Run again after the merge: ruff clean; tests/test_gapsdoc.py 30 passed; tests/test_queue.py 17 passed; and the five
  gap tests in tests/test_factory.py passed (old-folder resolution, definition before an Entry-only record, refusal
  of a GAPS.md edit, approved branch landing with main_sha equal to the pushed head, and no-change/malformed record).
  Not run here: the whole unit suite and the browser files.
- The size note is unchanged: dev/bin is still about 208 net lines against 130, and the merge adds no new lines. The
  overrun reasons are the ones given in rounds 1 and 2 above.

## Where it stopped

Built, in round 2 of the second continuation: main (f086f76e) merged in (e74f4824), and the review's one finding fixed
(14167388). The review listed no other findings.

- **The merge.** `dev/bin/implement.py`: main now passes `against` (main, or main and the bases) to `conflict_brief`.
  That is kept, and so is the branch's GAPS.md-edit brief, which still compares with main. `dev/bin/queue.py`: both
  sides' imports are kept (`flakes`, `gapsdoc`, `halves`). `tests/test_factory.py`: main deleted `dev/bin/prefixes.py`
  and its tests. The branch's copy of those tests is dropped and the gap's own tests are kept.
  `dev/records/remote-systems.md`: main's file is taken whole. Its Entry is main's GAPS.md text, and main's
  `tests/test_gaps_doc.py` checks that. `dev/records/the-day-s-ai-budget-p3-runs.md`: main's definition comes first,
  and the split's Entry is last, with its text set to main's current GAPS.md text for that entry (main added the
  `ergostat.toml` clause).
- **Found on main, not fixed here (lesson-13).** Main's own docs/GAPS.md holds two *The day's AI budget, P3* entries:
  the old "in progress" one, which toml-models-budget edited, and the new "done" one from the-day-s-ai-budget-p3-runs.
  A union merge kept both. The records hold only the first. The first landing carries the second into
  `dev/records/the-day-s-ai-budget-p3-runs-2.md` (see the fix below), so neither is lost. Removing the stale one is
  for its own gap, which would delete that record's Entry.
- **The finding (two records of one title).** carry() matched a block to a record by title alone and kept only the
  last record read, so editing one of two same-title records wrote over the other. Now `tops` keeps every record of a
  title. An edited block goes to the one record of its title whose drawn block (render's `drawn`) the batch's GAPS.md
  no longer shows. If two such records exist, which one the block replaces is not known: the block is kept whole in
  GAPS-unplaced.md and named on the run, and neither record is written. A block of a title whose records all still
  show their own block is another entry of that title. It gets a record of its own, `<branch>-N`, as split() names
  one. A union merge of two branches editing one entry puts the first block in the record. The second goes to a
  `-N` record, or, if a done line in it names the first record, it is kept in GAPS-unplaced.md and said. It is never
  written over the first. New tests:
  `test_two_records_of_one_title_each_keep_their_entry_when_either_is_edited` (editing either of two same-title
  records keeps both and renders the edit in its own record) and
  `test_two_edits_of_one_entry_keep_the_first_in_its_record_and_the_other_said_never_lost` (the union case, plus a
  third entry of a title going to `remote-systems-2`). Breaking the fix (matching the last-read record of the title,
  as before) failed both.
- Tests run after the merge and the fix (through `scripts/named_tests.py`): tests/test_gapsdoc.py 33 passed;
  tests/test_queue.py 17 passed; tests/test_queue_halves.py 55 passed; tests/test_gaps_doc.py 9 passed; and the five
  gap tests in tests/test_factory.py passed. ruff is clean on ergostat, tests and scripts and on dev/bin/gapsdoc.py.
  `ruff check dev/bin` reports two findings outside this gap: dev/bin/plan.py:439 B023 and dev/bin/review.py:43
  E501. Neither file is touched by this branch. Not run here: the whole unit suite and the browser files.

Overrun reason: dev/bin is 219 net lines against 130 (208 before this round). Beyond the reasons given in rounds 1 and 2, the review asked carry() to tell apart records that share a title, which takes 11 more lines.

## Where it stopped

The build step failed on `tests/test_factory.py::test_an_approved_switch_drains_and_switches_through_the_engine`
(`'switcher' in e.running` after its 120 s wait, in an 831 s run of the file). Nothing was changed for it. It is
outside this gap (lesson-13):

- Run alone on this branch it passes (1 passed, 147 s for the whole test, setup and the 90 s switch wait included).
- The switcher's run is `dev/bin/drain.py`. It imports only `fac` and `live`. The branch changes neither drain.py nor
  live.py. Its one change to fac.py (`definition_file`, `defines`, `entry_only`) is never called on that path. Each
  step makes several `ergostat` CLI calls (`fac.items`, `fac.say`, `action_state`), and each is a fresh process that
  loads the whole model. The model (ergostat.yaml, dev/model/) does not read dev/records/, so the branch's new
  records do not reach it. A run that misses a fixed 120 s wait only when the machine is loaded is lesson-10's
  load-dependent bound, which belongs in its own gap.
- Not checked: whether it fails on main under the same load. Running the test in a worktree of main
  (`git worktree add -q /tmp/mainwt main && ...`) was refused in this session.
- The merge of main (f086f76e) was already committed in e74f4824, with no conflict left.

## Where it stopped

The switcher test's failure is fixed in the code, as the factory asked. The cause was found by timing each ergostat
call the step makes (the timing was temporary and is not committed). `fac.items(kind)` with no state lists each of
the kind's states with an ergostat process of its own, including the states the kind's line counts 0. A switcher
step (`items("upgrade")`, then `under_way()` over gap, research and situation) made about 45 such calls, at about 1 s
each: 46 s a step alone, so two steps under the load of the build suite passed the test's 120 s wait. Now
`fac.items` lists only the states counted above 0 (a header it cannot read still lists everything, as before). A step
takes about 6 s, and the test runs in 75 s instead of 153 s. Every other caller of `fac.items` gets the same saving.
The cause is on main too: the branch had not changed this code. The fix is in this branch because the factory asked
for it here.

- New test: `tests/test_fac_items.py::test_a_state_counted_empty_is_not_listed`. It failed with the filter removed.
- Run: tests/test_fac_items.py, 9 passed; the switcher test, 1 passed (75 s); tests/test_queue.py,
  tests/test_backlog.py and tests/test_milestones.py (other callers of `fac.items`), 87 passed. ruff is clean on
  ergostat, tests and scripts.
- Refused in this session: `git checkout -- tests/test_factory.py` (the timing was taken out by hand instead), and
  running a short Python script through bash.
