# Slicing ergostat's code for complexity measures

Measured at main `2468c59b` (2026-11-22 03:52, 594 first-parent commits, 2,739 in all, first commit 2026-11-14).
Everything was read from git with the standard library. The scripts are in `design/work/cx/` (`sizes.py`, `slices.py`,
`blame.py`, `ncd.py`), with raw output in `sizes.json`, `slices.txt`, `slices_hist.txt` and `blame.txt`.

**Line counting.** "Lines" means net lines, the same as `scripts/code_evidence.py`: lines that are neither blank nor
only a comment. Docstrings count. In `ergostat/`, `dev/bin/` and `scripts/` the Python breaks down as 74,977 code
lines, 9,509 docstring lines, 438 comment-only lines and 11,345 blank lines. That gives 84.5k net lines, which is
the owner's "81,000" measured a few days later. The token-class slice below keeps code and docstrings apart.

## 0. The rule that keeps this from becoming hundreds of stocks

There are about 9 slicings × about 12 measure families × up to 400 members. That is tens of thousands of possible
series. Each slice goes into one of three tiers:

| Tier | What it is in the model | Used for |
|---|---|---|
| **A: stock or auxiliary** | One scalar part with a `run:` sensor, in a new system `complexity` (within `code-health`). Its parts are named `complexity-<measure>[-<slice member>]`, with the measure first, so the parts of one family sort together. | Measures you want as a time series, fitted, drawn, held by goals and backfilled. At most about 40 parts. |
| **B: item fields (the "labels")** | A `module/<path>` item kind. The measuring sensor prints observation lines (SPEC §6: `{"event": "module.measured", "item": "module/ergostat/spec/engine.py", "data": {...}}`). Each module item carries every measure plus its slice keys (`area`, `package`, `layer`, `lang`, `system`, `added`, ...). Threshold states such as `oversize` or `dead-candidate` are counted by tier-A stocks with `goal per: package` or `per: layer` (SPEC §8). | Anything with more than about 8 members, or a classification that may change. Shown in the Items tab, so no new UI is needed. |
| **C: on demand** | `dev/bin/complexity.py slice --by S --measure M [--at SHA]` prints a table. Nothing is recorded. | Cross-products (layer × measure × age), conditional compression, function-level detail, blame ages, pairwise coupling. |

ergostat has no labelled series: a sensor reads one number. The way to say "one series with labels" in ergostat is
to put the labels on items (tier B) and use a stock to count or aggregate them. **To keep the record small**, a
module is observed only when its blob changed on main. At about 10 merges a day touching about 5 files each, that is
roughly 50 events a day. The whole first-parent history has about 6,500 distinct tree and blob objects under the code
paths, so a backfill writes a few thousand events, not 594 × 420.

**Stock or auxiliary.** Size-like measures accumulate through merges and only a change drains them, so they are
**stocks**: lines, compressed bytes, functions, duplicate bodies and dead candidates. Each can get inflow and outflow
flows measured by `changes: rises` and `changes: falls` (SPEC §6), at the code scope only. Ratios, medians and shares
are **auxiliaries**: compression ratio, median function length, test-to-code ratio and coverage. The existing
`code-net-lines`, `code-long-functions`, `code-duplicates`, `code-dead-candidates` and `code-coverage` auxiliaries in
`dev/model/code-health.yaml` are already the code-scope readings of their families. Keep them as they are, with their
goals, and do not measure them again under a `complexity-` name. One question is open: whether they should become
stocks. That would change `code-health`'s goals' parts, so it needs a decision.

**Scope.** "Code" here means `ergostat/` own code, `dev/bin/` and `scripts/`. **Vendored files are excluded from
every measure**: `elk.bundled.js` (1.6 MB), `highlight.min.js`, `libavoid.js` and `libavoid.wasm`,
`uPlot.iife.min.js` and `marked.min.js`. Together they are 7,877 net lines and 2.2 MB, against 4.3 MB for all of
`ergostat/`'s Python. Left in, they would dominate any compression measure, and a naive line counter reads the wasm
as about 27k lines. The exclusion list is written down once, in one place, and it is itself an item field
(`vendored: true`). Vendored files are not dropped silently.

## 1. By top-level area

