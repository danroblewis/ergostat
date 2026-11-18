# The ergostat model: specification (draft)

This specifies the configuration format: the files people and AI agents write to describe a
system. It replaces the TOML format. The ideas behind it are in `docs/CONCEPTS.md`, the names
come from `docs/vocabulary.md`, and `schema/ergostat.schema.json` is the machine-checkable form
of this document.

**Status: draft for review, implemented.** `ergostat check`, `convert` and `run` follow this document
(`ergostat/spec/`). Where building it settled a question, the decision is marked *Decided*.

## 1. Principles

1. **Four kinds of thing are written, and more when they say something.** Stocks, flows, goals
   and blocks; auxiliaries, for quantities without memory; parameters, the numbers equations name
   (section 7b); and agents, only for machines shared
   by several blocks. (Kinds of item, section 5a, say how to read the record, not what the system
   is.) Valves, controllers, disturbances, errors, loops and diagrams are worked out from them,
   never declared.
2. **Two layers.** The material layer (stocks and flows: where work moves and accumulates) and
   the information layer (blocks and the signals between them: deciding and commanding). This is
   system dynamics' stocks and flows plus converters and connectors, and control engineering's
   function blocks and signals.
3. **Every reference is written once, on the side that acts.** A goal names its stock or flow; a
   flow names the stocks it connects; a block names its inputs and outputs, and its machine when
   it has one. Flows are passive: they never say who moves them. Reverse relations (a stock's
   goals, a flow's actuator, a machine's blocks) are looked up, never written, so they cannot
   drift.
4. **Nest only what is exclusively owned.** A sensor measures exactly one stock or flow, so it
   is written inside it. Everything else is top-level and referenced by name.
5. **What is real is measured.** A stock's value is only ever its sensors' readings. What blocks
   report is evidence, judged against the stocks.
6. **Nothing is a claim nobody acts on.** Every block is executed by ergostat, executed by a
   machine ergostat runs, or explicitly observed (`external`): the file never describes behaviour
   that nothing performs.
7. **Each key says what it names.** `from` and `to` are stocks, `stock` and `flow` say which kind
   a goal is about, `agent` is a machine; no word means two things.

## 1a. One model, two perspectives

There is one model, and two ways of looking at it, each true to its own discipline:

- **System dynamics** (what is): stocks, flows, auxiliaries and the influences between them, and
  the feedback loops they make, each reinforcing (R) or balancing (B). For product managers and
  sales; the language of Sterman's *Business Dynamics*, Vensim and Stella.
- **Control** (what is controlled): goals, sensors, controllers and actuators, the error each
  controller acts on, and the loop it closes. For engineers; classical block diagrams.

Neither is derived from the other: both are read from the same stocks, flows, auxiliaries, goals
and blocks. A kind of quantity (stock, auxiliary) belongs to the model; a role in a loop (process
variable, manipulated variable, controller, actuator) belongs to the control view, and is worked
out, never written.

## 2. Files

- The main file is `ergostat.yaml` at the root of the project. YAML 1.2; a JSON file is also
  valid YAML and is accepted.
- `include:` names more files (paths or globs, relative to the including file). Included files
  may include others. All files share one namespace.
- Each top-level section is a map keyed by name; maps from all files are merged. **Defining a
  name twice is an error**, reported with both files and lines. There is no overriding.
- A file may set `defaults:` (at present only `system:`), which applies to the stocks, flows,
  goals and blocks defined in that file, and not to the files it includes.

## 3. Names, references and values

**Names** are lowercase letters, digits and `-`, starting with a letter: `inbox`,
`keep-inbox-short`. Names are unique within each section; the same name may be used in two
sections (a stock and a goal both called `inbox`), but it is discouraged. Parameters (section 7b) are
named by their bare name in equations, so a parameter may not take a function's name (`min`, `delay1`).

**References** point at a thing, or at one port of it:

| Reference | Means |
|---|---|
| `stock.inbox` | The stock's measured level (its current best reading) |
| `stock.inbox.count` | The reading of one of its sensors, `count` |
| `auxiliary.quality` | An auxiliary's value (as an output: what a block sets it to) |
| `flow.processed` | As an input: the flow's measured rate. As an output: what a block moves along this flow |
| `goal.inbox-short` | The goal's setpoint (r) |
| `goal.inbox-short.error` | The goal's error, e = r − y |
| `goal.inbox-short.off` | 1 while the goal is off, 0 while it holds |
| `block.decide` | A block's output (its only output, or its output named `out`) |
| `block.decide.urgent` | A block's output port `urgent` |

A `driven-by` reference may carry a sign, its **polarity**: `+stock.improvements` (it rises when
that rises), `-auxiliary.price` (it falls when that rises). Unsigned means not known. No other
reference carries a sign.

*Renamed:* `variable.x` is the old spelling of `auxiliary.x`, and `variables:` of `auxiliaries:`;
both are still read, with a `deprecated-name` finding saying what to rename.

Where a key can only name one kind of thing, the name is written bare: a goal's `stock: inbox`, a
block's `agent: claude`, an `onoff` block's `goal: inbox-short`.

**Durations**: `30s`, `5m`, `2h`, `1d`, or a number of seconds.

**Setpoints**: `"<= 20"`, `"< 20"`, `">= 5"`, `"> 5"`, `"== 50"`. Quote them (YAML reads `>` as
a folding marker).

**Commands** (`run:`) are shell commands, run with `sh -c` in the project's root, with the
inputs described in section 9 on standard input.

**Style.** The examples use block-style YAML: one key per line. Short lists may stay on one line
(`in: [goal.a.error, goal.b.error]`). Flow style (`{ ... }`) is valid but not used here.

## 4. Top level

```yaml
name: checkout                  # the project's name (default: the folder's)
include:
  - systems/*.yaml
keep: 30d                       # how long the record is kept
storage:                        # optional: where it is kept, rolled up and downsampled (section 4b)
  ...
defaults:
  system: core
sources:                        # where existing metrics live
  ...
items:                          # optional: kinds of item, read from the record
  ...
systems:                        # optional: systems, and the systems they are within (section 4a)
  ...
stocks:
  ...
flows:
  ...
parameters:                     # optional: the numbers equations name (section 7b)
  ...
auxiliaries:                    # optional: quantities without memory (section 7a)
  ...
goals:
  ...
blocks:
  ...
agents:                         # optional: machines shared by several blocks
  ...
loops:                          # optional: names for feedback loops (section 12a)
  ...
```

## 4a. Systems: parts made of parts

A system is a named part of the model, and it may be part of another: they nest, the way a
cascade's inner loop is one block of the outer loop. Each stock, flow, goal and block belongs to
one system (its `system:`, or its file's `defaults: system:`), and so to every system that one
is within.

```yaml
systems:
  factory:
    description: tickets in, releases out
  intake:
    within: factory
  delivery:
    within: factory
  product:                       # within no other system: the top level
    description: what customers use
```

| Key | Type | Default | Meaning |
|---|---|---|---|
| `description` | string | none | |
| `within` | system name | the top level | The system it is part of. A system within itself, at any depth, is an error |
| `show` | stock, flow or auxiliary references | its goals' | The measures its box shows when it is drawn as one part: its control panel |

A system named by a part and not described here is a top-level system.

**Its interface is worked out, never written.** Whatever crosses a system's boundary is one of
its ports:

| Port | In | Out |
|---|---|---|
| setpoint | a block outside sets a goal inside (a cascade) | a block inside sets a goal outside |
| command | a block outside commands one inside | the other way |
| action | a block outside moves a flow inside | a block inside moves a flow outside |
| signal | a block inside reads a stock, flow or goal outside | a block outside reads one inside |
| material | a flow from a stock outside into one inside | a flow out to a stock outside |
| influence | a flow inside is `driven-by` something outside | something inside drives a flow outside |

A system whose setpoint comes in from outside, and whose goal's measurement goes back out, is an
**inner loop**: seen from outside, it is one block that holds what it is told, and an outer loop
can treat it so. `ergostat explain system.NAME` says what goes in and out, and names it an inner
loop when it is one.

**Drawn as parts.** The control diagram draws each system as one box: its ports on its edges
(inputs left, outputs right, each named for the part inside it reaches, with that part's
reading), how the loops inside it are doing, and its measures: each one's value, setpoint, health
and trend (`show:`, or by default what its goals hold). With every system closed, the diagram is
the model's control panel. A box opens in place (its parts, laid out
together inside its outline, its own systems still boxed), or is drawn alone: its parts, and
what it reaches outside as terminals at its edge, each naming the system it is in. A system alone
at its level starts open; the others start as boxes.

## 4b. Storage: where the record is kept

The record is two stores, kept apart (few events, many measurements), each behind one interface
with several backends, all held to one conformance suite (`tests/test_store_conformance.py`).
The defaults need no services; a project names another backend in `storage:` (main file only):

```yaml
storage:
  events: segments                 # or sqlite
  measurements:
    backend: sqlite                # or victoriametrics, with url: http://127.0.0.1:8428
    raw: 2d                        # raw readings kept this long (never: kept until keep)
    tiers: {1m: 14d, 10m: 90d, 1h: 2y}   # then buckets of each width, each kept this long
  rollup:
    after: 7d                      # an item's events older than this become one snapshot (never: not rolled up)
    kinds: {session: 1d}           # per item kind
    every: 1h                      # how often the engine rolls up and forgets
```

**Events.** `segments` (the default) is an append-only log in `<state>/events/`: the newest events
in `head.jsonl`, appended under a file lock by whichever process records them (the runner, the
page, the command line); every 32,768 events sealed into a segment of gzip blocks (512 events a
block, read alone) with an index (each item's and each type's rows, the times and seqs as
columns, a Bloom filter of the ids), so a query by item, type and time reads only the rows and
blocks that match. `sqlite` is `events.db`, as before. Both keep a transcript's lines
(`claude.*`) out of item counts without reading them (SQLite by a partial index, the log by its
type columns).

**Items rolled up.** An item's events older than its horizon (`rollup.after`, or its kind's) are
replaced by one event, `ergostat.item.snapshot`, the item as it stood after them:

- its document as a `set` (section 5a), and in `data.rollup` the rest of what the fold keeps: the
  state and when it was entered, every move, the first and last times, how many events, the latest
  type, what was refused, and each field's history summarised (how many changes, the first and the
  last, by time, event and type); where a transcript's lines were among them, the fold with them
  beside the fold without (`rollup.transcript`), so a count of items reads the same as one that
  folds the conversation;
- it takes the `seq` of the last event it replaces, so it folds where they did. Only a prefix of the
  item's events (by `seq`), every one older than the horizon, is rolled up; a later roll-up folds
  the snapshot with what followed it into the next.

Folding the snapshot and what came after gives the same item as folding the originals (fields,
state, moves, counts, refusals; `tests/test_rollup.py`, for every example's kinds, with and
without transcripts, rolled up again and again; `scripts/demo_check.py` on each demo's own record).
What is lost is detail before the horizon: an item read as it stood before its snapshot (time
travel) is not there, and its field history before the horizon is the summary. The originals are
moved to `<state>/archive/<kind>/<YYYY-MM>.jsonl.gz` (a gzip member per roll-up, an event per line)
with `<YYYY-MM>.idx.jsonl` beside it (per item and member: where, how many, first and last time);
the item's page shows "Show the full history", which reads them (`/api/items/ID?archived=1`, a page
at a time). A transcript read again from its start records none of its rolled-up lines.

**Keeping.** `keep:` (top level, default 30 days) is how long events are kept: older ones are
forgotten, except the model's history (`model.changed`) and each loop's last crossing. An item is
forgotten whole, once nothing about it is newer than `keep`; until then its older events are in its
snapshot (the engine never keeps more than `keep` outside one). Archive months older than `keep`
are deleted.

**Measurements.** Raw readings are kept for `raw`; older ones are rolled into tiers of buckets,
each bucket keeping the count, sum, min, max, and first and last reading (time and value), each
tier for its own time. A tier is made from the one before it (raw, then 1m, then 10m...), in whole
buckets, a few hours of record per transaction; a source is forgotten only once the next tier has
taken it. A reading that arrives for a span already rolled up is merged into its buckets. Every
read stitches the sources: raw where it is kept, buckets before that; a bucketed read (a chart's
points) takes the coarsest tier no wider than its own buckets; a read of readings one by one gets
each old bucket's last reading. `victoriametrics` keeps every reading as
`ergostat_reading{project, series}` in the server, which compresses and keeps them for its own
`-retentionPeriod` (the open-source server does not downsample): buckets are computed by the
server (MetricsQL over `query_range`), raw readings exported when there are few (20,000 at most),
and old spans bucketed otherwise; a reading set aside (`forget`) is kept in
`measurements.forgotten.json`.

**Chosen by measurement** (`scripts/loadtest.py`, the demos' records tiled to 1, 7 and 30 days;
the numbers in `docs/proposals/harness-parity-plan.md`, section 4). The segmented log is the
default for events: a fifth of SQLite's size for the same record (110 MB against 557 MB for a week
of image-squeeze), written faster, and read as fast or faster by every page. SQLite stays the
default for measurements: VictoriaMetrics holds them in almost nothing and answers the pages as
well, but every reading the engine reads is a request to the server, and the engine kept to under
one reading a second where it makes six; it is for a project that already runs one, until the
engine reads through a cache.

**Upkeep.** The engine rolls items up, forgets what is past `keep`, and rolls the measurements into
their tiers every `rollup.every` (an hour). `ergostat compact` does it now (`--dry-run` says what
it would roll up).

**The page's answers are bounded.** No answer grows with the record: events are at most 1,000 an
answer (`n`, paged by `after` and `before`), items 500 (`offset`), a kind's finished items a thousand
dots (and how many there were), a chart's series a thousand buckets, a sensor's readings its latest
60 and how many; a loop's crossings are read for the window (and the one before it), never the
whole record. A client that hangs up before its answer is written is one line in the log, not a
traceback.

## 5. Stocks

A quantity with memory: its value persists when nothing happens, and changes only through its
flows. What accumulates (a queue, a disk, a backlog), and also what is held at a level by equal
inflow and outflow, and a setting a controller steps (it stays where it was last moved: section
7a). Its reading may come from a script and may change suddenly; a sudden drop is a large outflow,
some process removing what was there. Real, measured, trusted.

```yaml
stocks:
  inbox:
    unit: files
    limit: 10000                       # optional: where it physically fails
    system: intake                     # optional
    description: files waiting to be processed
    sensors:                           # zero or more, keyed by name
      count:
        run: ls inbox | wc -l
        every: 5s
```

| Key | Type | Default | Meaning |
|---|---|---|---|
| `unit` | string | none | Its unit. Flows and sensors on it must use the same unit |
| `limit` | number | none | The physical limit: a full disk, a queue's capacity. Used to estimate time to failure |
| `initial` | number | none | A starting value, for simulation only |
| `cumulative` | bool | false | A running total that by its nature never drains (spent so far, kept so far): no outflow is missing, and `check` does not ask for one (**stock-without-outflow**) |
| `inferred` | model-change id, or `true` | none (declared) | Added by ergostat: the model change that added it (section 12e, *Inferred and declared*) |
| `system` | name | the file's default | The group it belongs to |
| `description` | string | none | |
| `sensors` | map of sensors | none | How it is measured (section 6) |
| `sensor` | sensor | none | Shorthand for a single sensor named `main` |

A stock with no sensor cannot be judged: any goal on it is reported (section 12).

## 5a. Items

What the work is made of, one thing at a time: a ticket, a pull request, a deploy, a customer's
order. An item is not written in the model; it is every event about one id, replayed in order.
Its id names it the way the system it lives in does, with a `/` in it: `ticket/12`,
`github/pull_request/4231`. (ergostat's own events are about the model's parts, whose names never
have a `/`; the two never mix.) An event about an item comes from a block's output
(`{"event": "pr.merged", "item": "github/pull_request/4231", "data": {...}}`), from a sensor's
observations, from `ergostat event --add`, or from an agent over MCP (`record_event`).

A kind of item says which ids are that kind, the states they move through, and how its events'
data folds into it:

```yaml
items:
  pr:
    id: github/pull_request/*        # a glob over ids
    states: [open, review, merged, closed]
    on:                              # event type: the state it moves the item to
      pr.review-asked: review
      pr.merged: merged
      pr.closed: closed
    show: [title, author]            # fields worth a column on the Items page
    fold:                            # field: how the data events carry folds into it (else replace)
      reviewers: union
      comments: append
      hours: sum
```

| Key | Type | Default | Meaning |
|---|---|---|---|
| `id` | glob with a `/` | required | Which ids are this kind. The first kind that matches an id is its kind |
| `states` | list of names | none | The states, in their usual order; a new item starts in the first |
| `on` | map of event type → state | none | Which events move an item, and where to |
| `show` | list of field names | none | Columns for the Items page and `ergostat item` |
| `formats` | map of field → format | by extension | How a file a field names is shown: `image`, `markdown`, `code`, `text`, `json`, or `claude-session` (a Claude Code transcript, as the conversation; its lines are also recorded as events, below) |
| `fold` | map of field → rule | `replace` | How the plain `data` of its events folds into each field (the rules below) |
| `system`, `description` | | | |

**Changesets.** An item's fields are one JSON document, and every event about it is a changeset
folded into that document in sequence. The event chooses how it changes it, in one of three forms
(never two at once):

- **`patch`**: a JSON Patch (RFC 6902): a list of operations, `add`, `remove`, `replace`, `move`,
  `copy` and `test`, each at a JSON Pointer (RFC 6901) `path` (`/reviewers/0`; `~1` for a `/`
  in a name, `~0` for a `~`), with `/-` appending to an array. They are applied in order.
  `{"event": "pr.labelled", "item": "...", "patch": [{"op": "add", "path": "/labels/-", "value": "bug"}]}`.
- **`set`**: the whole document, at once. It is the patch that removes every field and adds each
  field of the new document back, and it is applied, and kept in history, as exactly that.
- **`data`**: what blocks and scripts emit. Each key is folded into the field of that name by its
  kind's rule for it, and becomes the patch operations that do so; a key with no rule replaces its
  field (an `add` at its path, a `replace` when it was there).

A changeset applies whole or not at all. A `test` that does not hold, a path that is not there,
an index past an array's end, an operation that is not one, or a rule that cannot fold its value
(`sum` of a word) refuses the whole event: none of it changes the item, and the item says which
event was refused and why (its `refused` list, and its history). The event itself is recorded as
it was sent: the record holds what was said; the fold, what came of it. A changeset that is not
even the right shape (a patch that is not a list of operations, `set` that is not an object, or
two forms in one event) is refused before it is recorded, as a bad line is. `ergostat event --add`
and MCP's `record_event` say at once when a patch they recorded changed nothing.

**Fold rules**, for plain data (`fold:`; any other name is an error `ergostat check` reports):

