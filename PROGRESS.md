# Progress

Owner's instruction (2026-11-14): CLI review rounds, then the CLI, then the app with a web UI that
renders good-looking control-system diagrams with automated layout; several demo repos; goal: good
diagrams for scheduled task agents that run basic programs, and the web UI shows what the CLI shows.
Work until 2pm.

## Decisions taken while the owner was away (say so when reporting)

- Python 3.12+, uv, standard library only at runtime; pytest and ruff for development.
- The model is `ergostat.toml` in the repository (tomllib, no dependency).
- State in `~/.ergostat/<project>/`: `events.db` and `measurements.db`, two SQLite files (two
  stores, per NOTES).
- Web: standard-library HTTP server, one page, ELK.js (vendored) for layout, SVG drawn by us.
- Default web port 8781.
- No approvals in v1: a valve's mode is recorded and shown; only programs that act are recorded.

## Log

- 07:10 rounds 2-4 written (docs/cli-rounds.md).
- 07:40 model, stores, runner, state, graph, CLI, web page with ELK layout; disk-space demo renders (plant left to right, feedback above, system hulls).
- 08:05 four demos (disk-space, backups, docs-fresh, deps) run and render; flow direction, hulls, wrap option, readable fit; measured flows integrated over time for residuals.
- 07:40 round 5 (real CLI on ops): items, tolerance; web polish; SQLite per-thread connections (a deadlock under load); rates over one recorded interval (in/out now balance).
