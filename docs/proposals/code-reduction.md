# What ergostat's code can lose: a map, with evidence

The owner, 2026-11-21: before ergostat is given to people, review and reduce the amount of code. This is the map;
later gaps make the cuts. Nothing here changes code. Every line reference is to `main` as of 277a9c6c. The first draft
was made on 1336e50e, and every reference was checked again on 277a9c6c and moved where main had moved it (§1, the
last paragraph).

**What was looked at:** `ergostat/` (Python and the page's own JavaScript in `ergostat/web/static/`) and `dev/bin/`.
**The total:** eleven items, about **1,310 net lines**. That is about 1.4% of the 91,289 lines `wc -l` counts in the
Python of `ergostat/` and `dev/bin/` (`git ls-files 'ergostat/*.py' 'dev/bin/*.py' | xargs wc -l`). Little of the code
is dead. Most of what can go is a whole feature that a newer one replaced, or that sits outside ergostat's purpose. Each of those is the owner's decision, not a finding.

"Net lines" means lines that are neither blank nor only a comment (the rule `scripts/code_evidence.py` uses). For whole
files they were counted with the Grep pattern `^\s*[^\s#]`. For spans they were counted by reading the lines named
(marked ≈).

## 1. How "no caller" was checked (lesson-8)

Python could not be run in this session (the shell refused `python3`, `uv run python`, `awk`, redirection and pattern
files). So `scripts/code_evidence.py` was **not run**. The same rule was applied with `git grep`, and it was extended
to the docs:

1. **The names.** `git grep -h -E '^(def|class) ' -- 'ergostat/*.py' 'dev/bin/*.py' | sed -E 's/^(def|class)
   ([A-Za-z0-9_]+).*/\2/' | sort | uniq` gave 2,502 top-level names.
2. **Every mention, everywhere.** `git grep -h -o -w -E 'NAME|NAME|…' | grep -v '^Binary' | sort | uniq -c | grep -E
   '^ +[12] '` was run in seven batches over **all 1,398 tracked files**: code, `tests/`, `docs/`, `dev/records/`,
   `dev/model/*.yaml` (the `run:` lines), `examples/`, `pyproject.toml`. A name counted once is named only by its own
   `def`. Each one found was then located with `git grep -n -w NAME`.
3. **Mentions in code only.** The same count over `-- ergostat dev/bin dev/model 'dev/*.toml' scripts examples
   pyproject.toml` finds a name whose only other mentions are in tests or docs.
4. **Whole modules.** Each module's last name (e.g. `parity_draft`) was counted over the same code paths. Every module
   of `ergostat/` and `dev/bin/` is named in code outside itself. Each `dev/bin/` script is imported, or has a `run:`
   line in `dev/model/*.yaml` or `dev/factory.toml`.
5. **The page's JavaScript.** `git grep -h -E '^function '` over the 18 files of ergostat's own JavaScript (the vendored
   `elk.bundled.js`, `libavoid/`, `highlight.min.js` and `uplot/` were left out) gave the names. Each was counted over
   `-- ergostat tests scripts docs`.
6. **Same-named functions.** `git grep -h -E '^def ' … | sort | uniq -c | sort -rn` listed names defined in many
   modules. The ones that look alike were read side by side.
7. **Flags.** Every `os.environ.get("…")` / `os.environ["…"]` in `ergostat/` and `dev/bin/` was listed, and each name
   was searched for across the repository.
8. **Superseded paths.** `docs/SPEC.md`, `docs/GAPS.md` and `docs/DESIGN.md` were searched for
   `supersed|deprecat|legacy|no longer|replaced by|to be removed`.

**What this method cannot see.** Only top-level names at column 0 were counted (methods, nested functions and module
constants were not). Two modules defining one name count together, so a dead copy beside a live one is missed. A name
put together at run time (`getattr`, a string built from parts) looks dead only if it is never spelled out whole. Such
a name would be a false "dead", and none of the eleven below is one. Duplicates were found by reading same-named code,
not by hashing every body (`code_evidence.py`'s `duplicates`). Coverage was not measured. The first gap's acceptance
test runs `code_evidence.py` to confirm its numbers.

**Checked again on 277a9c6c.** Main gained about 3,750 lines in 67 files of `ergostat/`, `dev/bin/`, README and SPEC
after 1336e50e. In this second session
`python3`/`uv run python` were refused again, and so were shell loops and long pipelines. So passes 1 to 3 were **not**
run again over the new code: a name added after 1336e50e and never called is not in this map. What was done instead:
each name in item 4 was searched again with Grep over every file (only its own `def` and the mentions shown in item 4
remain), each file the map cites was checked with `git diff 1336e50e main`, and every line in a changed file (SPEC,
GAPS, `dev/bin/fac.py`, `dev/bin/watch.py`, `numbers/review.py`, `numbers/structural.py`, `remote/compose.py`,
`remote/serve.py`, `library/trust.py`, `library/expand.py`, `spec/compile.py`, `spec/load.py`, `spec/ir.py`,
`spec/engine.py`, `repair/fix.py`, `cli/intent.py`, `cli/remote.py`, `web/server.py`, docs/MESSAGES.md,
`tests/test_graph_cli_web.py`) was read again and its number corrected. Item 2 was surveyed again from the start (it
names every site `git grep -n "ergostat.toml" -- ergostat` finds).

## 2. The ranking

Risk: 1 = nothing calls it, or a pure refactor under existing tests; 2 = a user-visible command or text changes, or a
lock is touched; 3 = a format or promise in SPEC or the README changes, or the tests must be rewritten widely. Each
score is net lines divided by risk.

| # | Item | Evidence | Net lines | Risk | Score |
|---|---|---|---:|---:|---:|
| 1 | Delete the parity benchmark (`ergostat bench parity`) | outside the product's purpose; one caller | ≈487 | 2 | 243 |
| 2 | Stop reading `ergostat.toml` (the format before YAML) | superseded, said in README and SPEC | ≈482 | 3 | 161 |
| 3 | Drop `check --example`'s TOML starters and the empty-folder hint that points to them | superseded; no test | ≈75 | 2 | 37 |
| 4 | Delete ten dead names, and one only a test calls | no caller on main | 37 | 1 | 37 |
| 5 | Delete `avoidMove` and the router's single-part move (JS) | no caller on main | ≈34 | 1 | 34 |
| 6 | Brief `ergostat chat` from the agent guide instead of a TOML brief | superseded format | ≈62 | 2 | 31 |
| 7 | One helper for the item records of actions, messages and reports | duplicate code | ≈45 | 2 | 22 |
| 8 | One flock helper in `ergostat/` and one in `dev/bin/` | duplicate code | ≈35 | 2 | 17 |
| 9 | Stop reading the old name `variables:` (and `variable.X`, a goal's `variable:`) | deprecated in SPEC | ≈35 | 3 | 12 |
| 10 | One percentage and one "ago" formatter for the CLI | duplicate code | ≈10 | 1 | 10 |
| 11 | Stop re-signing old Node/Java/Go failures (`failure.superseded`) | a one-time migration in SPEC | ≈7 | 2 | 4 |
| | **Total** | | **≈1,309** | | |

Items 2, 3 and 6 overlap in subject (all are TOML), but not in lines: item 2 counts only what 3 and 6 leave behind.
Item 2's count rose from ≈330 in the first draft: the first draft missed the TOML body of `model.check`,
`cmd_convert`, the converted-spec path of `blockdiagram.spec_of`, the scrubber's TOML branch and the old runner's
start, and it counted all of `spec/convert.py`, whose YAML writer two other modules import.

## 3. The items

### 1. Delete the parity benchmark

- **Files and lines.** `ergostat/bench/parity.py` (342 lines, 290 net), `ergostat/bench/parity_draft.py` (119, 98 net),
  `ergostat/cli/bench_parity.py` (109, 95 net). The places that load it: `ergostat/cli/bench.py:35` and `:43-45` (`_parity`, `from
  .bench_parity import register`), `:81-83` (`cmd_parity`) and `:84` (the usage line), and the help line at
  `ergostat/cli/__init__.py:88`. `ergostat/bench/contexts.py` **stays**: `ergostat/recipes/talk.py:17` imports
  `NOT_OWNER, Turn, turns` from it.
- **Evidence.** It measures whether a fresh Claude Code session knows what a long one knew
  (`ergostat/cli/bench_parity.py:1-3`, `docs/parity-bench.md`). That is a question about the factory's sessions, not
  about the work of someone who runs ergostat. Its single run is done and recorded
  (`docs/proposals/harness-parity-plan.md:313-326`: "F3 first run … none 0.03 · docs 0.33 …"). The data was private
  and kept outside the repository (`:318-319`). Only `cli/bench.py` loads it; `parity_draft` is named once in code
  (pass 4).
- **Net lines:** 290 + 98 + 95 + 7 in `cli/bench.py` ≈ 490 (counted as 487 in the table, the usage line kept).
- **Risk 2.** It is a documented command (`docs/parity-bench.md:43-53`, `docs/DECISIONS.md:123`, `:156`). Deleting it
  is the owner's call. It is self-contained, so nothing else breaks. It can come back with `git revert`.
- **Tests.** `tests/test_parity.py` (made-up data; goes with it). `contexts.py` stays covered through
  `tests/test_recipes.py`.

### 2. Stop reading `ergostat.toml`

- **How the sites were found.** `git grep -n "ergostat.toml" -- ergostat` (26 files on 277a9c6c), then
  `git grep -n -E "mdl\.FILE|tomllib|mdl\.parse|model\.parse|spec\.convert|from \.convert"` over the whole repository,
  then the callers of each function found. Every one of the 26 files is in one of the two tables below.
- **Evidence.** README.md:36: "An `ergostat.toml` from before still runs; `ergostat convert` writes it as
  `ergostat.yaml`". SPEC.md:6961 says the same. `model.py:518-519` calls YAML "the format" and TOML what came "before
  it". No folder in the repository holds an `ergostat.toml` (Glob `**/ergostat.toml`: none). A model only lacks
  `spec` when `model.parse` made it: the only other `Model(` in the repository is `spec/legacy.py:27`, which sets
  `m.spec` at `:81`.

**Removed** (each exists only for a model `model.parse` made):

| Where | What | Net lines |
|---|---|---:|
| `ergostat/model.py:402-511` | `COMMON` and `parse`, the TOML tables | 104 |
| `ergostat/model.py:383-399` | `_names`, `_take`: only `parse` calls them (`:427`, `:431`-`:509`; the `_names` of `numbers/extremes.py:106` and the `_take`s of `changeset.py`, `engine.py`, `itemindex.py`, `pool.py` are others) | 15 |
| `ergostat/model.py:614-708` | the body of `check` after the YAML model's return at `:610-613` | 92 |
| `ergostat/model.py:551-555`, `:11` | the TOML branch of `load_main` (it becomes a refusal of about 3 lines), `import tomllib` | 3 |
| `ergostat/spec/convert.py:1-223` | `convert`, `fix`, `schedule`, `human`. `Dumper`, `whole`, `spaced` (`:225-248`, 20 net) **move** to `spec/discover.py`, which imports them (`discover.py:96`) | 206 |
| `ergostat/cli/spec_cmds.py:142-168` | `cmd_convert`: the second caller of `mdl.parse` (`:149`) and of `mdl.FILE` (`:145-147`) | 27 |
| `ergostat/cli/__init__.py:39`, `:153-155`, the name at `:22` | the `convert` topic | 4 |
| `ergostat/blockdiagram.py:1486-1505` | `spec_of`'s converted spec for a model with none (the other importer of `convert`, `:1494`); `spec_of` keeps `:1483-1485` | 19 |
| `ergostat/reports/scrub.py:378-385` | the parts' names of "an ergostat.toml" | 8 |
| `ergostat/cli/running.py:133-136` | the `else` that starts `runner.Runner` for a TOML model; `:171`'s format comparison loses its `spec` half (0 net) | 4 |
| `ergostat/model.py:1`, `:600`, `ergostat/web/server.py:5` | docstrings and `file_name`'s fallback that say `ergostat.toml` (0 net) | 0 |
| | **Total** | **≈482** |

**Stays, and why** (the gap does not touch these):

| Where | Why it stays |
|---|---|
| `ergostat/model.py:17`, `:517-524`, `:531` (`FILE`, `find`) | `find` must still see an `ergostat.toml`, so a TOML folder is refused, never read as "no model" or passed over for an `ergostat.yaml` in a folder above it (lesson-3) |
| `ergostat/calls/client.py:65`, `:89`; `ergostat/cli/fast.py:18` | the same rule on the fast path: a TOML folder gets no socket call, so the command loads the model and is refused |
| `ergostat/cli/common.py:27-28`, `ergostat/cli/__init__.py:150` | item 3 removes them |
| `ergostat/supervisor.py:2`, `:16`, `:20`, `:88-90` | item 6 removes them |
| `ergostat/cli/common.py:38` | names the file that failed to load; `mdl.FILE` is its fallback |
| 21 guards on `spec is None`: `cli/claims.py:25`, `cli/gated.py:48`, `cli/intent.py:45`, `cli/leases.py:43`, `cli/messages.py:15`, `cli/numbers.py:24-25`, `cli/spec_cmds.py:176`, `intent/measures.py:76`, `mcp.py:212`, `:307`, `numbers/measures.py:155`, `:161`, `:183`, `:194`, `web/actions_api.py:25`, `web/control_api.py:42`, `web/messages_api.py:17`, `web/numbers_api.py:746`, `web/remote_api.py:116`, `reports/shape.py:50`, `web/static/pages.js:1046` | With TOML refused, none of them can be reached from a loaded model. But they are 21 of the 111 `getattr(…, "spec", None)` reads in 50 files of `ergostat/` (Grep `"spec", None\)`), the old model's second path. Cutting them is the old-model migration (§4), ≈50 net lines more (2 to 4 lines each, not counted one by one), and is not counted here. `pages.js:1046` also shows when the fit request fails (`d` null), so its words are wrong today; that is for the same gap |
| `ergostat/reports/trace.py:29` | `tomllib` there is a name in a list of the standard library's modules, not TOML support |

- **Net lines:** ≈482 (the first table).
- **Risk 3.** Anyone with a TOML project loses it. The way out is to convert with the last release that has `convert`,
  and the refusal must say which release. The tests are the larger change. The `repo` fixture writes a TOML model
  (`tests/conftest.py:157-171`, `:162`). 76 functions in 16 files of `tests/` take `repo` (Grep `def \w+\([^)]*\brepo\b`, the `project`
  fixture among them), and 59 test functions in 5 files take `project`
  (`conftest.py:174-178`), which loads it. Direct TOML: `tests/test_model.py` (15 mentions; `:9` calls `model.parse`),
  `tests/test_runner_and_state.py` (28), `tests/test_graph_cli_web.py` (9), `tests/test_cron.py:39`, `:42`,
  `tests/test_reload_in_place.py:241`, `:246`, `tests/test_spec_compile.py:183-192` (with the twelve files of
  `tests/fixtures/toml/`). `tests/test_spec_compile.py:172-180` (the YAML wins over a TOML beside it) still holds, since
  `find` keeps its order. Some tests assert words only the TOML `check` says (`tests/test_model.py:99`, `:108`, `:129`,
  `:164`; `tests/test_runner_and_state.py:589`); those findings go, or are pinned on the YAML model's own. Each change
  must be named. `scripts/demos.sh:13` and `scripts/demo_check.py:303` still list a TOML demo, so that it is refused
  and seen. `demo_check` must pass on every demo in `~/ergostat-demos/`.
- **Not part of this item:** `ergostat/runner.py`. The engine borrows its helpers (`spec/engine.py:39`, `:1090`,
  `:1808` uses `old.Runner._prune`; `spec/stream.py:20`; `daemons/supervise.py:18`). Once `cli/running.py:133-136` goes,
  `runner.Runner` (`runner.py:364-561`, 182 net) is started only by tests (`tests/test_runner_and_state.py:99`, `:494`,
  `tests/test_reload_in_place.py:241`) and `_prune`. That is for the old-model migration too.
- **Tests.** The files above.

### 3. `check --example`'s TOML starters and the empty-folder hint

- **Files and lines.** `ergostat/cli/common.py:91-132` (`EXAMPLE`), `:135-182` (`EXAMPLE_CRON`), `:27-31` (the hint
  printed when no model is found: `ergostat check --example cron > ergostat.toml`). `ergostat/cli/__init__.py:149-150`
  (`--example`). `ergostat/cli/status.py:13` (the import), `:218-219`.
- **Evidence.** A new user's first screen tells them to write the superseded format (`common.py:27-30`, with
  `mdl.FILE` = `ergostat.toml`, `model.py:17`). The YAML way to start is the guide shipped as `ergostat help
  agent-guide` (`ergostat/helpdocs.py:19`). **No test passes `--example`**: searching `tests/` for `--example` and
  `args.example` finds nothing. Its docs are history: `docs/cli-rounds.md:115-128`, `:511`, `:563`, `:581`, and
  `docs/REPORT-2026-11-14.md:27`.
- **Net lines** ≈ 71 (the two strings) + 4 (flag and branch), with the hint shortened ≈ 75.
- **Risk 2.** It is the first-run text. `tests/test_graph_cli_web.py:159` asserts that a first-run hint names
  `ergostat chat`.
- **Tests.** `tests/test_graph_cli_web.py` (the hint).

### 4. Ten dead names, and one only a test calls

Each is named nowhere else in the 1,398 tracked files (pass 2), except where noted.

| Name | Where | Net lines |
|---|---|---:|
| `commit_all` | `dev/bin/fac.py:191-197` | 7 |
| `key_raw` | `ergostat/numbers/memory.py:37-42` | 6 |
| `find_any` | `ergostat/numbers/review.py:412-416` | 5 |
| `_entry` | `ergostat/numbers/structural.py:663-665` | 3 |
| `traceback_of` | `ergostat/repair/capture.py:36-38` (named only in `dev/records/repair-traces.md:9`, `:56`, a record of its move to `traces.last`) | 3 |
| `expr_names` | `ergostat/spec/blocks.py:57-59` | 3 |
| `is_lease` | `ergostat/leases/fold.py:35-36` | 2 |
| `UnitError` | `ergostat/spec/equation.py:425-426` | 2 |
| `glob_ok` | `ergostat/spec/items.py:486-487` | 2 |
| `any_relations` | `ergostat/spec/relations.py:149-150` | 2 |
| `closed_stable` (tests only) | `ergostat/control/lti.py:246-247`; called only by `tests/test_control.py:99-100`, which can read `margins(p, c, n=600)["stable"]` (`lti.py:247`) itself | 2 |

- **Net lines:** 37. **Risk 1.**
- **Tests.** No test calls the first ten. The modules' own suites must still pass: `tests/test_gate.py` (memory,
  review), `tests/test_chains.py` (structural), `tests/test_repair_traces.py` (capture), `tests/test_numbers.py`
  (equation), `tests/test_relations.py` (relations, items), `tests/test_lease_refused_cost.py` (leases.fold),
  `tests/test_control.py` (lti), `tests/test_factory.py` (fac).

### 5. `avoidMove` and the router's single-part move

- **Files and lines.** `ergostat/web/static/avoid.js:775-793` (`avoidMove`), `:286-294` (`move` in the router core),
  `:328`, `:332-335`, `:337` (the worker's handling of the `move` messages only `avoidMove` sends, `:791`).
- **Evidence.** `avoidMove` is named once in the repository (pass 5). Every drag goes through `avoidMoveMany`
  (`ergostat/web/static/interact.js:159`, its only caller), which posts `moveMany` (`avoid.js:769`) and calls
  `core.moveMany` (`:765`, `:331`). Only `avoidMove` posts `type: "move"` (`:791`) or calls `core.move` (`:787`).
- **Net lines** ≈ 19 + 9 + 6 = 34. **Risk 1.**
- **Tests.** The drag tests in `tests/test_diagram_rendering.py`: `:556`
  `test_the_background_hides_the_side_panel_and_a_part_dragged_stays_pinned`, `:614`
  `test_an_open_system_dragged_by_its_outline_takes_its_parts_and_stays`, `:1714`
  `test_a_block_dragged_in_the_blocks_view_stays_pinned_its_lines_end_on_it_and_unpin_all_restores_it`, `:1801`, `:2011`.

### 6. `ergostat chat`'s brief

- **Files and lines.** `ergostat/supervisor.py:13-82` (`BRIEF`, 70 lines describing `[[stock]]`, `[[agent]]` and the
  other TOML tables), `:88-90` (it shows the current file as ```` ```toml ````).
- **Evidence.** The brief teaches the superseded format (`supervisor.py:16`, `:20`). For a YAML project it labels the
  `ergostat.yaml` that `mdl.find` returns as TOML (`:87-90`). The guide for an agent setting up a model is
  `docs/AGENT-GUIDE.md`, which ergostat already ships as `ergostat help agent-guide` (`ergostat/helpdocs.py:19`; the
  first lines of `CLAUDE.md` point there too).
- **The choice taken here, the more reversible one:** keep `ergostat chat` and the Supervisor (a NOTES.md term), and
  brief from `helpdocs` instead of `BRIEF`. That is ≈62 net lines. Deleting the command (`supervisor.py`,
  `ergostat/cli/running.py:340-343`, `ergostat/cli/__init__.py:352-355`, the hints at `cli/common.py:29` and
  `cli/status.py:139`) would remove ≈84; that is the owner's call.
- **Risk 2.**
- **Tests.** `tests/test_graph_cli_web.py:379` (runs `chat`), `:159`.

### 7. One helper for item records

- **Files and lines.** `ergostat/actions/record.py:21-65` (`item_of`, `short`, `step`, `fold`, `get`, `stored`),
  `ergostat/messages/record.py:27-32`, `:58-94`, and `ergostat/reports/record.py:33-38`, `:213-234`.
- **Evidence.** The same six functions, with only the kind's prefix changed. `item_of`
  (`actions/record.py:21-22` = `messages/record.py:27-28` = `reports/record.py:33-34`) and `short` (`:25-26` =
  `:31-32` = `:37-38`) match. So do `step` (`actions:33-34` = `messages:58-60`), `fold` (`actions:37-42`,
  `messages:63-68`, `reports:213-217`: `its.fold` and the same dict, plus one field each) and `get` with its short-id
  prefix lookup (`actions:45-52`, `messages:87-94`, `reports:220-227`).
- **Net lines** ≈ 88 now, less a shared helper of about 30 and about 4 lines kept per kind ≈ 45.
- **Risk 2.** The copies differ in small ways the helper must keep. `messages.stored` reads an item whole when its
  start fell outside the window (`messages/record.py:79-80`). `messages.get` matches the raw id
  (`:90`), not `short(id)` (`actions:48`, `reports:223`). `actions.fold` lists `ignored` (`actions:40`). The claim
  and verdict records fold by hand (`claims/record.py:115-127`, `intent/record.py:67-92`). They do something different
  and are left alone.
- **Tests.** `tests/test_gated_actions.py`, `tests/test_program_actions.py`, `tests/test_messages.py`,
  `tests/test_reports.py`, `tests/test_inbox.py`.

### 8. One flock helper each in `ergostat/` and `dev/bin/`

- **Files and lines.** In `ergostat/`: `numbers/proposals.py:94-104`, `remote/cache.py:50-59`,
  `workspaces/pool.py:101-108`, and the non-blocking ones `numbers/extremes_cache.py:82-93` and
  `numbers/archreview.py:45-57`. In `dev/bin/`: `pools.py:65-72`, `drain.py:84-87`, `agents.py:112-118`,
  `fac.py:350-358`, `simplify.py:150-173`, `watch.py:295-304`, `parks.py:109-110`.
- **Evidence.** Each opens `<dir>/<name>.lock` and runs `fcntl.flock(f, LOCK_EX)` (or `| LOCK_NB`, yielding whether the
  lock was taken), then unlocks in `finally` (pass 6; Grep of `fcntl.flock(`: 46 uses in 25 files).
- **Left as they are.** `repair/apply.py:64-73` (it checks the name before building the path: lesson-11),
  `dev/bin/resources.py:192-204` (shared or exclusive), `dev/bin/manage.py:83-85`, `:272-273` (held across an exec).
- **Net lines** ≈ 20 + 15 = 35.
- **Risk 2.** If a lock file's name, folder or mode changes, two writers stop excluding each other (lesson-1). The
  helper must keep every path byte-for-byte.
- **Tests.** `tests/test_gate.py`, `tests/test_churn_carry.py` (proposals), `tests/test_workspaces.py`,
  `tests/test_extremes_closed.py`, `tests/test_architecture_review.py`, `tests/test_factory.py` (dev/bin).

### 9. The old name `variables:`

- **Files and lines.** `ergostat/spec/compile.py:142-157` (`deprecated`, `renamed`), `:76` (`GOAL_KEYS`' `variable`),
  `:355`, `:994-1002`, `:1016`, `:1022-1024`, `:1027`, `:1143` (the call of `renamed`), `:1248`. Also
  `ergostat/spec/load.py:19`, `:21`, `ergostat/spec/ir.py:19`, `:34` (`OLD_KIND`), `ergostat/library/trust.py:137`,
  `:194`, `ergostat/library/expand.py:52`, `:54`, `ergostat/remote/compose.py:37`, `:430`, `ergostat/remote/serve.py:27`,
  `:98`, `ergostat/state.py:264` (`variable.set` in old records), `ergostat/numbers/requests.py:42`.
- **Evidence.** SPEC.md:523 and SPEC.md:3510 ("**deprecated name**: `variables:`, `variable.x` or a goal's
  `variable:`, still read; rename to …").
- **Net lines** ≈ 35. **Risk 3.** It breaks a promise in SPEC. A file still using the old names stops compiling, so
  the error must say what to rename. Records written before the rename still hold `variable.set`, so the gap must decide
  whether `state.py:264` keeps reading it (keeping it is the more reversible choice).
- **Tests.** `tests/test_spec_auxiliaries.py:132-138` (it asserts the deprecation finding; it becomes a test of the
  refusal).

### 10. One percentage and one "ago" formatter for the CLI

- **Files and lines.** `ergostat/cli/claims.py:12-13`, `ergostat/cli/context_cmd.py:13-14`, `ergostat/cli/intent.py:29-30`,
  `ergostat/cli/numbers.py:30-31` (four `_pct`/`pct`). `ergostat/cli/remote.py:61-62` and
  `ergostat/remote/compose.py:334-339` (two `_ago`, beside `ergostat/show.py:20-23` `ago`).
- **Evidence.** The same job written four times, with differences that look accidental: `""` or `"–"` for none, and
  `round(x*100)`, `:.0%` or `:.0f`.
- **Net lines** ≈ 10. **Risk 1.** The output text changes where the copies differed, so the gap must state each change.
- **Tests.** `tests/test_claims.py`, `tests/test_intent.py`, `tests/test_numbers.py`, `tests/test_remote*.py`.

### 11. Re-signing old Node/Java/Go failures

- **Files and lines.** `ergostat/repair/capture.py:17` (`OTHER`), `:138-143`.
- **Evidence.** SPEC.md:6476-6483 ("**Superseding.** Node, Java and Go failures were signed by how they ended before
  triage read their traces, so their old items have other ids…"). It is a migration for records written before that
  change. A new install has none.
- **Net lines** ≈ 7. The `superseded` state stays in `ergostat/repair/__init__.py:8-12`, so old records still fold.
- **Risk 2.** An owner with old open Node/Java/Go failures would see two items for one bug.
- **Tests.** `tests/test_repair_traces.py:523`, `:533`, `:553`, `:571`, `:583` (they go with it).

## 4. Looked at and not found removable

- **Whole modules.** None is unreferenced (pass 4). The modules named only once in code (`context_cmd`,
  `impact_cmd`, `intent_api`, `parity_draft`, `push_api`, `relations_api`, `trips`, `warmcheck`, `yaml12`) each have
  exactly one importer. That is their caller, not dead code.
- **Private names.** Every top-level `_name` in `ergostat/` and `dev/bin/` is mentioned at least twice in the
  repository, except `_entry` (item 4).
- **Names mentioned exactly twice** (about 180 of them, e.g. `ar_fit`, `binned`, `OnOff`): pass 3 showed the second
  mention is code in every case.
- **The old model and its runner.** `ergostat/model.py`, `ergostat/spec/legacy.py` and `ergostat/runner.py`:
  `legacy.py:1-2` says the YAML model is turned into the old objects "so a YAML project is shown like any other while
  those move to the new model". `model as mdl` is imported by 25 modules of `ergostat/` (among them `cli/common.py:10`,
  `web/server.py:22` and `mcp.py:16`), and the engine borrows the old runner's helpers (`spec/engine.py:39`, `:1808`
  `old.Runner._prune`). Once item 2 lands, two parts of it are reachable only from tests: the 21 `spec is None`
  guards listed in item 2 (with 90 more `getattr(…, "spec", None)` reads, 111 in 50 files) and `runner.Runner`'s
  scheduling (`runner.py:364-561`, 182 net). They are not counted in the total. That is a migration of its own (which
  of `model.py`'s objects the page and the CLI still read), and it needs a survey first, not a cut.
- **Warm workers.** GAPS.md:369-376 calls them superseded by daemons, but the `warm` branch never landed; `warm: true`
  daemons are current (`ergostat/daemons/config.py`). Nothing on main to remove.
- **The improvement benchmark** (`ergostat bench improve | judge | meta`, `ergostat/bench/__init__.py:1-6`,
  `cli/bench.py:1-4`). It is how the improver is verified (SPEC §12f). Kept.
- **`ergostat/session_echo.py`.** The free stand-in for a Claude Code session (`ERGOSTAT_CLAUDE=echo`), documented
  (SPEC.md:5407, docs/MESSAGES.md:112) and used by `tests/test_messages.py`, `tests/test_run_costs.py`,
  `tests/test_workspaces.py`.
- **Flags.** `ERGOSTAT_STALL` and `ERGOSTAT_STARTUP` (`ergostat/spec/watchdog.py:45`, `:52`) are set nowhere in
  code or tests, but they are documented tuning knobs (SPEC.md:2478, `:2494`), not feature flags. `ERGOSTAT_IMPACT_SECONDS`
  (`ergostat/repair/fix.py:181-182`) is set only by tests (`tests/test_repair2.py:87`, `tests/test_repair_verify.py:35`):
  a 2-line test seam. `FACTORY_STANDIN_*` (`dev/bin/fac.py:677-706`) are the factory's stand-ins, set by its tests.
  The other names read in `ergostat/` (Grep `environ(?:\.get)?[\[(]\s*f?"([A-Z_]+)`: 34 distinct names on 277a9c6c, most of them
  `ERGOSTAT_RUN`, `_BLOCK`, `_ITEM`, `_SOCKET` and the like, which the engine sets for its runs) were read in the
  first draft and none looked like a flag left unset. That was a reading, not a check: a name was not traced to its
  setter one by one, so this map claims no more than that none of them is a found candidate.
- **Same-named functions that are not duplicates:** `_said` (10 modules), `_when` (6), `table` (9), `settle`, `sweep`,
  `stamp`, `listing`. Read side by side, each does something different.
- **`ergostat/spec/convert.py:35` `human`** next to `ergostat/durations.py:25` `human`. The first writes exact YAML
  durations (`90m`), the second rounds for a table. Not a duplicate. (It goes with item 2 in any case.)
- **Test seams and re-exports.** `ergostat/runlog.py:46-47` `_created` (tests monkeypatch it). The `# noqa: F401`
  re-exports at `bench/adapter.py:21`, `numbers/closedloop.py:42`, `numbers/impact.py:23`, `numbers/simulate.py:37`,
  `recipes/ir.py:10` and `web/numbers_api.py:22` are import paths other modules use, a few lines in all.
- **`dev/bin/`** is the factory's own code. Apart from `commit_all` (item 4) and the inline locks (item 8), no
  function in it is dead, and every script runs from `dev/model/*.yaml` or `dev/factory.toml`.
- **Not looked at:** methods and nested functions, CSS, the YAML templates in `ergostat/library/templates/`, and
  `scripts/` (outside this map's scope).

## 5. The first ten, as gap definitions

Each is ready to be committed as `dev/records/<name>.md`. The size budgets are negative: the branch must remove at
least that many net lines outside `tests/`, `docs/` and `dev/` (for `dev/bin/` gaps, inside `dev/bin/`).

---

### code-cut-parity-bench: delete `ergostat bench parity`

depends-on: []

**Definition of done**
1. `ergostat/bench/parity.py`, `ergostat/bench/parity_draft.py` and `ergostat/cli/bench_parity.py` are gone. So are
   `cli/bench.py:35`, `:43-45`, `:81-83`, the word `parity` at `:84`, and the parity words in `cli/__init__.py:88`. `ergostat/bench/contexts.py` stays
   (`recipes/talk.py:17`).
2. `ergostat bench parity` exits 2 as an unknown topic. `ergostat bench improve | judge | meta` work as before.
3. `docs/parity-bench.md` is removed. `docs/DECISIONS.md:123`, `:156` and `docs/proposals/harness-parity-plan.md` say
   that it was removed and when, and SPEC and GAPS are current.

**Files:** the three modules, `ergostat/cli/bench.py`, `ergostat/cli/__init__.py`, `tests/test_parity.py`, `tests/test_bench.py`, the docs named.
**Risks:** lesson-8 (no doc may still describe the command; `git grep -n "bench parity"` empty outside history files); lesson-7 (merge main and run the suites again).
**Acceptance tests:** `tests/test_bench.py::test_bench_has_no_parity_topic` (new); `tests/test_recipes.py` and `tests/test_bench.py` pass.
**Size budget:** −470 net lines or more.

---

### code-cut-toml-format: stop reading `ergostat.toml`

depends-on: [code-cut-toml-starters, code-cut-chat-brief]

**Definition of done**
1. Every site in item 2's "Removed" table is gone: `model.py:383-399`, `:402-511`, `:614-708`, `:551-555` and `:11`;
   `spec/convert.py:1-223`; `cli/spec_cmds.py:142-168`; `cli/__init__.py:39`, `:153-155` and `cmd_convert` at `:22`;
   `blockdiagram.py:1486-1505`; `reports/scrub.py:378-385`; `cli/running.py:133-136`, with `:171` comparing no
   format. The docstrings at `model.py:1` and `web/server.py:5`, and `file_name`'s fallback (`model.py:600`), stop
   saying `ergostat.toml`. `Dumper`, `whole` and `spaced` move unchanged to `spec/discover.py`, which imports them, and
   `spec/convert.py` is deleted.
2. `load_main` refuses an `ergostat.toml` (`ModelError`, exit 2 from the CLI), naming the last release that converts
   it. `find` (`model.py:517-524`), `calls/client.py:65`, `:89` and `cli/fast.py:18` still see the file, so a TOML
   folder below a YAML project is refused, not read as its parent's model.
3. Item 2's "Stays" table is not touched; the 21 guards and `runner.Runner` are left for the old-model migration.
4. The `repo` fixture (`tests/conftest.py:157-171`) writes YAML (the one `ergostat convert` writes for `DISK` today,
   made before `convert` is deleted), and every test in item 2's Risk list builds YAML. A test that asserted a message
   only the TOML `check` gives (`tests/test_model.py:99`, `:108`, `:129`, `:164`; `tests/test_runner_and_state.py:589`)
   is removed or pinned to the YAML model's finding, each one named in the definition's notes.
   `tests/test_spec_compile.py:183-192` and `tests/fixtures/toml/` are removed. `demo_check` passes on every demo.
5. `git grep -l "ergostat.toml" -- ergostat` lists exactly 20 files: `model.py`, `calls/client.py`, `cli/fast.py`, and
   the 17 that hold the 21 guards (`cli/claims.py`, `cli/gated.py`, `cli/intent.py`, `cli/leases.py`,
   `cli/messages.py`, `cli/numbers.py`, `cli/spec_cmds.py`, `intent/measures.py`, `mcp.py`, `numbers/measures.py`,
   `reports/shape.py`, `web/actions_api.py`, `web/control_api.py`, `web/messages_api.py`, `web/numbers_api.py`,
   `web/remote_api.py`, `web/static/pages.js`). The other six of today's 26 drop out: `cli/__init__.py`, `cli/common.py`
   and `supervisor.py` (with the two gaps this one waits on), `spec/convert.py`, `reports/scrub.py`, `web/server.py`.
6. README.md:36, `:132`, SPEC.md:3352, `:6961`, docs/AGENT-GUIDE.md:517, docs/DESIGN.md:13 and docs/GAPS.md:351 are
   current.

**Files:** `ergostat/model.py`, `ergostat/spec/convert.py` (deleted), `ergostat/spec/discover.py`, `ergostat/cli/spec_cmds.py`, `ergostat/cli/__init__.py`, `ergostat/cli/running.py`, `ergostat/blockdiagram.py`, `ergostat/reports/scrub.py`, `ergostat/web/server.py` (its docstring); `tests/conftest.py`, `tests/test_model.py`, `tests/test_runner_and_state.py`, `tests/test_graph_cli_web.py`, `tests/test_cron.py`, `tests/test_reload_in_place.py`, `tests/test_spec_compile.py`, `tests/fixtures/toml/`, and any other file of item 2's `repo`/`project` counts whose assertions change; README.md, docs/SPEC.md, docs/AGENT-GUIDE.md, docs/DESIGN.md, docs/GAPS.md. These are exactly the files of DoD 1, 2, 4 and 6; the files of DoD 5's list are not edited.
**Risks:** lesson-3 (a TOML file must be refused, never read as "no model" or as a parent folder's model); lesson-8 (DoD 5 is a test, not a reading); lesson-13 (`runner.py` and the guards are not part of this gap). If the move of the tests is too large for one review, it goes first in a branch of its own (tests only: `repo` writes YAML), and this gap waits on it.
**Acceptance tests:** `tests/test_model.py::test_an_ergostat_toml_alone_is_refused_naming_the_release_that_converts_it`, `::test_an_ergostat_toml_below_a_yaml_project_is_refused_not_read_as_the_parent`, `::test_ergostat_toml_is_named_only_by_the_refusal_find_and_the_listed_guards` (runs DoD 5's `git grep -l` and compares it with the 20 files) (all new); `tests/test_runner_and_state.py`, `tests/test_graph_cli_web.py`, `tests/test_cron.py`, `tests/test_reload_in_place.py`, `tests/test_spec_compile.py`, `tests/test_blockdiagram.py`, `tests/test_spec_discover.py` (it covers the moved YAML writer) pass; `scripts/demo_check.py` passes.
**Size budget:** −450 net lines or more (item 2 counts ≈482).

---

### code-cut-toml-starters: no TOML on the first screen

depends-on: []

**Definition of done**
1. `EXAMPLE` and `EXAMPLE_CRON` (`ergostat/cli/common.py:91-182`) and `check --example` (`cli/__init__.py:149-150`,
   `cli/status.py:218-219`) are gone.
2. The hint for a folder with no model (`cli/common.py:27-31`) names `ergostat help agent-guide` and `ergostat chat`,
   and no file format to write by hand.

**Files:** `ergostat/cli/common.py`, `ergostat/cli/__init__.py`, `ergostat/cli/status.py`, `tests/test_graph_cli_web.py`, `docs/QUICKSTART.md` if it names `--example`.
**Risks:** lesson-8 (no doc may still offer `check --example`, `git grep -n -- "--example"`).
**Acceptance tests:** `tests/test_graph_cli_web.py::test_an_empty_folder_points_to_the_agent_guide_not_a_toml_file` (new); `ergostat check --example` exits 2 (in the same test).
**Size budget:** −65 net lines or more.

---

### code-cut-dead-names: delete what nothing calls

depends-on: []

**Definition of done**
1. The ten names in the table of item 4 are deleted: `commit_all`, `key_raw`, `find_any`, `_entry`,
   `traceback_of`, `expr_names`, `is_lease`, `UnitError`, `glob_ok`, `any_relations`.
2. `closed_stable` (`ergostat/control/lti.py:246-247`) is deleted. `tests/test_control.py:99-100` reads
   `lti.margins(p, c, n=600)["stable"]`.
3. Before deleting, each name is searched again with `git grep -n -w NAME` over the whole repository, and the result is
   written in the definition's notes.

**Files:** `dev/bin/fac.py`, `ergostat/numbers/memory.py`, `ergostat/numbers/review.py`, `ergostat/numbers/structural.py`, `ergostat/repair/capture.py`, `ergostat/spec/blocks.py`, `ergostat/leases/fold.py`, `ergostat/spec/equation.py`, `ergostat/spec/items.py`, `ergostat/spec/relations.py`, `ergostat/control/lti.py`, `tests/test_control.py`.
**Risks:** lesson-8 (a name built at run time: the search includes YAML, TOML and Markdown); lesson-9 (show that `code_evidence.py`'s `dead_candidates` falls).
**Acceptance tests:** `uv run python scripts/code_evidence.py --coverage FILE` on the branch lists none of the eleven names as `dead_candidates`; `tests/test_control.py`, `tests/test_gate.py`, `tests/test_chains.py`, `tests/test_repair_traces.py`, `tests/test_relations.py`, `tests/test_lease_refused_cost.py`, `tests/test_numbers.py` pass.
**Size budget:** −35 net lines or more.

---

### code-cut-avoid-move: one way to move parts on the page

depends-on: []

**Definition of done**
1. `avoidMove` (`ergostat/web/static/avoid.js:773-793`), the core's `move` (`:286-294`) and the worker's `move`
   messages (`:328`, `:332-335`, `:337`) are gone. Every move goes through `avoidMoveMany`.
2. A part dragged and an open system dragged still route their lines while moving and when dropped.

**Files:** `ergostat/web/static/avoid.js`.
**Risks:** lesson-10 (browser tests under load: rerun any failure before blaming the branch); lesson-9 (break `avoidMoveMany` and watch a drag test fail).
**Acceptance tests:** in `tests/test_diagram_rendering.py`, under the watchdog with Playwright and no page test skipped: `test_the_background_hides_the_side_panel_and_a_part_dragged_stays_pinned`, `test_an_open_system_dragged_by_its_outline_takes_its_parts_and_stays`, `test_a_block_dragged_in_the_blocks_view_stays_pinned_its_lines_end_on_it_and_unpin_all_restores_it`, `test_a_loop_marker_moves_with_its_system_when_the_system_is_dragged`.
**Size budget:** −30 net lines or more.

---

### code-cut-chat-brief: the Supervisor briefed from the agent guide

depends-on: []

**Definition of done**
1. `BRIEF` (`ergostat/supervisor.py:13-82`) is gone. `ergostat chat` briefs from `helpdocs` `agent-guide`
   (`ergostat/helpdocs.py:19`) and `NOTES.md`, as now.
2. The current model is shown as its own file, labelled with that file's name and format, never as TOML
   (`supervisor.py:88-90`).
3. `ergostat chat --print-prompt` prints the new brief.

**Files:** `ergostat/supervisor.py`, `tests/test_graph_cli_web.py`.
**Risks:** lesson-3 (if the guide cannot be read, chat refuses, never starts unbriefed); lesson-8.
**Acceptance tests:** `tests/test_graph_cli_web.py::test_chat_briefs_from_the_agent_guide_and_shows_the_yaml` (new); the existing chat test at `tests/test_graph_cli_web.py:379` passes.
**Size budget:** −55 net lines or more.

---

### code-merge-item-records: one helper for actions, messages and reports

depends-on: []

**Definition of done**
1. One module (in `ergostat/spec/`, beside `items.py`) gives `item_of`, `short`, `step`, `fold`, `get` and `stored`
   for a kind by its prefix and fold.
2. `ergostat/actions/record.py`, `ergostat/messages/record.py` and `ergostat/reports/record.py` use it. Their
   differences stay as options: messages' whole-item read (`messages/record.py:79-80`), messages' raw-id prefix
   (`:90`), actions' `ignored` (`actions/record.py:40`).
3. The claim and verdict records (`claims/record.py:115-127`, `intent/record.py:67-92`) are not touched.

**Files:** the three `record.py`, the new module, their tests.
**Risks:** lesson-5 (an id made again: the fold keeps nothing old); lesson-9 (for each kept difference, a test that fails without it).
**Acceptance tests:** `tests/test_item_records.py::test_a_message_whose_start_fell_outside_the_window_is_read_whole`, `::test_a_short_prefix_finds_one_action_report_and_message` (new); `tests/test_gated_actions.py`, `tests/test_program_actions.py`, `tests/test_messages.py`, `tests/test_reports.py`, `tests/test_inbox.py` pass.
**Size budget:** −40 net lines or more.

---

### code-merge-file-locks: one flock helper each side

depends-on: []

**Definition of done**
1. `ergostat/storage.py` gains `flocked(path, wait=True)`, a context manager that yields whether the lock was taken.
   It replaces the bodies at `numbers/proposals.py:94-104`, `remote/cache.py:50-59`, `workspaces/pool.py:101-108`,
   `numbers/extremes_cache.py:82-93` and `numbers/archreview.py:45-57`.
2. `dev/bin/fac.py` gains `locked(cfg, name)`, used at `pools.py:65-72`, `drain.py:84-87`, `agents.py:112-118`,
   `fac.py:350-358`, `simplify.py:150-173`, `watch.py:295-304` and `parks.py:109-110`.
3. Every lock file keeps its path and name. `repair/apply.py:64-73`, `resources.py:192-204` and `manage.py:83-85`,
   `:272-273` are left as they are.

**Files:** the modules named.
**Risks:** lesson-1 (a renamed lock file means no exclusion: a test holds the old path and shows that the new code waits); lesson-6 (a non-blocking lock still yields False and never waits).
**Acceptance tests:** `tests/test_file_locks.py::test_each_lock_keeps_its_file`, `::test_a_held_lock_is_not_taken_without_waiting` (new); `tests/test_gate.py`, `tests/test_churn_carry.py`, `tests/test_workspaces.py`, `tests/test_extremes_closed.py`, `tests/test_architecture_review.py`, `tests/test_factory.py` pass.
**Size budget:** −30 net lines or more.

---

### code-cut-old-variable-names: `variables:` no longer read

depends-on: []

**Definition of done**
1. `variables:`, `variable.NAME` and a goal's `variable:` are refused at compile time, each with an error that says
   what to rename. `deprecated`/`renamed` (`ergostat/spec/compile.py:142-157`) are gone, and so are the other
   readings listed in item 9.
2. Old records' `variable.set` events are still read (`ergostat/state.py:264`), because a record is never rewritten.
3. SPEC.md:523 and SPEC.md:3510 say the old names are refused, and since when.

**Files:** the files of item 9, `tests/test_spec_auxiliaries.py`, SPEC.
**Risks:** lesson-3 (an old name must fail closed, never be ignored silently); lesson-8.
**Acceptance tests:** `tests/test_spec_auxiliaries.py::test_the_old_name_variables_is_refused_saying_what_to_rename` (replacing the deprecation test at `:132-138`); `tests/test_spec_compile.py`, `tests/test_templates.py`, `tests/test_remote*.py` pass.
**Size budget:** −30 net lines or more.

---

### code-merge-cli-formats: one `pct` and one `ago`

depends-on: []

**Definition of done**
1. `ergostat/show.py` has `pct(x, none="–")` beside `ago`. The four copies (`cli/claims.py:12-13`,
   `cli/context_cmd.py:13-14`, `cli/intent.py:29-30`, `cli/numbers.py:30-31`) and the two `_ago`s
   (`cli/remote.py:61-62`, `remote/compose.py:334-339`) use them.
2. Each changed output is listed in the definition. Where the copies differed, one form is chosen and said.

**Files:** the modules named, `ergostat/show.py`.
**Risks:** lesson-8 (a test that greps CLI text may change: name each one).
**Acceptance tests:** `tests/test_show.py::test_pct_and_ago_for_none_and_numbers` (new); `tests/test_claims.py`, `tests/test_intent.py`, `tests/test_numbers.py` pass.
**Size budget:** −8 net lines or more.

---

Item 11 (the Node/Java/Go re-signing migration) is not written as a gap. It is worth about 7 lines, and the owner
should first say whether old records of that kind still matter.
