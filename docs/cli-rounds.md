# CLI review rounds

Pretend-user walk-throughs of the command line. Each round: a person, what they want, the commands
they type, and what broke. Findings are applied to the CLI before the next round.

Round 1 (four scenarios: first session, a loop off its setpoint, moving a role down the ladder, a
residual becoming a disturbance) is summarised in the findings list at the end.

## Round 2: scheduled programs

**Who:** an SRE with three cron jobs they already trust (a backup, a disk cleanup, a docs check).
They want to see them as a control system, not as a crontab.

```
$ cd ~/ops && ergostat
  no ergostat.toml here. Describe your system with `ergostat chat`, or write ergostat.toml.
$ ergostat chat
  > I have a nightly backup script, a disk cleanup, and a docs-age check. Model them.
  (the Supervisor writes ergostat.toml: stocks, flows, sensors, controllers, valves, agents)
$ ergostat check                       # does the file describe a closed system?
  ok   3 stocks · 6 flows · 3 sensors · 3 controllers · 3 valves · 3 agents
  warn loop docs-fresh: no sensor measures stale-docs, so the loop cannot close
$ ergostat run                         # starts in the background; says where its log is
$ ergostat
  running · 3 loops: 2 holding, 1 open (docs-fresh: no sensor)
```

**Findings:**
- **`check` is needed.** "Does what I described make a closed loop?" is the first question after
  writing the file, before anything runs. It is a question about the model, so it belongs to the
  model, but it must be reachable in one word. `ergostat check`.
- **A loop's status has three values, not two**: holding (error within tolerance), off (error
  outside it), open (the loop cannot close: a missing sensor, controller or valve). Open is a
  design problem; off is an operating one.
- Bare `ergostat` with no file must say what to do, not fail.

## Round 3: a scheduled program that does both

**Who:** the same SRE. The disk cleanup script measures usage *and* deletes old files: one program
fills two roles, sensor and valve, and arguably the controller too (it decides how much to delete).

```
$ ergostat agent
  AGENT          KIND      RUNS      LAST      FILLS
  disk-cleaner   program   every 5m  12s ago   sensor disk-usage · controller disk-under-80 · valve delete-old-files
$ ergostat loop disk-under-80
  disk-under-80   holds disk-used ≤ 80%   now 71%   error -9%   holding
    sensor     disk-usage        disk-cleaner (program)   read 12s ago: 71%
    controller disk-under-80     disk-cleaner (program)   last decision: nothing to do
    valve      delete-old-files  disk-cleaner (program)   last opened 2h ago: 3.1 GB
```

**Findings:**
- One agent filling three roles is normal for a program, and the `FILLS` column shows it. Good.
- `loop NAME` showing each part with its agent and last activity answered everything. The part
  topics were not needed.
- The program needs a way to say which role each line of its output is for: a reading is a
  sensor's, an opening is a valve's, a decision is a controller's. The output protocol names the
  part: `{"sensor": "disk-usage", "value": 71}`, `{"valve": "delete-old-files", "amount": 3.1}`,
  `{"controller": "disk-under-80", "decision": "nothing to do"}`.

## Round 4: reading the picture

**Who:** the SRE's manager, who never uses the terminal. They open the web page.

- The first thing they want is the diagram, not a table. The web app opens on the system diagram.
- They want to know, without reading, which loops are fine: colour on the loop, and a legend.
- Clicking a part should show what `ergostat <topic> <name>` shows.
- They do not know what a valve is. Every shape needs a short label, and the legend says what each
  shape means in one line.

## Findings, all rounds

1. Bare `ergostat` is the status; with no file, it says how to start.
2. `ergostat check` checks the model: unknown references, loops that cannot close.
3. `run` runs in the background (`run --foreground` to stay attached; `run --stop`).
4. Loop status: holding, off, open.
5. `loop NAME` shows every part along the loop, with its agent and last activity.
6. Part topics (stock, flow, valve, sensor, controller, disturbance) stay, for drilling in, but
   are not the main path; `--help` lists them last.
7. `measurement` folds into `sensor NAME`; `channel` waits for a scenario that needs it.
8. `--since` shows model changes and record changes, marked separately.
9. Approvals: not in the first version. Valves have a mode; only `auto` acts. (Decision pending
   with the owner.)
10. Agents' output names the part each line is for.
11. The web app opens on the diagram; colour shows loop status; click a part for its detail.

## Round 5: the real CLI, against the running `ops` demo

**Who:** the SRE again, now with the built tool and four loops running.

```
$ ergostat                      # one loop off: queue-short, jobs-waiting 38 against <= 20
$ ergostat loop queue-short     # sensor read 1s ago, controller decided 3s ago, valve opened: it is acting
$ ergostat system jobs          # the queue loop, and the disk loop (the workers' logs fill the disk)
$ ergostat agent                # eight agents, sorted by rung; what each fills
$ ergostat item                 # what the work is about
```