| Area | Files | Net lines (all text) | Of which Python | xz bytes (Python, one stream) |
|---|---|---|---|---|
| `ergostat/` product | 432 | ~86.4k own: Py 71,309, JS 10,805, CSS 936, YAML 2,626, MD 665 (+7,877 vendored) | 71,309 | 941,180 (of 4.26 MB) |
| `tests/` | 242 | 66,268 | 63,116 | 729,404 |
| `docs/` | 345 | 49,515: SPEC.md 6,222; roadmap 20,480; proposals 13,060 (non-blank) | none | n/a |
| `dev/` factory | 107 | 16,642: bin 8,335; records 4,520; model YAML 2,142; README 753; prompts 427 | 8,428 | 138,392 |
| `examples/` | 276 | 15,562: Py 7,780; YAML 5,696 | 7,780 | n/a |
| `scripts/` | 24 | 4,458 | 4,326 | 66,904 |
| `schema/` + root | 12 | 3,715 | none | n/a |

**Tier A.** Two stocks per area: `complexity-lines-<area>` and `complexity-xz-<area>`, for `product`, `factory`,
`tests` and `scripts`. Add `complexity-lines-docs` and `complexity-lines-examples` (prose and models; xz is not
useful for them). That is **10 stocks**. Areas are few, stable and unambiguous, so they backfill cleanly. For
`factory`, split code (`dev/bin`) from its model: add `complexity-factory-model-parts`, the parts defined in
`dev/model/*.yaml`, about 406 today. That is a model-size measure, which is the factory's own kind of complexity.

## 2. By package and module under `ergostat/`

Own code (Py, JS, CSS and HTML; JS counts only for `web/`), in net lines. "xz alone" is the package's Python
compressed by itself. "Shared" is the fraction that compresses away when the package is compressed after the rest of
`ergostat/`, which is a cheap stand-in for conditional Kolmogorov complexity K(pkg | rest). Commits counts commits
touching the package over all history; this is 8 days old, so 30 days means all of it.

| Package | Files | Net lines | xz alone | xz ratio | Shared with the rest | Commits (7d) |
|---|---|---|---|---|---|---|
| `web/` | 50 | 22,249: py 2,580, own JS 10,805, CSS 936; vendored 7,877 | 40,376 (py) | 0.257 | 0.22 | 231 |
| `numbers/` | 56 | 14,794 | 220,432 | 0.239 | 0.11 | 160 |
| `spec/` | 42 | 13,890 | 194,816 | 0.232 | 0.13 | 253 |
| top-level modules (44) | 44 | 12,674 | 177,836 | 0.237 | 0.13 | 183 |
| `cli/` | 24 | 4,389 | 62,124 | 0.245 | 0.19 | 107 |
| `library/` | 20 | 3,036 | 48,252 | 0.272 | 0.19 | 78 |
| `control/` | 10 | 2,729 | 44,156 | 0.279 | 0.16 | 22 |
| `bench/` | 13 | 1,979 | 30,428 | 0.277 | 0.22 | 9 |
| `remote/` | 15 | 1,894 | 28,892 | 0.273 | 0.22 | 20 |
| `repair/` | 8 | 1,467 | 24,844 | 0.275 | 0.19 | 20 |
| `daemons/` | 8 | 1,209 | 19,812 | 0.278 | 0.22 | 28 |
| `leases/` | 10 | 1,183 | 20,292 | 0.270 | 0.26 | 57 |
| `recipes/` | 9 | 1,111 | 16,832 | 0.281 | 0.28 | 3 |
| `decisions/` | 9 | 1,099 | 17,860 | 0.287 | 0.27 | 9 |
| `actions/` | 9 | 964 | 16,464 | 0.288 | 0.30 | 10 |
| `reports/` | 9 | 892 | 15,212 | 0.307 | 0.26 | 1 |
| `inbox/` | 7 | 877 | 16,392 | 0.292 | 0.27 | 18 |
| `costs/` | 6 | 867 | 14,912 | 0.295 | 0.25 | 12 |
| `intent/` | 8 | 736 | 13,560 | 0.297 | 0.32 | 3 |
| `messages/` | 6 | 685 | 11,992 | 0.287 | 0.31 | 8 |
| `sandbox/` | 5 | 595 | 10,200 | 0.324 | 0.23 | 2 |
| `claims/` | 4 | 481 | 9,160 | 0.314 | 0.34 | 3 |
| `calls/` | 4 | 436 | 6,804 | 0.307 | 0.35 | 16 |
| `workspaces/` | 5 | 411 | 7,548 | 0.298 | 0.33 | 4 |
| `intake/` | 5 | 331 | 5,784 | 0.337 | 0.33 | 5 |
| `help/`, `skills/` | 3 | (markdown only) | | | | 16 / 7 |

