# gap-size: every planned gap carries a size class (S/M/L/XL) with a confidence, and the factory measures how often the class matched the lines it merged

depends-on: []

## Definition of done

- **Size line.** The planner's definition holds a line `size: S|M|L|XL (confidence: low|medium|high)` in its `## Size budget` section. The classes count net lines outside `tests/` and `docs/`, and `dev/` code counts: S is 50 or fewer (a net removal counts as S), M is 51 to 150, L is 151 to 400 and XL is over 400. `dev/prompts/planner.md` states these bounds and asks for low confidence when the planner is unsure. `fac.STANDIN["planner"]` carries a size line too.
- **Bad size lines are sent back.** `plan.py` reads the line from every definition (the gap's own, or each sub-gap's) and records `size` and `size_confidence` on that gap's `gap.planned`. A definition whose size line is missing, has an unknown class or has an unknown confidence counts as a planner problem: it is sent back like the other `problems()`, never defaulted to a class.
- **A replan replaces the size.** A replanned gap's new `gap.planned` replaces `size` and `size_confidence`, so no old class survives under the reused id.
- **Merged lines are recorded at merge.** The queue counts the merge's net lines from `pre` to the merged head, outside `tests/` and `docs/` with `dev/` included, and records them as `merged_lines` on `gap.merged`. If that count cannot be read, the merge still stands: `merged_lines` is left out and `merged_lines_error` says why. A gap merged again records the newer count.
- **The measures.** `measure.py size-accuracy` gives, over the 14-day window, the share of merged gaps with a `size` and a `merged_lines` whose lines fall inside their class. `measure.py size-accuracy-high` gives the same for high-confidence gaps only. A merged gap with a size but no `merged_lines` is never counted as a hit. It is left out of the share and listed on stderr. When nothing in the window can be measured, both exit 1 with "no value yet", never 0.
- **The model shows them.** Both measures are auxiliaries in `dev/model/measures.yaml` with sensors, so they appear on the diagram and in the Items tab. No new page or panel is added.
- **What is not covered is said.** Gaps whose definitions the coordinator wrote, and split parents (which merge nothing themselves), get no size and are outside the measure. `dev/README.md` describes the classes and the two measures and says this plainly.

## Files to touch

`dev/bin/plan.py`, `dev/bin/fac.py`, `dev/bin/queue.py`, `dev/bin/measure.py`, `dev/prompts/planner.md`, `dev/model/measures.yaml`, `dev/README.md`, `tests/test_factory_knowledge.py`, `tests/test_factory.py`

## Risks

- **lesson-3:** a missing size line could default to a class, or a merge with no line count could count as a hit or as 0 lines. Either would flatter the measure.
- **lesson-5:** a replanned gap, or a gap continued and merged again, could keep its old `size` or `merged_lines` under the same id.
- **lesson-8:** "accuracy measured" could be claimed for a measure that counts unmeasured gaps, or reports 0 when nothing can be measured.

## Acceptance tests

- `tests/test_factory_knowledge.py::test_planned_gap_records_size_and_confidence`: a plan with `size: M (confidence: low)` records `size == "M"` and `size_confidence == "low"`. In a split, each sub-gap records its own class.
- `tests/test_factory_knowledge.py::test_plan_without_valid_size_is_sent_back`: a missing size line, a class `XXL`, or a confidence `sure` each give `gap.plan-sent-back` with a finding naming the size, and nothing is planned (lesson-3).
- `tests/test_factory_knowledge.py::test_replan_replaces_size`: a gap planned as S, sent back, then replanned as L reads L with the new confidence (lesson-5).
- `tests/test_factory.py::test_merge_records_merged_lines`: a branch adding 30 lines in `dev/bin/`, 20 in `ergostat/` and 100 in `tests/` merges with `merged_lines == 50`. A second merge of the same gap records its new count (lesson-5).
- `tests/test_factory.py::test_merge_stands_when_lines_unreadable`: when the line count raises (monkeypatched), `gap.merged` is still said, with no `merged_lines` and with a `merged_lines_error` (lesson-3).
- `tests/test_factory_knowledge.py::test_size_accuracy_counts_hits_over_measured`: four merged gaps in the window are recorded: S with 40 lines (a hit), M with 300 (a miss), XL with 900 (a hit) and L with no `merged_lines`. The measure reads 0.667, so the unmeasured gap is not a hit. A gap merged outside the window does not change it (lesson-8).
- `tests/test_factory_knowledge.py::test_size_accuracy_high_only_and_no_value`: `size-accuracy-high` counts only the high-confidence gaps. With no measurable gap, both measures exit 1 (lesson-3, lesson-8).

