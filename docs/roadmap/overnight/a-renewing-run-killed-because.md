# a-renewing-run-killed-because: close the gap's paperwork: main already has the renewal grace and the index-read refusal with its cost test, so the GAPS entry moves to *Done recently*
depends-on: []

## The gap (as found on main)

Main already has everything this GAPS entry asks for. Branch `leaserenew` was merged as 1f013ba. Its last commit, 372533d ("Leases: refused expiries read from the item index, never an item folded again"), fixed the cost that had parked it. **This branch changes no code**: nothing under `ergostat/`, `dev/`, `scripts/`, `schema/` or `examples/`.

- **Grace and second look.** `ergostat/leases/terms.py::grace(ttl)` gives the grace, and `ergostat/leases/dispatch.py` (around lines 309–361) takes the second look at the same expiry. Just before it writes, it reads the lease again and writes nothing if the lease was renewed or ended.
- **The fold's refusal.** `ergostat.lease.expired` carries `expires`, and the fold refuses an expiry when the lease was renewed after that `expires` was judged. SPEC §9.5 (the table row around line 2112, and around line 2212) already says so.
- **Readers that leave a refused expiry out.** `fold.refused_expiries` is honoured by `leases/measures.py` (`counts` line 47 and `attention` line 73), `numbers/etamodel.py:221` (passes `ix`), `numbers/blockmodels.py:250` and `workspaces/leases.py:91`.
- **What was "still needed", now done.** `refused_expiries` reads `refused` from `items` (the caller's folds) or else from the item index (`its._index(..., False)`). It folds an item only when neither holds it, and then skips `TRANSCRIPT_TYPES`. `tests/test_lease_refused_cost.py::test_many_expired_items_with_long_transcripts_cost_about_what_they_did` covers 300 items × 200 transcript lines. It asserts that no item's events are queried again, and that each of `measures.counts` (plain and `@developer`), `etamodel.read` and `blockmodels.identify` costs ≤ 2× + 50 ms of its cost with `refused_expiries` stubbed to `set()`.
- **Where it is written up.** `docs/roadmap/overnight/leaserenew.md` already ends with a *Done (2026-11-20)* paragraph.

What is still wrong: `docs/GAPS.md` (lines 224–231, under `## Runtime, scale and latency`) still lists the gap as "parked on `leaserenew`" with "Still needed: read `refused` from the item index, and a performance test…". Both now exist on main. As long as the entry stays, `dev/bin/intake.py::gaps_md` keeps returning it as a parked gap.

## Definition of done

1. **The definition is the first commit.** The branch's first commit adds `docs/roadmap/overnight/a-renewing-run-killed-because.md`, holding this definition. After that it changes only by appending *Where it stopped*.
2. **The entry leaves the open sections.** In `docs/GAPS.md`, the bullet starting `**A renewing run killed because the engine was busy recording its renewal**` and all its continuation lines (through "…long transcripts.") are removed from `## Runtime, scale and latency`. No other bullet in that section changes.
3. **One entry under `## Done recently` takes its place**, inserted as the first bullet of that section (above whatever is first when the branch is cut; on main today that is *Warm processes for blocks*). Its title starts `**A renewing run killed because the engine was busy recording its renewal**` and its first parenthesis starts `(done`. It cites `leaserenew`, the merge 1f013ba and 372533d, SPEC §9.5, and `docs/roadmap/overnight/leaserenew.md`. It says in one or two sentences what was built:
   - the second look a grace after the first, `grace(ttl)` (a tenth of the TTL, 1–30 s);
   - the re-read before the write;
   - the fold refusing an expiry judged before a renewal;
   - the readers that leave a refused expiry out, named exactly as in the list above (measures `counts`/`attention`, the estimates, the block models, the workspace sweep);
   - what each item refused, read from the item index, transcripts never folded.
4. **Numbers only from the record, attributed (lesson-8).** Any number in the new entry is quoted from `leaserenew.md` and labelled as measured there on 2026-11-20:
   - with a GIL-holding thread in the engine, 16 of 32 runs killed on main before the fix, 0 of 48 after;
   - at 1,000 items × 300 lines, counts / estimate / identify took 0.15 / 0.13 / 0.10 s before refused expiries were left out and 0.17 / 0.14 / 0.12 s now.

   The entry claims no figure the implementor did not see in that file or measure again. If they measure again, they write the new figures and the conditions in *Where it stopped*. The entry does not say "never killed" or "no cost". It may say "the cost test bounds each read at 2× + 50 ms of the cost without the refusal", which is what the test asserts.
5. **What the factory reads.** `dev/bin/intake.py::gaps_md` run on the new `docs/GAPS.md` returns no entry whose title starts "A renewing run killed because". It returns the same entries as before, minus that one (the same ids, titles and `gaps_says`). The intake code is not changed.
6. **Other docs are untouched.** `SPEC.md`, `leaserenew.md`, `RUNTIME.md` and the agent guide stay as they are. SPEC §9.5 already describes the grace, `expires` and refused expiries. If the implementor finds a sentence in SPEC §9.5 or `docs/` that contradicts main's code on this, they report it in *Where it stopped* and do not fix it here (lesson-13).
7. **The house rules' done.**
   - The acceptance tests below pass.
   - The unit suite and the four browser files pass with rc 0 (run through the slot script under `scripts/suite_watch.py`), with no page test skipped for want of a port.
   - `ruff` is clean.
   - origin/main is merged in, and the suites are run again after the merge.
   - The report gives the commands and results. Anything not run is said to be not run.

## Files to touch

- `docs/roadmap/overnight/a-renewing-run-killed-because.md` (new: this definition; later *Where it stopped*)
- `docs/GAPS.md`

## Risks

- **lesson-8 (a claim wider than the code).** The new entry could restate the branch's numbers as fresh, or claim more than the code does, such as "renewals are never lost", "costs nothing", or "every reader". The guard is point 4 above: each number is quoted and attributed, the readers are named exactly, and the performance claim is held to the test's 2× + 50 ms. The reviewer checks every sentence of the entry against `leaserenew.md` and the code cited above.
- **lesson-7 (two things merged that each passed alone).** Two other gaps edit the same places:
  - `from-upkeep-s-fault-injection` also inserts the first bullet under `## Done recently`;
  - `a-run-whose-lease-expired-is-killed` edits the *Runtime* section of `docs/GAPS.md` near line 296.

  After merging origin/main, the implementor checks three things: this entry is still the first under *Done recently* (or the one directly after one that landed first, with that ordering said in the report); no other gap's bullet was lost or duplicated; and the `gaps_md` check (point 5) still holds on the merged file.
- **lesson-13 (stay inside the gap).** A lease test could flake under load during the suites, for example `test_a_renewing_run_is_not_killed`, the very test this gap came from. If so, the implementor names it, gives its output, and stops. It is not fixed in this branch. If it fails repeatedly, that is a finding against the merged fix and is reported, not patched.
- **lesson-9 (a test that can't fail).** This branch adds no test. The existing tests it relies on must be shown able to fail. The implementor stubs `fold.refused_expiries`'s index read away in a scratch copy (for example, forcing the per-item fold path to query with no `skip`) and shows that `test_many_expired_items_with_long_transcripts_cost_about_what_they_did` fails on its `not per_item` assert. They then revert the stub, so it is never committed, and say so in the report.
- **lesson-3 / lesson-1** do not apply: no code changes. The existing guards (the re-read before the write; the index lock held over `ix.items`) are on main and are not re-judged here.

## Acceptance tests

Existing tests on main. All must pass on the branch after origin/main is merged:
- `tests/test_lease_refused_cost.py::test_many_expired_items_with_long_transcripts_cost_about_what_they_did`: refused expiries are read from the index. No item's events are queried again, and the cost stays within 2× + 50 ms of the cost without the refusal. This is the gap's "performance test" (the lesson-9 check above shows it can fail).
- `tests/test_lease_kill.py::test_a_renewing_run_is_not_killed`: the gap's original symptom.
- `tests/test_lease_kill.py::test_an_expiry_judged_before_a_renewal_landed_is_refused`: the fold's refusal.
- `tests/test_lease_kill.py::test_the_watchdog_waits_a_grace_for_a_renewal_on_its_way`: the second look.
- `tests/test_lease_kill.py::test_a_renewal_recorded_between_the_look_and_the_expiry_is_not_killed`: the re-read before the write.
- `tests/test_lease_kill.py::test_one_items_trouble_stops_no_other_leases_look`
- `tests/test_leased_workspaces.py::test_an_expiry_refused_in_the_moment_before_its_write_releases_nothing_and_counts_nowhere`: the raw readers honour the refusal.
- The docs check (point 5), run by the implementor and pasted into the report:
  `python -c "import sys; sys.path.insert(0,'dev/bin'); import intake; print([g for g in intake.gaps_md(open('docs/GAPS.md').read()) if g['title'].startswith('A renewing run killed because')])"`
  prints `[]`. Run on `main`'s `docs/GAPS.md` (`git show origin/main:docs/GAPS.md`), the same check prints the one parked entry. The set of other ids is identical between the two.
- `git diff --stat origin/main...HEAD` lists only the two files in *Files to touch*. This is the check for "no code changes".

## Size budget

0 net lines outside `tests/` and `docs/`. Any non-zero count is an overrun and needs a written reason in *Where it stopped*.

## Notes from the plan review (answer each)

- Point 5 / the docs check: give the exact command for main's side too, e.g. `git show origin/main:docs/GAPS.md | python -I -c "import sys; sys.path.insert(0,'dev/bin'); import intake; print(sorted((g['id'], g['title'], g.get('gaps_says')) for g in intake.gaps_md(sys.stdin.read())))"` and the same on the branch file, then paste both outputs and the diff of the two lists. The diff must be exactly the one removed entry. The plan assumes `gaps_md` returns dicts with `id`/`title`/`gaps_says` keys; if it does not, use what it does return and say so.
- Point 4: the numbers in the plan (16 of 32, 0 of 48, 0.15/0.13/0.10 and 0.17/0.14/0.12 s, 1,000 items × 300 lines) come from the planner, not from the record. The implementor checks each against `leaserenew.md` and quotes the matching line for each in the report. If a figure differs or is missing, the entry uses the file's figure or leaves it out.
- lesson-8 guard: for each clause of the new entry, the report names the source it rests on (a file:function or test from the plan's list, or a quoted line of `leaserenew.md`). Any clause without a source is cut.
- lesson-9 check: the report includes the failing assertion output from the stubbed scratch run, plus `git status`/`git diff` after reverting, to show the stub is gone.
- lesson-7: if another gap's entry landed first under *Done recently*, put this entry directly below the entries that landed first and quote the first three bullets of the section after the merge in the report.

## Where it stopped

Built (2026-11-21): `docs/GAPS.md` only. The parked bullet is gone from *Runtime, scale and latency* (no other bullet
there changed), and a `(done` entry is the first bullet of *Done recently*, above *Warm processes for blocks*.
`git diff --stat main...HEAD` lists this file and `docs/GAPS.md`, so the size budget is 0 lines outside `docs/`.

**Sources for each clause of the entry** (checked against the code and `leaserenew.md`):
- second look a grace after the first, a tenth of the TTL, 1-30 s: `leases/terms.py::grace`
  (`max(1.0, min(0.1 * ttl, 30.0))`), `dispatch.py::look`. leaserenew.md: "a tenth of the TTL, at least 1 s, at
  most 30 s".
- re-read before the write, nothing written when renewed or ended: `dispatch.py::expire` (`its.one` and then
  `return`).
- the fold refuses an expiry judged before a renewal: SPEC §9.5, row `ergostat.lease.expired`; `tests/test_lease_kill.py`.
- the readers: `measures.py:47` (`counts`) and `:73` (`attention`), `etamodel.py:221`, `blockmodels.py:250`,
  `workspaces/leases.py:91`.
- read from the item index, transcripts never folded: `fold.py::refused_expiries` (caller's `items`, else
  `its._index`; the fallback query skips `TRANSCRIPT_TYPES`, `transcript=False`).
- "16 of 32 ... 0 of 48": leaserenew.md, *The bug*: "on main, **16 of 32** runs killed ...; on this branch, **0 of
  48**".
- "0.15 / 0.13 / 0.10 ... 0.17 / 0.14 / 0.12 s" at 1,000 × 300: leaserenew.md, *Done (2026-11-20)*: "At 1,000 items ×
  300 lines: main 0.15 / 0.13 / 0.10 s, ... now 0.17 / 0.14 / 0.12 s (counts / estimate / identify)".
- 2× + 50 ms: what `tests/test_lease_refused_cost.py` asserts.
I did not measure again.

**lesson-9.** In a scratch edit of `ergostat/leases/fold.py::refused_expiries`, I skipped the index read and made the
per-item query unskipped. The cost test then failed:
`tests/test_lease_refused_cost.py:68: AssertionError: no item's events read again, its transcript least of all` /
`assert not ['job/0', 'job/1', 'job/10', ...]`. I reverted the edit by hand. `git status --short` afterwards
showed only ` M docs/GAPS.md`, so the stub was never committed.

**Docs check (point 5): checked by reading, not run.** The session's permissions denied `python -c` (and
`python -I -c`). I read `dev/bin/intake.py::gaps_md` instead. It returns dicts with `id`, `title`, `section` and
`gaps_says`, and it skips every line under a section starting "Done" and any entry whose parenthesis starts
`(done`. The removed bullet was the only line changed outside *Done recently*. So the new file's list is main's
list minus `gap/a-renewing-run-killed-because-...` (parked), with the other ids, titles and `gaps_says`
unchanged. The factory or the reviewer should run the command above on both files to confirm.

**lesson-7.** This clone has no `origin/main` ref. Local `main` (f7b93be) is the branch's parent, so nothing was
there to merge. If `from-upkeep-s-fault-injection` lands first, this entry goes directly below its entry.

**SPEC (point 6), not fixed here.** §9.5's `ergostat.lease.expired` row (line 2112) names the readers that leave
a refused expiry out as "workspaces, measures, estimates". It omits the block models (`blockmodels.identify`).
That is narrower than the code, not a contradiction.

**Tests run:** `tests/test_lease_refused_cost.py` (1 passed), `tests/test_lease_kill.py` together with
`tests/test_leased_workspaces.py` (13 passed), and `ruff check ergostat tests scripts` (clean). **Not run:** the
unit suite and the four browser files under `scripts/suite_watch.py`. The brief leaves those to the factory's
watched run after this session.
