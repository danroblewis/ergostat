# review-as-a-dial-proposal: Proposal: how much review is done is a setting chosen from the value review is measured to give

depends-on: [review-at-the-feature-proposal]

The owner: "when we do review cycles, we get a certain type of value out of them, and we should know what value we get from review cycles and we should be able to manipulate how much review we do based on the value we get from it." Write `docs/proposals/review-as-a-dial.md`.

Settle:
1. What review is measured to give: findings by class, how many would have reached main, escapes found later, and the cost in time, rework and money. Use this factory's record and state what cannot be known yet.
2. A controlled experiment: a random share of low-risk items reviewed after merge instead of before, and how escapes are compared.
3. Review levels a model declares by risk (by path, size, kind or history): none, after merge, one blocking pass, full; and a controller that moves the level from measured escapes and cost.
4. What makes lower review safe: fast reverts, feature flags, staging, tests chosen by changed paths, programs that catch common findings before review.
5. How this composes with review at the feature (review-at-the-feature-proposal).
6. The build split.

Definition of done.
1. The proposal settles all six with numbers where it claims them.
2. The experiment is specified so it can run without the owner's hands.
3. Any question for the owner is one sentence.

Boundary (the owner, 2026-11-23). Anything general goes in ergostat's core as options a model declares, off unless declared, naming no gaps, software or factories. This factory is the first user and its choices live in its own model. Do not measure or change the live instance in the session: the coordinator applies changes.

## Where it stopped

Round 1: written. `docs/proposals/review-as-a-dial.md` settles the six points: what review gives, from the record
(the 123 curated findings by lesson and by harm class, 115 of them estimated to pass every queue suite, 0 gap merges
reverted in 454, the cost at the caps: 2.6 reviews and 1.6 fix rounds, $37 and about 90 minutes a gap), and what
cannot be known yet (1); a randomised trial of review after merge on two low-risk rules, its outcomes, the Gamma
bound and the decision rule (about 65 treated gaps with no harm escape), its own stopping rules, and no owner hands
(2); core `levels:` on a kind (placement by rules over fields, strictest by default, a hashed trial, bounded moves)
and a rule-rung controller that asks to lower and raises at once (3); reverts, flags, staging, tests by path and two
programs before review (4); one list with review-at-the-feature's light paths, the group as the trial's unit (5);
seven build steps, measurement first and the levels in shadow before the trial (6). Two owner questions, one sentence
each.

Decisions taken without the owner, each easy to undo:
- Numbers are from what this clone holds (git, the records, the lessons in the brief, dev/factory.toml, risk.py and
  escapes.py), since the boundary forbids measuring the live instance: money is ceilings, rounds are upper bounds
  from the records' text, the harm classes are my reading of each example, and the eligible share is a sample of the
  last 40 merges. The proposal names the live reading that replaces each.
- The open owner choices have the cautious default: an escape is worth $1,000 (keeps review), the push waits for an
  after-merge finding's fix or revert, and a lowering is asked in the inbox, never made alone.
- No code: the definition asks for the proposal only. 0 net lines outside tests, docs and dev.

Run here: ruff; tests/test_gaps_doc.py. Not run: the unit suite and the browser files (no code or test changed).

Round 2: the one finding answered (blocking; there were no others). The trial's mean stop, applied from the first
pass, was the prior's ($50 against S of about $18) and stopped every trial at once. Now the mean stop (section 2) and
the controller's mean raise (section 3d) apply only once `least` (30) items have closed windows, with a worked check
(no escape: $12.5 at n = 30 and falling, so the trial runs to its decision; one escape: $37.5, it stops). An unreadable
S is stated: not used before `least` treated windows, then the trial is held (share 0 for new placements, the severe
and balance stops still on, no decision), stopped if held past 7 days. The decision count is corrected to 66 (1353 /
(10 + n) < 18), and the round-1 "with one escape, after about 164" is dropped: the mean stop ends the trial first.
`check` also refuses a `least` or `probation` outside 1 to 1000, and build step 3's tests name the new cases. The
entry's title now matches the gap's, so the brief can find it.
Decision without the owner, easy to undo: a trial held for an unreadable S stops after 7 days rather than waiting
forever (a held trial is otherwise invisible exposure).

## Entry

section: The factory (ergostat on ergostat)
done: 2026-11-24 The proposal for review as a setting chosen from its measured value: docs/proposals/review-as-a-dial.md.

- **Proposal: how much review is done is a setting chosen from the value review is measured to give**
  (proposal written, `review-as-a-dial-proposal`; `docs/proposals/review-as-a-dial.md`): a kind may declare levels its items are placed
  on by rules (strictest when none matches), a hashed trial and a controller; the factory's levels are none, after,
  one and full, and a trial reviews a random share of low-risk gaps after merge to measure the harm review prevents.
  Left: building it (readings first, then the core levels, then the factory's), after the owner's two questions.