For each test, the implementor reports breaking the code it guards and watching it fail (lesson-9).

## Size budget

`size: M (confidence: medium)`

110 net lines (all in `dev/`. `fac.net_lines` counts 0 core lines for this branch).

## Notes from the plan review (answer each)

- Merged lines at merge: 'merged_lines is left out' on an unreadable count is wrong under a fold that merges fields. A gap merged again whose count fails keeps the earlier merge's merged_lines under the same id and is scored on stale lines (lesson-5 with lesson-3). The definition must say the newer gap.merged clears any earlier merged_lines (for example, written as null, or the fold resets both fields on every gap.merged), and the measure must treat a gap whose latest merge has merged_lines_error as unmeasured. Add an acceptance test: merge with a count, merge again with the count monkeypatched to raise; merged_lines is absent or null, the error is present, and size-accuracy leaves the gap out of the share and lists it on stderr. The current test_merge_stands_when_lines_unreadable only covers a first merge, so it cannot fail on this.
- Test the class bounds at the edges: 50->S, 51->M, 150->M, 151->L, 400->L, 401->XL, and a negative count->S. An off-by-one in the classifier passes the current 40/300/900 test.
- size-accuracy-high: say and test that it exits 1 with 'no value yet' when low-confidence gaps can be measured but no high-confidence gap can, not only when nothing can be measured.
- State which timestamp the 14-day window uses (the latest gap.merged of the gap) and test a gap first merged outside the window and merged again inside it.
- Assert that the unmeasured gap is listed on stderr in test_size_accuracy_counts_hits_over_measured; the definition promises it and no test checks it.
- Say whether a replan after a merge (a gap continued) clears merged_lines, so a new size is never scored against the old branch's lines before it merges again.

## Where it stopped

Built, round 1. Every item of the definition of done is in, with the deviations and answers below. Nobody could be
asked, so where the definition and the plan review's notes differ, the review's (stricter) reading was taken.

**Deviation from "merged_lines is left out".** Every `gap.merged` writes both fields: `merged_lines` (the count) with
`merged_lines_error: null`, or `merged_lines: null` with `merged_lines_error`. Under the record's replace fold, leaving
the field out would keep an earlier merge's count under the same id. A null `merged_lines` is "left out" of the
measure, never 0.

**The plan review's notes, answered:**
- Re-merge with a failing count: the newer `gap.merged` writes `merged_lines: null` and the error. The measure counts a
  gap only when `merged_lines` is an integer and there is no `merged_lines_error`. Test:
  `tests/test_factory.py::test_a_merge_again_whose_count_fails_keeps_no_old_count` (merge with 40 lines, merge again
  with the count raising: null, error present, `size-accuracy` exits 1 and names the gap on stderr).
- Class edges: 50->S, 51->M, 150->M, 151->L, 400->L, 401->XL, -30->S, 0->S are asserted in
  `test_size_accuracy_counts_hits_over_measured`.
- `size-accuracy-high` with only low-confidence gaps measurable (and a high one unmeasured) exits 1 with "no value yet":
  `test_size_accuracy_high_only_and_no_value`.
- The window is on the gap's latest merge (`merged_at`, replaced by each `gap.merged`). A gap first merged 20 days ago
  and merged again yesterday is counted, which the test asserts (0.667 -> 0.5).
- The unmeasured gap is asserted on stderr in `test_size_accuracy_counts_hits_over_measured`.
- A replan clears `merged_lines` and `merged_lines_error` (`gap.planned` writes both as null), so a new size is never
  scored against an earlier branch's lines. Asserted in `test_replan_replaces_size`. A split also clears a parent's
  earlier `size` and `size_confidence` (`gap.split`), so a gap first planned whole and then split is not measured.

**Beyond the listed tests.** In a split, one sub-gap's bad size line sends the whole plan back and no sub-gap is made.
A size line outside `## Size budget` is not taken.

