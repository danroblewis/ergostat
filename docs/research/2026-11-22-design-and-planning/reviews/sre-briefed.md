# ergostat: briefed review by an SRE

Persona: an SRE who works from dashboards, alerts and runbooks. My questions are what this tool adds and what I do when something is off.

I read `intent.md`, `docs/WHY.md`, `docs/DISCIPLINES.md`, `docs/DECISIONS.md`, the relevant parts of `docs/SPEC.md` (the HTTP API, `notify:` and the inbox), the modelling template (`ergostat/library/templates/modelling/template.yaml`) and every demo README. Then I walked the demos again: the-job :8792, which I skipped blind even though it is the SRE's own job; ticket-factory :8791; image-squeeze :8793; and big :8797. I checked desktop at 1440x900, phone at 390x844 and dark mode. New screenshots use the prefix `shots/sreb-`. The blind ones keep `shots/sre-`.

## What I got right and wrong blind

Blind, I read it as a control-loop and SD console for an "AI software factory", built for its owner rather than for on-call. That was half right.

- **Right:** loops, setpoints, actors, gated outward actions, and read-only for people.
- **Wrong:** it is not a factory console. It is meant to be a **model of any running system** that sits *on top of* the monitoring and alerting I already have. It is meant for engineers and SREs as one of its two named audiences. It moves the question from "what is the number" to "which loop failed to hold it, why, and what fixes it".

That pitch is exactly what I would want. The UI does not say it.

---

## 1. Where the application failed to tell me what it is for

1. **The first screen is blank boxes.** The-job opens on two outlined rectangles: "job, 28 feedback loops inside" and "modelling, 11 feedback loops inside" (`sreb-job-home.png`). Big opens on seven of them (`sreb-big-home.png`).
   - Nothing on the canvas says what the system is, what it holds, or whether it is healthy.
   - The one-line purpose each system has in its YAML shows as "…" in the module panel (`sreb-is-measure-click.png`).
   - "N feedback loops inside" is a count of structure. It is not a status.
2. **The loudest red on every demo is ergostat grading its own model.** `requests-handled` and `model-fits` belong to the `modelling` subsystem (the template says so: "everything check finds answered"). They top Needs attention, the Loops table and the Agents page in every demo, without a `modelling.` prefix.
   - A newcomer concludes that the operated system is failing, or that the tool is broken.
   - Neither is true: these loops are the tool's housekeeping.
3. **The Blocks view, the "what is controlled" perspective, shows no control.** The-job shows two unconnected boxes, `Q_job` and `Q_modelling` (`sreb-job-blocks-fit.png`). Big shows seven `Q_x` boxes stacked in a column (`sreb-big-blocks.png`).
   - There is no reference, no summing junction, no error signal, and nothing marked off.
   - A control engineer cannot tell what is regulated. An SRE cannot tell what is broken.
4. **The "control panel" the image-squeeze README promises is not drawn.** The README says that with every system closed, "each system's box shows its measures, each with its value, setpoint, health and trend". The boxes show only names and values (`sreb-is-closed.png`).
   - "excess bytes-per-mp 51.4" carries no setpoint (20), no red and no sparkline.
   - That control panel *is* the answer to "what is this for". It is the alert surface I came looking for, and today it exists only in the docs.

**What would have made it obvious, within the decisions** (no new pages or panels, two separate diagrams, only recognised types):

- **Make the closed-system diagram the control panel by default.**
  - Each system box carries its purpose line in place of "…".
  - Each box shows its goals as rows: value, setpoint, a status mark and a trend.
  - The box frame takes the colour of its worst loop, and its title carries "2 off".
  - This uses the system boxes and their exposed parts, which the owner already named as the place to show things.
- **Namespace and demote the meta-system.**
  - Label it `modelling.requests-handled`.
  - Draw the `modelling` box apart, as "about this model".
  - Keep its loops out of the header's "N loops off".
- **Draw the Blocks top level as a block diagram**, with the hierarchy wired: each system's outer loop as r → Σ → C → P → y, with H on the feedback path. A collapsed subsystem block keeps its transfer-function label. Draw an off loop's e signal in the error colour.

