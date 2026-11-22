# cx-measure-frame: one complexity script, its cache and its output format

depends-on: []

Branch `cx-measure-frame`, from main. From the owner's request of 2026-11-22: measure the code's complexity in many forms and slices, as stocks on main, backfilled from git. Every other `cx-` gap builds against the format this one fixes.

## The problem

The factory has five code measures (`dev/model/code-health.yaml`, `dev/bin/measure.py`, `scripts/code_evidence.py`). Each sensor re-runs the whole evidence script, nothing is cached, and there is no place to add a measure without another full run per hour. Many more measures need one result per commit, computed once, and no sensor may wait on a computation.

## The change

A new stdlib-only `dev/bin/complexity.py` that measures a git ref (never the working files: `git ls-tree -r` plus one `git cat-file --batch`), caches per blob and per commit under the instance's `run/complexity/`, and loads measure families from sibling modules `dev/bin/cx_<family>.py`. It only measures and prints: nothing here writes the record, and no model sensor runs it (the record is filled by `cx-backfill-run`, one reading per commit at the commit's time).

## Definition of done

1. **Commands.** `complexity.py measure [SHA] [--family F]` (default: the configured base branch, resolved once) computes what the commit file lacks. `complexity.py value NAME [SHA]` prints, as its last line, the series' value at the newest measured first-parent commit at or before SHA, and names that sha on stderr; it never computes; no value is exit 1 with `NAME: no value (why)`, never 0. `complexity.py history NAME [--last N]` prints `seq sha at value` per measured commit. `complexity.py rows [SHA]` prints one JSON line per file. `complexity.py list [--json]` prints every series (name, unit, family, `part`, description). `complexity.py report NAME [SHA] [--json]` runs a family's report (none yet).
2. **Commit file** `run/complexity/commits/<sha>.json`, written by atomic rename: `{"v": 1, "sha": "<40 hex>", "seq": <git rev-list --count --first-parent>, "at": <committer time, epoch seconds>, "families": {"<family>": {"version": int, "env": str, "state": "ok" | "failed" | "skipped", "error": str or null, "tries": int, "seconds": number}}, "values": {"<series>": number}, "detail": {"<family>": JSON}}`. `values` holds series only; anything else a family wants to keep (a library fingerprint, a per-commit file list) goes in `detail`.
3. **Each family is computed apart**: its own lock file (`run/complexity/locks/<family>`), its own entry, merged into the commit file under a short lock. A family is recomputed when its `version` or `env` differs. A family that raises is recorded `failed` with its error and gives its series no value; it is tried again on the next `measure` of that sha, up to 3 tries per (sha, version, env), and the others stand.
4. **Row** (`rows`): `{"path", "blob", "area", "package", "lang", "vendored", ...other slice keys as flat strings, "m": {"<measure>": number or list}}`. `area` is one of `product` (`ergostat/`), `factory` (`dev/bin/`), `scripts`, `tests`, `examples`, `docs`, `other`; `package` is the first folder under `ergostat/` (or `top`); `lang` from the suffix. The **code scope** is product + factory + scripts. Vendored files (one written list: the bundled layout, highlighting, routing, charting and markdown libraries and the wasm under the web static folder) carry `vendored: true` and are left out of every sum.
5. **Blob cache** `run/complexity/blobs/<family>-v<VERSION>-<env>.jsonl`, one line `{"blob", "m"}`: a blob is measured once in all history.
6. **Family contract.** A module `dev/bin/cx_<family>.py` found by name may define `VERSION` (int), `ENV` (a function returning a short string naming what besides the code the result depends on, e.g. the Python minor version; default empty), `SERIES` (`{name: {unit, description, part: bool}}`; `part: true` means the factory model has a part of that name, `false` means the value is kept in the cache only), `EVERY` (stride, default 1: the family is measured only at commits whose `seq` is a multiple of it and is `skipped` elsewhere; its series have readings only at those commits, and `value` answers with the newest of them), `keys(path) -> dict[str, str]`, `per_file(path, text) -> dict` (cached by blob), `per_commit(snap) -> {series: number}` (may also return `detail`), and `REPORTS` (`{name: fn(snap) -> list[dict]}`). `snap` gives `sha`, `seq`, `at`, `rows`, `text(path)`, `git(*args)`, `sum(measure, **where)`, `commit(sha)` (another commit's file, or None) and `first_parents(n)`.
7. **Series names** are `complexity-<measure>[-<member>]` and equal the model part's name when `part` is true.
8. **First family** `cx_size.py` (`ENV`: the Python minor version, since tokenizing changed): per file `lines`, `net_lines` (as `code_evidence.net_lines`), `bytes`, `tokens` (from `tokenize`; comments and layout tokens left out; an f-string is one token however the tokenizer splits it). Series: `complexity-tokens` (Python of the code scope, `part: true`), and cache-only `complexity-lines-code` and `complexity-files-code`.
9. **Model.** New `dev/model/complexity.yaml`: system `complexity` within `code-health`; stock `complexity-tokens` with `sensor: {manual: true}` (its description says the readings are recorded per commit of main, at the commit's time, by `complexity.py record`, never by a person or a schedule) and flows `complexity-tokens-grown` (`changes: rises, over: 1d`) and `complexity-tokens-distilled` (`changes: falls, over: 1d`). The file's header comment states the pattern for later gaps: a headline stock gets grown and distilled flows, both `over: 1d`; a sliced stock one two-way `-change` flow (`changes: net, over: 1d`); a ratio, share or percentile is an auxiliary with `sensor: {manual: true}` and `driven-by` naming the stocks it is computed from (else `check` finds auxiliary-without-causes); no `changes` flow is drawn as caused by another flow; each later family brings its own `dev/model/complexity-<family>.yaml` with `defaults: {system: complexity}`; a measure becomes a part only when someone will read it weekly, and otherwise stays `part: false`.
10. At most 4 processes. `dev/README.md` gains a short section: what is measured, where the cache is, `complexity.py list`.

## Files to touch

`dev/bin/complexity.py` (new), `dev/bin/cx_size.py` (new), `dev/model/complexity.yaml` (new), `dev/README.md`, `tests/factory_cx.py` (new: builds a small git repository for the families' tests), `tests/test_factory_cx_frame.py` (new).

## Acceptance tests

`tests/test_factory_cx_frame.py`:
- `test_commit_file_shape`: on a fixture repository of three commits, the commit file has exactly the keys of point 2; `seq` and `at` match git.
- `test_reads_the_ref_not_the_working_files`: an uncommitted edit changes nothing.
- `test_blob_measured_once`: a second commit that changes one file calls `per_file` once.
- `test_vendored_left_out_and_marked`.
- `test_value_never_computes`: `value` on an unmeasured sha answers with the newest measured ancestor and starts no family; with none measured it exits 1.
- `test_failed_family_is_retried_then_left`: a family that raises once succeeds on the next `measure`; one that always raises stops at 3 tries; the other families' values stand throughout.
- `test_version_or_env_recomputes_only_that_family`.
- `test_stride_family_skipped_off_stride`.
- `test_fstring_is_one_token`.
- `test_lines_match_code_evidence`: `complexity-lines-code` equals the sum of `code_evidence.py`'s `lines` on the fixture.
- `ergostat check` on the root model: no new finding. Unit suite rc 0, ruff clean.

## Size budget

300 net lines outside `tests/` and `docs/` (all of it in `dev/`).

From the owner's request of 2026-11-22: measure ergostat's code complexity in many forms and slices, as stocks on main, backfilled from git history.