**Known limit (said in dev/README.md).** The backlog groomer (`backlog.py`, `gap.groomed`) also writes a field named
`size` (S/M/L or hours), including on gaps already planned. The measure counts only gaps with a planner's
`size_confidence`, so a coordinator-written gap the groomer sized is never measured. But a groomer regrade after the
plan replaces the planner's class, and that regrade is then what is scored. A fix belongs in `backlog.py`: do not
write `size` on a gap that has `size_confidence`. That file is outside this gap's list, so it is left for its own gap.

**Lesson-9, each test broken and watched fail:**
- Not recording the size on `gap.planned` failed `test_planned_gap_records_size_and_confidence` and
  `test_replan_replaces_size`.
- Leaving size findings out of `problems()` failed all three cases of `test_plan_without_valid_size_is_sent_back`.
- Not clearing `merged_lines` on `gap.planned` failed `test_replan_replaces_size`.
- Counting core lines only (dev/ excluded) failed `test_merge_records_merged_lines` (20 != 50).
- Omitting `merged_lines` on a failed count failed `test_merge_stands_when_lines_unreadable` and
  `test_a_merge_again_whose_count_fails_keeps_no_old_count` (40 survived).
- Testing S with `< 50` failed the edge assertions.
- Scoring unmeasured gaps as misses failed both measure tests and the re-merge test.
- Dropping the high-only filter failed `test_size_accuracy_high_only_and_no_value`.
- Ignoring the window failed `test_size_accuracy_counts_hits_over_measured`.

**Size.** About 74 net lines in `dev/` (45 in `dev/bin`, plus the model, the prompt and README), and 0 core lines.
That is within the 110 budget and is class M.

**Not run here.** The whole unit suite and the browser files (the factory runs them under the watchdog). There is no
remote in this container, so origin/main could not be fetched. Local `main` has not moved past the branch base.

### Round 2

**Not fixed: the branch base (blocking; needs the coordinator).** `main` does not contain the backlog merge 2b101c6,
and this branch is built on it (merge base with `main`: 05c6dc9). Merging the branch as it stands would land all of
backlog with it. The fix the review asks for is to replay this gap's three commits onto `main`. This session's
permissions refused every command that does that: `git checkout --detach main`, `git cherry-pick` and
`git rebase --onto main 2b101c6 factory/gap-size`. I did not try to get around the refusal. I did not revert the
backlog merge on the branch either: a revert landed on main would make git treat backlog's commits as already
merged, and that would quietly drop them when backlog itself merges later. That is far harder to undo than a replay.
The replay, for someone allowed to run it (it has no backlog-only conflicts; the gap's files do not depend on
backlog):

    git rebase --onto main 2b101c6 factory/gap-size   # picks d3cd937, 860a76f, c7e0faf and the round-2 commit

The old head (1a5cd15) stays in the reflog. **Do not merge this branch until that replay is done.**

**The size finding (141 core lines against 110).** All 141 lines come from backlog, the same base problem. This
gap's own changes have 0 core lines (`ergostat/` is untouched) and about 80 net lines in `dev/`. The replay fixes this
too. No other reason for an overrun is claimed.

**The groomer collision, fixed in code whatever the base.** `gap.planned` now also writes `planned_size`, a field
that only the planner writes, and `gap.split` clears it. `size-accuracy` selects and scores on `planned_size` with
`size_confidence`, never on `size`. A groomer regrade of `size` (`gap.groomed`) after a plan therefore changes
nothing that is scored, and a gap with a `size` but no `planned_size` is never measured. `size` is still written
because the definition of done names it. README: the groomer paragraph is replaced by this rule. Tests:
`test_size_accuracy_counts_hits_over_measured` now regrades a planned S gap to L with `gap.groomed` and still reads
0.667. It also has a `size` with high confidence and no `planned_size`, which is not counted. The plan tests assert
`planned_size` on the whole gap, on each sub-gap, as cleared on a split parent, and as replaced on a replan.
Lesson-9: scoring `size` in place of `planned_size` failed the measure test (0.333 != 0.667). Selecting on `size`
failed it as well (the unplanned gap was let in).
**Left, outside this gap's files:** `solve.py`'s `POINTS` has no `XL`, so on a branch that also has backlog, a gap
the planner sized XL is ranked as M. The fix belongs to whichever of the two branches merges second (add `XL` to
`POINTS`, or have the solver read `planned_size`). On `main` without backlog the case does not arise.

