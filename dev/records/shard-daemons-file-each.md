# shard-daemons-file-each: a shard engine writes `daemons.SHARD.json`, and the daemon status read by the pages merges every shard's file
depends-on: []

## Definition of done
- With `shard=None` nothing changes: the engine writes `<state>/daemons.json` exactly as today, and `read_status` gives the same answer for a state directory that holds only that file.
- A shard engine's supervisor writes `<state>/daemons.SHARD.json`, using a temporary file of its own so two shards never share one. It never writes `daemons.json`, and its final write on close goes to its own file.
- `read_status(state_dir)` (`ergostat/daemons/supervise.py`) merges `daemons.json` and every `daemons.NAME.json`, where NAME matches `^[a-z0-9][a-z0-9-]{0,63}$`. Only those names are read: no `.tmp` and no other file. A file that cannot be read, or is not JSON, adds nothing and does not stop the others from being read.
- A file whose writer pid is not alive gives its daemons as `stopped` with `pid` null, never as running. This covers a shard file left by an earlier run, or by a shard the current plan no longer has.
- A daemon named in two files (it moved after a swap) is given once. The entry that is not `stopped` wins. When both or neither are stopped, the file whose name sorts first wins, so the answer does not depend on directory order.
- SPEC §9.8's "Not yet by shard" no longer lists `daemons.json`, and the §9.8 text says which file each engine writes. The GAPS entry's "Left" drops `daemons.json` per shard and still names `shard-wires`, `shard-supervisor` and the measurements as left.

## Relation to other work
- gap/shard-supervisor: runs one process per shard, so each shard's file has its own pid. That gap builds on this one, and this one does not touch `runner.py` or `watcher.py`.
- gap/shard-wires: no overlap, because it touches `spec/shards.py` and how values are carried.
- shard-moved-flow-read-by-owner: a sibling sub-gap. Both edit SPEC §9.8's "Not yet by shard" list, and each removes only its own item.

## Files to touch
- `ergostat/daemons/supervise.py`
- `tests/test_engine_shard.py`
- `docs/SPEC.md`
- `docs/GAPS.md`

## Risks
- lesson-3: an unreadable shard file, or one whose writer is dead, is read as daemons still running, or one bad file empties the whole answer. `test_daemon_files_merged_dead_writer_stopped` guards this.
- lesson-5: a shard file from an earlier plan keeps showing its daemons under the same names after the shard is gone, or after the daemon has moved. The dead-pid and two-file tests guard this.
- lesson-7: a GAPS.md merge splices this entry's "Left" clause into another entry. Merge origin/main, reread the entry whole, and run the suites again.

## Acceptance tests
- `tests/test_engine_shard.py::test_shard_engine_writes_its_own_daemons_file`: shard engines `a` and `b`, each with a daemon, write `daemons.a.json` and `daemons.b.json`, and no `daemons.json`. A `shard=None` engine writes only `daemons.json`.
- `tests/test_engine_shard.py::test_daemon_files_merged_dead_writer_stopped`: `read_status` returns both shards' daemons. A file whose pid is dead gives `stopped` with pid null. An unreadable file and a `daemons.x.tmp` add nothing, and the other files are still read.
- `tests/test_engine_shard.py::test_daemon_in_two_files_given_once`: the same name, running in one file and stopped in the other, is given once as running. When both are stopped, the first file by name wins, whatever order the directory lists them in.

## Size budget
35 net lines
size: S (confidence: medium)
