# Progress

Owner's instruction (2026-11-14): CLI review rounds, then the CLI, then the app with a web UI that
renders good-looking control-system diagrams with automated layout; several demo repos; goal: good
diagrams for scheduled task agents that run basic programs, and the web UI shows what the CLI shows.
Work until 2pm.

## Decisions taken while the owner was away (say so when reporting)

- Python 3.12+, uv, standard library only at runtime; pytest and ruff for development.
- The model is `ergostat.toml` in the repository (tomllib, no dependency).
- State in `~/.ergostat/<project>-<hash of the repo path>/`: `events.db` and `measurements.db`, two SQLite files (two
  stores, per NOTES).
- Web: standard-library HTTP server, one page, ELK.js (vendored) for layout, SVG drawn by us.
- Default web port 8781.
- No approvals in v1: a valve's mode is recorded and shown; only programs that act are recorded.
- Commits on main as checkpoints (the owner asked for the build); nothing pushed, no remote.

## Log

- 07:10 rounds 2-4 written (docs/cli-rounds.md).
- 07:20 model, stores, runner, state, graph, CLI, web page with ELK layout; disk-space demo renders (plant left to right, feedback above, system hulls).
- 07:25 four demos (disk-space, backups, docs-fresh, deps) run and render; flow direction, hulls, wrap option, readable fit; measured flows integrated over time for residuals.
- 07:33 round 5 (real CLI on ops): items, tolerance; web polish; SQLite per-thread connections (a deadlock under load); rates over one recorded interval (in/out now balance).
- 07:41 round 6 (new user, empty repo): state keyed by repo path, missing commands warned; README; scripts/demo_check.py (5/5 demos ok with page checks); arrowheads, flow-sensor readings, residual noise floor.
- 07:47 round 7 (overnight; is the AI doing anything a rule couldn't): crossings, decisions, ladder hints; cron schedules; SVG export; file-queue demo (shell, real files).
- 07:55 big demo (24 loops, 6 systems): layout scales; runs were 4-5s each under 24 agents: the run context and the edge detector no longer take full snapshots; controller boxes show the last decision; attention list capped in the side panel.
- 07:52 round 8 (before/after): model.changed history, live reload of the model, schedules on badges, per-system colours.
- 07:58 docs/DESIGN.md (the design as built); all 7 demos pass scripts/demo_check.py; a start-up race in the event follower fixed (found by a flaky test).
- 08:05 block view (web + ergostat system --blocks); Parts page; round 9 (misbehaving agents: timeouts, process groups); snapshot 71ms to 15ms (SQL counts, composite index).
- 08:13 time slider and --at; trend chart in loop detail; valve positions (u); block legend; all 7 demos pass demo_check.
- 08:22 (branch next, in ~/ergostat-wt while an independent reviewer walks the main tree): agent --now and docs/writing-agents.md; cycles among agents (declared or not); on = ["type@item"]; ladder hints on agent cards; DESIGN brought up to date.