---

## 2. My earlier findings, revisited

| # (blind) | Finding | Verdict now |
|---|---|---|
| 1 | Approve/Deny in a reordering live list | **Stands (major).** I could not re-trigger pending action approvals this pass. The list is still live and reorders, and the person ask (`person/approve@3156`) still sends me to the CLI (`ergostat actions`) to see what waits. |
| 2 | `requests-handled` always red | **Partly a misunderstanding, and worse than I thought.** It is not a broken production loop. It is the modelling subsystem's own queue of model-housekeeping requests, which the fixer can never catch up on (about 4/h out against about 150 to 480/h in). Showing it unprefixed, first and red in every demo poisons the whole alert surface. |
| 3 | No machine-readable output, no deep links | **Partly a misunderstanding.** `/api/loops`, `/api/inbox`, `/api/items` and `/api/series` exist and answer JSON, and the SPEC has `notify:` channels (Slack, email, Discord, command) with grouping and quiet hours. **Still standing:** the header "2 loops off" is a `<span id="running">`, clicking a loop leaves the URL at `/loops`, and there is no Prometheus exposition or Alertmanager-style output, so I cannot page through my existing on-call tool. That matters more now that the intent says it sits *on top of* that tooling. |
| 4 | "0% time off" hides flapping; behaviour label flips | **Stands.** The-job shows "past its bound 5%" next to "time off 1%" and "oscillates, 5.09 s" on a loop that is holding. |
| 5 | Rates climb with nothing in flight | **Stands.** Ticket-factory still shows `address 5.23 tickets/min` and `work 31.5 tickets/h` while every factory stock is 0 (`sreb-tf-home.png`). Needs attention still reports unexplained stock changes. |
| 6 | System boxes show no health | **Worse.** The README promises setpoint, health and trend on each box, and the UI shows none of them (see section 1). |
| 7 | Process view blank on big | Stands (not re-walked). |
| 8 | Needs attention flooded by modelling requests | **Worse.** On big, 24 near-identical "modelling holds no-unit on stock.X-qN" requests offer only Deny, under "24 asked this week, 0 approved" (`sreb-big-home.png`). The same request reads "decision tier" in Dynamics and "rule tier" in Blocks. |
| 9 | Missed runs not flagged | Stands. `judge` shows "not run here · every 30s" in grey (`sreb-tf-agents.png`). |
| 10 | Agents headline counts contradict sections | **Stands.** The headline says "2 person"; the section below says "0 person" and lists 2 rows (`sreb-tf-agents.png`). |
| 11 | Model page `href="#"` links | Stands (not re-walked). |
| 12 | No runbook guidance | **Stands, and sharper.** The loop panel for the-job's `tickets-within-sla`, a *person* loop, says "Its valve did not open", "Moves nothing", "Not worked out: it has no one process". It does not link to the waiting ask `person/run-commands@2066`, which is the actual next step (`sreb-job-loop-panel.png`). |
| 13 | Header off-count jumps | Stands: 2, 3, 4 and 5 within a minute on the-job. |
| 14 | Module loop counts disagree | **Stands.** The service box says "22 feedback loops inside"; its panel says "16 inside and 17 through it"; its description is "…" (`sreb-is-measure-click.png`). |
| 15 | Open overflows and does not re-fit | Stands (not re-walked). |
| 16 | Blocks wire labels overlap | Stands (not re-walked). |
| 17 | Items chart grey-only | Stands (not re-walked). |
| 18 | Record timestamps lack date and zone | **Stands.** The Record is also flooded with `auxiliary.set {"value":0}` every 5 s from `teammate` (`sreb-tf-record.png`). |
| 19 | Phone Loops hides now and setpoint | **Stands,** in dark too (`sreb-job-phone-dark-loops.png`). |
| 20 | Items table cut off | Stands (not re-walked). |
| 21 | Check page run-on warnings | Stands (not re-walked). |
| 22 | Console `ShapeConnectionPin` errors | **Stands, and wider.** It now appears on the Blocks views of ticket-factory and the-job too. |
| 23 | Guide is a generic SD tutorial | **Partly a misunderstanding.** Teaching the two disciplines is intended. Still, nothing tells an SRE how to read *this* system's off loops. |
| 24 | Error sign and wording inconsistent between views | **Misunderstanding in part.** Dynamics says "excess/gap" and Blocks says "setpoint … (off by)" on purpose, each in its discipline's words. **Still wrong:** Dynamics writes "desired X = 0" for a `≤ 0` bound and "desired quality = 0.93" for a floor. |
| 25 | No hover tooltips | Stands (polish). |
| 26 | Truncated "how ma" placeholder; CLI reference | Stands. |
| 27 | Dark mode clean | Stands. Dark mode is good (`sreb-is-dark-home.png`). |

