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