The biggest modules, in net lines: `spec/engine.py` 2,347; `spec/compile.py` 1,652; `blockdiagram.py` 1,374;
`spec/ir.py` 1,067; `web/server.py` 963; `store.py` 956; `numbers/proposals.py` 953; `segments.py` 919;
`spec/itemindex.py` 876; `numbers/improve.py` 782; `numbers/structural.py` 768; `web/numbers_api.py` 716;
`numbers/judge.py` 699; `spec/chains.py` 681. In JS: `diagram.js` 1,409; `pages.js` 1,171; `blocks.js` 1,126;
`dynamics.js` 905.

Across the code there are 10,101 functions and 401 classes. 164 functions are over 60 lines; the median function is
9 lines and the 90th percentile is 28.

**What the numbers say for slicing.**
- The small packages have the highest "shared" fraction (0.30 to 0.35). Up to a third of them is vocabulary and
  boilerplate the rest already has. That makes them the cheapest places to merge or distill, and it is a slice-level
  finding that only the package grain shows.
- `numbers/` and `spec/` share the least (0.11 to 0.13). They are where the distinct content is.

**Tiers.**
- **B for every package and module.** 26 packages is too many for stocks × measures.
- **Tier A for packages: none.** Packages are reached through layers instead (section 4).
- Module items carry `package`. Goals such as "no module over 1,500 lines" are written as a state (`oversize`), a
  stock that counts that state (`complexity-modules-oversize`), and `per: package` to say which package breaks it.
  The same pattern works for `complexity-modules-dead` and for `complexity-functions-long` with items per function
  (below).
- **Tier C.** Conditional compression, which needs the whole tree, and any per-package table at any SHA.

Function items (`function/<path>:<qualname>`) would give 10,101 items. **Do not make them.** Function-level measures
are tier C. A module item keeps only summaries: `functions`, `long_functions` (names), `max_fn_lines`,
`duplicates` (names) and `max_nesting`.

## 3. By language

Own product code: Python 71,309; JS 10,805 (25 files; vendored excluded); CSS 936; HTML 51.
YAML: 2,626 in `ergostat/` (library templates), 2,142 in `dev/model`, 5,696 in `examples/`.
Markdown: 48,710 in `docs/`, 5,916 in `dev/`, 665 in `ergostat/help`.
Shell: 205 lines. There is one JSON schema of 2,898 lines.

**Tier A.** One stock: `complexity-lines-js`. JS is the one language whose growth no current measure sees, because
`code_evidence.py` reads only `.py`. Python is the code scope already, and the rest are small or not code.
**Tier B.** `lang` on module items.
**Tier C.** Language × anything else.

Every measure family has to say which languages it covers. AST measures cover Python only; JS needs its own parser
or a token-level measure. Compression and line measures cover every language. A family that covers only Python says
so in its description, so that JS is not silently counted as zero.

## 4. By layer (a computed classification of module paths)

The layer map is a first-match list of path patterns, kept in one file beside the measure script. Modules the map
names wrongly are fixed there. Today's assignment, in own net lines (`slices.py`, `LAYERS`):

