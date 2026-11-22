# repair-log-events: error-level log events in a good run's output are noted as swallowed failures, never opened
depends-on: []

## Definition of done
"Log events" (Repair *Left*) is taken here to mean errors a program logged without failing. Nothing on main defines it further.
- **What counts as an error log event.** After a run that ended well, when `traces.last` finds no trace through the project's code, the run's tail (its own run file, last 8,000 characters) is read for error-level log events. The last such line in the tail is the one used. Two forms count:
  - Python logging's default form, `ERROR:logger:message` or `CRITICAL:logger:message`;
  - a JSON line whose `level`, `levelname` or `severity` is error, critical or fatal (in any case), with `logger`/`name` and `message`/`msg`.
- **How it is recorded:**
  - It is recorded through the existing swallowed path as `ergostat.run.swallowed`, signed `(block, program, "log", level, logger)`.
  - A new failure arrives `noted` and is never opened. An existing failure gets counts only, so no failure is moved or unleased.
  - Its error is the scrubbed message (at most 300 characters).
- **What is not changed:**
  - A trace always wins over a log line.
  - A failed run's signature is unchanged, so no existing ids move.
  - Lines that are not error-level, malformed JSON, and lines over 8,000 characters are ignored.
- **Docs:** SPEC §12r says what is read and that this is an interpretation. GAPS drops "log events" from *Left*.

## Relation to other work
- repair-traces-more: both touch `capture.py`; this branch adds only the log reader and its call in `swallowed`.

## Files to touch
- `ergostat/repair/traces.py`
- `ergostat/repair/capture.py`
- `tests/test_repair_log_events.py` (new)
- `docs/SPEC.md`
- `docs/GAPS.md`

## Risks
- lesson-5: an existing failure of the same signature must get counts only, never fields that would overwrite its traceback or lease.
- lesson-8: the SPEC claim names only the two forms read; any other logging format is said to be unread.

## Acceptance tests
- `tests/test_repair_log_events.py::test_python_and_json_error_lines_noted`: each form makes one noted failure with the stated signature, and it is never opened.
- `tests/test_repair_log_events.py::test_info_and_bad_json_ignored`: INFO/WARNING lines and malformed JSON make no event.
- `tests/test_repair_log_events.py::test_trace_wins_over_log`: a project trace plus an ERROR line in the same tail is signed by the trace.
- `tests/test_repair_log_events.py::test_existing_leased_failure_untouched`: a leased failure at that signature keeps its state, lease and traceback, and gains only `swallowed`.
- `tests/test_repair_log_events.py::test_failed_run_signature_unchanged`: a failed run with an ERROR line and no trace keeps its `(block, program, how)` id.

## Size budget
80 net lines
size: M (confidence: medium)
