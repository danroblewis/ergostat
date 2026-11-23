# Measuring the code's complexity in ergostat itself: the engineering

The owner's ask (`plan/complexity-ask.md`): measure the code's complexity in as many forms and slices as we can, as
stocks of the factory model on main, backfilled from git history. These notes cover how that would be built in
ergostat: what exists, what the record can and cannot take, what a measurement script, its cache and the backfill
cost, and which parts are a script, a model change or a core change. Read against ergostat main `ae7bdc89ab`.
Paths below are relative to the ergostat checkout. Experiments were run on a bare clone under `work/cx/`, on a
machine with a load average of about 72, so the times are pessimistic.

## 1. What already exists (start here, do not build beside it)

The factory already measures code size, hourly, on main:

- `dev/model/code-health.yaml:48-97`: five **auxiliaries** (`code-net-lines`, `code-long-functions`,
  `code-duplicates`, `code-dead-candidates`, `code-coverage`), each with a `run:` sensor, for example
  `sensor: {run: python3 dev/bin/measure.py code-net-lines, every: 1h, timeout: 11m, ...}` (line 52), and five
  `*-change` auxiliaries (lines 73-97) with goals "not rising over main's last 10 merges" (lines 99-124). A size goal
  off fires the simplifier (`block.code-drift`, lines 153-162).
- `dev/bin/measure.py:354-397`: each code reading runs `scripts/code_evidence.py --ref <main sha>` in full, sums one
  field over its rows, and appends `{"measure", "seq", "sha", "value", "at"}` to `run/code-measures.jsonl`
  (line 396). `seq` is `git rev-list --count --first-parent <sha>` (line 366). `measure.py NAME-change`
  (lines 400-421) reads that file back, one value per sha, ordered by seq, never by time.
- `scripts/code_evidence.py` reads a git ref, **never the working files**: `ls-tree` plus one `git cat-file --batch`
  (lines 49-60), parses each module with `ast` (lines 92-104), and prints one JSON row per module of `ergostat/`,
  `dev/bin/`, `scripts/` (lines 107-131): net lines, long functions (>60 lines), churn (60 days), duplicate bodies
  (names and constants blanked, hashed), dead candidates.

So the pattern the complexity work needs (a stdlib script that measures a git ref, a `run:` sensor that prints one
number, a JSONL history stamped by sha and seq) is already in the codebase. Two weaknesses to fix while extending it:

1. **Each of the four code sensors recomputes the whole evidence** (`measure.py:370`, a full `code_evidence.py` run
   per sensor per hour: 4.3 s wall, 150 MB RSS at HEAD in my run). Thirty more measures done this way would be
   thirty full runs an hour. They should all read one result computed once per sha.
2. **They are auxiliaries, but by the SPEC's own rule they are stocks.** SPEC §7a (`docs/SPEC.md:2035-2046`):
   "Memory decides the kind ... What persists when nothing happens and changes only through some process is a
   stock". Code size persists between merges and changes only through merges. The owner also asked for stocks.
   A stock with no flows is a finding (`stock-without-flows`, `docs/SPEC.md:2103`, `ergostat/spec/findings.py:63`),
   so each needs flows; the SPEC already has the instrument for that (`changes:`, section 4 below).

## 2. How a stock, a sensor and its readings are declared and recorded