| Layer | What is in it | Net lines | Files |
|---|---|---|---|
| web-ui | `web/` (Python APIs, own JS, CSS) | 14,367 | 45 |
| ai-work | session, supervisor, calls, costs, sandbox, workspaces, intent, claims, decisions, recipes, messages, inbox, actions, repair, reports, intake | 11,753 | 98 |
| modelling-loop | `numbers/` proposals, improve, structural, judge, review, redesign*, changeset, scorecard, modeller, reviewer, gate, verify, ... | 8,913 | 33 |
| model-spec | `spec/` load, compile, ir, equation, findings, chains, causal, explain, ...; `model.py` | 7,733 | 23 |
| record | store, segments, storage, victoria, rollup, runlog, history, transcripts; `spec/` itemindex, items, changes, counts, relations, ... | 6,819 | 25 |
| engine | `spec/` engine, triggers, watchdog, shards, observer, blocks; runner, reload, restarts, watcher, service, state, notify, cron | 5,818 | 19 |
| cli | `cli/`, mcp, show, helpdocs | 5,068 | 27 |
| sd-analysis | `numbers/` simulate, fit, estimate, eta, extremes, sensitivity, dominance, modes, ... | 4,866 | 19 |
| views | blockdiagram, dynamics, graph, coherence, correspond, process, guide, series, fold, sensing | 4,709 | 10 |
| control | `control/`; `numbers/` extlaw, external, blockmodels | 3,495 | 13 |
| library | `library/` (templates) | 3,036 | 20 |
| remote | `remote/`, `numbers/remote_text` | 2,143 | 16 |
| bench | `bench/` (verification) | 1,979 | 13 |
| daemons | `daemons/` | 1,209 | 8 |
| leases | `leases/` | 1,183 | 10 |
| total | | 83,096 | 381 |

The layers cut across packages: `spec/` is split between model-spec, record and engine, and `numbers/` between the
modelling loop, SD analysis, control and remote. That is the point of the layer slice: it answers "how complex is
the engine" when the package tree does not.

**Tier A, for net lines only.** Six coarse layers, each a sum of the rows above:
- `complexity-lines-engine`: engine + record, 12.6k
- `complexity-lines-model`: model-spec + library, 10.8k
- `complexity-lines-modelling`: modelling-loop + sd-analysis + control, 17.3k
- `complexity-lines-drawing`: views + web-ui, 19.1k
- `complexity-lines-ai-work`: 11.8k
- `complexity-lines-interfaces`: cli + remote + leases + daemons + bench, 11.6k

That is **6 stocks**. They show where growth lands, layer by layer, on the system box.

**Tier B.** `layer` (fine grain) on module items.

**Backfill caveat.** The map is today's, so an old SHA is classified by today's patterns. A module that has moved or
been split since then lands in "other". Count the "other" lines at every backfilled SHA and show them as
`complexity-lines-unclassified`, which is 5 today. This stock is the slice's own health check.

## 5. By the factory model's systems (`dev/model/*.yaml`)

A `dev/bin` script belongs to the systems whose model file's `run:` lines name it. This is worked out from the
model, never written by hand. Today:

| Model file (system) | YAML lines | Parts | Scripts it runs (net lines of them) |
|---|---|---|---|
| knowledge | 572 | 89 | ask, knowledge, lesson, librarian, measure, plan, planreview, research (1,576) |
| landing | 381 | 64 | drain, live, queue, triage, upgrade (1,461) |
| building | 234 | 37 | dead, implement, intake, review (693) |
| code-health | 173 | 29 | measure, simplify (581) |
| manager | 163 | 32 | manage, manager, measure, parks, pools, watch (1,645) |
| resources | 153 | 28 | cleanup, resources (348) |
| measures | 148 | 26 | measure (379) |
| pools | 104 | 20 | pools, risk (368) |
| times | 64 | 55 | measure, times, watch (919) |
| interventions | 56 | 10 | measure |
| backlog | 42 | 6 | backlog, solve (442) |
| interlock | 37 | 7 | fac, load (653) |
| budget | 15 | 3 | fac |

Four scripts are named by no model file: `agents`, `brief`, `request` and `status`. They are libraries the named
scripts import (`measure.py` imports `brief`, `fac`, `parks` and `times`), so the mapping has to follow the import
closure. A script imported or run by several systems (`measure` by 6 systems; `fac` run by 2 and imported by `measure`) gets `system: shared`, rather than
being counted once per system. Otherwise the per-system sums add up to more than `dev/bin`.

**Tier A.** `complexity-lines-factory` (section 1) and `complexity-factory-model-parts`. **Tier B.** `system` on
`dev/bin` module items, plus one item per model file (`modelfile/dev/model/landing.yaml`) with its YAML lines, parts
and scripts' lines. That gives the per-system view in the Items tab without 13 × N stocks. **Tier C.** The same
mapping for `examples/` models, if it is ever wanted.

