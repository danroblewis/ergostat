# split-verified-2: a split parent waits in `joined` once every sub-gap merged, and a judge says whether the coverage was built (merged) or not (a new sub-gap, back to split)
depends-on: [split-verified-1]

## Definition of done
- **Joined, not merged.** In `ergostat.yaml` the gap kind has a state `joined` between `split` and `merged`. Its `join:` rule moves a split gap to `joined` (not `merged`) once every sub-gap is merged. `ergostat check` on the factory's model shows no new problem or `join-side-state` finding. Nothing else moves a split parent to `merged`.
- **The judge.** A new AI block (`plan.py join`, in `dev/model/knowledge.yaml` next to `split-watch`) takes a gap at `joined`. Its outcomes are `merged`, `split` and `parked`. It uses the plan reviewer's model and session cap (`opus`, 3.0 USD per session), and it waits (no session, gap left in `joined`) while `fac.may_spend` refuses. It runs in a read-only clone of main, with prompt `dev/prompts/join_judge.md`. Its brief holds four things:
  - the parent's entry;
  - its coverage (`run/plans/<parent-branch>.md`);
  - for each sub-gap, its definition (`run/defs/<branch>.md`) and its last review's verdict and findings;
  - the code on main.

  Any of these that cannot be read is shown as `(missing: why)`, never left out silently. The answer is one verdict: `covered`, or `short` with the coverage points not built, one `- ` line each. Its cost is recorded on the parent like every session's.
- **Covered.** The parent becomes `merged`, with the verdict, its reasons and the time judged recorded on it. It gets no merged lines of its own.
- **Short.** In this order:
  1. A new sub-gap is requested, open, with `parent:` the gap. Its entry is the parent's title plus the points not built. Its name is `<parent-branch>-join-<n>` (n = this short round), checked against `fac.SAFE` and against every existing gap id and branch.
  2. Those points are appended to the coverage file as `- point (by: that name)`.
  3. Only then does the parent move back to `split` (`gap.split`).

  The planner then plans the new sub-gap like any other. When it merges, the join moves the parent to `joined` again and the judge runs again, now seeing the new sub-gap too.
- **Bounded.** A named constant in `plan.py` allows at most 2 short rounds per parent. The third `short` parks the parent, listing the points still missing, instead of requesting another sub-gap.
- **Fails closed.** A verdict that cannot be read, an error in the session or a budget refusal never merges the parent. It stays in `joined`, and the run fails or waits like any other run under the block's lease. A missing coverage file still gets a judgment (from the entry and the sub-gaps), with the brief saying it is missing.
- `dev/README.md`'s planner paragraph describes `joined`, the judge, the short round and its cap.

## Relation to other work
- gap/split-verified-1: waits for it. The judge reads the coverage it saves (its commit is not yet on main in this clone).
- gap/split-verified-3: comes after this. Split quality is measured from the verdicts recorded here.
- gap/knowledge-queue: both touch `dev/model/knowledge.yaml` (here, only one added block). Merge origin/main and re-run the suites. Its test file `tests/test_factory_knowledge.py` is avoided.
- gap/timer-long-records-continued: avoids its files. `dev/bin/times.py` is not touched, so `joined` is not added to its waiting states.

## Files to touch
- `dev/bin/plan.py`
- `dev/prompts/join_judge.md` (new)
- `ergostat.yaml`
- `dev/model/knowledge.yaml`
- `dev/factory.toml`
- `dev/bin/agents.py`
- `dev/README.md`
- `tests/test_factory_join.py` (new)

## Risks
- lesson-1: the parent moved back to `split` before its new sub-gap exists lets the join fire again at once, because every old sub-gap is merged. The request must come first.
- lesson-3: an unreadable verdict, a failed session or a missing coverage file or definition could count as `covered`. Each must leave the parent unmerged or say `(missing)`.
- lesson-4: a judge that always says `short` would request sub-gaps for ever. The short rounds have a hard cap.
- lesson-5: a second short round reusing the first round's name would merge that sub-gap's old fields (its merged state, its review) into the new one. Each round's name must be new.

## Acceptance tests
- `tests/test_factory_join.py::test_a_split_whose_sub_gaps_all_merged_waits_in_joined`: the factory's compiled model moves a split gap to `joined`, not `merged`, when its two sub-gaps merge. The judge block takes `joined`.
- `tests/test_factory_join.py::test_a_covered_verdict_merges_the_parent`: with a stand-in session answering `covered`, the parent is `merged` with the verdict recorded. The saved brief has the coverage points, both sub-gaps' definitions and their last review findings.
- `tests/test_factory_join.py::test_a_short_verdict_requests_a_sub_gap_before_reopening_the_parent`: with `short`, the new sub-gap is open with the parent link and the missing points, and the coverage file names it. Its request's seq is lower than the parent's `gap.split`. The parent is not joined again until the new sub-gap merges.
- `tests/test_factory_join.py::test_a_second_short_round_names_a_new_sub_gap`: in the second round the new name differs from the first round's sub-gap, and no field from that sub-gap appears on the new one.
- `tests/test_factory_join.py::test_the_third_short_verdict_parks_the_parent`: after two short rounds the third parks the parent with the missing points, and no sub-gap is requested.
- `tests/test_factory_join.py::test_an_unreadable_verdict_or_failed_session_never_merges`: an answer with no verdict, a session that raises, and a budget refusal each leave the parent in `joined`. A missing coverage file gives a brief saying `(missing`.

## Size budget
150 net lines
size: M (confidence: medium)
