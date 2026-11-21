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
