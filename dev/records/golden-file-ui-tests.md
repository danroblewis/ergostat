# golden-file-ui-tests: Page tests compare against saved reference outputs that a program regenerates

Golden-file tests: a page's rendered structure (or a screenshot) is saved as a reference file; the test compares against it, and an intended change regenerates the reference by a command instead of rewriting assertions by hand. Start with the dashboard's panels.
Done: 1. A regenerate command and a test that fails on an unintended change. 2. Diffs are readable in review.

The owner's decisions behind this (2026-11-23): more delivered work per AI dollar; tests exist for regressions; prefer program and rule checks over AI review; any path that checks less before merge needs a way to find and revert regressions on main. General parts go in ergostat's core as options a model declares (off unless declared, naming no gaps or software); this factory is the first user. Do not measure or change the live instance in the session: the coordinator applies changes.
