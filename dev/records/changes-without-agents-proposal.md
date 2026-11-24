# changes-without-agents-proposal: Proposal: changes made by programs, rules and models instead of AI sessions

The owner: "what if we had a system rigorous enough that we no longer need to have the AI agents write code? ... We want to work all workers up the ladder, and we want to decompose our workers and delegate and split." Write `docs/proposals/changes-without-agents.md`.

Settle:
1. The worker ladder (agent, then script, then rules, then a declarative model) as a general core idea: a block's worker can be replaced by a cheaper one once it proves equivalent, and how that equivalence is shown (replaying past items and their recorded outcomes, shadow runs, agreement rates).
2. Which kinds of change can become data instead of code (dashboards, panels, workflows, thresholds, saved queries), and what the core needs for that.
3. Program-made code: conflict resolution in generated and append-only files, codemods and templates for repeated shapes, generation from declarations (schemas, routes, docs, test scaffolds).
4. Mining the record: how to find recurring change shapes from past merged gaps and their diffs, and how much of the recent work they cover. Measure it on a copy of this factory's record and state the share.
5. Routing: how an item is sent to the cheapest worker able to do it, with the agent as the fallback.
6. The minimum time from request to main for each lane, with numbers.
7. The build split: the gaps that follow, smallest valuable first (the merge-conflict resolver is the likely first).

Definition of done.
1. The proposal settles all seven with numbers from the record where it claims them.
2. At least one shape is shown end to end on recorded examples: the program's output against what the agent produced.
3. Any question for the owner is one sentence.

Boundary (the owner, 2026-11-23). Anything general goes in ergostat's core as options a model declares, off unless declared, naming no gaps, software or factories. This factory is the first user and its choices live in its own model. Do not measure or change the live instance in the session: the coordinator applies changes.
