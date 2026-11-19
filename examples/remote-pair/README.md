# A remote pair: one ergostat reading another's system

Two ergostat projects on one machine, each with its own record:

- **`incidents/`** is the **remote**: an incident desk, run by its own ergostat (think: the on-call team's).
  Incidents arrive as files in `queue/`; a responder works them off while more than 6 are open (`few-open`).
- **`support/`** is the **local** model: a support desk whose tickets rise with the incidents over there.
  Its `remotes:` entry brings the incident desk in as a system, `incidents`, drawn closed and marked remote.

```yaml
remotes:
  incidents:
    url: http://127.0.0.1:8796
    token-file: incidents.token          # made on the remote: ergostat remote token support
    every: 10s
```

What `support` does with it, and what it never does:

- It draws `incidents` as a **remote subsystem** in Dynamics and Blocks (dashed, with where it runs, its model's
  version and how old its readings are) and the remote's process map beside its own in Process. Open the box
  to see its parts: `incidents-open`, `incidents-opened`, `incidents-resolved`, `incidents-few-open`, and its
  blocks `incidents-pager` and `incidents-responder`, which are `external` here: **they run there, never here**.
- Its own parts **reference remote parts**: the flow `filed` is `driven-by: [+stock.incidents-open]` (a cause
  across the boundary), the block `customers` reads `stock.incidents-open`, and the goal `incidents-calm` holds
  a remote stock. `incidents-calm` is **watched here and acted on there**: nothing here may act on a remote part
  (a block that tried would be refused by `ergostat check`, `remote-output`), so its loop is open on purpose.
- It reads the remote's readings **in place**, one request every 10 s for all of them, and the remote's
  events by cursor (`ergostat remote events incidents`).

## Run it

```sh
sh examples/remote-pair/run.sh          # starts incidents on 8796 and support on 8797; stop: run.sh stop
```

The script copies both projects to a scratch folder, starts `incidents`, makes a token for `support` there
(`ergostat remote token support`), puts it in `support/incidents.token`, and starts `support`. Then:

```sh
ergostat -C <scratch>/support remote        # the remote: its url, version, parts, how it answers
ergostat -C <scratch>/support check         # references into it, checked against what it serves now
open http://127.0.0.1:8797/diagram           # the remote drawn as a closed, dashed box: Open it to see inside
```

## Watch it follow and go stale

1. **The remote's model changes while both run.** Add a flow to `incidents/ergostat.yaml` (say
   `escalated: {from: open, system: response}`). Within `every` (10 s) `support` reads the new version and
   reloads: `ergostat -C <scratch>/support remote` shows it, and `incidents-escalated` is drawn.
2. **A reference that stops resolving is a finding, not a crash.** Rename `open` in the remote to `waiting`.
   `support` still loads: `incidents-open` becomes a stand-in with no sensor, and `ergostat check` says
   `remote-reference-unresolved` for `filed`, `customers` and `incidents-calm`, naming the version it went
   missing in.
3. **The remote stops** (`ergostat -C <scratch>/incidents run --stop`). `support` keeps running on what it read
   last: its readings of the remote stay at their last values with their age, each failed reading is recorded
   (`sensor.failed`), the box says *not answering for 30s · readings 40s old*, and the status and
   `ergostat check` carry `remote-unreachable`. Start it again and everything picks up.
