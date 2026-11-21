# Remote systems: another ergostat's system, composed into this model

Status: designed 2026-11-18 on the `remote` branch; the first slice is built there (see *What the first slice
builds*). The owner's definition: a **remote system** is a system run by another ergostat instance, composed
into a local model. Its model is served by the remote instance and changes while it runs; its event log and
metrics are queried where they live; its agents run on the remote machine, never locally. The local ergostat
reads it, links to its parts and draws it as a subsystem; it never runs it.

This is not a shared library. A library (`docs/proposals/external-systems.md`) is a **copy** of a reusable
model, pinned by version, that the importing model runs as its own. A remote system is **one running system seen
from two places**: the remote runs it, the local reads it. Two library mechanics are reused: how an imported part
is named and placed (SPEC §2a's instances: `NAME-PART`, a system of its own, every part pointing at the line that
brought it in), and refusing edits to a part that belongs to someone else.

## In the disciplines' terms

- **System dynamics**: a remote system is a **subsystem with an interface** (Sterman's model boundary; Wolstenholme's
  subsystem diagrams). Its stocks, flows and auxiliaries are endogenous *there* and exogenous *here*: the local
  model reads them as data series and never integrates them. A local flow `driven-by` a remote stock is an
  influence across the boundary, and a material flow from a remote stock into a local one is a flow whose
  source is outside the local model's control (a cloud that happens to be measured).
- **Control**: the remote is a **separately controlled plant** (its own controllers, its own actuators, its own
  owner). Seen from our loops its outputs are either **measured disturbances** (feedforward: incidents opened
  over there load our support queue) or **setpoints** handed to us (a cascade across machines: its goal says
  how fast we must answer). We never close a loop *through* its actuators: a local block may not output to a
  remote flow, block or goal. Where we want it to act differently, we propose that to its owner.
- **Process mining**: its items are objects of other kinds in another log. The local process map draws the
  remote's map beside ours, frame by frame, marked remote; lines between our items and theirs need a shared id
  and are left to a later slice.

## 1. What a remote ergostat serves

Every ergostat that runs its page (`ergostat run` or `ergostat web`) can serve a read-only API under
`/remote/v1/`, turned on by issuing a token (section 2). Every answer is JSON, bounded and paged; nothing
under it writes.

| Address | Answers | Bounds |
|---|---|---|
| `GET /remote/v1/status` | name, model version, now, the newest event's `seq`, whether it is running | |
| `GET /remote/v1/model` | the compiled model's document (below), its `version`; `ETag` is the version, so `If-None-Match` gets a 304 with no body | one document |
| `GET /remote/v1/events?after=SEQ` | events in `seq` order after the cursor; filters `type` (glob), `item`, `kind` (an item kind's ids), `since`, `until`; `next` (the cursor to send next) and `more` | `n` ≤ 1,000 |
| `GET /remote/v1/items` | the item listing (`kind`, `state`, `n`, `offset`), as `GET /api/items` | `n` ≤ 500 |
| `GET /remote/v1/items/ID` | one item's fold and its recent history | the history shown on its page |
| `GET /remote/v1/counts` | items by kind and state, from the item index | one row per kind |
| `GET /remote/v1/readings?series=…&ref=…` | the newest reading of each measurement series (`sensor/open.count`), and of each model part (`stock.open`, `flow.resolved`, `auxiliary.load`, `goal.x`), each with its time | 200 a call |
| `GET /remote/v1/series?name=…` | one series' readings over `since`…`until` | `n` ≤ 1,000 points |
| `GET /remote/v1/process` | its process map (SPEC §5b), as `GET /api/graph?view=process` | the map's own bounds |

**The model it serves** is today's compiled document, not the IR (`docs/proposals/ir-and-runtime.md` is not
built): the merged sections after includes are read and templates expanded, exactly what the compiler sees,
as JSON. `format: ergostat-model/1`. It is **redacted** before it leaves: no `sources:` (their URLs and
queries), no `workspaces:`, `actions:`, `contexts:`, `claims:`, `leases:`, `loops:`; a block keeps its
`type`, `in`, `out`, `goal`, `agent`, `system`, `description` and `role`, never its `run`, `prompt`, `ask`,
`tools`, `read`, `workdir` or `workspace`; a sensor keeps what kind of instrument it is (`items`, `run`,
`query`, `manual`, `changes`, `builtin`) and its `every`, never its command or query; an agent keeps `kind`
and `description`. Item kinds go with their `id`, `states` and `show`. The **version** is the first 16 hex of
the SHA-256 of the canonical JSON of what is served (sorted keys, no whitespace), so it changes exactly when
what the local side can see changes. When the IR lands, `?format=ir` serves it beside this one, with the IR's
own hash; the local side takes whichever it knows.