| Rule | The field becomes |
|---|---|
| `replace` | the value given (the default) |
| `append` | a list, the value appended (each value of a list given, in order) |
| `sum` | the sum of the numbers given |
| `min`, `max` | the least, the greatest, of the values given (numbers, or text) |
| `union` | a set of the values given (a list given is each of its values), kept as a sorted list |
| `merge` | an object, each object given deep-merged into it (an object's keys merged, anything else replaced) |
| `first` | the first value given, kept |

**History.** Every change is kept, per path, in order: when, by which event (its id and type),
the operation (with its rule, or `patch` or `set`), the path, and the value before and after. A
change deeper in a field (`/comments/3`) is that field's. The item's `fields` is the folded
document as it stands, so whatever reads fields reads them as before; its history is beside it
(`ergostat item ID --history [FIELD]`; the item's page, where each field shows its value and a
history disclosure, each change linked to its event; `/api/items/ID`, each field's latest 100
changes and how many there were, all with `history=all`). An item can be read as it stood at any
time (`--at`, the pages' time travel): its fields, its state and its history are folded from
the events up to then.

**Built-in kinds.** Six kinds are ergostat's own, present in every project and never declared (a project's
kinds may not take ids starting `ergostat.`): `ergostat.model-change`, every change to the model (section 12e),
`ergostat.claim`, what a block said it did, checked (section 12g), the owner's intent, `ergostat.decision` and
`ergostat.correction` (below), and `ergostat.message`, the owner's messages, routed to the work they concern
(section 12h), and `ergostat.verdict`, the intent judge's verdict on finished work (section 12i). ergostat may also
move any item: `ergostat.item.reopened` moves it to the state its data names (`reopened.to`, else its kind's first),
`ergostat.item.follow-up` starts one (section 12h), and `ergostat.item.judged` sets its field `intent` (section 12i).

**Decisions and corrections.** What the owner decided, and what the owner corrected, are items, so that every
later session can start from them (`docs/DECISIONS.md` is how to use them):

| Kind | States | Fields |
|---|---|---|
| `ergostat.decision` | `proposed` → `confirmed` → `superseded`; `dismissed` (an exit, from proposed) | `decision` (one sentence), `words`, `reasons`, `alternatives` (`[{option, why}]`, what was rejected), `scope`, `supersedes`, `proposed_by`, `confidence`, `extractor`, `evidence` |
| `ergostat.correction` | `proposed` → `confirmed` → `retired`; `dismissed` | `correction` (what to do differently), `words`, `corrects` (the behaviour or result), `kind_of_work`, `scope`, `source`, `repeats` (and `repeat: true`), `repeated_by`, `evidence` |

`words` is the owner's words, verbatim, each with where it was said: `{text, session, line, time}` (a
transcript), or `{text, time, event}` (the record). Their fold rules: `words`, `evidence`, `alternatives` and
`repeated_by` are `append`; `reasons`, `scope`, `supersedes` and `kind_of_work` are `union`; the rest
replace. An id is the kind and a slug of the sentence (`ergostat.decision/never-add-page-7c1e`), so the same
sentence proposed again is the same item.

The events, `ergostat.decision.*` and `ergostat.correction.*`:

| Event | From | Data, and what it needs |
|---|---|---|
| `.proposed` | anyone: a block's output line, the extractor, `ergostat decisions propose`, MCP `record_event` | the fields above; checked before it is recorded: the sentence (at most 400 characters), and `words` (required unless the owner proposes it, when the sentence is the owner's words) |
| `.seen` | the same | a known item proposed again with new words: `words` and `evidence` appended |
| `.confirmed` | the owner | `confirmed_by`, an optional `confirmed_reason`; only a proposed item |
| `.dismissed` | the owner | `dismissed_reason`, required; only a proposed item |
| `decision.superseded` | the owner | `superseded_by` (the decision that replaces it, not dismissed or superseded) and `superseded_reason`, both required; only a confirmed decision. The replacing decision records `decision.supersedes` |
| `correction.retired` | the owner | `retired_reason`, required; only a confirmed correction |
| `correction.repeated` | ergostat | on the first correction, when a later one makes the same point: `repeated_by` (`{item, text, line, ...}`), `repeated_n` |

A block may print a `.proposed` line (`{"event": "ergostat.decision.proposed", "data": {...}}`), checked like
any proposal and refused with why when it does not hold; the owner's acts (`confirmed`, `dismissed`,
`superseded`, `retired`) are never a block's, and are refused. A supersession is never implied: a decision
proposed with `supersedes` leaves the older one confirmed until the owner supersedes it with a reason.

A correction that makes the same point as an earlier one (most of the content words of the owner's sentence
shared, for the same kind of work) is linked to the first (`repeats`), and the first records
`correction.repeated`. A repeat is a finding (`correction-repeated`, needs attention) while it waits for the
owner, or while the correction it repeats is confirmed: the first did not change what was done.

`ergostat corrections scan` proposes the corrections the record already holds: an owner's dismissal with a
reason, an item moved back to an earlier state (or by a `*.reopened` event) with a reason, an
`ergostat.message` classed as a correction (`class: correction`, or unclassed and read as one).

**Projections.** `ergostat context decisions [--scope X] [--budget N]` and `ergostat context corrections
--kind K [--budget N]` render the confirmed items (with `--proposed`, those waiting too, marked) as Markdown
for the start of a session, most relevant first: an item whose `scope` (or `kind_of_work`) names a word of
the scope asked comes first, then one whose words mention it, then the rest, the newest first within each;
corrections for another kind of work are left out, those for `general` kept. As many as fit the budget are
given in full (the sentence, up to two quotes with where they were said, reasons, what was rejected, what it
replaces, the scope, its id), the rest as one-line pointers, then a count of those that did not fit. A budget
is characters (`6000`; the default `8000`) or tokens (`1500t`, at four characters a token). MCP `context`
gives the same.

**States.** An item arrives in its kind's first state (a move from nowhere, so a flow can count
arrivals with `entering:`), and stays there until an event its kind maps moves it; every move is
kept (from, to, when, by which event), so how long it spent in each state is known. An item no
kind matches is still shown, with its fields (folded with no rules) and no state.

A field whose value is `file:PATH` names a file in the project (a picture a program made, a report,
an agent's transcript): the page shows it where the item is shown, as what it is (`formats`, or its
extension: an image as an image, Markdown rendered, code highlighted, a Claude Code transcript as the
conversation, re-read while it grows; raw HTML in Markdown is shown as text, never run), and serves
only files inside the project and its state directory, at `/file/PATH` (a path, so a Markdown file's
relative links open the files beside it: opened in the browser, a Markdown file is shown rendered). A file is kept apart from the record: the
record holds what happened, the file what was said.

**Claude Code transcripts as events.** While ergostat runs, a field its kind shows as
`claude-session` that names a file (`transcript: file:run/sessions/developer-1a2b.jsonl`) is read
every two seconds as it grows, and each complete line is recorded as an event about the item,
once: its id is made from the item and the line's `uuid` (a line without one, from its number and
content), so reading it again records nothing. Its time is the line's `timestamp`; it is caused by
(`causedby`) the event of its `parentUuid`; its source is whoever started the item. The types:

| Type | `data` |
|---|---|
| `claude.message` | `messages`: `[{role, text, line, uuid}]`, what the user or the assistant said |
| `claude.tool-use` | `tool_calls`: `[{id, name, input, line}]` |
| `claude.tool-result` | `tool_results`: `[{tool_use_id, text, error, line}]` |
| `claude.thinking` | `thinking`: `[{text, line}]` |
| `claude.other` | `other`: `{type, line, text}`, any other line (a summary, a snapshot, ...) |

An assistant message's first line also carries `tokens_in` (input, cache writes and reads) and
`tokens_out`; a message split over several lines repeats its usage, and is counted once. A text
over 4 KB keeps its head in the event, with `truncated`, its size in `bytes`, and `full`, the file
and line where all of it is: the transcript file stays the full record of what was said, and the
conversation the page shows. A line is one event, typed by what it holds (a tool call first, then
a result, text, thinking). The kind folds them with its rules, so the item folds into its
conversation:

```yaml
  session:
    id: session/*
    formats: {transcript: claude-session}
    fold: {messages: append, tool_calls: append, tool_results: append, thinking: append,
           tokens_in: sum, tokens_out: sum}
```

What does not ask for a transcript leaves its events out: a sensor counting sessions, the Items
list and `ergostat item` (which count them, without reading them), the Record and `ergostat event`
(unless a type or the item is asked for), and the wiring. A fold reads them when its kind moves on
a `claude.*` type, or when a sensor's `where:` or a column names a field they fold into. The item's
own page and `ergostat item ID` fold them all. A session of 2,000 lines is recorded in well under a
second, and leaves a count of sessions as fast as it was.

Items are counted by sensors (section 6): a stock may be the number of items in some states, and
a flow the rate at which items enter or leave one. The record is then the instrument: what is
counted is what the events say, so a stock counted from items is only as true as the events
reporting them.

## 6. Sensors

An instrument: it measures one stock or one flow, and nothing else. It never decides or acts. It
is written inside the stock or flow it measures. Exactly one of `run`, `query`, `manual`, `items`,
`changes` or `builtin`:

```yaml
sensors:
  count:
    run: ls inbox | wc -l
    every: 5s
  depth:
    query:
      source: prom
      promql: 'sum(queue_depth{app="checkout"})'
    every: 30s
  eyes:
    manual: true                 # a person records readings: ergostat sensor inbox.eyes --read 12
```

Counting items (section 5a), on a stock and on a flow:

```yaml
stocks:
  in-review:
    unit: prs
    sensor:
      items: pr
      state: review              # one state, or a list: [open, review]
      where:                     # optional: only items whose fields match
        label: bug
      every: 30s
flows:
  merging:
    from: in-review
    sensor:
      items: pr
      entering: merged           # or leaving: review
      over: 1h                   # the rate per hour over this window (default 1h)
```

| Key | Type | Default | Meaning |
|---|---|---|---|
| `run` | command | | A command whose output is the reading: a bare number, or JSON `{"value": n}` |
| `query` | map | | A query against a source (section 11): `source` and the source's own fields |
| `manual` | bool | | Readings recorded by a person |
| `items` | item kind | | Counted from the record: on a stock, the items in `state` (any state when left out); on a flow, the items `entering` or `leaving` a state per hour, over `over` |
| `state` | state or list | any | On a stock: which states count |
| `measure` | `count` or `oldest` | `count` | On a stock: how many, or the hours the oldest of them has been in its state |
| `entering`, `leaving` | state | | On a flow: exactly one; the move it counts |
| `changes` | `rises`, `falls` or `net` | | On a flow into or out of one stock: its rate from that stock's own successive readings, how much they rose (an inflow), fell (an outflow), or both, net, in the flow's direction (a `two-way` flow), per hour over `over` |
| `over` | duration | `1h` | On a flow: the window the rate is taken over |
| `builtin` | `ergostat.model.fit`, `.unexplained`, `.unidentified-loops` or `.open-findings` | | On a stock or an auxiliary: one of ergostat's built-in measures of the model's own quality (section 12e), read by ergostat itself (`ergostat measure ergostat.model.fit`, in a process of its own; `timeout` 2m by default) |
| `averages` | duration | none | On a flow's `run`, `query` or `manual` sensor: its reading is the average rate over this window before it (a count of the last ten minutes, per hour: `averages: 10m`). The model's rate is read through the same window before it is compared (section 12b) |
| `where` | map of field → value (or list) | | Only items whose fields match |
| `every` | duration | `1m` | How often it reads (`run`, `query`) |
| `cron` | cron expression | | Instead of `every` |
| `timeout` | duration | `30s` | |
| `parse` | regex with one group | | Takes the number from a line of text |
| `unit` | string | the stock's | Must equal the stock's (or the flow's rate unit) |

On a flow, a sensor's reading is a rate per hour; on a `two-way` flow it may be negative (it ran
back).

`changes` measures a flow by what it did to its stock: a benchmark's score rising with a release
is its inflow, a sudden fall its outflow. It is how a stock read by a script gets measured flows
without a second instrument (the flows are then only as true as the stock's readings, and see only
the net change between two readings).

A `run` sensor may also print what it observed about items, one JSON line each, beside its number:
`{"event": "case.met", "item": "case/logo-3", "data": {...}}` (a benchmark that records each case
it measured). These are recorded as events from the sensor (`benchmark-score.main`) and fold into
the items like any other. An observation records what was seen, never a command: it must name an
item (an id with a `/`), may not use ergostat's own types, and a sensor has no outputs. A measured
value is shown as measured by its sensor; an auxiliary a block sets is shown as set by that block.

## 7. Flows

What changes stocks: into one, out of one, or from one to another. Leaving out `from` or `to`
means outside the system (at least one is required). A flow is passive: it says which stocks it
connects, never what moves it.

```yaml
flows:
  arrivals:
    to: inbox
  processed:
    from: inbox
    to: outbox
  time-passing:
    to: report-age
    rate: 3600                   # a known, declared rate per hour
  churn:
    to: stale-docs
    sensor:                      # a measured rate
      run: ./churn.sh
      every: 5m
```

