# Complexity measures for ergostat: a catalogue, with first numbers

For the owner's request in `complexity-ask.md`: measure the code's complexity in as many forms and slices as are useful,
as series on main, backfilled from git history. This file lists the measures, how to compute each, what it costs on
the current tree, and what a change in it would tell us. It ends with the measures to start with.

The figures come from a read-only run on the scratch copy at HEAD `2468c59bcb` (2026-11-22). The scope is
`ergostat/**/*.py`: 352 files, 81,456 lines, 4,263,231 bytes. That is the owner's "81,000 lines". Other trees are
measured apart: tests/ (74,559 py lines), dev/ (9,943), examples/ (9,487), scripts/ (4,980) and the docs
(57,357 lines of `docs/**/*.md`). The scripts are in `scratchpad/design/work/`: `cx_measure.py`, `cx_history.py`
and `cx_imports.py`. Their outputs are `cx-head.json` and `cx-hist.json` in the same folder. Every script uses the
Python standard library only and reads blobs from git with `git cat-file --batch`, never from the working tree.

## 0. What already exists (build on it, do not duplicate it)

- `scripts/code_evidence.py` produces one row per module of `ergostat/`, `dev/bin/` and `scripts/`. It reads them at
  a git ref and records net lines, functions over 60 lines, 60-day churn, duplicate function bodies (a normalised
  AST hash), dead candidates (names nothing else mentions) and coverage.
- `dev/bin/measure.py code-*` sums those rows. Each reading is stamped with the seq and sha it measured in
  `run/code-measures.jsonl`. It also gives each measure's `-change` over main's last 10 merges.
- `dev/model/code-health.yaml` holds the five measures as auxiliaries, with goals that they do not rise and a
  simplifier that fires on drift.

The new measures should follow the same pattern. A `scripts/code_complexity.py` (or an extension of
`code_evidence.py`) would emit rows per module at a ref. `measure.py` would sum them per slice, stamped by seq and
sha. A backfill would walk main's first-parent merges. The model would get one stock (or auxiliary, following
code-health's precedent) per measure. Driven by `+gaps-merged`/`-removals-merged` as now.

## 1. Slices: the different ways to cut the code

Every measure below is computed per file. A measure that composes is summed or recomputed for each slice. A
compression measure must be **recomputed on the concatenation**, never summed, because cross-file redundancy is the
point.

- **By tree:** `ergostat/` (the product), `dev/` (the factory), `scripts/`, `tests/`, `examples/`, own JS under
  `ergostat/web/static/`, docs. Leave out vendored JS: `elk.bundled.js` (6,696 lines), `highlight.min.js`,
  `uplot/` and `libavoid/`.
- **By package:** the 25 subpackages of `ergostat/`, plus the 44 top-level modules as one package.
- **By file**, and **by function or class** for the AST measures.
- **By kind of text:** code only (comments and docstrings stripped, with `ast.unparse` normalising layout), prose
  (comments and docstrings), and *shape* (identifiers, strings and numbers replaced by placeholders).
- **By age:** the lines still alive per month of origin (`git blame --line-porcelain`), and old code against new.
- **By origin:** which gap or item a line came from, read from commit trailers. This gives complexity added per gap
  and removed per simplification.
- **By size or complexity band:** functions in cyclomatic bands 1–5, 6–10, 11–20, 21–50 and over 50, or modules in
  size bands. The tail usually matters more than the mean.

## 2. The catalogue

Costs are wall time on one core at HEAD, measured where a figure is given and estimated where marked "est.". A
backfill multiplies the per-commit cost by main's 594 first-parent commits. Caching per-file results by blob sha cuts
that cost to the changed files plus the tree-level compressions.

### 2.1 Size