New findings this pass: the Blocks top level shows no control at all; the inbox link `?around=block/approve` lands on the unchanged top level (`sreb-tf-blocks-around.png`); the Loops table has no system column; the Blocks symbol `Q` is not one control engineers use and is undocumented; the Record is full of unchanged auxiliary sets.

---

## 3. Where the UI contradicts the intent

- **"Systems are namespaced" (decision 5).** Loops, stocks and suggestions appear unprefixed everywhere: `requests-handled`, not `modelling.requests-handled`. The Loops table has no system column at all.
- **"A control panel is the diagram with everything else folded away" (decision 1).** The folded diagram shows structure counts and values without setpoints or status. It shows less than the Loops table, so the Loops table and the Needs-attention text end up doing the control panel's job.
- **"Blocks: what is controlled … r/e/u/y, the definition on click" (decision 2).** The top level is a column of disconnected `Q` boxes with no r/e/u/y. The inbox's link to a block (`around=block/approve`) shows nothing more than the top level.
- **"On top of existing tools" (intent).** The page is built as a destination: header badge, sidebar, CLI pointers. It does not feed the tools that already page me: no metrics exposition, no Alertmanager webhook, no stable link per loop.
- **"Large systems matter" (decision 6).** On big, the modelling subsystem's 24 requests crowd out the six real systems in Needs attention, and the seven boxes are indistinguishable.

### What it does well and should keep

- **The loop panel** (`sreb-job-loop-panel.png`). It has y with r and the time off shaded, u, e, the last decision, the crossings list, the decisions grouped "alike when only their numbers differ", and "it holds again 30s after (slowest 30s, 2 times)". That is a better incident view of one SLO than any dashboard I own. Keep it and make it linkable.
- **Suggestions with Evidence.** "Falling behind: its flow moved 4.9/h out while 483/h came in … its decision (fixer, every 1m) is the slowest stage" is a real diagnosis in plain numbers.
- **The demo switcher carrying off-counts per demo** ("image-squeeze (8 off)"). It is a ready-made fleet view.
- **Read-only, with gated actions and a weekly record per class** ("24 approvals of jira-transition … suggest"). This is the right trust ladder for automation.
- **The image-squeeze closed diagram with values on the ports** (`sreb-is-closed.png`). It is the start of the control panel and needs only setpoints and status added.
- **Dark mode.** It is clean, and red stays readable (`sreb-is-dark-home.png`).
- **The JSON API** (`/api/loops` carries status, setpoint, error, last_decision and gaps). The machine-readable layer exists. Only the bridge to my tools is missing.

---

## 4. Significant changes I would make

### A. The system box becomes the alert surface (Dynamics view, closed systems)

```
┌─ service ─────────────────────── ● 2 off ─┐   frame: red if any goal off,
│ squeeze, serving the images customers send│   amber if unknown, ink if holding
│ ● quality         0.921  ≥ 0.93   ╱╲_╱    │   one row per goal on an exposed part:
│ ● bytes-per-mp    45.1   ≤ 20     ‾‾╲_    │   status dot · value · setpoint · trend
│ ○ failures        0      ≤ 0      ____    │   (window = the header's)
│   batch-time      19.3 s                  │   plain values stay as today
└───────────────────────── Open  Into ──────┘
```

