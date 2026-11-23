# Making sensible dashboards and panels

For people and agents building a page on ergostat's Dashboard (`/dashboard`). A dashboard is a grid of panels kept
as a draft in the page's address and in the browser (nothing is written to the server); each panel is a
`chartPanel` config: a title, a note, a form, its options, how it is displayed, and the queries it asks of
`GET /api/query` (SPEC §4e). Every panel config below is a real one: a test loads each and asks its queries of the
query API (see *How this document is checked*, at the end).

The diagrams come first in ergostat (CLAUDE.md, invariant 9): a dashboard is for the numbers a diagram does not
show at a glance, read by someone who has a decision to make.

## 1. Start from the question and the decision

Before a panel, write two lines:

- **The question** it answers, in the words of the person who asks it: "is work flowing?", "are we spending more than
  we planned?".
- **The decision** its answer supports: "if completions fall below arrivals for a day, add an agent to *working*";
  "if today's cost passes the budget, pause the AI tier".

The question becomes the panel's `title`, the decision its `note`. **A panel with no decision is removed**: if no
answer it could give would change what anyone does, it is decoration, and it costs a query on every refresh and a
moment of every reader's attention. "Interesting" is not a decision. A panel kept only "in case" is a log search
waiting to be asked when the case comes.

## 2. Layout

- **The headline state first**: the top row answers "is everything all right?" in one look, as a few stat panels
  (size `s`, a quarter of the row each), each with its goal as a threshold.
- **Then rates**: what is flowing in and out, a row of line or bar panels (size `m`, half the row).
- **Then detail**: where it is stuck, what it cost by group, the tables for looking things up (size `l` or `full`).
- **Few panels.** A dashboard holds at most 32; a good one has six to twelve. Past one screen, split it into a second
  dashboard for a second audience, not a longer page.
- **One time range.** Every panel reads the dashboard's one window and the same moment (the page asks for all of them
  together); never give a panel a window of its own to make it look better. A day is the usual window for running
  work, a week or four for trends.
- **Related panels aligned**: arrivals above completions, in the same columns and the same size, so their time axes
  line up and the cursor, shared across the page, reads both at one moment.
- **Refresh** no faster than the panels change: 1m or 5m for most work; 10s only while watching a change go out.

## 3. Choosing the measure

| What it is | Ask for | Not |
|---|---|---|
| A flow (things happening: arrivals, completions, events) | a **rate**: `transform: rate` with `rate_per`, or bars per fixed `bucket` | a count per automatic bucket, whose size changes with the window |
| A stock (a level: a backlog, items in a state) | a **count** or level: `counts`, or a `series` with `agg: last` | a sum over time, which adds up a level as if it flowed |
| A duration (time in a state, a run's length) | **percentiles**: `p50` for the usual case, `p90` or `p99` for the tail | `avg`, which one stuck item drags anywhere and which hides the tail people feel (Little's law, which needs the mean, is the exception: 7d) |
| Money | a rate (`usd/h`, `usd/day`), or the running total against a budget (`transform: cumulative`) | a per-bucket sum whose height depends on the bucket |

- **Arrivals beside completions.** A completion rate alone cannot say whether work is keeping up; put the rate in
  (entries to the first state) and the rate out (entries to the finished states) on one panel, in one unit.
- **Little's law as a check.** In a steady state, items in progress = throughput × time in the system (L = λW). Put
  the three side by side (section 7d); when they disagree by much, the record has holes (items that never finish,
  events not recorded) or the system is not steady, and the other panels are not to be trusted yet.
- **The RED method** for anything that serves requests: **R**ate (arrivals per hour), **E**rrors (entries to the
  failed state per hour), **D**uration (p90 time in *working*). Three panels, one row.
- **The USE method** for a resource (an agent pool, a machine): **U**tilisation (busy agents against the pool's
  limit), **S**aturation (the backlog waiting for it), **E**rrors (its failures). Use it where there is a resource
  with a limit; a flow of items with no shared resource is a RED question.

