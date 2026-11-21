# modelreview: a reviewer in the modelling template, and its loop with the authors

Branch `modelreview`, from origin/main at fdf83b9.

## The gap

The owner: "I see that there is an improver. I don't see a reviewer... a reviewer could be added, and have a
feedback loop between the reviewer and the improver." Today the judge reviews a model change only by the numbers (a
replay on the record held out, or a redesign's scorecard). Nothing reads a change as a senior modeller would.

## Definition of done

The modelling template has a `reviewer`, an `ai` block there only with `ai: true` (and not with `review: {when:
off}`), on haiku by default, its calls charged against the template's daily cap (the redesigner's `daily`, shared).
It reads each change of the reviewed kinds (structure and redesign by default; equation when named) after the judge
passes it and before it is written or reaches the owner, deliberately disagreeable, through MODELLING-WELL.md's review
checklists (a plausible causal story; units and boundary; fitting noise, spurious stocks; one coherent change; the
behaviour it predicts). Its verdict, `pass`, `revise` or `reject`, each with specific findings, is an event on the
change's item (`ergostat.model-change.reviewed`). `reject` fails the change (so the memory holds it back); `revise`
sends it back to its author (an AI or person block; one ergostat's finders or a program made waits for the owner with
the findings), and that author's next proposal on the same parts carries the findings (`revising`, `review_asked`) and
is reviewed as the second round; a second `revise` is a reject. The authors' prompts (the improver's input, the
modeller's and the redesigner's prompts) carry the reviewer's recent verdicts on their own proposals. With the reviewer
on, the judge's policy writes a reviewed kind only after the reviewer's pass, and the inbox offers one to the owner only
after it; the owner may still accept it from the review queue. Measured: the reviewer's passes, revises and rejects,
and its misses (changes it passed that the prediction check later flagged for revert), as built-in measures.
Documented in SPEC §12e, the template's help and the agent guide.

## Acceptance tests

`tests/test_modelreview.py`:

- `test_the_reviewer_is_there_only_with_ai_and_tells_the_judge_what_it_reviews`
- `test_a_pass_lets_the_judge_write_and_the_verdict_is_an_event_on_the_item`
- `test_a_reject_fails_the_change_with_its_reasons`
- `test_a_revise_goes_back_to_its_author_and_the_next_proposal_carries_the_findings`
- `test_two_revises_on_one_change_mean_reject`
- `test_a_change_no_author_can_revise_waits_for_the_owner_with_the_findings`
- `test_the_authors_prompts_carry_the_reviewers_recent_verdicts`
- `test_with_the_reviewer_on_a_policy_auto_change_waits_for_its_pass`
- `test_a_change_for_the_owner_reaches_the_inbox_only_after_the_pass`
- `test_the_reviewer_stops_at_the_daily_cap`
- `test_an_answer_without_specific_reasons_records_nothing`
- `test_the_reviews_and_the_misses_are_measured`

All with a stand-in AI (no network). And the four suites with rc 0 (under `scripts/suite_watch.py`), `demo_check` on
the examples that use the modelling template.

## Size budget

450 net lines outside `tests/` and `docs/`.

## Where it stopped

Parked under the kill rule after the final re-review (2026-11-20). The gate's first findings 1 and 3, and the
reviewer's side of the cap, are fixed (38f6ddc). Left:

- **(1) A stale review still applies to a new version through time ordering.** `reviewer.py:43` compares
  `review.at >= verdict.at`. The judge stamps its verdicts with its pass's start time (`judge.py:323/346/356/407`). The
  reviewer stamps at record time, after a call that can take up to 600 s, outside `pr.locked`, and checks nothing again.
  A redesign carried and passed again while it is under review gets the old pass, and the judge writes code nobody
  reviewed. **Fix:** stamp the review with the verdict it read (its seq or `at`) and compare for equality; or record
  under `pr.locked` after checking again.
- **(2) The redesigner overshoots into the reviewer's quarter and past `daily`.** `redesigner.py:234` checks
  `cost >= budget`, then calls. **Fix:** check `cost + md.unsaid(...) > budget` before the call at :240.
- Note: `md.unsaid` ignores claude's own system prompt.

Tests needed: a change carried and passed again during a review; the redesigner at a cap of $0.01.