## 2. Authentication

- **A token per consumer.** `ergostat remote token NAME` (on the remote) makes a token, prints it once, and
  keeps only its SHA-256 in `<state>/remote-tokens.json`; `--revoke NAME` removes it. With no tokens the API
  answers 404: it is off until the owner turns it on.
- **Sent as** `Authorization: Bearer TOKEN`, compared in constant time. The local side reads it from a file
  (`token-file:`), never from the YAML, so the model can be committed.
- **Read-only.** Only `GET` is answered under `/remote/`; nothing there writes the record, the model or the
  owner's state. The page's own write path (the run's page token, the Host and Origin checks) is unchanged.
- **The transport.** The server stays bound to 127.0.0.1. Across machines it is reached through an SSH tunnel
  (`ssh -N -L 8795:127.0.0.1:8781 incidents-host`, then `url: http://127.0.0.1:8795`) or an https reverse
  proxy in front of it. The page's Host check (against DNS rebinding) is not applied under `/remote/`, since a
  tunnel or proxy sends its own name: the bearer token, which no other page can attach, is what admits a
  request. `check` refuses a plain `http://` URL to a host that is not loopback.
- **A rate limit per token**: a token bucket, 10 requests a second with bursts of 30; past it, 429 with
  `Retry-After`.

## 3. The local declaration

```yaml
remotes:
  incidents:                          # the remote's local name: its parts are incidents-...
    url: http://127.0.0.1:8792        # https, or a tunnel's loopback port
    token-file: ~/.config/ergostat/incidents.token
    systems: [triage]                 # optional: only these of its systems (and what is inside them)
    within: support                   # optional: the local system it is drawn inside
    every: 1m                         # how often its model and readings are read (default 1m, at least 10s)
    description: the incident desk, run by the on-call team
```

`remotes:` is a top-level section (main file or any included file). Each entry also defines a **source** of the
same name, `type: ergostat` (section 5), which a local sensor can query. A `sources:` entry may be
`type: ergostat` on its own (`url`, `token-file`), for reading a remote's measurements without importing its
model.

**Fetched, cached, refreshed.** The remote's model is kept in `<state>/remotes/NAME/model.json` with its
version, and how the last attempt went in `status.json` (when, whether it answered, why not). It is read again:

- by a refresher in the running ergostat and in the page's server, every `every`, with `If-None-Match`, so an
  unchanged model costs a 304;
- by any other process that loads the model (`check`, the CLI) when the cache is older than `every`, with a
  three-second timeout; a remote that does not answer leaves the cache as it was;
- whenever a reading says the remote's version moved (each readings answer carries it).

The cached file is one of the model's files: when a refresh writes a new version, the model's stamp changes and
the engine and the page reload it exactly as they do when `ergostat.yaml` is edited.

## 4. How the remote's model appears locally

**As a system with a `remote:` origin.** The remote becomes a system named for the entry (`incidents`), with
its own systems inside it (`incidents-triage`), and every part it serves named `incidents-PART` and placed in
them, the way a template's instance is. Every part points at the `remotes:` line that brought it in
(`ergostat.yaml:12 (remote incidents)`), and `spec.remotes` says, per remote, its URL, version, when it was read,
and which parts are its. Its agents come with it, named the same way and `external: true`, so each part still
shows its rung; its kinds of item stay there (section 5).

**Drawn as a subsystem, closed by default.** In Dynamics and Blocks the remote is one box, marked *remote*
(its border dashed, its subtitle saying where it runs, its version, and how old its readings are), with its
ports where our parts meet its parts. It opens in place like any system; it is never opened by default, even
alone at its level. In Process its kinds' maps are drawn beside ours, each frame named `remote incidents: KIND`.

**Never run here.** Every block it serves becomes `type: external` locally, whatever it was there (a program,
an AI, a person, a built-in `onoff`): it keeps its inputs and outputs, so its loops are drawn, and a block that
named a goal reads that goal's error. The local engine never starts it, never leases its items, never
evaluates its built-ins. Every sensor it serves becomes a query of the remote (section 5), with the remote's
`every` (at least the entry's), so its stocks and flows carry the remote's readings. A flow with no sensor of
its own there (one its valve moves) gets one sensor, `remote`, that reads the remote's rate for it. Its goals are
evaluated here from those readings, as monitors: the local record notes when we saw them cross, and nothing
here acts on them.

**Local parts may reference remote parts**, by their local names: a local goal on a remote stock (`stock:
incidents-open`), a local flow fed from a remote stock (`from: incidents-escalated`), a cross-system cause
(`driven-by: [+stock.incidents-open]`), a local block reading a remote measure (`in: stock.incidents-open`).
They are checked against the remote's **current** model, at every load. **A local block may not output to a
remote part** (`remote-output`, an error): what runs there is changed only there.

**When the remote model changes, the local view follows**: the next refresh writes the new version, the model
reloads, the diagrams redraw. A local reference that no longer resolves is **a finding, not a crash**: the
referenced part is put in as a stand-in (no sensor, in the remote's system, described as missing from version
V), so the model still loads and runs, and `check` says `remote-reference-unresolved` with the reference, the
file and line, and the version it went missing in. A goal on such a stand-in is unjudgeable, as any goal on a
part with no sensor.

**`systems:` narrows** what is imported to those remote systems and what is inside them. A reference from an
imported part to one left out is cut: a flow's end becomes a cloud, a `driven-by` or a block's input is dropped,
an equation that names it is dropped (the remote's equations are its own business; ours never integrate them).

## 5. How remote events and metrics are read

**Measurements in place.** A local sensor reads a remote series or part:

```yaml
stocks:
  escalations-waiting:
    sensor:
      query: {source: incidents, ref: stock.escalated}   # a part's reading (or series: sensor/escalated.count)
      every: 1m
```

All the sensors of one remote are read in **one request a period**: the first to read fetches the newest reading
of every series and part the local model asks of that remote, and the others take theirs from that answer for
half a period. The engine records each reading in the local measurements as it records any query's (the local
record holds what we saw, when we saw it), so replay, fit and the charts work across the boundary unchanged.

**Stale readings.** Each reading comes with the time the remote took it. One older than three of the remote
sensor's periods (`stale`, at least two minutes) is not taken: the sensor fails with "the remote's reading is
N old". A remote that does not answer fails every sensor reading from it ("incidents at URL: unreachable").
Either way the engine records `sensor.failed` and keeps the last reading, so every view shows the last value
with its age; the remote's box says *unreachable since T* or *readings N old*, the Check page and `check`
carry `remote-unreachable` and `remote-stale` findings, and `/api/status` puts the remote among what needs
attention.

**Events in place, with a cursor.** The remote's events are read by `seq` cursor, a page of at most 1,000 at a
time, at most five pages a refresh, into a cache kept in memory and bounded by the window (one day by default,
20,000 events at most). The cursor is the last `seq` read. The cache serves `ergostat remote events NAME` (and,
later, the Record page); the remote's items are read in place through its own `/items` and `/counts`.

**What the local fold sees of remote items: nothing.** The local item index is the fold of the local record
(invariant 10); the remote's items are folded where they live. So:

- local `items:` sensors count local items only; to count the remote's, read the remote stock that counts
  them (its sensor is mirrored), or `query: {source: incidents, ref: stock.open}`;
- the Items page and `ergostat item` list local items; a remote's items are to be listed through its API,
  marked remote, linking to its own page (a later slice);
- the process map draws the remote's own map (from `/remote/v1/process`) beside ours; a line between one of
  our items and one of theirs needs an id both logs carry (a reference in an event's data) and is not drawn
  in the first slice;
- coherence (§12l) holds the three views of the **local** model against the **local** record; the remote's
  parts are left out of it (the remote checks its own), as they are of "not exercised by the record".

## 6. Modelling and analysis across the boundary

- **Analysis reads across.** Loops are found through remote parts (a local goal whose controller moves a local
  flow that drives a remote stock that drives ours closes a loop across the boundary: `explain` names the
  remote parts on it). Replay, fit and what-if use the mirrored readings of remote parts as data, never as
  state to integrate: a remote stock in a replay is an input series, like a measured disturbance.
- **The modelling loop never changes a remote part.** A proposal that would add, remove or change a remote part
  (an estimate, an equation, a rewiring) is refused like an edit to a template's part, and says why. It may
  instead write the change **as text for the remote's owner**: what to change, the evidence, the fit it would
  give. Those are kept as proposals marked `for-remote: NAME` and shown, never applied; sending them is the
  owner's act (an outbound message, by a valve the owner grants).
- **Structure on our side is ours to change**: a local flow driven by a remote stock, a goal on a remote measure,
  a new local stock fed from a remote flow, all as any proposal.

## 7. The cost model

Per remote, at the default `every: 1m`, a running local ergostat makes about **three requests a minute**:

| What | How often | Cost to the remote |
|---|---|---|
| The model | every `every`, conditional | a 304 when unchanged (the version is cached per model stamp, so it costs one hash per change) |
| Readings | one batched request every `every` (shared by every sensor of that remote) | one latest reading per series |
| Events | one page every `every` when the cache is used | an index read by `seq` |
| Process map | only when someone opens it, kept for `every` | the remote's own 5-second cache |

A failed request backs off: twice the period after each failure, up to ten periods, then once every ten
periods until it answers. The remote's token bucket caps a misbehaving consumer. A CLI process that loads the
model reads the cache and fetches only when the cache is older than `every`.

## 8. What the first slice builds

1. **The remote API** on every ergostat's page server (`ergostat/web/remote_api.py`): status, model with
   version and ETag, events by cursor, items, counts, readings, series, process; behind bearer tokens
   (`ergostat remote token`), read-only, rate-limited.
2. **`remotes:` in the YAML** (`ergostat/remote/`): loaded, checked, the model fetched, cached in the state
   folder and refreshed on `every` (and on its version moving) by the runner and the page; the parts imported
   as above.
3. **Drawn** in Dynamics, Blocks and Process as remote subsystems: closed by default, marked remote, with
   where, version and age.
4. **Source type `ergostat`**, read by `query: {source, ref | series}` sensors, batched and stale-aware.
5. **`ergostat check`** checks local references to remote parts against the remote's current model:
   `remote-reference-unresolved`, `remote-output`, `remote-unreachable`, `remote-stale`; `ergostat remote`
   lists each remote, its version and how it answered.
6. **A demo with two instances on one machine** (`examples/remote-pair/`): a local *support* model reading a
   remote *incidents* model; the remote's model changes while both run and the local follows; the remote
   stops and the local marks its data stale.

**Left for later**: the event cache feeding the Items and Record pages; cross-log lines in the process map;
proposals written for the remote's owner (the refusal is built, the text is not); serving the IR
(`?format=ir`); a remote that is itself composed of remotes (a remote's own imported parts are not served).
Mutual TLS is built (`remote-mtls`, SPEC §4c): `web: mtls:` serves the remote API alone on a listener of its
own, to client certificates one CA signed, and a `remotes:` entry's `tls:` reads it.

## 9. Decisions, in one place

| Question | Decision |
|---|---|
| What is served as the model | the compiled document, redacted, `ergostat-model/1`, hashed; the IR later beside it |
| How remote parts are named | `REMOTE-PART`, as a template's instance; the remote is a system, its systems inside it |
| Do remote blocks run here | never: every one is `external` locally |
| Remote sensors | each becomes a query of the remote's same series; one batched request per remote per period |
| Goals of the remote | evaluated here as monitors from its readings; nothing here acts on them |
| Local references to remote parts | allowed for reading, influence and material in; refused as an output |
| A reference that stops resolving | a stand-in part and a `remote-reference-unresolved` finding; the model still loads |
| The local fold | never folds remote items |
| Unreachable | the cache stands, readings fail and keep their last value with its age, findings say so |
| Authentication | bearer token per consumer, hashed at rest, read-only, loopback plus tunnel or https |
| The modelling loop | never edits a remote part; may write a proposal for its owner as text |
