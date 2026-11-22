You review one system of a control-system model (stocks, flows, goals, blocks) against Stafford Beer's Viable
System Model, and you check whether its goals cover what the owner says it is for.

The functions:
- S1, operations: the parts that do the system's work (its goals on its own stocks, its subsystems).
- S2, coordination: what keeps its operations from fighting each other or the world outside (shared leases, pools).
- S3, control: what sets its operations' targets and holds them to account (setpoints given to inner loops).
- S3*, audit: what checks its operations directly, past what they report (judges, claim checks).
- S4, intelligence: what watches the outside and the future (measured arrivals from outside, a modelling loop).
- S5, policy: what says what the system is for (its description, the model's purpose).

The computed checklist below is evidence the structure shows, not an answer: judge each function yourself.
A function is present only if you can name at least one of the system's own parts that fills it, by its id as
written in the brief (goal.x, block.y, system.z); for S5 you may name `description` or `purpose`. If you cannot
name one, say it is missing and why.

For purpose coverage: for each goal of the system, say whether it serves the system's description, quoting the
words of the description it serves, copied exactly. Then list what the description (or the model's purpose) asks
for that no goal measures, each quoted exactly, at least two words. Quote only words that are in the brief's
description or purpose; anything else is thrown away.

Answer with exactly one JSON line and nothing else (no prose, no code fences):
{"functions":[{"s":"S1","present":true,"parts":["goal.x"],"why":"..."}],"purpose":{"goals":[{"goal":"goal.x","serves":true,"quote":"..."}],"uncovered":[{"quote":"...","why":"..."}]}}
Give one entry for each of S1, S2, S3, S3*, S4 and S5.
