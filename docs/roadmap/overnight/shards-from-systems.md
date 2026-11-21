# shards-from-systems: a pure, deterministic assignment of every part of the model to one engine shard, by top-level system, with the wires that cross between shards
depends-on: []

## Definition of done
- A new module `ergostat/spec/shards.py` (the standard library only) has `plan(spec, most=MAX_SHARDS) -> Plan`. Running it changes nothing. Nothing calls it on the running path yet.
- **Seeds.** Each top-level system (the outermost entry of `spec.chain(spec.owner(ref))`) starts one shard. Parts with no system, ergostat's own built-in kinds, and anything else nothing assigns go to the **lead** shard. The lead shard always exists, even in a model with no systems, and is the one `Plan.lead` names.
- **Merges.** Shards are merged with union-find, and each merge records why in `Plan.why[shard]` (a list of `{"joined": shard, "because": kind, "via": name}`). Two seeds merge when:
  1. blocks in both run on the same agent (its `at-once` is a semaphore in one process);
  2. blocks in both take items of the same kind (`takes.kind`), or watch it through a join, since taking a lease is locked only inside one process;
  3. blocks in both are served by the same daemon (`params["daemon"]`).
  Nothing else merges them. In particular, a signal read across systems does not.
- **Wires.** `Plan.wires` is a sorted list of `Wire(ref, source, target, kind)`. It lists every reference that a part in shard T reads from a part in another shard S, where the value exists only in memory: a goal (setpoint, error, off), a block's output or port (a command or a cascade), or an auxiliary or flow worked out from an equation rather than read by a sensor. A stock, flow or auxiliary that has sensors is read from the measurements by whichever shard needs it, so it is never a wire. Its sensors are read only by the shard that owns it.
- **Partition.** Every stock, flow, auxiliary, goal, block, sensor series, agent and item kind of the spec is in exactly one shard. `Plan.of(ref)` returns that shard and raises `KeyError` for a ref not in the spec. It never returns a default: a part nothing assigned goes to the lead shard by rule (lesson-3).
- **Ceiling.** `most` is clipped to `1..MAX_SHARDS` (`MAX_SHARDS = 16`). With more seeds than that, the two smallest shards (counted in parts; ties broken by name) merge repeatedly, each merge recorded with `because: "ceiling"`. `most=1` gives a single lead shard with every part in it.
- **Names.** Shard names are safe to use in file names: a shard is named after its first top-level system (by name), lowercased, and must match `^[a-z0-9][a-z0-9-]{0,63}$`. A name that fails gets `s-` plus the first 12 hex characters of its sha256. The lead shard is `lead`. A system called `lead` is named `lead-2`.
- **Deterministic.** The same model gives the same plan in every process, whatever `PYTHONHASHSEED` is. Every iteration is over sorted names, never over sets or dict order that depends on hashing.
- **Docs.** SPEC gets a new section "9.8 Engine shards" with the rules above. NOTES.md and the AGENT-GUIDE stay unchanged: there is no new term, and a shard is not a declaration (invariant 8: shards come from analysing the graph). docs/GAPS.md: the entry "An engine per system" says this part is done.

## Files to touch
- `ergostat/spec/shards.py` (new)
- `tests/test_shards.py` (new)
- `docs/SPEC.md`, `docs/GAPS.md`