The same "system" key can later be applied to `ergostat/` through `ergostat.yaml`'s own model of the product, if one
names product modules. Today it does not.

## 6. By age and churn

The history is 8 days long, so "age" is measured in days and "churn over 60 days" (`code_evidence.py`'s
`CHURN_DAYS`) is the whole history.

Code lines alive at HEAD, by the day `git blame -w` attributes them to: 11-14 5,274 · 11-15 5,269 · 11-16 17,847 ·
11-17 16,559 · 11-18 22,885 · 11-19 15,811 · 11-20 12,791 · 11-21 10,066 · 11-22 1,214. These are raw lines of
`ergostat/` Python, own JS, `dev/bin` and `scripts`, 107.7k in all. Blame for the whole code takes 6 s on 4 threads.

| Package | Median age (days) | Share older than 4 days |
|---|---|---|
| control | 5.4 | 0.81 |
| web | 5.4 | 0.67 |
| top-level modules | 5.1 | 0.71 |
| cli | 5.0 | 0.70 |
| spec | 4.2 | 0.56 |
| numbers | 3.1 | 0.41 |
| remote | 1.5 | 0.00 (rewritten since 11-18) |
| repair | 0.6 | 0.00 |
| dev/bin | 1.6 | 0.00 (created 11-20) |

Churn in the last 7 days, in commits: spec 253, web 231, top-level 183, numbers 160, cli 107, library 78, leases 57.
Ten packages had 10 or fewer.

**Tiers.**
- **Tier B.** Module items get `added` (the date the file was first added, `--follow`), `median_line_age` and
  `churn_7d` / `churn_30d`. Churn × size is `code_evidence.py`'s pick signal, so it already belongs on the module.
- **Tier A.** `complexity-lines-young`: lines blamed to the last 2 days. It is a rough "fresh code not yet distilled"
  stock. As the history lengthens, change the windows to 7 and 30 days.
- **Tier C.** Age buckets × layer, and survival curves: how long a line lives before it is rewritten. That is
  `numbers/survival.py`'s Kaplan-Meier, applied to lines.

**Two caveats.**
- `blame -w` without `-M` or `-C` resets the age of moved code. Moved code should keep its age, so use `-M -C` for
  the measure; it is slower but within budget.
- Run every blame-based measure against a SHA on main, never the working tree.

## 7. By the gap or feature that added it

Of 288 first-parent merges, 152 are `Merge branch 'factory/<name>'`. The rest predate the factory or are the
coordinator's own. Each factory merge's diff against its first parent, over `ergostat/`, `dev/` and `scripts/`:

- Net lines per merge: median +89, 90th percentile +383, total +23,891.
- Test lines added by those merges: +32,481 net.
- **Merges with a net removal: 0.** Not one factory merge has made the code smaller. 28 merges added more than 300
  lines. The largest were ai-approver-for-repairs-needs-a +1,521, relations-as-of +990,
  finding-structure-from-residuals +657 and code-health-simplifier +557.

