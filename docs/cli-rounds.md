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

## Round 16: an independent code review

Fifteen bugs, most proven with a small script; all applied:

- A bad agent line (a list as a name, `NaN`, `Infinity`, an object as an item) raised inside the
  read loop and left the run half done: no `agent.ran`, the process unwaited, `--now` hung. Reads
  are guarded, names and items must be strings, numbers finite; the run always ends recorded.
- The timeout started only after stdin was written, so a large trigger and an agent that does not
  read stdin dodged it. The timer starts first; stdin is written from its own thread.
- A cron that never matches (`0 0 31 2 *`), or rarely (`0 0 29 2 *` seen from March), killed the
  scheduler for every agent. It is refused at load (looking eight years ahead), and a failing
  schedule stops only its own agent. Day fields with a step (`*/2`) count as unrestricted, as in
  Vixie cron.
- One infinite reading made every page's JSON invalid: numbers must be finite.
- The page reloaded the model into the object the runner was using, unchecked: the page has its
  own model now.
- An agent listening on `*` woke itself with its own `agent.*` events: never again.
- Two disturbances on one stock, in and out, were never estimated: the residual is shared among
  the ones pushing the way it went.
- Pruning could forget a loop's last crossing, and with it the hysteresis: each loop's last
  crossing is kept.
- The follower thread died on any error (a busy database), silently: it says so and carries on.
- Two readings at once could record the same crossing twice: crossings are recorded under a lock.
- A stop during a live reload was lost, and `--stop` said "stopped" without checking: the reload
  yields to a stop, `--stop` waits and says when a runner did not stop, and no run starts after
  stopping.
- The pid file had no lock: a reused pid looked like a runner, and two `--foreground` runners
  could run at once. `run.pid` is locked for the runner's life; a pid file nobody locks is stale.
- The noise floor was taken on averaged readings while the change was raw: it is taken on raw ones.
- The page opened and closed database connections on every request: requests are served by a
  fixed pool of threads. Agent logs are kept to their last megabyte past five, and read from the end.

## Round 17: a third independent review (a visual designer; a new user starting cold)

Twenty findings; applied:

- A person had no way to record that they acted: `ergostat valve NAME --opened N`, `sensor NAME
  --read V` and `controller NAME --decided TEXT`, for roles a person fills, checked like any
  agent's lines. A valve a person fills is manual unless the file says otherwise.
- The views disagreed on a measured flow (the latest scan said 0): a measured flow's rate is its
  average over the window.
- Agent badges coloured by kind clashed with the colours of roles and status: badges are neutral
  with a dot by kind, and the kinds are in the legend.
- The setpoint's dashed line struck through the stock's value: it is a marker on the tank's edge.
- The controller's last decision read as the present: it carries its age.
- e was never shown on the Loops page and tolerance was written three ways: e = r − y always,
  coloured by status; one form for tolerance, in the block view too.
- The status kept saying "holding" after the runner stopped: it says the readings are old and
  nothing is measuring. `projects` counts unknown loops.
- A new user had no docs after installing: `ergostat help agents` and `help ai-agents` ship the
  guides (a test keeps them equal to `docs/`).
- `--now` exited 0 with lines refused, and cut the reason short: it fails, with each reason whole.
- The Guide said a controller measures; plurals; the ladder's "move right" and "move down": fixed.
- Large block views were one tall strip: a column per six loops. A loading message, and one when
  the server does not answer.

Not applied: nesting overlapping system outlines (overlap is the point of systems), the phone
layout beyond what round 11 did, and the wiring view's packing.

## Round 18: on call (a page at 03:00: "the archive loop is off")

The on-call engineer runs `ergostat`, then `ergostat loop archive-under-50`. The status names the
off loop and why (it samples too slowly, once a minute, for a valve that moves 44 files a run);
the loop shows 118 crossings in the hour and the evidence. One line misled: the valve "opened 31s
ago: 1" was the last of 44 files moved by one run.

- The valve row sums its last run: "opened 31s ago: 44 in 44 openings".

## Round 19: a second code review (the code since round 13)

Eleven findings, all applied, each with a test where one could be written:

- An idle browser connection kept the page's pool thread, and `run --stop` waited on it forever:
  the pool's threads are daemons, a request that never comes is given up after 10s, and there are
  enough threads that idle connections never starve a request.
- A page checking whether the runner was up took the pid file's lock for a moment, so a runner
  starting then thought another held it: starting waits a second for readers, and only a runner
  holding the lock refuses it.
- A reload let go of the lock until the new process took it again: the locked file is handed on
  through `execv`. A file locked but not yet written is read again rather than read as no runner.
