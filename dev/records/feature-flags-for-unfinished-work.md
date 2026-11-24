# feature-flags-for-unfinished-work: Work can land switched off behind a flag, so it skips the checks it does not affect

A general flag mechanism: a change declares a flag, its code paths are off by default, and tests for the flagged path run only when it is turned on. Useful where the owner says it really saves regression work (new pages, panels, isolated features), not for engine paths. Turning a flag on is its own gap with the full checks.
Done: 1. Tests: flagged-off code is unreachable by default; turning it on requires the full suite. 2. The guide says when a flag is worth it.

The owner's decisions behind this (2026-11-23): more delivered work per AI dollar; tests exist for regressions; prefer program and rule checks over AI review; any path that checks less before merge needs a way to find and revert regressions on main. General parts go in ergostat's core as options a model declares (off unless declared, naming no gaps or software); this factory is the first user. Do not measure or change the live instance in the session: the coordinator applies changes.