The gap items already carry `merged_lines` (`measure.py`'s size-accuracy). **Tier B.** At merge, the measure runs on
both parents. The delta of each tier-A family (Δlines, Δxz, Δfunctions, Δduplicates, Δlong functions, Δdead) is
written as fields on the existing `gap/<name>` item, in the same program that records `merged_lines`. No new item
kind is needed.

The factory gets two things from this:
- A size and complexity cost per gap, to set against the gap's planned size class.
- **Tier A flows.** `complexity-lines-added-by-gaps` sums Δlines entering merged (an `items` flow with `sum:`, SPEC
  §6), and `complexity-lines-removed-by-simplify` covers the simplifier's gaps. Together they say whether the
  simplifier's outflow matches the gaps' inflow, which is the loop the owner is asking about.

**Tier C.** Attribution of every line alive at HEAD to the gap that added it: blame → commit → its first-parent merge
→ branch. This is a "which features cost the most code" table, and it is never stored.

## 8. Tests per module

Test code is 63,116 Python lines in 209 files, against 71,309 product Python lines, a ratio of 0.89. 21 test files
(10,321 lines, 435 tests) reach `dev/bin`, so the factory's tests are about 16% of the suite. 11 files are browser
tests (10,696 lines), and 24 files import nothing of `ergostat`.

**Attribution by import is noisy.** `model.py`, `spec` and `store.py` are each imported by about 140 test files,
because they are the fixtures' foundations. A test file importing a module says little about what it tests. Use
three keys, from weakest to strongest:
1. **Name.** `test_<module>.py` ↔ `<module>.py`. Cheap, and it covers most of the long tail.
2. **Imports, excluding the foundation modules** (`model`, `spec`, `store`, and any module imported by more than a
   third of the test files). The cut is computed, not listed.
3. **Coverage contexts** (`coverage run --context=test` / dynamic contexts). They give which tests execute each
   module. `code-health-coverage`'s report already gives each module's share, so it can also record the contexts.
   This is the only honest per-module test mapping. Compute it when the coverage report is made, never in a sensor.

**Tiers.**
- **Tier A.** `complexity-lines-tests` (section 1) and the auxiliary `complexity-test-ratio`: test lines over product
  lines.
- **Tier B.** Module items get `tests_named`, `tests_importing` (key 2) and `coverage` (already in `code_evidence.py`),
  plus `tests_executing` (key 3) when the report has contexts.
- Test files are module items themselves, with `area: tests` and `tests: N`. The tests' own complexity counts in
  every measure: tests are 44% of the repository's Python.

## 9. By token class within a file (a slice of the text, not the tree)

In `ergostat/`, `dev/bin/` and `scripts/` Python: code 74,977, docstrings 9,509, comment-only 438, blank 11,345.
Trailing comments live inside code lines. Bytes per net line run at about 60, because the docstrings are long prose.
Kolmogorov-style measures (compressed size) count prose and code alike. Report them on two streams, the code with
docstrings and comments stripped and the docstrings alone, so that a distillation which shortens prose is not
confused with one that removes logic.

**Tier A.** `complexity-xz-product` (section 1) is the code stream. Add `complexity-lines-docstrings`, 9.5k.
**Tier B.** `docstring_lines` on module items.

## 10. The stock budget, in total

| Tier A part | Count |
|---|---|
| Area × {lines, xz} + docs and examples lines | 10 |
| `complexity-factory-model-parts` | 1 |
| `complexity-lines-js` | 1 |
| Coarse layers' lines + `-unclassified` | 7 |
| `complexity-lines-young` | 1 |
| `complexity-lines-docstrings` | 1 |
| Threshold-state counts over module items (`-modules-oversize`, `-modules-dead`, ...) | about 4 |
| Auxiliaries: `complexity-test-ratio`, `complexity-xz-ratio-product` | 2 |
| Flows: lines added by gaps, removed by simplify, and `changes:` rises/falls on `complexity-lines-product` | 4 |
| **Total** | **about 31**, plus the measure families' code-scope parts the sibling plan defines (the five existing `code-*` auxiliaries are among them) |

All of these live in `dev/model/complexity.yaml`, system `complexity` within `code-health`, which gives one box with
a `show:` of about 6.

## 11. Computing it and backfilling

- **One pass over a tree.** `git ls-tree` plus one `git cat-file --batch`, which is what `code_evidence.py` already
  does. All the slices above are aggregations of one per-file row. The full measure here (sizes, AST counts and
  whole-area xz) took 8.6 s on one core for HEAD.
- **Cache by blob SHA.** A file's row depends only on its blob, except churn, age and conditional compression, which
  are per-tree. There are about 6,500 distinct objects under the code paths across the 594 first-parent commits, so
  each blob is parsed once and each commit's per-file rows are a lookup. Per-tree compressions of the 4 areas cost
  about 3 s per commit, about 30 minutes for all 594 on 4 cores. Use preset 6, as `ncd.py` does; preset 9 is no
  better at these sizes.
- **Order readings by first-parent seq, never by time.** Many commits on 11-14 share hours. `measure.py` already
  orders code readings by seq and SHA. The backfill gives one reading per first-parent commit: 594 points today.
- **A gap in ergostat itself.** I found no way in the SPEC to record a sensor reading at a past time: `sensor --read`
  records now. Until there is one, the history lives where `code-measures.jsonl` already keeps it (`run/`, one line
  per seq and SHA), and the charts read it from there. A request for `sensor --read V --at T` (or importing a
  readings file) belongs on the GAPS list, so that the backfill becomes real stock history the fit and the dynamics
  view can use.
