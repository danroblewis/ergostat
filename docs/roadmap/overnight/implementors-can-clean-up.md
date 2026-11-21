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

Round 3: main (9acc11c2) merged in; its one conflict, tests/test_factory.py, was two independent additions at the
file's end (this branch's three acceptance tests, main's park-owns-resume tests), and both are kept. After the merge:
tests/test_factory.py 69 passed, 2 skipped; ruff clean; and `unit` under suite_watch.py, which this round's allowlist
allowed, rc 0 (2131 passed, 69 skipped, peak 294 threads, 1.6 GB). No code was changed this round. The four browser
files under suite_watch: rc 1, 2 failed, 222 passed. Run again alone (`--lf`), one passed and one failed again:
tests/test_diagram_rendering.py::test_a_loop_clicked_chooses_its_members_in_both_panes_and_the_split_is_pictured,
with `PermissionError: '/split-shots'`. Its screenshot folder is `ROOT.parent / "split-shots"` (test line 2485,
unless SPLIT_SHOTS is set), and in this container that is `/`, which cannot be written. This branch changes nothing
under ergostat/ or in that test, so it is unrelated (lesson-13) and was left alone. The other failure was a 30 s
Playwright wait for a "page" event during the parallel run, and it passed when run again alone. Refused this round: a
`timeout ... sh -c 'while ...; sleep'` wait for that run's output, which was not worked around.

Round 4: main (12d7deb2) merged in. Its one conflict, dev/model/measures.yaml, was two independent additions to the
auxiliaries: this branch's `tool-denials`, and main's `size-accuracy`, `size-accuracy-high` and `coverage-below-floor`.
All four are kept. Answers to round 3's review: (1) not run by the reviewer: they are run here and by the factory's
queue. (2) suite_watch.py runs any command given after `--`: this stays as built. Inside the disposable container,
pytest and `rm` already run arbitrary code, and the egress proxy still blocks the network. The deny list is a list of
tool names, and the definition keeps it as it was. No guard is claimed. (3) Reviewer sessions count toward
`tool-denials`: kept as designed. A reviewer refused a tool is a missing permission, and the measure is meant to show
it. (4) dev/README.md now names the implementor's new commands and `tool_denials`. After the merge:
tests/test_factory.py 76 passed, 2 skipped, and ruff is clean. Refused this round: `uv run python
scripts/suite_watch.py -- uv run python -m pytest ... > /tmp/unit.log 2>&1; echo rc=$?; tail` (the unit suite under
the watchdog, a compound command). It was not worked around, so the factory's fast suites after this session are the
unit and browser runs for this round.

Round 5: main (7c0e4a60) merged in. Its one conflict, tests/test_factory.py, was again two independent additions in
the same place: this branch's three acceptance tests, and main's `.gitattributes` merge tests
(test_two_gaps_editing_gaps_md_merge_cleanly, test_two_lessons_editing_review_lessons_merge_cleanly). Both are kept,
unchanged. After the merge: tests/test_factory.py 94 passed, 2 skipped, and ruff is clean. No code was changed this
round. Round 4's review had no blocking finding; its notes (reviewer sessions counted, `rm` reaching the session's own
clone, the files outside "Files to touch") were answered in round 4 and stay as built. Refused this round: a compound
`python3 - <<EOF ... ; git add ... && git commit` that resolved the conflict markers. It was not worked around in
the shell; the markers were removed with the editor and the commit made as separate commands. The unit suite and the
four browser files were not run here; they are the factory's fast suites after this session.

Round 6: the merge of main (7c0e4a60) was already committed (a92ff3e4), with no conflict markers left. The `unit`
failure handed to this round has a tail that ends just after uv rebuilt the package, before pytest printed anything.
No test is named, so the run was cut off from outside. Here, `unit` under suite_watch.py ran to the end with rc 1:
2235 passed, 69 skipped, 1 failed (peak 309 threads, 1.9 GB, nothing killed). The failure was
tests/test_warm.py::test_the_owners_stop_is_said_only_on_the_run_it_stopped, a 5 s wait for a warm worker to be
replaced, under -n 8. Run again alone, tests/test_warm.py passed (21 passed). This branch changes nothing under
ergostat/ and nothing that test reads: it builds its own project in tmp_path and never reads the repository's
ergostat.yaml. So it is unrelated (lesson-13), a load flake for its own gap, and was left alone. tests/test_factory.py:
94 passed, 2 skipped. No code was changed this round. The four browser files were not run here.
