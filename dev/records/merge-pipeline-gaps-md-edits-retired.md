# merge-pipeline-gaps-md-edits-retired: No branch edits docs/GAPS.md any more: the carry step and the union merge go

depends-on: [merge-pipeline-gaps-intake-reads-records, merge-pipeline-gaps-deps-read-records, merge-pipeline-gaps-briefs-read-records]

Problem: the carry step in the queue (gapsdoc.carry) and `GAPS.md merge=union` in docs/.gitattributes exist only for branches approved before the cutover. Once none is left they are dead code and the union merge can still splice. Change: before removing anything the gap checks, and says in its record, that no gap in building, built, review, fix, approved, queued or push-pending has a branch whose diff against main touches docs/GAPS.md; if one does, the gap is given back uncounted naming it. Then: remove gapsdoc.carry and its call; the queue gives back to fix, uncounted, an approved gap whose diff touches docs/GAPS.md, with the brief implement.py already gives; remove the union line from docs/.gitattributes; dev/records/GAPS-unplaced.md, if it holds anything, is listed in the record for the coordinator and not deleted. Done: a batch-mate editing GAPS.md goes back uncounted and the batch lands without it; the regeneration commit is unchanged; README and the queue's docstring no longer mention carrying. Files: dev/bin/queue.py, dev/bin/gapsdoc.py, docs/.gitattributes, dev/README.md, tests/test_factory.py. Budget: -20 net lines in dev/bin (a removal).

Area: merge-pipeline. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Round 1, built (2026-11-24).

**The check before removal: not made, and why.** This clone holds only `main` and this branch (`git branch -a`), and
no factory record is reachable from the container, so the gaps in building, built, review, fix, approved, queued or
push-pending and their branches could not be listed or diffed. No branch was found touching docs/GAPS.md, but that is
because none could be looked at, not because none does. The more reversible choice was to go on: after this branch
no GAPS.md edit can land and be lost quietly. The queue sends an approved gap whose own commits touch the file back to
`fix`, uncounted, with the reason as its finding, and the implementor refuses such a branch, uncounted, with the brief
that says to put GAPS.md back and write the entry as the record's `## Entry` (implement.py, unchanged). The worst
case is a gap from before the cutover sent back for one more round, never text dropped from main. **For the
coordinator before landing:** for each gap in those states, `git diff --name-only main...factory/<branch> --
docs/GAPS.md`; if any names the file, give this gap back, uncounted, naming that gap.

**dev/records/GAPS-unplaced.md**: not on main at this branch's base (no such file), so there is nothing to list. The
constant is kept, so entries(), render and the tests still skip the file if a coordinator's copy ever shows up.

**Done:**
- `gapsdoc.carry`, `with_entry`, `rendered_at` and `DONE_AT` removed. `regenerate(root)` now only renders
  docs/GAPS.md from the records (never reading the file) and writes it. The queue's `gaps_md()` still makes the same
  commit, `docs/GAPS.md from the records`, only when the render differs, and lands the batch without it when the
  render fails.
- queue.py: `gaps_md_edited(repo, onto, sha)` (a `onto...sha` diff, where onto is the batch so far, so a stacked
  gap's bases are not counted against it). picks() sends such a gap back the first time it reads its reviewed commit
  (`gap.sent-back`, findings `not merged: uncounted: ...`, no failed_gates). It takes no slot and the batch lands
  without it. If it is the run's own gap, the batch's why is SENT and nothing is nacked. A diff git cannot make
  raises and the run fails, rather than reading as no edit.
- docs/.gitattributes deleted: its only line was `GAPS.md merge=union` and the comment on it.
  dev/knowledge/.gitattributes (review-lessons) is not this gap's and is untouched.
- dev/README.md, queue.py's module and picks() docstrings, gapsdoc's docstring and implement.gaps_md_edited's
  docstring no longer mention carrying.

**Acceptance tests** (tests/test_factory.py):
`test_a_batch_mate_editing_gaps_md_goes_back_uncounted_and_the_batch_lands_without_it` checks that zeta and plain
land, the last commit is still `docs/GAPS.md from the records` with zeta drawn, and edits is in `fix` with no
failed_gates.
`test_the_run_s_own_gap_editing_gaps_md_goes_back_uncounted_and_main_stays` and
`test_gaps_md_has_no_union_merge_so_two_edits_side_by_side_conflict` (`git check-attr` reads unspecified, and two
side-by-side edits conflict) were added too.
`test_no_record_change_makes_no_commit_and_a_malformed_record_lands_without_one` is narrowed to the malformed
record, with no GAPS.md edit. The two carry landing tests are gone.
With the queue check disabled, both queue tests failed; with it back, they pass.

tests/test_gapsdoc.py is not in the Files list, but its carry() tests had to go with carry(). It now has three
regenerate tests: it writes only GAPS.md and never reads it into a record; a record-only entry is drawn and
GAPS-unplaced.md is neither drawn nor deleted; a malformed record writes nothing.

Size: dev/bin is +36 / -163 lines (-127 net), against a budget of -20.
