# ergostat: design

What ergostat is, as built. The terms are in `NOTES.md`; the rules in `CLAUDE.md`. Where this file
records a choice made while the owner was away, it says so (*decided in the owner's absence*).

## 1. Purpose

ergostat keeps work going. Someone draws a control-system boundary around some work and describes
what is inside it: what accumulates, what moves it, what measures it, what decides, what acts, and
who (which agent) fills each of those roles. ergostat runs the agents that run themselves, records
what they do, estimates the state, says what needs attention, and draws the system.

## 2. The model: `ergostat.toml`

One file in the repository, read with the standard library (`tomllib`). Every part has a unique
`name` (lowercase letters, digits, `-`, `_`), an optional `description` and `systems`.

| Table | Declares | Keys |
|---|---|---|
| `[[stock]]` | what accumulates | `unit` |
| `[[flow]]` | what moves a stock | `from`, `to` (a stock; left out: outside the boundary), `unit` |
| `[[disturbance]]` | a flow no valve controls | `into` or `out_of`; `rate` (per hour) when it is known; `agent`: whose doing it is (a load, drawn on it, never a role) |
| `[[valve]]` | where an agent acts, on one flow | `flow`, `agent`, `mode` (auto, advise, manual); `max`: the most one opening moves |
| `[[sensor]]` | measures a stock or a flow | `measures`, `agent`, `unit` |
| `[[controller]]` | holds a stock at a setpoint | `holds`, `setpoint` (`<= 80`, `>= 1`, `== 0`), `tolerance`, `reads` (sensors), `drives` (valves), `agent`; `open_loop = true` for a timer that reads nothing (the stock's sensors only watch it) |
| `[[agent]]` | fills roles | `kind` (person, ai, narrow-ai, decision, program, rule), `command`, `every` / `cron` / `on`, `description` |
| `[[system]]` | names a selection | `description` |

**Loops are derived, never declared.** Each controller is a loop. It closes when one of its
sensors measures its stock (or a flow of it) and one of its valves acts on a flow of it; otherwise
it is open, with the gaps named.

**Systems are selections and overlap freely.** A part is in a system when it is tagged, or attached
to a tagged stock (the stock's flows and their valves, the sensors measuring it, the controllers
holding it). The system with no selection is everything.

**`ergostat check`** reports errors (a reference that does not resolve; a valve on a disturbance)
and warnings (a loop that cannot close; a part no agent fills; a flow with no valve that is not a
disturbance; an agent with nothing to do, no roles, or a command that is not found).

## 3. The record

(Where the record is kept, rolled up and downsampled, and its backends: SPEC §4b. What follows is
the SQLite backend of each.)

Two stores, kept apart because there are few events and many measurements, both SQLite files in
`$ERGOSTAT_HOME/<name>-<8 hex of the repository's path>/` (default home `~/.ergostat`;
*decided in the owner's absence*). Each thread keeps its own connection open (opening and closing
connections from many threads deadlocked inside SQLite's file locking).

- **`events.db`**: `events(seq, id, time, type, item, source, causedby, data)`, append-only,
  indexed by item, type, time and cause. An event's `item` is what it is about; an item is the fold
  of its events.
- **`measurements.db`**: `samples(series, time, value)`. A sensor's readings are the series
  `sensor/<name>`; a valve's position, `valve/<name>`. A long span is averaged into buckets by
  SQLite (the first and last readings kept exact), so a week of readings never reaches Python one
  by one.
- **Keeping**: the top-level `keep = "30d"` (the default) says how long the record is kept; the
  runner forgets older events and measurements hourly, except the model's history (`model.changed`),
  which is kept whole.

ergostat's own event types (agents may not publish them): `agent.started`, `agent.ran`,
`agent.failed`, `agent.refused`, `valve.opened`, `controller.decided`, `loop.off`,
`loop.holding`, `model.changed`, `ergostat.started`, `ergostat.stopped`, `budget.closed`,
`budget.refused`. `ergostat item` lists
only items that other events are about (the user's things); `--all` adds the parts.

## 4. Running agents

`ergostat run` starts a background process (`run --foreground` stays attached; `run --stop`) that
serves the web page and runs every agent that has a command and is not a person:

- **When**: `every` (a duration), `cron` (five fields, local time), or `on` (event-type globs,
  optionally `@item`, never its own events). One run at a time per agent; a scheduled run is skipped while the last one
  still waits.
- **Given** on stdin: the agent, its roles, every stock's current value, its controllers'
  setpoints, values and errors, and the triggering event.
- **Says** on stdout, one JSON object per line, naming the part:
  `{"sensor": N, "value": x}` (a measurement), `{"valve": N, "amount": x}` (`valve.opened`),
  `{"valve": N, "position": x}` (how far it is open, a setting kept as the measurement `valve/<name>`;
  it is u in the block view), `{"controller": N, "decision": "..."}` (`controller.decided`), or
  `{"event": TYPE, "item": ID, "data": {...}}`. Anything else goes to the agent's log.
- **Discipline**: a line naming a part the agent does not fill, or one of ergostat's own types,
  is refused and recorded as `agent.refused`. Every agent acts only through the roles it fills.
- **The edge detector**: after a reading, each loop that sensor serves is compared with its last
  crossing; a change records `loop.off` or `loop.holding`. This is the one place a measurement
  becomes an event.
- **The model's history**: each load that differs from the last recorded one records
  `model.changed` (added, removed, changed parts). A running ergostat notices an edited file; when
  it loads without errors it swaps the model in place at run boundaries: runs under way finish under
  the model they started with, new runs start under the new one, and nothing is killed (SPEC §9.1).

## 5. The state estimate

Over a window (default 1 hour), with every rate taken over the time actually recorded:

- **A stock's value** is the latest reading of a sensor that measures it; unmeasured is unknown.
- **A flow's rate** (per hour) is its sensors' average over the window (each reading covering the
  time back to the one before; several sensors averaged), else the amounts its valve opened over
  the window. The latest reading is shown as such ("now") where it is used, as for feedforward.
- **A residual** is a stock's change minus what its known flows explain (valve amounts between the
  first and last reading; measured flows integrated over time; declared rates). When an unmeasured
  disturbance pushes that stock, the residual is its estimate, unless it would have to run
  backwards to explain it: then it is flagged, never clamped. Such an estimate is *lumped*: it is
  the disturbance plus every error in the model (a valve that over-reports, a biased sensor), and
  one sensor on the stock cannot tell several disturbances apart, so the share among them by
  direction is a convention, not a measurement. Otherwise the residual is unexplained
  when it is larger than 5% of the flow and twice an ordinary non-zero step between readings
  (timing at the window's edges is noise), and the recent half of the window shows it too, the same
  way (a one-off long ago in the window is not flagged for an hour).
- **The error** is e = r − y, the control convention: negative when the value is too high, 0 on a
  one-sided setpoint's satisfied side.
- **A loop** is open (cannot close: it needs a sensor on the stock itself, since a sensor on a flow
  measures u or d and feeds forward), unknown (no reading), holding, or off. The *status* has
  hysteresis on the side that matters: off past the setpoint by more than the tolerance, holding
  again only back within the setpoint itself (for `==`, within half the tolerance); a strict bound
  (`<`, `>`) counts the bound as off. The band filters the alarm, not the agent's own control law,
  except for an agent woken by `loop.off`, for which the band is the control law (it sets the limit
  cycle). A loop acted when a reading and a decision or opening both fell in the window; its time
  off is measured from its crossings, so it is as precise as its sensor's period.
- **Hints**, apart from the problems:
  - the refactor path: a controller filled by a person, an AI agent or a decision that decided the
    same thing (numbers taken out) at least 80% of at least 10 times could be filled by a lower rung;
  - a loop off at least half the time though it acts: *falling behind* when its valve moved less
    than the load came in (saturated only when every opening moved the same amount: the valve at
    its limit); otherwise it answers too late, and the slowest stage (sensor, controller or valve,
    by its schedule) is named. For a job emptying a stock under an upper setpoint, the longest
    period that can hold it is said (the room under the setpoint over the load), and when cron
    cannot run that often.
- **Attention**: problems first (goals off, goals open or unknown past two minutes of record,
  agents failing, lines refused or unreadable, missing readings while running, unexplained
  residuals), then the hints. What a run by hand refused is not kept as a problem.

## 6. The diagram

The control diagram is the product's main view. Conventions:

- **Shapes**: a stock is a tank (a meter under its title with the setpoint's tick, the setpoint
  written beside the value, a trend along the bottom on one scale with the setpoint, dashed); a flow is a pipe; a valve is a bow tie on the pipe (filled: auto, half: advise, open:
  manual); a disturbance is a diamond with a wave; outside the boundary is a cloud; a sensor is a
  gauge; a controller is a box with a summing junction, its setpoint, status and last decision;
  an open loop's controller has a clock in place of the junction and draws no signal from a sensor.
  Every role carries a badge: the agent's kind, name and schedule, with a dot coloured by kind and
  lettered (H person, A ai, N narrow-ai, D decision, P program, R rule), so colour is never the
  only cue; a disturbance may carry the badge of the agent whose doing it is.
- **Lines**: pipes are double lines with moving dots while they flow; measurement is dashed
  (stock to sensor), signal solid (sensor to controller), action purple (controller to valve).
  A loop's lines take its status colour (green holding, red off, amber open).
- **Layout** (ELK layered, vendored): the plant runs left to right along the pipes (pipes carry the
  highest straightness and direction priority), the feedback path above it; each loop a row.
  Systems are drawn as thin outlines named in muted type (one ink: no colour per system), overlapping where they
  share parts, labels never stacked. A chain of loops in series folds into rows at the pipes that
  join them (one loop per row, upstream first, the joining pipe routed by hand), by itself when it
  would be far wider than the window, or with "Wrap loops into rows" (the toolbar's ⋯ menu, beside "Open
  all systems", "Close all systems" and "Unpin all parts"). The first view keeps text legible (9px or
  more) and says when more lies beyond the edge; "Fit" shows everything.
- **The process view** (`process.py`, `process.js`; SPEC §5b) is process mining's process map: a
  directly-follows graph per item kind, from the record in the window (the states items entered, or
  the event types about them), each kind's map laid out left to right in time order in a frame of its
  own, how often as line weight, rework marked, and dashed lines where an event on one kind's item
  caused one on another's. It replaced the wiring view (machines and what passed between them),
  which stays on the command line (`ergostat system --wiring`). Its nodes and its kinds' frames are put by
  hand as the other views' parts are (below).
- **The block view** draws each loop as a classic negative-feedback block diagram, one row per
  loop: the setpoint r into a summing junction (Σ, + and −), the error e into the controller C, its
  output u into the actuator (the valve), a second junction where the disturbance d joins, the
  plant (the stock), its output y, and the sensor H on the feedback path carrying ym back to Σ.
  Every block names the agent that fills it; the loop's lines take its status colour. An open
  loop has `t: <schedule>` driving C with no Σ, and ym ends in "watched against r, not fed
  back". With several systems the rows are grouped by system and tagged. The command line prints
  the same in text (`ergostat system --blocks`).
- **One selection, two views.** What is chosen is model parts (`stock.x`, `flow.x`, `auxiliary.x`,
  `goal.g` and its reference `goal.g.r`, `block.b`, `system.s`), never shapes, so it survives a change
  of view. Every graph comes with a correspondence (`ergostat/correspond.py`): each shape, the parts it
  is; each part, the shapes standing for it there. The rule is identity, never what a shape touches: a
  stock's integrator and its output y are the stock, a controller (with its sampler, hold and junction)
  its block and the valves it opens, a goal's comparator its desired level and gap, r the desired level,
  d its flow; a stock's summing junction, a MIMO process, a closed system and an open system's frame are
  regions holding what is in them. A part with no shape of its own in a view is stood for by the
  smallest region holding it, dashed, and its panel says so ("In the block diagram: inside P_service");
  a block, which the dynamics view does not draw, by what it moves. A click chooses what its shape is,
  Shift or a box adds, a loop chooses its members, the background or Escape lets go. A panel open on
  what is chosen stays open when the view is switched (Dynamics ↔ Blocks), on what stands for it there
  and titled in that discipline's words: a stock as "output y_quality of P_service", a flow a controller
  moves as "actuating signal u_tuner", a reference as "reference r = 0.93 and its summing junction". A
  part's panel opens at the click, its name first, and fills when its numbers come.
- **Parts put by hand.** In the Dynamics and the Blocks view alike, a part dragged (a block, a summing
  junction, a sensor, a stock, anything drawn) moves, with the others chosen if it is one of them; an open
  system dragged by its top (its outline, or its frame in the block diagram) moves with everything in it.
  While they move their lines keep their last shape, greyed, and take their new way from libavoid; let go,
  they are pinned there and only the lines are routed again, with no new layout. A pin is kept in the
  browser per project, view, system drawn and focus (the Blocks view's apart from the Dynamics view's),
  from the corner of the frame it is in, so it survives a reload and a system opened or closed; a
  system's box and its open outline (or frame) share one. A pin clicked, or "Unpin all parts" (⋯), lets
  the layout place it again. The Blocks view is laid out by its own ELK graph (`blocks.js`); the pins
  are applied to that layout afterwards, as to the Dynamics view's (`places.js`). So is the Process view's
  (`process.js`): a node (an activity, a start or an end) or the chosen ones, and a kind's frame by its top
  with its whole map, pinned in its own set (apart from the other two views'), each node from its kind's
  frame; a line within a kind keeps ELK's way while its two ends moved together (a frame dragged) and that
  way crosses no node, and is routed by libavoid otherwise, as the dashed lines between kinds always are.
  A pin is kept by the node's name (its kind and activity), not per States or Events: a node drawn in both
  stays where it was put in both, and the frames too; it holds through the map refreshed in place and laid
  out again as events come, and whichever kinds are drawn.
- **The caption.** One line under the view switch, the page's only h1 and the diagram's accessible name
  (`aria-labelledby`), names the drawing by its discipline, the model with its purpose (`purpose:`), the
  number of top-level systems, and the verdict as that view counts it: "Stock-and-flow diagram (system
  dynamics) · NAME: PURPOSE · 2 systems · 25 goals, 0 off" (every goal), "Block diagram (control) · … ·
  16 control loops, 2 off" (the goals a controller holds). The Process view gives its type, the model and
  its systems, and no goal count: a process map holds no goals.
- **Two views at once.** A grip on each edge of the canvas, dragged inward, reveals a second pane
  behind a separator (left or right: side by side; top or bottom: stacked); the separator resizes it,
  a double-click halves it, dragged back to the edge it closes; the edge and size are remembered in the
  browser. The second pane is the page itself in a frame, a whole diagram with its own pan, zoom, open
  systems and view (the other one at first), and its own view switch; the panes never follow each
  other's pan or zoom. They share the selection, and a shape pointed at in one lights what it is in
  the other, to be found at a glance: a thick ring that keeps its width at any zoom, haloed and pulsed
  once, with the rest of that pane stepped back. While the split is open the side panel and a part's
  panel are drawn over the pane clicked in, so the diagrams keep the whole width. At phone width there
  is no split.
- **Colour by correspondence** (the ⋯ menu, remembered; or C held). Off by default. Every shape of the
  dynamics and block views, in both panes, a closed system's box and an open one's outline included, is
  ringed in the colour of the model part it is (`correspond.colours`: one slot per part, the same in
  every view), so what stands for each other in the two views shares a colour; a shape that is several
  parts (a controller: its block, its valves, its setting) takes turns of each round its outline. Ten
  muted qualitative hues, then each again darker, then lighter; parts that touch get different hues.
  The ring for a part pointed at in the other pane takes its colours while they are shown.
- **Export** (the zoom bar's Export menu): "SVG" and "PNG" write a standalone file with a header (project, system, view,
  when) and, for the control view, a one-line legend, every style resolved; "Design SVG" leaves out
  what changes minute to minute (values, rates, status, decisions, trends) for a design document; `ergostat snapshot` writes the whole page and its answers as one
  HTML file that opens offline (agents' logs only with `--with-logs`). The model behind the picture, as Markdown, for
  the system drawn: Dynamics' "Model (Markdown)" (a variable table: name, kind, unit, equation or sensor, now; the
  flows per stock; the feedback loops of the side list, with the goal each closes) and Blocks' "Loops (Markdown)" (a
  row per goal in the system drawn, the goal or the part it holds inside it at any depth: goal, reference, measured output, controller and its law in the panel's words, actuator,
  process, sensor and period, status). The server writes them (`GET /api/export?view=dynamics|blocks&system=S`,
  `format=md` by default, `json` for the page), so `curl` gets the same file; a snapshot file says it cannot.

## 7. The command line

`ergostat agent NAME --now` runs one agent at once, recorded like any run, and prints what it said;
it is how an agent is tried while it is being written (`docs/writing-agents.md`, shipped as
`ergostat help agents`).

People fill roles too, and say what they did: `ergostat valve NAME --opened N [--note]`,
`ergostat sensor NAME --read V`, `ergostat controller NAME --decided TEXT`, only for roles a person
fills, checked like any agent's lines and recorded as that person. These are records of what was
done, not changes to the system; a valve a person fills is manual unless the file says otherwise.
A plainly wrong reading is set aside with `ergostat sensor NAME --forget-above V` (or
`--forget-below`): kept apart, out of every estimate, with the crossings it caused, and recorded.
`ergostat run --service` prints a launchd agent or systemd unit that keeps the runner up; it
installs nothing.


`ergostat [TOPIC] [NAME] [FLAGS]`; topics are nouns, a name shows one. Bare `ergostat` is the
status. `system` draws (`--all`, `--around PART`, `--wiring`, `--list`, `--open`); `loop` adds each
part along the loop, its crossings and decisions; `agent`, `event` (`--follow`), `item`,
`residual`; the parts one at a time; `check`, `run`, `web`, `chat`. Every topic takes `-s SYSTEM`,
`--since`, `--at` (a past moment: the state is estimated as it was then, over the window before it)
and `--json`. Nothing on the command line changes the system except `run` and `chat`.
The review rounds that shaped it are in `docs/cli-rounds.md`.

## 8. The web page

Every page is a path, so its links are ordinary links (opened in a new tab, copied, reloaded):
`/diagram?view=blocks`, `/goals` (its old address `/loops` goes there, keeping its query), `/agents`, `/items?kind=K&state=S`, `/item/ID` (the id encoded, its `/` as
`%2F`), `/record?type=T`, `/model`, `/check`, `/guide?frame=N`. The server answers each with the page
(`UI_PAGES` in `web/server.py` and `util.js`, one list); `/api/*`, `/static/*` and `/file/PATH` are never
shadowed. The page routes with the History API: a plain click on one of its links draws the page in
place; a ctrl-, cmd-, shift- or middle-click is the browser's. An old address, `#/items` or
`/#/item/ID` from a bookmark, a brief or a message, is shown at its path. A snapshot, one file opened with no
server, keeps its routes in the hash (`snapshot.html#/items`).

Standard-library server on 127.0.0.1 (port 8781, the next free one when taken; *decided in the
owner's absence*), read only but for one kind of write: the owner's answer to a proposal (Accept,
Approve or Dismiss), asking for estimates (Calibrate, Estimate now) and proposing the values tried as a
what-if (Propose these), each a `POST` the page makes. A request is served
only when addressed to the server by its own name (the Host header is `127.0.0.1`, `localhost` or
`[::1]` with its port: a page on another site whose name was pointed at 127.0.0.1, DNS rebinding,
sends its own), and a write only from the page's own origin (Origin, Sec-Fetch-Site) carrying the
token this run of the server wrote into the page it served (`X-Ergostat-Token`), which no other
page can read; a snapshot offers none. Pages: Diagram (dynamics, blocks and process views; the side panel:
attention, goals and their control loops, feedback loops or the process map's kinds, model changes, legend), Goals, Agents (one list, by rung), Items (the
record folded by id, by kind and state), Record (events, with runs hidden by default), Model (`/model`;
its old address `/fit` goes there; first **What's available**: each loop, whether its process is
identified and what would identify it, or that it closes through queues; each parameter to estimate,
the parts it is in and whether the record is long enough yet; and where each model tool lives, every
link choosing the part and opening its view and panel; `docs/MODEL-TOOLS.md` is the guide; then the
review queue: every change waiting, read like a pull request, each with what kind of change it is, where
(Show on diagram chooses its parts and opens both views), why, how it was found, its benefit, its effect
simulated in memory and the exact diff Accept writes; Simulate all pending; what ergostat can and cannot
propose yet; then, over the
last day of record, whatever the window: the model fit, the stocks its equations move, with the
total; each equation with its inputs as measured and replayed; accounting, the stocks moved only by
measured flows; each with R², MAPE, Theil's U_M, U_S, U_C and what a large error says, or "too
little record"; the total led by its scaled error; the fit's history across versions with the span each covered and
each accepted change; Calibrate (each part alone, each system alone, or every stock integrated, with the
loops a decision leaves open listed), the proposals waiting,
and why the estimates not proposed were not; and the residuals),
Check, and a Guide: a sequence of frames, one line each, every frame a tiny built-in model drawn by
the real dynamics and blocks renderers (`ergostat/guide.py`), with its behaviour over time beside
it (why: what we control and what we want; system dynamics; control; then the project's own model,
both ways). Clicking a part opens what `ergostat <topic> <name>` shows, in the detail panel, which
takes the side panel's place. Behaviour over time sits beside the structure, never on a page of
its own (`docs/proposals/charts.md`, drawn with uPlot, vendored): a part's panel in the dynamics
view opens with its causes strip (it, then what drives it, on one time axis; where the model works a part
out, its replay dashed over the measured line and its projection past now dashed and lighter: open
loop, the controllers held, so it is left out downstream of a flow a block sets; the projection's
Monte Carlo fan shaded, a short projection given the chart's last quarter on its own time axis, the
spread over the record on request, a what-if in the accent: SPEC §12c), a
valve's and an auxiliary's panel show its equation in MathML with each parameter's value and
provenance, its calibrations side by side, and any proposal for it, with Accept (each value may be
typed over: a what-if, drawn on every chart until put back, its fit shown beside it, saved only by
Propose these and then Accept), a feedback loop's panel how much of the behaviour it drives over the
window at each stock it runs through, beside the loops competing there (loop dominance), parts chosen with
Shift chart in the side panel (with none chosen, no chart); a goal's panel, its
comparator, controller or output in the blocks view, and its sparkline on the Goals page open its
scope (y with r, u, e), and under it how its control loop is doing (Harris index or, for a ceiling or a floor,
how often and how far past it, oscillation, settling and overshoot, saturation, step tests and starts
left out; the Goals page says it in a word, or what it lacks); in the blocks view, the process block a
loop's y comes out of shows that loop's process identified (K, τ, θ, how sure, how tested, its step
response and Bode plot, with Accept, or a step test to Approve, or why none is offered yet), and its
controller's panel the closed loop with it (margins, at the worst the process could be too, its own
delay, what the linear numbers leave out, step response, Bode) and a SIMC tuning or a detuning (SPEC
§12c); a block's dead band is drawn before its law as a dead zone; the Items page draws each
kind's cumulative flow and cycle times. Every
chart in one place shares its cursor and covers the page's window. One control in the header
holds the window and the moment: its menu sets the window and slides the page to a past moment
(the API's `at`), with "Back to live". Light theme first, a dark one from the same tokens; usable at
phone width.

### 8.1 How it looks, and why

ergostat is an instrument, so it looks like one. The references are tools whose quality comes from
restraint and a strict notation, not from personality: Linear and Grafana for density, tables and
side panels (Grafana's first principle: "don't get in the way of the data"); Observable for pages
that are mostly figures with a line of text; Vensim and Stella, and the figures in Sterman's
*Business Dynamics*, for the dynamics view; Åström and Murray's *Feedback Systems* figures for the
blocks view. The method is Refactoring UI's (limit the choices, set the scales first, design in
greyscale and add colour last, de-emphasise to emphasise, labels are a last resort) and Tufte's
(maximise data-ink; erase what is not data, then what repeats it; thin, light lines for structure
so the data reads on top). The craft checklist is Vercel's Web Interface Guidelines. The research
behind this, with the tells of a generated UI it removes, is kept outside the repository
(the redesign's `RESEARCH.md`).

The diagrams keep their notations (§6): the dynamics view is Sterman's and Vensim's, the blocks view
a textbook block diagram, monochrome, functions in the blocks. This section is about everything
around them, and their chrome and type.

**Decisions.** Every value below is a custom property in the one token block at the top of
`ergostat/web/static/style.css`; nothing else in that file may write a colour, a font size, a
radius or a spacing, or use `!important` (`tests/test_style_tokens.py` fails it).

- **Type.** One typeface for everything, the platform's own UI face (`system-ui`: San Francisco,
  Segoe UI, Cantarell or Roboto), chosen because it is built for dense interfaces, has tabular
  figures, needs nothing loaded and works in an offline snapshot. Numbers are always
  `tabular-nums`. Monospace only for ids, code, patterns and raw event data. Four sizes for the
  interface: 12 (meta, table headers, captions), 14 (body), 17 (panel and section titles), 22
  (page titles); and three for drawings: 11, 12, 13. Two weights, 400 and 600. Headings in sentence
  case, never upper case, never letter-spaced.
- **Space.** 4, 8, 12, 16, 24, 32 and 48 px (and 2 px for hairline offsets). More space around a
  group than within it.
- **Radius.** Two: 4 px for controls, inputs, code and menus; 6 px for the menus' own box. The
  diagrams' shapes keep their notations' corners (a stock is a rectangle). Circles are circles.
- **Colour.** A neutral ramp of eight steps with a slight cool bias (OKLCH hue 250, chroma under
  0.015): cool because the tool sits beside terminals and editors, and warm cream is a tell of its
  own. Not pure grey: the bias keeps the page from looking unfinished. Ink is not black (about 13:1
  on white), so long reading is not harsh; muted text stays above 4.5:1. Hue is reserved:
  red for off or failing, amber for open or a warning, *nothing* for fine (a healthy row is
  plain); one blue accent for interaction only (links, focus, the selected thing, what is pointed
  at), never for data or decoration. Lines in charts are ink; a setpoint is a muted dash. The one
  line in the accent is a what-if: not the record nor the model, but values the owner is trying
  now, which go when they put them back (interaction state, so the accent). A projection's fan is
  two greys of its own (`--fan-90`, `--fan-50`, darker than the gridlines so it never reads as one): nine
  in ten of its runs, and half. A projection too short to see on the window's axis gets the last
  quarter of the chart, on a time axis of its own past now (+20s, +40s). A loop's dominance draws it in
  ink and the loops competing at the same stock in the muted grey.
- **Themes.** Light first. The dark theme follows the system setting and is the same ramp read
  the other way, with the same hues, generated from the same OKLCH values (the hex values in the
  token block say which).
- **Surfaces.** The canvas and pages are the plain surface; the header and the side and detail
  panels sit on a faintly tinted one, divided by hairlines (1 px, the lightest line). No shadows,
  except under a menu, which floats. No cards, no boxes in boxes, no coloured side stripes.
- **Status only for exceptions.** A loop holding says nothing; one off says "off" in red. No status
  dots, pills, chips or badges on rows; a state is a word in a column.
- **Controls.** The few that matter are visible; the rest are in a menu inside the toolbar that
  already holds them (the diagram's "⋯" and "Export" menus). Buttons are quiet (borderless) unless
  they are the selected one of a set. Nothing shifts when it is chosen: the active tab is marked by
  colour and a rule, not by weight. Hit targets at least 24 px. One hover style, one focus ring
  (2 px accent, outside). No animation on frequent actions.
- **Tables.** Hairline rules between rows only: no outer border, no rounded corners, no header fill.
  Numbers right-aligned, headers too over numbers. A wide table scrolls inside its own box; the page
  never scrolls sideways.
- **Numbers.** One formatter (`fmt` in `util.js`): integers as they are, with thousands separated;
  others to three significant figures; a real minus (−). Raw data on the Record is shown whole,
  never rounded. Setpoints and conditions use the
  real symbols: ≤, ≥, =, ≠, −, ×, and … for an ellipsis. Subscripts are subscripts (K<sub>p</sub>,
  not K_p).
- **Times.** One formatter (`stamp` in `util.js`): `2026-11-22 04:03:55 PST`, the date, the time and
  the browser's zone by its short name, on the Record, a goal's Crossings, the Items page and an item's
  page. A field named `*_at`, `raised`, `since` or `started` holding epoch seconds or ISO text is
  shown the same way.
- **Copy.** No paragraph under a page's title: what a thing is belongs to the Guide. Labels are
  terse and specific; a panel opens with what the thing is now, not its definition. Sentence case
  everywhere. No " · " chains to fake structure: two lines, or a label and a value. No arrows on
  links. Empty states say what is missing in one line; a panel whose model tool is not available yet
  (no equation, so no what-if; no process, so no margins) says why and what would make it available,
  in one line, never nothing.

## 9. Not yet

- **Approvals.** A valve's `mode` is recorded and drawn; nothing waits for the owner yet. Whether
  approving at a valve is a command (it would be the command line's one write) is the owner's call.
- **Discovery.** Inferring the system from measurements alone. The record keeps what was declared
  and what was measured apart, so it can be added.
- **Cascades.** A controller setting another's setpoint is not modelled.
- **Channels.** The pub/sub topics as their own topic (`ergostat channel`) wait for a scenario
  that needs them.
- **Several repositories at once.** Each repository has its own record and page. `ergostat projects`
  lists every project on the machine (its record's folder remembers the repository) and the page
  header switches between running ones; one page drawing all of them together is not built.