| Measure | How (stdlib) | Now | Cost | A change tells us |
|---|---|---|---|---|
| Physical lines | `count(b"\n")` | 81,456 | <0.2 s | Growth. It says nothing about simplicity on its own. |
| Net lines / SLOC (not blank, not only a comment) | `tokenize`, as in `code_evidence.net_lines` | (existing measure) | ~1 s | The usual LOC. Already a stock. |
| Code-only lines (docstrings and comments stripped, `ast.unparse`) | `ast` | 62,085 | 1.3 s | Robust to reformatting and to prose. The gap to physical lines is the prose share (~24%). |
| Bytes | `len` | 4,263,231; stripped 3,186,285 | 0 | Same as lines, but finer. |
| Tokens (no comments, NL, INDENT or DEDENT) | `tokenize` | 829,174 | ~2 s | Size that line wrapping and formatting cannot change. The best simple size unit. |
| AST nodes | `ast.walk` | 848,300 | ~1.5 s | Structural size. Tokens per node shows syntactic overhead. |
| Definitions: functions, classes, top-level, public | `ast` | 4,192 functions, 305 classes, 3,163 top-level defs (2,325 public) | in the AST pass | Count of concepts. Splitting a long function raises it, so read it with the mean size. |
| Files, packages | ls-tree | 352 files, 25 packages | 0 | Granularity. |

### 2.2 Compression: estimates of Kolmogorov complexity

K(x) cannot be computed. A real compressor's output length is an upper bound on it, and changes in that bound track
changes in information content well. Use several compressors. They see different context:

- **zlib** has a 32 KB window. It sees repetition only within ~32 KB.
- **bz2** works in 900 KB blocks.
- **lzma** (preset 9|EXTREME) has a dictionary of up to 64 MB, so it sees the whole tree.

Record the Python and liblzma versions with each reading, and always concatenate files in sorted path order. The
compressed size depends on both.

| Measure | How | Now (ergostat/ py) | Cost | A change tells us |
|---|---|---|---|---|
| **Tree K-estimate**: C(tree), concatenated | `lzma.compress(blob, preset=9\|lzma.PRESET_EXTREME)` | lzma 941,080 B (ratio 0.221); bz2 970,247 (0.228); zlib 1,240,475 (0.291) | lzma 1.5 s, bz2 0.2 s, zlib 0.3 s | **The headline measure.** It counts information, not keystrokes. Code that only repeats existing code grows lines but barely grows this. |
| **Code-only K-estimate**: C(stripped tree) | strip docstrings and comments with `ast` and `ast.unparse`, then lzma | 666,592 B | +1.3 s | Insensitive to formatting churn and to prose. **The best single "how much logic is there" number.** Prose's share of the information is 941k−667k ≈ 29%. |
| Prose K-estimate | lzma of comments and docstrings only | est. ~270 KB | +1 s | The documentation load carried in the code. |
| Compression ratio C/raw, per tree, package and file | as above | tree 0.221. Packages range from 0.232 (spec) to 0.337 (intake). Files of 100+ lines range from 0.235 (`spec/compile.py`) to 0.48 (`supervisor.py`). | small | **A low ratio means repetitive text**: boilerplate, copy-paste, long repeated names. These are the "easy tricks" targets. Small files compress worse because they have less context, so compare files only within a size band. |
| **Cross-file redundancy**: 1 − C(tree)/Σ C(file) | per-file lzma and tree lzma | lzma 0.323 (Σ files 1,390,964 against tree 941,080). bz2 0.284. zlib 0.120 (its window hides it). Per package, 0.14 (claims) to 0.27 (numbers, cli). | +1.5 s | The share of each file's information that is already said elsewhere. **When it rises, code is being repeated across files**, and a shared helper or a deletion is the cure. |
| **Conditional complexity of a slice**: C(rest+p) − C(rest) | lzma, once per slice | claims: 9,156 B alone, 6,100 B given the rest (33% already said elsewhere). workspaces 7,552→5,036. calls 6,808→4,404. intake 5,784→3,804. leases 20,312→14,968. costs 14,920→11,148. | ~3.5 s per slice (22 s for 6) | What a package **adds** to the system. Deleting the package would save this much "real" content. Better than lines when ranking what to remove. |
| **NCD** (normalised compression distance) between packages | (C(xy) − min(C(x), C(y))) / max(C(x), C(y)), **with lzma** | The nearest pairs are intent–messages 0.870, claims–intent 0.871, claims–workspaces 0.882, intent–decisions 0.882. The farthest are numbers–calls 0.993 and spec–calls 0.991. 105 pairs over 15 packages took 12.8 s. | O(p²) lzma | Packages that say the same things: candidates for merging or for a shared layer. **Never use zlib for objects over ~16 KB.** With zlib the same pairs read 0.91–0.998 and spec–cli, numbers–workspaces and spec–control all read 0.998, because its 32 KB window cannot see the first object while it compresses the second. |
| NCD between files (near-duplicate search) | zlib is fine for files under ~16 KB, lzma above that | Inside `numbers/` (55 files of 60+ lines, 1,485 pairs, 4 s): archreview–modeller 0.843, meta–verify 0.844, modeller–redesigner 0.846, trial–unmoved 0.851. Whole tree: 327 files, 53,301 pairs, about 60 s with zlib (est.). | ~1 min, or ~4 min with lzma (est.) | A ranked list of near-twin files for a distillation pass. Track the count of pairs under a threshold such as 0.80 as a series. The list itself is evidence for gaps. |
| Shape K-estimate | lzma of the token stream with identifiers → `I`, literals → `L` | ~270 KB on a 2.29 MB stream (ratio 0.118) | 3.5 s with tokenizing | Structural information without names. If text K rises while shape K stays flat, the change is renames and literals, not logic. |
| Compressor agreement (bz2/lzma, zlib/lzma) | from the above | 1.03 and 1.32 | 0 | A rising zlib/lzma gap means repetition at long range (across files). A falling one means the repetition is local. |