**Declared** in the factory model: `ergostat.yaml` includes `dev/model/*.yaml` (`ergostat.yaml`, `include:`), so a
new `dev/model/complexity.yaml` is picked up with no other edit. A sensor sits inside the stock, flow or auxiliary it
measures, with exactly one kind: `run`, `query`, `manual`, `items`, `changes`, `builtin` or `daemon`
(`docs/SPEC.md:1864-1935`). For a `run` sensor the keys are `run:` (a shell command run in the model's folder),
`every:` (default `1m`) or `cron:`, `timeout:` (default `30s`), `parse:` (a regex with one group), `unit:`
(table at `docs/SPEC.md:1900-1925`; IR at `ergostat/spec/ir.py:518-537`).

**Read**: `read_sensor` (`ergostat/spec/engine.py:2371-2411`) runs the command with `shell=True, cwd=spec.root`,
`timeout=s.timeout`, and an environment carrying `ERGOSTAT_CMD`, `ERGOSTAT_STATE_DIR` etc.; non-zero exit or timeout
is no value (`sensor.failed` event). `number_in` (`engine.py:2445-2466`) takes the **last** bare number, or the last
JSON line's `"value"`. Any other key on that line (an `"at"`, say) is ignored. A run sensor may also print
observation lines about items (`docs/SPEC.md:1927-1934`), which become events.

**Recorded**: the engine stamps the reading with the time it was read and writes `(s.series, t, v)` with
`measurements.add_many` (`engine.py:1553-1555`), or `measurements.add(s.series, v)` on the thread path
(`engine.py:1391`). The series name is `sensor/<part>.<sensor>` (`ir.py:565-566`), e.g.
`sensor/code-net-lines.main`. The store is SQLite `measurements.db`: table `samples(series, time, value)`
(`ergostat/store.py:40-45`), rolled into tiers. Defaults (`ergostat/storage.py:40-41`): raw readings kept 2 days,
then 1-minute buckets for 14 days, 10-minute for 90 days, 1-hour for 2 years (`docs/SPEC.md:669-671, 765-776`).
Events (`events` table, or segments) are a separate store (CLAUDE.md invariant 10), kept `keep:` 30 days by default
(`docs/SPEC.md:759`), so **a history of readings belongs in the measurements store, not in events**.

**Read-after-act**: when a block moves a flow, the engine reads the sensors of the stocks that flow connects at once
(`engine.py:836-842`, `after_acting` at 847). That is how a stock fed by `flow.gaps-merged` gets read right after a
merge without a short `every:`.

## 3. Can readings be written with past timestamps? The store can; nothing exposed can

**The store API takes a time.** `Measurements.add(series, value, at=None)` (`store.py:608-613`) and
`add_many([(series, time, value)])` (`store.py:615-624`) both accept any time. A reading for a span already rolled
into buckets is put aside in `late` (`store.py:599-606`) and merged into its buckets at the next roll
(`_merge_late`, `store.py:882-896`; `roll`, 898). The VictoriaMetrics backend takes times too
(`ergostat/victoria.py:134-154`). Core code already writes past readings: run costs (`ergostat/costs/record.py:39-46`)
and a rename's copied history, which skips times already present (`ergostat/numbers/proposals.py:1055-1072`).

**No command, API or sensor output reaches it with a time:**

| Path | Evidence | Past time? |
|---|---|---|
| `ergostat sensor STOCK.SENSOR --read V` | `cli/__init__.py:306`; `cli/spec_cmds.py:291-308` calls `p.measurements.add(s.series, float(value))` | No. Only for a `manual: true` sensor (line 302). The global `--at` (`cli/__init__.py:121`, "as it was then") is parsed but `read_manual` never reads it: `--read 5 --at 1d` records now, silently |
| MCP `read_sensor` | `ergostat/mcp.py:335-342` | No; manual sensors only |
| `run:` sensor output | `engine.py:2445-2466` | No; `{"value": n, "at": t}` loses `at` |
| daemon push `{"reading", "sensor"}` | `ergostat/daemons/proc.py:272-283` | No |
| `ergostat event --add TYPE` | `cli/__init__.py:203`; `cli/record.py:176-225` | Events, not readings; `Events.add(at=...)` exists (`store.py:245-255`) but `add_event` never passes `--at` |
| old-model agent line `{"sensor", "value"}` | `ergostat/runner.py:189-195` | No |

Also, a sensor is exactly one kind, so a `run:` sensor cannot also take manual readings.

**Conclusion: a backfill needs a core change.** `dev/bin` programs reach the record only through the CLI
(`$ERGOSTAT_CMD`, `dev/bin/fac.py:94-99`; the rule is stated in `docs/roadmap/overnight/state-times.md:104`: "dev/bin
reads the record only through the CLI"), so opening `measurements.db` from a script is not an option.

### The core change: `ergostat sensor STOCK.SENSOR --backfill FILE`

About 60-100 lines in `ergostat/cli/parts.py` and `cli/spec_cmds.py`, plus a store conformance test:

- Input: JSON lines `{"at": <epoch>, "value": <n>}` from a file or `-`, for a sensor of any kind that records a
  value (`run`, `query`, `manual`, `daemon`); refused for `items`, `changes` and `builtin`, which ergostat derives.
- Refused: an `at` in the future, or not a number; a value not a number. Readings whose `(series, at)` is already
  there are skipped, as `numbers/proposals.py:1068-1069` does, so a backfill run twice writes nothing the second time.
- Written with one `measurements.add_many` (late readings then land in their buckets at the next roll).
- Recorded with one ergostat event, `sensor.backfilled` (item: the sensor; data: count, first and last `at`, skipped,
  and a free `from` text such as `complexity.py backfill 726760f..ae7bdc8`). That keeps invariant 11 (defined and
  inferred distinguishable): a page or `ergostat explain` can say which span of a series was backfilled.
- `--json` says what was written. The same op in MCP is optional, not needed here.
- The smaller fix alongside it: make `sensor --read V --at T` either honour `--at` or refuse it, instead of
  silently recording now.

One process per reading through `--read --at` would also work after the small fix, but only for manual sensors,
and 589 commits x 30 series is about 18,000 process starts. The batch flag is the right shape.

What the core change does not need: no change to the stores, the tiers, the engine or the page. Readings older than
2 days are kept as 1-minute buckets for 14 days, then 10-minute, then hourly for 2 years. A bucket read one by one
gives its last reading (`docs/SPEC.md:771-772`), so two merges in the same minute lose the first in the record. The
cache (section 5) keeps every sha at full detail; the record is the coarse, charted view.

## 4. The measurement script as a sensor

One program, `dev/bin/complexity.py` (stdlib only, like `measure.py` and `code_evidence.py`; `pyproject.toml` has
no analysis dependencies and the experiments below needed none):

- `complexity.py compute [SHA]`: measures one sha of main (default the checkout's `main`, resolved once, as
  `measure.py:365` does) into the cache; returns at once if the sha is already there.
- `complexity.py read NAME`: prints one number, `compute`'s result for main's current sha (computing it first if
  missing). This is what each sensor runs.
- `complexity.py backfill [--since SHA]`: walks main's first-parent history (section 6), computes what is missing,
  and pipes each series' readings to `$ERGOSTAT_CMD sensor PART.main --backfill -`.

**The sensors.** Thirty or more `run:` sensors each starting Python every 10 minutes is about 3 process starts a
minute: acceptable, but the SPEC's answer for many sensors is a **daemon** (`docs/SPEC.md:3038-3062`): one
long-lived `python3 dev/bin/complexity.py daemon` declared once under `daemons:`, every sensor
`sensor: {daemon: complexity, every: 10m}`. It answers `{"op": "read", "sensor": ...}` from the cache, so a reading
costs a dictionary lookup, and computes a new sha when main moves. Either works; start with `run:` (simplest, same
as `measure.py`) and move to the daemon if the count grows. Settings: `every: 10m` (cheap once cached; the reading
lags a merge by at most 10 minutes) and `timeout: 5m` (one sha is computed in seconds; `code-health.yaml`'s `11m` was
for a full evidence run on a loaded machine).

**When the stamp should be the merge time.** A live reading is stamped when read (`engine.py:1553`). Between merges
the stock is flat, so a reading stamped up to 10 minutes late is a correct level. If the stocks are drawn as fed by
`flow.gaps-merged` (`driven-by: [+flow.gaps-merged]`, as `code-health.yaml:51` does), they are not re-read on a
merge: read-after-act (`engine.py:836-847`) only reads stocks the moved flow connects. Short `every:` is the simple
answer.

## 5. Where the results live: a cache keyed by content, then by commit

Under the instance's `run/` (`dev/factory.toml` `[paths] run = "run"`, resolved by `fac.run_dir`,
`dev/bin/fac.py:56-59`), never in git (derived data, rebuilt from git at any time):

```
run/complexity/
  blobs.jsonl          one line per git blob sha: that file's own measures (additive ones: bytes, lines, net lines,
                       tokens, AST nodes, functions, classes, cyclomatic, max nesting, imports, Halstead volume,
                       zlib/bz2/lzma sizes; plus what tree-wide measures need: body hashes, top-level names)
  commits/<sha>.json   one main commit: {sha, seq, at (committer time), version of the measures,
                       slices: {slice: {measure: value}}, tree: {measure: value}} (tree-wide measures)
  readings.jsonl       what was sent to the record: {series, sha, at, value} (so a backfill knows what it sent)
```

**Two levels of cache, because most measures are sums over files.** A blob (a file's exact content) never changes,
so its measures are computed once in all history. A commit's per-slice totals are then sums of its tree's blobs
(`git ls-tree -r <sha>`: path to blob). Only the files a merge changed are new blobs: median 5, p90 18, max 49
`.py`/`.js` files per first-parent commit of main (443 of 589 touch any). Slicing is free after that: any grouping of
paths (top directory, package, module, test vs product, file age, file size class, owner gap) is another sum over
the same blob table, recomputable for the whole history in seconds without re-reading a file.

**Tree-wide measures are computed per commit, not per blob**, because they are not sums: whole-tree compressed size
(the Kolmogorov proxy that sees cross-file repetition), duplicate bodies across files, dead candidates (a name nothing
else names). They are kept in `commits/<sha>.json` and never recomputed for a sha already there.

**A measures version.** Each line and file carries the version of `complexity.py`'s measures (a constant bumped when
a definition changes). A new version recomputes into a new cache and backfills its series again; readings of an old
definition are not mixed into a series (a changed definition gets a new series name, or the old series is set aside
with `--forget-above/-below`, `cli/__init__.py:307-310`).

## 6. The backfill: walking the history cheaply

**What to sample.** `main` has 2,663 commits (the 2,739 counts other refs); 589 on its first-parent line, 283 of
them merges; 9 calendar days (2026-11-14 to 2026-11-22). The first-parent commits are exactly the states main was
in, each stamped by its committer time, which is monotonic along that line (0 of 589 out of order, checked). The
other 2,074 are branch commits: their times are when they were made on a branch, not when main had them, so a
series through them would show states main never had. Daily sampling would give 9 points, too few for any rate.
**Sample every first-parent commit of main** (589 now, about 100 a day added). Stamp each reading with that
commit's committer time (`%ct`), and record its `seq` as `measure.py` does.

**No worktree and no checkout.** `git cat-file --batch` reads every blob straight from the object store, as
`code_evidence.py:49-60` already does. `git archive <sha> | tar -x` (0.11 s, 9.9 MB for `ergostat dev scripts` at
HEAD) is needed only for an external tool that wants files on disk; none is planned (everything below is `ast`,
`tokenize`, `zlib`, `bz2`, `lzma`). A worktree per commit is never needed.

**Measured on a bare clone (26 MB) with stdlib Python, 4 processes, load average ~72:**

| Step | What | Time | Disk |
|---|---|---|---|
| Unique `.py` blobs in all of main's history | `ls-tree -r` of every commit (a `git log --raw` replay is faster: 0.05 s for the whole first-parent diff) | 58 s (the slow way) | 0.6 MB list |
| Per-blob measures, every unique `.py` blob ever | 4,855 blobs, 141 MB of text: bytes, lines, net, tokens, Halstead volume, AST nodes, functions, classes, cyclomatic, max depth, imports, zlib-9, bz2-9, lzma-6 | 34 s wall (100 s CPU), 420 MB RSS | 1.3 MB JSON (0.34 MB gzipped) |
| Per-commit slice sums, 589 first-parent commits | `ls-tree -r` each, sum cached blobs into 6 slices | 16 s, one process | 1 MB JSONL |
| Whole-tree compression per commit | product code concatenated (5.0 MB at HEAD) | zlib-9 0.34 s, bz2 0.24 s, lzma 1.8-3.1 s at HEAD; about 1 s on average over history (estimated: the full 589-commit run, one process, was stopped after 3.5 CPU-minutes on the loaded machine) | none kept |
| `code_evidence.py` per commit (the existing four measures, identical to the live sensors) | full run | 4.3 s at HEAD, 0.7 s at `main~300`, 0.2 s at the root | none kept |

**Totals for the 589 commits:** per-blob measures about 0.5 minute, slice sums under 0.5 minute, whole-tree lzma
about 10 CPU-minutes (2.5 minutes on 4 cores), `code_evidence.py` per commit about 20 CPU-minutes (5 minutes on 4
cores). All in, **under 10 minutes on 4 cores, under 5 MB of cache**, a few hundred KB in `measurements.db`
(589 commits x 30-80 series is 18,000 to 47,000 rows). Every new merge afterwards costs a few new blobs plus the
tree-wide measures of one commit: 2 to 8 seconds. Memory: cap the pool at 4 processes and stream blobs in chunks;
the 420 MB peak came from one process holding a 32nd of all history's text at once, and can be cut by smaller chunks
(the owner's load-test rule: watchdog RSS and threads, cap N).

A few results from the run, to show the measures move: at HEAD the product code (`ergostat/`, `dev/bin/`,
`scripts/`) is 83,060 net lines (the owner's "81,000"), 5.0 MB; files compressed one by one with lzma sum to
1.65 MB, the whole tree compressed at once to 1.13 MB. So about 32% of what the files hold one by one is
repetition across files, which only a whole-tree compression (or NCD between modules) sees. zlib's 32 KB window and
bz2's 900 KB block see much less of it (zlib-9 1.49 MB, bz2 1.16 MB for the same tree): use lzma for the K proxy and
keep zlib only as a per-file measure. Across history, Python net lines went from 2,339 (the root, 18 files) to
35,843 (midpoint) to 153,010 (HEAD, 722 files, tests included).

**Order of work in the backfill:** list first-parent commits with `%H %ct`; replay `git log --first-parent -m
--raw --no-renames` to get each commit's changed blobs (faster than `ls-tree` per commit); compute missing blobs in
a pool of 4; per commit, sum and compute tree-wide measures in the pool; write `commits/<sha>.json`; then, per
series, one `--backfill -` call with all its readings. Resumable at every step, since each writes only what is
missing.

## 7. The model change: `dev/model/complexity.yaml`

A new file (picked up by `include: dev/model/*.yaml`), a system inside `code-health`, a stock per measure and
slice, each with a `run:` sensor (or the daemon) and two flows measured from the stock's own readings, so nothing
new is needed to have "grown" and "distilled" rates:

```yaml
defaults:
  system: complexity
systems:
  complexity:
    within: code-health
    description: the code's complexity on main, by measure and by slice, measured per merge and backfilled from git
    show: [stock.code-lzma-bytes, stock.code-net-lines, stock.code-cyclomatic, ...]
stocks:
  code-lzma-bytes:
    unit: bytes
    description: the product code (ergostat/, dev/bin/, scripts/) compressed as one stream by lzma, on main - a
      Kolmogorov-complexity upper bound that sees repetition across files
    sensor: {run: python3 dev/bin/complexity.py read code-lzma-bytes, every: 10m, timeout: 5m,
             description: complexity.py, cached per sha}
flows:
  code-lzma-grown:
    to: code-lzma-bytes
    description: what merges added to it
    sensor: {changes: rises, over: 1d}
  code-lzma-distilled:
    from: code-lzma-bytes
    description: what merges took out of it
    sensor: {changes: falls, over: 1d}
```

(`changes:` flows, `docs/SPEC.md:1917` and `engine.py:2414-2443`: the rate from the stock's own successive
readings, read back through `measurements.range`, so with a backfilled stock the rate is right from the first day.
Do not also draw these flows as caused by `flow.gaps-merged`: a `changes` flow drawn as caused by another flow is
the finding `measured-not-caused`, same row.) A goal on a distilled flow, or on a
ratio auxiliary (`lzma-bytes / net-lines`, density), can later drive the simplifier exactly as `code-drift` does
now; that is the designer's call, not needed to start measuring.

**How many parts.** Each stock with two flows is three parts in the diagram. 10 measures x 6 slices is 60 stocks
and 120 flows, which the diagram and `check` would carry but the page would drown in. Suggested: stocks for the
headline measures on the whole product (perhaps 8-12), and the slices as more stocks only where a goal will read
them; everything else in the cache, where any slice is a sum away. The existing five auxiliaries in
`code-health.yaml` should become stocks of this file, read from the same cache (and `measure.py`'s `-change`
measures read `commits/<sha>.json` by seq instead of `run/code-measures.jsonl`), so there is one measurement path,
not two.

## 8. What is a script, what is a model change, what is core

| Part | Kind | Size | Notes |
|---|---|---|---|
| `dev/bin/complexity.py` (`compute`, `read`, `backfill`, later `daemon`): blob cache, commit cache, measures, slices | script (factory) | 300-500 lines, plus `tests/test_factory_complexity.py` | stdlib only; reads git refs, never working files; 4 processes at most |
| Fold `measure.py`'s code measures onto the cache | script (factory) | net removal | `measure.py:354-421` reads the cache; `code_evidence.py` stays the simplifier's evidence, or becomes a view of the cache |
| `dev/model/complexity.yaml`: system, stocks, sensors, `changes:` flows; the five code auxiliaries turned stocks | model | 100-200 lines of YAML | `ergostat check` clean: no `stock-without-flows` |
| `dev/README.md` section (how it is measured, cached, backfilled) | docs | | |
| `ergostat sensor STOCK.SENSOR --backfill FILE` with dedupe and a `sensor.backfilled` event; `--read --at` honoured or refused | **core** | 60-100 lines, plus a conformance test (both backends) and SPEC §6 | the only core change; a gap of its own, landed first |
| Marking backfilled spans on the page | core, optional | | from the `sensor.backfilled` events; not needed to start |

Order: the core gap (`--backfill`) and the script can be built in parallel; the model file lands with the script;
the backfill runs once, by hand or as a one-shot run, after both are on main.

## 9. Open points and risks

- **Readings vs. ergostat's `keep` and tiers.** Readings older than 14 days are 10-minute buckets; older than 90 days
  hourly. Per-merge detail lives in the cache only. Fine for charts and fitting; say so in the README.
- **Rewrites of main.** A force-push that drops shas leaves readings for states main no longer had. Like
  `measure.py:416`, the reader should check `merge-base --is-ancestor` and the backfill should only send shas on
  main now.
- **The machine.** Load average was ~72 during these runs; the backfill must stay inside the resource caps the
  factory already measures (`dev/model/resources.yaml`) and the 4-process cap.
- **JS files** (34): no `ast`; count them with tokens by regex and compression, as their own slice, never mixed into
  the Python AST measures.
- **Definition drift.** Any change to a measure's definition is a new measures version and a new backfill (seconds
  to minutes), never a silent change inside a series.
