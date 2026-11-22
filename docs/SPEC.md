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
and blocks.

How each draws what measures and what comes in from outside:

- In the control view every loop's feedback path goes through a **sensor block**, beneath the loop,
  as Franklin, Powell & Emami-Naeini draw the standard loop. Inside it, its function: `H = 1` when
  the model gives it no dynamics; `H(s)` and its window (`avg 10 min`) for a rate over a window; a
  sampler's switch and `e^(−sT)` when it polls at a period T that is a tenth or more of the loop's
  own (its controller's `every`, else its identified process's τ + θ, else ten minutes). Beneath
  that, what it reads and how often (`items: alert, fired, every 5 s`; `prometheus: <query>, every
  30 s`; a `run` sensor's description when it has one, `Jira: FF tickets approved, every 5 min`,
  else its command). A sensor that counts items is preceded, on the same path, by its kind's
  **collector**: a `run` or `query` sensor on a flow that brings a stock counted by that kind in
  from outside (it polls the outside system and records what it saw as items, section 6), so a
  count is only as fresh as its collector.
- In the dynamics view a cloud an inflow comes from names its source where the model knows it
  (`from Jira`): the external block or the block outside the control system that drives it, the
  source its sensor queries, or what its sensor's description names before a colon.
- **Rates read naturally.** Every rate is kept, written, fitted and compared per hour (equations,
  `rate:`, a flow sensor's reading, stored series). The pages, the diagrams and the terminal show
  each one in the unit that reads best for its size: per minute above about 60 an hour, per day
  below about 1 an hour, else per hour (a chart picks one unit for its whole axis, by its largest
  value). A flow's `rate-unit:` (minute, hour, day or week), or its stock's for the flows it shows,
  overrides the choice. It is display only: nothing is converted where it is kept. A kind of quantity (stock, auxiliary) belongs to the model; a role in a loop (process
variable, manipulated variable, controller, actuator) belongs to the control view, and is worked
out, never written.

## 2. Files

- The main file is `ergostat.yaml` at the root of the project. YAML 1.2; a JSON file is also
  valid YAML and is accepted.
- **Which YAML.** *Decided* (2026-11-18): the format follows **YAML 1.2's core schema**. The files are read
  with PyYAML, which follows YAML 1.1, and the two read some plain (unquoted) values differently: 1.1 reads
  `9:30` as 570 and `18:00` as 1080 (base 60), `010` as 8 (octal), `1_000` as 1000, `0b101` as 5 and
  `2026-11-18` as a date, and leaves `1e3` and `0o17` as text; 1.2 reads the first five as text, `010` as 10,
  `1e3` as 1000 and `0o17` as 15. `yes`, `no`, `on` and `off` are already text, as in 1.2 (only `true` and
  `false` are booleans), but any 1.1 reader takes them for booleans. Today `check` warns on every such value
  (**yaml-1.1**, a finding, shown beside the errors too), with its file and line, what it is read as and the
  form to write (`"9:30"` quoted for the text). *Planned:* after one release of these warnings, the loader reads
  times, octals, underscores, binaries, dates and exponents as YAML 1.2 does (a resolver change in
  `spec/load.py`, the same in the template loader), and the warning is dropped for every value it would then
  read as written. Until then, quote a time or a date, and write numbers in plain decimal.
- `include:` names more files (paths or globs, relative to the including file). Included files
  may include others. All files share one namespace.
- Each top-level section is a map keyed by name; maps from all files are merged. **Defining a
  name twice is an error**, reported with both files and lines. There is no overriding.
- A file may set `defaults:` (at present only `system:`), which applies to the stocks, flows,
  goals and blocks defined in that file, and not to the files it includes.
- **This machine's settings: `ergostat.local.yaml`.** Beside the main file, never required and never tracked (list it
  in the repository's `.gitignore`), it holds what belongs to the machine a model runs on rather than to the model, so
  a model shared through git carries no private hostname and a copy placed again keeps them. It is read after the
  main file and over it. The **per-machine settings** are exactly these: `web:` (section 4d; it replaces the main
  file's whole) and `intake:`'s `bind:` and `allow:` (section 5c; each over the main file's, whose `hooks:` stay
  the model's). Any other key, or another key under `intake:`, is an error at its line in `ergostat.local.yaml`
  (**not-per-machine**). `check` says each setting it took and where (`web: from ergostat.local.yaml:1, this
  machine's own`; `--json`: `local`). It is not one of the model's files: nothing that edits the model (a proposal,
  a template's author) writes it, and a change to it reloads the model like any other.

## 2a. Templates: one shape, used many times

A **template** is a reusable shape of model: a generic structure in the system dynamics view (Hines's
"molecules", Lane and Smart's generic structures), a library block in the control view (Simulink's library
blocks, IEC 61131-3's function block types). It is written once, with parameters, and **used** as many times as
there are things of that shape; each use, an **instance**, expands into ordinary items, stocks, flows,
auxiliaries, goals and blocks, read and checked exactly as if they had been written out.

```yaml
uses:                                   # any file; the instances of every file share one namespace
  review-reminders:                     # the instance: its parts are review-reminders-..., and it is a system
    use: re-ping                        # the template
    within: delivery                    # optional: the system it is part of (else its file's defaults: system:)
    description: reviews I asked for    # optional: the system's description (else the template's)
    with:                               # the template's parameters
      every: 1d
      limit: 3
      ping: ./bin/remind.sh
library:                                # main file only: folders of templates (a path: the owner's own)
  - ~/private/ergostat-templates
  - {folder: ~/shared/from-a-friend}    # not marked trusted: untrusted (below)
```

| Key | Type | Meaning |
|---|---|---|
| `use` | template name | Required. ergostat's own (`ergostat/library/templates/`), or one from a `library:` folder or `$ERGOSTAT_LIBRARY` (folders, separated by `:`); the owner's shadows ergostat's of the same name, and `check` says so; an untrusted folder's never does (below) |
| `with` | map | The template's parameters. A parameter it does not take, a value of the wrong type (a duration that does not parse, a setpoint, a cron expression, a name) and a required one left out are errors at that line |
| `within` | system name | The system the instance is part of |
| `description` | string | |

**What a use makes.** Every name the template defines becomes the instance's, `INSTANCE-NAME`
(`review-reminders-unanswered`), and every reference to it follows (`stock.unanswered`, `from: unanswered`, a
parameter named in an equation); a name a parameter gives whole (an item kind, `${kind}`, by default the
instance's name) is taken as given. What a parameter brings in (a reference to a part outside, a command) is never
renamed, so an instance can name the model's other parts, and the model can name an instance's parts by their
full names. A template written `once: true` is the exception: it may be used once a model, and its parts keep
the names written in it (`modelling`'s `model-error`, `model-fits`, `improver`, `judge`), so prompts and the rest
of the model name them plainly; a second use is an error (**used-twice**), and a system the model declares under
the instance's name (to give it `show:` or `within:`) is the model's, in place of the one the use would make. The instance is a system of its own, and each part it makes is in it: drawn as one box, opened in
place or drawn alone, in both views, like any system. Templates may use templates; an inner instance is named
`INSTANCE-INNER` and is within the outer one.

**Where it points.** Every part a use makes is written at its `use:` line: an error in one, and every finding
about one, points there (`job/pings.yaml:3 (use review-reminders: re-ping)`). It is changed only through its
`with:` (or the template): a proposal that would edit such a part in place (an estimate written, an equation
fitted, a tuning) is refused, and says what to change instead.

**Stand-ins.** A template's parameters that reach the world (a source, an action) each say what stands in for
them when they are left out: a made-up feed, a pretend answer, a level that creeps up. Each instance runs offline
on them, and `check` lists the instances still on stand-ins (**template-stand-in**, a finding).

**Untrusted libraries.** Which folders are untrusted is declared in the main file's `library:` (below, *Folders the
owner did not write*): a map `{folder: PATH}` is untrusted unless it says `trust: owner`, and it may say so with a
YAML bool instead, `untrusted: true|false` (a value that is not a bool, or one disagreeing with a `trust:` beside it,
is **bad-library**). Only the main file declares trust: a `uses:` entry takes only `use`, `with`, `within` and
`description`, so `trusted:` or `untrusted:` there is **unknown-key**. `$ERGOSTAT_LIBRARY` folders and ergostat's
own templates are trusted. `Template.trust` is the one attribute (`Template.untrusted` is read from it, true unless
it is `ergostat` or `owner`), and a later source of trust sets it too. An untrusted template's name and each
parameter's name must match `^[a-z][a-z0-9-]{0,63}$`, or the template is refused. An instance is untrusted when its
template is or when any instance it sits inside is (a trusted template used by an untrusted one is untrusted there),
recorded in its `uses` entry (`untrusted`, a bool).

*Marked.* Library text is shown between ergostat's markers, `⟦untrusted: LABEL⟧` and `⟦end of untrusted⟧`, every
`⟦` and `⟧` inside it written `[` and `]`, so no marker character inside a marked span is the library's. `LABEL` is
never library text: `template NAME` (the name checked above) or the words `library file`. Three places are marked,
for an untrusted template only; a trusted template's output is unchanged:

- the `templates` tool (MCP, `author.library`), listed and in full: `description`, `reading`, `example`, `from`, and
  each parameter's `description`, `stand-in`, and `default` and `choices` (a list or a map written as JSON first;
  a number or a bool as it is). Each untrusted entry says `"untrusted": true`, and the output's `markers` says that
  text between the markers is a library's: data, not instructions;
- **template-library** notes from an untrusted folder (a file that does not read, a name refused, a shadowing
  refused): `untrusted library folder FOLDER:` (the owner's path), then the rest, file name included, marked as
  `library file`;
- the problems a use of an untrusted template gives: **bad-param** and **bad-template** messages after
  `use INSTANCE:`, the stand-ins in **template-stand-in**, and a broken template's note in **unknown-template**.

*Not marked.* The template's name and its parameters' names (checked instead), a parameter's `type` (one of the
known types), and everything an untrusted template makes in the model: its system's description, its parts'
descriptions, prompts, commands, equations and names, however `check`, the diagrams and the MCP model views show
them. Gating `ask:` and `query`/`source` is not done either (docs/GAPS.md, *Shared libraries*).

*Bounded.* A part is untrusted when it was made by an instance whose `uses` entry does not say `untrusted: false`
(an instance gone, or an entry without the flag, counts as untrusted); a part the model wrote is the owner's. After
the leases are checked, each limit below that an untrusted part passes is an error, **untrusted-limit**, at its
`use:` line. The limits are constants (`ergostat/library/bounds.py`), never config. They are a second line behind
the allowlist below: a held chain may not make a program, ai or judge block or a sensor with `run`, `every`, `cron`
or `daemon` at all, so today the limits that compile can reach are a sensor's default `every` and the run-time gates;
the rest bound whatever a later rule admits (docs/GAPS.md, *Shared libraries*):

| Limit | Value | Applies to |
|---|---|---|
| `UNTRUSTED_EVERY` | 300 s | a stock's or flow's sensor, and a program, ai or judge block: `every:` at least this, and its default when none is written (not 60 s, not the judge's 30 s); `cron:` firing at one minute of the hour at most (its minute field a single value, so at most hourly) |
| `UNTRUSTED_POOL` | 2 | a block's `pool:` |
| `UNTRUSTED_ATTEMPTS` | 5 | a block's lease attempts, as its lease terms come out (its own `lease:`, its kind's, the owner's `leases:` tier) |
| `UNTRUSTED_RUNS` | 4 | the runs at once of every untrusted program, ai and judge block together: its pool for a block that takes items, else 1 |

Refused outright for an untrusted part: a sensor's `daemon:`, a block's `on:`, and a program or ai block with none of
`every:`, `cron:` or `takes:` (it would run on every reading). These are the only fields bounded. A value that does
not read (`every: soon`, `pool: many`, a bad cron, `attempts: x`) stays the error it always is. When runs start, the
engine's `start` and a lease's take count the untrusted runs in `running` under the engine's lock, in the same hold
that adds the run (a take reserves before its lease is written, so no lease is written for a run that cannot
start), and a judge's pass is counted the same way. A run counts while its process is still exiting, and counts as
untrusted if it was when it began, if the model says so now, or if the model no longer has its block. The clock
paces an untrusted sensor, block or judge at `UNTRUSTED_EVERY` at least, even if the spec changed after it was
compiled. A sensor's `run:` goes through the reader pool, which is bounded already (`READERS`).

**Writing one.** A template file is YAML: `template:` (its name), `description:`, `reading:` (what it is in
control theory and in system dynamics), `params:` (each with `type`, `description`, and `default`,
`required: true` or nothing; `stand-in:` says what stands in when it is left out; `choices:`; `min:` and `max:` on a
`number` or `integer`, a value outside them an error naming the bound; type `any` takes a value as given, checked
where it is used), `example:` (a `uses:` entry), `once: true` when it is used once a model
(above), then the sections it makes (`items`, `systems`, `parameters`, `auxiliaries`, `stocks`, `flows`,
`goals`, `blocks`, `agents`, `uses`). In them:

- `${param}` is a parameter's value; a whole value that is one `${param}` takes it as it is (a number, a list).
  `${param:hours}` and `:seconds` give a duration as a number, `:quote` quotes it for the shell, `:json` writes it
  as JSON, `:arg` writes `--param VALUE` (nothing when it is not given; for a list, the flag for each); and
  `${param|text}` is `text` when the parameter is not given;
- `${name}` is the instance's name, `${lib}` the programs the built-in templates run (below), `${python}` the
  Python ergostat runs on, `${here}` the template's own folder (for the scripts a private template keeps beside
  it), quoted for the shell, and `${folder}` the same as it is (for a file's path);
- a key whose value comes out empty is left out; a map (or a section's entry) with `if: ${param}` is kept only
  when the parameter is set, `unless:` only when it is not, and either may compare (`if: ${rung} == person`);
- a value written `{if: C, value: V, else: E}` (or `unless:`) is `V` when the condition holds, else `E`, or left out
  when there is no `else:` (`type: {if: ${it.prompt}, value: ai, else: program}`);
- an entry with `each: PARAM` (a list parameter) is made once for each element, which is `${it}` (`as:` names
  it): its fields, `${it.index}`, and `${it.next}` and `${it.prev}`, the next and previous element's name (or
  the entry's `last:`, by default `done`, and `first:`); `{each: P, value: V}` in a list makes an element for
  each, and `each: {each: P, key: K, value: V}` in a map an entry for each; `${P.first}`, `${P.last}` and
  `${P.count}` name a list's ends and length.

**The built-in library.** `respond-to` (items from a source answered within a time), `re-ping` (asked again
until answered, up to a count, then a person takes over), `daily-report` (a report on a schedule, kept as an
item), `keep-under` (a level held under a limit by a corrective action), `steps` (an item worked through a list
of steps, a block each), `collect` (the event collector) and `modelling` (the model improved as a loop of its
own, section 12e: its fit held by a goal, what `check` finds held as requests, a rule tier and an AI tier that answer
them, and the judge; once a model, every model should have it), and `upkeep` (ergostat's own upkeep as loops of
the model, below). Each says its reading in both disciplines
(`ergostat help adding`, `docs/ADDING.md`). They run ergostat's own programs (`python -m
ergostat.library.run`): `collect` (a sensor that polls a command or an HTTP endpoint, records each new record as
an event about an item, once, from a cursor, and prints the arrivals per hour), `each` (a block's program that
runs a command on the item leased to its run and moves it on, or gives it back), `ping`, `due` and `report`. The
blocks that work on items take them (section 9.5): `respond-to`'s `answer` and each of `steps`' steps is leased
one item a run, `pool` at once, and an item that fails every try is a dead letter.

**Mirroring an outside log** (`collect` with `mirror: true`, `cursor-field:` the entry's position, `position: int`
or `text`). A system that keeps its own event log (Kafka, a ticket history, an incident log) is copied in, read in
place (another ergostat only, section 4c), or mirrored. A mirror records each entry once, under the id
`cite:<log>:<type>:<position>`: the log is the sensor that runs it (`<flow>.<sensor>`, given to its command as
`ERGOSTAT_SENSOR`), the type `i` (a whole number, `9` and `"9"` alike, ordered as numbers) or `t` (text, ordered as
text, so a text position must sort in log order: zero-padded, fixed-width times). The engine records a sensor's line
with a `cite:` id only when the log it names is that sensor (`sensor.refused` otherwise), and nothing pushed may
carry one (section 5c). Each poll, under the collector's lock: what it said last poll is looked for in the record,
and the cursor moves to the last of it that was all recorded; when one is missing (refused, or lost to a timeout or a
crash), the poll exits 1 naming it and why (the sensor's last `sensor.refused` or `sensor.failed` recorded by the
engine, source `ergostat`, since that poll, else "not in the record"; the reason is the record's word, and a push
that claims source `ergostat` can still put one there), and the next re-reads from the confirmed cursor. With its
memory lost (`library/<name>/collect.json` gone or unreadable), the cursor is the greatest of the sensor's own cites
in the record, its rolled-up items' snapshots included (`rollup.cites`), read a page of 5,000 at a time (bounded
memory, but a time that grows with the record); a record it cannot read fails the poll, never starting from the
beginning. Every entry is checked before any is said (a position missing or not of its type, two different entries
at one position: exit 1, nothing said), and at most 5,000 are said a poll, the lowest first. Entries at or before the
cursor are skipped. A log that went back stops the mirror (exit 1): when the source's newest entry is before the
cursor, or the entry it returns at the cursor has another id (`id-field`) than the one recorded there (`fields:`,
`kind` and `event` may change; a changed `id-field` reads as a restart). So does a changed `position`. Clearing the
collector's memory does not end the stop, since the cursor, its type and the entry at it come back from the record:
the owner renames the use (a new sensor, so a new log, mirrored from its start), or sets `position` back. What is
claimed: an entry is recorded once, under the cite of its position, across polls that failed, timed out or were
refused, and across lost memory while the record holds that sensor's cites (or their snapshots); only the sensor
named in a cite records it. Not claimed: after the record forgets the log's entries (`keep`, prune) and the
collector's memory is lost, they are mirrored again; and a restart is seen only when the source returns the entry at
the cursor or nothing newer than it: a log that restarted and grew past the cursor read from after it (a Kafka
offset in `{cursor}`) loses the new entries up to the cursor without a word, and so does a restart that grew past the
cursor once the cursor's own event is rolled up or pruned (there is then nothing recorded at the cursor to compare with).

**What a template may declare.** `items`, `systems`, `parameters`, `auxiliaries`, `stocks`, `flows`, `goals`,
`blocks`, `agents` and `uses`, and the `workspaces` and gated `actions` its AI blocks use (section 12k): each named
for the instance like any part (`steps` makes `NAME-workspace`, and `NAME-push` for an action `push`), and a
block's `workspace:` and `actions:` follow the names. A block's lease terms are its own (`lease:`, with `takes:`
and `pool:`); `leases:`, each tier's terms, belongs to the model as a whole, as do `messages:` and `storage:`.

**Folders the owner did not write.** A `library:` entry is a path (the owner's folder, trusted) or a map
`{folder: PATH}`, which is **untrusted** unless it says `trust: owner` (`trust: untrusted` says so plainly):

```yaml
library:
  - ~/private/ergostat-templates          # the owner's: trusted
  - {folder: ~/shared/team-templates}     # not marked trusted: untrusted
```

A map with another key, no `folder:`, or a `trust:` other than `owner` or `untrusted` is an error at its line
(**bad-library**), and its folder is not read at all. `$ERGOSTAT_LIBRARY` is the owner's. Trust is each file's: a
template file inside any folder listed untrusted is untrusted, even when a trusted folder (its parent, whose
`*/template.yaml` reaches it) is listed too. Each template's trust
(`ergostat`, `owner` or `untrusted`) is shown by the authoring tools' `library`. An untrusted template never takes the
place of ergostat's own or a trusted one of the same name, whatever order the folders are listed in: the trusted one is
used and `check` names the file skipped (**template-library**); between untrusted folders the first wins.

A use is **held** when its template, or any template it uses at any depth, is untrusted. Its whole chain is expanded
before anything of it is put in the model, and every part made from the first untrusted template down (trusted and
built-in templates it uses included), as expanded with every parameter's value in it, is checked against the allowlist
in `ergostat/library/trust.py`: the sections `systems`, `items`, `parameters`, `auxiliaries`, `stocks`, `flows`,
`goals`, `blocks` and `uses`, and in each only the keys (and shapes of value) listed there; blocks only of the types
`onoff`, `compare`, `proportional`, `limit`, `delay`, `schedule`, `lookup`, `select`, `expr`, `timer`, `counter` and
`alarm`, whose `out:` names only parts the chain made (an `out:` commands the block it names and sets the goal it
names); sensors counting items (`items:`) or reading a stock's changes (`changes:`); and the runs below.
Anything else is refused: any other section, block type or key (a sensor's `query` or `daemon`, a block's
`on-stale` or an `out:` to the owner's block or goal, a kind's `lease`, a goal's `owner`, `inferred` or `formerly`
anywhere). One refused part refuses the whole
use at the owner's `use:` line (**library-untrusted**), naming the template, its folder and the first refused path;
nothing of the chain is in the model. Only the owner can mark a folder trusted, after reading it (docs/SECURITY.md,
*Libraries you did not write*).

**Writers.** Every parameter value has a writer: the **owner** (a value in the owner's own file, in a depth-0
`with:`), a **trusted** template (ergostat's own, or one from the owner's folders: its literal text, its defaults and
its `|default`s), or the **library** (anything an untrusted template writes: its literal text, defaults, `|default`s,
and text it builds around values). A nested use's `with:` value that is wholly one `${p}` (no `:how`, `|default` or
`.field`) keeps p's writer; any other is the library's if any part of it is (a parameter written by a library, a
field such as `${it.x}`, `${p.first}` or `${p.count}`, whose writer can't be told, or a key that can't be found in the
template), else the writer of the template writing it. A value is an **owner command** only if the owner wrote it for
a `type: command` parameter and every later hop passed it wholly to a `type: command` parameter again; a hop through
any other type, or text equal to a command the owner wrote elsewhere, is not one. `expand.py` marks every substituted
value with its writer, its type and whether its own text is its type's narrow form, keeps the marks until the gate
has judged the chain, then strips them. Only expand makes marks: a template or a value holding a mark's control
characters is refused, whole.

**R1, what a held chain may run.** A sensor's or a `program` block's `run` stands when every character of it is: (a)
an owner command, as the whole value; or, inside a built-in template's run, (b) the template's own text, ergostat's
names (`${lib}`, `${python}`, `${name}`), a value ergostat's template wrote, or an owner command through `:quote` or
`:arg`; or (c) a value allowed by R2. A library's text (an untrusted template's words around `${cmd}`, its
`${here}`, a library default for a command), an owner value of another type (a `string`), and a run holding a field
(`${it.run}`) refuse the chain. `every`, `cron`, `timeout` and `averages` stand only as the owner or a trusted
template wrote them. A `program` block may say only `goal`, `run`, `every`, `cron`, `timeout` and the common block
keys; `parse`, `max`, `pool`, `lease`, `agent`, `workspace`, `actions`, `network` and the rest stay refused, as do
`ai` and `person` blocks (`prompt`, `ask`).

**R2, a library's values as arguments to ergostat's programs.** A value not written by ergostat's template (the
library's, the owner's of a narrow type, or an owner folder's) may stand in a run only in a built-in template whose
run starts `${lib} `, directly after a flag in trust.py's `LIB_DATA_FLAGS` (flags of `ergostat.library.run` whose
value is data, such as `--kind`, `--state`, `--every`, `--limit`; never `--run`, `--render`, `--command` or another
of `LIB_EXEC_FLAGS`), for a parameter typed `name`, `duration`, `number`, `integer` or `bool`, when both the value's
own text and the text that lands (after `:seconds`, `:hours`) fully match its type's pattern, with no space or
newline: name `[a-z][a-z0-9-]{0,63}`; duration `[0-9]{1,9}(\.[0-9]{1,6})?(ms|s|m|h|d|w)?`; number or integer
`-?[0-9]{1,15}(\.[0-9]{1,9})?`; bool the bare flag (`:arg`), or `true`/`false`. A rate or count flag is also bounded
(`LIB_BOUNDS`): `--every` `UNTRUSTED_EVERY` (300 s) or more, `--limit` 100 or less, `--stand-in` 3600 an hour or
less, `--window` 60 s to a week. No other type (string, strings, url, path, map, list, glob, cron, setpoint, any) reaches a run, and no value
not ergostat's own reaches the run of a template from the owner's folders (such as `sh -c ${x:quote}`), even though
that template is trusted: no test can vouch for one. Every option of every program is in exactly one of the two
lists, and every built-in run slot is scanned against these rules (`tests/test_library_provenance.py`).

What R1 and R2 let through is still an untrusted part, under the limits of *Untrusted libraries* above: one floor on
how often, `UNTRUSTED_EVERY`, whoever wrote the `every`. So a held chain's program block needs the owner's `every:`
of 5m or more, and built-in templates whose own timers are faster (collect's 30 s count of what it has collected,
re-ping's 10 s sensors and 30 s pinger) pass the gate but not those limits; collect compiles in a held chain with
`into:` a stock the chain made and the owner's `poll:` of 5m or more.

### Upkeep

`use: upkeep` (once a model, its parts in a system named for the use, `upkeep` by convention) draws ergostat's own
upkeep as loops of the model: the item-index files (section 4b: one `<state>/items/<hash>[.n].db` per shape of the
model's item kinds), and the watched loops below. The stock `index-files` (`ergostat.upkeep.index-files`,
the live files) fills by `index-files-made` (`changes: rises`, a new file on each change to the kinds) and drains by
`index-files-tidied` (`changes: falls`). The stock `retired-index-files` (`ergostat.upkeep.retired-index-files`)
drains by `retired-index-files-removed`. A file is *retired* when its mark `<hash>[.n].retired` stands beside it
(`itemindex.retired`, the one test the measures and the tidy both use): a process still held it when it was due to
go, and it is never opened again. The goal `index-files-few` holds `index-files <= ${index-files}` (default 6, 1 to
64, checked when the model loads), and `no-retired-index-files` holds the retired ones at 0. The controller
`index-tidier` is a program on the rule rung, `${lib} upkeep tidy --keep ${index-files}` every `tidy-every` (10m).
It works from the state directory alone (never the project, its model or an index, which it only locks), refuses
`--keep` outside 1 to 64 (exit 2), and exits 1 with a message when `<state>/items` is missing or cannot be listed.
It prints one line per output: `{"out": "flow.index-files-tidied", "moved": LIVE, "left": ..., "held": ...,
"young": ...}` (the live files it removed) and `{"out": "flow.retired-index-files-removed", "moved": RETIRED}` (the
retired ones), so the engine opens each flow's valve by its own count.

**The engine stands down.** In a model whose `uses:` holds ergostat's own `upkeep`, `index_for` no longer tidies the
folder when it makes a new file; the `index-tidier` does. The engine reads that from the model it is given (the
spec it folds with, after each reload). A model without it tidies as before (`KEPT_FILES`, 6).

**The interlock stays in the code.** Whether a file may be deleted is decided only in `spec/itemindex.py`, for the
engine and the tidier alike, and no goal, parameter or template changes it: only a regular file named
`^[0-9a-f]{16}(\.[0-9]+)?\.db$` directly in the resolved items folder (never a symlink, never another name), with
its `-wal`, `-shm` and `.lock`; only under its exclusive lock taken without waiting (a lock file that cannot be
opened counts as held). A retired file goes once its lock is taken, whatever its age (it is never opened again). A
live file goes only when, besides, neither it nor its WAL or shared memory changed within `TIDY_AGE` (an hour),
checked before the lock and again once it is held.

**Fail-safe.** A measure with no state directory, or a folder it cannot list, gives no reading, never 0. If the
tidier stops, nothing else limits the number of files under `use: upkeep`: they only pile up (one per change of the
kinds), and every index still opens and folds right. The event log's roll-up and measurement retention are still
to come.

**The watched loops.** The template also draws the functions that keep the engine itself going. They are drawn,
not run: each controller is ergostat's code, a `type: external` block (observed, never started by ergostat), and no
goal, parameter or block turns one off or goes round it (`coordinator/08-modes-and-protection.md` §5.3).

- The stock `stalls` (`ergostat.upkeep.stalls`: `ergostat.engine.stalled` events over the last hour) is held at 0 by
  `no-stalls`, served by `watchdog`, the engine's own watchdog (`spec/watchdog.py`, section 9.1). It drains by
  `stalls-mended` (`changes: falls`).
- The stock `heartbeat-age` (`ergostat.upkeep.heartbeat-age`: the seconds since the last pass `heartbeat.json`
  gives) is held at `<= ${stale}` by `heartbeat-fresh` (`stale` 180 by default, 60 to 3600, checked when the model
  loads), served by `outer-watcher` (`watcher.py`, kept running by `ergostat run --service`: launchd or systemd). It
  fills by `heartbeat-aged` (time passing, its rises) and drains by `heartbeat-renewed`. The stock `restarts`
  (`ergostat.upkeep.restarts`: `ergostat.engine.restarted` events over the last day) fills by `restarts-made`, which
  the outer watcher moves, and has no goal.
- With `leases: true` (default false): the stocks `overdue-leases` and `expired-leases` (`ergostat.leases.overdue`,
  `.expired`), the goal `no-overdue-leases` (`<= 0`), and the external block `lease-expiry` (`leases/dispatch.py`).
- With `pool: NAME` (default none): the stocks `free-workspaces` and `quarantined-workspaces`
  (`ergostat.workspaces.free@NAME`, `.quarantined@NAME`), the goal `no-quarantined-workspaces` (`<= 0`), and
  `pool-keeper`, a person: the owner, asked to free a quarantined slot (`ergostat workspaces NAME --free N`).
  Ergostat never frees one by itself. Nothing for leases or a pool appears unless asked for.

**The layers**, in order: the engine's watchdog mends a wedged sensor pool or loop inside its process and restarts
the process past that; the outer watcher, or launchd or systemd beneath it, restarts an engine dead or frozen whole;
then the owner. **The heartbeat goal is read from outside.** In a model with `use: upkeep` the engine writes the
goal's limit into `heartbeat.json` as `"stale": N` each beat (`ir.heartbeat_stale`). The file is written whole each
time, so a model without the template, or one the template was taken out of, writes no `stale`. The watcher uses
`stale` only when it is a real number (never a bool, NaN or infinity) with `60 <= stale <= 3600`; missing, it uses
180 and says nothing (the normal case without the template); malformed or out of range, it uses 180 and says so in
`run.log`, once for each value in a watcher process. So `stale` lets the watched engine relax the outer watcher's
limit to at most 3600 s, or tighten it to 60 s; it never turns the watcher off, and it never changes whether the
engine's own watchdog runs. The heartbeat the run writes as it starts carries no `stale`, so 180 applies until the
watchdog's first beat.

**No controller reads what it manages.** The watcher still reads only `run.pid`, `heartbeat.json` and `stopped`
(and, when it restarts, its own back-off, `restarts.json`, and `run.log`). The engine's sensor of `heartbeat-age` is
a drawing, not a protection: an engine frozen whole reads nothing, and the outer watcher is the layer that acts. Each
measure gives no reading, never 0, when what it reads is missing: no `heartbeat.json`, one that cannot be read, one
with no finite last pass or a pass stamped in the future; an event log that cannot be read.

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
purpose: keep checkout fast    # optional, main file only: what the whole model is for (section 4a)
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
leases:                         # optional: each tier's lease terms (section 9.5)
  ...
loops:                          # optional: names for feedback loops (section 12a)
  ...
uses:                           # optional: instances of templates (section 2a)
  ...
remotes:                        # optional: systems other ergostats run, read here (section 4c)
  ...
web:                            # optional, main file only (or ergostat.local.yaml, section 2): the page's public names and their login (section 4d)
  ...
library:                        # optional, main file only: folders of templates, {folder: P} untrusted (section 2a)
  - ...                         # a folder (trusted), {folder: PATH, trust: owner}, or {folder: PATH, untrusted: true|false}
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

`purpose:` (top level, the main file only) says in a sentence what the whole model is for: a goal in no system that
says what it is for is traced to it (the `purpose` note, section 12). Each system's size (its parts at any depth, the
feedback loops inside it and through it, and the levels of systems within it) is in `explain` and on its panel.
Beside its size, the Dynamics panel names each chain of its own stocks that, over the window shown, no feedback loop
beyond each stock's own drove: a candidate to aggregate into one delay, not a finding (section 12c, *Stocks to
aggregate*). It is worked out from the loop dominance over that window; no row is shown when the dominance is not
known.

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

With a project, it also says how stable the interface has been: "Interface over the model's
recorded history: unchanged over the last U of V recorded versions (since DATE); C changes."
It counts the `model.changed` events (section 9.1) in their order in the record, never by time,
over the latest unbroken run that records this system's interface. An event without interfaces
(a TOML stretch, a record from before they were kept), one without this system (it was removed and
made again), or one that cannot be read starts the count over. Two equal records of one version
count once. Only versions ergostat loaded are seen, so an edit made and undone between loads is
not. A change can also come from an upgrade that works out interfaces differently, with the model
unedited. When the interface as it is now is not the last one recorded, it says "the interface as
it is now is not recorded yet" and gives no counts. Only `explain` says this; the system's box
and panel do not.

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
  items:
    idle: 1d                       # an item with no event for this long is read from the item index, not kept in memory
  logs:                            # caps on what would otherwise grow without limit
    block: 5MB                     # a block's log (logs/<block>.log) past this is cut to its last fifth, as a run ends
    runs: 50                       # each block's run files (logs/runs/<block>/) kept, newest by start seq: 1 to 1000
    run: 5MB                       # run.log past this is copied to run.log.1 and emptied, at each start and each roll-up
    threads: 1MB                   # threads.txt (kill -USR1's stacks) past this is cut to its last fifth
    transcripts: 30d               # a transcript unchanged this long is forgotten by transcripts.json, not read again
```

**Each run's own log.** Each run of a `program` or `ai` block (a daemon's run too) writes to a file of its own,
`logs/runs/<block>/<seq>-<id>.log` (`<seq>` the seq of its `agent.started`, `<id>` the first 12 characters of the run's
id): its standard error and the lines it printed that were not JSON, with no header, and nothing of any other run. Its
`agent.ran` or `agent.failed` names it (`log`). It is opened relative to `logs/`, without following a link, and never
over a file already there (the names tried next are `-2` to `-9`, then `run-<seq>-<fullid>.log`). A block name that is
not a plain name, a link or something not a folder where `runs` or `runs/<block>` should be, or no start seq: the run
does not start (`could not start: its run log: ...`). When the run ends (its process has exited, or its daemon has
answered), its entry is added to the block's log, `logs/<block>.log`, in one write under `logs/<block>.log.lock`, with
the trim: the header `--- <start time> run <id8> (<why>)`, then the last `block:` bytes of its file, after
`(N bytes earlier: logs/runs/<block>/<file>)` when it is longer. So the block's log holds whole runs one after another
and shows a run once it has ended; a run's output as it goes is in its own file. Then the block's files past `runs:` are
removed, oldest by start seq first, but only names ergostat gives them and only a file no run still holds (a run holds a
shared lock on its file for its whole life; so does a process its child left behind, which keeps the file).

`ergostat compact --projects` lists the record folders under `~/.ergostat` whose `repo.json` names a repository
that is gone (its parent folder is there and it is not: an unmounted drive is not gone) and where no engine runs,
with their sizes; `--yes` lists them, then deletes those folders and nothing else (a symlink, a folder without a
`repo.json`, or whose repository is there, is never touched).

**Events.** `segments` (the default) is an append-only log in `<state>/events/`: the newest events
in `head.jsonl`, appended under a file lock by whichever process records them (the runner, the
page, the command line); every 32,768 events sealed into a segment of gzip blocks (512 events a
block, read alone) with an index (each item's and each type's rows, the times and seqs as
columns, a Bloom filter of the ids, and what its events add up to per valve, controller and block:
openings, decisions, runs), so a query by item, type and time reads only the rows and
blocks that match, and a month's tallies and crossings are read from headers and columns, not event by event. `sqlite` is `events.db`, as before. Both keep a transcript's lines
(`claude.*`) out of item counts without reading them (SQLite by a partial index, the log by its
type columns).

**The item index.** Every item's fold (section 5a) is kept on disk in `<state>/items/<key>.db`, one
SQLite file per fold (the model's item kinds, and whether a transcript's lines are folded in), and
followed as events arrive: whichever process asks first after events land (the runner, the page,
the command line) folds them, a chunk per transaction under SQLite's write lock, and the others read
what it wrote. A process that starts reads the index and folds only what is newer than it, so a
record of half a million items starts in seconds. Per item it holds its kind, state, times and
counts as columns and its document (fields and what was refused) packed small (marshal, compressed
when that saves, chosen by measurement over JSON and msgpack; JSON stays the format of the API and
the pages); kinds, states and event types are numbers. Every move is a row, so a flow counted from
items reads only its window, a stock counted from items only its states, and the Items page only
the page it shows. In memory, a process keeps folded only the items still open (a few thousand at
most, the latest touched): an item in a finished state (as `messages: {done:}` declares for its
kind, else its states after the first that no item has left) or with no event for `items.idle` is
read from disk when an event about it arrives. A field's history is never kept: the item's page folds
it from the record when asked. The record stays the truth: the index is folded again when it is
missing, when its layout changes, or when the record went back (a fresh record), and on
`ergostat compact --reindex`; a roll-up leaves it as it is (a snapshot folds to what its events
folded to), and a prune takes out the items whose events are all gone. `tests/test_item_index.py`
holds it equal to a fresh fold for every example's kinds, as events arrive, after roll-ups, read
cold and built again.

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
it would roll up). A roll-up reads only the items the item index says are due (their first event
since their snapshot older than the horizon, or a transcript's lines), a batch of them at a time.

**The page's answers are bounded.** No answer grows with the record: events are at most 1,000 an
answer (`n`, paged by `after` and `before`), items 500 (`offset`), a kind's finished items a thousand
dots (and how many there were), a chart's series a thousand buckets, a sensor's readings its latest
60 and how many; a loop's crossings are read for the window (and the one before it), never the
whole record. A client that hangs up before its answer is written is one line in the log, not a
traceback.

## 4c. Remote systems: another ergostat's system, read here

A **remote system** is a system another ergostat runs, composed into this model: its model is served by
that ergostat and changes while it runs, its events and measurements are read where they live, and its
blocks run there, never here. This model reads it, links to its parts and draws it as a subsystem; it
never runs it. (Not a library: a library is a copy this model runs; a remote is one running system seen
from two places. The design and its reasons: `docs/proposals/remote-systems.md`.)

In system dynamics terms it is a **subsystem with an interface**: its stocks and flows are endogenous
there and exogenous here (read as data, never integrated). In control terms it is a **separately
controlled plant**: what we read of it is a measured disturbance for our loops, or a setpoint handed to
us; we never close a loop through its actuators.

```yaml
remotes:
  incidents:                          # its parts are incidents-PART, in the system incidents
    url: http://127.0.0.1:8795        # https, or an SSH tunnel's loopback port
    token-file: ~/.config/ergostat/incidents.token
    systems: [triage]                 # optional: only these of its systems (and what is inside them)
    within: support                   # optional: the system it is drawn inside
    every: 1m                         # how often its model and readings are read (default 1m, least 10s)
    show: [stock.open]                # optional: what its closed box shows, in its own names
    description: the incident desk
```

| Key | Type | Default | Meaning |
|---|---|---|---|
| `url` | URL | required | The remote ergostat's page. Plain `http://` only to a loopback address (else **remote-insecure**, an error): across machines, https or an SSH tunnel (`ssh -N -L 8795:127.0.0.1:8781 HOST`) |
| `token-file` | path | none | The file holding the token the remote made for this model (`ergostat remote token NAME`, on the remote); `~` expanded, relative to this file |
| `tls` | map | none | Mutual TLS to a remote serving `web: mtls:` (below): `{cert: me.pem, key: me.key, ca: servers.pem}`, the certificate and key this model shows and the CA it trusts for the remote's (`ca` optional: else the system's trust, as for any https). Paths as `token-file`. Only with an `https://` url; a key missing or unknown is **bad-remote**; a file given that is missing, a directory or not PEM is **mtls-unreadable**, an error. Every read of the remote uses it; when a context can't be made from it the read fails (`tls: ca …: why`), never sent without the certificate or with the system's trust in place of `ca` |
| `systems` | list | all | Only these of the remote's systems, and the systems within them; a reference from them to a part left out is cut (a flow's end becomes a cloud, a cause or an input is dropped) |
| `within` | system name | the file's default | The local system it is drawn inside |
| `every` | duration | `1m` | How often its model is checked and its readings read |
| `description` | string | where it runs | |
| `show` | list | its top systems' `show:` | The measures its closed box shows, each `stock.NAME`, `flow.NAME` or `auxiliary.NAME` in the **remote's own** names, as it serves them: `stock.open` is its `open`, drawn here as `incidents-open`, even when this model has an `open` of its own; a local part is never shown on a remote's box. It takes the place of the served tops' `show:`. Anything else is **bad-remote**, an error |

**What it becomes here.** Each part it serves is put in under the remote's name (`stock.incidents-open`),
as a template's instance names its parts (§2a), in the system `incidents` (its own systems inside it,
`incidents-triage`), and points at the `remotes:` line (`ergostat.yaml:3 (remote incidents)`):

- its **blocks** are `type: external` whatever they are there (never started, leased or evaluated here),
  keeping their inputs and outputs, and a block that named a goal reads that goal's error;
- its **sensors** are queries of the remote's same series, `query: {source: incidents, series:
  sensor/open.main}`, every `every` or the sensor's own period there, whichever is longer; a flow a
  remote block moves, with no sensor of its own, gets one, `remote`, reading the remote's rate for it;
- its **goals** are evaluated here from those readings, as monitors; its **agents** are `external: true`
  (each keeps its rung); its **item kinds** stay there: the local fold never folds a remote's items;
- each remote is also a **source** of type `ergostat` (§11) of the same name.

**References into it.** A local part may read a remote part: a goal on it (`stock: incidents-open`), a
cause (`driven-by: [+stock.incidents-open]`), a flow from it (`from: incidents-escalated`), a block's
input. They are checked against the remote's **current** model at every load (`ergostat check` asks it
first). A local block may not output to a remote part (**remote-output**, an error): what runs there is
changed there. A reference the remote no longer serves is a finding, never a refused model
(**remote-reference-unresolved**): a stand-in with no sensor takes its place until it resolves again.

**Kept current.** The remote's model is cached in `<state>/remotes/NAME/model.json`, with its version, and
how it last answered in `status.json`. The running ergostat and the page ask again every `every`
(conditionally: an unchanged model is a 304), and at once when a reading says its version moved; a new
version is written to the cache, which is one of the model's files, so the model reloads as for an edit.
A remote that fails is asked less often (twice the period after each failure, up to ten). When it does
not answer, the model is drawn from the cache, every reading from it fails and keeps its last value with
its age (`sensor.failed`), its box says *not answering for 2m · readings 3m old*, and the status and
`check` carry **remote-unreachable**. A reading older than three of its sensor's periods (two minutes at
least) is stale and is not taken.

**Drawn.** In Dynamics and Blocks a remote is one box, closed by default (even alone at its level),
its outline dashed, saying where it runs, the version of its model and how old its readings are; it opens
in place like any system. In Process its kinds' maps are drawn beside ours, framed *remote incidents*.

**Lines to a remote's items.** Where one of our items names a remote's item through a relation to the remote's kind
(§5a, *A remote's kind*), the process map draws a related line, dashed, from the step our item was last at in the
window to the step the remote says its item was last at (`at=` on `/remote/v1/process`, in the same request as its
map). The ids sent are the distinct ids named, each 1 to 128 characters with no space or control character (any
other is `bad-id`), sorted by id (never by time), as many as fit in 200 ids and 32,000 bytes of query (the rest
`capped`); the remote refuses more than 200 (400). A link is drawn only when the remote's answer names its item with
the relation's kind (`other-kind` otherwise) and a step (`not-answered` when the answer leaves it out, is malformed,
or the remote predates `at`), that step is in the remote's map as drawn (`not-drawn`) and our step in ours
(`not-drawn-here`); an unreachable remote counts its links `unreachable`, after `bad-id` and `capped`, which are
decided before the request. A link not drawn is never dropped: `remotes.NAME.unlinked` counts it by reason, and
`linked` the ones drawn, so the two add up to every link; the side list says how many are not drawn and why.
Several relations naming one id ask it once, and the answer is checked against each link's kind. No time of the
remote's is compared with one of ours, and the line never gates (§5a). The remote's map as last read in the window
is drawn when it does not answer, marked `cached`, its `at` used only when it was for exactly the ids sent now.
Its closed box shows, in this order of precedence: (a) the `show:` on its `remotes:` entry; else (b) the
served `show:` of its top systems (those with no `within`, or with `systems:` the kept ones whose `within` is
not kept), in the order it serves them, each part once, a part `systems:` leaves out cut; else (c) the
measures of its goals that it serves (never a stand-in's); (d) a remote never read shows the parts its local
`show:` names, each *never read*, and with none no measures at all, never a goal's. A system inside it shows
its own served `show:`. The panel (Dynamics' module, the system panel) lists them under the remote note,
and Blocks' box draws them as rows. A measure there is **stale**, dimmed, and says `last V · AGE old`
(AGE: the snapshot's moment less its newest reading here) or *never read* when the remote is not answering,
its readings fail, or it has not answered yet: then every measure is stale. When it answers, a measure is
stale when its sensors' newest reading here is older than three of its sensor's periods (two minutes at
least, also for a sensor with no period), and says *never read here* when they have none; a part with no
sensor here is stale only when the remote is not answering. A local `show:` part it does not serve stays,
dimmed, *not served*, and is a finding (**remote-show-unresolved**, on the `show:` key: the version it was
checked against, as last read when the remote is not answering, and why: it serves no such part, `systems:`
leaves it out, or the name is a local one); neither it nor a *never read* one is charted.
The local residuals, coherence and attention leave its parts out: they are held to its own record, there.

**Never edited here.** A model change (§12e) that would write a remote part is refused, as one that would
write a template's part: it is the remote owner's to make.

**Proposals for its owner** (`ergostat/numbers/remote_text.py`). When the calibration's parameter estimate or the
equation finder (§12b) finds a change whose every edited part is one remote's (a parameter proposal's parameters, an
equation's flow), it is written as **text for that remote's owner**, never as an edit. Under the same id the local
one would have, it is an `ergostat.model-change` item holding only `kind`, `title`, `text`, `evidence`,
`for_remote` (`{remote, version, parts: {local ref: remote ref}}`), `subject`, `made_by`, `created` and `made`
(an allowlist, `FIELDS`): no fit, gate, estimate, edit or local version. Its text names the remote's parts in the
remote's own names (looked up in what it served, `parameter.incidents-rate` → `parameter.rate`; a stand-in is never
there), says what to change (a value from → to, ± one standard error; or a flow's equation and each new parameter's
value, the new names made from the remote's names and free against its parameters), and gives the evidence: points,
window and the series read. It makes no claim of fit. When a name is not served, nothing is written, and what is
under its id is left as it was. It is recorded under the proposals' lock and, inside it, the remote's cache lock
(`<state>/remotes/NAME/model.lock`, which a refresh holds while it reads and writes `model.json`), only when the
version in the cache file is the version the evidence was computed on: a file missing, unreadable or without a
version, or another version, records nothing. It is **current** only while both versions are read and equal (never
by time); a superseding pass supersedes it when the cache's version has moved (saying from what to what), and one
that cannot be read supersedes nothing but is listed as not current, with why. Found again at the same version with
the same text it is left alone, and a dismissed one is not written again there; at a new version, or with another
text, it is made again, open, and nothing of a decision under that id is kept (a change of this model's own under
the id, whatever became of it, is superseded first; one made again from a text loses `for_remote`, `text` and
`evidence`). Its state is `checked` and it is never in the review queue (`proposals.pending`), the judge, the
inbox, MCP or the Model page; Accept refuses it first, by every path ("is text for remote NAME's owner: it is never
applied here"); dismiss lets it go. It is **never sent by ergostat: sending it is the owner's act.** `ergostat
remote proposals [NAME] [--json]` lists the open and the dismissed ones, each with the version it was written
against, whether it is current and its text; it takes no lock and writes nothing, and runs on the last good model
while the YAML is broken (`goodmodel.READ_WHAT`; the rest of `ergostat remote` acts). `ergostat proposals` says how
many are waiting there. Not made for a remote: a change touching both this model's parts and a remote's, or two
remotes' (kept with its edit's error, and refused by Accept as before); structural changes, redesigns, a block's
proposal and the owner's what-if (refused, as any edit of a remote part).

**What a remote serves.** Any ergostat whose page runs serves this read-only API once a token is made
(`ergostat remote token NAME`, printed once, kept only as its hash; `--revoke`; `ergostat remote tokens`).
Every request carries `Authorization: Bearer TOKEN`; only `GET`; 10 requests a second per token (bursts
of 30), then 429. The page's Host check does not apply here (a tunnel sends its own name): the token is
what admits.

| Address | Answers |
|---|---|
| `/remote/v1/status` | name, model version, now, the newest event's `seq`, whether it runs |
| `/remote/v1/model` | its model, `format: ergostat-model/1`: the merged document after includes and templates, redacted (no commands, prompts, queries, sources, workspaces or actions), with `version` (16 hex of the SHA-256 of its canonical JSON); `ETag` is the version |
| `/remote/v1/events?after=SEQ` | events after the cursor in `seq` order, `n` ≤ 1,000, filtered by `type`, `item`, `kind`, `since`, `until`; `next` (the cursor) and `more` |
| `/remote/v1/items`, `/remote/v1/items/ID`, `/remote/v1/counts` | the item listing (`n` ≤ 500), one item, items by kind and state |
| `/remote/v1/readings?series=…&ref=…` | the newest reading of each series and part (`stock.x`, `flow.x`, `auxiliary.x`, `goal.x`), with its time; at most 200 a call |
| `/remote/v1/series?name=…` | one series over `since`…`until`, `n` ≤ 1,000 points |
| `/remote/v1/process` | its process map (§5b); with `at=ID` (repeated, each id whole, at most 200), `at`: the kind and the step each id asked was last at in the window (an id with no step there left out) |

`ergostat remote` lists this model's remotes (url, version, parts, how each answers); `ergostat remote
events NAME` reads a remote's newest events in place, by cursor, into a cache kept for a day (20,000 at
most); `ergostat remote refresh` asks each again now; `ergostat remote proposals` lists the texts written for
remotes' owners (above).

**Its items and events in the pages.** The Items page adds, after the local systems, one section per remote,
framed and marked *remote NAME · URL*: the remote's counts by kind and state and its newest 25 items, each linking
to `/item/ID?remote=NAME` (its fields, moves and events read there, marked remote, read only: no message box, no
actions) and to the remote's own page (`URL/item/ID`). A remote item's `file:PATH` value names a file in the
remote's project, so it is shown as its text, never read from this ergostat's `/file/` or drawn inline. It is asked
by its own call, so a slow remote never delays the local listing. The Record page's filter bar links to each
remote's events (`/record?remote=NAME`), listed as local events are, their items linking to the remote's. Nothing
of them reaches the local record or fold.

| Asked of the page | Answers |
|---|---|
| `/api/items?remote=NAME` (`kind`, `state`, `n` 1..500, `offset` 0..100,000) | `remote`, `url`, `ok`, `why`, `read`, `age`, `counts` (from `/remote/v1/counts`), `total`, `items` (each marked `remote`) |
| `/api/items/ID?remote=NAME` | `remote`, `ok`, `why`, `read`, `age`, `item` (the remote's own detail); 404 *no such item at NAME* on any 404 there, never a local item of the same id |
| `/api/events?remote=NAME` (`n` ≤ 1,000, `type` a glob) | `remote`, `ok`, `why`, `read`, `age`, `events` from the cursor cache, in `seq` order, each marked `remote` |

Without `remote=` these answer as before; `/api/items` also says `remotes` (each name and url) when the model has
any. `NAME` must be a key of `remotes:` (else 400 *no remote NAME (this model's: …)*). An item `ID` (such as
`incident/3`: item kinds' ids hold a `/`) must be at most 200 characters of `/`-separated segments, each fully
matching `[A-Za-z0-9_][A-Za-z0-9_.:@#+=-]*` (so no segment is empty or starts with `.`), and hold no `..`. This is
checked before anything is sent (else 400), and the id then goes quoted whole as one path segment
(`items/incident%2F3`), which the remote unquotes after splitting its path. It is an allowlist: an id with `%`, a
space, `\`, an empty segment or `..` is refused, and such an item is listed but can be opened only on its own page.

- **Bounded.** A remote's period is its `every` clamped to 10 s..10 min. In one period at most **8 requests** go to
  one remote for its items, counts, listings and details together; the counter goes up before each request, and a
  request that fails counts. Counts are cached once a period; listings (by `kind`, `state`, `n`, `offset`) and
  details (by id) up to 32 each a remote, the oldest dropped first; a cached answer younger than the period is
  served without asking. With the budget spent, a cached answer is served with its `age`; with none, 503 *NAME
  asked 8 times this period; again in Ts*. Its events are read at most once a period (a status call the first time,
  then at most five pages of 1,000). `ergostat remote events NAME` reads in its own process, every time it is run,
  whatever the period; it shares no cache with the page server, so the pages' period is unaffected by it.
- **One lock a remote.** Each decision (fresh? failed this period? within the budget?), the request, the write and
  the trim are made under one lock per remote, so many pages polling ask once. Each request has a 3 s timeout on
  each socket operation (connecting, and each read), not a total deadline, so a remote that answers slowly can hold
  its lock longer; a caller waits at most 7 s for an items lock (19 s for the events lock, whose holder may make six requests), then
  is answered with an error saying the remote is busy (503 for items, 502 for events). Events already read are
  instead shown as they were last read, with their age, `ok: false` and *busy*. A remote that hangs holds only its
  own callers.
- **By `seq`.** Only events past the cursor are kept, so a page read twice adds nothing. An answer whose
  `last_seq` is below the cursor means the remote's record was made again: what was kept is dropped and the read
  starts again from `last_seq - 1000` (0 at least). A remote remade whose record has already passed the old cursor
  is not detected (its status carries no identity of its record): its older events stay mixed in until the day's
  window drops them, and its events up to the old cursor are not read.
- **Failing closed.** A token file missing, unreadable or empty, a remote that does not answer or answers 401, 403
  or 5xx, and an answer that is not the expected shape (*unexpected answer*) are failures: what was read before is
  served with `ok: false`, `why` and its `age`, and with nothing read before the answer is 502 with the reason. A
  remote that failed is not asked again until its period has passed. The pages then say *NAME does not answer
  (why); these were read T ago*, never "Nothing recorded yet.". Any 404 on one item, whatever its text (an older
  remote, a proxy), is 404 *no such item at NAME*: it is that item missing, not the remote failing, so the
  remote's counts and listings are still asked. An event whose `time` is not a number cannot be windowed: it is
  left out, and `why` says how many were. `/api/events/ID?remote=NAME` is refused with 400: a remote's events are
  listed, never opened one by one here.

**Over mutual TLS.** `web: mtls:` (§4d; per machine, so in `ergostat.local.yaml` when the model is shared)
starts a second listener beside the loopback page that serves only this API, over TLS, to clients whose
certificate the owner's CA signed:

```yaml
web:
  mtls:
    port: 8796                                       # required, 1..65535
    bind: 0.0.0.0                                    # an address (default 0.0.0.0)
    cert: ~/.config/ergostat/tls/server.pem          # this listener's certificate (required)
    key: ~/.config/ergostat/tls/server.key           # and its key (required)
    client-ca: ~/.config/ergostat/tls/clients.pem    # required: whose client certificates are taken
```

Paths expand `~` and are relative to the model's folder. An unknown key, a bad port or a bad address is
**bad-web**. Each file that is missing, a directory or not PEM (or a key that is not the certificate's) is
**mtls-unreadable**: an error to `ergostat check`, and when the model loads no port is bound, the loopback
page serves as ever, and `ergostat run` and `ergostat web` say `remote API over mutual TLS: not listening:
web.mtls.cert PATH: why` (else `remote API over mutual TLS: https://BIND:PORT`). Both contexts, this
listener's and a remote's `tls:`, are set to TLS 1.2 at least; the listener requires a client certificate
and trusts `client-ca` alone (never the system's trust); a remote's checks the host name. Its limits are
fixed, not settings: 16 connections at once (one more is closed at once, never queued), 10 s for a
handshake in all (however slowly its bytes come), then 10 s without a byte after it or between requests;
past either the connection is closed. A client holding a certificate from `client-ca` that sends a byte
now and then keeps its slot: only the handshake has a total bound. Only `GET` (any
other method 405) of `/remote/v1/status`, `model`, `events`, `items`, `counts`, `readings`, `series` or
`process` and below, read on decoded path segments (none `.`, `..`, empty or holding a slash); any other
path is 404 and never reaches the page. The token is still needed, as on the page (its 10 a second, and
404 until one is made): the certificate admits the connection and the token names the consumer. The two are
not tied: any certificate `client-ca` signed may carry any consumer's token. Stopping the page stops the
listener, closing every open connection.

## 4d. The page behind a public name

The page answers on this machine only: a request must name it as `127.0.0.1:PORT` (or `localhost`, `[::1]`) in its
`Host`, so a page on another site whose name was pointed at this machine (DNS rebinding) is refused. To reach it
from elsewhere through a tunnel (cloudflared) at a public name, the main file declares the name and the Cloudflare
Access application that logs people in there (a tunnel belongs to one machine: put `web:` in that machine's
`ergostat.local.yaml`, section 2, when the model is shared):

```yaml
web:
  names: [ergostat.example.org]          # the tunnel's public hostname(s): no scheme, port or path
  access:
    team: myteam.cloudflareaccess.com    # the Access team domain (myteam alone is the same)
    aud: 4714c1358e65fe4b...             # the Access application's Audience (AUD) tag
    emails: [owner@example.org]          # who may use the page
```

| Request | Served |
|---|---|
| `Host` the local name, nothing from Cloudflare | as before: the owner |
| `Host` a declared name, or any request carrying `Cf-Ray`, `Cf-Connecting-Ip` or `Cf-Access-Jwt-Assertion` (a tunnel that rewrites `Host` to the local name) | only with a valid `Cf-Access-Jwt-Assertion` whose `email` is listed; 401 without one, 403 for an email not listed or when `web:` declares no login. Reads too |
| `Host` a name declared with `open: read` in place of `access:` | reads to anyone, Cloudflare's headers or not; every write 403; the page says it is public and read only, and `check` says so (**web-public**) |
| any other `Host` | 403 |

`open: read` (`web: {names: [dev.example.org], open: read}`) is for an instance whose owner wants it seen without a
login: anyone who reaches the name reads everything the page shows, and nothing is changed there. The tunnel must
keep the declared name as the `Host`: a request through Cloudflare by the local name is still refused.

The token is verified with the standard library: RS256 only, against the team's keys
(`https://TEAM/cdn-cgi/access/certs`, fetched again hourly, and on a key not yet seen at most every 30 s; a fetch
that fails keeps the keys there were), `aud` holding the tag, `iss` the team's `https://TEAM`, `exp` not passed and
`nbf` reached (30 s of leeway). A write under the public name needs, besides the page's own token, `Origin`
`https://NAME`, and what it records says the email where a write from this machine says `owner` (who accepted a
proposal, approved an action, answered the inbox, sent a message); the inbox counts it as the owner's own answer,
never an agent's. Under a public name `/file/` never serves the state directory (its tokens). The push paths (`/api/events`, `/api/hooks/`,
section 5c) and the remote API (`/remote/`, section 4c) keep their own tokens. Requests still come only from this
machine (cloudflared runs here). `check` refuses a malformed `web:` (**bad-web**), and names without `access`.

| `web:` key | Meaning |
|---|---|
| `names` | the public names the page answers to (a tunnel's hostnames) |
| `access` | the Cloudflare Access application in front of them: `team`, `aud`, `emails` |
| `open` | `read`: the names public and read only, with no login (never with `access`) |
| `mtls` | the remote API on a listener of its own, over mutual TLS: `port`, `bind`, `cert`, `key`, `client-ca` (section 4c) |

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
| `observe` | bool | false | Estimated between readings (`stock.X.estimate`), its innovations recorded, and the goals on it watched for staleness (section 9.6) |
| `cumulative` | bool | false | A running total that by its nature never drains (spent so far, kept so far): no outflow is missing, and `check` does not ask for one (**stock-without-outflow**) |
| `rate-unit` | `minute`, `hour`, `day` or `week` | chosen by size | How the rates of its flows are shown, for each flow that says none (section 1a); display only, kept per hour |
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
observations, from `ergostat event --add`, pushed to the running ergostat (`POST /api/events`, a webhook: section
5c), or from an agent over MCP (`record_event`).

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
| `relations` | map of name → kind(s) | none | Its typed relations to other items, each a field holding the ids it names (*Relations*, below) |
| `join` | a rule, or a list | none | When its children move it on (*Join*, below) |
| `about` | a field name | none | The field naming the parts of the model each item is about (*About*, below) |
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
| `relation` | a set of item ids, kept as a sorted list: an id or a list of ids is added; `{"add": ..., "remove": ..., "set": ...}` says it outright (`set` first, the whole set, as a collector mirroring another system's links says it; then `add`, then `remove`). Anything but ids is refused. A relation's field folds by it unless `fold:` says `union` or `replace` |

**History.** Every change is kept, per path, in order: when, by which event (its id and type),
the operation (with its rule, or `patch` or `set`), the path, and the value before and after. A
change deeper in a field (`/comments/3`) is that field's. The item's `fields` is the folded
document as it stands, so whatever reads fields reads them as before; its history is beside it
(`ergostat item ID --history [FIELD]`; the item's page, where each field shows its value and a
history disclosure, each change linked to its event; `/api/items/ID`, each field's latest 100
changes and how many there were, all with `history=all`). An item can be read as it stood at any
time (`--at`, the pages' time travel): its fields, its state and its history are folded from
the events up to then.

**Search.** `ergostat item --search "WORDS" [--kind K] [--state S] [-n N] [--json]` and `/api/items?search=WORDS`
(with `kind`, `state`, `n` and `offset` as the listing takes them) list the items whose text contains every word, newest
first, in the listing's shape. An item's text is the string values of its fields, nested ones too, in the document's
order, casefolded (Python's `str.casefold`, as the words are: `STRASSE` finds `straße`); keys, numbers and its id are
not in it. A word matches as a plain substring (`alpha` finds `alphabet`; `%` and `_` are only themselves): there is no
ranking and no fuzzy match. Only the first 65,536 characters of an item's text are kept (`items.TEXT_MOST`): a word
past them is not found. A search is 1 to 8 words; an empty one, or more, is refused (exit 2, HTTP 400), never answered
with every item. It answers as of now: with `--at` (or `at=`) it is refused. It narrows by kind and one state only:
`/api/items?search=` with a set's filters (`where`, `moved`, `through`, `followed`, `caused`, `alone`, a list of
states) is refused (HTTP 400), never answered with the filter dropped. The text is kept in the item index,
on the item's own row, written with it and replaced each time the item is folded again (a changed field, a `set`, a
snapshot), and gone when the item is; an index from before it is rebuilt from the record, and a row without its text
has the index rebuilt before a search reads it. The Items page's own search box is apart from this.

**Relations.** An item may name other items: a ticket blocked by another, a ticket's epic, a duplicate. A kind
declares its relations, each a field of the item holding the ids it names, of the kinds it says (any kinds:
cross-kind is the usual case):

```yaml
items:
  epic:
    id: epic/*
    states: [planned, underway, shipped]
    relations:
      after: epic                           # precedence: it follows the epic it names
  ticket:
    id: ticket/*
    states: [todo, doing, review, done]
    relations:
      blocked_by: ticket                    # a kind, or a list of kinds
      parent: epic                          # a group
      duplicates: {kind: [ticket, epic], inverse: duplicated_by}
      relates_to: {kind: ticket, precedence: false}
messages:
  done: {ticket: [done], epic: [shipped]}   # what each kind counts as finished (else as the item index says)
  paused: {ticket: [on-hold]}               # states an item waits in, held by hand: not finished, not moving
```

| Key | Type | Default | Meaning |
|---|---|---|---|
| `kind` | a kind, or a list | required | The kinds it may name (the short form, `blocked_by: ticket`, is only this) |
| `precedence` | true or false | true for `blocked_by`, `after`, `depends_on` | Its targets come first: the item is **ready** only once each item it names is finished |
| `inverse` | a name | `blocks`, `before`, `dependents`, `children`, `duplicated_by`, `related_from`; else `NAME_of` | The other direction's name. Never written: ergostat derives it |
| `group` | true or false | true for `parent` | A parent: the Graph view hangs its children off it, and the critical path treats it as their summary |

A relation is a field like any other: events add and take away links as they change fields (`"data": {"blocked_by":
"ticket/12"}`, `{"blocked_by": {"remove": "ticket/12"}}`, a JSON Patch), and every change is in its history. The
item index keeps every item's links both ways (one row per link, indexed by the item and by the id it names), so
what an item names and what names it (the inverse: `blocks`, `children`) are both one lookup: an item's page lists
them both ways, each related item with its state, and what it waits on first. A link to an id that was never
recorded is kept, and said: what it names is not known to be finished.

**A remote's kind.** A relation may name a remote's item kind by its local name (`blocked_by: incidents-incident`,
for the kind `incident` of remote `incidents`, §4c): a kind that is not a local kind and starts with a remote's
name and `-` (the longest such name, when more than one fits). A local kind of that name comes first: the relation
is local, and nothing is asked of the remote. A remote relation names only that kind (with another kind it is an
error, `bad-relation`), is never precedence or a group, whatever its name (`precedence: true` on it is an error,
`remote-relation-precedence`: ergostat does not see when a remote's item is finished, so it cannot gate on it;
`group: true` is `bad-relation`), so an item it names never blocks, and is not waited on by `takes: {unblocked:
true}`. It is checked against the remote's model as last read: a kind the remote no longer serves, or a remote
never read, is a finding (`remote-reference-unresolved`), never an error. It is drawn in the process map (§4c).

**Graph queries.** Three questions over the links, both ways, and the items' fields (`spec/itemgraph.py`), as the
record is now: `ergostat item ID --near [N]`, `ergostat item A --path B`, `ergostat item ID --about`, each with
`--json`, and `GET /api/items-query?near=ID&depth=N`, `?path=A&to=B`, `?about=ID`, which answer the same JSON.
- **near**: the items within `N` hops (1 to 4, default 1), each with its distance and the step that first reached it
  (`via`: the item it came from and the relation).
- **path**: a shortest chain of relations from A to B (breadth first, the fewest steps), walked either way. A step
  walked backward is named by the relation's inverse: the one the kind declares (`inverse:`), else `blocks`,
  `children`, `before`, `dependents`, `duplicated_by`, `related_from` for the relations of those names, and `NAME_of`
  for any other (`relations.inverse_of`; any relation may be walked, the names are not an allowlist). `says` is
  `found`, `no path` (every item reachable was visited), or `none within the cap`.
- **about**: the items linking to it by a declared relation (`declared`, with the relation), then those whose fields
  hold its id as a whole token (`inferred`, with the first such field): `ticket/1` is not in `ticket/12`,
  `ticket/1/x` or `xticket/1`. Each string value of a field is matched, nested ones too, so an id at the start of a
  line counts. The mentions are looked for among the items whose indexed text (*Search*: the first
  65,536 characters of their fields' strings) holds the id, newest first; a mention past that is not found.

Each visits at most 2,000 items (`itemgraph.VISIT`), and says `capped` when it stopped there: a path not found
within the cap is never said to be "no path"; a walk that runs out of items to visit exactly at the cap is.
An unknown id is an error (the command exits 2, the API answers 404); a depth outside 1 to 4 or not a number, a path
with no `to=`, more than one of `near=`, `path=` and `about=` (the CLI's flags likewise), or one of them with `--at`
(`at=`) is refused (exit 2, 400), never answered with a default (only
no depth at all is 1; the API reads an empty `depth=` as none).

**Never enforced.** No transition is refused for a relation, and a block that does not ask (`takes: {unblocked:
true}`, section 9.5) takes an item whatever it waits on: the record holds what happened. What relations are read
for:

- **Each item's status**, derived: *done* (in a state its kind counts as finished, `messages: done:`, else as the
  item index says; never its first state, a state a block takes from, `leased` or `dead`); *active* (leased, or in a
  working state: past its first, not one a block takes from, not finished); *queued* (started, and waiting in a later
  state a block takes from, such as review); *blocked* (a precedence relation names an item not finished, a paused
  one too: it is named as what the item waits on); *unblocked* (in its first state, nothing it waits on unfinished;
  not "ready", which is often a state's name); *paused* (in a state its kind declares paused, `messages: paused:`:
  not finished, not active, kept out of the critical path, and held where it is by the completion estimates, "paused:
  continued by hand", with no projected bar); *dead* (a dead letter).
- **Durations**: each kind's time per state, the median of the stays its latest 2,000 items made in it (`leased`, a
  run's hold, counted as the work it is), weighted by how often a finished item visits the state (a rework state,
  seldom). An item's expected duration is that of its states after its first that are not finished (the wait in
  its first state is the schedule's to say); a started item's, what is left of its state and the states after it.
  A kind with no stays yet takes the median of the kinds that have them, else ten minutes, said as assumed.
- **The critical path** (the critical path method, Kelley and Walker): a forward pass over the unfinished items in
  precedence order (each starts once what it waits on is expected to end; a started item now: one past its kind's
  first state and not waiting in a state a block takes from, or held), a backward pass
  from the last expected end, and each item's **slack**, how long it may slip without moving that end; the
  critical items have none. A parent with unfinished children is their summary: what comes before it comes before
  its children, what comes after it waits for all of them. The critical path itself is not levelled (a block's
  `pool` is not in it); the completion estimates are (below).
- **The projected schedule**: each unfinished item's states ahead, from its earliest start, state by state; once the
  completion estimates are worked out, from a levelled run of their simulation instead (below).
- **Cycles**: items whose precedence relations go round can never all be ready. Each cycle needs attention
  (`ergostat`, the page's side panel), and is left out of the projection.

**About.** An item may say which parts of the model it bears on: a lesson about a goal, a note about a stock. A kind
opts in by naming the field that holds them, `about: FIELD`; the field holds one name or a list, each in the text
form a claim's `about` uses: `goal.x`, `stock.x`, `flow.x`, `auxiliary.x`, `block.x`. ergostat declares no such
kind of its own, and a model none of whose kinds declares `about:` looks nothing up.

```yaml
items:
  note:
    id: note/*
    states: [open, retired]
    about: about                            # "data": {"about": ["goal.inbox-short", "stock.inbox"]}
messages:
  done: {note: [retired]}
```

The field folds by `replace` (any other `fold:` for it, or a relation's name, is an error, `bad-about`): an event
that sets it replaces the whole list, so a part dropped from an item, or an item made again under the same id with
a new list, no longer points at the old part. The item index keeps each item→part link beside its relations' links,
as they stand now, so the items about a part are one indexed lookup, never a read of every item (an index built
before these links is built again). They are read in three places, each listing only the **open** items about the
part (not in a state its kind counts as finished, `messages: done:`, else as the item index says; a kind without
states, always open), the latest first:

- `ergostat explain PART` (and MCP's `explain`), with a project, ends with a line `Open items about goal.x: ID
  (title), ...`: each item's id, then its `title`, else its first field with a value; **at most 5**, then `and N
  more`. `none.` when there are none; `unknown` (with why) when the item index cannot be read, never `none`.
- `ergostat check`: a finding whose part has open items about it carries their ids (`items` in `--json`, and said
  in its message, at most 5 named); an open item naming something that is not a part of the model (`goal.gone`,
  `foo.x`, `goal.`, `stock.x.main`) is a finding, `about-missing-part` (section 12). Finished items are not checked.
- `ergostat` (the status): a loop that is off names the open items about its goal or the value it measures
  (`goal.x`, or its `stock.y` / `flow.y` / `auxiliary.y`), on its attention line (`· items about it: a, b, c +2`)
  and in its row of the loops table, **at most 3**, then `+N`; `unknown` when the index cannot be read. A loop that
  is not off names none. Under `--at` (a past snapshot) no items are named: the items open now are not the ones
  that were open then.

**Join.** A parent moved on by its children (fork-join) is a rule on the parent's kind, over the relation its children
name it by, not a block that lists and matches items:

```yaml
items:
  epic:
    states: [planned, underway, shipped]
    join:
      - {children: parent, any: [doing, review, done], to: underway}   # once one has started
      - {children: parent, all: done, to: shipped}                      # once every one is done
  ticket:
    relations: {parent: epic}
```

| Key | Type | Meaning |
|---|---|---|
| `children` | a relation's name | The relation its children name it by (on their kind: `parent: epic`) |
| `all`, `any` | a state, or a list (one of the two) | All of its children in one of these states (a join), or any one (the first to start) |
| `to` | a state of its own | Where it goes |

It fires on each move of a child, read from the item index (its moves, its links both ways), and once for every
parent when ergostat starts, so what moved while it was stopped is joined then. A parent with children, all (or any)
of them in the states, and in a state before `to` in its kind's order, is moved there by `ergostat.item.joined`
(`data.joined`: `to`, `children`, `all` or `any`, `n`, the children counted; folded only forward, so a parent that
went past `to` meanwhile, or was cancelled after it, stays), recorded by ergostat and caused by the
latest move of its children, so the Process view draws the join. It is a move like any other: counted (`entering`),
kept in the item's history. Never backwards: a child reopened leaves its parent where it is; a parent with no children
is never joined. Rules are tried in their order, each from where the one before left it. `check` says when no kind
names the parent by `children`, or a state is not one of theirs (`bad-join`, `unknown-state`), and, as a finding
(`join-side-state`), a side state (one its kind counts as finished, or named as an exit: `cancelled`, `closed`, ...)
listed before a join's `to`, which the join would move on. Each child's move costs a look at its parents' children
(their links and states): fine for tens of children, not tuned for thousands.

At a moment travelled to (the pages' time travel), the Graph and the Timeline show the items, their states, their
segments and their links as they stood then: an event at that moment counts as before it, an item made after it is
not there, and one made again since under its id shows its earlier self. They are read from the item index, each
item changed since folded again from the record up to then (`spec/asof.py`; when more than a tenth of the items, and more than 50, changed since,
the whole record up to then is folded instead), and each kind's time per state counts only the moves by then. Three things
stay of now: which states a kind counts as finished (as the item index says now, unless `messages: done:` says),
the completion estimates (none at a moment travelled to), and the status's list of relation cycles. A snapshot
(`ergostat snapshot`) holds the Items page's list with no kind chosen; each kind chosen alone, its list (the
first 500 of its items, as `items?kind=K` answers) and its list in each state it declares or counts; and the
Graph and the Timeline of each system's related kinds together and of each kind alone, related or not. An
answer that could not be got is left out, and the page says it is not in the snapshot. It also holds the item sets its own panels link to: each part's (a stock's, a
flow's, a sensor's side-panel set) and each node's and line's of every process map it holds (a node's `through`, a
related line's first end's `through`, a caused line's `caused`, any other line's `followed`, with the map's `by` and
span). Each is held both as the side panel lists it and as the Items page opened from its link shows it, at most 400
sets: parts first, then each map's nodes as the map lists them, then all the maps' lines by count, most first
(equal counts as listed). A set named twice is held, and counted, once; one past the 400, or one the server refuses,
is not held and says "not in this snapshot", as a set typed into the address does. The process map's other `by`
and the leased items a flow's panel links to are not held. The Process view draws relations too (§5b).

**Completion estimates.** Each open item's time to completion (a state its kind counts as finished, or a dead
letter) is estimated by a discrete-event **Monte Carlo over every open item together** (`numbers/eta.py`), from what
the record measured before now (`numbers/etamodel.py`: two weeks; every open item, and each kind's latest 2,000 items
for the fit; a stay that began before the record counts from its first move there, and relations are read as they
stand now):

- **The path** (a semi-Markov model per kind): each state's next-state shares from the items' moves, a lease's hold
  folded into the state it was taken from, rework loops kept; each kind's expected visits per state, the first row of
  the absorbing chain's fundamental matrix N = (I − Q)⁻¹, said in the Timeline's legend.
- **Time in a state** no block takes from: Kaplan–Meier over the stays that ended, the stays still going censored at
  their age; an item's residual life given its age there, S(a + t) / S(a); past the longest stay seen an exponential
  tail whose mean is the longest tenth's mean excess over the 90th percentile (every stay's mean when they are alike),
  so an item older than every stay seen is never given nothing left. A state with fewer than five ended stays takes its kind's pooled stays, then every
  kind's.
- **A state a block takes from** is a wait and a run: the item queues at the block in its `takes:` order (the states
  of `at` in order, then by when it came back to the state, so a nack's return goes to the back; with
  `unblocked: true`, those more items wait on first; with `order:`, by its fields before all of these: the
  dispatcher's comparator for the order fields and the states, so the projection takes them in the order the block
  will; among equals the dispatcher takes the least slack and the longest path ahead first, the projection those
  more items wait on, which agree on a chain but may differ between items of unequal durations). An item waiting in a state
  whose every block that takes from it is commanded off now (its gate shut, a switch at 0 or never read: worked out as
  the engine would from the newest readings) is projected not to move: no bar, its reason "waits for B, which is
  switched off now (by C)", at most the block's capacity at once: its pool now (its `pool:` number, or its stock's
  newest reading at or before the moment estimated, at most its `most`; a pool read as 0 or not read at all is
  estimated at 1, and each item waiting there says so: "its pool (stock.S) is 0 now: estimated at 1 run at once";
  the what-if `block.NAME.pool` overrides it), its agent's
  `at-once` and its daemon's `concurrency`, whichever binds (seats and daemons shared with the other blocks that use
  them), and its `workspace:` pool (§12k): a workspace taken at the item's first run of such a block is held by the
  item across every state until it finishes, so a pool of three keeps at most three items between that take and their
  finish; an item that would need one while all are held waits in the queue, holding nothing (the record's runs given
  back for want of one, "put off ten seconds, not counted", are that wait, never runs; who holds which workspace now is
  read from the workspaces' own events). A run's length is drawn from the block's run-time curve (Kaplan–Meier, the leases still held censored, so the
  long runs are not lost to those not yet ended), and how it ended from the recorded attempt nearest that long
  (bootstrapped per Monte Carlo run): moved on (to where), given back (its `after` kept: put off) or expired; a run
  past its lease's TTL expires at it. The last two return the item to the queue, its attempts counted, a dead letter
  after the most its terms allow. A
  block with fewer than five attempts on record runs an assumed one (its `every`, else a quarter of its TTL, at most
  ten minutes), said so; one whose state items have stayed in takes that stay's curve as its runs instead.
- **A leased item's** run is drawn the same way, given how long its lease has been held; past every run seen, the
  tail; never past its TTL. A failure share tried in the what-if reaches the runs already held too.
- **Dependencies:** an item does not leave its kind's first state, nor is it taken by an `unblocked` block, until
  every item its precedence relations name is finished (an item named but not in the record is not waited on).
- **Arrivals:** new items at the record's rate per kind (a batch brought in at one moment is not a rate), into the
  states they arrive in, competing for the same capacity.

200 runs at most, within five seconds (and the levelled run within as much again: ten at most), a fixed seed (each
run its own, so the same record gives the same estimates), 90 days ahead at most (past that: "beyond the horizon"). No
run finished within the budget: no estimate ("not worked out"); fewer than 20: no p90 is said, only the run count. Per item: its **p50** and **p90** finish, its
expected start, what it waits in now (a block, or a state), its place in that block's queue, and why, in words ("6
of 6 busy in dev; 34 ahead of it; a run takes 18m (median)"); per kind, when its last open item finishes (p50, p90).
The schedule the Timeline draws is the run whose last finish is the median's: never more runs in a block at once
than its capacity, each in a lane (leases held over a pool the what-if lowered keep theirs until they end). The Items page's list gives each open item's p50 (**done by**, the p90 beside it
and why in its title), and an item's page its estimate and why. Worked out in a thread, never on a page's request: a
page is given the latest, and the next is worked out by one worker (the latest asked for first; the eight used last
kept) when the record changed (at most every thirty seconds, and every
two minutes regardless); of now only (a moment travelled to has none), and not in a snapshot. The owner's what-if
(`block.NAME.pool`, `block.NAME.failure`: a share of its runs given back, `0.2` or `20%`; typed beside each block's
identified model) is worked out the same way, apart, and drawn on the same pages. The pages say what is left out
(below), how many runs, and which blocks' runs are assumed.

**What it leaves out**, and so what makes it wrong: a capacity no block declares (a reviewer who is one person across
two kinds, a rate limit), a goal that switches a block off (its
gate is not simulated: a block takes whenever it has room), a process that changed (the record's two weeks are taken
as how the work goes now), relations as they stand now, and a state never seen left (its items move to the next state
in their kind's order, assumed). **Validated** (`tests/test_eta.py`; `tests/eta_backtest.py` replays past moments,
estimates from the record before each alone, and compares with what happened): an M/M/c queue's mean wait matches
Erlang C within 12%; on three synthetic records of the owner's case (100 tickets brought in at once, a pool of six)
the p90 covers 89 to 94% of the items, the estimates' mean is within a fifth of the error of what happened, and the
p50's error is about a third of the median path's, whose p90 covered 36 to 42%. The components were kept by a
backtest with ablations (`docs/roadmap/overnight/eta.md`): a throughput cap measured from the record changed no
estimate, and was dropped. On the ticket-factory demo's record, with its workspace pool read as a capacity, the p90
covers every item.

**The Items page's views.** Beside **List** (each kind's items, newest first), the Items page shows, per system
group (or for the chosen kind), the kinds with relations and the items their relations reach, of any kind
(`GET /api/items-graph?kinds=A,B` or `system=NAME`; worked out again only when the record changes):

| View | What it shows |
|---|---|
| **Graph** | The items left to right, each after what it waits on (ELK, layered). A parent with children drawn (an epic) is a stadium its children hang off when nothing else they wait on is drawn; **By kind**, each kind is a frame instead. A card's left bar is its state, in the shade its kind's chart gives it; its border its status (active: the accent, breathing; queued: dotted; unblocked: ink; blocked: dashed, with how many it waits on; paused: dotted on a fill; done: faint, ticked; a dead letter: bad), and the run's block when one holds it. The critical path is drawn heavier, in the bad hue; other relations (a duplicate) dashed and named. **Frontier**: only the unfinished and what they wait on, however far back; **Collapse done**: the finished vanish, and a chain through them is one dashed line, "via N done". The search narrows it; a legend counts each status (a count clicked shows only that status, again shows all:
`status=` in the address) and says when the critical path is expected to end (until the completion estimates are worked out); a click opens the item |
| **Timeline** | A Gantt chart: a row an item (a parent, then its children under it), its bar its states over time, from its moves (what happened), and for the unfinished, faint bars ahead (what is projected: the completion estimates' levelled run, a wait in a block's queue a dotted line, a tick at the item's p50 and a whisker to its p90; before they are worked out, the forward pass), a parent's a bracket over its children's span. **Lanes** instead: a row a lane of each block that takes items, no more than its capacity, its projected runs in them. Arrows from each item to what waits on it; the critical path and its arrows in the bad hue; a now line; the legend says when each kind's last open item is done (p50, p90). Ctrl or cmd and the wheel zoom it about the pointer, a drag moves it, **Fit** shows it whole. The frontier by default, the finished kept as what happened |

Both stay as they are while what they show is the same (a refresh draws nothing), and are drawn again in place,
the reader's pan and zoom kept, when it changes. Bounded: 600 unfinished items of each kind asked, 400 finished in
the window, 400 more reached by relations (six links away at most), 300 cards and 200 rows drawn; a note says when
any was reached. The caps bound what is drawn, never whether an item waits: a precedence target cut from the graph
is read by id and its own status counts (one that cannot be read counts as unfinished, and is named). In a snapshot
they are not drawn.

**Built-in kinds.** Seven kinds are ergostat's own, present in every project and never declared (a project's
kinds may not take ids starting `ergostat.`): `ergostat.model-change`, every change to the model (section 12e),
`ergostat.claim`, what a block said it did, checked (section 12g), the owner's intent, `ergostat.decision` and
`ergostat.correction` (below), and `ergostat.message`, the owner's messages, routed to the work they concern
(section 12h), and `ergostat.verdict`, the intent judge's verdict on finished work (section 12i), and `ergostat.report`, a report
about ergostat itself, drafted and scrubbed for the owner to submit by hand (section 12m). ergostat may also
move any item: `ergostat.item.reopened` moves it to the state its data names (`reopened.to`, else its kind's first),
`ergostat.item.joined` to the state its join names (`joined.to`, *Join*),
`ergostat.item.follow-up` starts one (section 12h), and `ergostat.item.judged` sets its field `intent` (section 12i).
A kind a block takes (section 9.5) is moved by its leases too (`ergostat.lease.*`: to `leased`, back, or to `dead`),
and its items carry the field `lease`, ergostat's own.

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
kind matches is still shown, with its fields (folded with no rules) and no state. A built-in kind
may also say which states an event moves an item **from** (`ItemKind.moves_from`: event type to a
tuple of states): such an event moves the item only when its state at that point of the fold (in
the record's order, `seq`) is one of them; otherwise it moves nothing, and the item lists it in
`refused` with `form: "from"`. So a decision to move an item is made against its state where the
event lands, not where its writer last read it (the repair loop's failures, section 12r). It is
not written in a model's YAML.

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
(unless a type or the item is asked for), and the Process view (§5b). A fold reads them when its kind moves on
a `claude.*` type, or when a sensor's `where:` or a column names a field they fold into. The item's
own page and `ergostat item ID` fold them all. A session of 2,000 lines is recorded in well under a
second, and leaves a count of sessions as fast as it was.

Items are counted by sensors (section 6): a stock may be the number of items in some states, and
a flow the rate at which items enter or leave one. The record is then the instrument: what is
counted is what the events say, so a stock counted from items is only as true as the events
reporting them.

**Which items: what is going through the wires.** A stock's or a flow's side panel (in every view; in the
Blocks view, a loop's output, sensor and process blocks) lists its items, the first ten, and links to the
Items page filtered to exactly that set (`item_sets.py`). What a part's items are comes from the model:

| Part | Its items |
|---|---|
| a stock or auxiliary with an `items:` sensor | the items it counts now: its kind, `state` and `where`; each with its age in its state and the lease holder |
| a flow with an `items:` sensor | the items whose move it counts (`entering` or `leaving`, `where`) in the page's window, each with when |
| a flow between stocks counted from items of one kind | the items that moved from the source stock's states to the target's in the window (a side outside the system: any other state, or arriving) |
| a flow moved by a block (its valve) | each opening in the window, with the items the run that opened it was about |
| a flow whose `run` sensor reports items | the items it reported in the window |
| anything else (a query, a declared rate, `changes`, read by hand) | none, and why: a rate from a metrics store names no items |

The Items page's filters, in its address (`/items?...`) and in `GET /api/items`:

| Parameter | Meaning |
|---|---|
| `kind` | the kind; every other filter needs it |
| `state=A[,B]` | in one of these states now |
| `where=FIELD:VALUE` | the field equals the value (repeated: any of the values for one field, all the fields) |
| `moved=FROM>TO` | moved from one of `FROM` to one of `TO` (states joined by commas); an empty side is any other state, or none (an arrival): `>done` entering done, `briefed>` leaving briefed |
| `moved_since`, `moved_until` | the span of `moved` (after since, up to until): `2026-11-18T10:00:00Z` (UTC) or seconds since 1970; default the hour before now |
| `remote=NAME` | a remote's items instead, asked there within its budget (§4c, *Its items and events in the pages*); with it only `kind`, `state`, `n` and `offset` |

The page shows the set as one chip with its count (for moves, the items and the moves), removed with its ×;
each item's latest matching move is a column. The API answers the set alone, newest first (a move's set by its
latest move), at most 500 a page (`n`, `offset`), with `total` (and `moves`); `alone=1` leaves out the page's
kinds and counts. A filter that is not one (an unknown state, `where` without a `:`) is a 400 that says why.
Sets are read from the item index: a state's items counted and paged there, a span's moves read there alone.

## 5b. The Process view: how the items really moved

The Diagram page's third view, beside Dynamics and Blocks, draws the work as the record says it went:
process mining's **process map**, a **directly-follows graph** (DFG; van der Aalst, *Process Mining:
Data Science in Action*; the map Disco and Celonis draw), **object-centric** (van der Aalst's
object-centric process mining, OCEL): one map per kind of item, and between the maps the lines where
work on one kind caused work on another. Nothing is declared for it: it is read from the record in the
page's window (`process.py`), with the item index's moves for the states.

| Part | What it is |
|---|---|
| a node | an **activity** of a kind's items: by **States**, a state they entered (a move, from the item index; a lease's hold, `leased` (§9.5), folded out as the index's transitions fold it: the time held counts in the state it was taken from, and a lease handed back is no move); by **Events**, an event type about them. Its number is how many times in the window, and how many items; the more, the darker |
| start, end | where the kind's items **start** (their first event is in the window) and **end** (they reached a state the kind counts as finished, as §12h's `done` or the item index says; `leased` never counts) |
| a line A → B | **directly follows**: on one item, B came next after A with nothing about that item between. Its weight is how often (one scale for the map); its number how many times (**Counts**) or the median time between A and B (**Times**). By States, a move from A to B is such a line, its time the time spent in A, even when A was entered before the window |
| rework | a line from a later step to an earlier one (by States, in the kind's declared order of states; by Events, by each type's usual place in its items' runs), or round to the same step: marked ↺, and laid out running back |
| a dashed line between kinds | **caused**: an event on an item of one kind caused (`causedby`, followed up through events about no item, such as a block's run, up to four steps) an event on an item of another kind; aggregated by the two activities, with the event types under it. One into many is a fan-out, many into one a join |
| a schedule | where a scheduled run's events come from: a cause followed up to a run a block started on its own schedule (`every:`, `cron:`; its `agent.started`, `"trigger": "schedule"`, caused by nothing) ends there. The run is the cause its events cite, so no event of its own is recorded for a firing. Drawn in a frame of its own, **schedules**, a node per block (a clock, its name and how often; its number, how many of its runs caused something), with a dashed line to each activity its runs caused, its fan-out; its items `caused=ergostat.schedule:BLOCK>A` |
| a dotted line, named | **related**: an item names another in a relation its kind declares (§5a, *Relations*: `parent`, `blocked_by`), both drawn: from the activity the naming item was last at in the window to the one the named item was last at, aggregated by the relation and the two activities; its number how many links. Read as the links stand now; a link to an item not drawn is no line |

**Which.** The kinds are the system's being viewed (`item_systems.py`: where each kind belongs); for
everything, every kind but ergostat's own. The ⋯ menu chooses any of them. **States** is the default when
every kind drawn declares states: the states are the workflow as the owner wrote it, with the names the
stocks counting them use, so the map is held directly against the model (an event that moves nothing, a
comment, a transcript's line, is left out); a kind without states is drawn by its events. **Events**
draws every event type about the items (a transcript's lines, a lease's renewals and roll-ups aside): what
happened between the moves, and loops on one step.

**The paths slider** (in the view bar) hides the lines rarer than its share of their kind's most frequent
(the lines between kinds, of theirs), and the nodes it leaves alone, as process mining tools' slider does;
the side panel says how many were hidden. The related lines to a remote's items (§4c) are not subject to it.

**Bounded.** The newest 50,000 events in the window are read, the moves of at most 20,000 items (the
latest moved), and the 60 most frequent nodes and 160 most frequent lines drawn; the side panel says when
any was reached. The answer is kept for five seconds.

**Held against the model.** `check`'s coherence (§12l) compares this map with the Dynamics and Blocks views:
each move it draws against the chain's flows, and who made each against the blocks that declare it.

**Layout.** Each kind's map is laid out alone by ELK (layered, left to right, in time order: its start
first, its states in their declared order, its end last), in a frame named with its kind, how many items
and by what; the frames are packed in rows to the screen's shape. The lines between kinds are routed by
libavoid around every part, from the bottom or top of their ends. Plain ink: no colour carries meaning.
A node dragged (or the nodes chosen), or a kind's frame dragged by its top, is pinned where it is put, as in
the other two views (DESIGN, "Parts put by hand"): no new layout, the lines it touches routed again by
libavoid. The Process view keeps its own pins, each node's from its kind's frame and by its kind and
activity, so the same in States and in Events; "Unpin all parts" (⋯) lets the layout place them again.

**Clicking.** A node or a line opens its panel: what it is, its count and median time, the lines into and
out of a node, a cross-kind line's event types; and the items behind it, the first ten, linked to the Items
page filtered to exactly them. The Items page's (and `GET /api/items`') filters for these, read as the map
read them:

| Parameter | Meaning |
|---|---|
| `through=A` | went through activity A in the span (`^`: started, `$`: ended) |
| `followed=A>B` | B directly followed A on the item in the span (`^>A`: started with A; `A>$`: ended after A) |
| `caused=KIND:A>B` | B on the item was caused by A on an item of KIND in the span (repeated: any of them) |
| `by` | `states` or `events`: what A and B are |
| `moved_since`, `moved_until` | the span, as for `moved` |

`GET /api/graph?view=process` answers the map (`kinds` joined by commas, `by`, `paths` as a percentage, and
`system`); `view=wiring`, the view this replaced, is the same, and the page's `view=wiring` opens it. (The
machines and what passed between them, which the wiring view drew, are on the command line: `ergostat
system --wiring`.)

## 5c. Pushed, not polled: events sent to the running ergostat

What arrives from outside may be **pushed** instead of waiting for a collector's next poll: recorded and folded at
once, and what waits for it (a block that takes the item, a goal on its queue, a step put off until there is news of
it: section 9.5) wakes on the write itself. Collectors stay as they are, the fallback for what nobody pushes.

**`POST /api/events`** on the running ergostat's page (`ergostat run` prints where): one event, or a list, in the
envelope a block's output lines use: `{"event": "ticket.found", "item": "ticket/SCRUM-12", "data": {...}}` (or
`patch` / `set` in place of `data`), with an optional `id` that makes a retry the same event (recorded once). An `id`
starting `cite:` is refused: it is a mirror's own, recorded only by the sensor it names (section 2, *Mirroring an
outside log*); so is one from a webhook's `id:` or from `ergostat event` sent to the engine. A push is checked
whole and recorded in one write, or refused whole (400, and why). The answer says how many were new and their ids.
An event type is lowercase words joined by dots, never ergostat's own.

**Webhooks, `POST /api/hooks/NAME`**: a sender's own payload, made into events by a small mapping per sender:

```yaml
intake:
  allow: [10.0.0.0/8]                  # who may push besides this machine (default: nobody else)
  bind: 0.0.0.0                        # where the page listens (default 127.0.0.1); others reach only the push paths
                                       # (allow: and bind: are this machine's: they may go in ergostat.local.yaml, §2)
  hooks:
    jira:                              # POST /api/hooks/jira
      event: {from: webhookEvent, map: {"jira:issue_created": ticket.found, "jira:issue_updated": ticket.changed}}
      item: "ticket/{issue.key}"
      id: "jira-{issue.id}-{timestamp}"
      data: {title: issue.fields.summary, status: issue.fields.status.name, labels: issue.fields.labels}
    github:
      event: {from: "header:X-GitHub-Event", map: {pull_request_review: ticket.news, check_suite: ticket.news}}
      item: "ticket/{pull_request.head.ref~^ergostat/([A-Z][A-Z0-9]*-[0-9]+)}"
      id: "{header:X-GitHub-Delivery}"
      data: {news: action, review: review.state, ci: check_suite.conclusion}
    pagerduty:
      event: {from: event.event_type, map: {incident.triggered: alert.triggered, incident.resolved: alert.resolved}}
      item: "alert/{event.data.id}"
      id: "{event.id}"
      data: {title: event.data.title, urgency: event.data.urgency, service: event.data.service.summary}
```

`event` is a type (a template), or a value in the payload looked up in `map` (one not in the map is ignored: 202,
nothing recorded). `item` and `id` are templates: text with `{path}` in it, a path being dotted keys
(`issue.fields.summary`), list positions by number (`pull_requests.0.number`), or `header:NAME`; `{path~REGEX}`
takes the part of the value the expression's first group matches. Each of `data`'s fields is a path (its value as it
is) or a template (text). `each: PATH` makes one event per element of a list. An item a payload does not name is
refused (400).

**Who may push.** Every push carries the project's token, `<state>/intake.token` (made the first time, readable by
its owner only), in any of the ways a sender can: `Authorization: Bearer TOKEN`, `X-Ergostat-Token: TOKEN`,
`?token=TOKEN`, or as the secret of an HMAC-SHA256 of the body the way GitHub (`X-Hub-Signature-256`; Jira's
webhooks with a secret too) and PagerDuty (`X-PagerDuty-Signature`) sign theirs. Pushes come from this machine
only, unless `intake: allow:` names more; another machine reaches nothing of the page but the push paths. A sender
outside reaches it through whatever forwards to this machine (a tunnel, a reverse proxy).

**Calls from a step.** The engine also listens on a Unix socket in the state directory (`engine.sock`, its owner's
only; when that path is too long for a socket, one in the system's temporary folder, named in `engine.sock.path`),
given to every run as `ERGOSTAT_SOCKET`. `ergostat event --add`, `act`, `lease --renew` / `--nack` and `item ID
--json` are answered there when an engine runs, in milliseconds and without loading the model, and do what they
always did when none does (`ERGOSTAT_NO_SOCKET=1`: never ask it). The protocol is one JSON line asked and one
answered, so a step's own code may speak it with no ergostat installed: `{"op": "event", "events": [...],
"causedby": RUN}`, `{"op": "item", "id": ID}`, `{"op": "act", "name", "args", "key", "wait", "env":
{"ERGOSTAT_ACTIONS": ..., "ERGOSTAT_RUN": ...}}`, `{"op": "lease", "how": "renew" | "nack", "why", "after",
"count", "env": {...}}`, each with `"root"`, the project's folder (another project's call is not answered:
`{"elsewhere": ...}`). An answer is the command's `--json` answer, or `{"error": WHY, "code": EXIT}`. An `act` that
waits for an approval holds no thread: it is answered when the owner answers.

A run's call (`ERGOSTAT_SOCKET` set) survives the engine restarting: while no engine answers (no socket, a refused
connection, or one closed before its answer), it asks again with backoff for `ERGOSTAT_CALL_RETRY` seconds (default
120, at most 3600), then does what it does with no engine. A command from a shell does not wait. It does not wait
where the run's state folder (`ERGOSTAT_STATE_DIR`, or the socket's own folder) is not on this machine, and once
the socket is removed it waits 10 s at most for it to be made again. Only a final stop removes it: `ergostat run`
starting itself again in place under the same name (a change of storage or format, or the watchdog's restart) leaves
it, as a killed engine does, so its calls wait the whole bound for the new engine; a new name is a new state folder,
so that restart removes it. Over-long keys are hashed, never cut short. Each call carries a
key, `"call"`, made once by the command, the same on every try and in what the command records itself when it falls
back: an event it records without an `id` of its own is given `call-KEY.N`, a lease's
renewal or nack `call-KEY`, so a call recorded just before the engine stopped is not recorded again (its answer is
the event recorded the first time); an `act` with
no `--key` from a run with no item is keyed by it, so one held for the owner is asked once (a run with an item already
finds its held action again, by its action and arguments). An `act` asked again after a restart waits for its `wait`
again, from when it is asked.

## 6. Sensors

An instrument: it measures one stock or one flow, and nothing else. It never decides or acts. It
is written inside the stock or flow it measures. Exactly one of `run`, `query`, `manual`, `items`,
`changes`, `builtin` or `daemon`:

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
| `run` | command | | A command whose output is the reading: a bare number, or JSON `{"value": n}`. Run in the model's folder; its environment carries `ERGOSTAT_CMD`, `ERGOSTAT_PROJECT`, `ERGOSTAT_STATE_DIR` and (when the engine has one) `ERGOSTAT_SOCKET`, as a block's run does (section 9.3), so a collector can read the items with `$ERGOSTAT_CMD item --kind K --json` |
| `query` | map | | A query against a source (section 11): `source` and the source's own fields |
| `daemon` | map, or a name under `daemons:` | | Read by a long-lived process (section 9.7): each reading asked as a line on its schedule, no process started per reading; several sensors may name one daemon |
| `push` | bool | false | With `daemon`: the daemon sends its readings by itself (`{"reading": V, "sensor": "STOCK.SENSOR"}`); none is asked for |
| `manual` | bool | | Readings recorded by a person |
| `items` | item kind | | Counted from the record: on a stock, the items in `state` (any state when left out); on a flow, the items `entering` or `leaving` a state per hour, over `over` |
| `state` | state or list | any | On a stock: which states count |
| `measure` | `count`, `oldest` or `age` | `count` | On a stock: how many; the hours the oldest of them has been in its state; or the hours since the oldest of them was first seen, whatever states it passed through (an item taken, given back and taken again keeps its age: a commitment's clock) |
| `entering`, `leaving` | state | | On a flow: exactly one; the move it counts |
| `sum` | field | | On a flow's `items`: the rate per hour of this field summed over the items moving (a number; else 0), not how many moved. `model-mended` sums each written change's `fit_gained`, what Accept measured it took off the error |
| `changes` | `rises`, `falls`, `net` or `rest` | | On a flow into or out of one stock: its rate from that stock's own successive readings, how much they rose (an inflow), fell (an outflow), or both, net, in the flow's direction (a `two-way` flow), per hour over `over`; `rest` (two-way, one a stock): the net change less what the stock's other measured flows moved, each at its last reading (the residual flow). Every rise or fall is whatever caused it: a flow so measured that is drawn as caused by another flow is the finding `measured-not-caused` |
| `over` | duration | `1h` | On a flow: the window the rate is taken over |
| `builtin` | `ergostat.model.fit`, `.unexplained`, `.unidentified-loops` or `.open-findings`; `ergostat.upkeep.*` (`index-files`, `retired-index-files`, `heartbeat-age`, `stalls`, `restarts`) | | On a stock or an auxiliary: one of ergostat's built-in measures of the model's own quality (section 12e) or of its own upkeep (section 2a, *Upkeep*), read by ergostat itself (`ergostat measure ergostat.model.fit`, in a process of its own; `timeout` 2m by default) |
| `averages` | duration | none | On a flow's `run`, `query` or `manual` sensor: its reading is the average rate over this window before it (a count of the last ten minutes, per hour: `averages: 10m`). The model's rate is read through the same window before it is compared (section 12b) |
| `where` | map of field → value (or list) | | Only items whose fields match; a field's field is named with a dot (`lease.back: triage`: the items whose lease was taken at `triage`, section 9.5). Values compare as typed JSON: a number matches a number (`1` matches `1.0`), a string a string, a boolean a boolean, `null` a field that is null or missing, so `priority: 1` never matches the text `"1"` (write it quoted when the field holds text). *Decided* (2026-11-18): before, both sides were compared as text, so `1` missed a field holding `1.0`; `check` notes each bare number or boolean in a `where:` (**where-typed**) since its meaning changed. The same holds for a block's `takes: where:` |
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
A sensor read by a daemon may print the same lines tagged with `"sensor": "STOCK.SENSOR"` (section 9.7).

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
| `rate-unit` | `minute`, `hour`, `day` or `week` | chosen by size | How its rate is shown (section 1a): display only; its `rate`, equation and readings stay per hour |
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
| `per` | `item`, or a field | none | On a stock counted from items (an `items:` sensor): held by each item (`item`, by its own measure: its hours in its state for `measure: oldest`, since first seen for `age`), or by each group of the items by what a field holds (a relation such as `parent`: each id it names; an item with nothing there is in no group): each group's count, oldest or age. Below |
| `on-stale` | `act`, `hold` or `off` | none (not watched) | Watched for staleness, and what it does while its reading is stale (section 9.6): worked out from the stale value as if it were current; its `.error` and `.off` kept as they were, so what it commands is kept; or counted as off (`.off` is 1, its error the last one). Its status shows `stale` under each |
| `system`, `description` | | | |

A goal exists whether or not anything serves it. A goal nothing serves is **missing feedback**.

**Per item or per group.** "No ticket in review older than two days", and "each epic's open tickets at most 10":

```yaml
stocks:
  review-age: {unit: hours, sensor: {items: ticket, state: review, measure: oldest}}
  open-tickets: {unit: tickets, sensor: {items: ticket, state: [todo, doing, review]}}
goals:
  review-fresh: {stock: review-age, hold: "<= 48", per: item}
  epics-small: {stock: open-tickets, hold: "<= 10", per: parent}
```

The goal is still about one stock. Its value is the worst item's or group's (for `<=`, the greatest), worked out from
the item index each time the stock's sensor reads, and as it stood at any moment the pages travel to; it is off while
any breaks the setpoint (its `tolerance` as usual), and its `loop.off` names those that do (`breaking`: the worst
20, each `{item}` or `{group}` with its `value`; `breaking_n`, how many). A block serving it is given the same in its
context (`goals.NAME`: `value`, the worst; `per`, `breaking`, `breaking_n`), and the loop's panel and "needs
attention" list them. A setpoint an outer block sets (a cascade) holds each item or group. With no items (no
groups), nothing breaks it and it holds: its value is 0, or the setpoint itself where 0 would break it (a floor on
each item's age). A group is only what its items name: an epic with no open ticket is no group, so a floor on each
group's count could never be broken, and `check` refuses it, as it refuses `per:` on a goal not on a stock counted
from items and `per: item` on a count (**goal-per**); it notes a `per:` naming neither a relation nor a field the
kind shows, folds or the sensor matches (**goal-per-field**). The items are read from the item index again only
when the record changed; their hours are worked out again at each reading.

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
| `on-stale` | `act`, `hold` or `off` | Watches what it reads directly (a stock, flow or auxiliary, or a goal), and says what it does while that is stale (section 9.6; none: not watched): as before (`act`); keeps its last command (`hold`: a built-in is not stepped, a machine block is not started); or sees the goals it reads as off (`off`). A machine block's `goal:` passes it to the onoff it implies |
| `system`, `description` | | |

Every block has an output. A block with none has no visible effect: either it does nothing worth
modelling, or the flow it changes is missing from the model; `check` reports it.

A machine block's output lines take effect as its run prints them, not when the run ends (section 9.1), so a
long run's findings land one by one.

### 9.1 How blocks run

- **Built-in blocks** (9.2) are executed by ergostat itself, on every reading of their inputs:
  no program, no machine. They are how ergostat closes loops by itself.
- **Machine blocks** (9.3) run a program, an AI prompt or a request to a person. They run:
  - when an input commands them (the input becomes nonzero, or a new command arrives);
  - on their own schedule (`every`, `cron`), when nothing commands them: an open loop; or
  - when an event of a type they name is recorded (`on:`, section 9.3): a run for each.

  A machine block never runs twice at once. A command that arrives while it is running is held,
  not queued (anti-windup): the latest command is used when it finishes. Without an `agent`, a
  machine block runs locally, launched by ergostat.
- **Machine blocks that take items** (`takes:`, section 9.5) run once per item instead: a run for
  each item that reaches a state, several at once up to their `pool`, each holding a lease on its
  item. Commands to them are signals and are held; items are queued.
- **External blocks** (`type: external`) are performed by something ergostat does not run (an
  autoscaler, a Kubernetes controller, a team). They are declared for the structure: their
  inputs and outputs are what that thing reads and moves, judged by the stocks' and flows'
  sensors.

**Readings and passes.** ergostat reads its sensors on their schedules, and works the loops out again in a **pass**
after readings land, after a run ends, and every second (the clock's pass):

- Readings are taken in **batches**: those due together, and those a run asked for when it moved a flow, are begun
  together; counts of items are read from what ergostat keeps as the record folds (an `items` sensor's value is its
  count at the reading's time, kept as events arrive: it costs nothing to read), a flow read from its stock's changes
  is worked out at once, and commands and queries run on a fixed pool of eight. The batch is recorded together and
  followed by one pass. What lands within 50 ms of a pass (readings, runs ending) waits for the next pass together.
- When the record is written (by ergostat, a run, a push, or another process: each wakes it), every count of items
  is read at once, and those that changed are recorded and worked out with the batch: a goal on a queue sees its first
  item when it arrives, not at its sensor's next reading. A count that did not change is not recorded again.
- A pass reads **one snapshot**: each series' newest reading when the pass begins. Readings that landed in one batch are
  seen together; a series read twice within one batch counts with its newest reading (the other is recorded, not
  evaluated).
- A pass works out **what changed**: the parts with a new reading, the goals on them, the built-ins that read
  what changed (in the built-ins' order, as always), and the machine blocks commanded by what changed, whose stocks or
  goals have a new reading, or whose run ended. The first pass after ergostat starts or the model changes works out
  everything. Built-ins whose output can move with time alone step at every pass: every `delay`, `timer` and
  `schedule`, an `onoff` with `min-on`, `min-off` or `until`, an `alarm` with `for`, a `counter` with `reset`, a `limit`
  with a `rate`.
- What only time makes due is seen at the clock's pass: a block paced by `every` whose pace has run out starts at the
  next whole second, as does a block a step test stops holding.
- The events a pass makes (`loop.off`, `loop.holding`, `controller.decided`, `person.asked`, `block.advised`) are
  recorded in the order it made them, together, before any run it starts.
- An event about an item counts in the item counts at once, even when stamped later than the reading (another
  machine's clock ahead of this one).

A machine block receives on standard input (or, for `ai`, in its prompt):

```json
{"block": "worker", "command": {"amount": 12, "from": "keep-short"},
 "inputs": {"stock.inbox": 32, "goal.inbox-short.error": -12},
 "goals": {"inbox-short": {"hold": "<= 20", "value": 32, "error": -12, "status": "off"}},
 "trigger": "command"}
```

and reports on standard output, one JSON line per output, or a bare number when it has a single
output. Its lines take effect **as it prints them**, not when it ends (below): a program that works for hours may
report each finding as it makes it.

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

**Lines take effect as they arrive.** A run's standard output is read while it runs, line by line, and each
complete line is taken when it is printed, in the order printed; half a line waits for the rest (or for the end of
the output). Its input is written, and its errors go to its log, beside the reading, so neither a large output nor
a program that reads its input slowly stalls it. **A run outlives its engine:** it starts in its own session, its
input is a file and its output goes to its run log file (`runs/RUN.out` in the state folder), which the engine
follows (looking again within 50 ms when nothing is new), so no pipe ties the run to the engine: an engine killed
mid-run leaves the run going, and a small `sh` wrapper writes its exit code to `runs/RUN.exit` when it ends.
`runs/RUN.json` is its record: pid, the process's start time (a pid reused by another process has another start
time), run id, lease and block. The files are removed once the engine has read the run to its end. (Taking up a run
left behind by a stopped engine is not built yet.) A run has ended when its process has and nothing it started is
left in its process group, or 2 s after its process ended, whichever is first. **Its exit code is the wrapper's**,
and `sh` reports a command killed by signal N and one that exits with 128+N alike, so the wrapper chooses: for HUP,
INT, PIPE, ALRM, TERM, USR1, USR2 and KILL it ends itself by the same signal, and the run's exit reads -N (as a
simple command's did before the wrapper); for every other code it exits with the code itself, so a run killed by a
signal that dumps core (SEGV, ABRT, QUIT, ILL, BUS, FPE, TRAP, SYS, XCPU, XFSZ) reads 128+N, e.g. 139, never
crashing the wrapper. The cost: a command that *exits* 129, 130, 134, 137, 139, 141, 142, 143 or another such code on
purpose reads as ended by that signal (section 12's triage files both as `signal`). Event lines in a row are recorded together, in one write, before
anything printed after them, so a run printing thousands of lines a second costs a few writes. A program flushes
each line for it to be seen at once (`print(..., flush=True)`, `python -u`; `echo` and `jq -c` in a shell already
do); what it holds in its own buffer arrives when it flushes or ends. By line:

| Line | When it takes effect |
|---|---|
| `{"event": ...}` | At once: recorded, caused by the run (`causedby`), and folded into its item; it renews the lease its run holds on that item, and is refused at once once that lease has ended (section 9.5) |
| `{"decision": ...}`, `{"answer": ...}`, `{"route": ...}`, `{"propose": ...}` | At once, as when the run ended before |
| `{"out": ..., "moved": n}` (a flow) | Its valve opening (`valve.opened`) at once; the run's total (`moved` on `agent.ran`) and the reading of that flow's stocks after acting, when it ends |
| `{"out": ..., "command": n}`, a goal's setpoint, an auxiliary's value | At once: what it commands may start before it ends, and a later line replaces an earlier one, as commands always do |
| `{"claim": ...}` | Recorded at once; checked after the run ends, against its exit code and what it did (section 12g) |
| `{"nack": ...}` | Noted at once; its item is given back when the run ends (section 9.5) |
| A bare number (or what `parse:` finds) | When it ends: the last one printed, and only from a run that exited 0 and printed no JSON line |
| Anything else | Its log, as it arrives |

A run stopped part way (its timeout, the owner's `--stop`, ergostat stopping) keeps everything it printed before it
was stopped: what it recorded stays recorded, what it moved counts. Equally for `program` blocks and `ai` blocks
with `run:` (an `ai` block's own `claude -p`, and the session helper, `ergostat session`, print their result lines when the session ends; the session helper copies the transcript as it grows).

**When the model changes** (`ergostat.yaml` or a file it includes edited, or a change to the model accepted), a running
ergostat takes the new model **in place, at run boundaries**: it never restarts and never kills a run for it.

- A run under way carries on to its end under the model it started with: its block's definition, its command, its
  timeout. Each run records the model's version it started under (`model` on `agent.started` and `agent.ran`, a short
  hash of the dynamics, the control and the measurement together; `model_now` on `agent.ran` when the model changed
  while it ran), and its output is taken against that version. An output to a part the model no longer has is
  recorded and refused (`agent.refused`: no longer in the model), never a crash.
- New runs start under the new model. A block removed, or whose definition changed, lets its run under way finish
  and starts no more under its old definition; `ergostat block NAME --stop` stops that run when the owner asks
  (recorded as stopped as the owner asked, not as the block's failure).
- Goals and sensors switch over at once, bumplessly: a goal's new setpoint holds from the next pass (each second), a
  sensor's new definition from its next reading, and a schedule keeps its time unless its new `every` is shorter. A
  built-in block written the same keeps its state; one changed takes over the state of the one before it (a
  counter's count, a timer's start, a delay's line) when it is of the same type.
- `model.changed` records it, with how many runs carried over (`carried`, and which: `runs`), the version before
  and after, and the blocks still finishing under an old definition (`finishing`: `removed`, `changed`). A YAML
  model's `model.changed` also carries each system's interface as a short signature (`interfaces`: system → a hash
  of its ports' direction, kind, part and peers). An event is recorded when only the interfaces differ, with the
  systems whose signature differs, appears or disappears (`interfaces_changed`, listed only when the event before
  has `interfaces` to compare). With the parts and the version unchanged, such a change comes from how ergostat
  works out interfaces (an upgrade), not from an edit to the model. The first time a model with a record from
  before interfaces were kept is loaded unchanged, one event with `baseline: true` records them; like `first`, it
  is not a change (`status --since` leaves both out). A TOML model records no `interfaces`.
- **Only once the edits settle** (`ergostat/reload.py`): a change is taken once the model's files, and the folders
  holding them, have stayed the same for 1.5 s (`ERGOSTAT_RELOAD_SETTLE`). A burst of writes is one change, and a file
  read half written (truncated, then written in pieces, as an editor or an agent saves it) is never taken.
- **Never a model with errors.** A model that does not load, has errors, or whose main file is empty is not taken:
  the last good one runs on, and "the edited model has errors (`file:line`); still running the last good version"
  is said in the log (with every error), at the top of `ergostat status` (with every error, even when the files do
  not load at all) and in the page's header, from `<state>/reload.json`, until the files are fixed. The same files
  are not read again until they change. `run --stop` and `run --service --uninstall` work while they do not load
  (the state folder found without the model).
- **The command line on the last good model.** Every file the model's loading reads goes through one place
  (`ergostat/spec/files.py`): the main file, its includes and what each glob matched, prompt files, the library's
  templates (ergostat's own too), remotes' cached models, and every file it looked for and did not find. When the
  engine takes a model (at start, and at each change it takes) it keeps that model whole as one snapshot, in
  `<state>/good/`: each file's bytes once, by their SHA-256 (`objects/`), and `manifest.json` (replaced atomically)
  naming every path with its hash, every path found missing and every glob with its matches. A snapshot is kept only
  when it reads back clean from itself. While the files do not load, a command that only reads (`status`, `item`,
  `event`, `lease`, `loop`, `system`, `explain`, `findings`, `residual`, `fit`, `claims`, `messages`, `agent`,
  `block`, `inbox` and the parts) loads that snapshot **alone**: every read, glob and existence check answered from
  the manifest, never from disk, so it is the model the engine took and never a mix with files edited since; a path
  the snapshot does not hold, or a kept file whose bytes no longer match its hash, fails the fallback, saying which
  path (and `ERGOSTAT_LIBRARY` when it differs from when the snapshot was kept). While it loads, in the loading
  thread, nothing may be opened or globbed in the model's folders and no process or connection started (a Python
  audit hook refuses them; a `stat` or a folder listing is not hooked, so these rest on every read going through
  `spec/files.py`). The snapshot is of loading only: what a command reads after the model is loaded, a prompt's text
  for a run or the parts a context recipe includes, is read live. The model keeps its real paths, so the project is
  the repository's, and its record is opened read-only: any write to the events or measurements is refused, so a
  path that acts is refused whatever its flags. One line on standard error names the YAML's first error and when the
  model was taken; `status` also shows "the edited model has errors (`file:line`); shown with the last good
  version". A command that acts (every other topic, and these with an acting flag: `event --add`, `block --now`,
  `lease --nack`, `inbox --approve`, `inbox --requests`, `sensor --read`, ...) refuses with the YAML's errors and
  "ergostat TOPIC acts, so it never runs on the last good model", except that while an engine runs, `event --add`,
  `lease --renew` and `lease --nack` go to it over its socket as always, without loading the files, so a run's
  findings and leases are kept through an edit. With no snapshot kept, a broken YAML is refused as before; `check`
  always reports the edited model's errors. The snapshot's objects are kept one generation past the snapshot that
  names them, for a command reading it as it is replaced.
- **Atomic.** The new model is worked out whole (its built-ins made, its version hashed) before anything of the
  running one is touched: a change that cannot be taken leaves the last one running as it was.
- **Timed.** The log gives each change's time; one slower than 2 s says where it went (reading and checking the
  files, taking it in place, recording it).
- The page follows the files the same way, and reads a change in one request while the others answer with the model
  it had.
- A change of the model's name, of its format (TOML to YAML) or of its storage is a new state directory or store:
  that one restarts in place, and stops the runs; a restarted runner whose files were edited again meanwhile waits,
  holding its lock, for a model that runs. `ergostat run --stop` (and any explicit restart) stops everything, as
  always.

**The watchdog** (`ergostat/spec/watchdog.py`). Inside the engine, once a second: when the sensor pool has given
nothing back for 30 s while readings are out (`ERGOSTAT_STALL`; or the longest timeout of the readings it has begun,
and 10 s more, when that is longer: one still queued never lengthens it), a fresh pool takes over and the readings it held are asked for again; when no pass has
finished for 30 s, the loop is started again; when there is still no pass 30 s after that, or the pool wedged three
times in ten minutes, the process restarts in place (by the run loop, or by the watchdog itself if that has not
happened within 20 s), which stops the runs under way (leased items are taken again when their leases end, the
attempt not counted). Before it waits on the daemons' groups it closes dispatch as stopping does (its stop set under
the lock a take checks it under, waiting at most 1 s for that lock): no lease is taken in that wait, and a run whose
process starts from then on is killed at once, so no run of an item outlives the old process to run beside the new
one's (one exception: a run whose process is being forked at the very moment of the exec). Each
time every thread's stack is written to `<state>/stalls/` and `ergostat.engine.stalled` is recorded (`what`: pool or
pass, `seconds`, `recovery`, `stacks`); the stacks begin with what holds the item index (the thread holding its lock,
with its stack, and any other process with the file open). **Restarts back off** (`ergostat/restarts.py`): the first
is at once, but one wanted soon after the last (within 10 minutes, or twice its own wait) means the last did not help,
and it waits 60 s from it, then 2 m, 4 m, ... at most 30 m, said once and recorded as a stall, while the cause lasts;
the engine recovering meanwhile cancels it. The last restart is kept in `<state>/restarts.json`, so the back-off
outlives the process. **A start that hangs** (a lock held by another process, say) is caught by a startup deadline
(120 s, `ERGOSTAT_STARTUP`): its stacks dumped (`stalls/*-start.txt`) and the process restarted under the same
back-off. Every 5 s the watchdog writes `<state>/heartbeat.json` (when the last pass finished, the pid, and under
`use: upkeep` the `stale` the outer watcher uses), and the run writes it as it starts. The alarms' own sensor pool
is watched as the sensors' is: replaced when wedged, and a third time in ten minutes restarts the process. `kill -USR1`
on the runner writes every thread's stack to `<state>/threads.txt` at any time, and the socket's `ping` says how long
ago the last pass finished.

**The outer watcher** (`ergostat/watcher.py`). The engine cannot restart itself when it is killed or frozen whole.
`ergostat run --service` prints, for the machine's service manager, a user LaunchAgent
(`~/Library/LaunchAgents/local.ergostat.<name>-<hash>.plist`, `KeepAlive`) on macOS or a systemd user unit
(`~/.config/systemd/user/ergostat-<name>-<hash>.service`, `Restart=always`) elsewhere, one per repository;
`--service --install` installs and loads it, `--service --uninstall` removes it. It runs the `ergostat` installed on
PATH (each in turn; one whose `#!` is a launcher, a repository's `.venv` or a temporary environment is passed over,
and none left is refused). What it keeps running is the watcher,
which reads only `run.pid`, `heartbeat.json` and `stopped` every 5 s: an engine dead, unless stopped on purpose
(`ergostat run --stop` leaves `<state>/stopped`, removed by the next start; a logout or a shutdown leaves none), is
started again; one whose last pass is older than 180 s, or than the heartbeat's `stale` when that is 60 to 3600 s
(`use: upkeep`'s `heartbeat-fresh`, section 2a; malformed or out of range, 180, said once in `run.log`), is stopped
(`SIGTERM`, then `SIGKILL`) and started again; each under the same back-off, said in `run.log`, and recorded as
`ergostat.engine.restarted` when the start succeeded. `ergostat status` says "engine not running (last seen ...)",
from the heartbeat, and shows each loop as it was then, never as holding now.

**What a run records.** Every machine block's run ends with `agent.ran` (or `agent.failed`), and besides what it said
and moved, that event says what the run cost, measured by ergostat, never by the run's own say:

| Field | What | How |
|---|---|---|
| `exit`, `seconds` | Its exit code; its wall time, from start to end | Its process's wait status (the run's wrapper's: a signal that dumps core reads 128+N, section 9.1); the clock |
| `resources.cpu` (`cpu_user`, `cpu_system`) | CPU seconds of its whole process tree: its process, everything it started, user and system | The larger of its wait status (`wait4`: exact for the process and every descendant it waited for) and one shared sampler's sum (below) |
| `resources.memory_peak` | The most memory the tree held at once, in bytes (resident) | The larger of the sampler's peak (summed over the tree at each sample) and the largest single process (`wait4`) |
| `resources.processes_peak`, `open_files_peak` | The most processes in its tree, and the most files they held open at once | The sampler; open files where cheap to count (Linux `/proc`, macOS `libproc` for the user's own processes), else left out |
| `resources.samples`, `method`, `sampler_cpu` | How many samples saw it; `wait4+sampled`, `wait4` (it ended before the first sample) or `sampled`; the sampler's own CPU, its share | |
| `ai.cost_usd`, `ai.cost` | What its AI sessions cost, in USD, and how that is known: `reported` (Claude Code's `total_cost_usd`), `estimated` (tokens priced by ergostat's price table, `costs/prices.py`), `partly estimated`, or `unpriced` (tokens on a model with no price: `cost_usd` none) | Claude Code's result message (below) |
| `ai.tokens` | `input`, `output`, `cache_read`, `cache_write` (of those, `cache_write_1h`: kept an hour, priced higher) and their `total` | The same |
| `ai.model`, `ai.models`, `ai.sessions`, `ai.turns` | The model that used the most tokens, and each model's tokens and dollars; how many sessions reported, their turns | The same |

Network bytes are not recorded: per process they are available only through `nettop` on macOS (root, or a process
per sample) and per network namespace on Linux, so ergostat leaves them out rather than guess.

*Where the AI usage comes from.* An `ai` block with no `run:` runs `claude -p` with `--output-format json`, and
ergostat reads the result message in place of plain text: its text is taken line by line as before (its log too), its
`total_cost_usd`, `usage` and `modelUsage` are the run's. A session started inside a run (`ergostat session`, from an
`ai` block's `run:` or any program) prints `session.ran` with the same `ai` record, and the run that started it adds
that to its own, so a session in a program is the program's run's cost. Any other line a program prints that is a
Claude Code result message (`{"type": "result", ..., "total_cost_usd": ...}`, what `claude -p --output-format json`
prints) counts the same way; a run whose AI says nothing has no `ai`.

*How CPU and memory are measured.* One sampler thread serves every run at once (never a thread per run): every second
it lists the processes once (`/proc` on Linux, one `ps` elsewhere), finds each run's tree (its process group: each run
is a session of its own, and every descendant by parent), and keeps each process's last CPU time, the tree's summed
resident memory, its processes and open files. It runs only while some run is under way. Its own CPU (its thread and
the `ps` it runs) is measured and shared out among the runs it sampled (`sampler_cpu`): about 10 ms a sample on a
laptop, so about 1% of one core while anything runs, however many runs. Accuracy: CPU is exact for everything the run
waited for (the wait status), and within one sample interval for processes it left running; peak memory is exact for
the largest single process and, for the tree together, sampled each second (a spike shorter than that is missed). A
run shorter than a second is measured by its wait status alone.

The same numbers are kept as series of the block, plain metrics beside the sensors' (`run/BLOCK/cost_usd`, `tokens`,
`cpu`, `memory` in MB, `seconds`, one reading at each run's end), and read back as built-in measures a goal can hold
through a sensor (`builtin:`, §6, §12e):

| Reference | What it is |
|---|---|
| `ergostat.cost.usd` | Dollars the runs' AI sessions cost over the last day (reported, or estimated); `ergostat.cost.usd-hour` over the last hour |
| `ergostat.cost.tokens` | Their tokens over the last day (`-hour`: the last hour) |
| `ergostat.cost.cpu` | CPU seconds of the runs' process trees over the last day (`-hour`) |
| `ergostat.cost.memory` | The largest peak memory of one run over the last day (`-hour`), in MB |
| `ergostat.cost.runs` | Runs that ended over the last day (`-hour`) |

Each is about every block, or with `@BLOCK` one block, or with `@model:MODEL` the runs whose sessions mostly used that
model (`@model:haiku` matches `claude-haiku-5-5`). A budget on AI spend is a stock read from one and a goal on it:

```yaml
stocks:
  ai-spend:
    unit: USD
    description: what the AI sessions cost over the last day
    sensor: {builtin: ergostat.cost.usd, every: 5m}
goals:
  ai-budget:
    stock: ai-spend
    hold: "<= 5"                 # $5 a day
blocks:
  developer:
    type: ai
    in: goal.ai-budget.error     # (an onoff in front of it, or its own prompt, decides what to do when over)
```

The Agents page shows each agent's totals over the window (runs, dollars, tokens, CPU, peak memory) and, in its panel,
the history of each (dollars by hour, and tokens, CPU and memory run by run) and its runs with their numbers;
`ergostat agent NAME` says the same in the terminal.

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
| `alarm` | one signal | raises an alarm while out of bounds (`for` that long): one line in *needs attention*, and "alarm raised" on its block in the Blocks view (cleared when it fails or its input is unknown); a command or query sensor it reads is read on a pool of its own, never on the sensor pool it may watch | `above`, `below`, `for` |
| `judge` | what it reads, for the diagram | what it moved on its ports (`testing`, `passed`, `failed`, `accepted`: flows) | `every`, `hold-out`, `windows`, `threshold`, `accept`: the judge of changes to the model, on its own clock and on the program rung (section 12e) |

More (filters, rate of change, latches) can be added when a case needs them.

### 9.3 Machine block types

| Type | What it runs | Key fields |
|---|---|---|
| `program` | a shell command | `run`, `parse`; or `daemon` instead of `run` (a long-lived process its runs are handed to, section 9.7) |
| `ai` | a prompt, given to a model | `prompt` (text or a file), `model` (when it has no agent), `run` (an optional wrapper command), `workdir` or `workspace` (where its session works), `read`, `tools` and `actions` (what it may use; section 12k) |
| `person` | a request to a person | `ask` (what they are asked to do); they report with `ergostat block NAME --done ...` |
| `external` | nothing: observed only | none |

Common to machine blocks: `agent` (optional: the shared machine it runs on, section 10), `max`
and `min` (limits on one run's amount), `timeout`, `every`/`cron` (its schedule when nothing commands it; when something does, `every`
is the least time between runs), `takes`, `pool` and `lease` (the items it works, a run for each, and its leases' terms:
section 9.5), `on` (the event types that start it, a run for each: *Started by an event*, below),
`mode` (`auto`, or `advise`: its commands wait for a person to approve; not on a block that takes
items, which `check` refuses as `advise-with-takes`: gate it instead, section 9.5), and its control law's
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

**Started by an event.** `on: {event: TYPE, where: {...}, emits: [TYPES], max-age: 1h, most: 60}` on a `program` or
`ai` block runs it once for each event of that type recorded (`event:` a type, a list of them, or a prefix, `ticket.*`;
`on: TYPE` alone is the same) whose `data` matches `where:` (typed, as a sensor's: section 6; `a.b` reads a field's
field), however it arrived: a block's line, a push or a webhook (section 5c), `ergostat event --add`. It is what a state
change cannot say: a comment, a review, a webhook that moves nothing. `emits:` is the block's **declared output set**:
the event types its runs may say, as lines or by `$ERGOSTAT_CMD event --add` (none, by default, which `check` notes:
`trigger-no-emits`).

```yaml
blocks:
  triage:
    type: ai
    on: {event: ticket.opened, where: {team: core}, emits: [ticket.triaged]}
    prompt: prompts/triage.md
    out: flow.triaged
```

- **One run at a time, in the record's order.** The record is the queue: an event recorded while a run is under way
  waits for it to end, then starts the next. The engine's loop is woken by the write itself (section 9.1), so a run
  starts within milliseconds of its event, and no clock looks for them. One look takes at most 100 of a block's events
  (the rest at the next). Started again, ergostat goes on after the event the block's last run was for: what was
  recorded while it was stopped runs then, nothing twice.
- **Too old.** An event older than `max-age:` (1h by default; its own `time` against this machine's clock) when it is
  looked at is passed over, and that is recorded, once per look (`trigger.skipped`: how many, the first and last `seq`).
- **Its cause.** The run's `agent.started` is caused by (`causedby`) the event, and everything it prints is caused by
  the run, so its events name what started it (and the Process view draws the line, §5b). Its input carries
  `"trigger": "event"` and `event` (the event: `id`, `type`, `item`, `source`, `time`, `causedby`, `data`); its
  environment `ERGOSTAT_EVENT` (its id).
- **No loops, when the model is read.** The blocks started by events and their `emits:` make a graph: an edge from a
  block to each block whose `on:` one of its `emits:` types can match (`where:` is not read, so an edge that `where:`
  would rule out still counts). A cycle in it, of any length, a block that starts itself among them, is an error
  naming it (`check`: `trigger-loop`, `a → b → c → a`). What a triggered run says outside its `emits:` is refused: a
  line (`agent.refused`), or `$ERGOSTAT_CMD event --add` (by the engine's socket or without it: its block is read
  from the run's own `agent.started`, the one `ERGOSTAT_RUN` names, never from what the caller says of itself).
- **A budget carried on the record.** The graph cannot see what blocks that are not started by events say (one that
  takes the items a triggered block moves, one it commands). So **every** run's `agent.started` carries what led to
  it, inherited from what caused it, whatever started it (an event, an item it takes, a command): `depth`, how many
  runs started by events in a row led to it, and `chain`, the blocks whose runs did (the newest 16, this one last). It
  is read from the run among its causes, each looked up by its id (at most four causes back, never a scan of the
  record); a cause not found, or further back, is recorded `unknown` (its depth counted 0: the breaker below still
  holds). A goal's crossing (`loop.*`) begins afresh: a control loop closes through a measurement, which paces it. An
  event that 8 runs started by events led to starts nothing, and is recorded once (`trigger.stopped`: the event, its
  depth and chain). The 8 are counted along one line of causes: a loop of any length, through any blocks, runs at most
  8 triggered runs in a row on each line. An event that starts several (one block on it and another taking the item
  it opened; two blocks on it) starts a line for each, and each line has its own 8, so a block may run more than 8
  times in all (twice 8 for two lines), each run's `depth` 8 at most.
  (An event looked up by id, here and by `ergostat event ID`, is the one with exactly that id when there is one, else
  the first, in id order, whose id starts with it, both by the index; before, any one starting with it could come.)
- **A breaker per block.** More than `most:` (60) of its runs started by events within a minute trips it: recorded
  (`trigger.tripped`), and an entry in the inbox (section 12o); its events then wait, starting nothing, until the
  owner resets it (approving the entry, or `ergostat block NAME --reset`: `trigger.reset`). It bounds a fan-out, and a
  loop through anything the budget cannot follow (a relay outside ergostat that drops `causedby`). A run never answers
  for its own block: `ergostat block NAME --reset` or `--approve`, or the inbox's answer to its ask or its breaker, from
  inside a run of `NAME` (`ERGOSTAT_RUN`, its block read from the record) is refused.
- **Advised.** In `mode: advise` each event is asked about before it runs (`block.advised`, caused by the event, its
  `data` naming it: `event`, `event_type`, `event_seq`), one at a time, in the inbox (section 12o); the events after
  it wait. An answer names the ask it answers (`data.ask`, the `seq` of its `block.advised`; the inbox and
  `ergostat block NAME --approve` say it), and an answer to any other ask changes nothing. Approved
  (`block.approved`), it runs on that event, and keeps trying until it can start; denied (`block.denied`), it goes on to
  the next. Started again, an ask not answered stands (it is not asked again), and one approved meanwhile runs.
- **Gated** like any machine block: while what commands it (`goal:`, `in: block.x`) is off, its events wait.
- **Alone, and on what blocks say.** A block started by events has no `every:`, `cron:` or `takes:`, and neither its
  `on:` nor its `emits:` names a type of ergostat's own record (`agent.*`, `block.*`, `person.*`, `trigger.*`,
  `budget.*`, `loop.*`, `ergostat.*`, ...: which no block may say) (`check`: `bad-trigger`); a block that works items one by one,
  each needing doing until done, takes them (section 9.5) instead.

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
its kind's rules; or, in place of `data`, a JSON `patch` or the whole document, `set`), each taken as it is printed
(section 9.1). Lines that are not JSON go to the run's own log (`logs/runs/<block>/`, copied
into `logs/<block>.log` when it ends: section 4b). Its environment carries `ERGOSTAT_BLOCK`, `ERGOSTAT_RUN` (the run's id), `ERGOSTAT_ITEM` and
`ERGOSTAT_LEASE` (for a run holding a lease on an item: section 9.5), `ERGOSTAT_COMMAND` (the amount),
`ERGOSTAT_STATE_DIR`, and `ERGOSTAT_CMD`, the command that runs this ergostat on this project
(`$ERGOSTAT_CMD item --kind ticket --state open --json`, `$ERGOSTAT_CMD event --add ...`), for a
block, or the AI agent it starts, to read and record items while it works; and `ERGOSTAT_SOCKET`, the running
engine's socket, which answers `event --add`, `act`, `lease --renew` / `--nack`, `item ID --json` and the listing
`item --kind K --state S --json` (`{"op": "items", "offset": N}`: a page of 500 from `offset`, and `total`) without
loading the model (section 5c). An `ai` block without `run` is given to `claude -p` (or `$ERGOSTAT_AI`),
with its prompt, the JSON above, and how to answer, in the model's folder unless it names its own (`workdir:`, or a `workspace:` per item), and gated
when it names its `tools:` or `actions:` (section 12k). Any block, whatever its type, may also propose a change to
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

### 9.5 Leases and work queues

Some work comes as items, one at a time, and every one needs doing: tickets to fix, reviews to brief,
hypotheses to build. A machine block may **take** them: for each item of a kind that reaches a state,
ergostat starts a run of the block of its own, and the run holds a **lease** on its item until the
work moves the item on. The queue is no new object: it is the items in that state. Leases are what
make it safe to run several at once, to notice a run that went silent, and to stop retrying work that
keeps failing.

```yaml
items:
  ticket:
    id: ticket/*
    states: [ready, doing, review, done]
    on: {ticket.started: doing, ticket.submitted: review, ticket.merged: done}
    lease: {attempts: 5}               # optional: this kind's terms (below)

leases:                                # optional: each tier's terms, over the defaults
  ai: {ttl: 30m}

blocks:
  developer:
    type: ai
    takes:                             # a run per ticket that reaches ready
      kind: ticket
      at: ready                        # a state, or a list (taken in that order)
      to: [review, done]               # optional: the states that count as done (else any but at:)
      where: {team: core}              # optional: only items whose fields match
    pool: 3                            # at most three runs at once (default 1)
    lease: {ttl: 45m, attempts: 2}     # optional: this block's terms
    goal: backlog-short                # optional: it takes items only while its command is on
    run: $ERGOSTAT_CMD session developer --model sonnet
  reviewer:
    type: ai
    takes: {kind: ticket, at: review, to: [done, ready]}
    pool: {now: stock.reviewers, most: 4}   # as many at once as the stock (measured) reads now, never more than 4
    run: $ERGOSTAT_CMD session reviewer --model sonnet
```

| Key | On | Meaning |
|---|---|---|
| `takes` | a `program` or `ai` block | `kind` (a kind of the model's own), `at` (the states it takes from), `to` (the states that count as done), `where` (field: value, or a list of values), `unblocked` (true: only items whose precedence relations name only finished items, the critical first; section 5a, *Relations*), `order` (a field, or a list of them, of any kind of item: the items taken by it, lowest first, `-FIELD` highest first, those without it after those with it; a backlog's `rank`, a ticket's `-priority`) |
| `pool` | a block that takes | The most runs of it at once, counting the leases its runs hold, whichever engine started them: the owner's cap on how much of this work runs at once. Lowering it drains: no new lease until fewer are held; nothing running is stopped. Or `{now: stock.NAME, most: N}`: the pool is the stock's level, read at each dispatch, rounded down and held within 0 and `most` (required, a whole number, 1 or more). The stock must have a sensor (else `pool-unmeasured`). No reading, or one that is not a number, is a pool of 0: nothing new is taken, and ergostat says so once until it is read again. A lowered stock drains as a lowered number does. The block's box in the Blocks view shows its pool: `3`, or `2 now, at most 4 (stock.NAME)` (`no reading, at most 4 ...`) |
| `lease` | a block, a kind | `ttl` (how long a run may be silent before its lease expires) and `attempts` (counted attempts before the item is a dead letter) |
| `leases` | the top level | Each tier's `ttl` and `attempts`, keyed by the rung: `person`, `ai`, `narrow-ai`, `decision`, `program`, `rule` |

**Terms.** A lease's TTL and attempts are the block's, else its kind's, else its tier's in `leases:`,
else the defaults: person 8 h, AI agent 40 min, narrow AI 10 min, decision 2 min, program 5 min (or
its `timeout`, when longer), rule 1 min; 3 attempts. A block's tier is its agent's kind, else its
type's (`ai`: an AI agent; `program`: a program). A lease keeps the terms it was taken under: a TTL
changed in the model reaches the next lease.

**Dispatch.** While nothing commands the block, or what commands it is on (a `goal:` on it gates
it, as on any machine block), every item of its kind in a state of `at`, not held, not put off, and
matching `where`, is leased to a new run, oldest first (by when it entered its state), while the
leases its runs hold are fewer than its pool now. A pool written `{now: stock.NAME, most: N}` is read at each look,
with the dispatcher's lock held, in the same hold as the count of the leases and the take: the stock's level as the
engine last read it (its newest reading, whatever its age; no sensor runs at dispatch), rounded down, at most `N`, and
0 when it has no reading (also before the engine's first pass has loaded the readings, when it is not said). A raised
stock starts more runs at the next look, with no reload; a lowered one drains (no new lease until fewer than the pool
now are held; nothing running is stopped). The lock is this engine's: a lease another engine takes after the count is
counted at the next look; on the same item the fold refuses the second lease, on another item both stand, as for a
`pool:` number. The pool's stock is not one of the block's reads, so its `on-stale` (section 9.6) does not watch it.
`ergostat block NAME --now` runs whatever the pool is. With `unblocked: true`, an item a precedence relation says
waits on an unfinished item is not taken (one in a cycle never is), and the rest are taken the critical first: the least
slack, then the longest path ahead (section 5a, *Relations*), oldest first among equals. The kind must have a
precedence relation. With `order: FIELD` (or `[FIELD, ...]`), the items it may take are taken by those
fields first, each lowest first (`-FIELD`: highest first; numbers, then text, the items without it after those with
it), then the states of `at` in order, then the order above (the critical first, or the oldest): `takes: {kind: gap,
at: ready, unblocked: true, order: rank}` takes the groomed backlog's next unblocked gap, `order: [-priority]` a
ticket queue's most urgent. The dispatcher and the completion estimates (section 5a) sort by one comparator
(`leases/ready.py`'s `take_key`: the order fields, then the states of `at`), so the Timeline's projected runs are in
the order the block will take them; only the critical tiebreak among equals is measured differently (section 5a). `check`
notes an order field no item in the record holds yet (`takes-order-unset`). ergostat looks whenever the record has something new,
so a run starts as soon as its item reaches its state, and every second besides. A block that takes
items has no `every:` or `cron:`: its items start it. Nor has it `mode: advise` (`check`:
`advise-with-takes`), which asks before a command or an event, never before each item. To have a person
hold its items, gate it with `in: block.X` from an `expr` block that reads a stock with `sensor: {manual:
true}` (`expr: o` over `in: {o: stock.open}`). `ergostat sensor open --read 1` opens the gate and
`--read 0` shuts it. It opens for all of the block's items at once, not for one item; while it is off,
or has no reading yet, the items wait. A `person` block is no gate: its `--done` records work and never
sets a command, so `check` refuses one wired to command a block that takes (`person-gate`). A kind taken
by a block gains two states, when it does not list them: `leased`, after the first `at` state, and
`dead`, last.

**A lease** is a run's hold on one item. Its events, about the item, are ergostat's own:

| Event | Data | The item |
|---|---|---|
| `ergostat.lease.taken` | `item`, `run` (the holder), `block`, `fence`, `ttl`, `max` (attempts), `back` (the state it was taken from), `tier`, `attempt` | moves to `leased`. Caused by the event that brought it to its state |
| `ergostat.lease.renewed` | `run`, `fence`, `seen` (`activity` or `asked`) | its lease expires a TTL after this |
| `ergostat.lease.ended` | `run`, `fence`, `how` (`ack` or `nack`), `why`, `exit`, `note`; a nack's `after` (seconds), `count` and `news`; `item`, `state` (where it leaves the item) and `terminal` | ack: it stays where the work moved it. Nack: back to `back`, the attempt counted unless `count` is false, not taken again before `after`, or, with `news`, before the first event about it its own runs did not cause |
| `ergostat.lease.expired` | `run`, `fence`, `block`, `silent` (seconds), `ttl`, `expires` (the expiry it judged); `count` (false: its holder was not a run this engine process took); `item`, `state`, `terminal` | back to `back`, the attempt counted unless `count` is false; refused when the lease was renewed after that `expires` was judged (it expires later now): the watchdog reads the lease again just before it writes and writes none then, and one written in the moment between is no expiry to anything that reads the record (workspaces, measures, estimates) |
| `ergostat.lease.redriven` | `why`, `to` | a dead letter back to `to` (else `back`), its attempts from nothing |

A counted attempt that reaches the most allowed moves the item to `dead` instead: a **dead letter**.

**Renewal is observed, never declared.** Any event the holder caused about the item (`causedby` its
run: an event line it printed, taken when it prints it, or `$ERGOSTAT_CMD event --add` during the run), and any line of the
item's transcript (`claude.*`), renews the lease, in the fold itself. A run may also renew it
outright (`$ERGOSTAT_CMD lease --renew`). And before a lease expires, ergostat looks once more at what
its holder did elsewhere since its last renewal: an event it caused about anything, or an event about
an item it started (its session, `session/developer-1a2b`). If there is one within the TTL, it records
`renewed`, at that time; if not, `expired`.

**How a run's lease ends.** When the run ends, ergostat folds its item: moved on (to a state in
`to`, or, without `to`, any state but `leased` and those it was taken from) is an ack; otherwise a
nack, its why the run's own (`exited 3`, `stopped after its timeout of 1200s`) or "the run ended with
ITEM still leased". A run may give its item back itself: `{"nack": "why"}`, or `{"nack": {"why":
"...", "after": "4h", "count": false}}` (put off, not counted: a deferral or a transient fault), or
`$ERGOSTAT_CMD lease --nack WHY [--after 4h] [--no-count]`. With `"news": true` it is put off until `after` **or** the
first news of the item, whichever comes first: an event about it that none of its own runs caused and that is not
ergostat's (`ergostat.*`, `agent.*`): a webhook's (section 5c), a person's, another block's. A step that waits on
someone outside (a reviewer, CI) gives its ticket back this way, and is taken again the moment their answer is
pushed; `after` is only the fallback re-check. An item put off is looked at again when it falls due, not at the
dispatcher's next look. A run stopped with ergostat gives its item
back uncounted, unless what it printed before had already moved the item on (its lines take effect as it prints
them, section 9.1): that is an ack. Once ergostat has begun stopping it takes no lease; a take that raced the stop is
given back uncounted before its run starts, and a run still going when ergostat has waited its last for it has its
lease given back uncounted as ergostat exits. Before the engine records `ergostat.stopped`, every lease it took and
has not ended is given back uncounted (one whose run's own end failed too), each ended once. A process that a run of a
block's own `run` starts while its engine stops is killed (its process group) before the engine exits; this keys on
that engine's own stop, so another engine in the same process keeps a run it starts after the first one's kill (a run
of another engine already going when one engine kills its runs is killed with them, and one that then exits non-zero
is said to be stopped with ergostat). A daemon's item is stopped by the daemon's own close (section 9.7). A lease
that could not be given back (the write failed, or ergostat was killed, or restarted itself at once) is expired by the
next engine's watchdog on its TTL, so after a restart no item stays leased by a run that never ran; that expiry counts
no attempt (`count: false`), since its holder was not a run this engine process took (the dispatcher keeps, in
memory, the runs it took whose leases have not ended). A lease that expired is not ended again when its run ends.

**Fencing.** Each lease of an item has the next fencing number (`fence`, 1, 2, ...), and its run is
told it (`ERGOSTAT_LEASE`). A run whose lease expired is **killed** (*decided*, 2026-11-18: before, it was left
to run on, and the item was back in the queue meanwhile): when its lease expires, the engine that started it sends
SIGTERM to its process group and every process it started (in whatever group or session; one whose parent has
exited too, as the run's watch saw it: the run's processes are looked at after each sample of the runs' resource
sampler, about once a second, so one started and left between two looks is not seen; a pid the watch saw is
signalled only while its start time is still the one it saw, so a pid used again by another process is left alone
(start times are read to the second: a pid freed and taken again within the same second as its first start is not
told apart); the run itself and its group are signalled while it is not yet waited on, even when the processes
cannot be listed), and SIGKILL after a grace
(`ERGOSTAT_KILL_GRACE`, read at each kill; 10 s when unset or not a number) to what is left, and records
`ergostat.run.killed` (about its block; `run`, `item`, `fence`, `why`, `signal`: TERM or KILL, or `cancel` with no
`pids` for a run a daemon holds, which is sent `cancel` instead: section 9.7, *Cancel*; `pids`, `grace`). The run
then ends as any run: `agent.failed`, its note
`killed: ...`, its time, resources and cost measured (section 9.1); its lease is not ended again. The lease is read
again after the expiry is recorded, and the run is killed only when that expiry took (not renewed meanwhile); a run
that ended meanwhile is not signalled, nor, once its tree is gone, anything under its pid. A run that renews
is never killed, and a run left behind by an engine that stopped is not signalled (it is not this engine's). Whatever
a run says about the item after its lease ended (before it is stopped, or from elsewhere) is refused, not applied: an event line about it is refused when it is printed, before it is recorded
(`agent.refused`, its why the fencing), and an event recorded any other way, caused by a run whose lease on the item ended,
is recorded as it was said and refused by the fold (the item's `refused`). A `taken` while the item
is held, or with a fence that is not the next one, is refused too: one lease at a time.

**The fold is the truth.** The lease is the item's field `lease`, folded from these events like
everything else (an event's data never replaces it, nor does a `set`):

```json
{"fence": 3, "holder": "8c1f...", "block": "developer", "tier": "ai", "ttl": 2400, "taken": 1763460000,
 "renewed": 1763460900, "expires": 1763463300, "back": "ready", "attempts": 2, "max": 3,
 "history": [{"fence": 1, "run": "...", "block": "developer", "taken": ..., "renewed": ..., "ended": ...,
              "how": "expired", "silent": 2412, "counted": true},
             {"fence": 2, "run": "...", "how": "nack", "why": "exited 1", "exit": 1, "counted": true},
             {"fence": 3, "run": "8c1f...", "taken": ...}]}
```

`holder` is the run holding it, None while none does; `history` is each attempt's evidence; a dead
letter has `dead` (when), and an item put off `not_before`. An engine that starts reads the leases
from the record: a lease held when the last one stopped is still held, counts against its block's
pool, and expires on its TTL unless its holder (a run left behind) is seen to work.

**Across a model change.** A model changed while runs hold leases (swapped in place, section 9.1) changes no
lease: each leased run finishes under the model it was taken under (its block, its `takes`, its terms), keeps its
lease, renews it by what it records as before, and ends it, ack or nack, by its own block's `to`; its fencing number
stands, for the fold, not the model, holds it. New leases are taken under the new model: its blocks, pools and terms.
A lease whose block was removed is still watched, and expires on its TTL if its run goes silent.

**What a run is given.** Its input carries `"trigger": "item"`, the item (`item`: `id`, `kind`,
`state`, `fields`, without the lease) and its lease (`lease`: `fence`, `ttl`, `expires`, `attempt`,
`attempts`, `tier`, `back`); its environment `ERGOSTAT_ITEM` (the item's id), `ERGOSTAT_LEASE` (the
fencing number; the holder is `ERGOSTAT_RUN`), `ERGOSTAT_LEASE_TTL` and `ERGOSTAT_LEASE_EXPIRES` (when
it was taken). An event line that names no `item` is about its item. The owner's messages it is
given are those routed to its block or to its item (section 12h), and a recipe's context is rendered
for its item (section 12j).

**For what holds a resource as long as a lease** (a working copy, a session, a seat): the lease
events are the hook. React to `ergostat.lease.taken` (acquire, for `data.run` on the item), and to
`ergostat.lease.ended` and `ergostat.lease.expired` (release). Each names its `item`; an end says the `state` it
leaves the item in and whether that is `terminal` (a dead letter, or its kind's last state): finished, so what it
held can be cleaned, or not (under review, or back in the queue to be taken again), so it can be kept. In the run, `ERGOSTAT_ITEM` and
`ERGOSTAT_LEASE` name what it holds, and `ERGOSTAT_RUN` the holder. A run whose lease expired is killed, but
may still be stopping (its grace): what it writes about the item is refused, and what it holds should be released or
fenced the same way, by the fencing number. The workspace pools (section 12k) are held this way: an `ai`
block with `workspace:` that takes items works in its item's workspace, kept across its attempts and
its review, and cleaned when the item is terminal. `$ERGOSTAT_CMD event --type ergostat.lease.* --follow`
watches them; `ergostat lease` lists who holds what.

**Stalls, as a watchdog loop.** The built-in measures `ergostat.leases.held` (leases held now),
`ergostat.leases.expired` (expiries over the last day), `ergostat.leases.dead` (dead letters now) and
`ergostat.leases.overdue` (held past their expiry, not yet expired: non-zero during the watchdog's grace below even
when it keeps up, so a goal on stalls holds `expired`, not `overdue`),
each narrowed by `@KIND` or `@BLOCK`, are read by a sensor (`builtin:`), so a goal can hold them:

```yaml
auxiliaries:
  stalled-runs:
    driven-by: +stock.building
    sensor: {builtin: ergostat.leases.expired@developer, every: 30s}
goals:
  no-stalls: {auxiliary: stalled-runs, hold: "<= 0"}
```

ergostat's own watchdog, on the program rung, is what acts on it: it expires a silent lease on a second look at the same
expiry, a grace after it first found it past its TTL (a tenth of the TTL, at least a second and at most 30 s; renewed
meanwhile, the grace starts again: a renewal the run asked for in time may still be on its way into the record, the
engine or the machine busy), and the item is taken again. Each dead letter, and each lease that expired in the
last hour, needs attention (`ergostat`, the page's side panel); `ergostat lease ITEM --redrive` gives a
dead letter another go once its cause is fixed. The Items page shows, for a kind with leases, who
holds each item and when its lease expires, and its attempts; an item's page, its lease and every
attempt.

### 9.6 The observer: stale readings and estimated stocks

A controller acts on its picture of the world, and a reading is only a picture as of when it was taken. The engine can
keep, beside a reading, its age, and beside a stock an estimate between readings (`ergostat/spec/observer.py`; the
design is `docs/proposals/coordinator/06-observer.md`). **It is opt-in**: a model that asks for none of it records
exactly what it did before (its events, series, signals, findings and statuses). A model asks for it by:

- `observe: true` on a stock: it is estimated, and the goals on it are watched for staleness (policy `act`);
- naming `stock.X.estimate` or `stock.X.uncertainty` in a block's `in:`: that stock is estimated;
- `on-stale:` on a goal (that goal is watched) or on a block (what it reads directly, and the goals it reads, are watched).

**Stale.** A watched part is stale once the third reading its quickest periodic sensor should have taken since its last
is overdue: 3 × `every` after it, or the third time its `cron` comes round after it (as `sensor-stale` counts). One with
an `items`, `changes` or `manual` sensor, or no reading yet, is never stale; nothing is stale before its sensors could
have read since the engine started, or since it woke (the wall clock jumping ahead of the monotonic one by more than
30 s between passes: a laptop that slept, recorded as `ergostat.engine.woke` with `slept`, which the page reads
too). A watched goal on a stale part records `ergostat.goal.stale` and `ergostat.goal.fresh` as it
goes stale and reads again (`part`, `age`, `on_stale`). What it and the blocks reading it do is their `on-stale:`
(sections 8, 9): a built-in reading a stale goal whose policy is `hold` is held, and one whose policy is `off` sees it as
off without reading its stale value (an onoff's `until:` does not release on it). A machine block's input names what it
reads that is stale, with the ages in seconds, under every policy: `"stale": {"stock.inbox": 312.0}`, and each such goal
under `goals` carries `"stale"` too. `on-stale: off` on a machine block: its stale goals are given to it as `status: off`;
with `goal:`, the onoff it implies takes the policy too, so it is commanded to run (a stale stock it reads directly is
given as it was read). The page, `ergostat status` and the MCP `status` show a watched goal as `stale`, with its age,
only while it holds (off outranks stale), only while ergostat runs, and not before its sensors were due since ergostat
started; so do the goal and controller panels and "needs attention".

**Estimated stocks.** Between readings an estimate moves by the stock's modelled net flow, worked out once a pass: its
flows' equations, by the replay's stepper (section 12b), where they have them; their measured rates otherwise; and the
stock's last measured rate of change when a flow is neither. Each reading is weighed against the estimate at the moment
it was taken (one that lands late is not compared with the estimate since moved on), and blended in with a Kalman
gain, scalar per stock (no covariance between stocks), that is **adaptive**: re-estimated at each reading over the last
50 open-loop one-step errors (a reading less the reading before it moved by the model). Their lag-1 autocovariance is
minus the sensor's noise variance, and their variance the model's error over the interval plus twice the noise's; the
gain is the steady state's for those at the median interval. Until four readings each is taken whole; the model's error
is taken as at least 1% of the noise, so the estimate keeps listening. A model that is right drives the gain down (the
model carries the estimate between readings); one that is structurally wrong makes its errors large and drives the gain
towards 1, so the estimate follows the readings and is no better than them. A block reads it by naming it in `in:`:

| Reference | What it is |
|---|---|
| `stock.X.estimate` | The estimate now, in the stock's unit |
| `stock.X.uncertainty` | Its standard deviation now: after a reading, the steady state's; growing by the model's error until the next |

(A stock with a sensor itself named `estimate` or `uncertainty` keeps that sensor under that name.)

**Innovations.** For an estimated stock, each reading less what the estimate predicted for it is recorded as the series
`observer/X/innovation`. Five in a row more than 3 expected standard deviations off (the standard deviation never taken
below the sensor's resolution: half a count, for a stock read as whole numbers) record `ergostat.model.disagrees` (about
`stock.X`: the last innovation, its standard deviation, the run), and the finding **model-disagrees** stands on that
stock while one is in the window (`check`, `ergostat findings`): the model's flows miss something that moves it, which
modelling takes as a request like any finding (`finding:model-disagrees@stock.X` as a proposal's evidence). Finding the
structure behind a residual can build on these series.

### 9.7 Daemons: long-lived runners

A `run:` command is a process per run, and a `run:` sensor a process per reading: 170 sensors read every 3 minutes
are 57 process starts a minute. A **daemon** is a long-lived process that runs and readings are handed to as JSON
lines instead: on a `program` block, `daemon:` in place of `run:`; on a sensor, `daemon:` as its kind (section 6).
Either is a map, or the name of a top-level `daemons:` entry, so one process may serve many sensors and blocks:

```yaml
daemons:
  probes:
    run: python3 probes.py             # started in the model's folder; its standard error goes to logs/daemon-probes.log
                                       # (one stream for all its runs: never copied into a run's own log, section 12r)
    concurrency: 50                    # the most runs it holds at once (default 10; readings are not counted)
    heartbeat: 30s                     # restarted when it prints no line of any kind for this long (default: never)
    restart: {max: 5, within: 10m, backoff: [1s, 2m]}   # given up after more than 5 restarts within 10 minutes
    stdin-timeout: 10s                 # restarted (an alarm) when a write to its standard input waits this long
stocks:
  queue-depth:
    unit: jobs
    sensor: {daemon: probes, every: 3m}
  errors:
    unit: errors
    sensor: {daemon: {run: ./tail-errors.py}, push: true}    # its own daemon, which sends readings as it sees them
blocks:
  builder:
    type: program
    takes: {kind: ticket, at: ready}
    pool: 20                           # at most the smaller of pool and the daemon's concurrency at once
    daemon: {run: ./builder.py, concurrency: 20, heartbeat: 30s}
```

**The protocol.** One JSON object per line, both ways. In, on its standard input:

| Line | Meaning |
|---|---|
| `{"op": "item", "run": ID, "item": ITEM, "lease": {...}, "input": {...}, "env": {...}}` | A run: `input` is what a run gets on its standard input (section 9.1; for an item, with `item` and `lease`, section 9.5); `env` the `ERGOSTAT_*` values a run's process would have (`ERGOSTAT_RUN`, `ERGOSTAT_ITEM`, `ERGOSTAT_LEASE`, ...). `item` and `lease` are null for a run that holds none |
| `{"op": "read", "sensor": "STOCK.SENSOR", "request": ID}` | A reading asked for |
| `{"op": "cancel", "run": ID}` | Stop that run (its lease expired, its timeout, the owner's `block NAME --stop`) and say `done` |
| `{"op": "stop"}` | Finish what it holds and end; its standard input is closed after it |

Out, on its standard output, every line tagged with what it is for:

| Line | Meaning |
|---|---|
| a run's line with `"run": ID` added | As that run printed it (section 9.1): `{"event": ..., "run": ID}`, `{"out": ..., "moved": n, "run": ID}`, ... Event lines renew the run's lease as always |
| `{"done": EXIT, "run": ID}` | The run ended with that exit code. Exactly these two keys, `EXIT` a whole number (never `true`, never `1.0`) |
| `{"reading": V, "request": ID}` | The answer to a reading (`{"error": WHY, "request": ID}`: none) |
| `{"reading": V, "sensor": "STOCK.SENSOR"}` | A reading it sends by itself, for a sensor with `push: true` |
| `{"event": T, "item": I, "data": {...}, "sensor": "STOCK.SENSOR"}`, `{"message": {...}, "sensor": "STOCK.SENSOR"}` | What one of its sensors observed (section 6), or a message it relays: checked and recorded as a `run` sensor's are, from that sensor (a refused one is a `sensor.refused`). No `reading` beside it |
| `{"heartbeat": true}` | It lives (any line says so) |

A line that is not a JSON object, tags nothing, or names a run or request the daemon does not hold, is written to its
log and dropped: never taken as another run's. So is an observation that also carries a `reading`, that names a
sensor this daemon does not serve (a warm daemon serves none), or that a `run` sensor's would neither take nor
refuse (`{"message": "text"}`): it is never recorded from another source, and never counted. A sensor's
observations are taken at most 50 a second (accepted and refused alike, in one-second windows from the first); more
are dropped and counted, not recorded, and each window's count is said once, as a `sensor.refused` with
`{"why": "N observations dropped: more than 50 a second", "dropped": N}`, at the first of: its sensor's next
observation after the window closes, the supervisor's next look once the window is a second old (every 0.2 s), or
ergostat stopping (after its daemons have ended, or a second after they were killed; a line read later than that is
written to the log and dropped, not counted). The lines of one read are judged at the time it was read. A line over
1 MiB is dropped (said once in the log), up to its newline, and never held. Lines are read as UTF-8, what is not
UTF-8 replaced. A run's `done` is taken after its earlier lines; should taking a run's batch of lines fail as a
whole, each line of it is said dropped in the log. The `env` of an item travels in its line and never in the
process's environment, which holds only what every item shares (`ERGOSTAT_CMD`, `ERGOSTAT_PROJECT`, `ERGOSTAT_STATE_DIR`,
`ERGOSTAT_SOCKET`): a daemon passes an item's `env` to what it starts for that item, and never writes it into its own.
Its standard error is one stream for all its runs: it stays in `logs/daemon-<name>.log` and is never split by run or
copied into a run's own log (section 4b), which holds only what that run handed back that was not an event (usually
nothing); so a daemon run's failure is triaged by how it ended (section 12r).

**Each item is still a run**: `agent.started`, `agent.ran` or `agent.failed` (with `daemon`: its name), its lease
and fencing, its lines taking effect in the order it printed them (a run's line may be taken after lines of the
same read that are no run's, such as requests, readings and observations, printed after it). Its time is its wall
time only: a process serving many items at once cannot say which CPU second was whose, so a daemon's CPU and memory
are its own, sampled about 1 s after it
starts, then at doubling gaps up to every 30 s (never two samples within 1 s), and exact from its wait status when it
ends (on `ergostat.daemon.restarted`), shown on the Agents page, and no run claims them. Lines that arrive together
are taken together, per run, up to 500 at once, in the order printed.
A sensor read by a daemon starts no process and holds none of the sensor pool's threads while it waits.

**Supervision** (`ergostat/daemons/supervise.py`: a thread of its own, never the engine's loop). Everything written
to a daemon goes through a bounded queue (1,000 lines: items, reading requests and cancels together) and a writer
thread per daemon: the engine never waits on one. A queue that fills is a daemon not reading: restarted, an alarm.
A run is handed over only to the daemon running now under its name, checked and held under one lock (a restart or a
swap in between never strands it), and only while its lease is still its own. `concurrency` is the daemon's, shared
by every block it serves: the dispatcher takes no more items for them than it has room for. A push sensor's readings
are taken at most one a second; more are dropped.

- It **exits**: started again after a back-off, the first wait doubled each time, at most the most
  (`ergostat.daemon.restarted`, with why, its exit and its resources). Its runs in flight fail, counted.
- It is **silent** past `heartbeat`: restarted.
- It does **not read its standard input** for `stdin-timeout` (a write waits that long, or its queue is full):
  restarted, and an alarm raised (`alarm: true` on the restart; it needs attention for the hour after).
- **Cancel**: a run whose lease expired is sent `cancel` (`ergostat.run.killed`, `signal: cancel`), as is one past
  its timeout or stopped by the owner; a daemon still holding the run a grace later (`ERGOSTAT_KILL_GRACE`, 10 s) is
  restarted, its other runs given back uncounted (not their fault).
- **Given up**: more than `restart: max` restarts within `within`: no more starts; state `failed`, an alarm (it needs
  attention until it is revived), and one `ergostat.daemon.failed` recorded with `intervention: true`, `class:
  alarm:daemon:NAME` and `users` (every block and sensor it served), the intervention the owner's interventions
  measure counts. While failed, its blocks are handed no items (they stay in their queue, uncounted), a run already on
  its way is given back at once (uncounted, put off 60 s), and its sensors are not read (no `sensor.failed` each).
  `ergostat block NAME --restart` (a block: its daemon; or a daemon's name) records `daemon.restart.requested`, and the
  engine starts it afresh, its restarts forgotten; so does any change to the model.
- **Whole groups**: a daemon leads a process group of its own; whenever it ends (crashed, restarted, drained, ergostat
  stopping) the group is sent SIGTERM, then SIGKILL after the grace, so nothing it started outlives it. A crash is
  seen from its exit status, even while something it started holds its output open.
- **A model swap** (section 9.1): a daemon whose definition changed, or that nothing uses now, is sent `stop` and
  drained: its runs finish under the old model, and once it holds none it is killed if it has not ended within the
  grace. A new one, started at once, takes the new work. One whose definition is the same carries on.
- **ergostat stopping**: each is sent `stop`, and killed if it has not ended within the grace.
- **ergostat restarting itself** (its process started again in place: a new model's name, format or store, or the
  watchdog's last resort): just before, every daemon process group it started and has not seen end is sent SIGTERM,
  and SIGKILL goes to what is left after one wait shared by all of them, the grace but at most 3 s, however many there
  are. Nothing it waits on takes the supervisor's lock, and a daemon spawned meanwhile kills its own group at once.
  On a restart for a new model the daemons were first sent `stop` as when ergostat stops; this catches what that
  left (a warm process being killed, a group still waiting for its SIGKILL). On the watchdog's restart they are sent
  no `stop` and not drained: their groups get SIGTERM, then SIGKILL after at most 3 s, their runs are not recorded by
  the old process, and the items they leased are taken again when their leases end, uncounted. Dispatch is closed
  before the groups are signalled, so no item is handed to a daemon in that wait.

Its state is written to `<state>/daemons.json` every 2 s (running, backoff, failed or stopped; its pid, restarts,
last line, runs in flight, what it serves, CPU and memory): the Agents page lists the daemons, and an agent's panel
names its daemon.

**Warm** (`warm: true`; `recycle: M`, default 1,000, only with it). The owner's declared promise that the program
keeps no state between runs: a process per item without its start-up, for a program that holds one item at a time.
A warm daemon is `concurrency` processes of its command (`NAME#1` ... `NAME#N`, each supervised as a daemon of its
own: restarts, back-off, given up), each holding **one run at a time**; the dispatcher's room is its idle processes.
It serves blocks only (a sensor naming one is an error). The protocol is the one above. Because a process holds one
run, the run is charged its CPU (`resources: {cpu, method: warm}`): what its process group used between hand-over
and `done`, each member's own CPU and that of every descendant it reaped (read from outside: `proc_pid_rusage` on
macOS, `/proc` on Linux; elsewhere none): the group's total at `done` less its total at hand-over, so a member that
ended during the run and was reaped inside the group is charged only its part since. A run that never says `done`
(its process crashed, or hung past its timeout and was restarted) is charged the same way when it is failed, its
leader's part read from its exit (`wait4`) once it has ended; when its leader can be read neither way, the run's CPU
is `unmeasured`, never zero. Everything outside a run is
the process's own, left over with its start-up: CPU used after `done` and before the next hand-over is no run's;
only what is used after the next hand-over's total was taken is that run's. Not charged: a child
that left the group (`setsid`) or was orphaned and reaped outside it, and a member whose usage cannot be read. At
most 32 processes per warm daemon and 64 warm processes in all (an error in `check`; at run time, draining ones
counted, a process waits to start until one ends). A process is **restarted** (counted toward giving up) once its run has ended when it misbehaved:
a line for a run it does not hold (a late `done`), a line tagged with nothing, or a member of its group, not its
leader, still running at `done` (`left_running` on the run; killed with the group). One that ended but was not
reaped is said (`unreaped`) and not held against it. Its processes are given up one by one; the daemon's alarm and
`ergostat.daemon.failed` are recorded once, its status says how many processes are in each state (a partial
give-up shown), and `block NAME --restart` revives them all. It is **replaced**, uncounted, after a cancelled run
(its state may be half-changed) and after `recycle` runs. Neither is handed another run in between.
`ergostat block NAME --check-warm FILE` checks the promise on one input (FILE: a run's input, as JSON): it runs it
twice on one fresh process and once on each of two others, for real, and compares what each run printed (its run's
id put back as `RUN`) and its exit, without what the engine prepares for a run (no workdir, workspace or action
policy; only `ERGOSTAT_RUN` and `ERGOSTAT_ITEM` in its env). Unless every run ended with its own strict `done`, rc
3; the same, rc 0; the second run on one process differing from a fresh one, state
was kept, rc 1; the fresh runs differing, the program is not deterministic for that input and nothing is concluded,
rc 3. A daemon that is not warm, or a FILE that is missing, not JSON or not a JSON object, is a usage error (rc 2,
the file named, nothing run). A program started for a run reads its `env` from the line and passes `{**os.environ, **env}` to what it starts;
it never writes its own environment, and it reaps what it starts before `done`.

### 9.8 Engine shards

A model can be divided into **shards**, each to be run by an engine of its own. The division is worked out from the
model's graph, never written in it (invariant 8): `ergostat/spec/shards.py`'s `plan(spec, most=16)` reads the compiled
model and changes nothing. `ergostat run` does not use it yet: it runs one engine for the whole model, and no shard
runs as a process of its own.

- **Seeds.** Each top-level system (the outermost system a part is within) starts a shard, named after the system,
  lowercased. A name that is not `^[a-z0-9][a-z0-9-]{0,63}$` becomes `s-` and the first 12 hex digits of the system
  name's sha256; a name already taken gets `-2`, `-3` and so on. The **lead** shard, named `lead`, always exists, even
  in a model with no systems. It holds the parts with no system, ergostat's own kinds (`ergostat.*`) that no block
  takes, agents no block runs on, and anything else nothing assigns.
- **Parts.** Every stock, flow, auxiliary, goal, block, sensor, agent and kind of item is in exactly one shard. A
  sensor is in its part's shard, an agent in the shard of the blocks that run on it, a kind in the shard of the
  blocks that take it, else in its system's, else in the lead. `Plan.of(ref)` names a part's shard and raises
  `KeyError` for one not in the model; it has no default. A stock's estimate or uncertainty is in the stock's shard.
  A daemon (`daemon.NAME`) is in the shard of the blocks and sensors it serves, else in the lead; it is in
  `Plan.where`, not in a shard's `parts`.
- **Merges.** Two shards are merged when blocks in each run on the same agent (its `at-once` is counted in one
  process), take items of the same kind (a lease is locked in one process), or are served by the same daemon (a
  block's `daemon:` or a sensor's: it is one process, started by one engine). Kinds tied by a join (a parent kind
  and the kinds whose relation names it) count as one kind here. Nothing else merges shards; in particular, reading a
  signal across them does not. Each merge is recorded in `Plan.why`: the shard that joined, the rule (`agent`,
  `kind`, `daemon` or `ceiling`) and the agent, kind or daemon.
- **Wires.** `Plan.wires` lists, sorted, each value a part in one shard reads from a part in another that exists only
  in memory, with the shard it comes from and the one that reads it: a goal's setpoint, error or off (`goal`), a
  block's output read by another block (`cascade`), a block's output to a goal's setpoint (`setpoint`) or to a block,
  flow or auxiliary (`command`), a flow or auxiliary worked out from its equation (`equation`), a stock's estimate or
  uncertainty, which its shard's observer keeps (`estimate`), and any other stock, flow or auxiliary with no sensor
  (`memory`). The readers counted are goals (their part), equations, blocks (their inputs, and each goal they read or
  act in as an actuator, with that goal's part, as the engine gives them), and the observer of an estimated stock
  (each flow it adds up). Reading a part with a sensor is reading the measurements, which any shard can do, so it is
  never a wire; its sensors are read only by the shard that owns it. Writing to one (a command) still is.
- **Ceiling.** `most` is clipped to 1 to 16. While there are more shards than that, the two smallest (counted in
  parts, ties broken by name) are merged (`ceiling`). With `most` 1 there is one shard, the lead, with every part.
- **The same plan.** A model gives the same plan in every process, whatever `PYTHONHASHSEED` is.
- **An engine of one shard.** `Engine(project, shard=NAME)` works only on what `Plan.of` puts in that shard; with
  `shard=None` (what `ergostat run` uses) it works on everything, as before. A name the plan does not have is a
  `ValueError` when the engine is made. Its own are: the built-ins, the machine blocks and the goals a pass works out;
  the clock's timed sensors, sensor crons, timed and cron blocks and judges, and the item-count sensors read when the
  record moves; the blocks the dispatcher takes items for and the kinds whose leases it watches; the blocks an event
  starts and the kinds whose joins move a parent; the daemons `Supervisor.sync` starts, with the sensors they serve;
  and the stocks the observer estimates. A pass reads the newest measurements of its own stocks, flows and auxiliaries
  and of those in other shards its parts read (a goal's part, a block's inputs, an equation's references, an estimated
  stock's flows), and no others; an estimate read from another shard is a wire and is not carried yet. The shards of
  one plan divide each of these between them: none twice, none left out. The plan is worked out once per model, so
  whatever reads a model reads that model's plan. `swap` works out the new model's plan under the engine's lock; a
  plan without the engine's shard is refused, and the last model keeps running. A part that moved to another shard
  leaves nothing here: its built-in and output, its goal's signals, status, staleness and setpoint, its stock's
  readings, estimate and observer track, and its daemon (drained). Each owner's ask in the record is followed by
  the one engine whose shard `Plan.of` gives for what it names: an approval, a denial, a breaker reset or a stop by
  the block's (`block.NAME`), a restart by the daemon's, a step test by its goal's (and at start each engine resumes
  only its own goals' tests), an approved program action by the shard of the block whose run asked for it. An ask
  about something the model does not have (a removed block, an unknown daemon, an action with no block) is the
  lead's alone; besides, an engine still holding the run of the block a stop names, itself or in a daemon, stops it,
  whoever owns the block now. Each engine judges an ask under the one model it read for it, so after a `swap` the
  next ask about a moved part goes to its new owner. `start` refuses a block outside the shard as the model is when
  the run would start: an approval judged just before a swap moved its block is refused there, said, and must be
  given again (the new owner judged it not its own). Only the lead does what is done once: the `ergostat.started`
  event, `history.note` (at start and on a swap), the sweep of the messages, workspace leases, actions and notices,
  the roll-up, and the transcript ingester; each engine keeps its watchdog and calls socket. Not yet by shard: the
  wires are not carried; a run a block's moving a flow asks for reads that flow's stocks' sensors wherever they are;
  and the calls socket is one per state directory, not one per shard process.

### 9.9 The day's AI budget: runs reserve before they start

```yaml
budget: {daily: 20, max-cost: 2}     # dollars over the trailing 24 hours; dollars a charged run reserves
```

`budget:` (main file only; `ergostat.local.yaml` may not set it) takes both keys, each required: `daily`, US dollars
over the trailing 24 hours (the window of `ergostat.cost.usd`), with 0 < daily ≤ 10000; `max-cost`, with
0 < max-cost ≤ daily. An unknown key, a missing key, a value that is not a number, and one out of bounds are each an
error with its own message. Without `budget:` nothing here applies and no run or lease event carries a `reserve`.

`max-cost` is only what a run **reserves** before it starts. It is not a cap on what the run spends: a run that
spends more is charged what it spent, and nothing stops it as it runs (that is T1, `docs/GAPS.md`).

- **Charged and free runs.** A run is free (it reserves 0) only when its block is not `ai` and its agent is declared
  with kind `person`, `decision`, `program` or `rule`. Every other run is charged and reserves `max-cost`, including
  a block with no agent, or an agent with no kind.
- **The permit.** Before a charged run starts, ergostat opens `<state dir>/budget.lock` (a new open each time) and
  holds `flock(LOCK_EX)` while it reads the record, decides and writes the run's reserving event. Threads of one
  process and separate processes (the engine and `ergostat block NAME --now`) exclude each other. It refuses when
  `spent + reserved + max-cost > daily`, when the record cannot be read, or when the budget's values are out of
  bounds when the run asks (checked again, as at compile time). A leased run's reserving event is its
  `ergostat.lease.taken` (written by the dispatcher's take: the dispatch loop, and `block --now` on a block that
  takes items); an unleased run's is its `agent.started` (the engine's loop, event triggers, `block --now`, the
  message classifier, step tests, library trials). Each carries `reserve` and `pid`. The `agent.started` of a leased
  run has the lease's run id and carries no `reserve`: it is not counted again.
- **A refusal** writes no `ergostat.lease.taken` or `agent.started`; no lease is held and the block is not left
  running. It records `budget.refused` (item: the block; data: `reserve`, `spent`, `reserved`, `daily`, `why`) at
  most once a minute per block per process. `ergostat block NAME --now` prints `refused: budget: …` and exits 1.
- **What is spent and reserved** is a fold by run id (`data.run` of a lease's take, the id of an `agent.started`),
  never by lease state. It reads reserving events and ends (`agent.ran`, `agent.failed`, and `budget.closed`, data
  `run`, `cost_usd` or null, `why`) over the last 7 days, and matches each end to its run by `causedby` or `run`,
  never by time. A run with no end is *reserved* at its reserve, however old within the 7 days: a lease that expires,
  is released or nacked changes nothing. An end counts in *spent* only while it is within the last 24 hours: its
  known `cost_usd`; else its reserve, or `max-cost` when it used AI at no known price; a run with several ends, the
  largest. An end whose run has no reserving event in the 7 days (a free run, a run started more than 7 days ago,
  and the starts outside the permit below) counts its known cost, `max-cost` when it used AI at no known price, and
  otherwise 0. A cost is known only when it is a finite number of at least 0. A cost that is reported but is NaN,
  infinite or negative (it comes from the run's own output) is unknown: it is charged the run's reserve, or
  `max-cost` when the run has none.
- **Closing what has no end.** `budget.closed` with cost null (charged its reserve for 24 hours from the close) is
  written by recovery, under the same lock, for each reserving run with no end whose recorded `pid` is not alive, or
  is this process's but no longer among the runs it has open. Recovery runs when the engine starts and on the
  dispatcher's clock, at most once a minute, and reads the open runs without taking the engine's or dispatcher's
  locks. It copies the open runs before it reads the record, so a run that ends between the two is seen as ended.
  A run is listed as open under the lock, before its event is written. A run that `run_block` raises out of
  after its `agent.started` is closed there, cost null. A take the item fold refused (another holder won), or one
  that won its lease as ergostat stopped and so never ran, is closed with `cost_usd: 0`: nothing ran.
- **Only ergostat writes them.** `budget.*` is among ergostat's own types: no run's output, `ergostat event --add`
  (whatever its `--as`), push, MCP call or trigger may record one, so no run can close itself, or another, at 0.
- **`ergostat.budget.left`** is daily − spent − reserved. With no `budget:`, or a record that cannot be read, it is
  an error (`MeasureError`), never `daily` or 0: the measures list shows none and the error.
- **Limits, stated.** The budget governs the runs started through `Engine.run_block` and `Dispatcher.take`, and only
  those. It does not cover ergostat's own judge passes (`Engine.judge`), the AI calls inside ergostat that keep their
  own per-call caps (decisions extract, intent verdicts, the redesigner), or models in `ergostat.toml`
  (`runner.run_agent`), which have no `budget:`; their ends count in spent as ends with no reserving run. A pid
  reused by another process keeps a reserve held until that process exits. A run in flight for more than 7 days
  drops out of reserved. Each permit reads 7 days of starts and ends.

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
| `ergostat` | `url`, `token-file`, `tls` | another ergostat's reading (section 4c): `series` (a measurement there, `sensor/open.main`) or `ref` (a part's reading as it reckons it, `stock.open`); every sensor of one source is read in one request a period |

More types (Datadog, CloudWatch, SQL) can follow the same shape.

## 12. What ergostat derives and checks

**Derived** (never written): valves and actuators, controllers, disturbances, errors, loops
(a goal, the sensors of what it is about, the blocks serving it, and the flows they set), the
stock-and-flow diagram, block diagrams, the process map of the items (§5b).

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
- a cycle of built-in blocks with no delay (an algebraic loop);
- **bad-library**: a `library:` entry that is neither a path nor `{folder: PATH}` with an optional `trust: owner` or
  `trust: untrusted`, or `untrusted: true|false` (a YAML bool, agreeing with any `trust:`) (its folder is not read;
  section 2a);
- **untrusted-limit**: a part an untrusted instance made whose schedule, pool, attempts or runs at once pass the
  limits of section 2a, *Untrusted libraries*, at its `use:` line;
- **library-untrusted**: a use whose chain holds a template from a folder not marked trusted, and makes something
  `ergostat/library/trust.py` does not allow: at the owner's `use:` line, and nothing of the chain is in the model
  (section 2a).

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
  `auxiliaries:`, `auxiliary.x`, `auxiliary:`;
- **template-stand-in**: an instance of a template running on its stand-ins for a source or an action
  (section 2a);
- **no-modelling-loop**: a model with stocks and no judge, so nothing improves it: add `use: modelling`
  (section 12e);
- **template-library**: a template in a `library:` folder that does not read, or one used in place of
  ergostat's own; in an untrusted folder, also a template whose name or a parameter's name is refused, or one not
  used because a trusted one has its name (its text marked, section 2a, *Untrusted libraries*);
- **about-missing-part**: an open item (of a kind that declares `about:`, section 5a, *About*) names something that
  is not a part of the model: a part taken out, an unknown prefix (`foo.x`), no name (`goal.`), a port
  (`stock.x.main`). One finding per name, with the ids of the open items that hold it (at most 5 named in its
  message, all in `items`). Finished items are not checked. When the item index cannot be read, **about-unknown**
  says so instead, and nothing is said to be missing or not.

A finding of `check` (CLI or MCP) about a part (`about`: `goal.x`) that has open items about it carries their ids:
`items` in `check --json` and MCP's `check`, and `(open items about it: a, b)` at the end of its message, at most 5
named there. This is done last, after the calibration and extreme-conditions findings, so those carry them too; the
coherence report (section 12l) is apart and does not. These two findings and the ids are `check`'s alone: loading the
model (any other command, the engine, a proposal's trial) does not open the item index for them.

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

**The craft** (notes, `ergostat/spec/craft.py`; `docs/MODELLING-WELL.md`'s review checklists). Not wrong, but what a
professional in each discipline would wince at; each a **note** (level `note`): `check` lists them after the findings,
counted by code (`--json` gives each, with its `id`), they are not counted among the findings (`ergostat.model.open-findings`
leaves them out), and the modelling loop takes each up as a request (§12e). Parts a template made are left out (they
change only through the use's `with:`):

- **no-description**: a stock, flow, auxiliary, parameter, goal, block, item kind or agent with no description;
- **no-unit**: a stock with no unit;
- **no-equation**: a flow between two stocks with no equation (nor a declared rate): replayed, never projected;
- **collector-undescribed**: a sensor that reads the outside (`run:`, `query:`) with no description (the Blocks view
  titles the collector with its command);
- **event-names-mixed**: an item kind whose event types are not all `KIND.verb-past`, with the name each reads best as;
- **queue-goal-tolerance**: a goal served by a block that takes the items its stock counts, with a tolerance or a
  setpoint above 0, so items wait unseen (the block runs only while the goal is off);
- **schedule-removed**: a machine block with `every:` or `cron:`, and no `takes:` or `on:`, that also names a `goal:`.
  The controller that goal puts in front of it (§9.1) commands it, and a commanded block leaves the clock: it runs
  only while the goal is off, its `every:` only a pace. Meant, that is a paced controller; meant as a schedule (a
  sweep that must run whatever the goal reads, or one whose goal only its own runs can set off), read the goal as an
  input instead (`in: goal.NAME`). Only the model's author knows which was meant, so `check` says it and no
  modelling request is raised for it (§12e);
- **process-not-identified**: a goal's `process:` with no `identified:`.

**A kind's states, chained** (findings, `ergostat/spec/chains.py`). When two or more stocks count the items of one
kind in different states (`items: K, state: S`), the moves between those states are flows from one stock to the
next: arrivals from outside into the first state's stock, a flow from each state's stock to the next, completions
out of the last. What says items move from P to S: the record (each move the item index kept, a lease's hold taken
out: into `leased` from P and out of it to S is one move, P to S), a block that takes them at P to S
(`takes: {at: P, to: [S]}`), a flow's own sensor (an outflow from P's stock counting the items `entering: S`), and,
for a stock nothing fills, the kind's state order (the modelled state before it). A move is carried by a path of
flows from P's stock to S's (a move the record saw may pass only through stocks of the items being worked,
`state: leased`; one a block or the order implies may pass through other states' stocks), or by an aggregate the
other side relies on: a stock filled from outside by every item `entering: S` from two states or more (stopped,
set aside from any step), or drained to outside by every item `leaving: P` to two or more. `leased` and `dead`
are ergostat's own states and are left out. Each finding names its fix, with the YAML:

- **outflow-not-chained**: an outflow to outside from P's stock whose items go on to S's stock: `to:` that stock
  (and a flow from outside counting the same items entering S taken out);
- **inflow-not-chained**: an inflow from outside into S's stock whose items all come from P's: `from:` that stock
  (never a flow that also counts arrivals: the kind's first state, or a state items arrive in);
- **state-stock-without-inflow**: a state's stock nothing fills, though items arrive in it from another state (a
  flow from that state's stock, measured as items entering it), or, for the kind's first state, from outside (the
  arrivals);
- **move-without-flow**: items move from P to S and no flow carries them: a flow from P's stock to S's, measured
  as items of K entering S (with `where: {lease.back: P}` when a block takes them and S has other origins);
- **state-stocks-disconnected**: the kind's state stocks are pieces no flow joins, listed, with every change that
  joins them;
- **chain-stock-not-a-count**: a stock flows fill or drain whose sensor reads its items' age (`measure: oldest` or
  `age`): flows move items, so it counts them; the age is a stock of its own beside the chain, with no flows;
- **loops-not-connected**: the loops of the goals on the kind's stocks (each goal's stock and the stocks at the ends
  of the flows its blocks set) are groups that share no stock: the missing chain, named.

The last two are said only when a move is not carried (pieces with no move between them are a chain through a
state with no stock of its own). `numbers/structural.py` makes each a structural proposal, and the pieces one
proposal that chains the whole kind; each carries `rewires` and waits for the owner whatever the judge's policy.
`try_change` takes them as evidence (`finding:outflow-not-chained@flow.NAME`).

**The boundary, crossed once** (findings, `ergostat/spec/chains.py`). A cloud is the system's boundary, so an item
crosses it once, when it arrives; after that it moves between the model's own stocks. An inflow from a cloud is
measured as items of a kind when its sensor counts them `entering:` a state, or, with no sensor of the kind, when the
stock it fills counts a state of the kind (a sensor with a `where`, a part of the kind, and a `two-way` flow, an
adjustment, are not arrivals). In the record, an item arrives in the state its first event leaves it in.

- **kind-enters-many-times** (`items.KIND`): inflows from clouds measured as one kind enter two states or more. It
  names the flows and the states they enter, and says the meaning: the same items counted twice, or their moves
  between the kind's own stocks drawn as arrivals, so those stocks relate only through information links. The
  arrival into the kind's first state is kept (the first by the kind's order among the states the record sees items
  arrive in, else the first by the order); each other inflow is re-pointed `from:` the stock of the state its items
  come from, by, strongest first, the flow's own `leaving:`, the record's moves (back through states with no stock),
  a block taking them there, an outflow counting them entering it, and the kind's state order. When that is the stock
  it fills, it is taken out (it counts them twice); when the items pass through one state with no stock, which an
  outflow drains them into, that state gets a stock and the two flows meet at it. A flow the chain's own finding
  already answers is left to it: `inflow-not-chained` on the same flow becomes this finding, and a flow
  `outflow-not-chained` takes out, a stock the chain's fix fills, and the chain's aggregate (a stock filled by every
  item entering it from two states or more) are not said again. Items the record shows arriving in a later state
  directly (reopened in the outside system), or a state no state with a stock comes before (the items branch from
  states the model keeps no stock of), are real arrivals: then it is a note, not a fault, with no change.
  `numbers/structural.py` proposes the rewiring as one change (`rewires`), and `try_change` takes it as evidence.
- **many-cloud-inflows** (`model`): more inflows from clouds than half the model's stocks, and at least five,
  beyond each item kind's one arrival and leaving out two-way flows. Then most stocks fill from outside and pass
  little to each other: a note to draw the boundary chart (Sterman ch. 3: what the model explains, what it takes as
  given, what it leaves out) and decide what is really outside. Five, because fewer can be read at a glance, and a
  model of a few independent quantities, each filled from outside, is right as it is.

**How the model is divided into systems** (notes, `ergostat/spec/architecture.py`; the methods and their sources:
`docs/proposals/architecture.md`). Worked out from the causal links alone (each counted once, undirected, an implied
block's taken as its goal's; a system's subsystems each one node), never a run:

- **system-splits** (`system.NAME`, or `model` for the top level): a system of 20 parts or more whose parts fall
  into two clusters or more (greedy modularity clustering, Clauset, Newman and Moore 2004, an analogue of clustering
  a design structure matrix; a cluster of fewer than 4 parts joined to its nearest, and two joined by more than a
  tenth of the links inside the smaller made one: a heuristic set on the examples), at modularity 0.4 or more, and
  some of them loose parts in no subsystem of their own: those are named (at most six). When every cluster is one
  of the system's own subsystems it is **nearly decomposable** (Simon 1962), as a good hierarchy is: `explain`
  says so, and it is no note;
- **systems-merge** (`system.NAME`): two systems within the same one with at least 3 links between them, and at least
  as many as inside the smaller: the boundary cuts through one system;
- **interface** (`system.NAME`): what crosses its boundary (§4a's ports, counted by kind), said when material crosses
  through clouds on both sides (a flow to a cloud outside drives a flow from a cloud inside, in one unit), a block
  outside moves or commands what the system's own goals' loops use (not an arrival: filing work into a queue is how
  work is handed on), or 10 information links or more cross it (a heuristic);
- **time-scales** (`system.NAME`): its own parts' time constants (a stock's own drain and a delay's time, from one
  evaluation of the equations at the model's start; a goal's identified `process:`: a screen, not the system's
  modes) with a gap of more than 10 times between neighbours, the fast and the slow linked within the system: the
  fast parts a candidate inner system, given its setpoint by the slow (singular perturbation; hierarchical control);
- **purpose**, in a model with systems: a system with no `description` (its purpose); a described system whose blocks
  act for no goal inside it (one with stocks and no blocks, a sector, is normal); goals in no described system, when
  the model has no `purpose:`.

**Modes** (`ergostat/numbers/modes.py`; eigenvalue elasticity analysis, Kampmann 1996/2012, Saleh et al. 2010): only
`explain` shows them, never `check`, which neither imports nor works them out. They are the eigenvalues of the
stocks' Jacobian at the model's start, linearised by the same forward differences the time constants use (one
evaluation of the equations, no run; the diagonal is the one `time-scales` reads). Only the stocks are states: a
delay's stages are not. `explain` lists up to 8 modes, slowest first: each mode's λ per hour, its time constant 1/|Re λ|
(or "grows, e-folding every τ"), its period when complex (a conjugate pair once, ±), its 3 strongest links by |ε| (the
eigenvalue elasticity ε_ij = (a_ij/λ)·∂λ/∂a_ij; a link is each nonzero entry of the Jacobian, "stock.j → stock.i", or
a stock's own; real modes show ε signed, complex ones |ε| and ε), and the stock it is most in (participation |w_k
v_k|). `explain system.NAME` lists those most in a stock of the system. Over 40 stocks, modes are not worked out.
In place of numbers it says why: a λ = 0 mode (a conserved quantity, or a stock nothing drains) or a repeated one
has no elasticities; an eigenvector not found is said; and "Modes: not worked out" is printed when an equation the stocks
depend on is not run (a parameter with no value yet, as one still to be estimated; by name), no equation reads a
stock, the equations fail or fault at the start or when a stock is moved by the difference step (by name; a value
that is not a number or is past ±10¹² counts as a fault), an entry is not finite, or QR does not converge.

**The AI rung: the Viable System Model and purpose coverage** (`ergostat/spec/vsm.py`,
`ergostat/numbers/vsm_review.py`), run only when the owner asks: `ergostat improve --architecture [SYSTEM]`. For a
system, the **checklist** is computed from the structure (no run, and no note): for each of Beer's functions the
parts that may fill it, with why: S1 the goals directly in it on a stock of its own, and its subsystems; S2 its blocks
that take an item kind (sharing its leases, §9.5) or use a workspace pool that a block outside also does; S3 its
subsystems' inner-loop goals it sets, and its goals whose setpoint another goal's block commands; S3\* its judge
blocks and blocks with a `claims` param; S4 its measured flows in from a cloud, and the model's `use: modelling` loop
(marked model-wide); S5 its description, the model's `purpose:` and its subsystems' descriptions. One AI call
(`$ERGOSTAT_AI`, haiku by default, no tools, `--max-budget-usd 0.25`, killed with its process group after 300 s)
is given a brief of the system (its words, parts, subsystems, interface, its architecture notes and the checklist,
at most 30,000 characters) and answers with one JSON line. The answer is checked, not trusted: a function said
present must name at least one of the system's own parts (for S5, its description or the purpose), or it is dropped
as unsupported and counted; a goal must be the system's own (a subsystem's goal is judged by the subsystem's
review); a goal said to serve the purpose, and each part of the
purpose said uncovered (two words or more), must quote the owner's words, found in the description (or the purpose)
after whitespace and curly quotes are made plain, or it is dropped. A system with no description gets no purpose
coverage. The review is recorded (`ergostat.architecture.reviewed`: the system's `signature` and a hash of its words,
the model, its cost, `cost: reported`, or `charged` at the whole cap when none was reported, and what was kept). What
it keeps becomes modelling requests held for the owner (§12e, `source: architecture`): `vsm-s1` … `vsm-s5` and
`vsm-s3-audit` for a function said missing (naming the checklist's candidates, when it had some),
`purpose-uncovered`, `goal-off-purpose`. A later review answers one only on evidence it kept: that function present
with a real part, purpose coverage reviewed with nothing left uncovered, that goal said to serve; one said again is
reopened afresh and held. A call that fails, times out, errs or gives no answer line is recorded as
`ergostat.architecture.unreviewed`, at its cost, and raises and answers nothing. Writes are made under
`architecture.lock`, after reading the latest review's seq again: a review of the same system recorded since wins,
and this one is recorded `applied: false`. One call per system; at most 12 systems a run (never a once template's
own); a run's `--max-cost` is $1.00 by default and at most $5.00, and a call is made only while what was spent plus
$0.25 stays within it. `explain system.NAME` (with a project) says the latest applied review, and when the system's
parts or words have changed since. The reviewer is not shown to find every missing function: what the checks
guarantee is only that a function said present names one of the system's parts and that a quote is the owner's.

## 12a. Feedback loops (system dynamics)

Worked out, never written: every cycle of cause and effect through stocks, flows, auxiliaries,
goals and blocks (`ergostat/spec/causal.py`; `explain` lists them, and the graph API gives each
one's members, polarity and name). Each link has a sign:

| Link | Sign |
|---|---|
| a flow → the stock it fills / drains | + / − |
| a `driven-by` | as written; unsigned: not known |
| what a goal is about → the goal's error, e = r − y | − |
| a goal → a block reading its error | a built-in block: + (its law says what it does with the number). A machine block: as it moves the goal's quantity (a controller acts on its error: that is what serving a goal means): + when it raises it (it acts the more, the more room below the setpoint: a dispatcher filling up to a limit), − when it lowers it (it acts the more, the further the quantity is over: a worker draining a queue), not known when its paths there disagree or are not known |
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

**Projection**, two ways, from the state now (each stock the mean of its last few readings, each delay as the replay
left it), the inputs held where they were (or carried on along their recent trend), for a horizon of three of the
slowest time constant the replay met, within a twentieth and a quarter of the window:

- **with the loops running** (closed loop, `ergostat/numbers/closedloop.py`, through `simulate.project`'s control hook;
  the default wherever the model has a block that moves a flow, commands a block or sets a setpoint, *decided*
  2026-11-18): the control structure runs forward beside the stocks and flows, as system dynamics simulates a policy
  (Sterman ch. 1, 21: the decision rule is part of the model). Every goal and built-in block is worked out by the
  engine's own code (its `goals`, `_builtins`, `get` and `command_of`, run on a shadow of its state), started from
  where the record left it: each goal's last crossing and a setpoint a block set, each built-in's last output and when
  it changed, and the internal state the record lets it rebuild (a `delay`'s line from its input's readings, a
  `timer`'s or an `alarm`'s start from when its input last began to qualify, a `counter`'s count and its last reset, a
  `limit`'s clock). Given the same readings at the same moments, a built-in decides what the running engine would
  (tested by stepping both from mid-run); in the projection the readings are the model's, taken at its own steps, not
  the sensors' at theirs. What the record cannot rebuild (a built-in reading a goal's error or a machine's command, a
  delay whose input the engine works out after it in a pass, a counter's reset clock never seen) is said in the
  projection's notes. Goals and built-ins read a level as its sensor would: a count of items is a whole number, so a
  queue drained to a fraction of an item is empty to a goal "<= 0".

  Each **machine block** (program, AI agent, person, external) is not run but replaced by its **identified model**
  (`ergostat/numbers/blockmodels.py`; Ljung: a model of its input-output behaviour, with each number's standard
  error), identified on the reference window and said in words in the causes strip and by `ergostat project`:

  | The block | Its identified model | Identified from |
  |---|---|---|
  | takes items (`takes:`, §9.5) | *servers*, a multi-server queue: success × min(waiting, servers) / the time a server is held (a run's median time; its lease's TTL for an attempt that expired) | its runs' times, the share that ended well, the expiries; its pool now (at the end of the record: 1 when its stock reads 0 or nothing, said in its basis) and lease terms |
  | moves a flow with an equation | the equation, while commanded, at most its servers over their time | the model; its runs for the cap |
  | reads the goal on the stock it fills (a dispatcher reading its work-in-progress limit) | *fill*: at most the 95th percentile of its rate, never past that goal's setpoint, a run every `every` | the flow's record while commanded |
  | drains a stock | *drain*: min(the 95th percentile of its rate, waiting / residence time) while commanded | the residence time (time in system) by Little's law over the buckets it was commanded, mean level over mean outflow |
  | fills from outside | *rate*: its mean rate while commanded, and while not | the flow's record, by the commander's recorded output |
  | writes its law (`gain:`, `every:`, reading a goal) | that law, gain × error each run, with its `deadband`, `resolution` and `limits` | the model |
  | sets a setpoint, an auxiliary or another machine's command | held where it was, and said | |

  An identified model needs six buckets of its flow measured while it was commanded (five runs for *servers*); with
  less it is a declared **assumption** (a run moves what waits; its declared rate; a run of a quarter of its TTL, at
  most ten minutes), flagged in the strip and `ergostat project`. A flow measured long enough that never moved is
  identified as 0. A block whose flow moved while nothing commanded it (a person answering before being asked) is
  modelled ungated, and says so. An outflow held where it was (an input, not an equation) stops when its stock is
  empty. The judge of changes runs on its own clock and is held, like any input.
- **held** (open loop): the controllers held, every input held. What a flow a block sets moves (that flow, its stocks,
  and what follows from them) is left out, and the chart says so. `replay` is never closed-loop: the replay is the
  model driven by what was measured, as calibration and the judge use it.

**Honest about fit** (*decided*, the owner, 2026-11-19: projections far off after a burst, drawn as sure as any).
Where the parts a projection rests on fit badly, a charted stock (or a charted flow's stock) that the replay fits worse
than its mean on the reference window (skill < 0), or a goal on one whose loop the record does not identify
(**loop-not-identifiable**, §12d), the strip says so in front ("Low confidence: reviews-answered's model follows 2% held
out; the band is widened by the replay's own error", `low_confidence` in `/api/series`), as the impact report leads
with its confidence, and draws a wider band: the spread it has, or the projection itself, widened by two of the replay's
root mean squared error against the record (half and nine in ten at 0.67 and 2 of it) (`numbers_api.honest`).

The strip's foot has **With the loops running** and **Held**, one choice for every chart on the page
(`GET /api/series?…&loops=closed|held`); `ergostat project` (`--closed`, `--held`, `--horizon`, `--whatif`, `--risk`)
says the same in the terminal. Proposal effects (the review queue) project closed-loop where the model has
controllers.

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
stock that only integrates, the time things stay in it, by Little's law, both as the replay has them at the
estimate, not at the value written), on a young record (under twenty of that time constant) its effective record
holds at least ten independent points where the fit leaves a material error (its weighted error past 0.001, an RMS
past 3% of the readings' spread: it was past 0.01, and an image-squeeze record of 17 minutes drifting from its
readings as one passed as 80 points; on an older record errors that still drift together are said to put the
structure in question, not the record's length, and the calibration proposes nothing while a block may, for the
judge), and what it acts through **moved** six times (what the parameter multiplies in its equations, from
the Jacobian, going a tenth of its range from where it last moved: three cycles of an experiment started and
decided; one held at a single value the whole record cannot be told from a constant); otherwise it is **held,
inconclusive**, with how much more record it needs ("it needs about 30m more record", at the rate the record has
gone, or record in which what it acts through moves), said beside the parameter, and a block's proposal of a value
for it is recorded `inconclusive` at once with what it needs (`needs`), which the memory of what was turned away
(§12e) waits at least as long for. Then: the estimate is not at an end of
its range (the record would take it outside what the model says it might be: said first) nor at its
bound (one there is a question of structure), the record tells it apart, it is more than two
standard errors (within them, it says how much more record would tell a difference that size) and 2% from the value
written, and it fits the record held out better (with no record held out, nothing supports it out of sample, and it
is not proposed); otherwise it
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

Four more what-ifs are tried only **with the loops running**, and are never proposals (they change the world, not the
model): an input's rate (`flow.NAME:20`, an hour; `flow.NAME:x2`, twice its mean over the window, "arrivals doubled":
typed in the panel of a flow from outside), a goal's setpoint (`goal.NAME:5`, in the goal's panel), a pool
(`block.NAME.pool:4`) and a block's share of failed runs (`block.NAME.failure:20%`, its success the rest), both
beside its identified model in the causes strip; the last two change the items' completion estimates too (§5a). A
rate tried on a flow a block moves replaces its identified model. With the projection held they are refused and the strip says why.

**Sensitivity** (`ergostat/numbers/sensitivity.py`; the causes strip with the projection held; with the loops running
the strip's fan is the risk's, below): Monte Carlo over what the model
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

**Risk** (`closedloop.risk`; the causes strip with the loops running, its fan and a line for each goal on the part,
worked out in a thread of its own and drawn when it comes, no spread till then; a goal's panel; `ergostat project
--risk`): the closed-loop projection run many times over what it does not know: the model's uncertain parameters as
sensitivity samples them (an estimate whose standard error spans more than a factor of ten either way is held, and
listed, since sampling it makes every run another model: `sensitivity.informative`), each identified model's numbers
by their standard errors (a rate, a residence time, a run's time, its success), and each input from outside the
control about where the projection holds it, by its recent readings' spread over the square root of the horizon's
effective number of buckets (the buckets it spans times (1 − ρ)/(1 + ρ), ρ the readings' lag-one autocorrelation:
readings that drift together are fewer independent ones). That is how far the input's mean over the horizon could be
from now; when it arrives within the horizon (its timing, a burst) is not sampled. For each goal: the probability that
it is off at the horizon, at each point ahead, and its expected time off ("work-waiting: off at +8h with p≈0.3; 1h12m
off expected over the 8h"); a run that is not valid (it blew up) counts as off for every goal, and the line says how
many ("3 of 100 runs not valid, counted as off"). For each part, the half and nine in ten of the valid runs, drawn as
the strip's fan. Bounded: 100 runs by default, at most 400; at most 4,000 integration steps a run; a horizon of at
most 30 days; a watchdog stops it at 8 seconds of wall time on the page (60 at the command line) and says how many runs
it made. The draws come from a fixed seed (`--seed`): the same model and record give the same answer when every run is
made within the time allowed; a run stopped by the watchdog makes fewer, and says so.

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
too coarse is never blamed on the model. What a block would do is not simulated here (it is in a projection with the
loops running, above: the inputs doubled there is the closed-loop extreme condition).

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

**Stocks to aggregate** (`ergostat/numbers/aggregation.py`; a system's panel, the `aggregate` of
`GET /api/dominance`), from that loop dominance over the same window, the one the page shows: a chain
of stocks whose stages are each driven only by their own drain behaves as one delay (Simon and Ando
1961; Iwasaki and Simon 1994), so it is a **candidate** to aggregate into one, never a finding: it
holds for the window scored, and only among the loops of up to 30 parts that the loop search finds. A
stock qualifies when it is in the system itself (its innermost system), has a balancing loop of its
own through no other stock (its drain; a stock without one, an accumulator, is not a stage of a
delay), every loop through it is scored, it is named and moved in the window, it was never tied while
a loop through other stocks runs through it, and no loop through it and another stock dominated any
stock in any bucket. Anything not known disqualifies: a loop not scored (through one stock or more),
a stock not named or that never moved, the dominance missing or worked out for other loops than the
model's now, the loop search at its cap. A group is two or more qualifying stocks of one system
joined by flows into one linear chain, said in its material order: `over the window (SINCE to UNTIL)
no feedback loop beyond each stock's own drove stock.a, stock.b: a candidate to aggregate into one
delay`. A branch (a to b and a to c) or a cycle among them is no group, nor are two stocks with no
flow between them, nor two in different systems. The system's panel shows an `aggregate` row for
each of its groups, and none when there is none or the dominance could not be worked out; `check` is
unchanged.

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

**A quality floor** (*decided*, the owner, 2026-11-19, after a closed-loop identification that followed 2% held out
was proposed): whatever the rest says, it is not proposed when it follows less of the record held out than half of
what y's own jitter allows (at most 50%), when its errors held out are not independent of u, or, identified in closed
loop, when they are not white (there their colour is what was not measured, and it biases the estimate; an open-loop
output-error model needs only the independence, Ljung §16.6). Instead the goal has the finding
**loop-not-identifiable** (`ergostat findings`, the Check page): "the record so far does not identify this loop's
process (follows 2% held out; its errors held out not white). What would: a step test (offered), a large outside change
in its input (a burst of arrivals), or 2h more of record". It holds while the loop is as it was (`loop.key`) and clears
once an identification passes.

**Outside steps** (`ident.outside_steps`, `experiments.py`, `loop.around_step`): a large change in what arrives at the
goal's stock (a flow into it from outside the loop, measured) or in a measured input beside the path (a change from one
bucket to the next past six of its typical changes and a fifth of its range: a burst like 130 tickets added at once)
excites the loop from outside, as a step test does, while the controller keeps working. Every input is searched. Steps
on different inputs within forty buckets of each other are one step, at the earlier bucket, naming each input. On one
input, the larger of two such steps is kept (a burst's rise and fall are one). At most six are kept, the largest, and
they are taken in bucket order. Their windows, those inputs fitted beside u, are fitted together as one data set of
several experiments (Ljung §14.3, as the step tests are): the same K, τ and θ, each its own start and level, all but
the last fitted and the last held out whole. Windows that overlap are one experiment over their union, held out to its
last step's end. The windows are chosen in passes, three fits at most:
- Pass 0 is y's excursion: from forty buckets before the step to where y has come half way back, read no further than
  the next step. With one experiment, as long again after it is held out.
- Each later pass sizes the windows from the process the kept pass found. It fits from forty buckets before the step
  to its settling S = max(θ + 4τ, 5 (τ + θ) − 40 buckets) after it. With one experiment, it holds out as long again (20
  buckets at least).
- A later pass is kept unless it is worse by the order the identifications are ranked by (proposable, told apart,
  then precision). Its held-out record differs from the kept pass's, so this is not a like-for-like comparison: the
  precision favours the longer window.
- The passes stop when one would fit windows already fitted, when the kept pass found no process, or when it found an
  integrator (no settling to size from). What each pass did is said in `outside_step.passes`, and `window` says
  `process` or `excursion`.
- Nothing is clipped or filled in. A step whose process window runs past the record's end is dropped and said: "the
  step at 18:00 (flow.asked): the record after it covers 7m of the 8m40s its process needs to settle". If an earlier
  pass fitted that step, its result is not proposable either, and when no step is left nothing is proposed. A step
  where u or an input fitted has no readings in its window is dropped ("d2 has no readings in its window"). It is not
  filled from another experiment. When none is left, there is no process.
- The steps said as dropped (`outside_step.dropped`) are those the kept pass dropped, with the "covers" lines a later
  pass found for steps the kept pass fitted. A pass that was not kept does not add its own drops
  (`test_a_drop_in_a_pass_not_kept_is_not_said`).
- When there are several experiments, the record drawn with the result is the held-out one, the last (`last`), as for
  step tests (`test_the_record_of_several_experiments_draws_only_the_held_out_one`).

What is measured, on a synthetic loop with a known process (`tests/test_outside_experiments.py`):
- With one burst (τ = 60 s), K is within 0.1 and θ within 10 s on each of six seeds. The mean relative error of K and τ
  is under 0.3 and under a third of the loop working's.
- With three equal bursts, the standard error of K is below that from the largest burst alone, on each seed.
- With a slow process (τ = 300 s), the excursion's fitted part spans too little on every seed. The mean error is under
  0.3 and at most half the excursion's, but not every seed reaches a process window, so no per-seed claim is made. On
  some seeds the longer window has no step of u large enough for `ident.moves`: integral action ramps u.

The result is ranked with the others. It is said "identified around outside steps at 14:20, 16:05 (flow.asked), each
window from the process (θ + 4τ = 7m)" in its reason and its `identified:`, with any steps dropped. A later pass kept
as an integrator has no τ, and is said "… from the process (integrating: no settling time, so no θ + 4τ)"
(`test_the_reason_names_every_step_and_how_its_window_was_chosen`).

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
within the setting's resolution) stops the test, the setting put back at once. `.started` and `.finished` each carry
`plant`: for every system enclosing the goal, innermost first, its `plant_signature` (its stocks, flows and auxiliaries
as written, the parameters their equations use, and which u each of its loops moves; goals and blocks otherwise left
out, so accepting a `process:` or a `gain:` keeps it), or null when one cannot be worked out (the test runs anyway).

**Relative gain array** (`rga.py`; Bristol 1966, Skogestad & Postlethwaite §3.4, §10.6): for a system, never the model
without one, `explain system.NAME` with a project says one line of it. Its loops are the goals in it, at any depth, whose
u the record can read; fewer than two, no line; more than 8, or one whose `process:` is integrating or whose u fills or
drains its stock directly, not computed and why. Its tests are the latest 12 of them, in record order across the whole
system (so an older one may be the only test of a loop, and that loop is then named as having none), that finished
`done`, recorded their steps and finish, and whose stamps at start and at finish both hold this system's signature as it
is now, string for string (a missing or null one never matches). Each test gives, for every loop's u and y, Δ = the mean
of its readings over the last quarter of the hold, `[back − hold/4, back)`, less the mean over the quarter before the
step: the gains as held at the end of the hold, not a steady state proved. A test is left out, with its reason, when a
window has no reading of one of them, or when the two halves of that last quarter differ by more than 0.03·|Δ| plus
twice the spread before the step. A ramp always differs by a seventh of Δ, so an integrator the model does not declare
is left out this way, unless its Δ is within about 18 times the noise before the step. A first-order lag of time
constant τ differs by 0.016 of Δ at τ = hold/4 and by 0.030 at hold/3 (93% of its gain held), so a lag longer than about
a third of the hold is left out too. So is a response still rising late, behind a dead time near the hold. The other
controllers keep working: their u moves too, and every loop's ΔU and ΔY are fitted together by least
squares (ΔY = ΔU Gᵀ), so G is the open-loop gain matrix, not the closed loop's. Not computed: fewer tests than loops; a
loop with no test of its own; ΔU's columns (each scaled by its RMS) collinear, or the square root of the 1-norm
condition number of ΔUᵀΔU (the inverse taken exactly, not estimated) past 100; G singular. Else Λ = G ⊙ (G⁻¹)ᵀ, said
as each loop's λ on the pairing as built (its own u), with "never pair on a negative relative gain" (λ < 0), "the loops
fight" (λ > 10) and, with two loops, a better pairing swapped.

**Proposals.** Each is worked out afresh when the loop is looked at, and is one item while the loop is as it was
(`loop.key`): offered again with other numbers, the item is `revised`, never made anew; Accept applies what the page was
shown (the goal's `process:`, a block's `gain:`, made on the file's text so its comments stay, and
refused, with the file put back, if `check` would then find an error), recorded as `model.accepted`;
Approve records a step test's approval; a dismissed one is not offered again until what it depends
on in the model changes. Shown where the loop is: the process block's panel in the blocks view (the
identification, its step response and Bode plot, the process and step-test proposals), the
controller's panel (its law with that process, margins, closed-loop step and Bode, the tuning), the
scope (performance), and a loop's panel on the Loops page (all of it).

**Existing controllers** (`numbers/extlaw.py`, `numbers/external.py`; the gap in `docs/proposals/external-systems.md`):
a controller ergostat does not run (an autoscaler, an alert rule, a vendor's limiter) is an `external` block, and
`identify: {input: SIGNAL, output: SIGNAL}` (a stock, flow or auxiliary each, one sensor of each: the one named by its
port, else the first) asks for its law from the record. Both signals' readings on the reference window are put on one
grid at the output's median sensor period, each its last reading at or before each moment, over at most the last 2,000
samples (the grid is never widened: a law's durations are whole samples of its own period, and a coarser grid mistells
them). Each candidate law is fitted on the first three quarters, each with a pure delay of 0 to 6 samples searched:

| Law | Its parameters | Fitted by |
|---|---|---|
| **on-off** (an alert rule; a relay with hysteresis) | two levels; on once its input is past `on` (above, or below) for `for`, off once back past `off` for `for_off`; at least `min_on` on and `min_off` off | the output's switches: for each threshold (40, at the quantiles of the input just before each switch) and delay, the longest duration and wait consistent with every switch (or none, when that mistells no more; a wait only where it mistells at least three fewer), by the fewest switches mistold; a negative hysteresis is refused |
| **proportional** with saturation | u = c + k x, within [lo, hi] | least squares off the bounds |
| **PI**, velocity form, with a deadband | u += kp Δx + ki T (x − r) while \|x − r\| > db | least squares on Δu (r from the constant); the band from the errors where u held exactly, and its centre, each from the other |
| **three-position step (floating) control**, a stepper (the HPA's shape) | up `step_up` once above `up` for `for_up`, `cool_up` after its last move; down `step_down` once below `down`, likewise; within [lo, hi] | as on-off, each direction on its own; up below down is refused; a bound only where its rule held three times and it did not move |

Each is judged on the last quarter: its **skill** one step ahead (1 − its squared errors over those of holding the last
value) and its **R²** run free from that quarter's start on the input as measured (inside the loop it controls, the
input answered the true controller, so a free run that strays is not corrected: the skill is the sharper number there).
The law kept has the least n ln(SSE/n) + k ln n on the record held out, k its **active** parameters (those not none or 0,
its delay when not 0): a Schwarz-like parsimony rule, not a likelihood, since a switching law's errors are counts of
moves mistold, not Gaussian noise. PI in velocity form fits a proportional law as well, and a stepper between two levels
an on-off law: the fewer parameters win. A linear law's numbers carry least squares' standard errors (±); a threshold
carries the **spread** of the thresholds that mistell as few moves (at least the grid's step over √12), not a standard
error; a step, its moves' spread over √n. **Closed-loop bias** (Ljung ch. 13): where the controller's input answers its
output within a sample (an HPA's utilisation, a limiter's queue), the regression's input and its noise are correlated
and a gain fitted with no delay is biased toward 0 (a proportional law of 0.5 fits as about 0.44); a linear law with
delay 0 says so. The delay is as the record shows it, with how much of it may be the sensors' sampling said apart (the
median age of the input's reading at the output's, and one grid step). Said: the law, its parameters, the skill, the R²
and the delay.

The law is the block's model in the closed-loop projection (§12b), in place of the stand-in, said "identified,
external": sampled every grid period past its delay, from the state the record left (its last output, the time since it
last moved, how long its conditions have held), its input read from the projection's own values. An output flow is set
to the law's value; an output stock is moved by the block's own flow by each change of the law's level, so its other
flows still move it (the law's level is not imposed on the stock); an auxiliary output is identified and drawn, not run
ahead. Each projection run starts from a copy of that state. `check` (the findings that need the record) says
**external-unidentified** (fewer than 40 points, fewer than three moves, or no law fits) and **external-not-run** (a law
identified whose output the projection cannot move). The Blocks view writes the law in the block, its sketch (a relay,
a staircase, a saturation) and a small *identified* mark, from laws already fitted (a miss is fitted in a thread and
drawn on a later poll); its panel says the rest. *Not yet*: whether the law changed (someone retuned the controller:
two laws against one on held-out error; a first comparison of each half's numbers raised it on unchanged controllers),
a library of known laws declared and tested against the record (the proposal's `law: kubernetes-hpa`), an HPA's
multiplicative rule (desired = ⌈u x / target⌉) as its own family, and the law's numbers sampled by the risk.

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
| `ergostat.cost.usd`, `.tokens`, `.cpu`, `.memory`, `.runs` | What the runs cost over the last day (or `-hour`), every block's or `@BLOCK`'s (section 9.1) |

A measure's reference is `ergostat.model.NAME`: it reads beside `stock.x`, `flow.x` and `auxiliary.x`, and is
never one of them (a project's names have no dots). It is read by a sensor, `builtin: ergostat.model.fit`
(section 6), on a stock or an auxiliary, by ergostat itself (`ergostat measure ergostat.model.fit`, in a process
of its own); `ergostat measure` and the MCP tool `measures` print them all. *Decided:* a goal holds a measure
through the part its sensor fills, not by naming the measure: a goal's loop closes through the flows of what it
is about, and a measure has none, so the part gives it its history, its chart and the flows the loop closes
through (it falls by what the changes written took off it, `model-mended`, and moves either way by the rest,
`model-drift`: the record moving on and the world drifting from the model).
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
| revised | `.revised` (no move of state): ergostat's own change found again with other numbers or evidence, or carried to a new version of the model (`rebased`) | ergostat |
| superseded | `.superseded`: what it is about was removed or edited since it was made (said which), its edit no longer applies, or no longer found by the finder that made it | ergostat |

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
| `kind` | `parameter` (values only), `equation`, `structure`, `measurement` (a sensor of a part already there), `control` (a goal, a block, an agent, the judge's policy), or a change of words: `description` (descriptions alone, a sensor's too), `unit` (units alone) and `rename` (the same model under new names: each renamed part says `formerly:` its old name, every reference follows, and its structure, its control and every sensor are as they were; a change never edits a file that is not the model's). What the edit does decides, whatever it is called (`improve.kind_of`). Parameter, equation and structure are judged by the replay; a change of words by `check` alone (passed when it makes no new finding or note); control and measurement wait for the owner |
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
| `hold-out` | duration | `10m` | The least record after a change it is judged on (with twice the dominant time constant of what it touches, at most a day): the unit its bound counts in |
| `windows` | list of whole numbers | `[1, 2, 4]` | How the verdict shows its evidence: the record held out whole, in halves, in quarters (each at least a minute), sliced from the one replay the verdict pools |
| `warm-up` | duration | `6h` | The longest before each window its replay starts, so the window is scored with its stocks and delays as the record left them, not started cold with every delay in equilibrium (section 12f): three time constants of what the change touches, and never more than the record held before the window |
| `threshold` | share (`2%`, `0.02`) | `2%` | The least fall in scaled error that counts as better (its estimate; the bound must also exclude no change), and the most rise that counts as no worse |
| `accept` | `owner` or `auto`, or a map of kind (`parameter`, `equation`, `structure`, `description`, `unit`, `rename`, `redesign`) to either | `owner` for every kind | Who writes a change it passed. *Decided:* nothing automatic by default; with no judge, nothing is judged. `accept: auto` promotes `parameter`, `equation`, `structure`, `description` and `unit`; a rename and a redesign are written only when named (`rename: auto`, `redesign: auto`), never by `accept: auto`. Whatever the policy, the judge never writes a change that removes structure or rewires a kind's chain, a redesign that changes control, or any change to who decides (the judge's policy, a block's `accept`, a template instance's `with:`: refused when proposed); those are the owner's. How each is judged differs (the exemptions from the replay): parameter, equation and structure by the replay on the record after the change; description, unit and rename by `check` alone (they change no replay); a redesign by its scorecard on the record it has when the judge takes it up, its fit allowed 10% worse; control and measurement not at all (the owner's). Changes of words are written as many a pass as have passed; the rest one a pass. A change written moves the lines of the others waiting (their hunks shifted, `proposals.rebase`), and a change waiting is carried to the new version rather than superseded when its edit still applies (`proposals.supersede`: ergostat's own when their subject is unchanged; a description, a unit or a redesign whoever made it) |
| `reviewed` | a list of kinds (`structure`, `redesign`, ...) | none | The kinds written only after the reviewer's pass (*The reviewer*, below): the judge's policy writes none of them before it, and the inbox offers none to the owner before it (the review queue still shows each, and the owner may accept one there). The modelling template sets it with `ai: true` |
| `out` | map of `testing`, `passed`, `failed`, `accepted`, `inconclusive` to flows | none | What it moved on each pass, recorded as each flow's valve opening |
| `in`, `every` | | | What it reads (signed, as a machine block's), for the diagram; how often it passes |

**One change, whatever its numbers** (*decided*, the owner, 2026-11-19: every proposal ended "superseded" before it
was judged). A change ergostat's own finders make is identified by what it is about, never by its numbers: its kind, how
it was found (the calibration, the rule, the finding it answers), the parts it is about and those parts as the model has
them now (`proposals.subject`: each part as written, less where and its words; a structural change by its edit with the
numbers taken out). Found again with other numbers, the same item is **revised** in place (`.revised`: the new numbers,
reason and evidence, and `revisions` counted; found again saying the same, nothing is recorded); its history keeps every
earlier statement, and the judge holds out the record after its last revision. One under test or passed is left to the
judge, one decided is not made again, and one turned away is revised and checked again once `memory` lets it go. When
the model's version changes, a waiting change whose subject is as it was is **carried** to the new version, whoever made
it (a block records its `subject` too: the parts it touches, the stocks a flow it adds joins, the parts it removes):
`.revised` with `rebased`, its edit as it stands, moved by `rebase`, or a value's or an equation's made again on the files
as they are now (`tests/test_churn_carry.py`, *a block's value change is carried*). A carried change under test or
passed was judged on another version: it goes back to testing with its verdict and last look cleared, in the same event,
and is judged again (*a passed change carried goes back to testing*). A structural change of ergostat's own whose lines
moved is carried with the edit its finder finds again on the same item, not made again (*a structural change whose lines
moved is carried*). The rest are superseded, saying which: the subject removed or edited, the edit no longer applies (a
block's to make again), no longer found by its finder, recorded without a subject, no longer of its kind, or it would change
who decides. Every carry is decided under the proposals' lock on the model as its files are now (`files_now`): while they
do not compile, or differ from the model the pass read, nothing is carried, superseded, judged or written, and the next
pass decides (*an edit between the finder and the lock defers the carry*, *files that do not compile defer every pass*).
Each finder lets go only of its own changes it no longer finds: the calibration of values and equations, the structural
finder of structure; a loop's process or gain is its analysis's alone.

Each pass (`ergostat/numbers/judge.py`; `ergostat judge` makes one by hand) supersedes every open change made
against a version of the model since changed (but those it carries, above), starts **testing** each checked change it can replay (a value, an
equation, the structure; a loop's process or gain is not replayed, and waits for the owner), and replays each beside
the model as it is on the record that came **after** it was made, which neither its maker nor any estimate it rests
on has seen, in every window. It scores **what the change touches**: the stocks of its neighbourhood (as the gate
finds them), the goals' own stocks among them, each stock's mean squared error over its record's mean square,
whatever its time constant (the fit's total leaves out a stock slower than its window, so a change that slowed one
would look better; section 12f); the rest of the model and each goal's stock must be no worse. A mean over every
stock let one far stock's error dilute any change to 0%. It waits for **record long enough for the change to show**:
the hold-out, and at least twice the dominant time constant of what it touches (in the model as it is and with the
change), at most a day. Both are replayed once over all of the record held out, warm, from three of those time
constants before it, never longer than `warm-up` nor than the record held before it (on a young record a six-hour
warm-up integrated the stocks from where the record did not reach, and scored a regime of its own: errors of 12 to 700
where the goal read 0.03 to 0.14).

**The evidence is pooled, with its error rate stated.** At each reading the two scaled errors differ by
δ(δ + 2(after − record)), δ what the change moves the replay by. δ is known exactly; the only noise is the record's
own about the better replay, taken as AR(1) (its correlation from one reading to the next, its small-record bias taken
out, and from a twelfth of the record on, whichever is larger; while the record spans fewer than three of the time
constant of what it touches, in whichever of the two replays the record better, noise that drifts at all is taken to last that long,
since a short record reads a slow noise's correlation low; a stock with no time constant, which keeps whatever it gets
wrong, is also taken as a walk, its steps read from the record's successive differences, and the larger variance
counts; its second moment about that replay, so a bias counts as noise). Several stocks' noises may be correlated:
their standard errors add (the worst case). Scaled errors that stay within 0.005 of each other, bound and all, count
neither way. That gives the change's effect, the share by which it lowers the scaled error, and its standard error; a
**confidence sequence** (a normal mixture, Robbins 1970; Howard et al. 2021) bounds it, in units of the record the
change needs. It is a plug-in, asymptotic sequence: valid as far as its standard error is, under stationary AR(1)
noise (or a walk) read well enough from the record. Then looking again as the record grows does not raise the chance
of a false verdict: two-sided at 10%, by Ville's inequality it is ever crossed either way at most 10% of the time, and
each way about 5% (`ALPHA`) by the noise's symmetry: a change no better than the model as it is passes about 5% of
the time at most, and one no worse fails about that, its several fail tests (near it, the rest of the model, each
goal's stock) sharing the 5% (Bonferroni). On records made to that noise model (AR(1), far slower than the record, a
walk, two stocks sharing their noise, both replays wrong) it passed at most 5% and failed at most 6% of equally good
changes looked at seven times each (1,500 records each; a walk well under 1%). It
**passes** a change whose bound's low end is above no change and whose estimate is better by the `threshold`, near
what it touches, with the rest of the model and each goal's stock no worse by the threshold; one the bound holds no
worse than the threshold that answers findings without making any; or one no worse and **simpler** (fewer parts,
parameters and terms) where the record replays what it touches. It **fails** one whose bound's high end is below no
change and whose estimate is worse by the threshold, near it, elsewhere or on a goal's stock, and one no better that
makes new findings. One the bound holds within the threshold both ways is **inconclusive** once it has three times
the record it needs (the record tells it from the model as it is by less than the threshold). One the bound cannot
decide yet stays under test and says **about how much more record it needs** (the bound narrows as one over the root
of the record; on its testing event and in the judge's waiting list), looked at again each time the record it needs,
or a quarter more, has come; after seven times the record it needs (a day at least) it is inconclusive, saying how
much more. As is one too few readings can judge, and one it would pass whose parts the record held out has not
exercised (above: it does not vouch for a quiet part's rate). Measured (docs/roadmap/overnight/slowjudge.md): on a
queue drained over a day, filled at random and read every 15 minutes, the judge before this passed a change a fifth
worse in 6 of 20 records and failed one a fifth better in 11 of 20; now it passes none of the worse, and a change
halving a wrong drain within five days of record.

**A change the replay cannot tell** (`numbers/unmoved.py`). A change whose replay is exactly the model's (both
replays follow the same stocks, and every reading of each is equal as a float over all the record held out: no
tolerance, and a NaN is never equal) is judged by structure, once it has the record it needs (to within the same
second of grace the looks give, so a look due at the record it needs is not put off) and that record
exercised what it touches: a stock of its neighbourhood the record reads at least 12 times and does not find quiet
(`exercised.py`). A stock with no readings, or a change touching no stock, is never taken as exercised (a deliberate
narrowing of the design's "any stock both replay" for a change whose neighbourhood holds no stock: a busy stock
elsewhere says nothing of it, so it fails closed); such a change
waits, as one any record replays the same, for record in which what it touches moves, and is inconclusive at the
horizon. A change that moves any stock by any amount is judged by the record, through the bound, as above.
Judged by structure, the model it leaves is compiled with what `check` finds; any error fails it ("the model it
leaves no longer compiles"), with no scorecard. Otherwise the redesign scorecard (*Redesign*, below) is worked out for
the model as read from disk and the model with the change, with the fit counting only against it: a fit made
measurable or better never counts for it; worse, or behaviour lost, counts against it. Coherence that cannot be
compared on a side (an error reading the record, or no kind compared) is marked unmeasurable, with why, and never
counts for the change (no coherence gain counts then); a kind compared before and not after counts against it.
Unmeasurable on the before side only, it never makes the change better, but mismatches the after side shows still
count against it. **Better** (findings resolved, chains
joined, coherence mismatches fewer or coherence up, craft notes closed, and nothing worse) is passed; mixed, or no
better with anything worse, is failed. Nothing moving, with every measure measured, is inconclusive at once ("no
structural measure moves, and the record cannot tell it from the model as it is"); nothing moving with coherence or
the fit unmeasurable stays under test, its `undecided` naming which and why, worked out again at each look, until the
horizon, then inconclusive, naming the same. The verdict carries `on: structure`, its `scorecard` and the `version`
of the model the scorecard read, all inside `verdict` (replaced whole by every verdict, so a change made again under
its id keeps none of them). It is judged inside the proposals' lock, which Accept takes too, so nothing ergostat
writes comes between the scorecard's read and the verdict; a hand edit takes no lock, so a version read that is not
the change's own records no verdict (the next pass, on the model read again, carries the change to it and judges it
again, or supersedes it, as any change made against another version; until then it takes one of the pass's looks, as
any judged change does), and a hand edit after the read leaves a verdict stamped with the version read, which Accept
then refuses ("the model has changed"). An edit that cannot be tried on the model there (a `TrialError`) leaves the
change under test, its `undecided` naming the error. A pass on structure
alone is the owner's to write, whatever `accept` says, and waits in the review queue with its scorecard beside it.
Each verdict keeps its windows (each one's span, and the scaled error
before and after), its pooled estimate and bound, as its evidence, shown with the item in the review queue. Then, where `accept` says `auto` for a
passed change's kind, it writes the oldest, one a pass, so each is measured alone (never one that removes
structure, nor one passed on structure alone: those wait for the owner, whatever the policy): Accept's way (section 12b), the
smallest edit, refused and put back if `check` would then find an error, recorded as `.accepted` from the judge
with its policy named, and `ergostat.model.changed`. Accepting writes the YAML at once; ergostat never commits it:
the owner does.

### Requests: what check finds is modelling's work

Everything `check` finds is a **request** the modelling loop holds (`ergostat/numbers/requests.py`): an item of the
built-in kind `ergostat.modelling-request`, raised from each finding, chain finding and craft note (one about a part a
template made, or one no change to the model answers, such as `template-stand-in` or `no-modelling-loop`, is left out),
and, once the record is long enough to compare, each coherence mismatch (§12l) no finding already says (those about
ergostat's own kinds are left out). Each records what it is about (`about`), why (`says`, check's words), where, its
`source` (check, craft, coherence) and the tier that answers it first (`tier`: rule or ai).

Two sources are not check's, and the collector (`sync`) never answers them: `redesign` (a redesign's trigger, below)
and **`architecture`**, what an architecture review the owner ran kept (§12, *The AI rung*: `vsm-s1` … `vsm-s5`,
`vsm-s3-audit`, `purpose-uncovered`, `goal-off-purpose`, its id `rid("architecture", code, about)`). An
architecture request is held for the owner at once (`owner: true`, `tier: owner`): no tier writes a model change for
a judgement, and approval is not offered (only a dismissal, or the owner's own change). Only a later applied review
answers it, on the evidence it kept; one said again after it was answered is reopened with fresh `says`, `version`
and `review` (the review's seq), its `why` and `change` cleared, and held again.

| State | When |
|---|---|
| open | check finds it, and no change waiting cites it |
| proposed | a change waiting cites it (its finding, `finding:CODE@ABOUT` or `coherence:CODE@ABOUT`, among its evidence) |
| held | no tier enabled has a change for it, or its change was turned away (with why); left to the owner (no tier takes it up) when the owner dismissed its change, or its finding is control; opened again when the model's version changes (unless left to the owner). It is in the inbox (§12o) |
| answered | check no longer finds it |
| dismissed | the owner denied it from the inbox with why (`--deny --note WHY`; the note and who are kept): not raised again while the part it is about is unchanged (its definition and description, hashed; a finding about the model, or about no part found, waits on the whole model); raised again (`reopened`) once that part changes, as a new finding: untried, not the owner's, its tier the finding's, its dismissal's note and who cleared. Counted as an answered intervention (denied), never a suppressed one |

A held request **approved** from the inbox is `reopened`: open again, for the AI tier (`tier: ai`, its tries given
back, `approved_by` kept); if the AI tier holds it again after its tries, it is back in the inbox. Approval is offered
from an allowlist: only for a request the tiers take up (raised by check, a craft note, a coherence mismatch or the
fit; never a redesign's, such as `too-large`), whose tier is the rule or the AI tier (not the owner's), whose finding is
not one only the owner changes, and only when the model runs the AI tier. Otherwise the owner's own change citing it
answers it, or a dismissal. A redesign's request the owner dismissed stays dismissed across the redesigner's passes
while its unit is as it was (its own parts, hashed), and is held again once the unit changes.

Every write of a request's state (the owner's answer, the collector's moves, a tier's word, the redesigner's holds and
its run's end) is made under one lock (`requests.lock` in the project's state), the request read again inside it. A
tier that read a request before calling its model writes its word only if the request has not moved since it read it
(the record's seq of its last move, an event that changed its state or reopened it, is the one it read; the state alone
is not enough, because held then approved is open again): an answer the owner gave meanwhile stands. A tier's own
word in the same state (its tries and cost) and a refreshed wording from check are not moves. The redesigner's run writes its end only on a request still open (or
answered as never ended), never over a dismissal.

The **request collector** (`modelling requests`, the sensor of the template's `requests-raised`) reads check, raises
what is new, answers what is gone and moves each to where its changes say it is. **The tiers**, each an ordinary
block of the template, answer them, the cheapest first:

- **the rule tier** (`fixer`, a program, `ergostat/numbers/rules.py`): mechanical changes that are safe and certain:
  a stock's unit carried along its flows from the stocks they join, or the plural of the kind it counts. Each change
  cites every request it answers. A queue's goal with a tolerance and a process nobody identified are control: their
  requests are held for the owner as they are raised (they are in the inbox).
  What it cannot answer it hands to the AI tier, saying why. A kind's chain and the structure tests are answered by
  ergostat's own finders (§12b), whose changes say `rewires`. Each tier records and checks its changes in its own
  process, as the engine checks a block's propose line;
- **the AI tier** (`modeller`, an `ai` block, on only with `ai: true`; `ergostat/numbers/modeller.py`): the requests
  the rule tier could not answer, a few at a time, each with the neighbourhood of the model it touches (its part and
  every part one link from it, as written, and the first lines of the programs they run), and a prompt that is the
  author skill and the modelling guides made short (`library/templates/modelling/modeller.md`). It proposes
  descriptions, units, equations, structure, loops and collectors as ordinary changes; each is tried first as
  `try_change` tries it, and what would be turned away is given back once with why. Its cost is recorded on the
  requests it was given (`cost_usd`), and a request it has tried twice waits for the owner. Its parameters: `ai-model`
  (haiku), `ai-every` (10m), `ai-most` (requests in one call, 8, from 1 to 16) and `ai-daily` (dollars a day, 1, from
  0 to 20), passed as `modelling ai --most` (1 to 16), `--tries` (1 to 3) and `--daily` (0 to 20, required), each
  refused outside its bounds at expansion and again by the run. **Its daily cap** (`ergostat/numbers/modeller_spend.py`,
  `<p.dir>/modelling/ai-spend.jsonl` under an `fcntl` lock): each call, the go-back too, reserves the most its prompt
  and longest answer could cost (`unsaid`), which also goes to claude as `--max-budget-usd`. A call starts only when the
  day's spend plus its reservation stays within `ai-daily`; one call at a time (the lock is held from the check through
  the call to its charge); a call that reports more than its reservation is charged what it reported, so the day can end
  above `ai-daily` by that one call's overrun, and none starts after it until the day's spend is back under. A charge
  is its settled cost, or its whole reservation until settled (a run killed mid-call), dated by its reservation; a
  ledger that cannot be read means no call. A run the cap stops leaves its requests as they were (no try counted), and
  the status line says `the AI tier has spent $X of its $Y today` once a call was refused for the cap that day or the
  spend is within the latest reservation of it. **A failed call** (`modeller.call`: it timed out, exited non-zero,
  said `is_error`, or said no cost that is a finite number of dollars, 0 or more) is an `error` with what it said
  (its result, or its standard error), charged its reservation, or what it said if more. The AI tier does not try again
  in that run; when its first call fails, its requests keep their tries and state, are charged their share, and say the
  error (`why`, `error`), so the next run gives them to it again, within the cap. When only its second (go-back) call
  fails, its first answer was a real one, so the requests it did not answer use their try as before, held saying the
  second call failed. Failed calls are counted apart from tries (`failed`) and bounded, since some fail the same way
  every time (a prompt too long): a request that failed before is never in a call with others. While any request with
  no failed call waits, the call takes only those; after that, the one that failed least goes alone in its call. After
  `modeller.FAILS` (3) failed calls a request is held for the owner, saying the error. They are failed calls in a
  row: a first call that answers sets the count back to 0, and so does the owner's approval (with its `error`
  cleared), so an approved request is called again; raised again after a dismissal, it starts with none. The reviewer counts no failed
  call toward its tries and stops its pass there; the changes that failed least are read first, and one with
  `FAILS` failed calls is `undecided`, the owner's. A redesigner run whose calls failed ends `error` (with the
  error), not `nothing proposed`; its request stays open saying so, and the unit takes no rest for it until `FAILS`
  runs in a row have failed, when it rests as after a run that made nothing. The lock covers the AI tier's own calls only, not the redesigner's or
  repair's, and does not reach a claude child that outlives a killed run.

Edits may be written `{"part": "stock.x", "set": {"unit": "alerts"}}` (a sensor's: `"sensor": "main"`) or `{"add":
"parameters", "name": "t", "set": {...}}` besides `replace` and hunks.

### Redesign: a change set, judged as a whole

Refinement (the tiers above, the improver) answers what `check` finds one change at a time, each judged alone, and the
judge passes a change only when the record shows it better: most of what a model needs (a chain connected, a collector,
a system split, the names of its parts) changes no replay error, and a real restructure is a dozen edits that only make
sense together. **Redesign** sits beside it (`docs/proposals/redesign.md`):

- **A change set** (`ergostat/numbers/changeset.py`): one proposal holding many coordinated edits, made in order on a
  scratch copy of the model's files in memory, each on the text the ones before it left; the model need compile only at
  the end. Its edits take the forms a propose line takes (`{"part", "set"}`, `{"add", "name", "set"}`, `{"file",
  "replace", "with"}`) and three more: `{"remove": "stock.x"}`, `{"rename": "stock.x", "to": "y"}` (every reference
  follows: `stock.x`, a flow's `from:`/`to:`, a goal's `stock:`, a block's `goal:`, a parameter in an equation; a stock,
  flow or auxiliary says `formerly:` its old name) and `{"file", "write"}` (a model file written whole; a part taken
  away and one added that reads exactly what it read is the same part renamed, and says `formerly:` so). Each carries
  its `why`. What it does is then one diff from the files as they are, applied atomically to judge it and on Accept; what
  it adds says `inferred:` its change; its renames carry their readings across as a rename does.
- **One item**, an `ergostat.model-change` of kind **`redesign`** (`ergostat/numbers/redesign.py`), with its system,
  summary, each edit with its why, the parts it adds, renames, changes and takes away, its scorecard and its cost.
- **Judged as a whole by a scorecard** (`ergostat/numbers/scorecard.py`), the model as it is and the scratch copy each
  measured on the same record: `check`'s findings resolved and introduced (a finding about a renamed part is the same
  finding); each kind's state stocks in pieces no flow joins; the coherence score per kind and the mismatches (§12l),
  run again over the record as it is (what Blocks ↔ Process says of a block the change adds, or of a flow only such
  blocks move, is left out and said as unseen: the record holds none of their runs, and cannot; coherence that cannot
  be compared on a side, an error reading the record or no kind compared, is unmeasurable, says why, and never counts
  for the change); the craft notes closed and opened; the fit, not worse beyond 10% over the stocks
  both replay where it can be worked out (made measurable counts for it); and **behaviour kept**: a stock whose replay
  followed the record (scaled error at most 0.5), or an equation that explained its flow (R² at least 0.5), is still
  there, or renamed, and no worse beyond the tolerance. The verdict is **better** when findings, chains and coherence
  improve (net), none is worse, the fit is no worse and nothing is lost; **mixed** when something improves and
  something is worse; **no better** when nothing improves. Craft notes it opens (a new flow between stocks wants an
  equation) are said beside the verdict and count against it only when nothing else moves. The judge takes a redesign
  up at once: its scorecard worked out again on the record as it is, passed when better, failed otherwise; the owner
  sees the scorecard either way (the review queue; one judged not better is a model-change item, on the Items page).
  Every judging stamps what it read (`scored`: a **mark** of the record the scorecard reads, the store's last seq, for
  order only, and when) and clears `rescoring` and `rescore_error`, so a redesign made again under its id, or carried,
  keeps neither, nor an old stamp. The mark (`ergostat/numbers/redesign_record.py`) is model-wide and an allowlist: the
  newest seq of the events of the model's own kinds' items, of its own blocks' runs and of its own valves'
  openings; the latest reading of each of its own parts' sensors; and the model itself (its dynamics, control, sensors,
  words, units and kinds). The judge's, the redesigner's and modelling's own events, and a `once` template's parts, do
  not move it. It is compared for equality only, never by age. **A redesign waiting for the owner is scored again at
  most once every 30 minutes, and only when the record it reads has moved**, one a pass (first judgings and the write
  aside), least recently scored first; still better, it stays passed with the new scorecard; else it is failed, "no
  longer better on the record as it is now", and its system rests as after any failed redesign. Sensors read every
  few seconds move the mark nearly every pass, so in practice a waiting redesign is scored again about every 30 minutes,
  and most promoted ones are scored again when they are written. A mark that cannot be read fails closed: every passed
  redesign says `rescoring` with why (the review queue shows it), written once, not each pass; nothing is scored or
  written that pass, of any class (words and parameter changes too, not only redesigns), and the next pass that can
  read it scores them again at once, one a pass. **A promoted redesign is written only on a scorecard of the record as
  it is**: in one hold of the proposals' lock it is read again, its mark held against the record's, scored again when
  they differ (or it says `rescoring`), and written only if still better. With `reviewed: [redesign]` that hold also
  reads the reviewer's verdict again, and writes it only if the reviewer passed it as it stands then. A verdict that
  lands after the write loop's copy was read counts too. A rescore makes a new verdict, so the reviewer's pass, stamped
  with the verdict it read, would go stale and send the redesign back to the reviewer every 30 minutes. A rescore that
  is still better **keeps the reviewer's reading** instead: the edits it read are the same, and the review is stamped
  again to the new verdict (`kept`). A failed rescore keeps none. A first judging keeps none either, since one made
  again or carried is read again. So a reviewed redesign is written on the scorecard of the record as it is and on a
  review of the same edits, and the reviewer is not called again, against the daily cap, for every move of the record.
- **Never written without the owner** unless the class is promoted by name: `accept: {redesign: auto}`; `accept: auto`
  for every kind leaves it the owner's (promoted and passed, it is written first, alone in its pass; one that cannot be
  written is superseded, and the pass goes on). Even promoted, a redesign that takes a part away, rewires a kind's chain
  (a flow between two state stocks re-pointed, added or taken away: `rewires`) or changes control (`control`) waits
  for the owner. No change, a redesign or any other, may change who decides: one that alters the judge's policy, a
  block's `accept` or a template instance's `with:` is refused. While one waits,
  the judge writes no other change whose lines clash with it; a change written that does not clash moves its lines, and
  it stays waiting (carried by `proposals.supersede`, under the proposals' lock), back to checked and shown as
  rescoring until the judge scores it again on the model as it is, held to who-decides, its owner flags and its scope
  again (a carried description or unit goes back to checked too). While one is being made (a run started and not ended, for its first 5 minutes at most,
  so refinement is never frozen by a slow run), the judge writes nothing on its own, so the model the redesigner reads is the one its change set is made
  on; if the model moved anyway (the owner wrote a change), its edits are made again on the model as it is.
- **The redesigner** (`ergostat/numbers/redesigner.py`; the template's block `redesigner`, an `ai` block, there with
  `ai: true` unless `redesign: {when: off}`): given a whole system (or the whole model) as written, what `check` finds,
  the coherence report, the moves the process map observed, the record's summary (each stock's fit, the event types
  seen) and the guides (`library/templates/modelling/redesigner.md`, the modeller's craft, the review checklists of
  `docs/MODELLING-WELL.md`, read through the help documents, so an installed ergostat has them), it answers one change
  set. Each round its edits are made on the scratch copy, which is
  compiled, checked, held against the record and scored, and what is left (an edit that could not be made, an error, a
  finding, a mismatch, the scorecard) is given back for the next, up to `rounds`; the best round's copy is proposed.
  No call starts once `budget` dollars are spent; every call's cost is kept on the change and printed as a Claude Code
  result line, so the run's cost is the run's (`ergostat.cost.*`, `run/redesigner/cost_usd`).
- **When**: with `when: auto` (the default), on its own, a **system** at a time (`numbers/redesign_due.py`): the
  model's systems (its own, not a once template's), each of at most 40 parts, else its subsystems; a system too large
  with none to split into is held for the owner as a request (`too-large`: split it), never attempted whole; a model
  with no systems of its own is one unit. A system is due when its replay is worse than its mean (a stock's scaled
  error over 1) on at least 30 minutes of record; when a finding says its structure is wrong (`measured-not-caused`,
  `loop-not-identifiable`), or a structural one (a kind's chain, the boundary, a coherence mismatch) has been held for
  an hour; when refinement stalled on it (its last 4 changes turned away); on the first run; and once a day. Bounds:
  at most one redesign waits for each system, and systems equally due take turns; after one judged not better,
  refused, dismissed or superseded, one that made nothing, or a run that never ended (its request closed, saying so),
  the system rests 6 hours unless its own parts changed since (a hash of them, not the model's version); the cap is
  checked before anything is planned; the runs stop for the day once they have spent `daily` dollars,
  each call charged as it is spent (one that never says its cost charged its estimated most, `modeller.unsaid`). And when the owner
  asks (`ergostat improve --redesign [SYSTEM]`, or the Model page's Redesign button), recorded as
  `ergostat.model.redesign-asked` and taken up first; `when: ask` takes only those, `off` none. Each run is recorded
  (`ergostat.model.redesign-ran`: started, each call's cost, then what it made), and its trigger and result are held as
  a modelling request about the system (`source: redesign`, on the Items tab; `ergostat status` says the last). What
  it makes is written only with the owner's approval (the review queue, the inbox, its notifications), unless
  `accept: {redesign: auto}`.
- **What it learns from** (`ergostat/numbers/redesign_memory.py`). Its prompt also carries, for the system:
  *what was proposed before*, its past change sets (for the whole model, every system's) newest first, each with what
  became of it (proposed, judged better or NOT better with the scorecard's verdict and why, refused with why,
  accepted, dismissed with the owner's reason), its summary and its edits, and the other changes about its parts the
  owner dismissed with a reason; at most 6, 3,000 characters together, 600 each; and *interventions: evidence of
  missing loops* (§12p), by class over the interventions loop's window, the most hours blocked first: how many, their
  causes, how they were answered, the notes given with the answers (`inbox --note`, a person's report, a dismissal's
  reason; not only the owner's: a person block's report and whoever approved or denied an advised block's command
  are read too, each note once), and the class's request from `ergostat inbox --requests` with its state and the note it was worked
  on with (not its remedies: generic, they led haiku to add a goal and a controller for
  every class, and its change sets stopped compiling; `docs/redesign-bench.md`); a class is the system's when its block, or a part its cause names, is in it; at most 8, 2,500 characters.
  The guide says never to propose again what was dismissed or judged not better unless the record now answers the
  reason given, and to read each recurring intervention as a loop the model lacks, with a lookup from symptom to
  structure (a queue that builds only in bursts: a capacity; items seen twice: rework; a part that lags another: a
  delay or a stock between; a level that settles whatever its start: a balancing flow).
- **Its architecture** (`redesigner.architecture`). A redesign of a system is shown that system's architecture, from
  the structure alone (no run, no call), in a section of its own: its size (`architecture.size_said`), its interface
  (each port's part, kind, direction and peers, at most 30 listed and the rest counted), its subsystems and whether
  it is nearly decomposable. For the whole model: its size and each top system's. Its "What check finds" section
  holds the architecture notes on the system and on the systems within it (`system-splits`, `systems-merge`,
  `interface`, `time-scales`, `purpose`), and not those on other systems (`redesign_due._in`: a `system.S` note
  is a unit's when the unit is S or S lies within it; every note is the whole model's).
- **The daily architecture review** (`ergostat/numbers/archreview.py`, guide `architect.md`). Once a day, inside the
  redesigner block's run and before it plans, one call (no retry, tools off) on `review`, a model larger than haiku
  (sonnet by default, the owner's allowance in the overnight note of 2026-11-19: the redesign and architecture
  reviews may use a larger model, their costs recorded), reads the model's architecture as a whole: check's
  architecture notes, each system's size, interface counts by kind, subsystems, nearly-decomposable line and
  description, each unit's replay fit by stock, each unit's last redesign result, and the units too large to
  redesign; never the YAML; at most 40,000 characters and 60 systems. A part it cannot read (check, the fit) is
  said as unknown, never as fine. It answers JSON lines `{"review": {"system", "advice", "says"}}`, read by
  allowlist: `advice` is `redesign`, `split` or `merge`; a redesign's system is a unit the redesigner can take (or
  `model`), a split's or merge's one of the model's own systems; `says` is cut to 600 characters; at most 8 are
  taken, the first for a system and advice kept, and what is dropped is said on the review's event. Each is held as
  a modelling request (`source: redesign`, so the collector never answers it as "check no longer finds it"),
  `review-redesign`, `review-split` or `review-merge` about the system, stamped with the review's event
  (`review`). A `review-redesign` is open, and makes its system due before those due only for their daily review
  ("the architecture review: ..."); a system resting is still not taken. A `review-split` or `review-merge` is held
  for the owner and never acted on: it moves parts between systems, which is structure. One the review raised
  before and does not say again is answered ("the architecture review no longer says it"), but one `proposed`,
  waiting on its change; one said again is written again, its old change and why cleared. The run that takes a
  review's request up marks it after (proposed with its change, or answered with the result) only if, read again
  under the locks, it still carries the stamp the plan read: a newer review that said it again meanwhile leaves it
  open. The review writes no model change and edits no file.
  - *When*: with `when: auto` only (never `ask` or `off`; never with `review: off`), and only when no
    `ergostat.model.architecture-reviewed` event but a `capped` one is in the last day: a review that started
    (written before its call), failed (its call failed, or its answer had no JSON line) or reviewed is the day's, so
    a failing call is not retried each run.
  - *Cost*: within the redesigner's `daily` cap, on the redesigner's side of it. It is not called when its
    estimated most (`modeller.unsaid`) is more than the redesigner's block has left (`redesign.room`: what is left of
    the cap, and never the quarter kept for the reviewer), said on the log with an `architecture-reviewed` event,
    `capped`. That check and the estimate's charge are made under the lock `redesign.held` takes, so the reviewer and
    the review do not both start calls on one remainder. The
    estimate is charged before the call (`redesign-ran`, `result: call`, `by: architecture-review`) and the
    difference after it, so a run killed mid-call keeps the estimate charged. The bound is that estimate: `claude
    -p` takes no output limit, so a call can cost more. Its cost is printed as a Claude Code result line, and its
    event holds the model, the cost and the requests it raised. The redesign that follows gets what is left of
    the cap, read again after the review. Time: after a review that called, the review's call and each round's call
    are each given one share of the block's timeout in rounds + 1 (`archreview.timeouts`, through `per_call`), so
    their limits together are what the rounds' alone would be on a day with no review.
  - *The lock*: the review (due, cap, call, requests, event) and the mark after a redesign hold `redesign.lock` in
    the project's state directory, taken without waiting: a run that finds it held skips the review, or leaves the
    request unmarked, and says so.
- **The benchmark** (`scripts/redesign_bench.py`, `docs/redesign-bench.md`): models of known structure
  (`tests/redesign_cases/`) each cut (a capacity limit, a rework loop, a delay, a goal gap, a stock merged away, an
  outflow), the record made from the whole model, the redesigner asked to repair the cut one (nothing submitted), and
  each case scored: the missing structure found again (by place and shape, a rename followed by `formerly:`, and
  working on the truth's record: the flow moves something, the limit binds, the goal's sign closes the gap, the delay
  takes what leaves the stock before (how long it delays is not checked: a DELAY3 of near-zero time passes);
  necessary for a repair, not sufficient), the parts added beyond the known
  repair's, the fit before and after, compiled, the verdict, the cost; `--without memory,interventions` for an
  ablation; haiku by default under a cap for the run ($3), `--stand-in` for the
  harness alone; one JSON row a case appended to `docs/redesign-bench.jsonl`.
- **Drawn as proposed**: `GET /api/graph?proposal=ID&view=dynamics|blocks` draws the model as the change would leave it
  (nothing written), with `proposed: {added, changed, renamed, removed}`; the page draws the new parts dashed and
  tinted, the changed and renamed dashed, and names what it takes away; the review section's Dynamics and Blocks
  buttons open it.

The template's parameter: `redesign: {when: auto|ask|off, model: haiku, budget: 0.5, rounds: 3, daily: 2, review:
sonnet|off}` (and `redesign-every`, 10m). `review` is a decision taken here, the most reversible form of the
owner's allowance: it exists only with `ai: true` and `when: auto`, stays inside `daily`, and `review: haiku` or
`review: off` changes it (unquoted: the model's YAML takes only `true` and `false` as booleans, and `review: false`
is `off` too). `modelling redesign` itself takes `--review` (a model's name or `off`; `off` when not
given, so a run by hand reviews only when asked to).

### The reviewer: a senior modeller reads what the judge passed

The judge reads a change by the numbers only (the replay on record its author never saw, a redesign's scorecard). A
change can fit better and still be wrong. **The reviewer** (`ergostat/numbers/reviewer.py`; the template's block
`model-reviewer`, so as not to clash with a model's own `reviewer`; an `ai` block, there with `ai: true` unless `review: {when: off}`, on haiku by default) reads each change of
the kinds the judge's `reviewed:` names (the template's `review.kinds`: `structure` and `redesign`, `equation` when
named) once the judge has passed it, and before it is written or offered to the owner. Its prompt
(`library/templates/modelling/reviewer.md`) is deliberately disagreeable and carries the review checklists of
`docs/MODELLING-WELL.md` (section 5, *Reviewing a change* first: the causal story, units and boundary, fitting noise,
one coherent change, the behaviour it predicts), the change (its reasons, the judge's verdict, a redesign's edits with
their whys), its diff and the model near it.

| Verdict | Recorded | What happens |
|---|---|---|
| `pass` | `ergostat.model-change.reviewed` (from `reviewer`, no move of state): `review: {verdict, findings, summary, round, author, cost_usd, read}` | the judge's policy may write it; the inbox offers it to the owner |
| `revise` | the same, then `.superseded` ("sent back to AUTHOR by the reviewer: ...") | back to its author (a block of rung `ai` or `person`): its next proposal on the same parts (a redesign: of the same system, asked for again at once) carries `revising`, `review_round: 2` and `review_asked`, the findings, and is read as the second round. A second revise is a **reject**, and every revise on those parts in the last day counts (a second round the judge failed is still the second round); after two, the author's proposals on them are held back for the day. A change no author can revise (ergostat's finders, a program, the owner's what-if) stays passed and goes to the inbox with the findings, for the owner; the judge never writes it, and a redesign so left holds no lines |
| `reject` | the same, then `.failed` (the verdict "the reviewer rejected it: ...") | it leaves the queue, and the memory (*Turned away, remembered*) holds the same target back |

Each verdict needs a specific finding (`{"check", "says"}`) unless it is a pass; an answer without one records nothing,
and the change is read again on the next run, at most 3 times on the change as it stands (each call is stamped with
what it read, and calls on an earlier version do not count): then it is recorded `undecided` ("the reviewer could not
decide") and goes to the inbox for the owner, and the reviewer moves on. A review holds for the change as the judge last
passed it: each is stamped with what it read (`read`: the judge's verdict and the edit, fingerprinted), and one made
again under the same id, revised or carried and judged again has another stamp and is read again. A waiting redesign
the judge scores again as the record moves (section 12e, *Redesign*) is not read again: the rescore makes a new
verdict, which would make the review stale, so a rescore that is still better stamps the review again to it (`kept`).
A failed rescore leaves the review nothing to hold. The verdict is
recorded under the changes' lock and only if the change is still the one it read; one that moved on during the call
records nothing and is read again. **The authors remember:** the improver's input (`reviewer`), and the
modeller's and the redesigner's prompts ("The reviewer on your recent proposals") carry its latest five verdicts on
their own changes (each on the version as it stands), with the findings, so they stop repeating what it rejected and answer what it sent back.

**With the accept policy.** With the reviewer on, a change of a reviewed kind that the policy would write waits for the
reviewer's pass; one that waits for the owner reaches the inbox only after it. The owner may still accept it from the
review queue at any time (the owner asks; the review queue shows the reviewer's verdict beside the judge's).
**Cost:** each call is recorded (`ergostat.model.review-ran`, its dollars) and counted with the redesigner's against the
template's one daily cap (`redesign.daily`): neither the reviewer nor the redesigner starts a call whose estimated most
is more than is left of its share, and what waits for a review stays unwritten. The estimate (`modeller.unsaid`) is
its prompt at a token for three characters, claude's own system prompt (20,000 tokens) and 16,000 tokens written, at
the model's price. It is an estimate, not a bound: `claude -p` is given no limit on what it writes, so a call that
writes more can cost more than its estimate, and the day can end a little past the cap. What is left is read again
before each call, and the call's estimate is held against the cap while it runs (`ergostat.model.ai-held`, checked and
held under one lock, let go once its real cost is charged, kept for the day if the call fails), so the two running at
once do not both start calls on one remainder. A quarter of the cap is kept for the reviewer: the redesigner stops at three quarters of it.
**Measured:** `ergostat.model.reviews-passed`, `-revised`, `-rejected` and `review-misses` (changes it passed, in the
version that was written, that the prediction check later flagged for revert, §12f); the template's flow `changes-sent-back` counts what it rejected or
sent back from the passed changes. The template's parameter: `review: {when: auto|off, model: haiku, kinds: structure
redesign, most: 3}` (and `review-every`, 2m).

### The loop, in the model

One line, `uses: {modelling: {use: modelling}}` (the built-in template `modelling`, section 2a; `docs/ADDING.md`
gives its parameters: the improver's rung, prompt, command and schedule, the fit the goal holds, how often the
parts are read, and the judge's schedule, hold-out, windows, threshold and `accept` policy), which expands to plain
YAML, like any loop (`examples/image-squeeze/model.yaml`, `examples/the-job/job/modelling.yaml`): the model's
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
numbers, is never written on a verdict reached on another version: carried back to testing, or superseded, by the
judge or by hand. Under the default policy (`accept: owner`) the
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

*Then* (2026-11-18, from fresh 20-minute image-squeeze runs where the gate and the judge accepted
`images-per-hour` near 2,180 after 11 minutes, where the world compares 4,500 an hour): the equation counts an
experiment's whole open time (`images-per-hour * MIN(stock.experiments, 1)`), so the estimate is the record's
comparisons per open hour, and in the first minutes that share is set by one or two experiments (a first build, or
candidates dropped within a minute, are open and compare nothing); the replay of `paired` carries each such mismatch
forward, so its errors drift together (lag-one autocorrelation 0.87 to 0.97), and 50 to 80 readings held 1 to 4
independent points. The estimator asked for ten only where the error left was past a tenth of the spread, and a
block's value was not asked at all, so the stand-in re-submitted the declined estimate and the judge decided it on four
minutes of the same regime; the standard error, ±12, took every reading as independent. On fresh copies (three runs,
estimates 3,516 to 4,232 between 11 and 17 minutes), every such estimate is now held, inconclusive, with "it needs
about 24m to 2h more record", and the stand-in's resubmission is recorded inconclusive and held back as long; an hour
gives 4,460, which drifts still and is not proposed (4,500 is right). On a copy of the owner's aged record, where the
lab compared for 40 minutes and then for 15 hours not at all, the calibration had 3,885 ± 9 (three hours) and 6,114 ± 8
(now) ready to propose; both are held: what it acts through moved once or twice. `bench judge`: 0 false accepts and 0
false rejects over 240 trials, as before. `bench improve`, stand-in: unchanged (recall 11/16, 17 written, 14 real, 2
damaging); calibrator: recall 6/16 as before, 18 written (11 real, 6 damaging) where it wrote 20 (9 real, 8 damaging).

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
| `ergostat.model.reviews-passed`, `.reviews-revised`, `.reviews-rejected` | The reviewer's verdicts (§12e, *The reviewer*) |
| `ergostat.model.review-misses` | Changes the reviewer passed that the prediction check later flagged for revert (`regressed`) |

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

A claim line is recorded when the run prints it (section 9.1); after the run ends (`agent.ran` or `agent.failed`
recorded), each claim it made is checked in turn. Without `check`,
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

## 12k. Where an AI session works, and what it may do

An `ai` block's run is a Claude Code session: it reads and changes files and runs commands. Two things decide what it
can reach: the folder it starts in, and the tools it is given. Both are declared on the block; the outward acts (a push,
a pull request, a ticket moved, a message posted) are not tools at all, but **gated actions**, which ergostat runs for
the session only as their gate says. A `program` block may take a workspace and ask for gated actions too (below,
"From a program block"): the same gate, without a session to sandbox.

### Its folder

- **Today, with nothing said**, an `ai` block without `run:` runs `claude -p` in the model's folder (the one holding
  `ergostat.yaml`), and one with `run:` runs that command there: `ergostat session` then starts `claude -p` wherever it
  was started, the model's folder unless the wrapper moved (image-squeeze's `bin/ai.sh` starts it in the example's
  own folder, and the session works on `run/product/` from there). Claude Code's file tools reach that folder and
  below; what it runs with Bash reaches what the user running ergostat may reach.
- `workdir: DIR` (from the model's folder, or a whole path; `~` for the home folder) starts the session there.
- `workspace: POOL` starts it in the workspace its pool gives the item the run works on (below).
- `read: [DIR, ...]` are more folders it may read (`--add-dir`); with the sandbox on (below) it may not write them.

The session's `claude -p` runs in that folder (so its transcript is filed under it), and its run's environment says it:
`ERGOSTAT_WORKDIR`, and with a workspace `ERGOSTAT_WORKSPACE` and `ERGOSTAT_BRANCH`. A block with `run:` keeps running
its command in the model's folder (its paths are written from there); `ergostat session` takes the folder from the
run (`ERGOSTAT_SANDBOX`, below) and starts the session there. `session.started` records `workdir`.

### Workspace pools

```yaml
workspaces:
  code:
    repo: run/product              # a git repository (from the model's folder, or a whole path)
    pool: run/workspaces           # where its worktrees go (default: workspaces/NAME in the state directory)
    size: 3                        # how many
    branch: "{kind}/{id}-{slug}"   # the item's branch: ticket/12-fix-the-login-page
    base: main                     # what a new branch starts from (default HEAD)
blocks:
  developer:
    type: ai
    prompt: prompts/developer.md
    workspace: code
```

| Key | Default | Meaning |
|---|---|---|
| `type` | `git` | How a workspace is made: `git`, a worktree of `repo` (the only kind yet; a workspace is a folder with an acquire and a release, and another kind needs only those) |
| `repo` | required | The repository |
| `pool` | state directory | The folder its workspaces are made in, one subfolder each (`1`, `2`, ...) |
| `size` | 2 | How many workspaces |
| `branch` | `{kind}/{id}-{slug}` | A template from the item: `{kind}` (its id before the /), `{id}` (after it), `{item}` (whole), `{slug}` (its `title`, `name`, `summary` or `idea`, in lowercase words), or any field of the item; made a safe ref |
| `base` | `HEAD` | The ref a new branch is made from |

**The item a run works on** is its lease's (`ERGOSTAT_ITEM`, with `ERGOSTAT_LEASE`, in the run's environment), else its
context's item (§12j), else the item its command names. A run with a workspace and no item does not start
(`agent.failed`, saying so).

**Acquire.** At the run's start, under the pool's lock:

1. a workspace the item has already (in use, or held for it) is given back as it is, its work in progress with it: a
   retry, or more work after review;
2. else a free workspace that exists is checked (a worktree of the repository, nothing uncommitted) and reset for the
   item: onto its branch, made from `base` unless it is there already; one that fails the check is **quarantined**;
3. else a fresh worktree is made, on a new branch from `base` (or the item's branch, when the repository has it);
4. else none is free, and the run does not start (in use, held and quarantined counted, in its `agent.ran`'s note):
   not a failure of the run or its item, so a leased item is given back put off for ten seconds and not counted
   (`{"nack": ..., "count": false}`), and taken again when a workspace may be free. Any other reason one cannot be
   given (a worktree that cannot be made, no item named) is `agent.failed`, and counted.

**Release**, when the item's lease ends (`ergostat.lease.ended` or `.expired`), or when its run ends if it had no lease:
while the item is not finished (the end's `terminal` says; otherwise the states `messages: {done:}` gives, else its
kind's last state or a dead letter) its workspace is **held** for it, its work kept for review or for the next attempt;
once the item finishes it is **cleaned**: detached at `base`, untracked files removed, its branch left in the
repository; a workspace dirty or broken when cleaned is quarantined instead, nothing in it thrown away.
`ergostat.lease.taken` makes a held workspace in use again, under the new lease. The dispatcher takes each lease event
it records to the pools at once; ergostat's clock (every five seconds) takes every lease event to them (those another
process recorded: `ergostat lease ITEM --nack`) and cleans what is held for items that have finished since.

**Fencing.** A workspace is recorded with the fencing number of the lease it was acquired under (`lease`), and the
lease events act only on the workspace their fence holds: the end of a lease a later one replaced changes nothing, so
the events may be taken again (after a restart) to the same effect. A lease that expires while its run still goes on
holds the workspace **fenced** (`fenced`: the run and its fence): the next lease on the item takes it, its work with it,
and the old run's item events (§9.5) and gated actions are refused. A gated action records the lease it was asked for
under; it is denied when asked for, and fails unrun when approved, once that lease has expired or a later one has been
taken on the item. An action asked for under a lease that ended (ack or nack) and was not taken again still runs once
approved: its item waits for review. An action declared `fenced: false` is never fenced: once approved it runs
whatever became of the lease it was asked for under. That is for an action whose own command keeps it safe whenever
it runs, such as a push of one exact commit that the remote refuses unless it is a fast-forward.

**Quarantined** workspaces are never given to an item; `ergostat workspaces POOL --free N` (the owner) removes that
worktree, and the slot is made afresh when next needed. Each workspace is an item, `ergostat.workspace/POOL-N`
(states `free`, `in-use`, `held`, `quarantined`; events `ergostat.workspace.acquired`, `.held`, `.released`,
`.quarantined`, `.freed`, each saying the folder, the item, the branch and why). `ergostat workspaces` lists them.

| Measure | What it is |
|---|---|
| `ergostat.workspaces.free` | Workspaces free, now; `@POOL` for one pool |
| `ergostat.workspaces.in-use` | Workspaces an item's run has, now |
| `ergostat.workspaces.held` | Workspaces kept for an item under review, now |
| `ergostat.workspaces.quarantined` | Workspaces found dirty or broken, now (each needs attention) |

*Leases* (§9.5: `ergostat.lease.*`, `ERGOSTAT_ITEM`, `ERGOSTAT_LEASE`) are what the pool reads: the work item is the
event's `data.item` (else its own item), the lease its `data.fence`, and an end's `data.terminal` whether the item
finished.

### Gated actions

```yaml
actions:
  git-push:
    run: git push origin HEAD:refs/heads/{branch}
    gate: approve                  # auto | approve | deny
    class: push                    # counted with the others of its class (default: its name)
    description: Push this workspace's branch to origin
  open-pr:
    run: gh pr create --head {branch} --title {title} --body {body}
    gate: approve
    args: {title: the pull request's title, body: what it changes and why}
    wait: 15m                      # how long the session waits for the owner before going on (default 5m)
    timeout: 2m                    # how long it may run (default 2m)
    # fenced: false                # run once approved even after a later lease took the item (default true)
    risk: {severity: 3, threshold: 8}   # one step stricter when this act is riskier than its class (below)
blocks:
  developer:
    type: ai
    prompt: prompts/developer.md
    workspace: code
    tools: [Read, Edit, Write, Glob, Grep, Bash]
    actions: [git-push, open-pr]
```

An action is a command template. `{name}` is one of its `args:` (what the session gives, each a string, all
required), or ergostat's own: `{item}`, `{branch}`, `{workdir}`, `{block}`, `{run}`, the session's, not the session's
to say. Every value is shell-quoted. It runs in the session's folder (or `in:`, from the model's folder), with
`ERGOSTAT_ACTION`, `ERGOSTAT_ITEM` and `ERGOSTAT_BRANCH` set.

The session asks for an action as a tool: ergostat runs an MCP server for it (`ergostat.actions.server`, its tools
`mcp__actions__NAME`, one per action the block names, and `action_status`). A call is recorded, `ergostat.action.requested`
(an `ergostat.action/ID` item: the action, its class and gate, its arguments, the command exactly as it would run,
where, and the block, run, session and work item), and then by its gate:

- `deny`: `.denied` (by `gate`), never run; the session is told.
- `auto`: `.approved` (by `gate`), run at once; `.ran` or `.failed`, its exit and output, are the call's answer.
- `approve`: **held** for the owner. It needs attention (the status, the page's list, its work item's page) until the
  owner answers: `ergostat actions ID --approve` (or `--deny`, with `--note`), or Approve / Deny on the item's page
  (`POST /api/action/ID/approve`), or from the inbox (section 12o), which can also send it to the owner (`notify:`).
  The answer is an event from the owner. The session's call waits for it, up to
  `wait`: approved meanwhile, the server runs it and gives the session its output; denied, it says so. When the wait
  runs out the call answers that it is held, and the session goes on; approved later, the action runs at once (by
  whoever approved it, else ergostat's clock), and its result goes to the block's **next run**, under `actions` in its
  input, with the actions still held. Each result given is `.delivered` (how: `session` or `context`). An action runs
  once: the first to take its lock runs it.

**Act-risk.** An action may declare `risk: {severity: S, threshold: T}` (`ergostat/actions/risk.py`, plain
arithmetic). Each request for it is then scored, and its gate moves one step stricter when the score reaches T:

    act_risk = S × (1 + 4c) × (1 + n)        step  ⇔  act_risk ≥ T

A step goes from `auto` to `approve` (held for the owner) or from `approve` to `deny`, never the other way; `deny`
stays `deny`. An action without `risk:` is gated by its `gate:` alone. `S` is a whole number from 1 to 5 (not `true`);
`T` a number above 1 and at most 50 (not NaN or infinite), default 8. Anything else is `bad-value`, said where it was
written. Scores run from 1 to 50, and T is absolute, not a multiple of S, so severity alone can change the outcome.

- `c` is the asking block's contradicted share of its checked claims over the last week (as
  `ergostat.trust.contradicted` counts them). Each case where it cannot be read counts as the worst, c = 1, its reason
  recorded: `claims record unreadable`, `no asking block`, `no claims on record`, `claims made, none checked`. A share
  that is not a finite number counts as 1; any other is held to [0, 1]. A request that names no block (one the owner
  makes) always has c = 1, so an owner's own `auto` request with S ≥ 2 is held for that owner: intended, since no
  record vouches for it.
- `n` is novelty: 0 only when the record holds another action of the same name that reached `ran` (exit 0) within the
  last 90 days, else 1. One that only `failed` does not count; neither does an unreadable record (`action record
  unreadable`, n = 1). It is keyed by the action's name: an action whose command was changed under the same name
  counts as known, so "novel" never means "this command never ran".
- The staleness of the state the act was planned on is **not** part of the score.

The score is worked out before `requested` is written and recorded on it, `risk: {score, severity, threshold, c,
c_why, n, n_why, gate}`, `gate` being the stepped gate, which then decides as `gate:` does. A stepped gate says so in
its denied or held note ("act-risk 12 ≥ 8: its gate auto stepped to approve"), and the session is told it.

**At the act**, for every action, inside its run lock, after the fence check and before the command starts, the
model is read again (an in-memory model with no file: the one given). Unreadable, the action is **held again**: a
`requested` event with `held_by: act-risk`, its note, and `approved_by` cleared, written before the lock this run
took (`<short id>.run`) is removed by its name, so a sweep finds it held and the owner's later approval runs it.
Gone from the model, it is `denied` by `gate`. Otherwise its gate and `risk:` as they are now are scored on the
record as it is now, and the **effective gate** is the stricter of that and the request's stepped gate (the first
`requested`'s `risk.gate`, which a re-hold never replaces; its `gate` without `risk:`): `deny` is denied, even when
the owner approved it; `approve` runs if a person approved it and is held again if only `gate` did; `auto` runs. The
act's reading is recorded on the event that ends it (`ran`, `failed`, `denied` or the re-held `requested`) as
`risk_at_act`. So a gate is never looser than its `gate:`, at the request and at the act. A claim verdict, or the
owner's edit, recorded between the request and the act is seen at the act; one recorded after the act's re-check, in
the moment before the command starts, is not.

Actions are counted by class: `ergostat actions` lists them and, per class, how many were held, approved by the
owner, let through by the gate (auto), denied, ran and failed this week; a class the owner has approved five times or
more and never denied is said to be ready for `gate: auto`. **Promoting** a class is the owner's edit to the model
(`gate: auto`), never ergostat's, and takes effect at the next request; a gate made stricter takes effect at the act
too, for what was approved before it (above): the refactor path (invariant 5) from a person approving to a rule.

| Measure | What it is |
|---|---|
| `ergostat.actions.held` | Actions waiting for the owner, now; `@CLASS` for one class |
| `ergostat.actions.approved` | Approved by the owner, over the last week |
| `ergostat.actions.auto` | Let through by their gate, over the last week |
| `ergostat.actions.denied` | Denied by their gate or the owner, over the last week |
| `ergostat.actions.ran`, `.failed` | Run, and exited 0 or not, over the last week |

### From a program block

Most outward acts are made by plain programs: a step script that moves a ticket, labels a pull request, posts a
comment. A `program` block (or an `ai` block whose `run:` is a program of its own, not `ergostat session`) names the
actions it may ask for the same way, and may take a workspace:

```yaml
blocks:
  open-pr:
    type: program
    takes: {kind: ticket, at: worked, to: [pr-open, stopped]}
    workspace: code                # its item's workspace: ERGOSTAT_WORKSPACE, ERGOSTAT_BRANCH; it runs in the model's folder
    actions: [git-push, open-pr]
    run: python3 steps/open_pr.py
```

Its command asks for one with **`$ERGOSTAT_CMD act NAME --arg K=V ...`** (`--key K`, `--wait DUR`, `--json`), during
the run, and is answered when the gate has taken it:

| Exit | The action | What the call printed |
|---|---|---|
| 0 | ran, exited 0 | its output, on stdout |
| 1 | ran and failed | its exit and output, on stderr |
| 3 | held for the owner (or approved and not run yet, when the wait for ergostat ran out) | how to approve it, on stderr |
| 4 | denied, by its gate or the owner | why, on stderr |
| 2 | refused: not one of the block's `actions:`, an argument missing or not its own, not this run's | why |

`--json` prints the action as a session is given it instead. A command, not an output line: an output line is read
when the run has ended, and the act's result (a pull request's number) is wanted during it.

- **Run by ergostat, not by the program.** The run's environment names the file of what it was given
  (`ERGOSTAT_ACTIONS`: its block, run, item, lease, folder, branch, and its `actions:`), which `act` reads and checks
  against `ERGOSTAT_RUN`. An `auto` action, or an `approve` one once the owner approves it, is run by the engine
  (`ergostat run`, which follows the record for approvals) with ergostat's environment, in the run's folder (its
  workspace, else the model's) or `in:`; the call waits for its result (its `timeout:` and half a minute more). The
  owner's `ergostat actions ID --approve` runs it at once, as for a session; ergostat's clock runs any approved
  one no one ran. A run started outside a running engine (`ergostat block NAME --now`) runs its approved actions in
  `act` itself.
- **The same request is the same action.** `act` with the same action, arguments and `--key`, about the same item (or,
  with no item, the same block and a `--key`), is answered with the action asked before: one held is answered as it
  stands (exit 3) and **taken over** by the asking run's lease (`ergostat.action.reasked`: its `fence` and `run`), so a
  run that gives its item back while it waits (`{"nack": {"why": "...", "after": "30s", "count": false}}`) and is taken
  again finds it, approved and run or not; one that ran is never run again, its output given again; one the owner
  denied stays denied, and one its gate denied while the gate is still `deny`. One that failed, or was denied by a gate
  since promoted, or by fencing, is asked for anew. Without an item or a `--key`, each request is its own.
- **Held, it waits** up to `--wait` (default: not at all) for the owner. A step that cannot go on without it gives its
  item back, put off and uncounted, and asks again on its next run; a result it never asked for again goes to the
  block's next run on that item (`actions` in its input), as a session's does.
- **Fenced** by the lease as a session's action is: asked for by a run whose lease on its item expired, or after a
  later lease was taken, it is denied; held and approved after a later lease took the item without asking for it
  again, it fails unrun (a later run that asks again gets it anew).
- Every request and answer is the same `ergostat.action.*` events, item and measures as a session's (`asker:
  program` in its data), and `delivered` (`how: run`) when the run that asked got its result.

**What is enforced for a program block, and what is not.** A program is not a Claude Code session: ergostat cannot
take tools away from it, and starts it with the user's environment, as every block's command.

- Enforced: what goes through `act` is recorded, gated, fenced and run once, by ergostat; a held action never runs
  before the owner's answer, a denied one never runs; the step cannot change an action's command beyond its `args:`
  (each one quoted argument).
- **Not enforced: the program can make the act itself.** A script that runs `gh pr create`, `git push` or `curl` to a
  ticket system directly is not stopped and not recorded as an action: the gate holds only the acts that go through
  it. With the program and ergostat running as the same user, with the same credentials, nothing ergostat does can
  change that.
- **The mitigation: run the program without the write credentials.** Because the action runs in ergostat's process,
  not the program's, the program needs none: start its command as another user or in a container that has only
  read access (`run: sudo -u steps python3 step.py`, a read-only token in its environment), and keep the credentials
  that write (a `gh` sign-in, a ticket system's token) where only ergostat, which runs the actions, has them. Short of
  that, `run: env -u GH_TOKEN ...` keeps an environment variable from the program (but not a file or the keychain it
  could still read). The examples that ship do not do this: their steps read through the same sign-in.

### The sandbox: what is enforced

A block with `tools:` or `actions:` is **gated**. Its session is started with Claude Code's own controls (checked
against Claude Code 2.1):

| Flag | What it does |
|---|---|
| `--restricted` | No user, project or local settings are read (a user's broad allow rules cannot widen it), file tools confined to its folders, bypass refused |
| `--tools A,B` | Only the built-in tools `tools:` names exist in the session (an empty list: none) |
| `--allowedTools` | `tools:` as written (`Bash(python3:*)` allows only that) and `mcp__actions` |
| `--permission-mode dontAsk` | Anything not allowed is refused, never asked (no one is there to answer) |
| `--disallowedTools` | Refused by name, whatever is allowed: `git push`, `git remote`, `git config`, `git send-email`, `gh`, `hub`, `glab`, `curl`, `wget`, `ssh`, `scp`, `sftp`, `rsync`, `nc`, `telnet`, `ftp`, `npm publish`, `twine`, `docker push`, `kubectl`, `open`, `osascript`, `WebFetch`, `WebSearch` |
| `--strict-mcp-config`, `--mcp-config` | No MCP server but ergostat's actions server |
| `--settings` | Claude Code's OS sandbox for every command it runs (`sandbox.enabled`, `failIfUnavailable`, `allowUnsandboxedCommands: false`): writes only in its folder, `$TMPDIR` and, for a worktree, what git needs to commit (the objects, the worktree's own git folder, its branch's ref and log); `read:` folders denied for writing; **no network** (no domain allowed, unlisted ones refused) |

**Enforced**, then: the session cannot run an outward command by name (refused by its permissions), and cannot run
one by another way either (a script, `python -c`, an alias): every command runs in the OS sandbox, where it cannot
reach the network or write outside its folder, so `git push` to a remote on the network or in another folder fails
whatever starts it. The real check (`scripts/gated_check.py`, on haiku) shows both: `git push` refused by the
permissions, `sh push.sh` run and refused by the sandbox ("unable to create temporary object directory" in the
remote), and the same push through `git-push` after the owner's approval.

**Not enforced**, said plainly:

- An action's own command runs outside the sandbox, with the user's credentials: the gate is what holds it, and what an
  approved action does is what its template says. Write templates that take as little as possible from the session
  (`{branch}` is ergostat's; a free-text `{body}` is only ever one quoted argument).
- Reading is not confined: the sandbox lets commands read the whole machine except what is denied (credentials such
  as `~/.ssh` are readable unless denied), and what a session reads it may put in an action's arguments.
- `$TMPDIR` is writable: a remote in a folder under it could be pushed to.
- The repository's git folder is partly writable, for commits: its objects, the worktree's own folder, and the folder
  of refs its branch is in (`refs/heads/ticket/` for `ticket/12-x`; all of `refs/heads/` for a branch with no `/`), so
  the session could move another branch's ref in that folder, though never push it anywhere.
- The OS sandbox needs Claude Code's support on the platform (macOS: Seatbelt; Linux: bubblewrap); without it the
  session does not start (`failIfUnavailable`), it never runs unsandboxed.
- MCP servers, hooks and Claude Code's own file tools are not in the OS sandbox; the file tools are bound by the
  permissions and `--restricted`.
- A block without `tools:` or `actions:` is not gated at all: its session has whatever the user's Claude Code settings
  and its `run:` wrapper give it (image-squeeze's own `--allowedTools`), as before.
- A `run:` wrapper that is not `ergostat session` is given `ERGOSTAT_SANDBOX` and must pass the flags itself; `check`
  refuses `tools:` or `actions:` on a block whose `run:` does not start `ergostat session`.

## 12l. Coherence: the three views held against each other

One system is drawn three ways: the **Process** view (§5b), how the items really moved, read from the record; the
**Dynamics** view, the stocks and flows that model it (for a workflow, one chain of state stocks, §12's *A kind's
states, chained*); and the **Blocks** view, what moves the work (blocks and their `out:` flows and `takes:`, goals and
their loops). `check` holds them against each other over the record (`coherence.py`): the last day, or `--since`. Each
disagreement is a finding with its file and line, the change when it is clear, the pair of views that disagrees, and
the findings `check` already reports about the same thing (linked, not said again).

| Pair | Finding | When |
|---|---|---|
| Process ↔ Dynamics | `move-without-flow`, `rework-without-flow`, `chain-skipped`, `order-contradicted` | items moved between two states with stocks and no path of flows carries them: the chain's own finding (`move-without-flow`, `outflow-not-chained`, ...), given the window's moves, with its fix. Named for what the record did: back to an earlier state (rework, ↺ on the Process view), straight past a stock the chain passes through (a skip), against the chain's flows (contradicted) |
| | `arrival-not-modelled` | items arrived (their first event) in a state whose stock no flow fills from outside |
| | `completion-not-modelled` | items finished (a state the kind counts as done, with no stock of its own) and no flow takes them out of the stock they left |
| | `flow-not-seen` (a note, one per kind) | the flows of the chain no item moved along in the window, those the record has not exercised said so (linked to `not-exercised`). Not counted against: quiet is not absent (§12e) |
| | `kind-not-chained` (a note) | a kind whose items move, with fewer than two states counted by stocks: the Dynamics view does not show how they move (nothing is wrong if they are a status, not work) |
| Dynamics ↔ Blocks | `waiting-without-goal`, `goal-without-loop` | a stock where items wait for the model's blocks (a block moves its outflow, or takes the items in its state) with no goal on it (or on an auxiliary it drives), or a goal no loop closes (linked to `missing-feedback`). A stock its blocks read and work off is a loop without a setpoint; a run's own work in progress (the same block fills and empties it) and a stock whose items wait on the world (every flow out is from outside) are not queues of the model's |
| | `flow-moved-by-nothing` | a flow of the chain no block moves (its `out:`, or a block taking the items at its source's state), not ergostat's leases (out of the stock of items being worked), and nothing measures (no sensor, no rate): what moves the work is not said. Each flow's mover is in `movers` |
| | `loops-not-connected`, `block-moves-no-flow` | the chain's finding of loops that share no stock, and a block taking items with no `out:` (linked to `no-visible-effect`) |
| Blocks ↔ Process | `acts-undeclared` | a block's runs moved items (the event's `source`, or `causedby` its run, up through events about no item) between states it does not declare: neither its `takes:` nor an `out:` flow carrying the move |
| | `moved-without-its-block` | items moved with no block's run behind them (a collector, a person, `event --add`) along a flow the model says a block moves, and that block did not act in the window (a block that ran, or a person block asked, whose effect a collector saw, agrees) |
| | `declared-not-seen-acting` | a block declared to move items (`takes:` or `out:`) when there was work for it (items reached its `at:` states, or its flows moved), and something else moved it on; with who did. Work no one has moved on yet, and a block no work reached (one note per kind), are notes |

**The score.** Each kind's agreements over its comparisons (`ticket: 41 of 44 agree (93%)`), each pair's in the JSON.
The record is compared only where there is enough of it: a kind with fewer than 10 moves, or 3 items, in the window
says how much more it needs (`needs 4 more moves of ticket in the window`); Dynamics ↔ Blocks needs no record and is
always compared.

**Bounded.** The window is read once by the Process view's own computation (its caps: the newest 50,000 events, the
moves of 20,000 items), the moves from the item index, and each finding's chain evidence from `chains.py` given the
window's moves.

**Where.** `ergostat check` (after the findings; `--json`: `coherence`; `--no-coherence` leaves it out), the MCP tool
`coherence` (`since`), `GET /api/coherence`, and the Check page's Coherence section.

## 12m. Reports upstream: when ergostat itself is wrong

When ergostat itself is wrong (it crashed, answered wrongly, or cannot express what a model needs), a **report** is
drafted for the owner: scrubbed, kept in the state directory, and submitted to ergostat's GitHub project by the owner,
by hand, if they choose. *Decided* (the owner, 2026-11-18): **ergostat never files one**: nothing here makes a network
call, runs `gh`, or opens the link it offers.

**Every report is an item.** `ergostat.report` is a built-in item kind (section 5a), its id
`ergostat.report/<short id>`:

| State | Reached by | Source |
|---|---|---|
| drafted | `ergostat.report.drafted`: `title`, `labels`, `origin` (`agent`, `owner`, `crash`, `modelling`), `by`, `file`, `scrub_file`, `scrubbed` (removals counted by rule), `version`, `commit`, and a crash's `signature` | who drafted it, or `ergostat` |
| reviewed | `.reviewed`: the owner has read it (`note`) | the owner |
| submitted | `.submitted`: the owner pasted it into an issue (`note`: its link, say) | the owner |
| dismissed | `.dismissed` (from drafted or reviewed) | the owner |

`.seen` moves nothing: the same crash, or the same report line, again (`occurrences`). A drafted report needs
attention, all of them in one line (`reports upstream: N drafted ...: ergostat report`).

**Who drafts one.**

- An agent: the MCP tool `report_upstream` (`says`, `details`, `parts`, `findings`, `repro`; without `says`, the list).
- The owner: `ergostat report --draft "what went wrong" [--details T] [--part P ...] [--finding CODE ...] [--repro FILE]`.
- ergostat, on its own crash: an unhandled exception in the engine's evaluation pass, an agent's run in the runner, a
  page server request (a 500) or `ergostat check`. One report a **stack signature** (the exception's type and the
  frames in ergostat's own code, by file and function, not line); the same crash again is counted on it, once a
  process. The machine's trouble (an `OSError`, a locked database, a stop) is not ergostat's and drafts nothing.
- A block, by a line: `{"report": "what ergostat could not express or do"}` (or `{"report": {"says", "details",
  "parts", "findings", "repro"}}`): one report a block and sentence. The modelling loop's improver (and redesigner)
  print it when the change a model needs is one the format cannot say (origin `modelling`).

**Scrubbed before anyone reads it** (`reports/scrub.py`). Kept: ergostat's version and commit, Python and the OS; the
error and traceback, ergostat's and Python's frames as they are (their code is public) with paths reduced to
`ergostat/spec/engine.py` and `python3.12/json/decoder.py`, any other frame reduced to its (scrubbed) place; the
model's shape (counts of parts, block types, sensor kinds, item kinds and their states, systems, sources, template
uses); the findings named; and a **reproduction** where one can be made: a tiny generic model, from the parts
involved and what they name (or the whole model, when it has at most 30 entries and no part is named), every name a
stand-in, descriptions and prompts left out, commands `echo 0`; or one the agent wrote, scrubbed like the rest. For a
crash in `check`, the reproduction is checked, and the report says whether it crashes the same way. Removed, each
replaced by a stand-in that is the same wherever the same thing was:

| Rule | What |
|---|---|
| `denylist` | the owner's terms: `reports/denylist.txt` in the state directory and `reports-denylist.txt` in ergostat's home folder (never in a repository); one a line, `re:PATTERN` for a pattern, `#` a comment |
| `secret` | `token=`, `password:`, `api_key=` and the like with their values; `Authorization: Bearer ...`; well-known key prefixes (`ghp_`, `sk-`, `xoxb-`, `AKIA`, JWTs); hex runs of 32 or more; long mixed-case base64 |
| `url`, `email`, `ip`, `host` | every URL but ergostat's own project's and localhost's; emails; IP addresses (not 127.0.0.1); host names with a known top-level or internal domain (`.corp`, `.internal`, `.local`, ...) |
| `path` | file paths on this machine (ergostat's and Python's own reduced, as above) |
| `ticket`, `mention` | ticket keys (`ABC-123`, not `UTF-8`), `@mentions` |
| `name` | the model's names: parts, item kinds and their items' ids (`ticket/12` becomes `kind-1/item-1`), their event types, states and shown fields (common words such as `open` and `done` kept), systems, sources, agents, parameters, uses, pools, contexts, the model's and its files' names; names of three characters or more; ergostat's own (the modelling loop's parts) kept |
| `user` | this machine's user and host names |

Item data is never put in a report. A last pass over the whole text removes any original removed elsewhere, and any
denylist term, wherever it reached the text. **Each report records what was removed and why** (`<id>.scrub.json`: the
original, its stand-in, the rule, why and how often), so the owner can check the scrubbing; the log stays in the
state directory and is never part of the text.

**Reviewed and submitted by hand.** Each report is a Markdown file, `reports/<short id>.md` in the state directory:
`Title: ...`, `Labels: ...` (suggested: `ergostat-report`, and `bug`, `crash`, `cannot-express` by origin), a blank
line, then the body to paste (*What went wrong*, *Where*, *Error*, *The model's shape*, *Findings involved*,
*Reproduction*).

- `ergostat report` lists them; `ergostat report ID` prints one (the text, the link to a new issue, the scrub log;
  `--log` the log alone); `--reviewed`, `--done` (submitted) and `--dismiss` mark it (`--note`).
- Its item page shows the text with **Copy the body**, **Open a new issue on GitHub** (a link to
  `github.com/danroblewis/ergostat/issues/new` with the title and labels filled in; the owner opens it and pastes the
  body; nothing is sent), the owner's marks, and the scrub log. (`GET /api/report/ID`; `POST /api/report/ID/reviewed`,
  `/submitted` or `/dismissed`.)

## 12n. The impact of a change: what a fix restores, and when to roll it out

A fix for a failing program, or a change to the model, comes with the research a careful operator expects before
approving a change, worked out from the model (`ergostat/numbers/impact.py`, its fields in `impact_fields.py`). It is
shown on the item page of the failure (`ergostat.failure/ID`, the repair loop's) or of the change
(`ergostat.model-change`), with no page of its own. `GET /api/impact?block=NAME|item=ID|change=ID[&began=T&within=S&penalty=H]`
(`began` epoch seconds, `within` seconds, `penalty` hours) is worked out in a thread of its own, at most two at once:
`{"working": true, "at"}` until it is done, the page asking again with that `at` so every request is the same report,
kept five minutes; the page stops asking when it is left. `ergostat impact BLOCK|CHANGE [--began TIME] [--within DUR]
[--penalty DUR] [--tests passed|failed] [--commit SHA] [--json]`.

**Called** as `impact.report(p, parts, began=None, *, at=None, within=None, times=12, penalty=None, share=None,
tests=None, commit=None, runs=40, budget=20.0)`; it raises `impact.ImpactError` (a `ValueError`) for what it cannot
report on, and a caller that shows the report should also catch any other exception and say it:

| Argument | What |
|---|---|
| `parts` | what changes, a string or a list of them, of which the first that resolves is used: `"BLOCK"` or `"block.NAME"` (a block whose runs fail), `"flow.NAME"` (its block), an `ergostat.failure/ID` item (its field `block`; `began`, `commit` and `tests` read from its fields when not given), or a model change (`ergostat.model-change/ID`, or its id) |
| `began` | when the failure began, epoch seconds (not a number: an `ImpactError`); else the first `agent.failed` of the block's last unbroken run of failures, among its last 500 runs (when all 500 failed, it is said that it began earlier) |
| `at` | now, epoch seconds (default: the clock) |
| `within`, `times` | rollout times tried: `times` (at most 24) evenly over `within` seconds (default: seven of the model's time unit, a day, an hour or a minute by its slowest time constant) |
| `penalty` | hours of cost a rollout at the busiest hour of the day adds (default: one time unit) |
| `share` | the share of its rate the failing block still moves (default: its rate during the failure over its rate before, at most 1; with no rate measured before, 0, and said) |
| `tests` | the fix's tests: `"passed"`, `"failed"`, or None (not run); anything else is an `ImpactError` |
| `commit` | the fix's commit, for the rollback |
| `runs`, `budget` | the risk's Monte Carlo runs, and the seconds of wall time the whole report may take, counted from the call |

**Returns** a dict (times in epoch seconds, durations in hours, rates per hour):

```
{"kind": "failure" | "change", "about": "block NAME" | "change ID", "at": now, "said": one sentence,
 "broken": {"block", "began", "share", "flows": [{"ref", "before", "during", "said"}],
            "stocks": [{"ref", "at_failure", "now", "building"}], "drains": [...]},   # a failure only
 "horizon": seconds, "times": [past grid], "ptimes": [projection times],
 "charts": [{"ref", "name", "kind", "unit", "per", "goal", "measured", "without", "with"}],   # with: at the recommended time
 "goals": {NAME: {"of", "hold", "off_at": time | None, "off_before": bool, "due": bool, "off_end": bool, "hours_off": h,
                  "hours_off_fixed_now": h, "p_off_end", "expected_off", "p_off": [per ptime], "said"}},
 "rollout": {"unit", "penalty", "span": T seconds, "busy_from", "trusted": bool,
             "options": [{"at", "extra_off", "goals_off", "outage", "lost", "peak", "recovery", "busy", "cost"}],
             "ideal": option, "best": option, "said": one sentence} | None,   # a change: None, and why in "notes"
 "fields": {"touches": {"blocks": [...], "goals": [...], "commands": [...], "actions": [{"name", "gate"}]},
            "read_only": bool, "writes": [...],
            "rollback": {"how", "items": {"kind", "states": {STATE: count}, "dead"} | None, "said"},
            "risk": {"level": "low" | "medium" | "high", "why": [...]},
            "confidence": {"level", "worst": words | None, "parts": [{"ref", "how", "said" | "r2", "skill"}], "said"}},
 "notes": [...], "stopped": None | why, "seconds": wall time}
```

**What broke**: the flows the block moves, each one's mean rate over the record before `began` (as long as the failure
has lasted, between an hour and a day) and during it; a flow at under a tenth of its rate before has **stopped**, else
it is **degraded**; one idle both before and during is said so, not seen to stop. The stocks those flows drain or fill,
with their level when the failure began and now; one higher now is **building up**. The items of the kind it takes
that are now dead letters are counted.

**Without the fix**: the closed-loop projection (section 12b) from now, the block's flows by its identified model,
identified on the reference window that ends when the failure began, times `share` (its failing self); every other
machine block by its model identified now. For each goal: when it goes off (`off_at`), whether it is off at the end, its
hours off, and its risk (section 12c's Monte Carlo, `runs` runs, within what is left of the budget; the risk is worked
out without the fix only). A goal already off when the failure began is `off_before`, said apart; a goal is **due** to
the failure when it held then and is off longer without the fix than with it made now (by more than a hundredth of the
horizon); the sentence names those.

**With the fix at time d**, for each rollout time: the same, the block's model restored from d, and **scored against
rolling out now over the same span**, from now to d + T, T at least twice the recovery when fixed now (and at least
the projection's usual horizon, the horizon `within + T`), so a late rollout's own effects are never cut off. Its cost
in hours: the goals' extra hours off against fixing now (`extra_off`, every goal, those off before included; what
waiting puts off of the fix's own effects earns it nothing), the outage hours, (1 − share) × (d − now), and `penalty`
× how busy the hour of day of d is (the record's mean arrival rate at that hour, over the last week at most, of the
flows from outside into the stocks the block's flows drain, else of every flow from outside; scaled from 0 at the
quietest hour to 1 at the busiest; 0 everywhere when the record has no daily pattern, said). So a busy hour must
outweigh a real loss before waiting is advised. Also said: the throughput lost (what fixing now moves along the block's
flows by d + T and this does not), the backlog's peak (the highest of the stocks building up, else the stocks it
drains), and the recovery after d (until the due goals hold to the end and those stocks have settled, as
`predict.py` says a stock settles; none within the horizon, said). The **ideal rollout time** is the cheapest, the
earliest of equals. **When the confidence is low, the report never advises waiting**: it recommends rolling out now
(or as soon as its tests pass, when they have not), says why, and shows the ideal time as the model's, muted. When the
budget runs out, the rollout times not tried are left out and `stopped` says so.

A **model change** is projected as the model is and with the change (section 12e's forecast, with the loops running
where there are controllers); its rollout times are not tried, since a change to the model revises the forecast, not
the world.

**The fields.** *Touches*: the other blocks that read the block's flows or the stocks they move, or take items from
those stocks, the goals on those stocks, the blocks and goals it commands, and its gated actions (section 12k) with
their gates. *Read-only*: it has no gated actions; else *writes* names them. *Rollback*: revert the fix's commit
(`git revert COMMIT`); a block that takes items leaves the items it moved where they are, the ones it would take next
wait in its `takes.at` states (counted now), and a run in flight gives its item back when its lease expires; the dead
letters are said: the fix does not bring them back, a redrive does. For a change: revert the edit; the record is
untouched. *Risk level*: a point each for writes (two for an action with `gate: auto`), a blast radius of more than
three parts, and tests not run; failed tests add four; 0 or 1 is low, 2 or 3 medium, more high; each point said.
*Confidence*: every model the projection runs, identified or **assumed** (for want of record), and each charted stock's
fit on the reference window (R², skill against its mean), a stock fitting **worse than its mean** said as that. It is
low with a stock fitting worse than its mean, an assumed model, or a projection not valid; the worst part is named
(`worst`: the stock with the lowest skill below 0, else the first assumed model), and **a low-confidence report opens
its sentence with it** ("Low confidence: the model fits ready-work worse than its mean (skill −435)."). High when every
model is identified and every charted stock's skill is at least 0.5; else medium.

## 12o. The inbox: everything waiting on a person, answered and delivered

Human approval is for a system's early stages, while its owner and their agent work out its feedback loops; each kind
of it then graduates up the ladder (an AI approver, a narrow AI, a program, a rule; invariant 5). While it is used it
must reach the person and be quick to answer. **The inbox** is everything waiting on a person, in one list
(`ergostat/inbox/`):

| Kind | Waiting while | Id | Answered by |
|---|---|---|---|
| `action` | a gated action is held for the owner (section 12k) | `action/<short id>` | `approve`, `deny` (`gate.approve`, `gate.deny`) |
| `person` | a person block was asked (`person.asked`) and has not reported (`agent.ran`) | `person/BLOCK@SEQ` | `done N` (their report, as `ergostat block NAME --done N`) |
| `advise` | an advised command (`block.advised`) is neither approved (`block.approved`) nor denied (`block.denied`) | `advise/BLOCK@SEQ` | `approve`, `deny` |
| `steptest` | a step test was offered (`steptest.offered`, recorded when a loop's analysis first offers it, section 12d), is undecided, and the loop is as it was | `steptest/<id>` | `approve`, `deny` (accepted or dismissed) |
| `change` | a change to the model awaits the owner (the review queue, section 12b; with a judge, the ones it passed) | `change/<id>` | `approve`, `deny` (accepted or dismissed) |
| `request` | a modelling request is `held` (section 12e, *Requests*) | `request/<id>` | `approve` (`reopened`: open again for the AI tier, its tries given back; offered only for a request the tiers take up, never a redesign's, and when the model has the AI tier: section 12e), `deny --note WHY` (`dismissed`, with the note, until its part changes) |
| `breaker` | a block started by events tripped its breaker (`trigger.tripped`, section 9.3) | `breaker/BLOCK@SEQ` | `approve` (`trigger.reset`) |

An entry kind with no verb is not shown as answerable (`answer` says where it is settled instead); today every kind has
one. `ergostat inbox`, the status and the notifications say the same command for each entry.

A person's or an advised block's entry is **one ask**: `SEQ` is the event that asked. A newer ask before any answer
replaces it (the older is superseded, and no longer waits); an answer is to exactly the ask shown, and is recorded
with it (`ask: SEQ`), so approving an entry never approves a command advised after it was shown. Each entry has a
one-line summary, its age, a link to its page (the action's or the change's item, the block's or the loop's place in
the diagram), its answer verbs, why it waits (for an action about a work item: that item's `impact` sentence and
`tests` result, when it has them, section 12n), and its class's record this week. An id may be given by any unique
start of its key (`person/reviewer` is the reviewer's ask now). **Answering** goes through the path each kind has
always had, and is an event from whoever answered (the owner, unless `--as`):

- `ergostat inbox` lists them; `ergostat inbox ID --approve | --deny [--note TEXT]` or `--done N` answers one; `--json`;
  `--stats` (below).
- The MCP tools `inbox` and `answer`, so the owner's Claude session can answer on their behalf when told to; its
  answers are recorded as from `owner via mcp`, counted apart, and never evidence for graduating a class.
- The page: the entries are listed in *Needs attention* (the side panel) after its problems and before its warnings,
  each with Approve / Deny, or a number and Done, inline: `POST /api/inbox/ID/approve`, `/deny` or `/done?n=N`
  (`note=`); `GET /api/inbox`. The item pages keep their own buttons. No page or panel of its own.

**`notify:`** (top level, main file only) sends what newly waits on a person:

```yaml
notify:
  base-url: http://127.0.0.1:8790     # the link in each message (default: the running page's)
  group: 2m                           # new entries within this window become one message (default 2m)
  per-hour: 6                         # at most this many messages an hour, per channel (default 6)
  quiet: 22:00-07:00                  # optional: nothing sent then (local time); what waits is sent after
  wait-at-most: 4h                    # optional: the owner's goal; past it, a finding and one more notification
  escalate-to: [phone]                # optional: where the late ones go (default: every channel)
  asks-per-day: 10                    # optional: the approval budget; over it, a finding
  channels:
    desk: {type: macos, detail: full}                     # terminal-notifier if installed, else osascript
    mail: {type: email, to: me@example.com, command: sendmail -t}   # the message on its standard input
    team: {type: slack, url-env: TEAM_HOOK, gate: deny}   # the webhook's URL from the environment...
    phone: {type: discord, url-file: ~/.config/ergostat/discord-url}   # ...or a file: never in the YAML
    log: {type: command, run: "cat >> notified.txt"}      # the message on standard input (tests, demos, anything)
```

**Each delivery is a gated action** `notify.CHANNEL` (class `notify`; section 12k): the channel's `gate:` (default
`auto`) says whether it is sent, held for the owner, or never sent, so the owner decides where anything may go (at work,
`deny` for some). **What leaves the machine is little by default** (`detail: minimal`): a subject that counts ("2
approvals, 1 request waiting") and per entry its id, kind, class, age, link (`base-url` + its page, where Approve /
Deny are one click away) and the command that answers it. A channel with `detail: full` also carries each entry's
summary and why, scrubbed as a report upstream is (section 12m: the model's names, hosts, paths, secrets and the
owner's denylist replaced). Sending runs in a thread of its own, every few seconds, never on the engine's clock:
entries new on a channel wait `group` from the first of them and go as one message; at most `per-hour` messages an
hour per channel; none in the `quiet` hours. Each is recorded as `ergostat.notify.sent` (the channel, the entries, the
action and how it went); a denied channel records its entries as told, so they are not asked again; a message that
failed is tried again with the next one, and a channel whose last three failed is a finding (`notify-failing`).
**The cause-chain guard:** a `notify.*` action held for the owner is in the inbox but is never itself notified about,
and nothing is sent because of a notification's own events.

**Escalation and the budget.** With `wait-at-most`, an entry waiting longer is a finding (`waiting-on-owner`) and is
sent once more, to `escalate-to` when given, else to every channel. With `asks-per-day`, more asked of a person over
the last day than that is a finding (`approvals-over-budget`) naming the class that asked most, its record and its
rung up the ladder; the interventions loop (section 12p) is where such a class is worked on.

| Measure | What it is |
|---|---|
| `ergostat.inbox.waiting` | Entries waiting on a person, now |
| `ergostat.inbox.oldest` | Hours the oldest has waited (0 when none waits) |
| `ergostat.inbox.asked` | Asked of a person over the last day (the approval budget; ergostat's own notifications left out) |

**Graduation.** Per class (an action's class, `advise:BLOCK`, `person:BLOCK`, `change:KIND`, `steptest`, and the
interventions' `alarm:BLOCK`) over the last week: asked, approved (or done, or cleared), denied, answered by an agent,
waiting, and the median time to answer, shown on each entry and by `ergostat inbox --stats`. A class the owner approved
at least five times and never denied gets one line up the ladder: `gate: auto` or an AI approver for an action's
class, `mode: auto` for an advised block, the judge's `accept: {KIND: auto}` for a kind of change. Nothing is changed
automatically: promoting is the owner's edit (and is told from suppression, section 12p).

## 12p. Interventions: a stock under control

Every intervention (an approval held, a person's request, an advised command, a raised alarm) is **evidence of a
missing feedback loop or a gap in the model**. Silencing it is not a remedy; the remedy is more modelling and
automation until it is unnecessary. ergostat reads each from the record with its **class** (the action's class,
`person:BLOCK`, `advise:BLOCK`, `alarm:BLOCK`, `change:KIND`, `steptest`) and its **cause** (the process it blocked:
`block NAME` and the work item, what an alarm watches, the goal, the change), when it was asked, when and how it was
answered and by whom (an alarm: from its output rising to 1 until it falls; `ergostat/inbox/interventions.py`). A
notification is not an intervention of its own: it carries these, and counting it too would count them twice (and
reward grouping them).

**The loop**, one line: `uses: {interventions: {use: interventions}}` (the built-in template, used once a model),
drawn in all three views like the modelling loop:

- *Dynamics:* the stock `interventions-waiting` (`builtin: ergostat.interventions.waiting`: the inbox's entries and
  the alarms raised), filled as interventions are asked (`interventions-asked`, which each resolved class lowers) and
  drained as a person answers them (`interventions-answered`); the auxiliaries `interventions-per-day` (what is asked
  a day) and `intervention-trend` (below). The requests by state, items of the built-in kind `ergostat.model-request`:
  `open-requests` (open, investing, verifying), `suppressed-requests` (and back to open when the guard is put back),
  `resolved-requests` (and back to open when the class intervenes again).
- *Blocks:* the goal `interventions-falling` holds the trend at or under 0 (a steady load holds; a rise the record
  shows does not), and the controller `remedies` (a program on ergostat's own command, `ergostat inbox --requests`, on
  its own clock, whatever the short-term rate).
- *Process:* the requests move open → investing → verifying → resolved, or to suppressed and back.

**The controller**, each pass: (1) suppression and graduation recorded (below); (2) the classes ranked by the hours
they blocked their processes over the window, then by count; each that recurs (`recurs`, 3 by default, over the
window) and has no request gets one (`ergostat.model-request/<hash of the class>`, `.opened`), with its count, share,
hours blocked, rank, most common cause, and **candidate remedies**: automate the person's step with a block (the
person reviewing until its claims hold); graduate the gate (`gate: auto`, `mode: auto`, the judge's `accept:`) with
its evidence; add the missing structure (for an alarm, what explains what it watches: a capacity, rework, a delay, a
balancing flow, with a goal and a controller on it only where something should act before it rises, as the
redesigner's guide says; a check that makes an approval a rule); change the software so the step no longer needs a person. (3) A request is **resolved** only when its class
has not intervened for three of its mean intervals over the window (at least `verify`, 1d by default) since it was
last moved, and the process it blocked has worked in that time without it: its cause's block ran; an alarm was
evaluated and clear; a change of that kind was decided without the owner; a step test's loop holds its process. A
resolved class that intervenes again is reopened. `ergostat inbox --invest CLASS` marks a request as being worked on.

**Suppression does not count.** At each pass the model's guards are compared with the last version seen: each alarm's
bounds and what it watches; each action class's strictest gate, in the order `deny` > `approve` > `auto`; each
advised and person block; each channel's gate. Only a guard **removed or loosened** is judged; one kept, tightened
(`auto` to `approve`, `approve` to `deny`, a lower alarm bound) or edited otherwise is not. It is **suppression**
(`ergostat.model-request.suppressed` on its class's request, with the guard before and after and the class's rate
before, interventions per day over the window) when an alarm is removed or loosened and no goal holds what it
watches; an `approve` gate is removed, or becomes `auto` without the evidence that graduates it (the owner approved
the class at least five times this week, never denied); an advised block is removed, or turned `auto` without that
evidence; a person block is removed with no machine block moving its flows; a channel is removed or its gate made
stricter (shown, though it lowers nothing: notifications are not counted). A suppressed class keeps counting at its
rate before every day after, so suppression never lowers the measure, and it is never resolved; it reopens when the
guard is put back as it was. Otherwise the change **graduated** the class (`.graduated`: verifying), resolved as above.

**The trend, and the valley.** Fixing a cause often needs approvals of its own, so the rate may rise before it falls.
Let y_d be the interventions on day d of the window (`trend-window`, 21d; never more days than the record holds), each
suppressed class adding its rate before for the part of each day after its suppression, and a class being worked on
(investing, for at most `invest-for`, 14d) counting on those days at most at its rate before the work began (its
interventions over the window before, per day since its first). With b the least-squares slope of y_d against d and
SE its standard error (n days, residual variance over n − 2):

    b = Σ (d − d̄)(y_d − ȳ) / Σ (d − d̄)²,   SE = √( Σ (y_d − ȳ − b (d − d̄))² / (n − 2) / Σ (d − d̄)² )
    trend = 7 · max(0, b − 2·SE)

the lower bound of the weekly slope, so the goal is off only on a rise the record shows beyond its noise (a flat
Poisson load of 5 a day over 21 days is off about 3% of the time, not half of it). The planned rise of a class being worked on is
removed from y_d while it is worked on, up to `invest-for`; after that it counts again, so investing cannot hide a
class for good. The controller works the ranked classes whatever the trend says.

**Alarm-management measures** (ISA-18.2, EEMUA 191), read by a sensor (`builtin:`), shown on the goal's panel (the
loop's *Interventions*: the measures and the repeat offenders with their share, hours blocked and cause) and by
`ergostat inbox --stats`:

| Measure | What it is |
|---|---|
| `ergostat.interventions.waiting` | Interventions waiting now: the inbox's entries and the alarms raised |
| `ergostat.interventions.per-day` | Interventions over the last day, suppressed and invested classes counted as above |
| `ergostat.interventions.trend` | The trend above, per day, per week (0 unless a rise is significant) |
| `ergostat.interventions.standing` | Entries waiting longer than `standing` (notify's, default 24h) |
| `ergostat.interventions.chattering` | Classes that intervened 3 or more times within a minute over the last day |
| `ergostat.interventions.blocked-hours` | Hours the interventions held their processes over the last day |
| `ergostat.interventions.top-share` | The share of the window's interventions from the top class (the repeat offender) |

`notify:` keys for the loop: `trend-window` (21d), `recurs` (3), `verify` (1d), `standing` (24h), `invest-for` (14d).

## 12q. The sandbox: running a program ergostat does not trust

Some programs ergostat runs were written by someone the owner has not vouched for: a fix an AI agent wrote, run to
test it before anyone approves it (repair), or a script a shared library brings (libraries). `ergostat.sandbox` runs
such a program under the operating system's sandbox, by **allowlist**: what it may touch is listed, and everything
else is denied. It is one module for every caller; neither repair nor libraries uses it yet (GAPS). Claude Code
sessions keep their own sandbox (section 12k), which is a deny list for reads.

`run(argv, Policy(work=..., read=[...], hosts={...}, env={...}))` returns the exit code, the output, the time, whether
it timed out, and the proxy's log of every connection asked for.

| | Allowed | Everything else |
|---|---|---|
| **Read** | the work copy; the toolchain, resolved explicitly from an absolute interpreter path (the interpreter and every link to it, its standard library, its venv, the base prefix's `ssl` folder and the shared libraries at the top of its `lib`, never a whole prefix; `/usr/lib`, `/usr/share`, `/bin`, `/usr/bin`; on macOS `/System`, the timezone and certificate folders; on Linux `/lib*` and the loader's cache); `read:` paths the caller declares | denied: the whole home folder, other temporary files, the rest of the interpreter's prefix, `/Library`. A work copy or declared path that is `/` or holds the home folder is refused |
| **Write** | the work copy, except its `.git` (file or folder, which cannot be written, moved or removed); a private temporary folder (`TMPDIR`), removed after the run | denied, `/tmp` included |
| **Network** | none, unless `hosts:` lists some: then only the proxy on 127.0.0.1 | denied: other local ports, every other address, DNS |
| **Processes** | started freely inside, up to 256 more than the machine has (`RLIMIT_NPROC`) | all killed when the run ends or times out; one that cannot be killed fails the run (`escaped`) |
| **Environment** | `HOME`, `USER`, `LOGNAME`, `LANG`, `LC_ALL`, `LC_CTYPE`, `TERM`, `TZ`, `SHELL`; a `PATH` of the interpreter's folder, `/usr/bin` and `/bin`; `TMPDIR`; the proxy's variables when hosts are listed; what the caller passes | not passed: no `ERGOSTAT_*`, no dry-run, test or sandbox marker |

**How.** On macOS, `sandbox-exec` with a profile that starts `(deny default)` and allows only the above: process fork
and exec of readable programs, signals within its own sandbox, `sysctl` reads except `kern.proc*` (the process
table), POSIX semaphores (Python's `multiprocessing`), the listed files, the null and random devices, and outbound to
`localhost:PORT` of the proxy. No Mach service is allowed: name lookups, the keychain and `launchctl` fail inside.
Every rule names at most five filters, and the sysctl rules none but that one deny: long filter lists have panicked
macOS 15.5's kernel (a test holds the profile to this). On Linux, `bwrap --unshare-all
--die-with-parent --new-session` with an empty root binding only the allowed paths (read-only but the copy and its
temporary folder; `.git` bound read-only over the copy), and no network namespace but loopback; the proxy is a Unix
socket bound in, served on 127.0.0.1 inside by a small forwarder. Neither present: `Unavailable`, and the program is
not run. There is no fallback.

**The proxy.** Started by ergostat for the run, on a free port of 127.0.0.1. It admits a host only if listed (`name`,
ports 80 and 443; or `name:port`), resolves it itself, and records each request: the time, method, host, port,
whether it was allowed and why. For HTTPS (`CONNECT`) it reads the whole TLS ClientHello, across however many records it
was split into, and refuses one whose server name is missing, unreadable or differs from the CONNECT host. It serves
64 connections at once; the rest wait to be accepted. A host may be limited to methods (`hosts: {api.example: [GET]}`): for plain HTTP
every request is checked (one per connection, a body only by a single `Content-Length`, `Host` rewritten to the
listed name);
for HTTPS the proxy cannot see the method, so a method-limited host gets **no tunnel** unless the caller lists it in
`tls_unchecked`, which admits the tunnel with the limit unenforced.

**Process lifetime.** On Linux the pid namespace ends with the run. On macOS the program is started by a small
supervisor inside the sandbox, which reports its exit code on a pipe and then stops every process of the run at once
(`kill(-1, SIGSTOP)` reaches only its own sandbox's processes), so none can fork away. Outside, ergostat then lists
every process (`proc_listallpids`), asks the kernel which carry this run's sandbox (`sandbox_check`: it may read the
run's temporary folder and may not read a canary file only this run is denied), stops each it finds, round after round
until three find none, and kills them all. At the time limit it asks the supervisor to kill the program first. A
program that kills the supervisor loses its exit code (`exit` is None) and is reaped the same way from outside; a
process still alive after that is named in `escaped` and the run fails.

**Git.** `ergostat.sandbox.git.Repo(work, gitdir, common)` is how ergostat runs git on a work copy, never the program:
`GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=/dev/null`, explicit `GIT_DIR`, `GIT_COMMON_DIR` and `GIT_WORK_TREE`,
`-c core.fsmonitor=false -c core.hooksPath=/dev/null -c commit.gpgsign=false -c core.attributesFile=/dev/null`,
`--no-ext-diff --no-textconv` on the diff commands, every filter driver in the repository's config blanked, no pager,
editor, prompt or ssh. Before every call it checks that the copy's `.git` is the pointer ergostat made (not a link),
that the worktree folder's `commondir` leads to the repository and its `gitdir` back to the copy; otherwise `Tampered`,
and git is not run. `Repo.worktree(repo, work, branch)` makes such a copy.

What it protects against and what it does not, for people: `docs/SECURITY.md`.

## 12r. Repair: a failing program triaged, fixed, and proposed as a gated change

Programs fail (an API changes shape, a field goes missing); a failure should need no person to find it or to fix it,
and, once a system's loops are trusted, none to approve the fix. **`use: repair`** (a built-in template, `once: true`)
is that loop as parts of the model, in a system of its own, drawn in the three views. What it does not do yet (the
ladder's other rungs) is in `docs/GAPS.md`.

```yaml
uses:
  repair:
    use: repair
    with:
      approver: person        # the only one for now
      model: haiku            # the fixer's (default)
      budget: 0.25            # dollars, one AI call at most
      daily: 2                # dollars, every AI call of the loop in a day
      test: pytest -q         # the project's tests, for a program that is not read-only
      tries: 3                # fixes tried for one failure before it is a dead letter
      verify: 3               # good runs of the block, begun after a fix, before it counts as verified (1 to 50)
```

**Triage.** In a model that uses repair, every failed run of a `program` or `ai` block is recorded as
`ergostat.run.failed` about an item of the built-in kind **`ergostat.failure`** (it exists only in such a model), one
item a **signature**: the block, its program (the first word of its `run:` that is a file under the model's folder), the
exception's type and its innermost frame in the project, from the last trace in the run's output; without one, the
block, its program and how it ended. Traces are read from the **tail** only: the last 8,000 characters of the run's own
file, its first partial line dropped when it does not begin at the run's start. Four languages are read
(`repair/traces.py`): **Python**'s `Traceback (most recent call last)` (its frame the innermost one outside
`site-packages`, `/lib/python`, `<frozen` and `<string>`, as triage always signed it, so a Python failure keeps its id);
**Node**'s `Name[ [CODE]]: message` directly followed by `    at` lines; **Java**'s outer exception line (with or
without `Exception in thread "T"`) directly followed by `\tat` lines, then its `Caused by:` blocks (indented
`Suppressed:` blocks ignored); **Go**'s `panic: message`, `goroutine N [running]:` and its function and file lines (its
type `panic`). The trace whose header line comes last is taken, and **a trace needs its header**: one whose header the
tail cut off is no trace, whatever frames or `Caused by:` lines are left, and the run is signed by how it ended (so a
Python traceback more than 8,000 characters before the end of a failed run's output is too). A **project frame** is one
whose file, a relative path taken against the model's folder, lies under that folder, in none of its `site-packages`,
`node_modules`, `.venv`, `venv` or `vendor` folders, and is not the runtime's (`node:`, `<frozen`, `<string>`); for
Node and Go the signature frame is the innermost project frame, else the innermost frame. **Java** signs by its **root
cause** (the last `Caused by:`, else the outer exception): its type and message, and the innermost project frame of
its own frames, else of the nearest enclosing exception's, else its innermost frame. A Java frame's file is its class's
package path (`com/acme/Store.java`), the project's when a file under the model's folder ends with it; the folder is
walked for that once a trace, at most 5,000 entries (dot-folders and the library folders not entered), and a walk that
reaches the cap finds no Java frame the project's (the trace says `walk: capped`). Ruby and other languages are not
read. The item keeps the error, the traceback, the tail of standard error (8,000 characters), the
program, the model's version and the input the run was given (`repair/NAME.input` in the state directory), all scrubbed
of secrets and the owner's denylist (section 12m's rules); the same failure again adds to its `count`. The standard
error is read only from the run's own file (`log`, `logs/runs/<block>/<seq>-<id>.log`, section 4b), never from the
block's log, so a run that overlapped it adds nothing. A daemon's run (section 9.7) is the exception in what it can say:
the daemon's standard error is one stream for all its runs, kept in `logs/daemon-<name>.log` and never copied into a
run's file, so a daemon run's file holds only the lines it handed back that were not JSON (usually none), its `stderr`
is usually empty, and it is triaged by how it ended. A run whose own file could not be made safely does not start (its
note `could not start: its run log: ...`), so its failure stays `noted`. A failure starts
`noted` and is **opened** for repair only when its block runs a program of the project's and it did not end by a
timeout, a kill, a signal or failing to start. A signal is an exit of -N, or of 128+N for a signal that dumps core
(SEGV, ABRT and the rest of section 9.1's list), so a segfault or an abort is noted, never opened; a program that
exits with such a code on purpose is noted too. Triage writes `ergostat.failure.opened` whenever the run's own facts
allow it, and the **fold decides** whether it moves the item, by the item's state at that event's place in the record
(`moves_from`, section 5a): `opened` moves a failure only from `noted`, `verified` or `superseded`, so a failure leased,
awaiting approval, dismissed or dead stays where it is, the refusal listed, whatever triage read before it wrote. One
that fails again while its fix is `applied` is counted on the item and left for `repair-settle` to judge (below), one
that fails again after it was `verified` is opened again, and a `regressed` or `reverted` one is left to a person. An
`opened` written when triage read one of the states it moves from clears the last cycle's `verdict`, `revert` and
`revert_key`; one written when triage read another carries none of them, so a refused `opened` never wipes a regressed
failure's `revert_key`. What triage still decides from a read (whether the item is new, when its run of failures
`began`, which old item it supersedes, whether `opened` clears the cycle's fields) is read, decided and written while it
holds `repair/capture.lock` in the state directory. The loop's own blocks (`repair-fix`, `repair-settle`) and any run a
failure's events caused (six steps up the cause chain) record no failure. States: `noted`, `open`, `leased` (being
fixed), `awaiting-approval`, `applied`, `superseded`, `dismissed`, `dead` (its fixes failed `tries` times),
`verified`, `regressed`, `reverted`.

**Swallowed errors.** A run of a `program` or `ai` block that ended well (exit 0, no note), whose block runs a program
of the project's, has its tail read the same way. When its last trace has a project frame, one
`ergostat.run.swallowed` is written about the failure that trace signs (the same signature a failure would get). A new
item arrives `noted`, with a failure's fields, `swallowed: 1` and `count: 0`, and is never opened by it; for an
item that exists, in any state, the event says only `{"swallowed": 1, "last_swallowed": RUN}` (`swallowed` folds as a
sum). The event moves no state, writes no `repair/NAME.input` for an existing item, and carries none of the fields the
fixer reads, so a failure being fixed keeps its lease and its traceback. A trace with only library or runtime frames,
or none, records nothing. A later failed run with the same signature opens the noted item as usual. A daemon's run
hands back no standard error (above), so what a daemon swallows is not seen.

**Superseding.** Node, Java and Go failures were signed by how they ended before triage read their traces, so their old
items have other ids. When a failure is signed by such a trace, triage looks for the item at its old signature (block,
program, how it ended); only if that item's kept `stderr` parses to the same new signature does it write
`ergostat.failure.superseded` (`{"by": NEW}`) about it, which moves it to `superseded` from `noted` or `open` only. One
being worked (leased, awaiting approval, applied) is not moved, the refusal listed, and a later failure tries again;
one whose stderr is another bug that ended the same way is left alone. A failure at that old signature with no readable
trace (one that ended the same way) opens the superseded item again, so it hides nothing. Python failures are never
superseded: their signatures did not change.

**Sealed.** A failure's fields are ergostat's alone: its kind is *sealed* (`ItemKind.sealed`), so the fold
(`spec/items.py`) refuses every event about it whose type is not ergostat's own (`ergostat.*`, which no block line,
sensor observation, push, `event --add`, MCP call or legacy runner may write). The impact report reads its fields the
same way. Nothing the loop runs is taken from a failure's fields: the block and its command come from the compiled
model, the input from the state directory.

**The fix** (`repair-fix`, an `ai` block whose `run:` is `python -m ergostat.repair fix`, its rung shown as AI) takes
each open failure, leased (section 9.5), and:

1. makes a **clone** of the project's repository at its `HEAD` under the state directory (`repair/NAME/`: `git clone
   --no-local --no-hardlinks`, so its `.git` and objects are its own, never the owner's, never a worktree sharing them),
   and runs git on it only through `ergostat.sandbox.git.Repo` (section 12q);
2. asks the **AI** (`claude -p --tools "" --strict-mcp-config --no-session-persistence`, `--max-budget-usd` the
   `budget`, in an empty folder) with the prompt `ergostat/repair/fixer.md` and the failure, given **only what ergostat
   read for it**: the program and the plain files beside it in the clone (committed files only: no dot-files, links or
   binaries; 32,000 characters each, 96,000 in all; scrubbed). It reads, runs and writes nothing itself. It answers with
   the program's whole new text (at most 32,000 characters) and an explanation, or why it cannot. Refused before the
   AI is asked, and left to a person: a program not among the files given (too large, not text), one with changes in
   the owner's tree not committed (its fix would be made from other text), and one whose fixes could not be applied
   twice;
3. writes that text over the program in the clone (refused: a link, a path outside the clone or in `.git`, no change;
   nothing else is ever written) and commits it;
4. **tests** it in `ergostat.sandbox` (section 12q) on a throwaway copy of the clone's files without `.git`: reads only
   the copy and the toolchain, writes only the copy and its temporary folder, an environment with no ergostat or test
   variable, every process it started killed. A fix can still tell it is sandboxed (its home folder is unreadable, it
   has no DNS), so a test shows only that it ran well there, not how it behaves outside. A block that says `read-only: true` (its program changes nothing outside)
   is re-run with the input that failed; its `network:` hosts are reachable through the sandbox's proxy for `GET` and
   `HEAD` only (an HTTPS host gets no tunnel, its methods unchecked inside TLS). Any other block runs the template's
   `test:`; without one the fix is **untested**, said. The output is scrubbed and kept (`test`, `tests`), and what it
   showed is said as it is: "exited 0 on the input that failed, in the sandbox", or "its test (CMD) exited 0 in the
   sandbox", never "tests passed".
5. A fix that failed its test is recorded (`fix-failed`) and the failure **given back** (a lease attempt: the fixer is
   told what its last fix did; a dead letter after `tries`). Passed or untested: the **impact report** (section 12n) is
   worked out for the failure (at most 20 seconds) and kept with it (`impact`, `risk`, the report as `repair/NAME.impact.json`),
   and the gated action **`apply-fix`** is asked for (section 12k), its `key` naming the failure and the fix's commit:
   the fix proposed as a gated change, in the inbox (section 12o). The inbox says it plainly: "Approving merges this
   code into your repository; it then runs with your rights, outside the sandbox", then the link to the diff (the
   failure's page), what the test showed and the impact sentence; the action's description says the same.

A failure the AI cannot fix, a refused proposal, git refusing, or an AI call not answered within its time is given
back with why.

**The ladder's first rung only** (invariant 5). `apply-fix` is held for the person, answered from the inbox, the CLI
or the failure's page; a notification of it (section 12o) always carries the sentence "Approving merges this code into
your repository; it then runs with your rights, outside the sandbox", whatever the channel's `detail`, so a person
answering from a phone has read it. What an approved fix then does runs with the owner's rights, as the program it
replaces did. `approver: ai` is refused by `check` ("not yet: a sound allowlist guard is needed"): an AI approver was
built and cut, since a guard that denies listed calls is bypassed many ways (`docs/GAPS.md`). **A denial is final**
(the kind's `final` states, `spec/items.py`): an approval recorded after an action's denial, whoever wrote it and
however the two raced, is ignored and listed (`ignored`); the action stays denied, is counted as denied (never as
evidence for promoting its class to `gate: auto`), and is never run; one that ran anyway, having got through before the
denial was seen, is shown as **ran despite denial** on the action's page.

**Applying** (`python -m ergostat.repair apply`, the approved action, in the model's folder): the failure must be
awaiting approval with a tested fix; the approved action's `key` must name that fix; the clone's metadata must be what ergostat made and its `HEAD` the tested commit;
the owner's `HEAD` must still be the commit the fix was made on (else refused: fixed again on the new one). Then the
tested commit is fetched from the clone and fast-forwarded (`git merge --ff-only`, which refuses atomically when the
branch moved or a local change would be overwritten), and the clone removed. Refused, the failure goes back to open
(`apply-failed`, with why). **`repair-settle`** (every 30 s) dismisses a failure whose `apply-fix` was denied, judges
the applied fixes (below), and removes the clones of failures no longer awaiting approval.

**Verifying** (`repair-settle`, `python -m ergostat.repair settle --verify N`). Each applied failure is judged on its own,
under its lock (`<state>/repair/locks/<name>.lock`, an `fcntl.flock` the kernel frees when the process dies), and read
again inside it: one no longer `applied` is left alone. The runs counted are the failing block's `agent.started` events
whose `seq` is after the newest `ergostat.failure.applied` about the failure (never compared by time), oldest first,
each with its end event (by `causedby`). A run not yet ended stops the count there; one that ended by a timeout, a kill,
a signal or failing to start (triage's rule) counts neither way; any other `agent.failed` **regresses** the fix; each
`agent.ran` is one good run, and at `verify` of them the fix is **verified**. Verified means only that `verify` runs
of its block begun after it finished well, not that the failure is fixed. A regression is any failed run of the block
the code may be to blame for, whatever its failure's signature: the `verdict` says which run it was, its note, and
whether triage recorded it on this same failure (`same`). The `verdict` field holds the runs counted, the seq they
were counted after and `verify: {used, asked, clamped}`. With an input missing (no `applied` event, the block no longer
in the model, a commit that cannot be read) the fix is not verified: it stays `applied` and settle says why. It can
also stay `applied` for good, said each pass: a run that never ends, or a first ten times `verify` runs begun since
the fix that all ended by a timeout, a kill, a signal or failing to start; a person looks. **`verify`** is a whole
number from 1 to 50: `check` refuses any other in `repair-settle`'s `run:`, and settle clamps again (below 1 is 1,
above 50 is 50, one that cannot be read is 50) and records the clamp. It reads the oldest ten times `verify` runs begun
since the fix, by seq, however many began after them, so a first run that failed regresses the fix even when many
more followed before settle's pass.

**Reverting.** A regressed failure gets `revert_key` (`<name>-<commit>`), and settle asks for the gated action
**`revert-fix`** in the same locked step, and on every later pass while it is regressed, unless an action about the
failure already has that key, so a request lost to a crash is asked next pass and none is asked twice. The inbox says:
"Approving reverts the applied fix COMMIT in your repository with one new commit (git revert); the program goes back to
what it was before the fix." (never "merges"). The approved action runs `python -m ergostat.repair revert` (`timeout:
5m`), every step under the failure's lock: the failure must be `regressed` (`reverted` already: said, nothing done,
exit 0) and the action's key its `revert_key`, so an earlier cycle's approval reverts nothing; the commit must be 40
hex characters and an ancestor of the owner's `HEAD`. A revert commit of it already there (`This reverts commit ...`,
from a run whose event was never written) is recorded as the revert. Otherwise the owner's tree must be clean (tracked
files) and no revert, merge or cherry-pick in progress, else `revert-failed` with why and nothing touched; then `git
revert --no-edit` through `ergostat.sandbox.git` (no hooks, editor, filters or gc; each git call stopped after 120 s).
When git fails or times out, `git revert --abort` is run and checked: `aborted: true` means no revert in progress, `HEAD`
where it was and a clean tree; otherwise the owner is told the repository is left mid-revert. `revert-failed` writes the
`revert` field and moves nothing, so it never undoes a `reverted`; the failure stays `regressed`. A gated action past its
`timeout` has its whole session killed (section 12k's `run_once`: the shell, its command and theirs). A **denied**
`revert-fix` leaves the failure `regressed` for good: nothing reopens or moves it; a person reverts or fixes it by hand.

| state | entered by | left by |
|---|---|---|
| `applied` | the approved `apply-fix` | `verified`, `regressed` (settle) |
| `verified` | `verify` good runs after the fix | `opened`, when it fails again |
| `regressed` | a failed run after the fix | `reverted` (the approved `revert-fix`); else stays |
| `reverted` | the revert commit | nothing: a person looks |

**Costs and the cap.** Each AI call's Claude Code result message is passed on without its text (so its cost is the
run's, section 9.1, and nothing the AI wrote is read as one of the run's lines). Before every call the loop's ledger
(`repair/spend.jsonl`, under a lock) is read: the day's spend plus the call's `budget` must not pass `daily`; a ledger
that cannot be read means no call (it fails closed). The whole budget is written before the call and corrected after
it by the difference to what it said it cost (either way), so a run killed mid-call still counts it, and a call whose cost is not said counts whole.
Each AI call and the test get a quarter of the block's `timeout`, so the three end before the run is killed. A
capped failure is given back for an hour, not counted as an attempt. `repair-spend` charts the fixer's cost.

| Part | What |
|---|---|
| stocks | `open-failures`, `fixing` (leased), `awaiting-approval`, `applied-fixes` (cumulative) |
| flows | `failures-found`, `fixes-started`, `fixes-proposed`, `fixes-failed` (rework), `fixes-applied`, `fixes-dismissed` |
| goals | `no-open-failures` (`repair-fix`), `fixes-answered` (`repair-settle`, and the approver) |
| action | `apply-fix` (`gate: approve` or `deny`; `auto` is not offered: approval is the ladder's) |

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
   open. The request is in the inbox (section 12o), answered there too (`ergostat inbox person/NAME --done N`), and
   `notify: wait-at-most:` is the owner's own limit on how long anything waits on them.
5. The built-in set: is it the right first twelve?
