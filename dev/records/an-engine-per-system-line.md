## Entry

section: Runtime, scale and latency

- **An engine per system; line routing for large diagrams** (open; `docs/proposals/scale.md`). Done of it: the plan
  (`shards-from-systems`, SPEC §9.8): every part assigned to one shard by top-level system, merged by a shared agent,
  taken kind or daemon (a block's or a sensor's), with the in-memory values read across shards listed as wires; and
  an engine of one shard (`engine-runs-its-shard-1`, SPEC §9.8): `Engine(project, shard=NAME)` works only on its
  shard's built-ins, machine blocks, goals, clock, item work, triggers, joins, daemons, observer and readings, and a
  swap clears what moved out; each owner's ask is followed only by the shard that owns what it names (an unknown
  one by the lead), and only the lead does the one-time duties (`engine-runs-its-shard-2`). Each shard engine has
  its own calls socket, `heartbeat.SHARD.json` (read by the watcher when its pid is the engine's) and
  `ergostat.stopped`, both events carry `data.shard`, its `close` stops only its own runs and daemons, and an
  unknown shard is a `ShardError` (`engine-runs-its-shard-join-1`). `ergostat run` still runs one engine for the
  whole model. Also done (`route-one-large-system-in-parts`): a line group of more than 100, one system's view
  included, routed in parts of at most 100 (`static/routeparts.js`; `docs/layout-rules.md`), the shared group past
  100 lines routed free. Also done (`shard-moved-flow-read-by-owner`): a moved flow's stocks are read at once by the
  shard engine that owns each, the others following the run's ended event by `seq`. Also done
  (`shard-daemons-file-each`): each shard engine writes `daemons.SHARD.json`, and the pages' daemon status merges
  every shard's file, a dead writer's daemons read as stopped. Left: the wires carried between shards, and refused
  until then (`shard-wires`); a process per shard (`shard-supervisor`); the measurements; for the lines, the quick first pass (`line-routing-for-large-diagrams`), and scale_model's
  one-system view measured again. A reshard on swap is not needed: a swap clears what moved out.
