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