Clicking a goal row opens the existing loop panel. No new panel is needed: the box and its exposed parts already exist. In SD terms a goal is a goal-seeking auxiliary, so drawing it on the module's port is true to the discipline.

### B. The modelling meta-system is separated, not hidden

- Prefix it everywhere: `modelling.requests-handled`.
- Draw its box at the canvas edge, dashed: "about this model, not the system".
- Leave it out of the header count. The header reads "2 loops off" for the operated system and, greyed beside it, "model: 2 off".
- In Needs attention, fold its requests into one row: "modelling: 24 requests (no-unit ×24) ▸".

It stays observable, and it stops burying operations.

### C. The Blocks top level is a real block diagram of the hierarchy

```
 r_web ─►(Σ)─e─►[ C_web ]─u─►[ P_web ]──┬─► y_web
          ▲−                            │
          └───────────[ H ]─────────────┘
          ...one row per system, its outer goal on top;
          a collapsed subsystem is the P block, labelled with its loops
          ("P_api: 4 loops, 1 off"), e drawn in the error colour when off
```

Drop `Q`. Use the textbook symbols (`P` or `G` for a plant, `C` for a controller). The `around=` link should open and outline the named block, not repeat the top level.

### D. Needs attention restructured into three fixed groups (same sidebar, no new panel)

1. **Off now:** operational loops only, sorted by time off, not by arrival.
2. **Waiting on you:** person asks and gated actions, in a **frozen order** keyed by id. Each entry names the action, its arguments and its target, inline, so nobody has to reach for `ergostat actions`. Approve sits on the row, never on a moving list.
3. **Model housekeeping:** grouped counts, collapsed.

### E. A runbook inside the loop panel, from the model

Replace "Not worked out: it has no one process" and "Its valve did not open" for person and program loops with one block:

> **If this is off:** *run-commands* (a person, you) acts on it. It is waiting on **person/run-commands@2066**, asked 6 min ago → [Done]. It last ran 32 s ago: "act: run-commands". It typically recovers in 30 s; it has been off for 4 min, **past its typical recovery**. Suggestion: … [Evidence]

All of it is already in the record. It only needs saying in operational order: who acts, what it waits on, whether this is unusual, what to do.

### F. Feed the tools that page me ("on top of", not instead of)

- `GET /metrics` exposing `ergostat_loop_off{system,loop}`, `ergostat_loop_error`, `ergostat_loop_time_off_ratio` and `ergostat_inbox_waiting{class}`, so Prometheus and Alertmanager page on a loop the way they page on anything else.
- Stable links: `/loops?loop=web.q2-low&window=1h` opens the panel, and `/diagram?around=loop/web.q2-low` outlines it. The header badge links to `/loops?status=off`.
- A `notify:` channel type `alertmanager` beside slack and email, carrying the same minimal payload.

None of this adds a page. It makes ergostat one more source in the on-call path, which is what the intent says it is.

### G. The Loops page grouped by system, honest about flapping, readable on a phone

- Group the rows under system headings (job, modelling, …), with modelling collapsed.
- Add a "crossings" column beside "time off", and debounce the behaviour label.
- At 390 px, render each loop as a two-line card: `● name   now / setpoint` on the first line, `off 4m · back in ~30s` on the second.

### H. Numbers say what they are

- Every rate on a port says its window ("5.2/min over 10m").
- A rate fades to "–" when nothing moved in the window.
- Large unexplained stock changes go to model housekeeping, not to operational attention.
- Record timestamps carry date and zone.
- Unchanged `auxiliary.set` values are collapsed ("×120, value 0").

## Bottom line

The intent is exactly what an SRE would want: SLOs as loops with a named actor, explained and fed into the tools I already use. The UI hides that intent in three places:

- It leads with the tool's own model housekeeping.
- It draws structure where the status should be.
- Its control-theory view shows no control.

Put status on the system boxes, wire the Blocks hierarchy, separate the meta-system, and bridge to Alertmanager. The same pages would then make the case on the first screen.
