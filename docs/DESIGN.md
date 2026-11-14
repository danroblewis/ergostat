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
| `[[disturbance]]` | a flow no valve controls | `into` or `out_of` |
| `[[valve]]` | where an agent acts, on one flow | `flow`, `agent`, `mode` (auto, advise, manual) |
| `[[sensor]]` | measures a stock or a flow | `measures`, `agent`, `unit` |
| `[[controller]]` | holds a stock at a setpoint | `holds`, `setpoint` (`<= 80`, `>= 1`, `== 0`), `tolerance`, `reads` (sensors), `drives` (valves), `agent` |
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

Two stores, kept apart because there are few events and many measurements, both SQLite files in
`$ERGOSTAT_HOME/<name>-<8 hex of the repository's path>/` (default home `~/.ergostat`;
*decided in the owner's absence*). Each thread keeps its own connection open (opening and closing
connections from many threads deadlocked inside SQLite's file locking).

- **`events.db`**: `events(seq, id, time, type, item, source, causedby, data)`, append-only,
  indexed by item, type, time and cause. An event's `item` is what it is about; an item is the fold
  of its events.
- **`measurements.db`**: `samples(series, time, value)`. A sensor's readings are the series
  `sensor/<name>`.

ergostat's own event types (agents may not publish them): `agent.started`, `agent.ran`,
`agent.failed`, `agent.refused`, `valve.opened`, `controller.decided`, `loop.off`,
`loop.holding`, `model.changed`, `ergostat.started`, `ergostat.stopped`. `ergostat item` lists
only items that other events are about (the user's things); `--all` adds the parts.

## 4. Running agents

`ergostat run` starts a background process (`run --foreground` stays attached; `run --stop`) that
serves the web page and runs every agent that has a command and is not a person:

- **When**: `every` (a duration), `cron` (five fields, local time), or `on` (event-type globs,
  never its own events). One run at a time per agent; a scheduled run is skipped while the last one
  still waits.
- **Given** on stdin: the agent, its roles, every stock's current value, its controllers'
  setpoints, values and errors, and the triggering event.
- **Says** on stdout, one JSON object per line, naming the part:
  `{"sensor": N, "value": x}` (a measurement), `{"valve": N, "amount": x}` (`valve.opened`),
  `{"controller": N, "decision": "..."}` (`controller.decided`), or
  `{"event": TYPE, "item": ID, "data": {...}}`. Anything else goes to the agent's log.
- **Discipline**: a line naming a part the agent does not fill, or one of ergostat's own types,
  is refused and recorded as `agent.refused`. Every agent acts only through the roles it fills.
- **The edge detector**: after a reading, each loop that sensor serves is compared with its last
  crossing; a change records `loop.off` or `loop.holding`. This is the one place a measurement
  becomes an event.
- **The model's history**: each load that differs from the last recorded one records
  `model.changed` (added, removed, changed parts). A running ergostat notices an edited file; when
  it loads without errors it restarts itself in place (same process, same page).

## 5. The state estimate

Over a window (default 1 hour), with every rate taken over the time actually recorded:

- **A stock's value** is the latest reading of a sensor that measures it; unmeasured is unknown.
- **A flow's rate** (per hour) is its sensor's latest reading, else the amounts its valve opened.
- **A residual** is a stock's change minus what its known flows explain (valve amounts between the
  first and last reading; measured flows integrated over time). When an unmeasured disturbance
  pushes that stock, the residual is its estimate; otherwise it is unexplained when larger than
  5% of the flow and twice an ordinary non-zero step between readings (timing at the window's
  edges is noise).
- **A loop** is open (cannot close), unknown (no reading), holding (within setpoint ± tolerance)
  or off. It cycled when a reading and a decision or opening both fell in the window.
- **Hints** (the refactor path): a controller filled by a person, an AI agent or a decision that
  decided the same thing (numbers taken out) at least 80% of at least 10 times could be filled by a
  lower rung.
- **Attention**, most important first: loops off, loops open, agents failing, lines refused,
  missing readings (only while running), hints, unexplained residuals.

## 6. The diagram

The control diagram is the product's main view. Conventions:

- **Shapes**: a stock is a tank (its fill and setpoint line drawn to scale, a trend along the
  bottom); a flow is a pipe; a valve is a bow tie on the pipe (filled: auto, half: advise, open:
  manual); a disturbance is a diamond with a wave; outside the boundary is a cloud; a sensor is a
  gauge; a controller is a box with a summing junction, its setpoint, status and last decision.
  Every role carries a badge: the agent's kind, name and schedule, coloured by rung.
- **Lines**: pipes are double lines with moving dots while they flow; measurement is dashed
  (stock to sensor), signal solid (sensor to controller), action purple (controller to valve).
  A loop's lines take its status colour (green holding, red off, amber open).
- **Layout** (ELK layered, vendored): the plant runs left to right along the pipes (pipes carry the
  highest straightness and direction priority), the feedback path above it; each loop a row.
  Systems are drawn as outlines in their own colours (golden-angle hues), overlapping where they
  share parts, labels never stacked. A long chain can be folded into rows ("wrap"). Fit never
  shrinks text below legibility; a bigger system is panned and zoomed.
- **The wiring view** draws agents (coloured by rung, with schedule and roles) and an arrow when
  one agent's output reaches another: through a sensor or valve it hands on, through a stock, or
  through an event type it listens for. It runs top to bottom.
- **The block view** draws each loop as a classic negative-feedback block diagram, one row per
  loop: the setpoint r into a summing junction (Σ, + and −), the error e into the controller C, its
  output u into the actuator (the valve), a second junction where the disturbance d joins, the
  plant (the stock), its output y, and the sensor H on the feedback path carrying ym back to Σ.
  Every block names the agent that fills it; the loop's lines take its status colour. The command
  line prints the same in text (`ergostat system --blocks`).
- **Export**: "save SVG" writes a standalone file, every style inlined.

## 7. The command line

`ergostat [TOPIC] [NAME] [FLAGS]`; topics are nouns, a name shows one. Bare `ergostat` is the
status. `system` draws (`--all`, `--around PART`, `--wiring`, `--list`, `--open`); `loop` adds each
part along the loop, its crossings and decisions; `agent`, `event` (`--follow`), `item`,
`residual`; the parts one at a time; `check`, `run`, `web`, `chat`. Every topic takes `-s SYSTEM`,
`--since`, `--at` (a past moment: the state is estimated as it was then, over the window before it)
and `--json`. Nothing on the command line changes the system except `run` and `chat`.
The review rounds that shaped it are in `docs/cli-rounds.md`.

## 8. The web page

Standard-library server on 127.0.0.1 (port 8781, the next free one when taken; *decided in the
owner's absence*), read only. Pages: Diagram (with the side panel: attention, loops, model changes,
legend), Loops, Agents (the ladder, one column per rung), Record (events, with runs hidden by
default; items), Residuals, Check. Clicking a part opens what `ergostat <topic> <name>` shows.
A slider in the header moves the whole page to a past moment (the API's `at`), with
"back to live". Light and dark themes; usable at phone width.

## 9. Not yet

- **Approvals.** A valve's `mode` is recorded and drawn; nothing waits for the owner yet. Whether
  approving at a valve is a command (it would be the command line's one write) is the owner's call.
- **Discovery.** Inferring the system from measurements alone. The record keeps what was declared
  and what was measured apart, so it can be added.
- **Valve positions and cascades.** A valve's opening is an amount per run; how far open it stands,
  and a controller setting another's setpoint, are not modelled.
- **Channels.** The pub/sub topics as their own topic (`ergostat channel`) wait for a scenario
  that needs them.
