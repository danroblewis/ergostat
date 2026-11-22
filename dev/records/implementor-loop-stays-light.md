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

Round 1, after the fast suites: `unit` failed with no test named, and no code was changed.

- **What the failure showed:** the tail ends at the outer `uv run`'s `Uninstalled 1 package / Installed 1 package`.
  It has no pytest line (not even xdist's worker line), no FAILED line, no summary and no `suite_watch` JSON line. So
  `suite_watch` itself stopped before pytest wrote anything. No test failed. This is the same silent stop as round 6
  of `implementors-can-run-the-four` and the four runs of `the-module-map-is-read-and`, both on main's code. The full
  log is outside this clone, so I could not read it.
- **Checked against this branch:** the branch changes which suites the round runs, a session's `--cpus` and one
  permission. Suite containers keep `LIMITS` (4 CPUs, 12g) and `fac.suite` is untouched. Before the session, `browser_ready`
  no longer runs, so the .venv resync on /work now happens in the unit container's outer `uv run`. That step finishes
  before pytest starts, and the tail shows it ending normally. So I found no path from this change to a run that
  dies before pytest's first line. The five new tests run in standin mode, with `echo` suites, no slot and no Docker.
  They kill nothing outside their own process groups.
- **Not fixed (lesson 13, the most reversible choice):** no test was named, so there was no test to fix. A guessed change
  to the suite runner or the watchdog is outside this definition. If the queue's unit run stops the same way, that
  belongs in a gap of its own, which would need the full log and the container's exit (OOM or killed from outside).
- **Run here:** `tests/test_agents.py` (10 passed, including the real Chromium launch).
  `tests/test_factory.py`, `_times.py`, `_manager.py` and `test_in_container.py` together, serially: 173 passed,
  2 skipped (Docker-only, as on main). Ruff is clean. **Not run:** the whole unit suite and the four browser files.
  The brief forbids that, and running several files at once in a loop was refused.

Round 2, answering the review's two findings (both blocking; there were no others).

- **Finding 1: a prefix plus a denylist let the glob, a directory and `-qn4` through.** Replaced with an allowlist.
  The new `scripts/named_tests.py` takes 1 to 3 arguments. Each must fully match `tests/test_<word>.py` with optional
  `::name` parts, and the file must exist. Anything else is refused with exit 2 before pytest starts: options of any
  form (`-n`, `-qn4`, `--numprocesses=…`, `-k`, `-p`), directories, `..`, and a glob that expanded to more than 3
  files. It then execs `python -m pytest -q -rs -p no:xdist -o addopts= <ids>`, so it runs serially. Clearing the
  ini's addopts means an edited `pyproject.toml` cannot add `-n` either. The implementor's browser permission is now
  `Bash(uv run python scripts/suite_watch.py -- uv run --with playwright==1.63.0 python scripts/named_tests.py:*)`.
  The two `-n`/`--numprocesses` DENY rules are removed because the script makes them redundant, so `DENY` is back to
  main's list.
- **Finding 2: `Bash(uv run python -m pytest:*)` was kept.** It is removed. The implementor's only way to run
  pytest is now `Bash(uv run python scripts/named_tests.py:*)` (unit files, without the watchdog, as before) or the
  watched browser form above. The prompt's two commands now name the script and say "at most three, no options; it
  runs pytest serially". `test_the_whole_suite_watch_command_is_not_the_implementors` now also refuses
  `uv run python -m pytest -q -n 8`, `… -q tests/test_agents.py`, a bare `uv run python -m pytest`, and pytest run
  directly under `suite_watch`. The new `test_named_tests_runs_named_files_only` refuses every test file (what
  `tests/test_*.py` expands to), the first 4 files, `tests`, `tests/`, `[file, tests]`, `-qn4`, `-n 4`, `-n4`,
  `--numprocesses=auto`, a literal glob, a missing file, `..`, a fixtures directory, `-p`, `-k`, an empty `::` and
  an argument with spaces. It also runs the script for real in a tmp project whose ini has `addopts = "-n 8 -x"`:
  the run passes serially, and `-n 8` gives exit 2 with no pytest output.
- **Break checks (lesson-9):** each of these was seen to fail its test. Putting `Bash(uv run python -m pytest:*)`
  back failed the permission test. Dropping the 3-file cap, and separately letting options through (the `ID` check
  replaced by "not starting with -"; `-qn4`, `-n4`, `--numprocesses=auto`, `..` and `::` were then accepted), failed
  the allowlist test. Dropping `-o addopts=` made the tmp run fail on `-n` from the ini.
- **What the code does not cover (the most reversible choice):** permission matching is modelled by `permits` in
  `tests/test_agents.py`, not checked against the real `claude` binary. The guard does not depend on that model any
  more, because the script refuses whatever a prefix lets through. The reviewer's prompt still names
  `uv run python -m pytest`, but its tools never allowed that. This gap does not change it.
- Overrun reason: the allowlist the review asked for is a new 30-line script, `scripts/named_tests.py` (16 code lines
  plus its docstring). With the round-1 changes in `dev/` (31 net lines, 7 of them prompt and config comments), the
  net count outside `tests/` and `docs/` is about 61, against 40. Counted outside `tests/`, `docs/` and `dev/`, as the
  brief counts, it is 30.
- **Run:** `tests/test_agents.py` (11 passed, including the Chromium launch), `tests/test_factory.py` (141 passed,
  2 skipped, both Docker-only), and `uv run ruff check ergostat tests scripts` (clean). `ruff check dev/bin` reports
  B023 in `plan.py` and E501 in `review.py`. Both files come from main and this branch does not touch them (lesson 13).
  **Not run:** the whole unit suite and the four browser files (the queue runs them). Refused:
  `timeout 300 uv run python scripts/named_tests.py tests/test_parallel_runs.py 2>&1 | tail -3`, and a `python3 -`
  heredoc that would have edited files (I made those edits with the edit tool).