## 4. Choosing the form

| Form | For | Not for |
|---|---|---|
| `line` | a measure over time; a few series to compare | more than about five series; a discrete period's total (use bars) |
| `line` with `fill: area, stack: stacked` | **parts of a whole only**: one query split by `group_by`, whose parts add up to something real (items by state) | series that overlap or do not add (percentiles, arrivals and completions, two different kinds' durations) |
| `bar` | discrete periods (per hour, per day, with a fixed `bucket`), or categories | a continuous level, whose bars imply a total per bar |
| `stat` | a current value, with `sparkline: on` for its recent shape and `color: thresholds` for its goal | a value whose trend is the point (use a line) |
| `table` | looking things up: a value per group, sorted (`sort`), with `columns` | seeing a change over time |

Percent stacking (`stack: percent`) answers "what share", never "how many": say so in the title.

## 5. Units, scales, thresholds, legends

- **Units.** Leave `display.unit` at `auto`: the answer carries its unit (a field's name ending `_usd` is money, a
  duration is seconds, a rate says `/h`), and the panel picks the readable scale. Set it only when the answer cannot
  know it.
- **One unit per panel, and no dual axes.** A panel has one y axis. Two units on it (a backlog in items and a cost in
  dollars) draw one of them against the wrong scale, and the panel warns. Make two panels, aligned.
- **Scales** start at zero for rates and counts (the panel does this for bars and filled areas); a log scale
  (`display.y.log`) only for a line spanning decades, and say so in the note.
- **Thresholds tied to real goals.** A threshold is the goal it stands for, at the goal's value, with the goal's name
  as its `label` ("goal: p90 under 2 h"). A threshold no goal or decision stands behind is a line people learn to
  ignore. The model's goals (SPEC §8) are the first place to look for them.
- **Legends beside the plot** (the default, `legend: right`; it moves under a narrow panel by itself). Hide it only for
  a single series the title names. Nothing is drawn over a plot but the cursor.
- **Cardinality.** `group_by` a field with few values (`state`, `kind`, a size or a team): at most 12 groups are drawn,
  the rest added up as `other` (the answer's `capped` says how many). A field with many values (a requester, an id) is
  a filter (`where`), or a table sorted by value; never a line per value. A group relation (a gap's `milestone`) is
  a category too, and `state_group` each item's stage in it (done, in progress, waiting, stopped): gaps by milestone,
  stacked, is a `bar` with `stack: stacked` of four `counts` queries, each `x: {type: category, by: milestone}` and
  `where: {state_group: ...}` one stage.

## 6. What a panel costs, and when one is slow

Each source reads a different store:

- `items`, `moves` and `counts` read the **item index**, the fold of the record into items (a projection, in the event
  log's sense; not the model's projection forward from now, which the query API does not chart). Cheap: an indexed
  read per query.
- `series` reads the **metrics store**'s roll-ups. Cheap, and a long window reads coarser roll-ups, not more rows.
- `events` reads the **event log** itself: at most the latest 20,000 events of a window of at most 31 days, four reads
  per request and two at once in all, its answer marked `read_log` (and `truncated` when cut). It is the dear one.
- A request stops starting queries after 10 s; what is left answers *busy*, and the page asks again shortly.

Answers are kept by query and by the version of the data they read, so a refresh with nothing new costs nothing, and a
window ending now moves in 5 s steps so panels asked together share one answer.

When a panel is slow (it says it is late, or answers *busy*):

1. Ask the same thing of a cheaper source: entries to a state from `moves` rather than counting `events` by type.
2. Shorten the window, or set a coarser `bucket`; fewer `points` in the page.
3. Merge panels that ask the same query: an identical query on two panels is asked once, so reuse beats near copies.
4. Fewer queries per panel (at most 12) and fewer panels; drop the panel with no decision first (section 1).
5. Slow the refresh.

## 7. Recipes

The panels below read the example model at the end of this document: requests that wait, are worked on, reviewed
and finish `done` or `failed`, with a `cost_usd` folded into each, a backlog stock and a pool of agents measured by
sensors. Put your own kinds, states, fields and series in their places (`GET /api/query/fields` lists what yours can
chart).

### 7a. Is work flowing?

Arrivals beside completions, as rates, on one panel:

<!-- panel: flowing -->
```json
{"id": "flowing", "title": "Is work flowing?", "size": "m", "form": "line",
 "note": "If completions stay under arrivals for a day, add an agent to working.",
 "queries": [
   {"id": "in", "label": "arrived", "source": "moves", "kind": "request", "measure": "entries", "state": "waiting",
    "transform": "rate", "rate_per": "hour"},
   {"id": "out", "label": "finished", "source": "moves", "kind": "request", "measure": "entries", "state": ["done", "failed"],
    "transform": "rate", "rate_per": "hour"}]}
```

### 7b. Where is it stuck?

Items in each state: a stock, split into parts of a whole, so a stacked area is right here:

<!-- panel: where-stuck -->
```json
{"id": "where-stuck", "title": "Where is the work?", "size": "m", "form": "line",
 "options": {"fill": "area", "stack": "stacked"},
 "note": "The band that keeps growing is the stage to look at first.",
 "queries": [{"id": "wip", "source": "counts", "kind": "request", "group_by": "state",
              "state": ["waiting", "working", "review"]}]}
```

And how long what is there now has been there, by state, as a table to look up:

<!-- panel: how-long-stuck -->
```json
{"id": "how-long-stuck", "title": "How long has it been there? (p90)", "size": "m", "form": "table",
 "options": {"columns": ["last", "max"], "sort": "last"},
 "note": "A state whose p90 age passes a day holds something nobody is working on: open the Items tab on it.",
 "queries": [{"id": "age", "source": "moves", "kind": "request", "measure": "time_in_state",
              "state": ["waiting", "working", "review"], "group_by": "state", "agg": "p90", "include_open": true}]}
```

### 7c. What does it cost?

The running total against the day's budget, as a stat:

<!-- panel: cost-today -->
```json
{"id": "cost-today", "title": "Spent in the window", "size": "s", "form": "stat",
 "options": {"value": "last", "sparkline": "on", "color": "thresholds"},
 "display": {"thresholds": [{"value": 20, "label": "daily budget"}]},
 "note": "Past the daily budget, pause the AI tier and ask the owner.",
 "queries": [{"id": "spent", "source": "items", "kind": "request", "field": "cost_usd", "agg": "sum",
              "transform": "cumulative"}]}
```

And by the hour, as bars, since an hour is a discrete period:

<!-- panel: cost-by-hour -->
```json
{"id": "cost-by-hour", "title": "Cost per hour", "size": "m", "form": "bar",
 "note": "An hour far above the rest names the runs to read in the Record.",
 "queries": [{"id": "hourly", "source": "items", "kind": "request", "field": "cost_usd", "agg": "sum", "bucket": "1h"}]}
```

### 7d. Are we keeping up?

The backlog, its goal as a threshold:

<!-- panel: backlog -->
```json
{"id": "backlog", "title": "Backlog", "size": "s", "form": "stat",
 "options": {"value": "last", "sparkline": "on", "color": "thresholds"},
 "display": {"thresholds": [{"value": 12, "label": "goal: backlog under 12"}]},
 "note": "Over the goal for an hour: raise the pool's limit or stop taking new requests.",
 "queries": [{"id": "level", "source": "series", "series": "sensor/backlog.count", "agg": "last"}]}
```

Little's law as a check on one state, three stats side by side: the items in *working* (L), the rate they leave it
(λ), and the time they spend in it (W). The law is about the mean time, so this is the one place an average of a
duration is right: read as a number beside the other two, never watched as a line.

<!-- panel: littles-l -->
```json
{"id": "littles-l", "title": "In working (L)", "size": "s", "form": "stat",
 "options": {"value": "avg"},
 "note": "Should be near λ × W; far off, the record has holes (items never finished, events missing): fix them before trusting the rest.",
 "queries": [{"id": "l", "source": "counts", "kind": "request", "state": "working", "group_by": "kind"}]}
```

<!-- panel: littles-lambda -->
```json
{"id": "littles-lambda", "title": "Leaving working (λ)", "size": "s", "form": "stat",
 "options": {"value": "avg"},
 "note": "Read with L and W: L ≈ λW.",
 "queries": [{"id": "lambda", "source": "moves", "kind": "request", "measure": "exits", "state": "working",
              "transform": "rate", "rate_per": "hour"}]}
```

<!-- panel: littles-w -->
```json
{"id": "littles-w", "title": "Time in working (W, mean)", "size": "s", "form": "stat",
 "options": {"value": "avg"},
 "note": "Read with L and λ: L ≈ λW, with W in hours.",
 "queries": [{"id": "w", "source": "moves", "kind": "request", "measure": "time_in_state", "state": "working", "agg": "avg"}]}
```

The pool, by the USE method: utilisation as busy agents against the limit (saturation is the backlog above, errors
the failures in 7e):

<!-- panel: pool-use -->
```json
{"id": "pool-use", "title": "Agents busy", "size": "m", "form": "line",
 "options": {"style": "step-after"},
 "display": {"thresholds": [{"value": 4, "label": "pool limit"}]},
 "note": "Busy at the limit while the backlog grows: the pool is the constraint; raise it or shed work.",
 "queries": [{"id": "busy", "source": "series", "series": "sensor/agents.busy", "agg": "max"}]}
```

### 7e. What changed?

What happened, by type, per hour; a type that appears or vanishes is the change:

<!-- panel: what-changed -->
```json
{"id": "what-changed", "title": "What happened, per hour", "size": "full", "form": "bar",
 "options": {"stack": "stacked"},
 "note": "A new type, or one that stopped, is where to read the Record from.",
 "queries": [{"id": "types", "source": "events", "group_by": "type", "bucket": "1h"}]}
```

Errors by the RED method, as a rate beside the duration that matters:

<!-- panel: failures -->
```json
{"id": "failures", "title": "Failures per hour", "size": "m", "form": "line",
 "display": {"thresholds": [{"value": 1, "label": "goal: under one an hour"}]},
 "note": "Over the goal: read the latest failed request's Record before retrying any.",
 "queries": [{"id": "failed", "source": "moves", "kind": "request", "measure": "entries", "state": "failed",
              "transform": "rate", "rate_per": "hour"}]}
```

## 8. Bad panels and their fixes

Each bad panel below asks real queries that answer; it is bad as a panel, and breaks one rule of the sections above.

### An average of a duration

<!-- panel: avg-duration, bad: duration-averaged -->
```json
{"id": "avg-duration-bad", "title": "Time to work a request", "size": "m", "form": "line",
 "note": "If it rises, look at working.",
 "queries": [{"id": "t", "source": "moves", "kind": "request", "measure": "time_in_state", "state": "working", "agg": "avg"}]}
```

One request left in *working* over a weekend moves the average for everyone, and the average hides the tail. The
fix: the median and the tail, with the goal on the tail:

<!-- panel: avg-duration, fix -->
```json
{"id": "avg-duration", "title": "Time to work a request", "size": "m", "form": "line",
 "display": {"thresholds": [{"value": 7200, "label": "goal: p90 under 2 h"}]},
 "note": "p90 over the goal for half a day: split the work, or add an agent to working.",
 "queries": [
   {"id": "p50", "source": "moves", "kind": "request", "measure": "time_in_state", "state": "working", "agg": "p50"},
   {"id": "p90", "source": "moves", "kind": "request", "measure": "time_in_state", "state": "working", "agg": "p90"}]}
```

### Stacked series that are not parts of a whole

<!-- panel: stacked-flows, bad: stacked-not-a-whole -->
```json
{"id": "stacked-flows-bad", "title": "Requests", "size": "m", "form": "line",
 "options": {"fill": "area", "stack": "stacked"},
 "note": "If it falls, look at intake.",
 "queries": [
   {"id": "in", "source": "moves", "kind": "request", "measure": "entries", "state": "waiting", "transform": "rate", "rate_per": "hour"},
   {"id": "out", "source": "moves", "kind": "request", "measure": "entries", "state": "done", "transform": "rate", "rate_per": "hour"}]}
```

Arrivals and completions are the same requests counted twice; their stacked total is nothing, and the top band's
height cannot be read. The fix is section 7a's panel: two lines, unstacked:

<!-- panel: stacked-flows, fix -->
```json
{"id": "stacked-flows", "title": "Arrivals and completions", "size": "m", "form": "line",
 "note": "Completions under arrivals for a day: add an agent to working.",
 "queries": [
   {"id": "in", "label": "arrived", "source": "moves", "kind": "request", "measure": "entries", "state": "waiting", "transform": "rate", "rate_per": "hour"},
   {"id": "out", "label": "done", "source": "moves", "kind": "request", "measure": "entries", "state": "done", "transform": "rate", "rate_per": "hour"}]}
```

### Two units on one axis

<!-- panel: two-units, bad: units-apart -->
```json
{"id": "two-units-bad", "title": "Backlog and cost", "size": "m", "form": "line",
 "note": "If either rises, look into it.",
 "queries": [
   {"id": "backlog", "source": "series", "series": "sensor/backlog.count", "agg": "last"},
   {"id": "cost", "source": "items", "kind": "request", "field": "cost_usd", "agg": "sum", "transform": "rate", "rate_per": "hour"}]}
```

Requests and dollars per hour share one scale, so the smaller is a flat line along the bottom; a second axis would
only make the crossing points mean something they do not. The fix: two panels, aligned, each with its own decision:

<!-- panel: two-units, fix -->
```json
{"id": "two-units-backlog", "title": "Backlog", "size": "m", "form": "line",
 "display": {"thresholds": [{"value": 12, "label": "goal: backlog under 12"}]},
 "note": "Over the goal for an hour: raise the pool's limit.",
 "queries": [{"id": "backlog", "source": "series", "series": "sensor/backlog.count", "agg": "last"}]}
```

<!-- panel: two-units, fix -->
```json
{"id": "two-units-cost", "title": "Cost per hour", "size": "m", "form": "line",
 "display": {"thresholds": [{"value": 2, "label": "planned: $2/h"}]},
 "note": "Over plan for three hours: find the runs behind it before the day's budget goes.",
 "queries": [{"id": "cost", "source": "items", "kind": "request", "field": "cost_usd", "agg": "sum", "transform": "rate", "rate_per": "hour"}]}
```

### A line per requester

<!-- panel: per-requester, bad: too-many-groups -->
```json
{"id": "per-requester-bad", "title": "Cost by requester", "size": "m", "form": "line",
 "note": "Find who is spending the most.",
 "queries": [{"id": "cost", "source": "items", "kind": "request", "field": "cost_usd", "agg": "sum", "group_by": "requester",
              "transform": "rate", "rate_per": "hour"}]}
```

Fifteen requesters: twelve tangled lines, the rest lumped into `other`, and the one asked about may be in it. The
question is a lookup, so the fix groups by a field with few values and leaves the lookup to the Items tab:

<!-- panel: per-requester, fix -->
```json
{"id": "per-requester", "title": "Cost by size of request", "size": "m", "form": "table",
 "options": {"columns": ["last", "avg", "max"], "sort": "avg"},
 "note": "If large requests cost most, size the work before it is taken.",
 "queries": [{"id": "cost", "source": "items", "kind": "request", "field": "cost_usd", "agg": "sum", "group_by": "size",
              "transform": "rate", "rate_per": "hour"}]}
```

### A flow counted per automatic bucket

<!-- panel: done-count, bad: flow-as-a-count -->
```json
{"id": "done-count-bad", "title": "Requests done", "size": "m", "form": "line",
 "note": "If it drops, find out why.",
 "queries": [{"id": "done", "source": "moves", "kind": "request", "measure": "entries", "state": "done"}]}
```

The count in each bucket depends on the bucket, which depends on the window and the panel's width: the same flow
reads 2 on a day and 14 on a week. The fix asks for a rate, which reads the same at any window:

<!-- panel: done-count, fix -->
```json
{"id": "done-count", "title": "Requests done per hour", "size": "m", "form": "line",
 "note": "Under one an hour while the backlog is over its goal: look at review, the last stage before done.",
 "queries": [{"id": "done", "source": "moves", "kind": "request", "measure": "entries", "state": "done",
              "transform": "rate", "rate_per": "hour"}]}
```

### A threshold that is not a goal

<!-- panel: bare-line, bad: threshold-unnamed -->
```json
{"id": "bare-line-bad", "title": "Backlog", "size": "m", "form": "line",
 "display": {"thresholds": [{"value": 10}]},
 "note": "Act when it crosses the line.",
 "queries": [{"id": "backlog", "source": "series", "series": "sensor/backlog.count", "agg": "last"}]}
```

Nobody remembers why the line is at 10, so nobody acts when it is crossed. The fix names the goal it stands for and
puts it at that goal's value (section 7d's `backlog` panel, drawn as a line).

<!-- panel: bare-line, fix -->
```json
{"id": "bare-line", "title": "Backlog", "size": "m", "form": "line",
 "display": {"thresholds": [{"value": 12, "label": "goal: backlog under 12"}]},
 "note": "Over the goal for an hour: raise the pool's limit or stop taking new requests.",
 "queries": [{"id": "backlog", "source": "series", "series": "sensor/backlog.count", "agg": "last"}]}
```

### A panel with no decision

<!-- panel: no-decision, bad: no-decision -->
```json
{"id": "no-decision-bad", "title": "Events", "size": "m", "form": "line",
 "queries": [{"id": "all", "source": "events", "transform": "rate", "rate_per": "hour"}]}
```

What would anyone do differently at any value of it? Nothing, so the fix is to remove it. If a real question was
behind it ("did something new start happening?"), section 7e's `what-changed` answers that one.

## The example model

What the panels above read:

<!-- example model -->
```yaml
name: requests
stocks:
  backlog:
    unit: requests
    sensors:
      count: {run: ./count-waiting.sh, every: 1m}
  agents:
    unit: agents
    limit: 4
    sensors:
      busy: {run: ./count-busy.sh, every: 1m}
items:
  request:
    id: request/*
    states: [waiting, working, review, done, failed]
    on:
      request.started: working
      request.reviewed: review
      request.done: done
      request.failed: failed
    show: [requester, size]
    fold:
      cost_usd: sum
```

## How this document is checked

`tests/test_dashboards_doc.py` reads every panel above (each fenced `json` block after a `<!-- panel: ... -->` mark)
and the example model. For each panel it checks the config's keys, its form, its options against the choices
`panels.js` declares for that form, and its display; then it asks the panel's queries of the query API over a record
of the example model, and every query must answer, without an error and with a value. It also checks the rules this
document can state as checks: no panel has no note; no line or bar of a duration is an average; no panel answers in two units; a
stacked panel is one query split by a group; no answer folds groups into `other`; a flow on a line or bars is a rate
or has a fixed bucket; every threshold has a label. Every panel not marked bad keeps all of them, and every bad panel
breaks exactly the rule it is marked with. The rest of this document (the layout, the choice of question) is advice
no test can judge.