### 2.3 Entropy and Lempel-Ziv

| Measure | How | Now | Cost | A change tells us |
|---|---|---|---|---|
| Unigram token entropy (bits per token) | `Counter` over token strings | 7.72 bits, over a vocabulary of 23,873 | in the token pass | Lexical richness. A rise means more distinct names and words. Read it with the vocabulary size: a vocabulary growing faster than tokens means many new names for things. |
| Shape entropy, H₁ and the bigram conditional H₂ | `Counter` over shape tokens | H₁ 4.11, H₂|₁ 2.79 bits | same | How predictable the syntax is. Low H₂ means idiomatic, regular code. |
| Vocabulary growth (Heaps' law exponent) | distinct names against tokens, over files in a fixed order | est. | cheap | Whether the code reuses its concepts or keeps inventing new ones. |
| **Lempel-Ziv (LZ76) complexity** | Kaspar–Schuster phrase count on the shape stream, normalised by n/log_k n | numbers 0.172 (19,158 phrases over 185k tokens), spec 0.168 | **191 s and 138 s in pure Python**, O(n²) in the worst case | The textbook estimate. It agrees with the lzma ratio and costs about 100× more. **Not worth tracking.** lzma is an LZ77-family estimate and gives the same signal. Keep LZ76 as a one-off check only, or on functions (n of a few hundred), where it is cheap. |

### 2.4 Control flow and cognitive complexity

| Measure | How | Now | Cost | A change tells us |
|---|---|---|---|---|
| **McCabe cyclomatic** per function: 1 + branches (if, for, while, except, comprehension, match case, IfExp, assert, and/or) | `ast`, ~20 lines | 4,192 functions. Mean 8.6, median 5, p90 19, p99 62, max 257 (`coherence.compare`, 374 lines). 978 over 10, 387 over 20. Sum 36,123. | ~2 s | Paths through the code, which is what tests must cover. **Track the sum, the count over 20 and the p99.** The mean hides the tail. The top six (`coherence.compare` 257, `web/server._answer` 218, `state.snapshot` 149, `spec/chains._one` 136, `mcp.call` 122, `spec/compile.run` 119) are the first targets. |
| **Cognitive complexity** (SonarSource): +1 per break in flow, plus the nesting depth | `ast` visitor, ~80 lines. The `complexipy` package does it too, but is not needed. | est. | ~2 s | How hard the code is to read: it penalises nesting and cyclomatic does not. Use it for the "flatten this" tricks. |
| Max nesting depth per function | `ast` | est. | in the same pass | Arrow code. |
| Function length distribution | `end_lineno − lineno` | over 60 lines is already a measure | 0 | The tail is what matters. |
| Parameters per function, returns per function, branches per `match`/`if` chain | `ast` | est. | 0 | Interface width. Long `if` chains are dispatch tables waiting to be written. |
| Maintainability Index (Halstead, cyclomatic and LOC combined) | formula | est. | 0 | A composite. **Not worth tracking as a goal** because its parts say more, but it is cheap if wanted. |

### 2.5 Halstead

Count n₁ and n₂ (distinct operators and operands) and N₁ and N₂ (their totals) per function from `tokenize`. Treat
keywords, OP tokens and calls as operators, and names and literals as operands. From these:

- vocabulary n = n₁ + n₂
- length N = N₁ + N₂
- volume V = N·log₂ n
- difficulty D = (n₁/2)·(N₂/n₂)
- effort E = D·V

All stdlib, about 3 s. Volume is a crude information measure that sits between token count and compressed size.
Difficulty rises when the same operands are worked over by many operators. **Track ΣV and the p90 of D per
function.** `radon` computes these too, but it is an extra dependency for about 40 lines of code, and not worth it
for Python.

### 2.6 Duplication and clones

| Measure | How | Now | Cost | A change tells us |
|---|---|---|---|---|
| Exact duplicate function bodies (type-1/2: names and constants normalised, AST hash, 5+ lines) | `ast.dump` and sha1 (already in `code_evidence.py`) | 12 functions | ~2 s | Literal copy-paste. Few today, so a small absolute number to keep at zero. |
| **Token-shape clone coverage** (type-2: a K-token window of the shape stream that occurs more than once) | hash every 40-token window and mark the covered tokens. Winnowing (Schleimer et al.) cuts memory. | **8.4% of all tokens** lie in a 40-token shape window that appears elsewhere | ~6 s | The real duplication level. It sees copies inside functions and across files that whole-body hashing misses. Report it at K = 25, 40 and 80, by package, and as clone pairs. |
| Near-miss clones (type-3: statements added or removed) | hash AST subtrees at statement-block level and compare sets by Jaccard, or use file-level NCD (§2.2) | est. | ~10–30 s | Copy, paste and edit. NCD finds the files; subtree hashing finds the blocks. |
| Repeated literals: string constants, f-string templates and magic numbers occurring 3+ times | `ast.Constant` counter | est. | 1 s | Easy wins: hoist them into named constants. Error messages and help texts are likely heavy here. |
| Similar function signatures, the same parameter lists repeated | `ast` | est. | 1 s | Missing objects, or parameters threaded through many layers. |

`jscpd`, `pylint --duplicate-code` and PMD CPD are not worth adding: the stdlib versions above take an afternoon and
can run at any git ref.

### 2.7 Coupling and structure

These come from `cx_imports.py`, which counts every `ergostat` import, the deferred in-function ones included. Count
top-level and deferred imports separately as two series. A deferred import is often how a cycle is hidden.

| Measure | Now | A change tells us |
|---|---|---|
| Modules and internal import edges | 352 modules, 1,616 edges (4.6 per module) | Density of coupling. |
| Fan-in / fan-out per module | max fan-in 126 (`spec.ir`), max fan-out 60 (`spec.engine`) | High fan-in is a stable core: fine if small. High fan-out is a god module. |
| **Cycles (strongly connected components)** | 5 cycles. **The largest holds 138 modules**, and 155 modules are in a cycle. | The single most telling structure measure: 40% of modules cannot be understood or removed apart. Track the largest SCC's size and the number of modules in cycles. |
| Depth (longest path in the condensed DAG), layering violations (an import against a declared layer order) | est. | Whether the layering is real. |
| Package-level coupling: instability I = Ce/(Ca+Ce), abstractness, distance from the main sequence (Martin) | est. | Packages to break or merge. Read it with the package NCD. |
| Public API surface: top-level names not starting with `_`, `__all__`, CLI commands, MCP tools, web routes, spec keys in `schema/` | 2,325 public of 3,163 top-level defs (73%) | The surface others depend on. A good distillation pass shrinks it. |
| Each module's names used by others (with `importlab`- or `ast`-based resolution) | est. | Unused public names: the halfway point between public and dead. |

Cost: 1.6 s for the graph and well under a second for the SCCs. All stdlib. `pydeps` and `grimp` are not needed.

### 2.8 Dead code candidates

- **Names nothing mentions**: already `code-dead-candidates`, a word search over the repo.
- **Unreferenced from an entry point**: reachability from the console scripts, the CLI, the MCP tools, `run:` lines
  in YAML, and the tests, over the call/import graph. This is stdlib `ast` work, about 200 lines.
- **Reached only by tests**: names that only `tests/` mention. Code that exists only to be tested is a strong removal
  candidate.
- **Never executed under the unit suite**: zero-coverage functions from the existing coverage report, per function
  rather than per module.
- **`vulture`** gives a confidence per finding and handles attributes and unused arguments. It is **worth adding as a
  dev dependency** for the candidate list only, never as a goal, since it has false positives on dynamic names. A
  run costs ~5 s.

A change tells us whether removals keep pace with additions. The series to track is candidates per 1,000 lines.

### 2.9 Docs and tests relative to code

| Measure | Now | A change tells us |
|---|---|---|
| Test lines / code lines | 74,559 / 81,456 = 0.92 | Tests growing faster than code: maybe brittle, maybe good. Compare it with coverage. |
| Test K / code K (lzma, stripped) | est. | Information in tests against code. Test code is usually far more repetitive, so a low test ratio is expected. A rising one means more fixtures per behaviour. |
| Docstring and comment share of lines or K | lines 24%, K ~29% (from §2.2) | Whether prose grows with code or is dropped. |
| Docs/ lines and K per code K | docs/ 57,357 lines | Spec weight. A spec that grows faster than code may be over-specifying. |
| Public names without a docstring | est. | Missing documentation, which is cheap to find. |
| Tests per public name, and asserts per test | est. | Test density. |

### 2.10 Churn and age (from git)

| Measure | How | Now | A change tells us |
|---|---|---|---|
| Lines added and deleted over a window, per slice | `git log --numstat` | 60 days (the whole history): 1,043 commits touching ergostat/, +127,163 and −20,329. **Deletions are 16% of additions.** 1 s. | **The deletion ratio is the distillation rate.** Track it per week. |
| Churn per file (commits and lines in a window) | the same | existing (60-day commits) | Hot spots. **Churn × complexity** (Tornhill's hotspots) is the best ranking of where to simplify first. |
| Survival / age of lines (blame), per month of origin | `git blame --line-porcelain` per file | est. ~2–4 min for the tree, 4 cores | Code that never changes after landing (stable or dead) against code rewritten constantly. |
| Rework rate: lines deleted within 14 days of being added | blame diff between refs | est. | Thrash: work done twice. |
| Change coupling: files that change together without an import between them | co-change counts from `git log --name-only` | est. ~5 s | Hidden coupling that the import graph does not show. |
| Complexity added per gap, from trailers, and removed per simplification (`Removed:` trailers) | per merge: the difference of each measure across the merge | est. | Which kinds of work inflate the code, and whether simplifications pay off. |

### 2.11 History: what backfilling already shows

`cx_history.py` sampled 14 of main's 594 first-parent commits (27.5 s in all, ~2 s per commit for size and three
compressors):

| date | files | lines | lzma B | lzma/raw |
|---|---|---|---|---|
| 11-14 07:29 | 13 | 2,384 | 26,556 | 0.260 |
| 11-15 22:51 | 41 | 9,205 | 105,440 | 0.234 |
| 11-17 03:06 | 92 | 25,981 | 300,032 | 0.227 |
| 11-18 06:51 | 198 | 46,076 | 521,040 | 0.221 |
| 11-19 14:56 | 277 | 61,949 | 701,032 | 0.220 |
| 11-20 17:30 | 312 | 70,845 | 806,380 | 0.220 |
| 11-21 17:46 | 332 | 74,990 | 860,556 | 0.220 |
| 11-22 03:52 | 352 | 81,456 | 941,080 | 0.221 |

The ratio fell while the code was small, as a compressor finds more context, and has held at 0.220 ± 0.001 since
~46k lines. So **information has grown in proportion to lines**: about 11.6 KB of lzma per 1,000 lines. New code is
neither more nor less repetitive than old. A goal could be to bend that ratio down (more reuse) while holding the
code-only K-estimate flat.

**Backfill cost.** Size and compression run at ~2 s per commit, ~20 min for all 594. The full first set (§3) runs at
~10–15 s per commit, ~2.5 h on one core and ~40 min on 4 workers. Caching per-file AST measures by blob sha cuts it
further, since most merges touch a few files. Run the backfill over first-parent merges only and stamp each reading
with seq and sha, as `run/code-measures.jsonl` does now.

## 3. Pitfalls, so a reading means what it seems

- **The zlib window** (32 KB) makes zlib blind to cross-file and cross-package redundancy. Use lzma for anything
  over ~16 KB. This experiment saw it directly: zlib cross-file redundancy read 0.12 against lzma's 0.32.
- **Order and version:** the concatenation order (sorted paths) and the liblzma version change the bytes. Record
  both, and re-baseline if either changes.
- **Formatting:** a `ruff format` run moves raw K but not the code-only K (`ast.unparse` normalises), nor tokens or
  AST measures. Prefer those for goals.
- **Renames** move text K and entropy but not shape K. Read the two together.
- **Small objects compress badly**, because the compressor's header and lack of context dominate. Compare ratios
  within a size band only. Use conditional complexity (C(rest+p) − C(rest)) rather than C(p) for small slices.
- **The tokenizer on Python 3.12+** splits f-strings into `FSTRING_*` tokens. Map them to the literal placeholder,
  or the shape vocabulary inflates. The first script did not, and its 5,690-shape vocabulary is wrong for that
  reason; `cx_history.py` maps them.
- **The import cycle count** depends on counting in-function imports. Report top-level and deferred imports
  separately.
- **Every measure is a candidate signal, never a verdict.** Like `code-dead-candidates`, a goal on one should only
  ask for a look, not force a removal.

## 4. Where to start: cheapest and most telling

Each of these runs in seconds, needs only the stdlib and backfills over all 594 merges in under an hour:

1. **Code-only K-estimate**: lzma of the docstring- and comment-stripped, `ast.unparse`d tree, plus the raw tree
   lzma and its ratio. It is the closest thing to "how much there really is" and resists formatting and prose
   noise. (~3 s)
2. **Cross-file redundancy**, 1 − C(tree)/Σ C(file), per tree and per package. The direct measure of the "easy
   tricks" target: things said more than once. (~2 s)
3. **Token-shape clone coverage** at K = 40, per package. 8.4% today. (~6 s)
4. **Cyclomatic sum, count over 20 and p99**. 36,123, 387 and 62 today. Add cognitive complexity next. (~2 s)
5. **Largest import SCC and modules in cycles**. 138 and 155 today: the strongest structural signal. (~2 s)
6. **Deletion ratio** (lines deleted / added per week) from `git log --numstat`. 16% over 60 days. (~1 s)
7. Already tracked: tokens and AST nodes beside net lines, as size units that formatting cannot move.

Next tier, also cheap, but they produce lists more than series:

- **Conditional complexity per package**: what each package adds; rank removals by it.
- **lzma NCD between packages, and zlib NCD between files under 16 KB**: near-twins for merge candidates.
- **Churn × cyclomatic hotspots**: where to simplify first.
- **Halstead ΣV.**
- **`vulture` candidates.**

Not worth tracking: LZ76 (100× the cost of lzma for the same signal), the Maintainability Index (a blend of numbers
we already have), and the extra packages `radon`, `lizard` and `jscpd`. The one exception is **`lizard`**, if the
own JavaScript (~10k lines outside the vendored bundles) is to get cyclomatic numbers, since stdlib Python cannot
parse JS. It is worth adding only when the JS is in scope.

Every one of these suits a stock or auxiliary sensor in the shape of `dev/model/code-health.yaml`:
`measure.py complexity-<name>`, reading rows from one evidence script at a ref, and driven by `+gaps-merged` and
`-removals-merged`. The slices (tree, package, kind of text) become separate series or labels, whichever the model
supports.
