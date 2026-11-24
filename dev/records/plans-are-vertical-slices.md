# plans-are-vertical-slices: Planners split work into thin end-to-end slices

Teach the planner and definition prompts to split a feature into vertical slices: each slice works end to end and lands on its own, instead of layers that only work together. Add an example from a recent feature.
Done: 1. The prompts say it, with the example. 2. A planner test on a fixture feature produces slices that each have their own acceptance test.

The owner's decisions behind this (2026-11-23): more delivered work per AI dollar; tests exist for regressions; prefer program and rule checks over AI review; any path that checks less before merge needs a way to find and revert regressions on main. General parts go in ergostat's core as options a model declares (off unless declared, naming no gaps or software); this factory is the first user. Do not measure or change the live instance in the session: the coordinator applies changes.
