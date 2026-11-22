# repair-traces-more: triage reads Ruby traces and finds a Python traceback that starts before the 8,000-character tail
depends-on: []

## Definition of done
- **Ruby traces:**
  - `traces.last` also reads Ruby. A header line `path:N:in 'meth': message (Type)` (the older backtick-quote form too) is directly followed by zero or more `\tfrom path:N:in ...` lines. The frames are innermost first.
  - Project frames follow the existing project-frame rule, with `vendor`/`gems` paths treated as library paths. A Ruby failure is signed like the other languages.
  - Its old `(block, program, how)` item is superseded by the existing rule 6: only when its kept stderr parses to the same signature, and only from noted or open.
- **Long Python tracebacks:**
  - When a failed run's tail ends in a Python exception line but holds no `Traceback (most recent call last):` header, capture reads at most the last 64,000 characters of that run's own file. This is the file `data["log"]` names, never the block log.
  - It signs the run from the last Python traceback found there that runs to the end. A failure signed this way supersedes its old how-signed item by the same rule.
  - No file, or a file that cannot be read, means the run is signed by how it ended, as now.
- **What is still not done:**
  - What a daemon swallows is still not seen (one stream for all its runs).
  - A program with uncommitted changes stays refused and is left to a person, as SPEC §12r already says.
- **Docs:**
  - GAPS' Repair *Left* is rewritten to say the three points above, and drops the 8,000-character limit and "Ruby".
  - The uncommitted-changes wording in *Left* is corrected to match the code ("left to a person", not "fixed from its committed text").
  - SPEC §12r names Ruby and the 64,000-character read.

## Relation to other work
- repair-log-events: both touch `capture.py`; this branch adds only the long read and the Ruby supersede path.

## Files to touch
- `ergostat/repair/traces.py`
- `ergostat/repair/capture.py`
- `tests/test_repair_traces_more.py` (new)
- `docs/SPEC.md`
- `docs/GAPS.md`

## Risks
- lesson-3: an unreadable or missing run file must fall back to how the run ended, never to an empty trace.
- lesson-4: the longer read is capped at 64,000 characters.
- lesson-5: newly signed Ruby and long-Python failures would strand their old how-signed items unless they are superseded.

## Acceptance tests
- `tests/test_repair_traces_more.py::test_ruby_trace_innermost_project_frame`: a Ruby trace with gem frames is signed at the innermost project frame, in both quote forms.
- `tests/test_repair_traces_more.py::test_ruby_supersedes_old_item_only_on_same_signature`: an old open item with the same parsed stderr is dismissed; one with other stderr is left alone.
- `tests/test_repair_traces_more.py::test_long_python_traceback_read_from_run_file`: a traceback starting 20,000 characters before the end is signed by its frame. One starting 70,000 characters back is signed by how the run ended.
- `tests/test_repair_traces_more.py::test_missing_run_file_signs_by_how`: an absent or unreadable run file gives the how-signature, and no exception is raised.
- `tests/test_repair_traces_more.py::test_never_reads_block_log`: another run's traceback in the block log is not used.

## Size budget
100 net lines
size: M (confidence: medium)