- A measured flow read every two hours averaged to 0 over the last hour, and two sensors on one
  flow were added: each reading covers the time back to the one before (the first back to the
  window's start), the last holds until now, and sensors on one flow are averaged.
- A valve line refused for its amount still recorded its position: the whole line is checked first.
- System outlines could enclose parts outside the system, and deep ones were clipped in the view
  and in exports: the test is against the outline as drawn, depth is the longest chain of systems
  inside, and the outlines count in the diagram's size.
- A system view whose loops had parts outside it drew nothing at a NaN size: it says there are no
  whole loops to draw.
- Upgrading ergostat logged every valve as a model edit (a field that says how the file was read,
  and the default mode for a valve a person fills, entered the fingerprint): neither does now.
- A stop during a run left the agent "running" forever: stopping waits for the killed runs to be
  recorded.
- `*/5` skipped the repeated hour when the clocks went back: cron steps through real minutes.

## Round 20: a crontab of one-liners (the end goal, from the other side)

A user has scheduled jobs that are plain commands (`find ... -delete`, `du`, a rotate in one `if`)
and wants their control diagram without rewriting them. Modelled as the demo `plain-crontab`.

- Every job had to print JSON: an agent filling one sensor or one valve may print a bare number,
  its reading or what it moved (0 is no opening). `wc -l` and `cut -f1` are enough.
- `check` called `for` and `s=$(...)` missing programs: a line starting with shell syntax is not
  looked up on PATH.
- `agent --now` said "a sensor should always read" about a silent controller: a sensor that did
  not read is a warning of its own; other silent roles are noted as fine.
- The guide has "A job you already have"; the Supervisor's brief says the same.
- The block view's own labels (loop names, r, d, ym) were black on the dark theme: they take the
  ink colour. r's label ran into the junction's + sign: the junction moves right of the longest one.
- The Agents page drew a loop hint as a decision hint (`"" 52% of 0`): it shows what the hint says.
- A job rotating a log every 2 minutes was called saturated: a sawtooth that gets back under the
  setpoint is sampling too slowly. Saturated needs the loop off at least 90% of the window.

## Round 21: "send me the diagram" (a manager asks for the picture in a ticket)

The engineer had the page open but nothing to send but a screenshot or one SVG; the reader cannot
click a part, switch to the block view or see the loops.

- `ergostat snapshot [-o FILE] [--since 1h]` writes the page with every answer it would ask for
  (each view of the whole and of each system, every loop, agent and part, the record, the
  residuals) into one HTML file, scripts and style inline. It opens offline; the header says it is
  a snapshot and when; ages are counted from then; the slider, window and project switcher are
  gone. A view it does not hold (around one part) says so rather than "the server is not answering".

## Round 22: a fourth independent review (a cold start with the user's own cron jobs)

Thirteen findings; applied:

- A load generator could not be drawn: a disturbance may name `agent`, the agent whose doing it is.
  It is drawn as a badge on the diamond, as an agent in the wiring view ("the load: ..."), with
  arrows to the agents whose sensors read the stock it pushes; `check` no longer calls it an agent
  filling nothing, and `agent NAME` says what it is the load of.
- The saturation hint came only after 10 minutes, silently: before then a loop off half the time
  says so, and that why is told after 10m of record (so far: N).
- `system --wiring` alone listed the systems: it draws everything, like `--blocks`.
- Loops were in four orders: the file's order everywhere (the diagram, blocks, wiring).
- `event` was mostly run bookkeeping: `agent.started` and `agent.ran` are left out unless `--runs`
  or `--type` (the page's Record already did this).
- `valve NAME` printed `mode_set`; disturbances were listed as "flows outside any loop": they are
  "disturbances (nothing controls them)", with the agent whose doing each is.
- A bare number vanished from the agent's log: the log says what it became.
- The loop's trend said "over 1h" after five minutes: it says the span recorded.
- Twin edge labels in the wiring view were placed by name and could cross: by where the lines run.
- The README says names are unique across parts and every amount is in its stock's unit.

Not applied: a way to forget a bad reading (an open question: the record is append-only), and
marking a controller as not reading its sensor (a time-based job that ignores the measurement:
the loop is drawn as declared).
- A tank's level and setpoint did not read at a glance (the setpoint marker hid under the
  sensor's arrow): a meter under the title shows the level, with a tick at the setpoint, and the
  setpoint is written beside the value.
- A sensor's label could lag its stock ("reads 12" by a tank at 24): a redraw that keeps the
  layout took the labels' text from the layout; it takes it from this tick's data.

## Round 23: the weekly review ("how did our loops do this week?")

A team lead runs `ergostat --since 7d` on Monday.

- The status had no time off per loop, though the page's Loops did: a TIME OFF column, the share
  of the window each loop spent off.
- One model change listed 32 parts on one line: past eight, six and "and N more".
- Changes older than a day said only the time: they say the day too.

## Round 24: a third code review (the code since round 19)

Nine findings; applied:

- One event holding `<!--<script` swallowed the snapshot's scripts: every `<` in the snapshot's
  data is written `<`, and `<!--` cannot open in an inlined script.
- An agent that speaks JSON got fake openings from a stray number (`wc -l`): a bare number is
  taken only when the run printed no JSON line, and only the last one, at the end of the run.
- `.50` (from `bc`) and `007` were not taken as numbers: they are read as numbers; the log says
  what the number became, or that it was refused.
- A valve moving less than its load, in a loop off between half and nine tenths of the time, was
  said to keep up: it is said to be behind, getting back only now and then.
- Items named with `(`, `)`, `!`, `'` or `*` were missing from snapshots: keyed as the page asks.
- The Record page and `ergostat event` could differ (the page filtered runs after its limit): the
  server leaves run bookkeeping out the same way (`runs=1` puts it back).
- A snapshot carried the end of every agent's log: left out unless `--with-logs`.
- `snapshot --since bogus` went through: refused, as everywhere.
- A long value could run into the tank's setpoint text, a negative setpoint put its tick off the
  meter, and a part that gained a badge kept its old label space: the tank is sized for both, the
  tick is clamped, and the layout is redone when a part's label lines change.

Not applied: a cron time inside the hour the clocks skip in spring does not run that day
(Vixie cron runs it after the gap); the repeated autumn hour runs twice. Noted, not changed.

## Round 25: the wrong first reading (from the fourth review, left open in round 22)

A broken first run recorded an age of 1.79 billion seconds; for the rest of the hour every rate
and residual on that stock was nonsense, and `--since` could not get past it.

- `ergostat sensor NAME --forget-above V` (and `--forget-below V`) sets the readings aside: they
  move to their own table, kept, out of every estimate, and `ergostat.forgotten` records what was
  set aside and why. On the reviewer's record, the residual went from −1794679277 to 14.

## Round 26: the timer is not a feedback loop (from the fourth review, left open in round 22)

Most cron jobs act by the clock: `find -mmin +60 -delete` runs whatever the count. Declared with
`reads`, it was drawn as a closed loop and listed as a cycle among the agents, which it is not.

- A controller may say `open_loop = true` (and no `reads`). Its loop is still judged against its
  setpoint by the sensors on its stock, which only watch it. The control view draws no signal into
  the controller and a clock in place of its Σ, with "open loop: acts on its schedule, reads
  nothing"; the block view has `t: <schedule>` driving C with no Σ, and ym ending in "watched
  against r, not fed back"; the text views say the same; the wiring view finds no cycle. `check`
  warns when an open loop also lists `reads`. The plain-crontab pruner is one.

## Round 27: after the reboot (an SRE puts it on a box for good)

`ergostat run` started a background runner, and nothing started it again after a reboot; the SRE
was about to write a launchd plist by hand, guessing the arguments.

- `ergostat run --service` prints a launchd agent (macOS) or a systemd user unit (elsewhere) that
  runs this repository's ergostat in the foreground, with its log and `ERGOSTAT_HOME`, restarted
  after a crash or a reboot but not after `run --stop`; and says where to save it and how to load
  it. It installs nothing: where it goes is the owner's to decide.
- `check --example cron` prints a model of two one-liners (a count, and an hourly prune as an open
  loop) that runs as it is, in an empty repository: nothing to write before the first diagram.

## Round 28: a visual design review (an information designer with a control background)

Ten problems; applied:

- Agent kinds were told apart by colour alone, and program/rule and ai/narrow-ai were near twins:
  six hues apart in both themes, and a letter in every dot (H, A, N, D, P, R), in badges, the
  wiring view's agents, the ladder and the legend.
- The first view shrank text to 4-7px on wide systems: it keeps text at 9px or more (a system
  that fits at 0.7 is shown whole), pans from the left otherwise, and says "more beyond the edge:
  drag, or fit". The fit leaves room for both toolbars.
- An exported SVG did not say what it was, carried `var()` attributes, and repeated the font
  stack on every element (161KB): it has a header (project, system, view, when, window), no
  leftovers, and styles only where they differ from SVG's defaults (55KB).
- A trend had its own scale, so 2512 against ≤ 5 looked like 13 against ≤ 4: the trend and the
  setpoint share a scale, the setpoint dashed.
- Badges and quotes cut with "…" had nothing to reveal the rest: the full text on hover.
- The open loop's ym ended in an arrow pointing at nothing: it ends in a bar.

Not applied (noted for later): automatic wrapping of long chains (the wrapped layout detours:
needs rows broken at stocks), the big demo's block view grouped by system with an overview, and
drawing another loop's actuator as a coupling rather than as d.

## Round 29: after a restart, a loop that never came back

Found while retaking screenshots: ops's backup-fresh had been off for 890 (simulated) hours. Its
policy listens for `loop.off`; the backup its crossing asked for was killed by a restart, the loop
stayed off, and no crossing ever came again. An event-driven controller whose action is lost
waits forever; and the killed run was shown as the agent's failure ("exited -9").

- When ergostat starts, every loop already off is said again (`loop.off`, `"still": true`), so
  what listens for it acts. ops recovered within a second of the restart.
- A run killed because ergostat itself stopped is noted "stopped with ergostat", never a failure.
- "acts too late (on on loop.off...)": the schedule is said once.

## Round 30: a chain of loops, folded where it joins (from round 28's open items)

A chain of loops in series (file-queue, deps) was one strip, five times wider than the window;
ELK's own wrapping cut it anywhere and sent pipes on long detours.

- The pipe from one loop's valve into the next loop's stock is left out of the layout, so each
  loop is laid out on its own; the loops are stacked one per row in the model's order (upstream
  on top), and the pipe is drawn by hand: out of the valve, past its labels, down into the gap
  above the next row, across, and into the next stock. This happens by itself when the unwrapped
  diagram would be more than twice as wide as the window allows; the "wrap" button turns it on
  or off either way.

## Round 31: the first command in an empty repository

- `ergostat` with no model said to write one: it lists three ways to start, the first a single
  command (`check --example cron > ergostat.toml`, then `run`) that gives a running loop and a
  diagram with nothing written.
- "1 loops · 1 stocks": the counts agree with their number.

## Round 32: a fourth code review (rounds 25-31)

Nine findings, all applied:

- Forgetting a wrong reading left the loop "off" (the crossing it caused stayed in the record):
  the crossings whose value was forgotten are voided with it (listed in `ergostat.forgotten`,
  left out wherever crossings are read), and the loop is judged again on what remains.
- Every model reload said "still off" again, and on an old reading: only a fresh start does,
  only on a reading under ten minutes old, before any agent runs and under the crossing lock.
- A bare number was recorded from runs that failed, timed out or were killed: only from a run
  that ended well.
- Runs cut short by our own stop still counted as failures in `agent` and on the page: they are
  recorded as runs, noted "stopped with ergostat".
- An open loop that also listed `reads` was drawn with feedback: an open loop reads nothing.
- `check --example cron` pruned the repository's own `tmp/`: it keeps to `.ergostat-example/`.
- A service whose runner found another holding the lock restarted forever: "already running"
  is not a failure.
- The systemd unit did not escape `%` or `$`, quoted WorkingDirectory, and did not say a user
  unit starts at login (`loginctl enable-linger`): all three; and the unit runs this very
  ergostat, not whichever is first on PATH.
- The block view's system tag ran into the loop name (measured now); the systems fallback
  never applied; an open loop's `t:` says the full schedule, as the text view does; the "more
  beyond the edge" hint follows drags and zooms.

## Round 33: a control engineer's review

Nine points, seven applied:

- A loop whose only sensor measured a flow was "closed", comparing a rate with a level: feedback is
  a reading of the stock itself; a sensor on a flow feeds forward, and `check` says so.
- "Saturated" rested on a near-circular test (the estimated load is the stock's change minus the
  valve): the hint says *falling behind* (out below in, the stock grew by N), and *saturated* only
  when every opening moved the same amount.
- "Run it more often" blamed the controller whatever the bottleneck: the slowest stage is named
  (sensor, controller or valve, by schedule); and the longest period that can hold the setpoint is
  said (file-queue: 14s; cron cannot).
- Outflow disturbances were never drawn in the block views: they join the plant with −, both views.
- `==` with a tolerance never came back to holding: back within half the tolerance.
- The tolerance was said to stop the loop chattering: it stops the *status* chattering; for an
  agent woken by `loop.off` it is the control law. An estimated disturbance is lumped (it holds
  every model error too). A measured flow is the window's average; a latest reading says "now".
  The text block view shows feedforward, as the page did.
- A cron sensor's old reading was never called stale: its period is cron's gap.

Not applied: the stage delays measured from the record (reading → decision → opening → holding),
a valve's declared maximum per run, and naming upstream action piling up behind a loop that is
off (anti-windup): noted for later.
- Added afterwards (one of the noted concepts): a loop that keeps feeding a stock whose own loop is
  off half the time or more is named: work piles up downstream; hold it back while the downstream
  loop is off (the anti-windup question for loops in series). deps shows it.
