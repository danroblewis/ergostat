# implementors-can-clean-up: an implementor may run what its definition and its reviewer require

depends-on: []

Found 2026-11-21: at least 9 gaps parked with their work done or nearly done because the implementor's tool allowlist (`TOOLS` in `dev/bin/agents.py`) refused the command needed. It can `Write` a scratch file but has no `rm` or `git rm`, so a reviewer's "remove this file" can never be answered (external-event-logs, operating-states, redesign-rescored, light-theme, the-judge). It cannot run the watched suite the house rules require (`uv run python scripts/suite_watch.py ...`), which stalled lease-shutdown-race for 8 rounds and gap-size. Sessions run in a disposable container on their own clone, so these commands risk nothing outside it.

## Definition of done
- The implementor may run `git rm`, `git mv`, `git restore`, `rm` and `uv run python scripts/suite_watch.py`. The deny list (push, remote, config, stash, network) is unchanged.
- The implementor's prompt says: keep scratch files out of the repository (under `/tmp`), and if a command is refused, say which one in the result instead of working around it.
- Each session's refused tool calls are recorded on its session item and gap (`tool_denials`, from the Claude Code result's permission denials), with a measure and a goal of 0, so a missing permission shows up the first time.

## Files to touch
`dev/bin/agents.py`, `dev/bin/sessions.py`, `dev/prompts/implementor.md`, `dev/model/measures.yaml`, `tests/test_factory.py`.

## Risks
- lesson-3: a result with no denial field is unknown, never zero.

## Acceptance tests
- `tests/test_factory.py::test_the_implementor_may_remove_files_and_run_the_watched_suite`
- `tests/test_factory.py::test_the_deny_list_still_holds`
- `tests/test_factory.py::test_refused_tool_calls_are_recorded_on_the_session`

## Size budget
50 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Round 2's fast suites: `unit` came back failed, but the last 3000 characters of its log end mid-run at 60% with no
pytest summary, no failing test and no watchdog message. The run was cut off from outside (the suite container's 12 GB
limit, or a cancel); no test failed it. In this round's container, the test files near this branch's change pass one
file group at a time: tests/test_factory.py (62 passed, 2 skipped); test_factory_knowledge, _manager, _resources and
test_architecture (87 passed); test_factory_sessions, _times, test_claims, test_coherence and test_correspond (56
passed); test_backlog, test_agents_page and test_watchdog (16 passed, 1 skipped). The diff's tests start no process,
thread or container. I could not run the whole unit suite under the watchdog: this session runs main's allowlist, which
refuses `uv run python scripts/suite_watch.py ...`, the very permission this gap adds. Following this gap's own rule, I
did not work around the refusal. No code was changed in answer (the most reversible option). What is left: run `unit`
again under suite_watch, and if it fails with a test named, fix that.
