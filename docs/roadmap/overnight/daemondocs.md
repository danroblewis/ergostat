# daemondocs: how to use daemons and how to write them, for people and for agents

Branch `daemondocs`, from main at 4a4eda3 (daemons and daemons2 merged). Asked by the owner (2026-11-19): make sure
the human documentation and the agent documentation tell people and agents how to use daemons and how to write
these programs. The owner is not sure the YAML schema is the best yet, but the functionality is there. The owner's
rule: `docs/` is prose for people; what is for AI agents goes in the skill (`docs/skills/ergostat-author/`: SKILL.md
and the resource files it points to) and the agent guide (`docs/AGENT-GUIDE.md`), never generated as CLI output.

## Definition of done

**For people: `docs/DAEMONS.md`**, a how-to linked from `docs/RUNTIME.md` and the README. It says when a daemon is
worth it (process starts, kept sessions, batching) and when it is not; the shapes (an inline daemon for one sensor; a
named daemon shared by several sensors, one per outside service, with a kept session and batched queries; a push
daemon; a block daemon taking items under leases), each with its YAML and a complete, runnable program in Python,
and in shell where shell is sensible; the protocol in plain words; supervision (restarts and back-off, heartbeat,
standard-input back-pressure, give-up and revive with `ergostat block NAME --restart`, cancel on a lease's expiry);
testing a daemon by hand by piping JSON lines in, and what to look for; migrating existing `run:` sensors a group at
a time with readings compared before and after; failure isolation (a daemon per service); and the costs (per daemon,
wall time per item).

**For agents: `docs/skills/ergostat-author/daemons.md`**, linked from SKILL.md's read-first list and from a shorter
agent-guide section (§3e) that points to it. Patterns and rules: never block the standard-input reader; worker
threads; heartbeat; tag every line; strict `done`; honour `cancel`; fail hard; per-item env from the line, never the
process's; batching and kept sessions. A checklist an agent runs before calling a daemon done (check passes, a local
pipe test, readings match the old sensors). One compact, correct template per shape. Packaged with the skill in an
installed ergostat.

**Verified, so the docs cannot rot.** Every complete example in both files is marked with the file it is and the
model it belongs to; `tests/test_daemon_docs.py` extracts them, checks each model with `ergostat check`, pipes JSON
lines through each daemon by hand as the docs tell people to, and runs each model under the engine until readings
are recorded and items finished. Every other code block parses (YAML through ergostat's loader, Python compiled,
shell `sh -n`). `examples/daemon-demo/` (small: arrivals, a block daemon, a sensor daemon) is built from the docs'
own files, byte for byte, and passes `demo_check`. Each example is also run by hand under a short `ergostat run` in a
temporary copy (ports 8791-8797).

**GAPS:** an open entry, "daemon YAML schema review" (owner, 2026-11-19): the functionality landed, the schema may
change, with the alternatives worth considering.

## Acceptance tests

`tests/test_daemon_docs.py`:
- `test_every_code_block_in_the_daemon_docs_parses`
- `test_each_example_model_passes_check`
- `test_each_daemon_answers_lines_piped_by_hand`
- `test_each_example_records_readings_and_finishes_items_under_the_engine`
- `test_the_demo_is_built_from_the_docs_own_files`

Then the unit suite and the four browser files under `scripts/suite_watch.py` (one at a time, rc 0, no skips),
ruff, and `scripts/demo_check.py daemon-demo`.

## Budget

300 net lines outside `tests/` and `docs/` (the demo's files, the packaging line, a pointer in the shipped help).
