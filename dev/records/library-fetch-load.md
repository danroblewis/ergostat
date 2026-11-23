# library-fetch-load: `ergostat library fetch`, and a model loading fetched libraries only as locked, with untrusted ones behind the same gate as untrusted folders
depends-on: [library-fetch-git]

## Definition of done
- `libraries:` is allowed only in the main file (`libraries-in-include` otherwise) and is in the schema.
- `ergostat library fetch [NAME...] [--update]` reads only `libraries:` with the loader's YAML reader. It never opens the project or the fallback, and `library` is not in `goodmodel.READS`. An unparsable file gives rc 2 with no git run.
- Load (`ergostat/library/fetched.py`) checks each library in turn. No lock, or no entry, or an entry with no `tree` or `commit`, or one whose `git`/`version`/`path` differ, is `library-unlocked`. A bad lock is `library-lock-unreadable`. A missing copy is `library-missing`. A hash mismatch, a wrong kind or a size over a cap is `library-altered`. Templates are parsed from the same bytes that were hashed. The listing is kept in the good model's snapshot (`trees`), so the fallback replays it without walking the disk.
- A fetched library with `trust: owner` is trusted. Any other fetched library is untrusted exactly as an untrusted `library:` folder is: it passes the trust and provenance gates and is marked, and it is not refused outright.
- When a use names a missing template, the `unknown-template` message lists each refused library and the reason.
- SPEC §2a, SECURITY and GAPS describe fetch, the lock and the error codes. The claims are only that the copy is checked at load, and that a script run from `${here}` is read again when it runs.

## Relation to other work
- library-fetch-git: waits for it.
- library-model-text-marked and library-sandbox-sensors-proven: fetched untrusted libraries get their marking and sandboxing through the untrusted flag.
- ir-read-back and ir-control-document both touch `spec/` loading. This sub-gap changes only the library hook in `spec/load.py`.

## Files to touch
- `ergostat/library/fetched.py` (new)
- `ergostat/cli/library.py` (new)
- `ergostat/cli/__init__.py`
- `ergostat/library/templates.py`
- `ergostat/library/uses.py`
- `ergostat/spec/load.py`
- `ergostat/goodmodel.py`
- `schema/ergostat.schema.json`
- `docs/SPEC.md`
- `docs/SECURITY.md`
- `docs/GAPS.md`
- `tests/test_library_fetch_load.py` (new)

## Risks
- lesson-3: a missing lock, a missing entry, an entry without a tree or an unreadable lock must each refuse by name, never load the copy on disk.
- lesson-5: a changed `git:` alone must not reuse the old lock entry.
- lesson-7: a new CLI topic must stay off the read-only fallback, and `trees` must survive replay.

## Acceptance tests
- `tests/test_library_fetch_load.py::test_unlocked_treeless_missing_refused`: the copy deleted, the lock deleted, the entry removed, the entry without `tree`, and invalid JSON each refuse with their code, and the template is unavailable.
- `tests/test_library_fetch_load.py::test_changed_git_alone_unlocked`: changing only `git:` gives `library-unlocked`.
- `tests/test_library_fetch_load.py::test_altered_copy_and_link_refused`: one changed byte, `chmod +x` or a retargeted link gives `library-altered`.
- `tests/test_library_fetch_load.py::test_parses_bytes_it_hashed`: a description rewritten on disk after the walk is not what loads.
- `tests/test_library_fetch_load.py::test_untrusted_fetched_goes_through_gate`: an untrusted fetched library's structure-only use expands and is marked. Its use with a `command` block is refused `library-untrusted`.
- `tests/test_library_fetch_load.py::test_fetch_off_fallback_and_replay`: fetch on unparsable YAML gives rc 2 with no git run and no fallback. `status` on the last good model works with the copy deleted.

## Size budget
240 net lines
size: L (confidence: low)

## Notes from the plan review (answer each)

- The parked branch's ergostat/library/uses.py (origin/factory/library-fetch, inside plan() right after the unknown-template branch) adds `if t.library and not tp.trusted(t): return err(... 'listed, never expanded', 'library-untrusted')`. That is exactly the outright refusal this plan's definition of done forbids. Do not port that hunk. Let the template reach `under = under or (...)` at uses.py:122 so trust.refused and bounds.untrusted_part handle it the way they handle an untrusted folder.
- In the parked fetched.py `_one`, a TemplateError from an untrusted fetched library becomes `Problem('finding', f'library {name}: {x}', ...)` with the library's own text unmarked. find_all wraps the same case for an untrusted folder in `ut.note(...)` (templates.py). An untrusted fetched library must get that same marking, or it is not 'exactly as' an untrusted folder. Mark it the same way and add one assertion for it to test_untrusted_fetched_goes_through_gate.
- The refusal text at uses.py:73-75 says 'from {u.path.parent}, a library folder not marked trusted ... Only the owner can mark a folder trusted'. For a fetched library the fix is `trust: owner` in libraries:. Say so when `u.library` is set; a one-line branch is enough.
- The definition of done says the unknown-template message lists each refused library and its reason, but no acceptance test names it. Assert it in test_unlocked_treeless_missing_refused: use the template from a refused library, then check the unknown-template message names the library and its code.
- In test_fetch_off_fallback_and_replay, also delete libraries.lock before running status, and assert that the replayed model still has the fetched template. Then break it on purpose: drop `"trees": r.trees` from goodmodel.keep and show the test fails, so it is proven to pin the snapshot field.
