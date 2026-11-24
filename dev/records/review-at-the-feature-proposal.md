# review-at-the-feature-proposal: Proposal: review and full testing once per feature, not once per task

The owner: "we don't need to do reviews for every change. In Jira, a ticket may have multiple tasks. We may have several tasks that contribute to a feature branch, and only the feature branch needs to go through review and testing." Write `docs/proposals/review-at-the-feature.md`.

Settle:
1. A group of items (a feature, milestone or epic) with its own integration branch: tasks merge into it with light checks; the group is reviewed and fully tested once before it reaches main. As a general core option for any group relation, not only gaps.
2. What checks a task still gets on its way into the feature branch (lint, targeted tests, a build), and what only the feature gets.
3. Keeping a feature branch current with main, conflicts between features, and how long a feature may stay open.
4. Review effort and findings at the feature level against per-task review, using this factory's record: cost, rework, and what per-task review caught.
5. How this fits the merge queue, stacking and the dashboard's pipeline row.
6. When per-task review is still worth it (risky paths), so the choice is per group or per path.
7. The build split.

Definition of done.
1. The proposal settles all seven, with numbers from the record.
2. A worked example on three recent related gaps shows the time and review cost each way.
3. Any question for the owner is one sentence.

Boundary (the owner, 2026-11-23). Anything general goes in ergostat's core as options a model declares, off unless declared, naming no gaps, software or factories. This factory is the first user and its choices live in its own model. Do not measure or change the live instance in the session: the coordinator applies changes.