**The non-blocking notes of round 1, answered.** The `except Exception` around the count was judged right by the
review and stays. The count runs under the queue lock: it is one `git diff --numstat` per merge, and it is kept there
because `pre` and the merged head are only certain under that lock. The README's long paragraph is split, with "Not
covered" in a paragraph of its own.

**Run here (round 2):** `tests/test_factory_knowledge.py` 29 passed, `tests/test_factory.py` 44 passed and 2 skipped
(both need Docker and the agent image). `ruff check ergostat tests scripts dev/bin` is clean. Not run: the whole unit
suite, the browser files, and a merge of origin/main (there is no remote here).

### After round 2: the factory's `unit` suite failed

The tail the factory gave shows only `bringing up nodes...` (twice) and a line of dots. It has no failing test, no
pytest summary, and not the JSON line `suite_watch.py` always prints at its end. So the run was most likely stopped
from outside (a timeout or a kill) rather than failed by an assertion. I could not reproduce a failure. This session
refused a whole-suite run, even a serial one. These files passed, one run at a time:
`test_factory_knowledge` (29), `test_factory` (44, 2 skipped for Docker), `test_backlog`, `test_architecture` and
`test_take_order` (26), `test_relations`, `test_eta`, `test_numbers`, `test_cli_fallback`, `test_leases`,
`test_spec_items`, `test_spec_compile`, `test_spec_schema` and `test_guide` (178), `test_intake`, `test_review`,
`test_factory_sessions`, `test_factory_resources`, `test_daemon_docs`, `test_model`, `test_spec_discover` and
`test_spec_auxiliaries` (117), and `test_leased_workspaces`, `test_lease_kill`, `test_lease_refused_cost`,
`test_spec_engine`, `test_spec_structure`, `test_spec_systems`, `test_spec_blocks`, `test_item_systems` and
`test_process` (79). Ruff is clean. With no failing test named, no code was changed: guessing at a fix would be less
reversible than saying so. **Left:** rerun `unit` and read its full output, not only the tail. If a test fails, it
is either this gap's (fix it here) or backlog's, which this branch still carries (see "Branch base" above: the replay
onto `main` is still needed and still blocks the merge).

### Round 3

**Main merged (8eb0fc0, pipeline-manager and relations-as-of).** The four conflicts were each between main and
backlog's lines, not this gap's. Both sides were kept: the `groomer` and the `pipeline_manager` roles side by side
in `agents.py` (TIMEOUTS, TOOLS), `fac.STANDIN` and `factory.toml`; in `ergostat.yaml`, backlog's Items columns
(rank, value, size) with a `gap.closed` comment naming both writers, and `messages: done:` with main's `situation`
added. `parked` was left out of `done` because backlog moved it to `paused`, which main's line predates.

**Still not fixed: the branch base (blocking; needs the coordinator).** After this merge, `main` still does not
contain 2b101c6 (`git merge-base --is-ancestor 2b101c6 8eb0fc06` is false), and `git diff 8eb0fc06...HEAD` is still
41 files and about 1,870 lines, almost all backlog's. This session is allowed only `git add`, `commit`, `merge`,
`status`, `diff`, `log` and `show`, so the replay cannot be done here, and I did not try to get around that. For
someone allowed to run it, the replay keeps this merge's resolutions irrelevant (they are backlog's lines):

    git rebase --onto origin/main 2b101c6 factory/gap-size   # the gap's own commits: d3cd937, 860a76f, c7e0faf,
                                                             # 39d6fb8, 093f942 and this round's note

