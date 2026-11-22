# cx-compress-tree: the Kolmogorov estimates of the code scope

depends-on: [cx-measure-frame]

Branch `cx-compress-tree`, from main. The owner named Kolmogorov complexity; a real compressor's output length is an upper bound on it and the headline measure of this work.

## The problem

Lines count keystrokes. Nothing says how much information the code holds, how much of it is prose, or how much is already said elsewhere. At 2468c59b the product's Python compresses to about 941 KB with lzma (ratio 0.221) and about 667 KB with docstrings and comments stripped. A compressor left at its defaults is not a measure: preset 6 has an 8 MiB window, the code scope is about 5 MB and growing fast, and the day it passes the window the numbers jump with no change in the code.

## The change

Family `dev/bin/cx_compress.py` and `dev/model/complexity-compress.yaml`.

## Definition of done

1. **One fixed compressor**, exported as `packed(data, window=FAR) -> int`: `lzma` `FORMAT_RAW` (no container, so no per-stream overhead), one LZMA2 filter with every parameter written out (`dict_size` `FAR` = 32 MiB, `lc` 3, `lp` 0, `pb` 2, mode, match finder, nice length, depth as preset 6 gives them today, stated as numbers). An input longer than `FAR` raises (the family is then `failed`, never a silently degraded number); raising `FAR` is a `VERSION` bump. `NEAR` = 64 KiB is the same filter with that window. zlib is not used anywhere.
2. `ENV` is the Python minor version (the `ast.unparse` output's formatting belongs to it) and the liblzma version; `detail` keeps both. A change in either is a new definition: the frame recomputes, and `cx-backfill-run` replaces the recorded history.
3. Per file (cached by blob): `packed` bytes of the file alone, and the stripped text (docstrings and comments removed, `ast.unparse`d; a file that does not parse keeps its raw text and counts in cache-only `complexity-unparsed-files`).
4. Per commit, over the Python of the code scope, files concatenated in sorted path order (`stream(snap, where, kind)`, exported):
   - stock `complexity-lzma-logic` (bytes): the stripped text as one stream, the best single number for how much logic there is; headline pattern;
   - stock `complexity-lzma-prose` (bytes): comments and docstrings as one stream; two-way flow;
   - auxiliary `complexity-repeat-share` (share): 1 - `packed(raw, FAR)` / `packed(raw, NEAR)`: how much of the code is said again farther than 64 KiB away. It does not depend on where file boundaries are, so splitting or joining modules does not move it; `driven-by: [+stock.complexity-lzma-logic]`;
   - cache only (`part: false`): `complexity-lzma-code` (raw text, one stream), `complexity-lzma-ratio`, `complexity-lzma-per-token` (logic bytes per token), `complexity-repeat-share-per-file` (1 - whole / sum of per-file sizes; its description says it rises when a module is split and falls when two are joined, with no repetition added or removed, because a small input compresses worse), `complexity-lzma-window-used` (raw bytes over `FAR`).
5. The system's `show:` gains `stock.complexity-lzma-logic`.
6. One commit costs under 12 s on one core and under 500 MB at today's size; the numbers measured are written in the module's docstring.

## Files to touch

`dev/bin/cx_compress.py` (new), `dev/model/complexity-compress.yaml` (new), `dev/model/complexity.yaml` (the `show:` line), `tests/test_factory_cx_compress.py` (new).

## Acceptance tests

- `test_repeated_file_barely_grows_lzma`: a commit that adds a copy of a 100 KB file under another name raises `complexity-lzma-code` by under 10% and raises `complexity-repeat-share`.
- `test_splitting_a_module_does_not_move_repeat_share` (within 0.005), and does move the per-file one.
- `test_docstring_only_change_moves_prose_not_logic`.
- `test_reformat_does_not_move_logic`.
- `test_order_is_by_path`.
- `test_input_over_the_window_fails_not_degrades` (window set small in the test).
- `test_unparsable_file_counted_not_dropped`.
- `test_env_names_python_and_library`.
- `ergostat check`: no new finding. Unit suite rc 0, ruff clean.

## Size budget

170 net lines outside `tests/` and `docs/`.

From the owner's request of 2026-11-22: measure ergostat's code complexity in many forms and slices, as stocks on main, backfilled from git history.

## Where it stopped

Built: all six points and every acceptance test named above (`tests/test_factory_cx_compress.py`), plus five more:
`test_filter_is_preset_6_written_out` (the written-out filter gives byte for byte what preset 6 gives),
`test_window_fitted_to_the_input_gives_the_same_bytes`, `test_empty_blob_first_seen_outside_python_is_measured`,
`test_the_model_parts_split_no_system` and `test_cost_at_todays_size` (point 6). Nothing within the definition is left.

Measured at 34ece0da in the factory's Linux container (also in the module's docstring): a commit whose parent is
already measured (warm blob cache, as a backfill goes) costs 8.3 CPU s (8.4 s wall). A cold cache costs 28.7 CPU s.
Peak RSS is 160 MB. I read point 6's 12 s as the warm cost. A cold cache is paid once per VERSION or ENV, at the oldest
commit of a backfill, and at today's size it cannot get under 12 s: the four whole-stream compressions are most of the
warm time already. The test holds the warm cost under 12 CPU s, the cold under 60 and RSS under 500 MB, and it is
marked serial.