| Key | Type | Default | Meaning |
|---|---|---|---|
| `from`, `to` | stock name | outside | The stocks it drains and fills |
| `unit` | string | the stocks' | Must equal theirs |
| `rate` | number | none | A known, declared rate per hour |
| `sensors` / `sensor` | | none | Measurements of its rate |
| `driven-by` | flow, stock or auxiliary references, each optionally signed | none | What its rate follows: an influence from elsewhere in the system (see below) |
| `two-way` | bool | false | It may run either way (system dynamics' biflow): a block may move it by a negative amount, and its sensor may read a negative rate |
| `inferred` | model-change id, or `true` | none (declared) | Added by ergostat: the model change that added it (section 12e, *Inferred and declared*) |
| `system`, `description` | | | |

**`driven-by`: an influence, not a pipe.** Some flows are moved by nothing in the model, yet follow
something that is: a deploy (`flow.deployed`) is what fixes the product's broken features
(`flow.fixed`), though nothing pipes one into the other. `driven-by: [flow.deployed]` says so. It
is a claim about how the system works, drawn as a dashed arrow; nothing checks it against the
record yet. It also lets a loop close the long way (section 12).
It never says who moves the flow. Each reference may be signed (`+flow.deployed`,
`-stock.bugs-live`): the influence's polarity, used to find which feedback loops reinforce and which
balance (section 12a).

**A connector acts at once.** In system dynamics a link between two variables is instantaneous: a
flow driven by another flow says its rate now depends on the other's rate now. When the cause acts
over time (a flag ramped without review breaks something hours later, if at all), what the first
flow moves accumulates in a stock, and the second follows that stock: the delay is the stock
(`check` reports a flow driven by a flow as **rate-driven-by-rate**). Where the dependence really is
immediate (a release fixes what it fixes as it goes live; the next document is needed the moment the
last is approved), the link says so, written out:

```yaml
flows:
  fixes:
    from: bugs-live
    driven-by:
      - +stock.bugs-live                       # it takes a share of what is there
      - cause: +flow.deployed
        instant: true                          # as the release goes live: nothing between
        description: a release fixes what it fixes when it is deployed
```

| Key | Type | Meaning |
|---|---|---|
| `cause` | a reference, optionally signed | What it follows, as in the short form |
| `instant` | bool | The effect follows the cause in the same moment, with no stock between; `explain` says "at once" |
| `description` | string | |
| `inferred` | model-change id, or `true` | Added by ergostat: the model change that added the link (section 12e) |

A flow that follows a flow of something else (alerts following ramps) moves so many of its own units
for each of the other's: a **coflow** (Sterman, ch. 12). The ratio is an auxiliary
(`unit: alerts/ramp`, `exogenous: true` while it is not measured), and the flow is driven by both;
or, for an outflow, by the stock it takes from (`check`: **units-mismatch**).

**Polarity of structure.** A flow is + on the stock it fills and − on the stock it drains; a
two-way flow is the same, counted in its direction (from `from` to `to`).

**Two-way flows.** A flow runs one way: what a block moves along it is 0 or more, and a negative
amount is refused. `two-way: true` lets it run back: a setting a controller steps up and down, a
window of measurements whose level rises and falls as what it holds turns over.

What sets a flow is the block whose `out` names it (at most one). Seen from a goal's loop:

- a flow set by a block that the loop's controller commands is that loop's **valve**;
- any other flow on the goal's stock is a **disturbance** to that loop: set by nothing in the
  model (its rate declared, measured, or estimated from what the stock does that the other flows
  do not explain), by an `external` block (something known, not run by ergostat), or by a block
  no controller of this loop commands.

## 7a. Auxiliaries

A quantity without memory: determined at each moment by others, through an equation (written, section
7b, or else measured). System dynamics calls it an auxiliary (or converter). A ratio of two
stocks, a difference between two builds measured on the same images, a share that is a function of
the clock. Nothing flows into it, and it keeps nothing between moments.

Memory decides the kind, not how something is measured or what it is used for. What persists when
nothing happens and changes only through some process is a stock (section 5), even when it is a
setting, a score or a statistic over a window of what is served; what is a momentary function of
other things is an auxiliary. *Process variable* and *manipulated variable* are not kinds: they are
roles a part plays in a control loop (what its goal holds; what its controller turns), said by
`explain` and the page, never written.

```yaml
auxiliaries:
  quality-change:
    unit: ssim
    description: how much better the candidate looks than production, on the same images
    sensor:
      run: python3 world/read.py quality-change
      every: 8s
    driven-by: +stock.candidate-offset          # what it follows, and which way
  flat-share:
    unit: share
    exogenous: true                             # from outside the model: nothing in it drives it
    description: how much of the mix is flat images, a function of the clock
```

| Key | Type | Default | Meaning |
|---|---|---|---|
| `unit`, `system`, `description` | | | |
| `sensors` / `sensor` | | none | How it is measured (section 6), as a stock is |
| `driven-by` | references, each optionally signed | none | What it follows (flows, stocks, auxiliaries): an influence, as on a flow |
| `exogenous` | bool | false | An input from outside the model (system dynamics' exogenous input); it then has no `driven-by` |
| `inferred` | model-change id, or `true` | none (declared) | Added by ergostat: the model change that added it (section 12e, *Inferred and declared*) |

A block may set an auxiliary by naming it in `out:` (`out: auxiliary.flat-share`) and printing its
whole value each run (`{"out": "auxiliary.flat-share", "value": 0.3}`, or a bare number); what it
set is the auxiliary's reading, as if a sensor named `set` had read it, and is recorded as
`auxiliary.set`. One block sets an auxiliary. *Decided:* this is kept only for what is genuinely
memoryless, a value the block states afresh from what it reads now (a proportional controller's
output, a schedule, the world's mix brought in from outside). A controller whose output is its
last output plus a step (integral action) keeps memory: what it turns is a stock, and it moves it
through a two-way flow (`out: flow.quality-steps`, `{"moved": -2.5}`).

```yaml
stocks:
  quality-setting:                              # a setting the tuner steps: a stock
    unit: q
    sensor:
      run: python3 world/read.py quality-setting
flows:
  quality-steps:
    to: quality-setting
    two-way: true
blocks:
  tuner:
    type: program
    run: python3 bin/tune.py                    # prints {"out": "flow.quality-steps", "moved": <the step>}
    in: goal.quality-held.error
    out: flow.quality-steps
```

A goal may be about an auxiliary (`auxiliary: quality-change`), and its loop closes when what the
controller moves reaches it: directly, or through what it drives (a stock the controller steps,
then the auxiliary or the flow that follows it).

A stock no flow fills or drains is reported (`stock-without-flows`): give it its flows, or, if it
has no memory, make it an auxiliary.

## 7b. Equations and parameters

A flow's rate and an auxiliary's value may be written as an **equation**, the way Vensim and Stella
write them, in the model's own names; the numbers it names are **parameters**. A stock needs none:
it is the integral of its flows, exactly. Without an equation a flow or an auxiliary is what its
sensor reads, or what the block that sets it says.

```yaml
parameters:
  workdays-per-hour:
    value: 60
    unit: workdays/h
  alerts-base:
    value: 1.2
    unit: alerts/workday
    estimate: true                              # fitted from the record (section 12b)
  alerts-per-outage:
    value: 4
    unit: alerts/outage
  window-time:
    value: 19.2s                                # a duration, read in hours
  effect-of-load:
    table: [[0, 1], [10, 0.5], [20, 0.2]]       # a lookup: linear between its points
  k: 0.45                                       # short for value: 0.45
flows:
  alerts-fired:
    to: alerts-to-draft
    driven-by: [{cause: +flow.outages-noticed, instant: true}]
    equation: workdays-per-hour * alerts-base + alerts-per-outage * flow.outages-noticed   # a coflow
  quality-turnover:
    to: quality
    two-way: true
    driven-by: [+auxiliary.batch-quality, -stock.quality]
    equation: (auxiliary.batch-quality - stock.quality) / window-time   # first-order smoothing
```

| Key | Type | Default | Meaning |
|---|---|---|---|
| `equation` | expression | none | On a flow: its rate per hour; on an auxiliary: its value. Not with `rate:` on the same flow |
| a parameter's `value` | number or duration | none (not known) | What it is believed to be; a duration (`40s`, `2h`) is read in hours, the model's time |
| `unit` | string | none | Its unit, products and quotients of words (`alerts/ramp/workday`, `1/h`); `share` and `1` are pure numbers. Time is counted in hours: a unit counting it in `s`, `min`, `d` or `week` is an error (*decided*: 30 with `unit: min` would be read as 30 hours), so a time is written as a duration and a rate per hour; a model's own clock (`workdays`, with `workdays-per-hour`) is a word like any other |
| `estimate` | bool | false | Fitted from the record (section 12b): the estimate is kept apart and proposed, never written here until it is accepted |
| `table` | points | none | A lookup, called like a function: `effect-of-load(stock.queue)` |
| `range` | `[low, high]`, numbers or durations | none | What it might be: sensitivity analysis samples it uniformly there, calibration keeps to it, and the extreme-conditions test pushes it to its ends (sections 12b, 12c). A value outside it is a finding (**parameter-range**) |
| a parameter's `inferred` | model-change id, or `true` | none (declared) | Added by ergostat: the model change that added it (section 12e) |
| `system`, `description` | | | |

**Expressions.** Numbers; parameters by their bare name; parts by reference (`stock.x`, `flow.x`,
`auxiliary.x`: a flow is its rate per hour); `+ - * / ^` and brackets; `MIN`, `MAX`, `ABS`, `EXP`,
`LN`, `SQRT`, `ZIDZ(a, b)` and `XIDZ(a, b, x)` (a / b, or 0, or x, where b is 0); and system dynamics' delays: `DELAY1(x, T)` and `DELAY3(x, T)`, material delays of
the first and third order (what goes in comes out after `T` on average, and nothing is lost), and
`SMOOTH(x, T)` and `SMOOTH3(x, T)`, information delays (exponential smoothing toward `x` over `T`).
Each delay keeps hidden stocks of its own, starting in equilibrium with its input. Names have
hyphens in them, so subtraction is written with spaces: `a - b`. Nothing that fails is hidden: a
division by 0 written with `/`, the logarithm or square root of a number out of range, a negative
number to a fractional power and an overflow are each taken as 0 and counted, and the run's notes
say which equation did it how often (write `ZIDZ(a, b)` where 0 is meant); a value past 10¹² is
clamped and makes the run not valid.

**Every number says where it comes from**, its **provenance**: *declared* (its value is written
here), *estimated* (fitted from the record, with how well, from how many points, and when: kept in
the state directory, section 12b), or *unknown* (no value yet). The page and `ergostat explain`
show each beside the equation; the replay uses only what is declared, so nothing estimated changes
the model until the owner accepts it.

**Checks.** Errors: an equation that does not read; a bare name that is not a parameter (with the
hint to write `a - b` when `a-b` was meant); a reference to a part that does not exist, or to the
part itself (what it was a moment ago is a stock); a flow with both `rate:` and `equation:`; an
`exogenous` auxiliary whose equation names parts of the model; equations that need each other at
once with no stock or delay between (an algebraic loop); a lookup used as a number. Findings:

- **delay-drains-late**: a flow out of a stock whose equation is a DELAY1 or DELAY3 of its own stock's level
  (`DELAY3(k * stock.a, t)`, from `a`): it takes what the level called for a delay ago, so the stock drains late
  and can go below empty. A material delay is two flows: what leaves the stock at once, and, into the next stock,
  `DELAY3(flow.leaves, t)`.
- **equation-units**: where units are written, an equation must add like things and come out in
  its part's unit (a flow's per hour); a number written in it takes the unit it needs, and anything
  whose unit is not written is not checked;
- **equation-sign**: a `driven-by` written with a sign the equation contradicts. A link's polarity is
  the sign of the partial derivative (Sterman ch. 5.2), so each is worked out by finite differences
  across a range of operating points (every part at 0.25 to 50, the parameters at their values,
  each delay in equilibrium): the other sign wherever it was tried, or a sign that changes across
  the range, is said, since every loop drawn through the link would have the wrong polarity;
- **size-unknown**: a `driven-by` the equation does not use: the link is drawn, with its sign, and
  its size is not known (the equation says it has none);
- **equation-not-drawn**: a part the equation uses that `driven-by` does not name, so the diagram
  draws no connector for it and no loop runs through it;
- **parameter-unknown**: a parameter with no value that is not to be estimated; equations using it
  are left out of the replay (their parts are taken as measured);
- **parameter-unused**: a parameter no equation uses;
- **parameter-range**: a parameter whose value is outside its `range`;
- **extreme-conditions**: the model's equations pushed to the extreme do what the world cannot (section 12c).

## 8. Goals

What we want. Each goal is about exactly one stock (its level), one flow (its rate) or one auxiliary
(its value).

```yaml
goals:
  inbox-short:
    stock: inbox
    hold: "<= 20"
    tolerance: 5
  disk-headroom:
    stock: disk
    hold: "<= 80"
    critical: true
    owner: platform
  low-errors:
    flow: errors                 # a goal on a rate
    hold: "<= 1"
```

| Key | Type | Default | Meaning |
|---|---|---|---|
| `stock`, `flow` or `auxiliary` | name | required, exactly one | What it is about: a stock's level, a flow's rate, or an auxiliary's value (`variable:`, its old name, is still read) |
| `hold` | setpoint | required | The setpoint |
| `tolerance` | number | 0 | Hysteresis for the status: off past the setpoint by more than this; holding again only back within the setpoint (for `==`, within half of it) |
| `critical` | bool | false | It guards against a cascade or an accumulating failure: watched for decay |
| `owner` | string | none | Who answers for it |
| `process` | map | none | The loop's process, from what its controller moves (u) to what the goal holds (y), as control engineering writes it: `gain` (y per u), `time-constant` and `dead-time` (durations): P(s) = K e^(−θs)/(τs + 1); or `integrating: true`, `gain` per hour and `dead-time`: P(s) = k e^(−θs)/s. `identified:` says it was accepted from an identification (when, how, on how much record); without it, it is declared (section 12d) |
| `system`, `description` | | | |

A goal exists whether or not anything serves it. A goal nothing serves is **missing feedback**.

## 9. Blocks

A block is a function: inputs to outputs. Blocks are the information layer: system dynamics'
converters and control engineering's function blocks. Every controller, every actuator, and every
piece of logic between them is a block.

```yaml
blocks:
  keep-short:
    type: onoff
    goal: inbox-short            # on while the goal is off ...
    until: "<= 15"               # ... until the stock is back to here
    out: block.worker            # commands the worker

  worker:
    type: program
    run: ./process.sh
    in: block.keep-short         # runs while commanded
    out: flow.processed          # reports what it moved along this flow
    max: 25                      # the most one run may move
```

Common keys:

| Key | Type | Meaning |
|---|---|---|
| `type` | block type | What it computes (below) |
| `in` | reference, list, or map of port → reference | Its inputs. On a machine block, a stock, flow or auxiliary read may carry its sign, as a `driven-by` does: `+stock.x` (it does more as x rises), `-stock.x` (less); see §12a |
| `out` | reference, list, or map of port → reference | Where its outputs go: a flow (it sets that flow), another block (it commands it), or a goal's setpoint (cascade) |
| `role` | `controller`, `actuator`, `logic` | Optional label, for drawing and checks. Derived when left out |
| `system`, `description` | | |

Every block has an output. A block with none has no visible effect: either it does nothing worth
modelling, or the flow it changes is missing from the model; `check` reports it.

### 9.1 How blocks run

- **Built-in blocks** (9.2) are executed by ergostat itself, on every reading of their inputs:
  no program, no machine. They are how ergostat closes loops by itself.
- **Machine blocks** (9.3) run a program, an AI prompt or a request to a person. They run:
  - when an input commands them (the input becomes nonzero, or a new command arrives); or
  - on their own schedule (`every`, `cron`), when nothing commands them: an open loop.

  A machine block never runs twice at once. A command that arrives while it is running is held,
  not queued (anti-windup): the latest command is used when it finishes. Without an `agent`, a
  machine block runs locally, launched by ergostat.
- **External blocks** (`type: external`) are performed by something ergostat does not run (an
  autoscaler, a Kubernetes controller, a team). They are declared for the structure: their
  inputs and outputs are what that thing reads and moves, judged by the stocks' and flows'
  sensors.

A machine block receives on standard input (or, for `ai`, in its prompt):

```json
{"block": "worker", "command": {"amount": 12, "from": "keep-short"},
 "inputs": {"stock.inbox": 32, "goal.inbox-short.error": -12},
 "goals": {"inbox-short": {"hold": "<= 20", "value": 32, "error": -12, "status": "off"}},
 "trigger": "command"}
```

and reports on standard output, one JSON line per output, or a bare number when it has a single
output:

```json
{"out": "flow.processed", "moved": 12}
{"out": "block.writer", "command": {"amount": 3, "item": "install.md"}}
{"decision": "12 waiting: process them", "why": "over the goal by 12"}
{"propose": {"kind": "parameter", "parts": ["parameter.k"], "edit": {...}, "reasons": [...], "confidence": 0.6}}
{"claim": {"says": "tests pass", "about": "hypothesis/3"}}
{"answer": {"message": "ergostat.message/1a2b3c4d5e", "says": "left review/2041 for later"}}
```

Its input also carries, under `messages`, the owner's messages that waited for it (section 12h), when there are any.

ergostat records what was **commanded** and what was **moved**: the gap is the direct evidence of
saturation.

### 9.2 Built-in block types

A first set, kept small:

| Type | Inputs | Output | Parameters |
|---|---|---|---|
| `onoff` | a goal | 1 while it should act, else 0 | `goal`, `until` (the release point: hysteresis), `min-on`, `min-off` |
| `compare` | one signal | 1 or 0 | `above` or `below`, `back-below` / `back-above` |
| `proportional` | a goal | an amount: `gain × error`, clamped | `goal`, `gain`, `min`, `max` |
| `limit` | one signal | the signal, clamped | `min`, `max`, `rate` (most change per hour) |
| `delay` | one signal | the signal, later | `delay` (a duration) |
| `schedule` | none (time) | a value by time of day or week | `table`: times to values (a lookup on the clock) |
| `lookup` | one signal | a value from a table | `table`: points, linear between them |
| `select` | several | the minimum, maximum, or the first nonzero | `pick: min`, `max` or `first` |
| `expr` | several | an arithmetic expression of them | `expr: a * 2 + b`, with `in` as a map naming them |
| `timer` | one signal | 1 once it has been nonzero this long | `after` |
| `counter` | one signal | how many times it became nonzero | `reset` (a duration) |
| `alarm` | one signal | raises a finding while out of bounds | `above`, `below`, `for` |
| `judge` | what it reads, for the diagram | what it moved on its ports (`testing`, `passed`, `failed`, `accepted`: flows) | `every`, `hold-out`, `windows`, `threshold`, `accept`: the judge of changes to the model, on its own clock and on the program rung (section 12e) |

More (filters, rate of change, latches) can be added when a case needs them.

### 9.3 Machine block types

| Type | What it runs | Key fields |
|---|---|---|
| `program` | a shell command | `run`, `parse` |
| `ai` | a prompt, given to a model | `prompt` (text or a file), `model` (when it has no agent), `run` (an optional wrapper command) |
| `person` | a request to a person | `ask` (what they are asked to do); they report with `ergostat block NAME --done ...` |
| `external` | nothing: observed only | none |

Common to machine blocks: `agent` (optional: the shared machine it runs on, section 10), `max`
and `min` (limits on one run's amount), `timeout`, `every`/`cron` (its schedule when nothing commands it; when something does, `every`
is the least time between runs),
`mode` (`auto`, or `advise`: its commands wait for a person to approve), and its control law's
constants when it says them: `gain` (for a block that steps a setting by its goal's error, the step
per unit of error, acting at once on the error it has just read, u_k = u_(k−1) + gain × e_k: integral
action, C(z) = gain·z/(z − 1)), `integral-time` (with `gain`, a PI law in velocity form), `deadband`
(no step while the error is within ± it), `resolution` (the setting is rounded to steps of it) and
`limits` (`[least, most]`: the setting it steps is kept within them; not `min`/`max`, which limit one
run's amount). They are given to it in its input as `params`, so the program reads them from the
model rather than holding its own copy, and a tuning accepted (section 12d) reaches it at its next
run.

**A step test.** A block run for a step test the owner approved (section 12d) is given
`"trigger": "step-test"` and `"command": {"amount": Δ, "test": ID}`, to move its flow by exactly Δ,
or, to put the setting back, `"command": {"amount": Δ, "to": value, "test": ID}`, to put it at that
value; it decides nothing else, and says what it moved (its output line), which must be the step
commanded to within the setting's resolution, or the test stops. A block that cannot is not offered
one.

**A machine block may name its goal.** `goal: inbox-short` (and optionally `until:`) on a
`program`, `ai` or `person` block means "run while this goal is off, until it is back to `until`
(or holding)". It is the commonest loop there is ("when the disk is over 80%, clean it"), written
in one block: ergostat puts an `onoff` block in front of it, named `keep-<goal>` (one per goal
and release point, shared by every block that names it), and draws and runs it like any other.
`ergostat block` lists it as implied. *Decided* (question 1).

```yaml
blocks:
  worker:
    type: program
    goal: inbox-short            # runs while the goal is off ...
    until: "<= 15"               # ... until the inbox is back to 15
    run: ./process.sh
    out: flow.processed
```

**How a commanded block runs.** While its command is nonzero it runs, once per fresh reading:
after each run it waits for a new reading of the system before running again, so it never
outruns its sensors. `every` on a commanded block paces it: it runs at most that often while
commanded (a worker pool that is always commanded would otherwise run back to back). When it moves a flow, the sensors of that flow's stocks read at once. The
command it gets is clamped to its `max` (and `min`); `block.commanded` records both the clamped
amount and, when they differ, what was asked.

**Reading a machine block's output.** A bare number goes to its single output (a flow: what it
moved; a block: a command; a goal: a setpoint). JSON lines may also be `{"moved": n}` without
`out` when it moves one flow, and `{"event": "backup.verified", "item": "backup/nightly"}` for
anything else that happened (an event about an item, section 5a: `data` holds its fields, folded by
its kind's rules; or, in place of `data`, a JSON `patch` or the whole document, `set`). Lines that are not JSON go to its log (`logs/<block>.log` in the state
directory). Its environment carries `ERGOSTAT_BLOCK`, `ERGOSTAT_COMMAND` (the amount),
`ERGOSTAT_STATE_DIR`, and `ERGOSTAT_CMD`, the command that runs this ergostat on this project
(`$ERGOSTAT_CMD item --kind ticket --state open --json`, `$ERGOSTAT_CMD event --add ...`), for a
block, or the AI agent it starts, to read and record items while it works. An `ai` block without `run` is given to `claude -p` (or `$ERGOSTAT_AI`),
with its prompt, the JSON above, and how to answer. Any block, whatever its type, may also propose a change to
the model, `{"propose": {...}}` (section 12e); `agent.ran` counts what it proposed and what was not taken. And any
block may say what it did, `{"claim": {"says": "tests pass", "about": ...}}`: ergostat checks it after the run,
against the record and the world, never taking the block's word (section 12g). And any block may answer a message the
owner sent, `{"answer": {"message": ID, "says": ...}}`; a classifier answers where one goes with `route` lines (section
12h).

### 9.4 Roles

Roles are derived (or labelled with `role:`):

- a block whose output is a flow is an **actuator** (the flow's valve);
- a block whose output commands another block, or sets a goal's setpoint, and that reads a goal
  or a stock, is a **controller**;
- anything else is **logic**.

Sensors are not blocks: they are always inside a stock or flow. At most one block may output to a
given flow.

## 10. Agents

A machine shared by several blocks. Declare one only to say something true across them; whatever
concerns one block alone belongs on the block.

```yaml
agents:
  claude:
    kind: ai
    model: claude-opus-5-5
    at-once: 2                   # the blocks on it share this
    cost: 0.02/run
  oncall:
    kind: person
  hpa:
    external: true               # ergostat only observes it
  build-box:
    host: build-box.internal
    at-once: 4
```

| Key | Type | Default | Meaning |
|---|---|---|---|
| `kind` | `person`, `ai`, `narrow-ai`, `decision`, `program`, `rule` | from its blocks | Its rung on the ladder, when it adds something to the blocks' types |
| `external` | bool | false | ergostat never runs it; it only observes what its blocks do |
| `at-once` | integer | 1 | How many of its blocks may run at the same time |
| `model` | string | none | For an AI machine: which model |
| `cost` | string | none | What a run costs, for budgets counted across its blocks |
| `host` | string | local | Where its commands run (local only at first) |
| `description` | string | none | |

What an agent is for:

- **shared limits**: blocks on one machine queue behind its `at-once`, and ergostat can show the
  machine as a bottleneck;
- **identity**: a named person, an on-call rotation, an AI allowance, an external system, whose
  work and response times are seen across every block it fills;
- **location**: a host, for every block sent there;
- **budgets**: cost counted across its blocks.

Which blocks an agent runs is looked up from the blocks' `agent:`.

## 11. Sources

Where existing measurements live. Read only.

```yaml
sources:
  prom:
    type: prometheus
    url: http://prometheus:9090
```

| `type` | Fields | A sensor's `query` |
|---|---|---|
| `prometheus` | `url` | `source` and `promql`: an instant query, which must return one series |
| `command` | none | (the same as `run`) |

More types (Datadog, CloudWatch, SQL) can follow the same shape.

## 12. What ergostat derives and checks

**Derived** (never written): valves and actuators, controllers, disturbances, errors, loops
(a goal, the sensors of what it is about, the blocks serving it, and the flows they set), the
stock-and-flow diagram, block diagrams, the wiring of agents.

**A loop that closes the long way.** When nothing a goal's controller commands moves a flow of the
goal's stock directly, the loop may still close through other stocks: the controller moves work
into a queue (it files tickets into a backlog), that queue's own goal and blocks work it off, and
what they move drives a flow of the first stock (`driven-by`). ergostat finds the shortest such
path, from the controller through blocks, flows, stocks and influences to a flow of the goal's
stock, and the loop closes along it (`explain` names each part). Its delay is the sum of every
queue along the way.

An integral controller closes the same way, through one stock: it steps a setting (a two-way flow
into a stock that keeps its value between steps), and what its goal holds is driven by that
setting. `explain` says so: the setting is the loop's manipulated variable, and the loop settles
where the error is 0.

**Errors** (the model is refused until fixed; each names the file and line):

- a reference to something that does not exist, or of the wrong kind;
- a name defined twice;
- a flow with neither `from` nor `to`;
- a goal without exactly one of `stock`, `flow` and `auxiliary`, without `hold`, or with a
  setpoint that does not parse;
- a sensor with none or more than one of `run`, `query`, `manual`, `items`, `changes` (or
  `changes` on a flow between two stocks, `rises` on an outflow, `falls` on an inflow, `net` on a
  one-way flow);
- a negative amount moved along a flow that is not `two-way` (refused when the block reports it);
- an `exogenous` auxiliary that is also `driven-by` something;
- an item kind whose `id` has no `/`, an `on` naming a state not in `states`, or a sensor counting
  a kind or state that does not exist (or `state`/`measure` on a flow, `entering`/`leaving`/`over`
  on a stock);
- two blocks outputting to the same flow;
- a `run`, `prompt` or `ask` on an external block, or a built-in block with an `agent`;
- a block whose agent cannot run its type (an `ai` block on an agent of kind `person`);
- units that disagree between a flow and its stocks, or a sensor and what it measures;
- a cycle of built-in blocks with no delay (an algebraic loop).

**Findings** (reported, not errors):

- **missing feedback**: a goal no block serves;
- **unjudgeable goal**: a goal on something with no sensor;
- **heading for a limit**: a stock with a `limit`, growing, and no goal: time to failure;
- **no visible effect**: a block with no output;
- **acting on its own**: an actuator nothing commands (an open loop);
- **competing commands**: two controllers commanding one block;
- **its own disturbance**: a controller that also adds to the stock it holds;
- **critical goal decaying**: answering more slowly, saturating more often, its machine changed;
- **deprecated name**: `variables:`, `variable.x` or a goal's `variable:`, still read; rename to
  `auxiliaries:`, `auxiliary.x`, `auxiliary:`.

**Structure** (findings, the tests system dynamics makes of a model's structure before its
behaviour: Sterman, *Business Dynamics*, ch. 21, structure assessment, dimensional consistency and
extreme conditions; each says its fix and the YAML that writes it; `docs/MODELLING.md` explains
them for someone new to system dynamics):

- **rate-driven-by-rate**: a flow `driven-by` another flow. A connector acts at once, so a cause
  acting over time goes through a stock: what the first moves accumulates, and the second follows
  that stock. Silenced by `instant: true` on the link (section 7) where it really is immediate;
- **stock-without-outflow**: flows fill a stock and none drains it (no outflow, no two-way flow),
  so in the model it can only grow. Give it the outflow, or say it is a running total
  (`cumulative: true`, section 5);
- **units-mismatch**: a flow driven by a flow in another unit (both declared; counts compared with
  any per-hour taken off; shares, percentages and compound units left alone), with no auxiliary
  among its causes to convert, and not driven by the stock it drains. Name the ratio as an auxiliary;
- **outflow-ignores-stock**: an outflow nothing sets, `driven-by` things that are not its stock (nor
  an auxiliary driven by it): with the stock empty it would still run and take it below zero (the
  extreme-conditions test). Drive it from the stock as well;
- **auxiliary-without-causes**: an auxiliary nothing drives, nothing sets and not `exogenous`: the
  model cannot say why it changes. Name its causes, or mark it `exogenous: true`.
- **extreme-conditions**: the behaviour test of extreme conditions (section 12c): the equations run
  with the stocks empty, with nothing coming in, with each input alone at 0 and at a hundred times its
  largest, and with each estimated, timed or ranged parameter alone at its extremes, and a stock
  drained below empty, a one-way flow running backwards, a division by 0 or a blow-up is said, with
  the input or parameter that showed it and the fix.

## 12a. Feedback loops (system dynamics)

Worked out, never written: every cycle of cause and effect through stocks, flows, auxiliaries,
goals and blocks (`ergostat/spec/causal.py`; `explain` lists them, and the graph API gives each
one's members, polarity and name). Each link has a sign:

| Link | Sign |
|---|---|
| a flow → the stock it fills / drains | + / − |
| a `driven-by` | as written; unsigned: not known |
| what a goal is about → the goal's error, e = r − y | − |
| a goal → a block reading its error | + (a controller acts on its error: that is what serving a goal means) |
| a goal → a block acting while it is off (`.off`, an `onoff` or `proportional` on it, the goal itself) | + for a floor (`>=`), − for a ceiling (`<=`), not known for `==` |
| a block → the block it commands | + for a machine block; a built-in's own sign (`compare below` and a falling `lookup` −, `expr` not known) |
| a block → what it moves, sets or commands (a setpoint it sets raises the error) | + |
| a stock, flow or auxiliary → a machine block that reads it | as written on the read (`in: +stock.x`); unsigned, as the gap of a goal the block serves that is about that very quantity says (+ for a ceiling, − for a floor, not known for `==`), else not known |

A block **serves** the goals it names (`goal:`, or reading `goal.x`); one that names none serves the
goals whose loop closes with it as a controller or an actuator (section 12). So a block reading a
stock its own goal keeps down acts the more, the higher the stock: `rollout` reading `failures`
for `no-failures ≤ 0` is +. A link whose sign is still not known is reported by `check`
(**unsigned-link**, one finding per block or flow, naming each read or `driven-by`): every loop
through it is of unknown polarity until it is signed. An exogenous input is in no loop, so its
unsigned influence is not reported.

A loop is **R** (reinforcing) when the product of its signs is +, **B** (balancing) when −, and of
unknown polarity when any sign along it is not known. A goal-seeking loop whose links are all known
comes out balancing, as it should; one that comes out reinforcing is a controller pushing the wrong
way.

**Names.** A loop's name is how system dynamics people talk about it ("rework", "word of mouth"),
so the model may give it one:

```yaml
loops:
  rework:                        # the shortest loop through every part named
    through: [flow.rejected, stock.backlog]
    description: rejected work goes back to the backlog
  quality:                       # or the shortest loop that seeks this goal
    goal: quality-held
```

| Key | Type | Meaning |
|---|---|---|
| `through` | list of references | The parts it runs through (any of them, in any order); the shortest loop through all of them takes the name |
| `goal` | goal name | The shortest loop through this goal takes the name |
| `description` | | |

One of `through` and `goal`; a reference that does not exist is an error. A loop the model does
not name takes its **head**: the goal it seeks (the first, by name, when it seeks several), else the
first stock it runs through. The shortest loop with a head takes it bare (`backlog-clear`); every
other loop with that head is the head "via" the fewest of its members no sibling loop has, flows
first, then stocks, auxiliaries, goals and blocks (`backlog-clear via rejected`). Never numbered,
never a list of everything in it.

**Drawn** (the dynamics view, `ergostat/dynamics.py`): each loop is labelled as Sterman numbers them,
R1, B1 (the shortest first, the ones the model names before others of their length), with its name
beneath. Only loops of known polarity are marked on the diagram, each inside the loop as drawn; the
others are one entry beside it, "+N of unknown polarity", that opens to list them. A goal is drawn
as a desired level (a value: `desired backlog = 0`) and the discrepancy that drives the correction +:
for a ceiling the **excess** (actual − desired), for a floor or a level held the **gap** (desired −
actual); when the decisions serving it switch (on while backlog > 0, off once it is ≤ 0), the panel
says so. A line between two parts both drawn, in open systems or not, is drawn as itself; only
where its other end is not on the canvas is it cut: a connector out of a closed module into an
open system comes from a shadow variable `<x>` inside the receiving system, and a shadow is an
input only, so a connector out to a part not drawn ends at a stub naming what it drives, and a
pipe out ends in a cloud with the part beyond named under it. An
open system is a sector, a light tint with its name at the top left; a closed one is a module, its
connection points named on its edge. The view's panels use system dynamics' words only. A flow's
valve (the bowtie) opens as the **valve**: the rate of the flow, its inputs (the connectors into it,
each with its sign) and its equation: written (section 7b), drawn in MathML with each parameter's
value and provenance (its calibrations side by side beneath: each one's estimate ± its standard error,
from how many points, and whether it is proposed or why not) and any proposal for it, with Accept; else a constant declared (`rate:`), the
decision that sets it, or "not known yet: a declared cause with a sign, its size not estimated"
(and which causes act at once). An auxiliary's panel shows its equation the same way. The causes
strip draws the model's replay dashed over the measured line, and its projection past now dashed
and lighter (section 12b), with the shaded fan of its sensitivity and, in the accent, a what-if beside it (section 12c);
each parameter's value in the panel may be typed over to try it. A feedback loop's panel draws how much of the
behaviour it drives over the window at each stock it runs through, beside the loops competing there
(loop dominance, section 12c). Its pipe opens as the **flow**: what moves (its unit and
description), from which stock, to which.

## 12b. Replay, projection, fit and proposals

**What is compared** (`ergostat/numbers/observe.py`): the record on a grid of equal buckets, and how
each part's record was made, so the model can be read the same way (Oliva 2003: fit the model's
output to the data through the same aggregation; Ljung ch. 4: an output-error predictor includes
the measurement). A **level** (a stock, an auxiliary) is its last reading in each bucket, and is
compared with the model at that reading's moment. A **counted** flow (items entering or leaving a
state, a valve's openings, a stock's own changes) is the amounts at the times they moved: it drives
the replay as it happened, and an equation for it is compared bucket by bucket with what it moved,
the model's own integral over the same bucket on the other side. A flow **read** as a rate is its
readings' mean in each bucket, compared with the model's rate averaged over the window the sensor
says its readings average over (`averages:`). The fit and the estimates look at the **reference
window**, the last day of record at most, in buckets of at least ten seconds, whatever window the
page shows (*decided*: a fit that changed with the page's window was not a fit of the model).

**Replay** (`ergostat/numbers/simulate.py`): the model run over the record, as system dynamics
calibrates a model (Oliva 2003; Homer 2012, partial-model testing). Each stock starts at its first
reading, at that reading's moment, and is integrated from its flows; each flow and auxiliary with an
equation is worked out from it; every other input (a flow a block moves, a rate a sensor reads, an
auxiliary from outside) is driven by what was measured, a counted flow by what moved when it moved.
So a stock whose flows are all counted replays its own readings exactly, and the replay tests
exactly the equations the model writes. With no stock integrated, every input is as measured: the
**partial-model test** of each equation. **The step** follows the model's dynamics, never its units
(Sterman app. A): at each bucket, how fast each stock answers itself and the others (|∂net/∂stock|
by finite differences of the compiled equations at the operating point, bounded by Gershgorin's
circles), a step a quarter of the fastest; a delay whose stages (T/order) are faster is stepped
through each step in smaller steps of its own, so what leaves its stages is what its flow moves.
Past 256 steps a bucket a stock's own drain is integrated implicitly (stable, settled at once) and
the notes say so; a run that hit the clamp, or whose stocks drive each other faster than its step,
is not valid, and is neither fitted nor shown as a fit.

**Projection**: open loop (*decided*, until the blocks' laws are simulated): from the state now
(each stock the mean of its last few readings, each delay as the replay left it), the inputs held
where they were (or carried on along their recent trend), the controllers held, for a horizon of
three of the slowest time constant the replay met, within a twentieth and a quarter of the window.
What a flow a block sets moves (that flow, its stocks, and what follows from them) is left out of
the projection, and the chart says so.

**Fit** (`ergostat fit`, the Model page), by Sterman's measures (*Business Dynamics* ch. 21;
"Appropriate summary statistics for evaluating the historical fit of system dynamics models",
1984): **R²** (the squared correlation: how much of the measured variation the replay moves with),
**MAPE** (the mean absolute error as a share of what was measured; where a reading is near 0 or
they cross it, the mean absolute error as a share of their mean or range instead), and **Theil's
inequality statistics**, which split the mean squared error into **U_M**, bias, **U_S**, unequal
variation and **U_C**, unequal covariation; they sum to 1, and a good fit's error is mostly U_C. A
large error (past a tenth of the readings' size) with U_M or U_S past 0.1 is said in words (runs
high, swings less than the record). Three tables: the **model fit**, the stocks an equation moves,
which alone make the total and its history. The total is led by its **payoff**, the **scaled error**:
each stock's mean squared error over its own size (its mean square measured), averaged, so no unit
outweighs another; it is what a calibration minimises, and what a proposal's "fit, in total" shows
(Oliva 2003). Theil's shares come from the same scaled errors; R² and MAPE are judged per stock (a
replay that does not move while its record does has R² 0, never none: a value that freezes a stock
never raises the total); the **equations**, each with its inputs as measured (the
partial-model test, the sharpest test of one equation) and replayed; and **accounting**, the stocks
moved only by measured flows, which test no equation (their error is a measurement's or a missing
flow's: the residuals). A flow measured only by its stock's `changes:` is judged by its stock's
replay, not against its own differenced readings. A series is judged only on ten points or more,
over at least three of the slowest time constant the replay met in it; else it says "too little
record". Each **version** of the model (a hash of its structure and the numbers written in it) has
its fit recorded with the span it covered (`<state>/fit/history.jsonl`, at most every five minutes
a version).

**Estimates** (`ergostat/numbers/estimate.py`): **calibration**, by optimisation over the replay
(Oliva 2003), in one of three ways, each the owner's choice (`ergostat proposals --calibrate`, the Model
page's Calibrate): **each part alone** (the default: what a parameter touches, each equation using it
in the partial-model test and every stock its flows move, replayed, the rest as measured; equations
are proposed only here), **each system alone** (Homer's partial model: a system's stocks integrated
from its flows, its equations worked out, everything that comes in from outside it as measured, an
equation outside it whose part is measured taken as measured; the parameters its equations use,
fitted to its stocks and its measured equations), or **every stock integrated** (only the inputs from
outside the model as measured; every `estimate: true` parameter together, fitted to every stock an
equation moves and every measured equation). The replay does not simulate the blocks, so what a
decision sets is still taken as measured, and every loop through a decision stays open: this one is
called "the whole model" only when no loop runs through one, else "every stock integrated; decisions
taken as measured", and the loops left open are listed in its proposals' reasons and on the Model page
(Homer 2012: name what is driven by data). Every `estimate: true` parameter is given
the value that makes what it is fitted to fit best; weighted least squares, each series' errors over its own spread
(the readings' standard deviation, at least 1% of their mean). Parameters that share an equation or
a stock are fitted together (Nelder–Mead, on their logarithm when they start positive, within the
parameter's `range` when one is written, the same bounds sensitivity samples, else within a factor of a
thousand of the value written), on the record but its last fifth, which is held out.
Each estimate has a standard error, and those fitted together their correlations, from the Jacobian
of the weighted errors at the optimum (Gauss–Newton, Ljung ch. 9), widened by (1 + ρ)/(1 − ρ) for errors that
run together in time, ρ their lag-one autocorrelation up to 0.99 (`numbers/identify.py`: a replay integrates
its errors, so a mismatch at one moment stays in every bucket after it, and the record holds as many independent
points as the errors have independent stretches, n(1 − ρ)/(1 + ρ), its **effective record**). An estimate is data: kept in `<state>/estimates/<structure>.json` (`<structure>.systems.json`,
`<structure>.whole.json` for the other calibrations, a system's keyed `parameter@system`), keyed by the
model's **structure** (a hash of what moves what: stocks, flows, links, equations, parameters' names
and units, not their values), so a value accepted keeps its estimates, and a changed structure
starts afresh.

**Proposals** (`ergostat proposals`, `ergostat accept ID`, `ergostat proposals --dismiss ID`, and an
Accept beside the part on the page): each a concrete change with its reason, the fit before and
after, and the smallest edit to the YAML that makes it, made on the file's text so its comments and
order stay. Two kinds so far. A **parameter** set to its estimate, only when the record supports it:
the record covers enough of the part's dynamics to identify it (Ljung ch. 13 and 16: an informative experiment),
it is fitted on forty points or more spanning three of the slowest time constant the parameter touches (for a
stock that only integrates, the time things stay in it, by Little's law), its effective record holds at least ten
independent points where the fit leaves a material error (its weighted error past 0.001, an RMS past 3% of the
readings' spread: it was past 0.01, and an image-squeeze record of 17 minutes drifting from its readings as one passed
as 80 points), and what it acts through **moved** six times (what the parameter multiplies in its equations, from
the Jacobian, going a tenth of its range from where it last moved: three cycles of an experiment started and
decided; one held at a single value the whole record cannot be told from a constant); otherwise it is **held,
inconclusive**, with how much more record it needs ("it needs about 30m more record", at the rate the record has
gone, or record in which what it acts through moves), said beside the parameter, and a block's proposal of a value
for it is recorded `inconclusive` at once with what it needs (`needs`), which the memory of what was turned away
(§12e) waits at least as long for. Then: the estimate is not at an end of
its range (the record would take it outside what the model says it might be: said first) nor at its
bound (one there is a question of structure), the record tells it apart, it is more than two
standard errors (within them, it says how much more record would tell a difference that size) and 2% from the value
written, and it fits the record held out better; otherwise it
is kept with why, shown beside the parameter and on the Model page, and proposes nothing. Its reason
and the numbers first shown are those of the objective it minimised, on the record fitted and the
record held out. An **equation** for a flow that has declared causes and none, a coefficient for
each cause by least squares on what was measured, proposed when it explains half or more of the
variation in the flow's readings (R² as 1 − SSE/SST) and agrees with every declared sign: an
outflow is first-order in its stock, written with the time things stay (`stock.x / time-in-x`), and
is proposed only when it names its stock as a cause; a one-way flow never gets a constant below 0
and never runs backwards (`MAX(0, …)`); a flow and a cause in a loop a controller closes carry the
warning that a regression there is biased (Ljung ch. 13). Nothing is applied by itself. Accepting
applies the edit, refuses it (and puts the file back) if `check` would then find an error, and
records `model.accepted` with the change, the versions before and after, and the fit of each on the
same record; a dismissed proposal is not made again for that structure. Each proposal says which
calibration made it, and asking again lets go only of that calibration's proposals still waiting. A
parameter proposal whose value written has changed since (another proposal for it accepted) is no
longer offered, and refused if accepted. A third kind is the owner's own: a **what-if** made a
proposal (section 12c), every value tried together in one, with its fit before and after, accepted
like the others; an accepted one is never overwritten (asking again makes another).

**Structural proposals** (`ergostat/numbers/structural.py`), looked for when the model changes and
every ten minutes: a change to what moves what, each the YAML edit that makes it. From `check`'s
findings with a concrete fix: *rate-driven-by-rate*, a stock between the two rates (the first fills it,
the second drains it and follows it; where both already join stocks, the stock gets two flows of its
own); *stock-without-outflow*, an outflow to a cloud, first-order in the stock with its time things
stay by Little's law (its mean level over what left an hour, the record's inflows less its rise), or,
when nothing left it, `cumulative: true`; *units-mismatch*, the converting auxiliary; *equation-sign*,
the equation's sign on the link (or none, where it changes sign); *extreme-conditions*, `MAX(0, …)` on
a one-way flow that runs backwards and `ZIDZ` on a division that faults; *auxiliary-without-causes*,
`exogenous: true`. From the estimators: a coefficient of a link ergostat inferred (the link, its part or the
parameter marked `inferred:`, §12e) indistinguishable from 0 (within two standard errors)
whose largest effect either way is under a tenth of its part's size is taken out with its link; a declared
sign that a least-squares fit of a flow on its causes (R² ≥ 0.5) contradicts is flipped. From SD Lab's
simplify rules (its SPEC §4.8), only as far as System Dynamics practice keeps them: structure **ergostat
inferred** (marked `inferred:`, §12e) **that the record shows to be redundant** is proposed for removal: an
inferred equation-only flow whose removal leaves the scaled error within 2%; two flows between the same two
stocks merged, the inferred ones merged away; an inferred stock nothing touches; an inferred stock that
carries exactly another's information (a twin: correlation past 0.999, scale within 5%, over an hour of
record or more, read together 60 times, each ranging over more than a tenth of its mean), removed (SD Lab
hides it; ergostat has no `hide:`, so the proposal removes it and makes its flows' ends there clouds). Each
says which part and why, carries `removes`, and waits for the owner (§12e). A **declared** part, a stock,
flow, link, auxiliary, parameter, sensor or goal the YAML writes without `inferred:`, with or without a
description, is never proposed for removal (*decided*, 2026-11-18: it was, when it had no description; the
key replaced the description as what tells the two apart), and never because it was quiet, flat or
uncorrelated in the record (SD Lab's dead-flow, still, empty and pass-through rules are not carried over):
see *not exercised*, §12e; what the rules find about declared parts is listed among what was found and not
proposed, with why. A stock a goal
holds, and what a goal or block names, is left alone. Each edit is applied in memory and the model
compiled from it: one that would leave an error, or not answer its finding, is not proposed, and is
listed with why. *Not yet*: a missing stock, flow or delay, or a part replaced, found from the pattern
in the residuals (the residual-pattern structure finder, `structural.from_residuals`).

**The review queue** (`ergostat/numbers/review.py`; the Model page; `ergostat proposals`, `--show ID`):
every proposal waiting, the loops' process and gain proposals (§12d) with them, each read like a pull
request: **what** kind of change, **where** (its parts, and the systems holding them: Show on diagram
chooses them and opens the dynamics view with the block diagram beside it), **why** (the evidence in
words), **how found** (the method, its span of record, its points and how sure it is), its **effect**
(each affected part's record, the model's replay and projection as it is and with the change, simulated
with the edit applied in memory, `numbers/trial.py`), its **benefit** (the fit before and after; what
changes ahead: a projected value, a time to a limit, a goal projected held or off; and the **leverage**
of the flows it touches, SD Lab's §4.9: each flow a tenth faster in turn, projected to the horizon, ranked
by how far it moves the goals), its **conflicts** with others waiting (the same lines, parameter or
equation) and the unified **diff** Accept writes. Accept carries the diff's hash and is refused if the
files would now be written otherwise; Dismiss takes an optional reason, kept with it and in
`model.dismissed`. **Simulate all pending** applies every change together in memory, in order, a
conflicting one left out and said, and shows their combined effect.

## 12c. Using the model: what-if, sensitivity, extreme conditions, loop dominance

The tools system dynamics uses once a model fits (Sterman ch. 21; Vensim's SyntheSim and sensitivity
runs), each where the model already is, and none of them changes it.

**What-if** (the valve's and the auxiliary's panel): each parameter's value in the panel can be typed
over, in its units: a number in the parameter's unit, a time written as a duration with its unit (`20s`,
`2m`; in the panel a bare number is read in seconds, as the value is shown; `ergostat proposals
--propose` and the API refuse one), never 0 or below for a time unless its `range` allows it. Every
chart on the page then draws, in the accent, the replay and the projection with the values tried beside
the model's own (`GET /api/series?…&whatif=name:value,…`), until they are put back; where the values make
an equation fault (a division by 0, taken as 0) or the run blow up, the strip says so, and that the blue
lines are not what the model would do. Beside the values, before anything is stored, their fit on the
reference window: each stock and equation they move, R² and MAPE before and after, and the payoff
(`GET /api/whatif-fit?whatif=…`). Nothing is saved: **Propose these** makes every value tried one
proposal, as the charts drew them (`POST /api/propose?whatif=NAME:V,…`, `ergostat proposals --propose
NAME=V --propose NAME=V`), with its fit before and after and its edit, which changes the model only when
it is accepted. A what-if is refused as a proposal when it faults or blows up where the model as
written does not, or is what is written already; one outside the parameter's range, or that fails an
extreme condition the model as written passes, is proposed with that said in its reason.

**Sensitivity** (`ergostat/numbers/sensitivity.py`; the causes strip): Monte Carlo over what the model
says is uncertain, a parameter's `range` (uniform), else an estimate's standard error (normal about
the value written, on its logarithm where it was searched there, widened to reach the estimate when it
lies further off); parameters estimated together are drawn jointly, from the multivariate normal of
their covariance (the Cholesky factor of their correlation applied to the hypercube's normal scores:
Iman and Conover 1982); every other number held. Two hundred samples, as Vensim's sensitivity runs
default to, a Latin hypercube from a fixed seed (the same model and record draw the same fan), each the
projection run again from the state now with the sample's values (the stocks from their last
readings; a material delay's contents as the replay left them, rescaled to the sample's delay time at
the same outflow, so each sample starts in its own steady state; a smoothed value kept). The projection
is drawn with a shaded fan: where half the runs fall, and, from a hundred runs or more, nine in ten. A
projection shorter than a third of the window is drawn in the last quarter of the chart, on a time axis
of its own past now (+20s, +40s), so a minute ahead of an hour's record can be read. **Spread over the
record** (the strip's button) draws the same over the window: a hundred replays with the sampled values,
the half and nine in ten of them under the replay, as Vensim's sensitivity graphs show the whole run.

**Extreme conditions** (`ergostat/numbers/extremes.py`; `ergostat check`, **extreme-conditions**):
with no record, the equations run for ten of their slowest time constant from each condition, each a
change from where the model usually is (every stock at its `initial`, else 10; every input at its usual
level): every stock empty and nothing coming in; nothing coming in; **each input alone** at 0 and at a
hundred times its largest (so zero capacity, workforce or productivity in a denominator is found, and
one input's failure is not masked by another's); and **each parameter alone** that is estimated, a time
or has a `range`, at its range's ends, else at a hundredth and a hundred times its value. An input is a
flow from outside no equation works out, or an auxiliary from outside; its usual level and largest are
the record's where it is at hand (a what-if proposal), else its declared rate (or 10 an hour) and 1 (*decided*:
`ergostat check` reads no record). A flow between stocks no equation works out is held at 0, or its
declared rate. Said: a stock with only one-way flows drained below empty, a one-way flow whose equation
goes negative, a division by 0 or a logarithm, root or power out of range, a blow-up. A failure the
model shows with everything as usual is said once as that; every other names the input or parameter
that caused it. A failure on a grid is confirmed on one eight times finer before it is said, so a step
too coarse is never blamed on the model. What a block would do is not simulated.

**Loop dominance** (`ergostat/numbers/dominance.py`; a feedback loop's panel, `GET /api/dominance`):
which loops drive the behaviour, and when, by the Loops That Matter method (Schoenberg, Davidsen and
Eberlein 2020), computed on the simulation at its integration step (the replay over the page's window,
every part along a scored loop traced at each step), from the model's own values: what it integrates
and works out, and the inputs it was driven by. Each link's score is the share of its effect's change
its cause's change made: for a flow into or out of a stock, ±|Δflow/Δnet flow|; into a part with an
equation, |Δₓz/Δz| times the sign of Δₓz/Δx, the others held; into a part with one cause and no
equation, all of it, with its sign, or 0 where it did not change; where the run has no value for that
part (a goal's error, a decision), it is **assumed** to follow its cause, and the panel names each link
assumed. A loop's score is the product of its links'. Its relative score is taken **per stock**, as LTM
does: over the sum of the |scores| of the scored loops through that stock, from −1 (a balancing loop
drives everything at the stock) to +1 (a reinforcing one); loops of stocks that do not interact are
never weighed against each other. Each display bucket gets the mean of its steps. The panel draws, at
each stock the loop runs through, its relative score in ink beside the loops competing there in grey,
and says how much of the window it dominated there; no loop is named where two are tied, nor at a stock
where a loop through it cannot be scored (the share of its loops that are scored is said instead). A
loop through a link that cannot be scored (a decision with several inputs, an equation with a delay
inside it, an unsigned link) says why, and is left out of the sums.

## 12d. Control: identification, analysis, monitoring and tuning

The control view's numbers (`ergostat/control/`), for each loop whose controller moves one thing: a
**setting** it steps (a stock moved by a two-way flow its block sets, SPEC §12) or a **valve** (a flow
it sets). That is u; what its goal holds is y. A loop that closes the long way through queues has no
one process, and says so; a valve that drains or fills the goal's stock directly is an integrator
known from the model, and only its dead time is not.

**The record** (`record.py`). For a setting, u is its sensor's readings with each change put at the
moment its block made it (the move recorded, `valve.opened`), not when the sensor next read it, so the
delay identified is the process's (Ljung §13.5). The loop working is read over the recent record at
half y's sensor period (some ten samples a rise time, Ljung §13.7), each step test over its own span
at the same resolution, whatever the reference window's buckets (a day of record makes them a minute
long); how the loop is doing is read over the reference window.

**Identification** (`ident.py`; Ljung, *System Identification*, ch. 4, 7, 14, 16): the process from u to
y as first order with dead time, K e^(−θs)/(τs + 1), or an integrator with dead time, k e^(−θs)/s
(when it leaves less of the record held out), fitted as an output-error model: driven by the
measured u alone from the state the record starts in, never one step ahead. The measured inputs
beside the path (an input from outside the model, a stock that also drives y) are fitted with it,
each its own gain through the same lag. The gains are linear for each (τ, θ), which are searched (a
grid, then Nelder–Mead). From the loop working, the last fifth is held out. Every step test that
finished is used, as one data set of several experiments (Ljung §14.3): the same K, τ and θ, each
test its own start and its own level; one test has its step up fitted and its step back held out,
several have all but the last fitted and the last held out whole. Said of it: the fit on each part,
100(1 − ‖y − ŷ‖/‖y − ȳ‖), beside the most the record's noise allows; what it leaves of the record held
out, against the noise (the larger of what it leaves of the part fitted and y's own jitter); the
standard errors of K, τ and θ (Gauss–Newton, widened for errors that run together); the
**whiteness** of the errors held out (Ljung–Box against χ² at 95%) and their **independence** from u
(the cross-correlation within Bartlett's 95% bound, which a held step widens); and, identified from
the loop working, that it is closed loop, where the estimate leans toward the controller's inverse
(Ljung ch. 13). It is proposed (written into the goal's `process:`) only with u stepped three times or
more in the part fitted (or a step test), forty readings fitted spanning five of τ + θ, a record held
out that moves past its noise (15% of it at least) and of which the model leaves at most 1.5 times the
noise (not a fit percentage: a correct model of a noisy step back follows little of it, Ljung
§16.5-16.6), its errors independent of u (from a step test: in closed loop the feedback correlates
them whatever the model), and K, τ and θ each told apart (a standard error under half of it). A
number at the edge of what was searched (θ at the longest, τ at the longest the record can tell) has
no confidence interval and is said so (Ljung §11.4). The step tests' estimate and the loop working's
are held out on different records, so they are ranked by how precise they are, not by their fits;
otherwise it says why.

**Analysis** (`lti.py`; Åström & Wittenmark, *Computer-Controlled Systems*, ch. 2, 3, 8): with the
process (the model's, else the one identified, said as such) and the controller as its block writes
it, in velocity form and acting at once on the error it has just read: integral action u_k = u_(k−1)
+ gain × e_k, C(z) = gain·z/(z − 1); PI with `integral-time`, u_k = u_(k−1) + Kc(e_k − e_(k−1)) +
Kc(T/τI)e_k. Its own delay, how old the reading it acts on is and how long its run takes before the
move is made (from its last runs), is added to the dead time; never a whole period. A sampled
controller is worked out exactly in discrete time: the process through the zero-order hold (its dead
time split into whole periods and a fraction), L(z) = C(z)P(z) on the unit circle up to the Nyquist
frequency, stable when every root of 1 + L(z) lies inside it (Schur–Cohn); a continuous one by the
Nyquist criterion (no open-loop poles in the right half-plane: stable with the gain margin past 1 and
the phase margin past 0). Said: the process's step response, the closed loop's step response to a
unit step of r (simulated; overshoot, settling into 2%, rise), the Bode plot (|P|, or the loop L = CP
and the closed loop T = L/(1 + L), and their phase), the **stability margins** (gain, phase and
delay margin, and Ms, the peak of the sensitivity: "not robustly" past Ms 2 or under 30° of phase
margin), and the margins **at the worst the process could be**, K ± 2σ, θ + 2σ and τ ± 2σ by the
identification's standard errors (robustly stable, or may be unstable: Skogestad & Postlethwaite ch.
7), said even when the process is not proposable; when K ± 2σ spans 0, that the margins cannot be
bounded. What the block does that is not linear is left out of the numbers and said beside them
(Åström & Hägglund, *Advanced PID Control*, §3.5 and ch. 7): a dead band (`deadband:`, inside it the
loop is open; a dead zone's describing function is at most 1, so a stable loop gets no limit cycle
from it), a setting rounded to its `resolution:` (a quantizer's describing function peaks at 4/π, so
a limit cycle of about one step is predicted with a gain margin under 1.27), and its `limits:` (in
velocity form the clamp does not wind up; at a limit the loop is open).

**Performance monitoring** (`monitor.py`; Desborough and Harris 1992, Thornhill, Huang and Zhang 2003,
Jelali 2013): over the reference window, less each step test and each start (ten controller periods
or three of τ + θ after ergostat starts or the record begins, two minutes at least). For a level held
(==), the **Harris index**, the variance a minimum-variance controller would leave given the dead time
(the process's and the controller's own) over the loop's mean squared error (an autoregression of the
error at the controller's period, never across a gap; it needs θ); a ceiling or a floor (<=, >=) is
not regulated to zero error, so instead how often y was past its bound (and past its tolerance) and
by how much, typically and at worst. Whether the error **oscillates**: from the zero crossings of its
autocorrelation, which noise does not break up as it does the error's own (the intervals' mean over
three times their spread past 1, five crossings or more, the record four periods or more, the
amplitude past the tolerance), with its period and amplitude; the share of time u was at a limit (a
setting at the end of its block's `limits:`, or a valve's openings at its most); and, each time the
loop went off and came back to stay, how long it took to **settle**, and for a level held (==) how
far it **overshot** to the other side. Shown under the scope, and in a word on the Loops page (which
says what it lacks, "needs θ" or "too little record", rather than nothing).

**Tuning** (`tuning.py`; Skogestad's SIMC, 2003): for a controller whose law its block writes and the
process the model holds: PI, Kc = τ/(K(τc + θ)), τI = min(τ, 4(τc + θ)); on an integrator, Kc =
1/(k(τc + θ)), τI = 4(τc + θ); integral action only, K_I = 1/(K(τc + θ + τ)), the lag taken as delay
(safe, and slow when τ is much longer than θ), gain = K_I T; τc = θ (the rules' own "tight" default;
a tenth of τ only when there is no dead time at all, and said), θ the process's dead time with the
controller's own delay and half its period (its sampler and hold). It is offered with its margins
and closed-loop step beside the controller's own, when it moves the gain by more than a fifth and
settles the loop; never on a process not yet in the model. When it is not offered and the gain
margin at the worst the process could be is under 2 (or that worst does not settle), a **detuning**
is: the gain scaled so that worst gain margin is 2 (Åström & Hägglund §4.8), from a process the model
holds or one identified with its numbers told apart.

**Step test** (`steptest.py`): when the record does not identify the process of a loop whose setting
its own controller steps by this loop's error alone, and once the loop is in steady operation (Seborg
et al. §7.2: the record past its start covers ten controller periods, three of τ + θ and ten minutes,
and over the last five periods, three minutes at least, the error has been within its tolerance on
average and not drifting, and u away from its limits; until then the panel says it is waiting, and why), ergostat offers a test.
The size of the step: from the process identified only when the record tells its numbers apart
(enough to move y past twice its tolerance and four times its jitter, no more than the setting is
used to moving); otherwise from the tolerance and the jitter against the most y moved per unit of u
in the record, no less than the setting is used to moving, half again for each test before (Ljung
§13.2: a poor prior, a conservative design). Never under ten of the setting's least steps (its
block's `resolution:`, else the least change the record shows), and signed and sized so the setting
stays within its block's `limits:`, else refused with why. How long each way is held (five of τ + θ
when told apart, else ten minutes; ten controller periods, forty readings, within 2 to 30 minutes);
when it stops early (the error past a bound); and the blocks held still: the loop's own, and those
that move the inputs beside the path (not the world). The proposal is bound to that plan: another
size or hold is another proposal (a dismissal holds for the loop until a test is done or the model
changes). Only once the owner approves it (and while ergostat runs) does `ergostat run` hold those
blocks, record the setting's value, check the step fits its limits (else it is not run), step, wait,
put the setting back to the value it recorded (commanded `"to"`, not back by the step), wait, and
give the loop back, recording each move and what the block said it moved (`steptest.approved`,
`.started`, `.stepped`, `.finished`). A block that moves anything but what it was commanded (to
within the setting's resolution) stops the test, the setting put back at once.

**Proposals.** Each is worked out afresh when the loop is looked at; Accept applies what the page was
shown (the goal's `process:`, a block's `gain:`, made on the file's text so its comments stay, and
refused, with the file put back, if `check` would then find an error), recorded as `model.accepted`;
Approve records a step test's approval; a dismissed one is not offered again until what it depends
on in the model changes. Shown where the loop is: the process block's panel in the blocks view (the
identification, its step response and Bode plot, the process and step-test proposals), the
controller's panel (its law with that process, margins, closed-loop step and Bode, the tuning), the
scope (performance), and a loop's panel on the Loops page (all of it).

## 12e. Improving the model, as a loop

Improving the model is a control loop like the others, built from the same parts: the model's quality is
measured, a goal holds it, a block acts while the goal is off, what it proposes is judged, and what passes changes
the model, which the measurement then sees.

**Not a block type, but a job.** A block's type says who does the work (the ladder: person, AI, narrow AI,
decision, program, rule), not what the work is. Reviewing the model needs no context beyond what every block can
reach (the MCP tools and the command line), no permission beyond proposing, and what is special about it, that a
proposal is checked before anyone sees it, belongs to the `propose` output, which every type shares. So any block
may improve the model: an AI agent reading it as a modeller would, a program applying rules, a person. The judge
is different: it is a function ergostat itself implements (judging means replaying ergostat's model on record
held out), so it is a built-in block, `type: judge`. Improving the improver needs nothing more: its prompt and its
results are a model like any other.

Everything ergostat owns here is named `ergostat.`, so it never collides with a project's names: the item kind
`ergostat.model-change`, the events `ergostat.model-change.*` and `ergostat.model.changed`, and the measures
`ergostat.model.*`. The prefix is ergostat's own (no block may publish an event under it, section 9.3).

### The built-in measures

| Reference | What it is |
|---|---|
| `ergostat.model.fit` | The scaled error of the replay on the reference window, the Fit page's total (section 12b; lower is better). None while there is too little record |
| `ergostat.model.unexplained` | The share of each stock's change over the last hour that its flows do not explain, unexplained over explained plus unexplained (in size), averaged over the stocks that moved (the residuals) |
| `ergostat.model.unidentified-loops` | The goals whose loop closes and whose process the model does not hold (no `process:`, section 8) |
| `ergostat.model.open-findings` | What `ergostat check` finds, errors aside |

A measure's reference is `ergostat.model.NAME`: it reads beside `stock.x`, `flow.x` and `auxiliary.x`, and is
never one of them (a project's names have no dots). It is read by a sensor, `builtin: ergostat.model.fit`
(section 6), on a stock or an auxiliary, by ergostat itself (`ergostat measure ergostat.model.fit`, in a process
of its own); `ergostat measure` and the MCP tool `measures` print them all. *Decided:* a goal holds a measure
through the part its sensor fills, not by naming the measure: a goal's loop closes through the flows of what it
is about, and a measure has none, so the part gives it its history, its chart and the flows the loop closes
through (it rises as the record moves on and the world drifts from the model, and falls as changes are written).
The scaled error over the reference window is a statistic over a window, so that part is a stock (section 7a).

```yaml
stocks:
  model-error:
    unit: "1"
    sensor:
      builtin: ergostat.model.fit
      every: 1m
goals:
  model-fits:
    stock: model-error
    hold: "<= 0.02"
```

### Every change to the model is an item

`ergostat.model-change` is a built-in item kind (section 5a), present in every project and never declared (a
project's item kinds may not take ids starting `ergostat.`). Every change to the model is one, whoever made it: a
block's propose line, ergostat's own finders (a calibration's parameter values, an equation, the structural
changes and simplifications, a loop's process or gain, section 12b and 12d), or the owner's what-if. Its id is
`ergostat.model-change/<short hash>`. **The record is the only store**: every step is an event about the item,
and the item, folded from them, is the change.

| State | Reached by | Source |
|---|---|---|
| made | `ergostat.model-change.made` | the block that proposed it (caused by its run), `ergostat` for its own finders, or `owner` for a what-if |
| checked | `.checked`: compiled, checked, replayed and refitted on a scratch copy | ergostat |
| refused | `.refused` (from made): with why | ergostat |
| testing | `.testing`: the judge replays it on the record after it | ergostat |
| passed / failed | `.passed`, `.failed`: the judge's verdict, with its windows | ergostat |
| inconclusive | `.inconclusive`: the record held out could not tell it from the model as it is; it needs more record, and is not failed | ergostat |
| accepted | `.accepted`: written into the YAML | who decided: the owner, or the judge's policy (the judge, naming the policy) |
| dismissed | `.dismissed`: with the owner's reason | the owner |
| superseded | `.superseded`: made against a version of the model that has since changed, or no longer found by the finder that made it | ergostat |

Its fields are folded from the events as any item's are (section 5a): `kind`, `parts`, `edit`, `reasons` with their
evidence, `confidence`, the measured effect (`fit_before`, `fit_after`, `refit`, `findings`), `verdict`, `made_by` and
the model `version` it was made against. Each is replaced, never appended: every event that carries one states it whole
(`checked` restates the reasons it verified in place of those `made` gave, and a verdict is the judge's whole
finding), so its history keeps each earlier statement, linked to the event that made it. When an accepted edit is written, `ergostat.model.changed` (from ergostat)
records the diff, the model's version before and after, the fit before and after, the reason, who made it and who
accepted it: the model's history.

The review queue (the Fit page, `ergostat proposals`) **is** the open items (checked, testing, passed) made against
the model as it is: a richer view of the same items, and Items → `ergostat.model-change` lists them all, decided
ones included. Item sensors count them like any items, so the loop is plain YAML (below).

### A proposal

Any block may print:

```json
{"propose": {"kind": "structure", "parts": ["stock.ideas"], "title": "ideas drain as they go stale",
             "edit": {"file": "lab.yaml", "replace": "    unit: hypotheses", "with": "..."},
             "reasons": [{"says": "the stock only fills", "evidence": "finding:stock-without-outflow@stock.ideas"},
                         {"says": "an idea not built in a day is dropped", "evidence": "bin/lab.py:150"}],
             "confidence": 0.6}}
```

| Key | Meaning |
|---|---|
| `kind` | `parameter` (values only), `equation`, `structure`, `measurement` (a sensor of a part already there) or `control` (a goal, a block, an agent, the judge's policy). What the edit does decides, whatever it is called: an edit to a goal, a block or an agent is a control change and one to a sensor a measurement change (`version.changed_control`, `changed_sensors`); else one that changes only values is a parameter change. Only the first three are judged by the replay or written by the judge; the others wait for the owner |
| `parts` | The parts it touches, as references (`stock.x`, `flow.y`, `parameter.z`) |
| `edit` | In the review queue's form, `{"files": [{"file", "hunks": [{"line", "old", "new"}]}]}`, or `{"file", "replace", "with"}` (the lines as written now, found once, and what they become), or a list of either. Files are named from the model's folder, and only the model's own files may be edited |
| `reasons` | Each `{"says", "evidence"}` (`evidence` one, or a list). Evidence is what ergostat can check: a finding `check` reports now, by its id (`finding:CODE@PART`, the `id` in `check --json` and the MCP `check`); a statistic of the fit (`fit:total.nmse`, `fit:stock.NAME.r2`, `.mape`, `.um`, `.us`, `.uc`, and an equation's `fit:flow.NAME.r2`); a residual (`residual:stock.NAME`); a line of a document or of the code, in the project or in ergostat (`docs/MODELLING.md:120`, `bin/lab.py:40-52`), or a URL; or a modelling rule (`rule:NAME`: the guidelines of `docs/MODELLING.md` and Sterman's tests, listed in `numbers/improve.py`) |
| `title`, `confidence` | A few words; how sure the block is, 0 to 1 (or `low`, `medium`, `high`) |

ergostat records it as **made** by that block, then checks it the same way whoever made it
(`ergostat/numbers/improve.py`): each reason's evidence is verified and what it found kept beside it (a reason
without evidence is refused); the edit is applied to a scratch copy (in memory), compiled and checked (the
findings it answers, and any it makes), replayed on the reference window, and the parameters to estimate that it
adds or uses differently are refitted (each part alone, the last fifth held out), said beside it. It is
**refused**, with why, when no reason has evidence, the edit cannot be made or does not compile, the replay it
leaves is not valid, it clearly worsens the fit, no reason's evidence supports it, or the same change is already an
item for this version of the model; refused changes are the review queue's "found, and not proposed" (and
`ergostat improve`).

**The gate** (`ergostat/numbers/gate.py`), for every change whoever made it, ergostat's own calibration, equations
and structural finds included: it clearly worsens the fit when the scaled error rises by more than a tenth (and not
by a trifle), refitted or not, either over the **whole model** (like for like: over the stocks both fits judge) or
**near what it touches**: the stocks of its neighbourhood, which is what it names or moves (a parameter through the
equations that use it, a flow through its stocks) and every part one link from them. That holds even when the part
it was fitted to improves: a value fitted on one stock alone may fit that stock at once and the whole replay many
times worse. The reason says both numbers ("the whole model's scaled error 0.788 → 18.5, 23.4× worse; near what it
touches (stock.paired) ...; though fitted each part alone, its weighted error on stock.paired falls by 100%"), and
the benefit shown in the review queue says worse as worse, never as a gain.

**Evidence that supports, not only exists.** Each reason's evidence is checked to exist, then to bear on the change:
a finding about a part it touches or one next to it (or, about no part, one it answers); a fit statistic of such a
part, or the total when the change does not raise it; a residual of such a stock, and significant; a rule that
`check` applies to such a part now. A rule `check` does not test, a line of a document or of the code, and a URL
are kept beside the reason as cited, and never alone carry it: a proposal needs one reason whose evidence supports it.

**Turned away, remembered** (`ergostat/numbers/memory.py`). A change refused at the gate, failed by the judge, or
inconclusive is not proposed again for the same target (its kind, what it is to, and how it was found: the
calibration or the rule, or a block's proposal) on the same version of the model until the record has grown enough
for an estimate to say something new: a quarter of the record it was estimated on, at least ten minutes and the
judge's hold-out, doubling with each turn-away, at most a day. Found again meanwhile, it makes no new item: its
item counts it (`repeats`, `held_until`, and `held_back`: "proposed again 3 times, held back until 16:20"), shown on
the item, in `ergostat proposals` ("turned away on this version"), `ergostat improve` and the Model page. A change
refused for its form (no evidence, an edit that cannot be made) is never held back: it is said so at once. Otherwise it is **checked**, and waits in the review queue attributed to its
block (its name and rung, its reasons with their evidence, how sure it said it was). `ergostat improve --try FILE`
and the MCP tool `try_change` check a proposal the same way and record nothing; `ergostat improve --edit-value
NAME=V` prints the edit that sets a parameter's value, in the form `edit` takes.

### Inferred and declared: `inferred:`

Invariant 11 asks that everything in the model say whether it was declared or inferred. Whenever a model change adds
a part, ergostat writes on it, in the edit the review queue shows and Accept writes, the key **`inferred:`** with the
change's item: on a stock, a flow, an auxiliary, a parameter, and a link written out (`{cause: +stock.x, inferred:
...}`).

```yaml
flows:
  pile-leaving:
    from: pile
    driven-by: +stock.pile
    equation: stock.pile / time-in-pile
    inferred: ergostat.model-change/3f9c01aa      # the change that added it
parameters:
  time-in-pile:
    value: 40m
    estimate: true          # from Little's law; refitted as the record grows
    inferred: ergostat.model-change/3f9c01aa
```

| | |
|---|---|
| The value | *Decided* (2026-11-18): the change's item id, `ergostat.model-change/<id>`, one key that says both that it was inferred and where from (not `inferred: true` with a `from:` beside it). `true` is accepted where the change is not known (a part copied from another model); `false`, or no key, is declared. Anything else is an error (**bad-inferred**) |
| Who writes it | ergostat's own finders (a stock between two rates, an outflow and its time to stay, a converting auxiliary and its link, an equation's parameters), and the check of a block's proposal, on each stock, flow, auxiliary and parameter its edit adds (written under the line the part's name is on; a part written in the short form, `k: 0.45`, is left as written). The id is the change's own: its edit is made with a placeholder, the change's id worked out from it, and the placeholder made that id, so the same change found again is the same change. A link a block adds to a declared part is not yet marked |
| Accepted or edited | It **stays**: a part the owner accepts, or edits afterwards (its equation, its value, its description), is still inferred, and still names the change that added it, until the owner takes the key away. Taking it away is how the owner declares the part as their own |
| What reads it | The structural rules (§12b): only an inferred part (or link) that explains nothing or duplicates another may be proposed for removal, and that always waits for the owner; a declared part never is. The gate refuses a block's removal of a declared part the record has not exercised. The side panel of the Dynamics and Blocks views says, quietly, "added by ergostat, from model change X" (X a link to its item), and a parameter's "from" column the same |
| What it is not | Not part of the model's structure or version: adding or taking away the key changes neither, so it never supersedes a change waiting. The description is the owner's and ergostat's words, never read for provenance (before 2026-11-18 the phrase `proposed by ergostat` in a description marked an inferred part, and the equation proposer's parameters, marked only by a YAML comment, counted as declared) |

### Not exercised by the record: quiet is not absent

A flow that has not moved yet is not evidence that it does not exist: points are lost rarely (an outage), a
queue of the owner's messages is empty until the owner writes, and a short record may never exercise them. In
Sterman's terms (ch. 21), the record has not exercised that structure, so its rate cannot be identified from the
data: a statement about identifiability, not about the boundary, and a modeller keeps declared structure with its
stated reason (`ergostat/numbers/exercised.py`).

| | |
|---|---|
| Not exercised | A stock, flow or auxiliary with 20 readings or more over ten minutes of record or more (the reference window, within the span the record reaches) that **never moved** (a flow under a thousandth of the typical flow on average and a hundredth at its peak, or nothing counted; a level at 0) or **held one value** (a range under a thousandth of its mean: no variation to identify a parameter from). A parameter is not exercised when every part it acts through that the record reads is not |
| The finding | `not-exercised`, about the part, a built-in finding from the record (`ergostat findings`, the MCP tool `findings`, the Check page, the part's side panel): the span of record it covers, the readings, why, and, as a suggestion only, that a step test or a planned disturbance would exercise it. It clears the moment the part moves |
| The estimator | An estimate of a parameter that is not exercised is not proposed: it is **held, inconclusive** (`estimate.judged`), said beside the parameter, until the record exercises it. A block's proposal that sets only such parameters is recorded as `inconclusive`, not checked |
| The judge | It does not vouch for what the record held out has not exercised: a value or an equation whose parts it acts through did not move there is never passed on that record; it stays under test and is then `inconclusive` ("needs record in which it moves") |
| Removal | Never for a declared part the record has not exercised: a block's proposal that removes one is refused at the gate. Only structure ergostat inferred (`inferred:`) that the record shows to be redundant (§12b), and any change that removes structure (`removes`, or parts it takes away) is never written by the judge's policy: it waits for the owner |

### The judge

`type: judge`, a built-in block on the program rung: ergostat runs it on its own clock (`every`, 30 s by default),
not on every reading, and records each pass as a run. At most one a model.

```yaml
blocks:
  judge:
    type: judge
    every: 30s
    hold-out: 10m          # the record after a change that it is judged on
    windows: [1, 2, 4]     # that record whole, in halves and in quarters
    threshold: 2%          # passed when the scaled error falls by this much in every window
    accept:                # who writes a passed change: owner (the default), or auto
      parameter: auto      # a value passed is written at once
      structure: owner     # waits in the review queue, its verdict beside it
    out:                   # optional: what it moved, on its ports
      testing: flow.tests-started
      passed: flow.changes-passed
      failed: flow.changes-failed
      accepted: flow.changes-accepted
```

| Key | Type | Default | Meaning |
|---|---|---|---|
| `hold-out` | duration | `10m` | How much record after a change it is judged on |
| `windows` | list of whole numbers | `[1, 2, 4]` | How that record is split into windows: 1 whole, 2 halves, 4 quarters (each at least a minute) |
| `warm-up` | duration | `6h` | The longest before each window its replay starts, so the window is scored with its stocks and delays as the record left them, not started cold with every delay in equilibrium (section 12f): three time constants of what the change touches, and never more than the record held before the window |
| `threshold` | share (`2%`, `0.02`) | `2%` | The least fall in scaled error that counts as better, and the most rise that counts as no worse |
| `accept` | `owner` or `auto`, or a map of kind (`parameter`, `equation`, `structure`) to either | `owner` for every kind | Who writes a change it passed. *Decided:* nothing automatic by default; with no judge, nothing is judged |
| `out` | map of `testing`, `passed`, `failed`, `accepted`, `inconclusive` to flows | none | What it moved on each pass, recorded as each flow's valve opening |
| `in`, `every` | | | What it reads (signed, as a machine block's), for the diagram; how often it passes |

Each pass (`ergostat/numbers/judge.py`; `ergostat judge` makes one by hand) supersedes every open change made
against a version of the model since changed, starts **testing** each checked change it can replay (a value, an
equation, the structure; a loop's process or gain is not replayed, and waits for the owner), and replays each beside
the model as it is on the record that came **after** it was made, which neither its maker nor any estimate it rests
on has seen, in every window. It scores **what the change touches**: the stocks of its neighbourhood (as the gate
finds them), the goals' own stocks among them, each stock's mean squared error over its record's mean square,
whatever its time constant (the fit's total leaves out a stock slower than its window, so a change that slowed one
would look better; section 12f); the rest of the model and each goal's stock must be no worse. A mean over every
stock let one far stock's error dilute any change to 0%. It waits for **record long enough for the change to show**:
the hold-out, and at least twice the dominant time constant of what it touches (in the model as it is and with the
change), at most a day; a window shorter than that time constant is not judged. Each window is replayed warm, from
three of those time constants before it, never longer than `warm-up` nor than the record held before the window (on
a young record a six-hour warm-up integrated the stocks from where the record did not reach, and scored a regime of
its own: errors of 12 to 700 where the goal read 0.03 to 0.14). Two scaled errors closer than 0.005 are within the record's noise
and count neither way. It **passes** one when the scaled error falls by the `threshold` or more in every window
judged that can tell (the rest within the noise) and is no worse elsewhere; when it is no worse in any window and answers
findings without making any; or when it is no worse and **simpler** (fewer parts, parameters and terms). It
**fails** one that is worse by the threshold in any window, near it, elsewhere or on a goal's stock, or better only
in some. One that no window can tell from the model as it is stays under test for more record, up to three times
what it needs, and is then **inconclusive** ("needs more record"), not failed; as is one too few windows can judge,
and one it would pass whose parts the record held out has not exercised (above: it does not vouch for a quiet
part's rate). Each verdict keeps its windows (each one's span, and the scaled error
before and after) as its evidence, shown with the item in the review queue. Then, where `accept` says `auto` for a
passed change's kind, it writes the oldest, one a pass, so each is measured alone (never one that removes
structure: that waits for the owner, whatever the policy): Accept's way (section 12b), the
smallest edit, refused and put back if `check` would then find an error, recorded as `.accepted` from the judge
with its policy named, and `ergostat.model.changed`. Accepting writes the YAML at once; ergostat never commits it:
the owner does.

### The loop, in the model

Plain YAML, like any loop (`examples/image-squeeze/model.yaml`, `examples/the-job/job/modelling.yaml`): the model's
error a stock (`builtin: ergostat.model.fit`) and a goal on it; the changes counted by state, `items:
ergostat.model-change` (pending: checked; testing; passed; accepted), with flows entering each state (made,
judged, accepted); the improver, an `ai` block (or a stand-in program) that names the goal and proposes; and the
judge. It closes the long way: the improver fills the pending changes, the judge moves them to passed and
accepted, and what is accepted lowers the error. It is drawn, explained and checked like every loop.

## 12f. Verifying the improver

How we know the loop that improves the model (section 12e) works. The benchmark drives that loop's own modules
(`propose` lines through `improve.submit`, the built-in judge, Accept, the `ergostat.model-change` items) through a
small handle, `ergostat/bench/adapter.py`, which runs each call at a moment of a simulated record (the benchmark's
clock, `bench/clock.py`, so what is recorded then is stamped then) and gives the judge the policy the benchmark
asks for, in memory, so the models it damages stay as written.

**1. The pipeline** (`tests/test_bench.py`). A proposal with no reason whose evidence ergostat can check is
refused; so is one whose edit cannot be made or does not compile. Accept writes exactly the diff shown, and refuses
when the file has changed since (the diff's hash). A change made against a model since changed, even only in its
numbers, is superseded and never written, by the judge or by hand. Under the default policy (`accept: owner`) the
judge passes a change and nothing is written.

**2. The judge** (`ergostat/bench/judging.py`, `ergostat bench judge`). On synthetic worlds whose truth is known
(`bench/cases/judge-*.yaml`), each written with one number off by a factor drawn per seed, one change is proposed
and the judge run on the record after it until it gives a verdict. The change is known **better**, **worse**,
**neutral** or **slowed** (a drain made so slow its stock's replay outlasts the record). The false-accept rate
(worse, neutral or slowed changes written) must be about 0; the false-reject rate (better ones not written) is
reported. *Found:* the fit's total leaves out a stock slower than its window, so a slowed change can look better
in every window; and each window is replayed cold (its delays in equilibrium), so a correct delay often looks
worse in a short one. *Fixed* in the judge (section 12e): it compares **like for like** (each stock's scaled error over the
stocks both models replay, whatever its time constant) and scores each window on a **warm** replay (started
`warm-up`, six hours by default, before it). Measured over 120 trials (10 seeds): before, 5 of 90 worse,
neutral or slowed changes written and 17 of 30 better ones not; now, 0 and 0. *Then* (2026-11-17, from the owner's
image-squeeze run, where 89 re-estimates failed as "0 of 7 windows, from -0% to 0%"): the judge scores the stocks
near what the change touches, waits for windows as long as their dominant time constant, bounds the warm-up by
that and by the record, and says inconclusive where it cannot tell; still 0 false accepts and 0 false rejects over
the same 120 trials, the neutral changes now inconclusive rather than failed.

**3. Recovery** (`ergostat/bench/recovery.py`, `ergostat bench improve [--improver standin|ai --model M]
[--cases LIST] [--rounds N]`). The truth cases (`bench/cases/*.yaml` and `cases.json`): SD Lab's
ladder cases converted into ergostat YAML (`scripts/bench_ladder.py`: affine rates written with a parameter for
every number, a DELAY3 between stocks as what leaves at once and arrives through the delay, a step three minutes)
and the examples' worlds written as ergostat models with equations. The record is the truth simulated by the
replay from its inputs' schedules and its stocks' starts, read every minute with Gaussian noise (2% of each
series' RMS, seeded). The defect catalogue (`bench/defects.py`) plants one or two of: `flow-removed`,
`sign-flipped`, `parameter-x3`, `delay-missing`, `stock-merged`, `spurious-link`, each with its **locus** (the
measured stocks it shows at). Eight hours of record, then rounds of two hours: the improver proposes on the record
so far, the judge judges at the round's end with `accept: auto`, hold-out two hours; four hours more are kept for
the forecast. Scores: **recall** (a visible defect is fixed when its locus error, the model's inflow and outflow at
each locus stock worked out on the truth's record against the truth's, as a share of the truth's RMS, is 0.15 or
less; a defect already that close as planted is not visible and not counted), **precision** (proposals that lower
the mean locus error over every measured stock by 0.02 or more and raise none by as much), **damage** (changes
written that raise it by 0.02 or more), **fit** (the scaled error over the record, damaged, final and the truth's),
**forecast** (the same on the four later hours) and **cost** (rounds, seconds, tokens, dollars). Written as
`scorecard.md` and `scorecard.json`, with the proposals counted by kind (proposed, checked, passed, failed, real
fixes). The improvers (`bench/improvers.py`): the **stand-in**, a program that searches a fixed menu of changes,
deterministic, run on two cases in the test suite; the **calibrator**, what the examples' stand-ins do (the
calibration's estimates proposed for the judge, parameters only); the **AI** (`claude -p`), run only on demand. Measured
(15 cases, 16 visible defects, the stand-in): with the judge as it is now, recall 12/16, 23 changes written, 15 of
them real fixes and 2 damaging, the final fit a median 1.01 times the truth's; before the judge's fix, recall 9/16,
14 written (9 real, 3 damaging), 1.54 times.

*Then* (2026-11-17, from the same run, where the simplify rules proposed removing 26 flows and stocks that had
not moved in a young record, `flat-points-lost` among them): a declared part the record has not exercised is a
finding (`not-exercised`), never a removal; the estimator holds, and the judge does not pass, what acts only
through it; removal is left to redundant structure with no declared reason, and waits for the owner. On a
three-hour copy of that record, ergostat's own finders went from 14 removals proposed (13 quiet flows, 1 empty
stock) to none, with 33 parts said not exercised. `bench judge` and `bench improve` are unchanged by it (their
truth cases exercise every part they plant a defect in).

**4. The prediction check** (`ergostat/numbers/verify.py`, `ergostat verify [--propose]`, run by a block). Each
change written is checked once, after three hold-outs of record: the model now beside the model with that change
undone (its hunks reversed where they sit now), replayed on the record since it was written and its halves.
`ergostat.model-change.verified` when it forecasts no worse; `ergostat.model-change.regressed`, with the edit that
undoes it, when without it the scaled error is lower by the threshold over the whole record since and in at least
half the windows; with `--propose` the undoing is proposed, by `verify`, for the judge and the owner. *Decided:*
the check never undoes a change itself. A change whose lines a later one rewrote is said so and not judged.
`verified` and `regressed` are states of the `ergostat.model-change` item kind, after `accepted` (its status stays
accepted).

**5. The loop's own measures** (`ergostat/numbers/meta.py`, `ergostat bench meta`), over the last week:

| Measure | What it is |
|---|---|
| `ergostat.model.accepted-per-day` | Changes written to the model, a day |
| `ergostat.model.regressed` | Changes written that the prediction check flagged for revert |
| `ergostat.model.verified-share` | Of the changes checked, the share whose forecasts held (none until one is) |
| `ergostat.model.fit-gained` | What the changes written lowered the scaled error by, together (each one's fit before minus after, as Accept measured it) |
| `ergostat.model.cost-per-accepted` | The `cost_usd` the blocks that make changes recorded, over the changes written |

They are built-in measures like the model's own of section 12e (`MODEL_MEASURES`): read by a sensor
(`builtin: ergostat.model.accepted-per-day`), or printed by `ergostat measure`.

## 12g. Claims and trust

A block's report is a sensor too, and only as good as its honesty: a run that says "tests pass" while a pipe hid
their failing exit code degrades every loop that reads it. So what a block says it did is a **claim**, and
ergostat checks it, by itself, after the run: against the record (what ran, what moved, what state an item is in)
and the world (the tests run again, the repository read). A contradicted claim is a finding against the block that
made it, and how far each block's claims hold is a measure a goal can read: its **trust**.

### The claim line

Any block, whatever its type, may print:

```json
{"claim": {"says": "tests pass", "about": "hypothesis/3"}}
{"claim": {"says": "submitted hypothesis/3", "about": "hypothesis/3", "check": {"state": "testing"}}}
{"claim": {"says": "changed squeeze.py", "about": {"file": "run/product/squeeze.py"}}}
{"claim": {"says": "the queue is down to 3", "about": "stock.queue", "check": {"level": "<= 3"}}}
```

| Key | Meaning |
|---|---|
| `says` | What was done, in words (required, at most 500 characters) |
| `about` | What it is about: an item (`hypothesis/3`, or `{"item": ...}`), a part (`stock.x`, `{"part": ...}`), a file in the project (`{"file": ...}`), a commit (`{"commit": SHA, "repo": DIR}`), a folder (`{"dir": ...}`), a run (`{"run": EVENT}`) or a test suite (`{"suite": ...}`). Text is read as an item id a kind matches, a part, a commit's hash or an existing file, in that order; `file:`, `commit:` and the other keys may lead it |
| `check` | Optional: which check judges it, by name (`tests`, `changed`, `state`, `exit`, `level`, or one `claims:` declares), or a map naming it and what it needs (`{"state": "done"}`, `{"level": ">= 3"}`, `{"exit": 0}`). A command given here (`run`) is never run: a claim is checked by the model's checks, not its own |
| `session`, `model` | Who made it, where the block cannot say: the session item the claim came from, the AI model behind it. A model the block or its agent declares is used before the one the claim names |
| `evidence` | The block's own evidence: kept beside the claim, never trusted in place of a check |

A line with nothing in `says`, or an `about` ergostat cannot read, is refused like any bad line (`agent.refused`).

### The checks

After a run ends (`agent.ran` or `agent.failed` recorded), each claim it made is checked in turn. Without `check`,
the claim's words choose: a claim that tests pass (or fail) is `tests`; one about an item that names a state of
its kind is `state`; "changed", "edited", "wrote", "fixed" ... about a file, a part or a commit is `changed`;
"succeeded" or "exited 0" is `exit`; one whose words a declared check's `says` matches is that check.

| Check | Verified when | Evidence |
|---|---|---|
| `tests` | The project's test command (`claims: {tests: {run}}`), run by ergostat, exits 0 (or, for a claim that they fail, does not). It runs where the claim says: in a folder it names, or on a copy of a commit (the one it names, or the one its item names in a `commit` or `branch` field), exported from the repository `in:` names into a scratch folder, so nothing is checked out; else in `in:`. With no test command declared, the latest test run in the record decides (`tests.ran` with its `exit`, `tests.passed`, `tests.failed`, about the claim's item when there is one) | The command, where it ran (the commit), its exit code, its time, the last 1,500 characters it printed |
| `changed` | A file: git shows it changed (uncommitted, or in a commit since the run began, or in the commit the claim names); outside git, it was written since the run began. A part: a change written to the model (`ergostat.model.changed`) since the run began touches it. A commit alone: it exists | What git said, the commits |
| `state` | The item, folded, is in the state claimed, or moved into it since the run began | Its state now, its last moves |
| `exit` | The run (or the run `about` names) recorded that exit code (0 by default) | The run's event, its exit code and note |
| `level` | The part's latest reading is within the level claimed | The reading, its time, its series |
| one `claims:` declares | Its command, run as `tests`' is, exits 0 | As `tests` |

A claim no check knows, a check that cannot run (no test command, no reading, a folder outside the project, a
command that does not finish within its timeout) or one that breaks is **unchecked**, with why: recorded, and never
trusted. Checking takes as long as its commands: the block is not run again until its claims are checked.

**The pattern this exists for**, tested (`tests/test_claims.py`): a block runs `pytest | tail -n 3`, which exits
0 whatever pytest did, and claims the tests pass. Its run's exit code is 0, so `exit` is fooled; `tests` runs the
declared command itself, which exits 1, and the claim is contradicted with pytest's own output as the evidence.

### Checks the project declares

```yaml
claims:
  tests:                                # what checks "tests pass": the project's test command
    run: '"$ERGOSTAT_ROOT/bin/py" test_squeeze.py'
    in: run/product                     # where it runs, and the repository a claim's commit comes from
    timeout: 3m
  lint:                                 # a kind of claim of the project's own
    says: "lint (is )?clean"            # the claims it judges, by what they say (or check: lint)
    run: ruff check .
```

| Key | Type | Default | Meaning |
|---|---|---|---|
| `run` | command | required | Run by ergostat with the shell; exit 0: what was claimed holds. Its environment carries `ERGOSTAT_ROOT` (the model's folder), `ERGOSTAT_STATE_DIR` and `ERGOSTAT_CLAIM` (the claim's id) |
| `in` | folder | `.` | Where it runs, from the model's folder (never outside it), and the git repository a claim's commit is exported from |
| `says` | pattern | none | A regular expression over what a claim says (case aside) that makes it this kind |
| `timeout` | duration | `10m` | Past it, the claim is unchecked |
| `description` | | | |

`tests` is the one name a built-in check reads; the other built-in names (`changed`, `state`, `exit`, `level`)
may not be declared.

### Every claim is an item

`ergostat.claim` is a built-in item kind (section 5a). Its id is `ergostat.claim/<short hash>`; every step is an
event about it, and the item, folded from them, is the claim:

| State | Reached by | Source |
|---|---|---|
| made | `ergostat.claim.made`: the claim as said, caused by the run | the block |
| verified | `.verified`: with its evidence | ergostat |
| contradicted | `.contradicted`: with its evidence | ergostat |
| unchecked | `.unchecked`: with why no check could judge it | ergostat |

Its fields: `says`, `about`, `check` (as given), `kind` (the check that judges it), who made it (`block`, `rung`,
`model`, `session`, `run`), `made`, and from the verdict `verdict`, `why`, `evidence` and `seconds`; each is
replaced, so its history keeps every verdict it was given (`ergostat claims --check` checks again what was left
made, when ergostat stopped between a run and its checks). Items → `ergostat.claim` lists them, with a **Trust**
table under them; a claim's page shows its verdict and evidence first. `ergostat claims` prints the trust table and
the latest contradicted claims, `ergostat claims ID` one claim with its evidence, and the MCP tool `trust` the same.
Item sensors count claims like any items (`items: ergostat.claim, state: contradicted`).

### Trust, as a measure

| Reference | What it is, over the last week |
|---|---|
| `ergostat.trust.contradicted` | Of the claims checked (verified or contradicted), the share contradicted; 0 while none is |
| `ergostat.trust.contradictions` | Claims contradicted |
| `ergostat.trust.verified` | Claims verified |
| `ergostat.trust.unchecked` | Claims no check could judge |
| `ergostat.trust.claims` | Claims made |

Each is about every block, or, with `@WHO`, one: `@developer` (a block), `@rung:ai` (every block on that rung: its
agent's kind, else its type's), `@model:haiku` (every claim made by that model). *Decided:* a parameterised
reference (`ergostat.trust.contradicted@developer`) rather than a measure per block, so a block added later needs
no new name. They are built-in measures like the model's own (section 12e): read by a sensor, `builtin:
ergostat.trust.contradicted@developer`, on a stock or an auxiliary, so a goal holds it through that part
(`examples/image-squeeze/lab.yaml`: `developer-honest`, `<= 0.1`); `ergostat measure trust.contradicted@developer`
prints one, and `ergostat measure` all of them for every block.

**A contradicted claim is a finding** (`contradicted-claim`, about `block.NAME`: how many in the window, the
latest's words and why; `ergostat findings`, the status, the MCP `findings`), and needs attention: the page's and
`ergostat`'s list says it against the block's agent, as bad.

## 12h. Messages: absorbing interruptions

A long session folds the owner's mid-work messages into the work: "that review can wait", "check the flag ramp
first", "on review 2041: I missed the migration". Work that ergostat runs as many short runs and sessions must do
the same: a message the work never hears is work done wrong, and redone. So the owner's words are a **message**: an
item ergostat routes to the work in flight it concerns and delivers to it, and how messages reach the work is
measured. (Harness parity, function 4: `docs/proposals/harness-parity-plan.md` §2.4.)

### Every message is an item

`ergostat.message` is a built-in item kind (section 5a). Its id is `ergostat.message/<short hash>`; every step is an
event about it, and the item, folded from them, is the message:

| State | Reached by | Source |
|---|---|---|
| received | `ergostat.message.received`: the text verbatim, who sent it (`by`), when (`sent`), what it is about when they said (`about`), how it came (`via`: cli, page, mcp, a sensor) | the sender |
| routed | `.routed`: what it matched (`matched`: `explicit`, `mention`, `classifier:NAME`), why, and the work it was routed to (`routed_to`) | ergostat, or the classifier block |
| delivered | `.delivered`: each delivery (`deliveries`, appended): how (`live`, `resume`, `context`, `follow-up`, `reopen`), and to which run, session, block or item | ergostat, or the session helper |
| unrouted | `.unrouted`: why nothing took it | ergostat |
| answered | `.answered`: what the work said back (`answers`, appended) | the block, or its session |

Two more events change no state: `.queued` (held for a session's next step) and `.missed` (the work it was routed to
finished before it was delivered). Each step restates `outcome`, in words. Items → `ergostat.message` lists them, with
a box to send one; a message's page shows where it went and how, and routes an unrouted one by hand.

### Sending one

- `ergostat message "that review can wait" [--about ITEM|PART ...] [--as WHO] [--reopen]`; `ergostat messages` lists
  them and what became of each, `ergostat messages ID` shows one, `ergostat messages ID --about X` routes it by hand.
- The page: Items → `ergostat.message` has a Message box; every item's page has "Send a note about this" (its
  `about` is the item) and lists the messages about it. (`POST /api/message`, JSON `{"text", "about"}`.)
- MCP: `message` (`text`, `about`, `by`), so an AI front-end can relay the owner's words verbatim; `messages` lists them.
- A sensor may relay them, one line each, like an observation: `{"message": {"text": "...", "by": "me", "about": ...}}`
  (the-job's note watcher).

### Routing

At once, in order, the first that finds anything:

1. **explicit**: what `about` names: an item (`review/2041`), or a part (`block.developer`, `stock.inbox`, `goal.x`,
   or a part's bare name, blocks first);
2. **mention**: item ids in the words (`hypothesis/3`), part references (`stock.queue`), and a machine block's name
   as a word ("the developer");
3. **classifier**: the block `messages: {classifier: NAME}` names, run once for the message (below); else ergostat's
   free **stand-in**, which scores the items by the words they share with the message (their kind's name, its plural
   or its words: +2; the number in their id: +3; each word of their shown fields and title: +1, at most 3) and takes
   the best scoring 2 or more, open items first, then those worked on now, then the newest, at most three. A finished
   item is a candidate only when its number is said ("on review 2041").

What it matched becomes its **targets**:

- an **open item**: the item, and each **block run going now that works on it**: a run (`agent.started` with no
  `agent.ran` or `agent.failed` after it, within its timeout) works on an item when an event about the item was caused
  by the run (`causedby`, which `ergostat event --add` sets from `ERGOSTAT_RUN`) or its command named the item; with
  the run's session, when the run is a session (below);
- a **part**: each machine block acting on it (a block; a goal's actuators; the block setting a flow; the blocks
  setting a stock's flows), with its run when one is going;
- a **finished item**: by the policy, below.

A message that matched nothing, or only parts nothing acts on, is **unrouted**: it needs attention (the status and the
page's list say it, with how to route it) until the owner routes it by hand. An item is finished in the states
`messages: {done:}` gives for its kind, else in its kind's last state and any state after the first that no item has
left while some item reached a later one (a review waiting for its reviewer is not finished; a ramp approved is).

**The classifier** is a machine block, typically an `ai` block on a cheap model (`model: haiku`). It is run like any
block (recorded as a run, `trigger: message`), its input carrying the `message`, the `candidates` (the open items, those
worked on now first, each with its kind, state, shown fields and `worked_on_by`) and the `blocks`; it answers with a
**route line**, `{"route": {"message": ID, "to": ["review/2041", "block.developer"], "why": "..."}}` (`to` empty: it
concerns none of them). A classifier with one flow output moves it by one for each message it routes. A run that fails,
or says nothing about the message, leaves it to the stand-in.

### Delivery

- **A running Claude Code session.** `ergostat session ROLE --model M [-- CLAUDE-ARGS]` (`$ERGOSTAT_CMD session ...`
  in a block's `run:`; the prompt on standard input) runs `claude -p` as the block's run with a session id it chose,
  records the session as an item (`session/ROLE-RUN`: `session.started`, caused by the run, with `session_id`, `model`,
  `live` and its `transcript`, copied as it grows), and gives it the messages routed to its run, its session, its
  block or an item it works on:
  - **live** (the default): the session runs with `--input-format stream-json`, its input kept open, and each message
    is written into it as a user message. Claude Code takes a message written while it works at its next step (after
    the tool call under way: "The user sent a new message while you were working"), within the same turn; one written
    after the turn's result starts a turn of its own. The input is closed three seconds after a result with nothing
    more to give. `delivered`, how `live`.
  - **resume**: with `--no-live` the prompt is given whole and a message cannot reach the session mid-run: it is
    `queued`. After the turn (and after a live session's last), ergostat resumes the session, `claude -p --resume ID`,
    the messages its input: its next turn. `delivered`, how `resume`; the reply answers them.

  It prints `session.ran` (or `.failed`) about the session item, with its cost, turns, time and the messages it was
  given (`owner_messages`; `messages` is what a session kind folds its transcript into), then the JSON lines of
  every turn's result, its claims marked with the session and model. `$ERGOSTAT_CLAUDE` names the program it runs
  (`echo`: ergostat's stand-in session, `ergostat/session_echo.py`, which folds a message that arrives mid-turn into
  the turn and echoes it; `$ERGOSTAT_ECHO_RUN` runs a stand-in program as its work).
  *Decided:* live delivery is the default, because Claude Code takes messages on an open stream-json input mid-turn
  (tested with Claude Code 2.1: a message sent during a ten-second tool call was answered in the same turn); resuming
  remains for a session that cannot keep its input open.
- **A block that is no session, or not running now.** Its next run's input carries, under `messages`, the messages
  routed to it, or to open items of the kinds it works on (those counted by the sensors of the flows it sets, of the
  stocks they move, and of what its goals hold), and to no run going now: each `{"id", "text", "by", "sent", "about",
  "items", "matched"}`, `delivered` how `context` with the run. An `ai` block's prompt footer says to take them in.
- **Answering.** Any block may print `{"answer": {"message": ID, "says": "..."}}`: the message is `answered`, by it.
- **Finished work**, by `messages: {finished:}`: `follow-up` (the default) makes a new item linked to it
  (`ergostat.item.follow-up`, its fields `follows`, `message`, `note`, and the shown fields of the item it follows),
  of the kind `follow-up:` names or the finished item's own (`review/2041.1`), arriving in its kind's first state so
  the work that does that kind takes it up; `reopen` moves the item back, `ergostat.item.reopened` (to the state
  `reopen-to:` gives for its kind, else its first; its field `reopened` says from where and by which message);
  `attention` leaves it unrouted, for the owner. `ergostat message --reopen` reopens whatever the policy.
- **Missed.** ergostat's clock sweeps the messages every five seconds: one left received is routed, and one routed
  to items that have all finished since, with no work having taken it, is handled by the policy and **missed**
  (`.missed`): the work finished without it, and is redone. A message about an item that had finished before it was
  sent is not missed.

```yaml
messages:
  classifier: router            # optional: a block that routes what no id or name in a message does
  finished: reopen              # follow-up (default), reopen, attention
  follow-up: note               # the kind a follow-up is made as (default: the finished item's own)
  reopen-to: {hypothesis: proposed}
  done: {ramp: [approved, rejected, broke, proved-fine]}
```

| Key | Type | Default | Meaning |
|---|---|---|---|
| `classifier` | a machine block | the stand-in | Routes a message nothing in it names (route lines) |
| `finished` | `follow-up`, `reopen`, `attention` | `follow-up` | What a message about finished work does |
| `follow-up` | an item kind | the finished item's | The kind a follow-up is made as |
| `reopen-to` | map of kind → state | its first state | Where reopening moves an item |
| `done` | map of kind → states | inferred (above) | The states an item of that kind is finished in |

`messages:` is written once, in any of the model's files.

### Messages, as measures

| Reference | What it is |
|---|---|
| `ergostat.messages.unrouted` | Messages that reached no work, now |
| `ergostat.messages.awaiting` | Messages routed and not yet delivered, now |
| `ergostat.messages.received`, `.routed`, `.delivered`, `.answered` | Those over the last week |
| `ergostat.messages.missed` | Messages whose work finished before they reached it, over the last week (work redone) |
| `ergostat.messages.reached` | Of the messages received over the last week, the share delivered (0 while none is) |

Built-in measures like the model's own (section 12e): read by a sensor (`builtin: ergostat.messages.unrouted`) on a
stock or an auxiliary, so a goal can hold it; `ergostat measure messages.unrouted` prints one. Item sensors count the
messages by state like any items (`items: ergostat.message, state: routed`; `entering: delivered`).
`examples/image-squeeze/messages.yaml` and `examples/the-job/job/messages.yaml` model them: unrouted and awaiting as
stocks, routed, delivered and missed as flows, and a goal holding the unrouted at 0.

## 12i. The intent judge: done as meant

A long session decides when work is done: not when its tests pass, but when it does what the owner meant. Work that
ergostat runs as many short runs must be held to the same: a change can pass every test and still do what the owner
decided against ("WebP output" when the owner chose JPEG and PNG only), and the tests cannot see it. So a piece of
work that says it is done is **judged against what the owner meant** before it counts as done: its done-when, the
confirmed decisions and corrections in its scope (section 5a), and the owner's messages about it (section 12h). The
verdict, with its evidence, is an item, and how often finished work turns out not done as meant is a measure.
(Harness parity, function 2: `docs/proposals/harness-parity-plan.md` §2.2.)

### The judge block

```yaml
blocks:
  intent-judge:
    type: judge
    judge: intent                 # (judge: model, the default, is section 12e's)
    every: 10s
    kinds:
      hypothesis:
        at: testing               # the state it says it is done in: its tests passed
        accepted: kept            # where it counts as done (default: its kind's last state)
        scope: [formats, squeeze] # the decisions it is held to: those whose scope shares a word, or that name none
        work: [code]              # the corrections it is held to: for this kind of work (default: its scope)
        repo: run/product         # the git repository its commit or branch is read from (default: claims' tests.in)
        base: main
        reopen-to: proposed
    model: haiku                  # optional: a judge on a model; without it, the free stand-in
    max-cost: 0.05                # dollars a verdict, at most
    held: attention               # or reopen: what a verdict that the work is not done as meant does
    within: 1d                    # work that entered its state longer ago is not judged late
    out: {held: flow.holding}     # its ports: judged, met, held
```

| Key | Type | Default | Meaning |
|---|---|---|---|
| `judge` | `model`, `intent` | `model` | What the judge judges: changes to the model (12e), or finished work |
| `kinds` | map of kind → `{at, ...}` or a state | required | The model's own item kinds it judges, and when (`kinds: {ticket: review}`) |
| `model` | a model name | none: the stand-in | An AI judge on that model (a cheap one: `haiku`) |
| `max-cost` | dollars | `0.05` | Per verdict, passed to the model as its budget |
| `held` | `attention`, `reopen` | `attention` | `reopen` moves held work back (`ergostat.item.reopened`, to `reopen-to`), with the verdict as its reason |
| `within` | duration | `1d` | How late it judges |

One intent judge at most. It is ergostat's own, like section 12e's judge: a program (rung `program`), or a narrow AI
(`narrow-ai`) when it names a model. Each pass (on its clock, or `ergostat intent judge [ITEM]`), every item of a kind
it holds that entered its `at` state within `within` and has no verdict for that moment is judged, oldest first,
twenty at most; a pass is recorded as a run, and a held verdict is said in the log.

### What a piece of work is held to (the brief)

- **its done-when**: the field `done_when` (or `done-when`), verbatim from the message that started it; a follow-up
  made from the owner's message (12h) carries the message's words as its `done_when`;
- **its change**: when it names a `commit` or a `branch`, the diff against `base` in `repo`, with the files it touches
  as they were;
- **the confirmed decisions in its scope**, each with the owner's words, reasons and rejected alternatives;
- **the confirmed corrections for its kind of work** (or `general`, or naming the item);
- **the owner's messages about it**: sent about it, routed to it, or naming it (a block's words are not the owner's).

Only what is confirmed holds: a proposed decision is not the owner's yet. Work held to nothing is **unjudged**, and
counts on its tests.

### The verdict

| Verdict | Means |
|---|---|
| `met` | It does what its done-when asks, and nothing in it goes against what it is held to |
| `unmet` | It does not do what its done-when or the owner's messages ask |
| `contradicted` | It does what a decision, a correction or a message rules out |
| `unjudged` | Nothing to hold it to, or a verdict its evidence did not support |

Each unmet or contradicted point carries **evidence**: the id of what it goes against (`ergostat.decision/...`, or
`done-when`) and a quote from the work (a line of its diff, with file and line, or a field's value).

- **The stand-in** (free, no tokens) reads what the owner ruled out (a decision's rejected alternatives; the words
  after `never`, `no`, `not`, `don't`, `without`, `instead of` ... in a decision, a correction, the owner's words or a
  message) and looks for it in what the work brings in: the words of the lines its diff adds that are in none of the
  files as they were nor in the lines it removes (identifiers split at `_` and case). A term ruled out that the work
  brings in is a contradiction, with the line. It cannot read what a done-when means (it says so); work with a
  done-when and nothing to show is unmet. It is a matcher of words: it misses a contradiction said in other words
  ("strip" for "stripping metadata"), and flags a word brought in that does not do what was ruled out (a format named
  in a comparison). Measured on image-squeeze: below.
- **On a model**, the brief is given as Markdown (`ergostat/intent/prompt.md`, replaced by a project's
  `prompts/intent-judge.md`) to `$ERGOSTAT_AI` (`claude -p`, no tools, `--max-budget-usd`), asked for one JSON line.
  Its answer is checked, not trusted: each unmet or contradicted point must name something it was given and quote the
  work (whitespace aside); points that do not are dropped, and a verdict left with none is `unjudged` (unsupported).
  Its cost and tokens are recorded with the verdict.

**Every verdict is an item.** `ergostat.verdict` is a built-in item kind (section 5a), its id `ergostat.verdict/<short
hash>` of the work and the event that moved it into its judged state, so one moment is judged once:

| State | Reached by | Source |
|---|---|---|
| asked | `ergostat.verdict.asked`: the work, its kind, the moment, what it is held to (ids), how (`mode`: standin, ai; `model`; `rung`) | the judge |
| met, unmet, contradicted, unjudged | `.met`, ...: `why`, `evidence`, `cost_usd`, tokens, seconds | the judge |
| overruled | `.overruled`: the owner says it was wrong, with a reason | the owner |
| missed | `.missed`: it passed work (met, unjudged) the owner later found not done as meant | ergostat |

The verdict is also put on the work: `ergostat.item.judged` sets its field `intent` (`verdict`, `why`, `id`, `by`,
`against`; `overruled` when it was), beside what its tests said, so its page shows it and its own programs read it
(image-squeeze's rollback drops a candidate held back, and its rollout keeps none before it has a verdict).

**The owner's acts.** `ergostat intent overrule ID --reason R` (a false alarm, or a pass that was not): the verdict is
overruled and stops holding the work; nothing else moves. `ergostat intent reopen ITEM --reason R`: work accepted that
was not done as meant goes back (`ergostat.item.reopened`, the reason in its field `reopened`), and counts against the
judge that passed it.

`ergostat intent` prints the counts and rates by kind and the latest verdicts; `ergostat intent ID` one verdict with its
evidence; `ergostat intent judge [ITEM] [--model haiku] [--max-cost USD] [--again]` a pass now. Items → `ergostat.verdict`
lists them; a verdict's page shows its evidence, and the work's page its `intent`.

### What became of the work, as measures

Work **reaches** its judged state, and is **accepted** when it then enters an `accepted` state. The owner **finds it
not done as meant** when, after accepting it and before it is judged again, it is reopened (not by the judge), a
follow-up is made of it from the owner's message, or a correction the owner proposed or confirmed names it.

| Reference | What it is, over the last week |
|---|---|
| `ergostat.intent.false-done` | Of the work accepted, the share the owner later found not done as meant (0 while none is) |
| `ergostat.intent.false-done-tests` | The same had the tests alone decided: of the work that reached its judged state, the share found not done as meant, by the judge (not overruled) or by the owner after accepting it |
| `ergostat.intent.accepted`, `.reopened` | Work accepted; of it, found not done as meant |
| `ergostat.intent.judged`, `.met`, `.unmet`, `.contradicted`, `.unjudged`, `.overruled` | Verdicts given |
| `ergostat.intent.held` | Verdicts unmet or contradicted, not overruled: work held back |
| `ergostat.intent.cost` | Dollars the judge spent |

Each with `@KIND` for one kind of item (`ergostat.intent.false-done@hypothesis`). Read by a sensor (`builtin:`) on a
stock or an auxiliary, so a goal holds it; `ergostat measure intent.false-done` prints one. *Decided:* the rate goals
read is what got past the judge (accepted, then found by the owner), and its tests-alone twin beside it, so the judge's
worth is the gap between them, and its cost is the false alarms the owner overrules.

`examples/image-squeeze/intent.yaml` models it: the owner's confirmed decisions and the work held back as stocks,
false-done and its tests-alone twin as auxiliaries, a goal holding false-done at 0.1 or below.

## 12j. Contexts: projection recipes

A session's starting context is a fold of the record, not a copy of a conversation. `contexts:` names recipes
for it: each has a `version`, an optional `description`, an optional `outcome` (the item states that count as the
work succeeding or failing), and a list of `parts`, rendered in order into one Markdown document, each within its
`budget` (characters, or tokens with a `t` suffix; a default per kind).

```yaml
contexts:
  worker:
    version: 3
    outcome: {success: [done], failure: [dropped]}
    parts:
      - decisions: {scope: checkout, budget: 1500t}     # confirmed decisions, most relevant to the scope first (§5a)
      - corrections: {kind: ui}                         # what the owner corrected before, for this kind of work
      - owner-words: {topic: checkout}                  # the owner's messages, verbatim, most relevant first (§12h)
      - item-history                                    # the item's fields and history, its sessions' key turns
      - state: {findings: true}                         # what moved on main, what is running, open findings
      - model                                           # the item's parts in the model and their goals
```

The other parts are `session` (`of`, `last`, `match`: a session's turns, as a fork does) and `docs` (`files`).
Each mistake (an unknown part or key, a bad budget) is said with its file and line by `ergostat check`.

- `ergostat context RECIPE [--item X] [--budget N]` renders one; `ergostat context --list` lists them; the MCP
  `context` tool takes a recipe. `decisions` and `corrections` are the built-in one-part recipes.
- An `ai` block takes `context: RECIPE`. ergostat renders it for the block's item and run and starts the session
  through the session helper (`ergostat/session.py`) with it as the appended system prompt. The recipe's name,
  version and the hash of what was rendered are recorded on the session as one use (`ergostat.context`: started →
  succeeded / failed), and the work's outcome is folded onto it when its item reaches an `outcome` state.
- Built-in measures compare recipes over the last week: `ergostat.context.RECIPE.outcome` (the share of uses whose
  work succeeded), `.cost`, `.uses`, `.succeeded`, `.failed`.
- A machine block's `review:` sets how deeply its work is reviewed by a measure, typically its trust (§12g): rules
  read in order, the first whose `when` holds decides (`by: reviewer` commands that block to review the run, with a
  `depth`; `by: none`, no review), and each decision is recorded (`review.required` / `review.skipped`) with the
  measure's value.

```yaml
blocks:
  developer:
    type: ai
    context: worker
    review:
      - when: "contradicted > 0.3"        # ergostat.trust.contradicted@developer
        by: reviewer
        depth: deep
      - by: none
```

Measured offline with the parity benchmark (harness parity plan §4): starting from decisions + corrections + the
owner's words on the topic scored 0.625, against 0.03 with nothing, 0.33 with the docs and 0.49 with decisions
alone; it is the recommended worker recipe. Adding `state` did not help yet (the state of the work is the weakest
kind of question): what `state` carries is the next thing to improve.

## 13. Examples

### First loop: an inbox kept short (ergostat closes the loop)

```yaml
name: first-loop

stocks:
  inbox:
    unit: files
    sensor:
      run: mkdir -p inbox; ls inbox | wc -l
      every: 5s

flows:
  arrivals:
    to: inbox
  processed:
    from: inbox

goals:
  inbox-short:
    stock: inbox
    hold: "<= 20"
    tolerance: 5

blocks:
  worker:
    type: program
    goal: inbox-short
    until: "<= 15"
    run: ls inbox | head -5 > .batch; (cd inbox && xargs rm -f < ../.batch); wc -l < .batch
    out: flow.processed

  drop:
    type: program
    run: mkdir -p inbox; for i in 1 2 3; do mktemp inbox/job.XXXXXX > /dev/null; done; echo 3
    every: 5s
    out: flow.arrivals
```

The threshold lives once, in the goal. The worker only works: ergostat runs it while the goal is
off (through the implied `keep-inbox-short`), once per reading, until the inbox is back to 15.
Written out, the implied block is an `onoff` with `goal: inbox-short`, `until: "<= 15"` and
`out: block.worker`; the long form is still valid, and is needed when the controller is something
other than on/off. No machine is shared, so there is
no `agents:` section.

### Production: observed autoscaling, a cron job ergostat now controls, a missing loop

```yaml
name: checkout

sources:
  prom:
    type: prometheus
    url: http://prometheus:9090

stocks:
  queue:
    unit: jobs
    sensor:
      query:
        source: prom
        promql: 'sum(queue_depth{app="checkout"})'
      every: 30s
  logs:
    unit: MB
    sensor:
      run: du -sm /var/log/app | cut -f1
      every: 1m
  disk:
    unit: "%"
    limit: 100
    sensor:
      query:
        source: prom
        promql: 'node_filesystem_used_pct{mount="/data"}'
      every: 1m

flows:
  requests:
    to: queue
  served:
    from: queue
  logging:
    to: logs
  rotated:
    from: logs
  writes:
    to: disk

goals:
  queue-short:
    stock: queue
    hold: "<= 500"
    critical: true
  logs-small:
    stock: logs
    hold: "<= 500"
  disk-headroom:                 # nothing serves it: missing feedback
    stock: disk
    hold: "<= 80"
    critical: true

blocks:
  autoscaling:
    type: external
    agent: hpa
    in: goal.queue-short
    out: flow.served

  rotate-when-big:
    type: onoff
    goal: logs-small
    until: "<= 300"
    out: block.rotate

  rotate:
    type: program
    run: logrotate -f /etc/logrotate.d/app
    in: block.rotate-when-big
    out: flow.rotated

agents:
  hpa:
    external: true
```

### Triage: an AI controller serving three goals

```yaml
name: triage

stocks:
  tickets:
    unit: tickets
    sensor:
      run: ./count-tickets.sh
      every: 1m
  alerts:
    unit: alerts
    sensor:
      run: ./count-alerts.sh
      every: 30s
  spend:
    unit: USD
    sensor:
      run: ./spend-this-hour.sh
      every: 1m

flows:
  filed:
    to: tickets
  fired:
    to: alerts
  resolved:
    from: tickets
  acked:
    from: alerts
  used:
    to: spend

goals:
  few-tickets:
    stock: tickets
    hold: "<= 10"
  alerts-acked:
    stock: alerts
    hold: "<= 2"
    critical: true
  within-budget:
    stock: spend
    hold: "<= 20"
    critical: true

blocks:
  triage:
    type: ai
    agent: claude
    prompt: prompts/triage.md
    in: [goal.few-tickets.error, goal.alerts-acked.error, goal.within-budget.error]
    out:
      tickets: block.ticket-worker
      alerts: block.alert-worker
    every: 2m

  ticket-worker:
    type: ai
    agent: claude
    prompt: prompts/resolve.md
    in: block.triage.tickets
    out: flow.resolved
    max: 5

  alert-worker:
    type: program
    run: ./ack-duplicates.sh
    in: block.triage.alerts
    out: flow.acked

agents:
  claude:
    kind: ai
    model: claude-opus-5-5
    at-once: 2                   # triage and the ticket worker share it
```

### Cascade: an outer goal sets an inner one

```yaml
blocks:
  backlog-to-workers:            # the outer loop: how many workers the backlog needs
    type: expr
    in:
      backlog: stock.backlog
    expr: min(50, max(5, backlog / 20))
    out: goal.enough-workers     # sets the inner goal's setpoint
```

## 14. From the TOML format

| TOML | YAML |
|---|---|
| `[[stock]]` | `stocks:` |
| `[[sensor]]` with `agent` | a sensor inside its stock (`run:` is the agent's command for that sensor) |
| `[[flow]]` | `flows:` |
| `[[disturbance]]` | a flow no block sets (its `rate` as before); its `agent` becomes a block (often `external`) whose `out` is the flow |
| `[[controller]]` | a goal (its `holds` and `setpoint`) and a block serving it; `open_loop` becomes a machine block on a schedule with no controller |
| `[[valve]]` with `agent` | a machine block whose `out` is the flow |
| `[[agent]]` | its `run`, `every`, `parse` move onto the blocks it ran; an `agents:` entry only when it is shared, external, a person, or has limits |
| `[[system]]` | `systems:` |

`ergostat convert` writes an existing `ergostat.toml` as `ergostat.yaml` (`--stdout` to look first).
A controller that held a stock through a valve becomes a goal, and the valve's block names it
(`goal:`), so the loop that the TOML only watched is closed. What needs a person (a program that
measured and acted in one run) is listed at the top of the file.

## 15. Open questions

1. *Decided:* `goal:` stays on `onoff` and `proportional`, and a machine block may name its goal
   too (section 9.3).
2. Should a sensor be allowed to run on a remote host (`host:`), or only through sources?
3. Arbitration when two controllers command one block. *For now:* the largest command wins, and
   `check` reports the competing commands; a `select` in front says otherwise (`pick: min`,
   `first`). A key on the block (`arbitrate: latest`, `priority`) is still open.
4. *Decided:* a person reports with `ergostat block NAME --done N` (or the MCP tool
   `report_done`); ergostat records `person.asked` when the command rises, and one not answered
   within an hour is a finding (`not-answering`). Whether the hour should be a key on the block is
   open.
5. The built-in set: is it the right first twelve?
