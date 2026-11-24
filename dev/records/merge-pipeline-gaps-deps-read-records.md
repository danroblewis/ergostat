# merge-pipeline-gaps-deps-read-records: The dependency reader reads the entries from dev/records/

depends-on: [merge-pipeline-gaps-md-regenerated-on-land]

Problem: dev/bin/deps.py:44-70 parses docs/GAPS.md on main for each gap's dependencies and closes. Change: deps reads the same entries through gapsdoc.entries over main's dev/records/ (the helper is added here if merge-pipeline-gaps-intake-reads-records has not landed; whichever lands second reuses it and the reviewer checks there is one). Done: on the pinned fixture deps gives the same dependencies, closes and blocked reasons from the records as from the rendered GAPS.md; an unreadable record is said by name and the gaps it names are treated as blocked, never as free; no test of deps reads the live docs/GAPS.md. Files: dev/bin/deps.py, dev/bin/gapsdoc.py, tests/test_backlog.py. Budget: 40 net lines in dev/bin.

Area: merge-pipeline. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Built, round 1 (2026-11-23). Nobody could be asked, so where the definition left room I took the most reversible
reading, listed here for the reviewer:

- `gapsdoc.entries(repo, ref)` is new: merge-pipeline-gaps-intake-reads-records is not on main, so no helper existed.
  It returns GAPS.md's text as the records at `ref` render it, plus `{record: why}` for each record it cannot read.
  deps then parses that text with its existing `from_gaps()`, so the Depends-on table in GAPS-head.md is read too,
  and links, sources and line numbers match the rendered GAPS.md exactly. Whichever of the two gaps lands second
  should reuse it.
- "Unreadable" means git cannot show the record, or its `## Entry` is malformed (`gapsdoc.parse` raises). "The gaps
  it names" means the gap the record belongs to, found by its name as for any NAME: by branch, id or own name. Its
  dependencies cannot be known, so that gap gets the problem (`dependency_problem`), `waits_on_parked` (the hold that
  `takes: where` reads), and a `blocked_reason` naming `dev/records/<name>.md`. Once it is merged or closed there is
  nothing left to hold. Every unreadable record is also said on stderr, including one that is no gap's.
- An unreadable `GAPS-head.md` raises (ValueError), which stops the intake, as an unreadable GAPS.md did before.
  A main with no `GAPS-head.md` at all (before the split) is read from its docs/GAPS.md, and that is said on stderr.
  The test fixtures' checkouts (tests/test_factory.py Factory) are like this.
- "Closes": deps has none of its own, so the test checks that the intake's done rule (`intake.gaps_md`) reads the same
  from the records' text as from the rendered GAPS.md. The intake's own finding and closing still read GAPS.md;
  that is merge-pipeline-gaps-intake-reads-records.
- The call site is in dev/bin/intake.py (`dependencies()`, 2 lines), which the Files list does not name. It is needed
  for deps to read the records at all. dev/README.md says the same in two places.
- The pinned fixture's only links are two `after `redesign``. The test adds a parked `redesign` gap so that the
  comparison covers resolved links and blocked reasons, not only "no gap" problems.
- Size: 39 net lines in dev/bin (deps.py +23, gapsdoc.py +15, intake.py +1).
- This gap has no GAPS.md entry ("not in GAPS.md"), so the record has no `## Entry`.