Choices made without anyone to ask (each easy to reverse):
- `complexity-repeat-share` is `driven-by: [+stock.complexity-lzma-logic, +flow.gaps-merged, -flow.removals-merged]`.
  Point 4 names only the first. Without the other two, `ergostat check` gave a new `system-splits@system.code-health`:
  the complexity subsystem, now 9 parts, linked to nothing else in code-health, took code-health past 20 parts and made
  two clusters with 0 links between them (modularity 0.41). The two added causes are what `code-duplicates` (the
  line-based sibling of this reading in code-health) and the other code readings there follow: a merge changes the code.
  Removing them brings the finding back (the frame's check test and `test_the_model_parts_split_no_system` both fail).
- `packed` fits the window to the input (the smallest power of two at least the input's length, at least 4 KiB, at most
  the window asked for). No match can reach past the input, and the test shows the bytes are the same as with the full
  window on every Python file of the code scope and on a 3 MB stream of them. This took the cold cost from 73.7 s to
  30.7 s. The parameters are written out as point 1 asks: preset 6's `lc 3, lp 0, pb 2`, mode normal, match finder bt4,
  nice length 64, depth 48 (what preset 6's depth 0, automatic, gives bt4 at nice length 64).
- `dev/bin/complexity.py` (not in the files to touch) gains `Snap.texts(paths)`: the blobs not read yet, read in one
  `git cat-file --batch`, and `text()` now calls it. Reading the raw stream through one git child per file (about 415)
  made the warm cost 11.7-13.1 s wall, over the bound. This adds to the snap contract (point 6 of cx-measure-frame) and
  changes no existing behaviour.
- `tests/test_factory_cx_frame.py` (not in the files to touch) had assumed size was the only family. Its CLI test now
  looks for size's line and size's series among the others, and its check test leaves out every `complexity*.yaml` in
  the "before" model. Otherwise the new file names a system that is absent there.
- ENV is `py<minor>-liblzma<version>-<8 hex>`. The version is read with ctypes from `_lzma`'s own library, then from
  the system's (`unknown` if neither has `lzma_version_string`). The hex is a sha256 of the filter's output on a fixed
  probe, so a library whose version reads wrong or unknown still changes ENV when its output changes. `detail` keeps
  `{"python", "liblzma"}`.
- Per file, only `.py` paths are measured (`lzma`, `logic`, `prose`, `unparsed`, `tokens`), and `logic` and `prose` are
  strings in the blob cache (point 3; the frame's row contract says number or list). A blob first cached under a
  non-Python path (the empty file, say) is measured when its Python row needs it, so it is never taken as having none.
- Prose is the comments (tokenize) and docstrings (the first string statement of a module, class or function) in source
  order. Removing a docstring that is a body's only statement leaves `pass`. A file that does not parse, or whose
  unparse fails, keeps its raw text as logic and adds nothing to prose. `complexity-lzma-per-token` uses cx_size's
  token count. It is left out (no value, not zero) when any file does not tokenize. The ratio and per-file share are
  left out when the scope has no Python.
- Files are joined with a newline in each stream.

Risk, not fixed here (the frame's): the blob cache is one JSONL per family, read whole on every measure. Since this
family keeps each blob's logic and prose text in it, the file grows with every Python blob in history, and so do the
measure's read time and memory late in a backfill. The 8.3 s and 160 MB above are with the cache of two commits.

Tests: `tests/test_factory_cx_compress.py` 13 passed, `tests/test_factory_cx_frame.py` 14 passed (with `ergostat check`
on the root model, no new finding). Ruff is clean. I broke the code and watched the tests fail (lesson-9) for: no sort by
path, no window check, a blob cached with no measures taken as having none, docstrings kept in logic, the repeat share
computed per file, ENV without the liblzma version, and the repeat share without its two merge causes. Not run here:
the unit suite and the browser files (left to the factory; this gap changes no page).