**Findings (applied):**
- A loop within its tolerance showed an error next to "holding". The error now shows only when
  the loop is off; the detail line says "within its tolerance of N".
- `ergostat item` listed ergostat's own bookkeeping (agents, valves, controllers) as items. Items
  are now what the agents' own events are about (`database`, `install.md`); `--all` adds the rest.
- `ergostat system jobs` showing the disk loop is right: the disk is tagged with both systems, and
  overlapping systems are the point.

**Open:**
- `agent.started` lines are noise in `ergostat event` for most questions; kept, because the record
  is raw. A filter (`--type`) answers it.

## Round 6: a new user, an empty repository

```
$ ergostat                                  no ergostat.toml here: chat, or check --example
$ ergostat check --example > ergostat.toml
$ ergostat check                            warn: agent disk-cleaner: ./clean.sh not found
$ ergostat                                  not running · start: ergostat run
```

**Findings (applied):**
- The record was keyed by the model's name, so a new repository whose example was named "ops"
  showed another project's 1841 events. The state directory is now `<name>-<hash of the repo's
  path>`; the example has no name (the folder's is used).
- `check` did not notice that an agent's command does not exist. It warns now.
- "No recent reading" was said before anything had run. Missing readings count only while
  running.
- `--help` names `check --example` as the place to start without the Supervisor.

## Round 7: "what happened overnight?" and "is the AI doing anything a rule couldn't?"

- `ergostat loop NAME` now ends with the loop's crossings (when it went off and came back) and its
  decisions, grouped with the numbers taken out, commonest first.
- A controller filled by a person, an AI agent or a decision that decides the same thing at least
  80% of at least 10 times is a hint in the status: a cheaper rung could fill it. The refactor path,
  with its evidence.

## Round 8: before and after a change

**Who:** the owner, asking the Supervisor to change a setpoint, then checking it took.

```
$ ergostat --since 10m        the model, since 10m ago: 1 change   07:51:25  ~controller:disk-under-80
```

**Findings (applied):**
- The model's changes were invisible. Each load that differs is recorded as `model.changed`
  (added, removed, changed parts); `--since` shows them above the loops, and the web page's side
  panel lists them.
- A running ergostat kept the old model until restarted. It now notices the file, and when the new
  model loads without errors it restarts itself in place (the same process, the same page).

## Round 9: when agents misbehave

**Who:** the SRE, with three bad agents: one exits 4, one names parts it does not fill (and one of
ergostat's own event types), one hangs.

```
$ ergostat
  ● agent crasher: its last run failed (exited 4)
  ● agent trespasser: 9 lines refused (a part it does not fill, or one of ergostat's own event types: ...)
  ● agent hanger: its last run failed (stopped after its timeout of 4s)
$ ergostat agent                 hanger   running for 3s
$ ergostat event --type agent.refused
```

**Findings (applied):**
- A hanging agent showed "never ran". It shows "running for 3s" (CLI and the Agents page).
- The timeout was fixed at five minutes. Agents take `timeout = "30s"`, and the note says so.
- A timeout killed only the shell, and `run --stop` left runs behind. Each run is its own process
  group; a timeout or a stop kills the group.
- The refusal note now says what else it can be (one of ergostat's own types) and where to look.

## Round 10: looking back

**Who:** the SRE, the morning after: the queue loop was off for a while overnight; what did it look
like then?

```
$ ergostat --at 03:10                 as of 03:10:00 (5h ago): queue-short off, jobs-waiting 48
$ ergostat loop queue-short --at 03:10
$ ergostat system --blocks --at 03:10
```

**Findings (applied):**
- There was no way to see a past moment. `--at` (`30m` ago, `07:30`, or epoch seconds) estimates
  the state as it was then, over the window before it; every topic takes it. The web page has a
  slider in the header and "back to live".
- The model's history called every agent changed after ergostat itself gained a field (`timeout`).
  Fingerprints now cover only what a part declares (fields that differ from their defaults).

## Round 11: an independent reviewer, two personas (an SRE on the CLI, their manager on the page)

Twenty findings; the ones applied:

- The diagram was cut off on first load and "fit" did nothing: fit now shows everything (the first
  view keeps labels legible and pans the rest).
- The side panel mixed two moments (a loop off beside "nothing needs you"): the attention list now
  comes with the diagram, from the same snapshot.
- Loops stuck at "unknown" were never flagged: after two minutes of record, they are.
- `-s` was ignored by the bare status and unknown systems were accepted: both fixed.
- `--at 25:00` crashed; a moment before the record raised false alarms: validated, and it says
  the record starts later.
- Windows claimed more record than existed: residuals and crossings say "the 36m recorded".
- The block view drew a draining actuator with "+" and left out another agent's inflow: signed by
  direction, and other agents' inflows are d.
- Suggestions outranked problems: problems first; suggestions apart (CLI) and folded (page).
- Python leaked into output (`['host', 'jobs']`, `disturbance True`, counts as strings): the
  file's words, numbers in JSON, `check --json` has `ok`.
- `--blocks` with no name listed systems: it draws everything.
- Tolerance was invisible: setpoints read `<= 24 (±2)`.
- The model's edits filled the side panel: one line, folded.
- Rates had no units: `734 %/h`, `1541 h/h`.
- Phones opened on a 400 px diagram: they open on Loops.
- Subcommand help was bare: every flag is described.
- `--exit-code` makes the status exit 1 when something needs attention, for cron.
- The file-queue "unexplained" residual was real: runs stopped midway by restarts had moved files
  without saying so. The agents now say each move as they make it, and `docs/writing-agents.md`
  says to.

## Round 12: a first agent, from the guide alone

**Who:** a new user keeping a scratch folder under 10 files, with `docs/writing-agents.md` open.
They forget to declare the valve's flow, and their script says no decision.

```
$ ergostat check
error  valve remove-oldest: flow 'removed' is not a flow; declare it: [[flow]] name = "removed" with from = ... or to = ...
$ ergostat agent tidy --now
the model has 1 error (ergostat check); running it anyway, to try it
ran in 0.03s: 1 reading, 1 opening, 0 decisions, 0 events
said nothing for: controller scratch-small (fine when there was nothing to do; a sensor should always read)
```

**Findings (applied):**
- `check`'s errors said what was wrong, not what to write. Each unresolved reference now names
  the declaration that fixes it.
- `--now` ran a broken model silently. It warns, and still runs: trying an agent is the point.
- `--now` now lists the roles the agent said nothing for: the likeliest thing missing from a new
  agent.
- A run by hand was logged as "(schedule)"; it says "(by hand)". "1 readings" is "1 reading".

## Round 13: a second independent review (a control engineer; a developer writing an agent)

Eighteen findings; applied:

- **The error's sign was y − r** while the legend said r − ym. It is e = r − y now, everywhere
  (status, block view, what agents are given), and documented.
- **The "off most of the time" hint could not tell saturation from slow sampling.** It now
  compares the loop's valve flow with the load: "saturated: 466/h out while 902/h came in: a valve
  with more capacity, or less load", and suggests faster sampling only when the valve can keep up
  (and never to an event-driven controller).
- **Tolerance was shown as ± on one-sided setpoints and had no hysteresis** (one loop crossed 90
  times an hour). It is shown on the side it applies, `(+2)`, and is a hysteresis band: off past
  r + tol, holding again only within r.
- **Strict `<` and `>` were treated as `<=` and `>=`.** The bound itself counts as off.
- **An unmeasured disturbance hid every fault on its stock**, its estimate clamped at zero. An
  estimate that would have to run backwards is now flagged, and a disturbance can declare a known
  rate (`rate = 1800` for time passing in the backups demo: its residual went to ~0).
- **Another loop's output was drawn as an anonymous d.** It is named: "u of loop inbox-empty,
  measured" (the loops are in series). The plant is marked ∫; H shows its sampling period.
- **Agents got too little on stdin, and nulls were undocumented.** Each controller now comes with
  op, target, tolerance and status; the guide says values can be null and are the last recorded.
- **Bad lines were silently defaulted or dropped.** They are refused (amount or position required,
  amounts not negative, decisions with words, type names, object data), and lines meant for
  ergostat that cannot be read are counted and reported by `--now` and the status.
- **Trial runs left permanent problems.** What a run by hand refuses is shown to the person who ran
  it, not kept in "needs attention". `--now` shows only this run's log.
- **The git-hygiene demo counted every merge twice** (printf repeated its format); the tool's
  residual had flagged it correctly.

## Round 14: the Supervisor, for real

**Who:** the owner, asking the Supervisor (a real Claude Code session briefed by `ergostat chat`) to
"add a loop that keeps ~/Desktop under 200 files, measured by the existing meter, held by me with a
manual valve", in a scratch copy of the `this-mac` demo.

**What it did:** added the stock, a disturbance (files saved to the desktop), an outflow, the
sensor (one read-only line in the meter), a controller filled by the owner and a manual valve; ran
`ergostat check` (ok) and `ergostat agent meter --now` (4 readings, nothing refused, every loop
holding); noticed that "under 200" is a strict `< 200` and offered `<= 200`.

**Findings:** none needed applying: the brief (the model, the agent protocol, `check`, `--now`,
strict bounds) was enough for a correct change on the first try.

## Round 15: a script author, using --json

Every topic, with and without a name, `-s`, `--at`, `system --wiring` and `--blocks`: each prints
one JSON document, with no terminal colour codes. Nothing to apply. (`system --blocks --json`
gives the control graph, from which the blocks are drawn.)