Continued (gap/modelreview-continued, round 1, 2026-11-20): (1) a review is stamped with what it read (`read`, a
fingerprint of the judge's verdict and the edit; `reviewer.seen`), held by equality, and recorded under `pr.locked`
only if the change is still the one it read (else `stale`, nothing recorded, read again). (2) The redesigner checks
`cost + md.unsaid(text) > budget` before each call. The note: `md.unsaid` now counts claude's own system prompt
(20,000 input tokens, `SYSTEM_IN`), so on haiku 5.5 one call's dearest is about $0.0105: the cap test runs at $0.02
(one call, not two) and at $0.01 (none) instead of the $0.01 named above, and `test_redesign`'s budget test moves from
$0.005 (which allowed the overshoot it now forbids) to $0.02. Tests:
`test_a_change_carried_and_passed_again_during_its_review_is_not_passed_by_it`,
`test_the_redesigner_never_calls_past_its_cap`.

Continued, round 2 (2026-11-20). (a) The shared daily cap was read once at the start of each block's run, so the
reviewer and the redesigner running at once could each spend most of the same remainder. Now each re-reads what is
left before every call (`room()`), and `redesign.held` checks the call's dearest against it and records a hold
(`ergostat.model.ai-held`, +usd) under `pr.locked`, then lets it go (-usd) once the real cost is charged; a call that
raises keeps its hold for the day (fails closed). `redesign.spent` counts the holds (the reviewer's own only in the
total, not in the redesigner's three quarters). The SPEC §12e *Cost* sentence says this. (b) GAPS no longer says the
reviewer is parked on the two fixed findings. (c) The earlier review's non-blocking finding (the cap test pinned
haiku's price, `0.008 < calls[0]`) is answered: the test now sets its budgets from the prompt's own dearest (1.5× and
0.5×), on any price table. Test: `test_the_reviewer_and_the_redesigner_running_at_once_stay_within_the_daily_cap`,
which charges the other block's spending inside each call; with the `room` wiring removed from `modelling.py` it fails
(the reviewer: no hold while its call runs; the redesigner: 3 calls instead of 1), checked by hand.
Size: 448 net lines outside tests, docs and dev against main (482 added, 34 removed), within the 450. Narrowing the
SPEC claim instead was the smaller option, but would have left a daily cap that does not fail closed, against the
owner's rule.

Continued, round 3 (2026-11-20), answering every finding of review/modelreview-1 and -2 still open:
(a) `reviewer.tries` counted `review-ran` events by `since=verdict.at`, the judge's pass-start stamp. Each such event
is now stamped `read: seen(x)` and counted by equality, so calls on an earlier version never count toward the new
one's three. (b) `reviewer.memory` (the authors' prompts and the improver's input) and `counts()['missed']` read the
raw `review` field; both now go through `review_of`, so a review of an earlier version made again under the same id
is not shown to its author, and a change the owner accepted under a pass that is out of date is not counted as the
reviewer's miss (only a pass of the version that was written). To keep a reject visible to `review_of` (its own
`failed` event replaces the judge's verdict, which `seen` stamps), the reviewer's failed verdict carries the judge's
verdict it read (`judged`), and `seen` reads that one. (c) review/modelreview-2's non-blocking finding (no test held
two holds at once): `test_two_holds_at_once_never_share_one_remainder` enters `redesign.held` from two threads, each
wanting 0.6 of 1.0, a barrier keeping both inside; exactly one fits. (review/modelreview-1's other non-blocking
finding, the pinned price, was answered in round 2.) `reviewer.asked` still reads the raw review: it counts the
revises of the last day on the author's parts, whatever became of them, which is the round count SPEC states.
Tests: `test_calls_on_an_earlier_version_do_not_count_toward_giving_up` (the change judged again inside a call),
`test_a_review_of_an_earlier_version_is_neither_shown_to_its_author_nor_counted_as_a_miss`,
`test_two_holds_at_once_never_share_one_remainder`; each fails with the code it guards put back as it was (`since=`
ordering; the raw `review` in memory, then in counts; the hold not recorded), checked by hand. SPEC §12e says the
tries, the memory and the misses are of the version as it stands. Size: 450 net lines (484 added, 34 removed).

## Where it stopped

Parked by the factory (review/modelreview-3, 2026-11-20 12:48).

Failed its gates 3 times (the kill rule). Blocking findings:
- docs/ADDING.md:237 (lesson-12): still says 'the `reviewer` block' although the block is `model-reviewer` (renamed in 38757b6). This was a review/modelreview-2 finding, and round 3's notes ('answering every finding of review/modelreview-1 and -2 still open') neither fix nor mention it. Name the block `model-reviewer`.
- docs/SPEC.md:3718-3720 and docs/GAPS.md:136-139 (lesson-8, lesson-12): they still say neither block 'starts a call that could cost more than is left', priced at 'the most it could write', 'worst-case cost', 'never pass it'. The figure is md.unsaid's estimate (prompt/3 + SYSTEM_IN 20,000 tokens in, MOST_OUT 16,000 out; ergostat/numbers/modeller.py:161-172), and md.call (modeller.py:144-158) sets no output-token or cost limit on claude, so a call can cost more than it and the cap can be passed. This is review/modelreview-2's finding, unanswered and unmentioned in round 3. Either say 'its estimated most' and drop 'never', or cap the call's output so the bound really holds, with a test.

Continued (gap/modelreview-resumed, round 1, 2026-11-21), answering both findings of review/modelreview-3 (it listed
no non-blocking ones):
- ADDING.md's Review paragraph now names the `model-reviewer` block. No other doc outside the roadmap calls it the
  `reviewer` block (searched).
- The cost claim is narrowed, not made true: SPEC §12e *Cost* now says neither block starts a call whose **estimated
  most** (`modeller.unsaid`: prompt/3 + 20,000 system tokens in, 16,000 out, at the model's price) is more than is
  left. It says the estimate is not a bound (`claude -p` is given no output limit), so the day can end a little past
  the cap, and the two blocks "do not both start calls on one remainder" (no longer "never both spend"). SPEC's
  redesign *runs stop* sentence, the GAPS entry (with that limit listed as Open) and the docstrings and comments of
  `modeller.unsaid`, `redesign.charge`, `redesign.held`, `reviewer.run` and `redesigner` say the same. I chose this
  over capping the output because it is the most reversible option: the docs change, the behaviour does not. A real
  cap would need a flag the stand-in AI understands, and `--max-budget-usd` in claude is checked between turns, so it
  does not bound a single turn either. A cap that actually holds is left for its own gap.
- Size: comments and docstrings only, so the net lines are unchanged (450).
- Tests: tests/test_modelreview.py (21 passed), tests/test_redesign.py (19 passed), ruff clean. No new test: the
  change only narrows the docs. The unit suite and the four browser files have not been run here; the factory runs
  them under suite_watch.py.
