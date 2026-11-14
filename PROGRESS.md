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
- 08:28 independent review (2 personas, 20 findings): fixed the bugs and most of the rest (see docs/cli-rounds.md round 11); git-hygiene demo (real git); block view signs by direction.
- 08:36 demo_check runs fresh copies; off-time per loop and a 'sample faster' hint (file-queue's cron archiver); README screenshots.
- 08:39 scale: readings bucketed in SQL, keep = 30d pruning; ergostat projects and the header switcher.
- 08:41 outlines per connected group; wiring labels on their edges; demos use @item; round 12 (a first agent from the guide).
- 08:53 second independent review (control engineer, agent developer): e = r − y; saturation vs sampling; hysteresis; strict bounds; backwards disturbances flagged, declared rates; series loops named; strict agent lines; by-hand runs; run history charts; --watch.
- 08:55 residuals must persist into the recent half of the window; DESIGN §5 rewritten; docs/ai-agents.md + examples/ai-controller.sh (tested with a fake claude); cron in words.
- 09:02 this-mac demo (real, read only); outlines merge when nothing intrudes; stocks without flows have no residual; scripts/demos.sh; demo_check notes residuals; round 14: the Supervisor for real (a correct change from the brief alone).
- 09:14 PNG export; round 15 (--json); code review (15 bugs, all fixed: guarded runs, timeouts, cron, finite numbers, lock on run.pid, pooled web, pruning keeps crossings...).
- 09:16 feedforward in the block view (H is the stock's own sensor); install as a uv tool verified end to end; docs/REPORT-2026-11-14.md; third review launched (designer, cold-start user).
- 09:24 third review (designer, cold start): 20 findings, most applied (round 17).
- 09:30 wiring packing and twin labels; phone layout; nested system outlines; all 9 demos pass demo_check.
- 09:32 page warns when not running; Supervisor brief: existing cron jobs, people's records; README brought up to date, screenshots retaken; second code review launched (on the last hour's changes).
- 09:42 second code review: 11 findings applied (web pool exit, lock races, reload lock hand-off, measured flow averaging, outlines, history defaults, cron at the clock change); on-call round 18: the valve row sums its last run. 79 tests.
- 10:01 round 20: plain crontab one-liners (bare numbers; check skips shell lines; cron badges say when); demo plain-crontab; cold-start review with own cron jobs launched.
- 10:07 round 21: ergostat snapshot (one offline HTML file); dark block labels; loop hints on Agents page; sawtooth is not saturation. 82 tests.
- 10:17 round 22 (fourth review, cold start with own cron jobs): a disturbance's agent (the load) drawn in control and wiring; early 'too soon to say why' hint; file order everywhere; event hides runs; twin labels by geometry; docs on names/units. demo_check also opens each snapshot offline. 83 tests.
- 10:22 tanks: a level meter with the setpoint's tick; labels follow each tick (a stale sensor label fixed); screenshots retaken; third code review launched (since 493879b).
- 10:29 round 23 (weekly review: TIME OFF column); round 24 (third code review, 8 of 9 applied). 85 tests.
- 10:38 round 25: sensor --forget-above/below (wrong readings set aside, recorded). 86 tests.
- 10:41 round 26: open_loop controllers (timers) drawn honestly in every view; plain-crontab's pruner is one. 87 tests.
- 10:43 round 27: run --service (launchd/systemd text). Guide explains open loops. Visual design review launched. 88 tests.
- 10:51 round 28 (visual review): lettered kind dots, legible first view + 'more beyond the edge', titled lean exports, setpoint on trends. 88 tests.
- 11:00 round 29: still-off loops re-announced at start; stop-killed runs not failures; block view grouped by system; screenshots retaken. 89 tests.
- 11:04 round 30: chains of loops fold at their joining pipes (auto when too wide). Fourth code review running.
- 11:12 rounds 31-32: first-run message; fourth code review (9/9 applied). 90 tests.
- 11:20 web snapshot shared across requests (1.5s): 0.6s → ms on big; README shows the folded chain.
- 11:26 round 33 (control engineer): feedback only from the stock; falling behind vs saturated; slowest stage; longest period that holds; outflow d; == hysteresis. 93 tests.
- 11:36 round 34: answer/recovery times per loop; pile-up hint for loops in series. 94 tests.
- 11:38 round 35: valve max per opening. Fifth cold-start review (design-doc SRE) running. 95 tests.
- 11:48 round 36 (fifth review): parse, export legend, service port/systemd/bootstrap, status alias. 96 tests.
- 11:56 unit mismatch warnings; run.log rotation; all 10 demos pass; fifth code review launched. 97 tests.
- 11:57 design SVG export (structure only).
- 12:03 round 38: fifth code review (9/9 applied); design SVG. 99 tests.
- 12:13 demo talking-scripts (parse, max, open loops); 11 demos.
- 12:25 round 39: parity review applied (panels, whole-window trends, suggestions open). 100 tests.
- 12:35 switcher refresh, panel room, residuals caption; 11 demos pass; sixth code review launched.
- 12:43 round 40: sixth code review (8/8). 101 tests.
- 12:53 valve max on labels; design picture in README; items FIRST; refused link.
- 12:54 wheel built and installed in a clean venv: blocks, snapshot, help, example all work.