## Risks
- **lesson-3:** a part the rules miss (a sensor on a flow with no system, a built-in kind, a library template's part) could be dropped from every shard. It would then never be read or run once sharded. The partition test covers every kind of part.
- **lesson-4:** the shard count multiplies processes in `shard-supervisor`. `most` has both a floor and a ceiling, both enforced here.
- **lesson-8:** the docs must not claim that "a shard runs alone" or that "no shard waits on another". The only claims are that the three merge rules hold and that every in-memory crossing is listed as a wire. Each claim has a test.
- **lesson-11:** shard names become file and socket names later. The name test feeds in system names like `../x`, `A B` and 80 characters.
- **lesson-9:** a merge test that passes whether or not the merge happened.

## Acceptance tests
- `tests/test_shards.py::test_every_part_in_exactly_one_shard`: on `scripts/scale_model.py`'s model at N=30 and on `examples/ticket-factory`, every part of each kind (stocks, flows, auxiliaries, goals, blocks, sensor series, agents, kinds) appears in exactly one shard. Dropping the lead shard's catch-all makes it fail (lesson-3).
- `tests/test_shards.py::test_systems_apart_unless_shared`: two systems that share nothing give two shards and no `why`.
- `tests/test_shards.py::test_shared_agent_merges`, `::test_shared_taken_kind_merges`, `::test_shared_daemon_merges`: each rule alone merges two systems, and `why` names the rule and the agent, kind or daemon. Each test fails if its rule is removed.
- `tests/test_shards.py::test_cross_reads_are_wires_not_merges`: a block in A that sets a goal's setpoint in B, an auxiliary in A whose equation reads an auxiliary in B, and a block in B commanded by A's block give three wires with the right source, target and kind, and two shards. A stock in B read by a goal in A gives no wire.
- `tests/test_shards.py::test_ceiling_merges_smallest`: 20 independent systems with `most=16` give 16 shards. `most=0` and `most=99` are clipped to 1 and 16.
- `tests/test_shards.py::test_names_safe`: system names `../x`, `A B` and an 80-character name each give a name matching the pattern, and a system called `lead` does not take the lead shard's name (lesson-11).
- `tests/test_shards.py::test_same_plan_any_hash_seed`: computes the plan in subprocesses with `PYTHONHASHSEED` 0, 1 and 2, and the JSON of each plan is identical.
- `tests/test_shards.py::test_of_unknown_raises`.
- In the report, the implementor says, for each test above, which change to `shards.py` made it fail (lesson-9).

## Size budget
200 net lines

## Notes from the plan review (answer each; not blocking)

- Wire rule omits stocks with no sensors (and any part with no sensors) whose value exists only in memory: a cross-shard read of one must be a wire. Restate the rule as 'a part with sensors is never a wire; any other stock/flow/auxiliary/goal/block output read across shards is', and split the 'stock in B read by goal in A' test into a stock with sensors (no wire) and one without (wire), else SPEC 9.8's 'every in-memory crossing is a wire' is false (lesson-8).

## Where it stopped

Built, round 1: every point above, with `ergostat/spec/shards.py` at 199 lines. No question could be asked, so these
are the choices I made. Each is the more reversible option and each is stated in SPEC §9.8:

- **The plan review's note: adopted.** A stock, flow or auxiliary with no sensor that is read across shards is a wire
  (kind `memory`; `equation` when an equation works it out). `test_cross_reads_are_wires_not_merges` covers both cases:
  a sensed stock in B read by a goal in A gives no wire, and an unsensed one gives a wire. So that test expects four
  wires, not three.
- **Shard count.** The lead is always in `Plan.shards`, and `most` counts it. So "two shards" in the tests means `a`
  and `b` beside the lead, and "16 shards" includes the lead. That count is the number of processes the supervisor
  will start, which is what lesson-4 bounds.
- **Part keys.** A sensor is keyed by its ref (`stock.x.main`), not by its series name (`sensor/x.main`). In the scale
  model a stock and a flow share names (`w0001-approve`), and their series names are the same. Agents are keyed
  `agent.NAME` and kinds `kind.NAME`.
- **Kinds.** A kind goes with the blocks that take it, even a built-in one (`ergostat.failure`, which blocks can
  lease), because its lease is locked in their process. A kind no block takes goes to its system's shard. A built-in
  kind or a kind with no system goes to the lead.
- **"Watch it through a join".** This is read as: a parent kind with a join, and the kinds whose relation names it,
  count as one kind for the kind rule. `via` names the group's first kind by name.
- **Daemons.** Only blocks' `params["daemon"]` merge shards, as written. A sensor read by a daemon that a block in
  another shard uses does not merge them. `shard-supervisor` and `engine-runs-its-shard` need to decide where that
  daemon runs.
- **Joined and via.** `joined` is the name the absorbed shard had before the merge. For a ceiling merge, `via` is
  that same name.

Found on the way, outside this gap: `scripts/scale_model.py` puts every workflow system under one top-level `org`. So
its plan has three shards whatever N is (`lead`, `org`, `modelling`) and no wires. `shards-measured` will see no
sharding of the scale model unless it changes the generator or the seed rule.

Not run here: the full unit and browser suites, because the factory runs them. Also not done: merging `origin/main`.
This clone has no `origin`, and local `main` has nothing this branch lacks.
