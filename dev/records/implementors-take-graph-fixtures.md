# implementors-take-graph-fixtures: the implementor may run the saved-diagram fixture command

depends-on: []

`gap/diagram-large-case-fixture` died under the kill rule after 21 sessions because its definition's first step, `uv run python -m tests.graph_fixtures` (it writes tests/fixtures/graphs/<model>-<view>.json from ergostat's own model, offline, with no server and nothing else reachable), is not in the implementor's allowed tools (`dev/bin/agents.py` `TOOLS["implementor"]`). The coordinator allowed it in the live instance on 2026-11-22; this puts it on main.

## Definition of done
1. `Bash(uv run python -m tests.graph_fixtures:*)` is in `TOOLS["implementor"]`, with a comment saying what it writes.
2. A test of the agents' tool lists says the implementor may run it and the reviewer may not.

## Files to touch
`dev/bin/agents.py`, its test.

## Size budget
2 net lines of code outside `tests/` and `docs/`.
