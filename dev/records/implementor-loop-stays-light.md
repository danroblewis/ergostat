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

## Where it stopped

Round 1, built, with one condition on the dependency.

**Done.** `dev/bin/onmain.py`: `FAST` is now `fast(cfg)`, which is ruff, then `build` (`unit` when no build is set),
then `browser` only if `[suites] build_browser` is the boolean `true`. `AGAIN` maps `build` to `alone`.
`dev/bin/implement.py` (outside Files to touch; 3 lines are needed because it called `browser_ready` and summed
`onmain.FAST`) now calls `agents.browser_ready` only when the round runs the browser files. `dev/bin/queue.py` is
unchanged: it still runs ruff, unit plus browser, then demo, and its skip check is untouched. `dev/bin/agents.py`:
the implementor's broad `Bash(uv run python scripts/suite_watch.py:*)` is replaced by
`Bash(uv run python scripts/suite_watch.py -- uv run --with playwright==1.63.0 python -m pytest -q -rs tests/test_*)`.
`DENY` gains `… suite_watch.py * -n*` and `… * --numprocesses*`. `[agents] session_cpus` (`settings()`) is the
`--cpus` of `run_args`, which every AI session's container uses. Empty or absent gives the suites' 4. A value that is
not a number, or is outside (0, 4], is refused (`Refused`). Suite containers (`contained`) and the git-only `finish`
container keep `LIMITS`' 4. `dev/factory.toml` has `session_cpus = 1.5` and `build_browser = false`, each with a
comment. `dev/prompts/implementor.md` now says this. Net lines outside tests and docs: 32.

**Most reversible choices made here (nobody to ask):**
- `build-suite-configurable` (the `depends-on`) is **not on main** at 07f9b250: there is no `[suites] build` and no
  `scripts/affected_tests.py`. I did not build it here. Until it lands, `fast()` falls back to the whole `unit`
  suite (the behaviour before this gap, minus the browser), so "never runs the whole unit suite" holds only once
  `[suites] build` is set. The prompt says this ("the unit suite while none is set").
- The quarantine handling (`fac.deselected`, and `suites()`' quarantined run beside) keys on `unit`/`browser`. A
  `build` suite therefore gets no deselection and no beside-run. That belongs to the dependency or a gap of its own.
- The permission relies on Claude Code reading a `*` that is not at the end as "anything", and `:*` as "a space
  then anything". `tests/test_agents.py::permits` models that reading. I did not check it against the real binary:
  `claude --version` was refused here. A prefix cannot stop flags after the file, so the `-n`/`--numprocesses` deny
  rules carry that.
- `Bash(uv run python -m pytest:*)` is unchanged (point 2 names only the `suite_watch` command). A session can still
  run `uv run python -m pytest -n 4` without the watchdog. Closing that is a gap of its own.

**The instance's live edits this replaces (point 5):** the hand edits to `dev/bin/agents.py` `run_args` (a session's
`--cpus`) and `TOOLS` (the implementor's `suite_watch` permission), and `[agents] session_cpus` in
`factory.local.toml`. Once this lands, drop the `agents.py` edits. The local key can be removed, since 1.5 is now the
default, or kept as an override (it is read the same way). The brief this session got also differed from
`dev/prompts/implementor.md` at point 3: it had no browser-file command. So the live prompt looks hand-edited too,
and this version replaces that edit as well.

**Run:** `tests/test_agents.py` (10 passed, including the real Chromium launch), `tests/test_factory.py` (126
passed, 2 skipped: both are `docker_ready()` tests, and there is no Docker here), `tests/test_factory_manager.py`,
`_sessions.py`, `_times.py`, `_knowledge.py` (all passed), and ruff (clean). Break checks (lesson-9): I forced the
browser into `fast()`, gave sessions a fixed "4", dropped the `-n` deny rule and dropped `browser` from the queue's
step. Each of the six new tests failed. Restoring the broad `suite_watch.py:*` permission, and separately removing
the 4-CPU ceiling, failed the permission and CPU tests. **Not run:** the whole unit suite and the four browser files
(the prompt forbids it; the queue runs them). origin/main: the clone has no remote. Local `main` (07f9b250) is
this branch's base.