Conflicts there are only expected in `fac.STANDIN` (main's `pipeline_manager` beside the size line). **Do not merge
this branch until that replay is done.** The 141 core lines the size gate counts are backlog's, as before. This
gap's own changes are still 0 core lines and about 80 in `dev/`.

**A failure on the merged tree that is backlog's, not this gap's (lesson-7, lesson-13).**
`tests/test_relations_asof.py::test_an_item_of_no_kind_changed_since_has_no_links_and_the_rest_answers` (both
parametrizations) fails here: main's new test expects precedence status `ready`, and backlog's
`ergostat/precedence.py` renamed it `unblocked`. This gap does not touch `precedence.py`. The replay removes
backlog from this branch and with it the failure. Whoever merges backlog after relations-as-of must reconcile the
name. It is not fixed here.

**Run here (round 3, on the merged tree):** `test_factory_knowledge` 29 passed; `test_factory` 44 passed, 2 skipped
(Docker); `test_factory_manager` 18 passed; `test_backlog` with `test_take_order` 17 passed; `test_model`,
`test_factory_sessions` and `test_daemon_docs` 56 passed; `test_eta`, `test_relations_asof` and `test_spec_items`:
26 passed, 2 failed (the two above). `ruff check ergostat tests scripts dev/bin` is clean. Not run: the whole unit
suite and the browser files.

### Round 4 (the factory's `unit` failures after round 3)

**Main's merge was already committed** (b6c58727); there was nothing left to resolve.

**The replay is still not done (blocking; needs the coordinator).** `git rebase --onto main 2b101c6 factory/gap-size`
was refused in this session again, and I did not try to get around that. The branch still carries backlog (2b101c6),
and everything said about this in rounds 2 and 3 still holds. **Do not merge until the replay is done.**

**`test_relations_asof.py::test_an_item_of_no_kind_changed_since_has_no_links_and_the_rest_answers` (both
modes): fixed by reconciling the merge.** Main's new test expects the precedence status `ready`. Backlog (which this
branch carries) renamed that status to `unblocked`. On this tree, `ergostat/precedence.py`, SPEC ("*unblocked* ...
not 'ready', which is often a state's name"), `relations.js`, `test_relations.py` and `test_items_page.py` all use
`unblocked`. Putting `ready` back in the code would break all of them. So the two expected strings in main's test
are now `unblocked`: a merge resolution, not a changed bound. After the replay (with no backlog), main's version
of the test is right as it stands. Then this change is not needed, and whoever merges backlog makes the same
change. Lesson-9: the test failed on this tree before the change, and it passes after.

**`test_leases.py::test_the_watchdog_renews_from_what_the_holder_does_elsewhere`: not fixed here (lesson-10,
lesson-13).** Neither this gap nor backlog touches the test or the code it guards: `git diff main HEAD` is empty
for `tests/test_leases.py`, and backlog's change to `ergostat/leases/dispatch.py` and `ready.py` is the take order
only, not the watchdog. The test's lease has a 1 s TTL, and the holder renews it only through `ergostat event --add`
calls, a fresh Python process each, 0.4 s apart. Under a whole suite at `-n` with 119 processes, a cold start of
more than about 1 s lets the lease lapse. The test is timing-bound on `main` too. Here it passes alone (1 passed in
3.4 s), and so does all of `test_leases.py` (20 passed). If it is a real race in the watchdog, it is main's and
belongs in its own gap.

**Run here (round 4):** `test_relations_asof` 9 passed; `test_leases` 20 passed. `ruff check ergostat tests scripts
dev/bin` is clean. Not run: the whole unit suite and the browser files.

## Where it stopped

Parked by the factory (review/gap-size-3, 2026-11-20 18:01).

Done: the gap's own work (plan.py size_of/problems, the size reset on replan and split, queue.py merged_lines/merged_lines_error written on every gap.merged, measure.py size-accuracy and size-accuracy-high with unmeasured gaps left out and named on stderr, the planner prompt, measures.yaml, the README, and the acceptance tests). Its code was found sound in rounds 2-4. Left: the branch is built on top of the unmerged backlog merge 2b101c6, so it cannot reach main without landing backlog unreviewed. Implementor sessions were refused the replay in every round, so further fix rounds cannot finish it. Someone allowed to rewrite the branch must replay only the gap's commits onto origin/main (d3cd937, 860a76f, c7e0faf, 39d6fb8, 093f942, the gap-size part of 1e16402's notes; not the tests/test_relations_asof.py change and not merges b6c5872 and 1a5cd15), for example `git rebase --onto origin/main 2b101c6 factory/gap-size` and drop the merges and the relations-as-of change. Then confirm `git diff origin/main...HEAD` touches only the definition's 'Files to touch' (plus docs/roadmap/overnight/gap-size.md), and run the acceptance tests, the unit suite, the browser files and ruff again before the branch is reviewed.

### Resumed (gap/gap-size-resumed, round 1)

**The branch base is settled by main, not by a replay.** Main (0ecf249c) now holds backlog's work, so merging it in
made the carried backlog commits main's (the owner's rule: continued, not rebased; no history rewritten).
`git diff 0ecf249c...HEAD` now touches only `dev/README.md`, `dev/bin/fac.py`, `measure.py`, `plan.py`, `queue.py`,
`dev/model/measures.yaml`, `dev/prompts/planner.md`, this file, `tests/test_factory.py` and
`tests/test_factory_knowledge.py`: all in the definition's list. The earlier `tests/test_relations_asof.py` change
dropped out: main's version and the branch's now agree.

**Main's merge, resolved (six conflicts).**
- `agents.py`, `ergostat.yaml`: main's side (it adds nothing of this gap's).
- `fac.STANDIN["planner"]`: main's longer stand-in (Files to touch, Risks) with this gap's size line kept.
- `planner.md`: main's new "The format" section. The size line is now in its `## Size budget` bullet.
- `plan.py`: main no longer says `gap.planned`. A lint-clean plan goes straight to `gap.defined` via `define()`.
  The size fields (`size`, `size_confidence`, `planned_size`, and `merged_lines`/`merged_lines_error` cleared to null)
  are now passed through `define()` for the whole gap and for each sub-gap. The split parent's reset is unchanged.
  "Records `size` on `gap.planned`" in the definition now reads "on `gap.defined`": main renamed the event, and
  the fields and their rules are the same.
