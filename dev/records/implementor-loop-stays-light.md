# implementor-loop-stays-light: an implementor's round never runs the browser suite or the whole unit suite, and each session is capped at a set CPU

depends-on: [build-suite-configurable]

The owner (2026-11-21): "We only want to run a minimum set of specific tests during the implementors loop, and we want to run the full suite on a combined merge queue", and "we need to cut those down per implementor". `implementors-can-run-the-four` (merged in 07f9b250, not yet live) went the other way: `dev/bin/onmain.py` has `FAST = ("ruff", "unit", "browser")`, so every round would also run the four browser files, after `agents.browser_ready` launches Chromium. Measured on the last 60 sessions: 10 used 52% of all session CPU-time, by running the whole suite themselves (`suite_watch -- pytest -n 4`), which the broad `Bash(uv run python scripts/suite_watch.py:*)` permission allows.

## Definition of done
1. The round's automatic step is ruff plus `[suites] build` only. The browser suite and `browser_ready` do not run in a round unless a setting turns them on (`[suites] build_browser = true`, default false, with a comment saying what it costs). The merge queue always runs them.
2. An implementor can still run one named browser file by hand with the command in its prompt, when its gap changes a page. The permission allows that command with named test files, and not `-n` or a run of the whole suite.
3. `[agents] session_cpus` in `dev/factory.toml`, default 1.5, is the `--cpus` of every AI session's container. Suite containers keep their 4. Empty or absent means the suite's limit, as before.
4. The prompt says the same as the code: which tests the implementor runs, and that the full suites run in the merge queue.
5. *Where it stopped* names the instance's live edits this replaces (`dev/bin/agents.py` run_args and TOOLS; `[agents] session_cpus` in `factory.local.toml`).

## Files to touch
`dev/bin/onmain.py`, `dev/bin/agents.py`, `dev/factory.toml`, `dev/prompts/implementor.md`, `tests/test_agents.py`, `tests/test_factory.py`.

## Risks
- A skipped page test must still fail in the merge queue: leave that check as it is.
- Permission patterns are prefixes: test that the whole-suite command is refused and the named-file command is allowed.

## Acceptance tests
- a round runs ruff and the build step, and no browser suite, by default
- `build_browser = true` brings the browser suite back into the round
- the merge queue runs unit, browser and demo in full either way
- a session's container gets `--cpus 1.5` and a suite container `--cpus 4`
- the whole-suite `suite_watch` command is not in the implementor's allowed tools

## Size budget
40 net lines of code outside `tests/` and `docs/`.
