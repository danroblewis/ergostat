# conformance-list-files: Conformance lists: a list file read and validated, every limit refused by name

depends-on: []

# conformance-list-files: a conformance list file is read and validated, and a bad one is refused by name



The owner (2026-11-21) wants the features we wish we had listed, each tested, and the passing count kept as a stock. docs/proposals/conformance-stock.md section 1 defines the list file: `list`, `description`, `cases` (each with `check`, `timeout`, `asked`, `from`, `description`). Its limits are names matching `^[a-z0-9][a-z0-9-]{0,63}$`, at most 500 cases in a list, at most 20 lists and 500 cases across one use, a timeout of at most 10m (default 1m), and each list's `list:` equal to its file name. Nothing on main reads such a file. The only list of cases today is hand-written inside one demo's runner (`examples/image-squeeze/world/bench.py:43-60`), and the library's programs live in `ergostat/library/run/` (`ergostat/library/run/__init__.py:1-17`). Every later conformance gap (the runner, ergostat's three lists) needs one reader that says yes or no in the same way. Proposal section 2, step 1: if any named list cannot be read, the run stops and no case moves.

## Change
A small, pure module `ergostat/library/run/conformance_lists.py`:
- `read(folder, names) -> Lists`: reads `<folder>/<name>.yaml` for each name, in order. It raises `ListError(name, why)` on the first problem.
- `Case(list, name, id, check, timeout_s, asked, from_, description)`, with `id = case/<list>/<name>`.
- `Lists.cases` (in file order), `Lists.declared` (the count) and `Lists.digest` (a sha256 over the files' bytes in name order, which the runner uses to tell an edited list).
- It never touches the model loader: lists are not model files.

## Definition of done
1. `read` returns every case of every named list, in order, with defaults filled in (`timeout` 1m, `asked` true).
2. Each of these is refused with the list's name and a reason naming the key: a missing file; YAML that is not a mapping; `list:` not equal to the file name; a name repeated in `names`; a list or case name off the pattern; a case without `check`; a timeout unparseable or over 10m; `asked` not a bool; an unknown key; more than 500 cases in one list; more than 20 lists; more than 500 cases across them.
3. Durations are parsed by `ergostat.durations.parse_duration`, not by a new parser.
4. `digest` changes when any named file's bytes change, and not when a file outside `names` changes.
5. The module imports nothing from `ergostat.spec` beyond durations, and is under 140 lines.

## Files to touch
`ergostat/library/run/conformance_lists.py` (new), `tests/test_conformance_lists.py` (new).

## Risks
- lesson-3: a list that cannot be read must stop the run, never read as a list with no cases. `read` raises; it never returns a partial `Lists`.

## Acceptance tests
- test_reads_two_lists_in_order_with_defaults
- test_missing_list_file_refused_by_name
- test_list_name_must_match_file_name
- test_name_repeated_in_names_refused
- test_case_name_off_pattern_refused
- test_timeout_over_ten_minutes_refused
- test_unknown_key_refused
- test_list_over_500_cases_refused
- test_more_than_20_lists_refused
- test_500_cases_across_lists_refused
- test_digest_moves_only_with_named_files

## Size budget
At most 140 net lines outside `tests/`.

Area: conformance. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.
