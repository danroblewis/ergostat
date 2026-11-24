# lint-in-a-pre-commit-hook: Linting is fixed by a pre-commit hook and never tested or reviewed

The owner: "we don't really care about linters at all, this is AI generated code ... just do a pre-commit hook, we don't need to ever test for linting." Add a hook in every build session's checkout that formats and auto-fixes (`ruff format`, `ruff check --fix`) before each commit. Remove ruff from the merge queue's suites and from the builder's gates, and tell reviewers not to raise lint or style.
Done: 1. A test proves a commit with fixable lint lands formatted. 2. The queue no longer runs ruff, and a batch is never red for lint. 3. The reviewer prompt says lint and style are out of scope.

The owner's decisions behind this (2026-11-23): more delivered work per AI dollar; tests exist for regressions; prefer program and rule checks over AI review; any path that checks less before merge needs a way to find and revert regressions on main. General parts go in ergostat's core as options a model declares (off unless declared, naming no gaps or software); this factory is the first user. Do not measure or change the live instance in the session: the coordinator applies changes.
