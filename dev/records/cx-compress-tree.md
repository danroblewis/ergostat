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