- `queue.py`: main lands batches of gaps. If the count ran from the batch's `pre` to its head, every gap of a batch
  would get the whole batch's lines. So `land()` now counts each gap's own merge, from main just before it to its
  merge commit, in the last try that landed it (a gap merged again onto other heads after a bisection gets that
  merge's count). A gap that failed the queue gets no count. The rule is the same as before: both fields are always
  written, and a count that raises gives null and the error.

**Tests changed by the merge.** `test_planned_gap_records_size_and_confidence` and `test_replan_replaces_size` expect
`gap.defined`. In main, a gap with a definition is never planned again (plan.py takes the existing definition as
the coordinator's). So the replan test now removes the earlier definition and sends the gap back to replan. It
asserts L/low, `replanned`, and `merged_lines` cleared. The "nothing planned" check also covers `run/defs/`.
Added in main's batch tests: in a green batch of 3 each gap reads `merged_lines == 1` (not 3), and in the bisected
batch p, q, s each read 1 and the failed r has no count.

**Lesson-9 (this round):** dropping `**sized` from the gap's `define()` failed both plan tests. Counting from the
batch's `pre` failed both batch tests (3 != 1).

**Size:** 102 insertions and 15 deletions in `dev/` against main (about 87 net), and 0 core lines. Within the 110
budget, class M.

**Run here:** `tests/test_factory_knowledge.py` 41 passed; `tests/test_factory.py` 60 passed, 2 skipped (Docker).
`ruff check ergostat tests scripts dev/bin` is clean. Not run (the factory runs them under the watchdog): the whole
unit suite and the four browser files.

**After this round: the factory's `unit` suite failed, with no test named.** The tail shows `bringing up nodes...`
twice, then one line of dots. It has no `F`, no pytest summary, and not the JSON line `suite_watch.py` prints at its
end, so the run was most likely stopped from outside (a timeout or a kill), not failed by an assertion. The same tail
was seen once before on this branch (see "After round 2"). The merge of main was already committed (f891cffa), and
nothing was left to resolve. I could not reproduce a failure. This session refused a whole-suite run, even a serial
one, and I did not try to get around that. Every file that reads `dev/` or might be affected passed, run serially:
`test_factory` (60, 2 skipped for Docker), `test_factory_knowledge` (41), `test_factory_manager`, `test_backlog`,
`test_take_order`, `test_factory_resources` and `test_factory_sessions` (48), `test_messages`, `test_gated_actions`,
`test_intent`, `test_eta`, `test_daemon_docs`, `test_model` and `test_architecture` (128), `test_in_container`,
`test_recipes`, `test_run_costs`, `test_workspaces`, `test_leased_workspaces`, `test_ticket_factory_daemons`,
`test_spec_auxiliaries`, `test_cli_fallback` and `test_relations_asof` (106), and `test_leases`, `test_daemons`,
`test_intake` and `test_review` (92). Ruff is clean. No failing test was named, so I changed no code: a guessed fix
would be less reversible than this note. **Left:** rerun `unit` and keep its full output, or at least its summary,
not only the head. If a test then fails, fix it here only if it touches this gap's files (lesson-13).
