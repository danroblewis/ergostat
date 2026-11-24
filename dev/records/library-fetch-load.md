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

## Where it stopped

Round 1: built. Every definition-of-done item is in the code, and the six named acceptance tests and one extra test pass. Net size is 238 lines outside `tests/`, `docs/` and `dev/` (counted with `git diff --numstat main`, schema included), within the 240 budget. `main` has not moved since the clone, so merging it is a no-op. The branch is two commits over main.

What was built:
- `spec/load.py`: `libraries` in TOP, kept on `Document.libraries`, `libraries-in-include` outside the main file. `schema/ergostat.schema.json`: a `libraries` entry of `git`, `version`, `path` and `trust`.
- `ergostat/cli/library.py`: `ergostat library fetch [NAME...] [--update]`. It reads the main file with `load.read_file` (the loader's own YAML reader) and takes `libraries:` only. Any YAML error stops it with rc 2 before git runs. It never opens a Project or the fallback, and `library` is not in `goodmodel.READS`.
- `ergostat/library/fetched.py`: `split` takes `trust:` (owner or untrusted) out of each entry, then runs `sources.check`. `add` checks each library in turn and refuses by name with `library-unlocked`, `library-lock-unreadable`, `library-missing` or `library-altered`. Each refusal is an error at its `libraries:` line (fails closed), and none of that library's templates load. Templates are parsed from the bytes of the one `files.tree` walk that was hashed. Untrusted notes go through `ut.note`, as `find_all` does it.
- `spec/files.py`: `Reads.trees` (path to `[kind, hash or target]`) and `Reads.blobs`. While noting, `files.tree` notes the listing. On replay it answers from `trees` alone (each file's bytes by hash, checked), and a copy not in `trees` is still `NotKept`. `goodmodel.keep` writes `"trees"` and the tree blobs.
- `library/tree.py`: `of(walked)`, the digest of a listing already walked. `digest(root)` is now `of(files.tree(root))`.
- `uses.py`: calls `fetched.add` after `find_all`. `unknown-template` lists each refused library as `library NAME (CODE: why)`. The refusal text has a `trust: owner` branch when `u.library` is set.

Decisions taken alone (each the most reversible choice):
- I touched `spec/files.py` and `library/tree.py`, which are not in the Files list. Without them, `trees` could not be noted and replayed, and the hashed listing could not be the one parsed. The changes are small and keep the old behaviour of each function.
- Fetched libraries load lazily, with the templates (`uses.library`). A model with no `uses:` never checks `libraries:`, so `check` does not report a bad lock there. Nothing from the copy enters such a model either.
- Precedence: a fetched template never displaces a template already found (folders, `$ERGOSTAT_LIBRARY`, ergostat's own). The one exception is a trusted fetched template over an untrusted one. Either way the skipped one is named in a note, marked when it is untrusted.
- A `library-altered` reason carries only the TreeError code or strerror, never a path inside the copy, so no library-chosen text reaches the message unmarked.
- Not done, and left in GAPS: the MCP `templates` tool (`author.library`) still lists folders only, not fetched libraries.

Answers to the plan-review notes:
1. Not ported. There is no outright refusal: a fetched template reaches `under = under or (...)`, and `trust.refused` and the bounds handle it. The test shows a structure-only use expanding with `untrusted: True`, and a program-block use refused `library-untrusted`.
2. Marked with `ut.note(copy, ...)`, exactly as `find_all` does. `test_untrusted_fetched_goes_through_gate` asserts that the broken template's note starts `untrusted library folder .../.libraries/shared: ⟦untrusted: library file⟧`.
3. Done: when `u.library` is set, the text says "from the fetched library NAME, not marked trust: owner in libraries: ... Only the owner can mark it trust: owner". The test asserts it.
4. `test_unlocked_treeless_missing_refused` checks, for every case, that `unknown-template` contains `library shared (CODE:`.
5. Done. The test deletes `.libraries` and `libraries.lock`, runs `status` (rc 0, from the last good model), and asserts the replayed model still holds the `c1` stocks. Dropping `"trees": r.trees` from `goodmodel.keep` makes it fail: keep's own read-back says `NotKept: .../.libraries/shared: a library copy not in the last good model's snapshot`.

Each test was broken on purpose and seen to fail (lesson-9), then the code was restored to the commit:
- `trees` dropped from keep: `test_fetch_off_fallback_and_replay` fails.
- `git` left out of the lock comparison: `test_changed_git_alone_unlocked` fails.
- Template parsed from disk instead of the hashed bytes: `test_parses_bytes_it_hashed` fails.
- Untrusted note unmarked: `test_untrusted_fetched_goes_through_gate` fails.
- Refused libraries dropped from `unknown-template`: `test_unlocked_treeless_missing_refused` fails.
- Digest check skipped: `test_altered_copy_and_link_refused` fails.

Tests run, each through `scripts/named_tests.py`, all passing:
- `tests/test_library_fetch_load.py`: 7.
- `test_library_tree`, `test_library_fetch_git`, `test_cli_fallback`: 37.
- `test_spec_schema`, `test_library_untrusted`, `test_library_trust`: 110.
- `test_templates`, `test_library_provenance`, `test_spec_structure`: 102.
- `test_item_graph_queries`, `test_cli_fallback`: 31.
- `ruff check ergostat tests scripts`: clean.

Not run here, as the rules say: the whole unit suite, the four browser files and `demo_check`. No page and no example changed.

### Round 2: the merge of main (59600738), and docs/GAPS.md

**The merge.** Main had landed `library-fetch`: its own `fetched.py` (an eager `take` at load, `Document.fetched` and
`Document.refused`), `cli/library.py`, `files.tree` noting `trees` with each file in `Reads.files`, `tree.hashed`,
the `libraries` schema entry, and SPEC §2a and SECURITY text for fetch, the lock and the four error codes. That covers
most of this definition, so I resolved every conflicted file (`cli/library.py`, `goodmodel.py`, `fetched.py`,
`templates.py`, `tree.py`, `uses.py`, `spec/files.py`, `spec/load.py`, the schema) to main's text. On top of main,
the branch keeps only what this definition asks and main lacks:
- `uses.py`: main's outright refusal (`library-untrusted`, "listed, never expanded") is removed, so an untrusted
  fetched template reaches `under = under or (...)` and is held, allowlisted and bounded as an untrusted folder's is
  (plan-review note 1). The refusal text's `trust: owner` branch for a fetched library stays (note 3).
- `fetched.py`: a template of an untrusted fetched library that does not parse is noted through `ut.note(copy, ...)`,
  as `find_all` does for an untrusted folder (note 2). `_lock` also takes `RecursionError` (deeply nested JSON) as
  `library-lock-unreadable`; before, it escaped load as a crash (lesson 3). The test has a case for it.
- Taken from main where the branches differed, each reversible: `trust:` is only `owner` (round 1 also allowed
  `untrusted`, which is the same as leaving it out); fetched libraries are checked at load, not lazily with the
  templates; and the `unknown-template` text is main's `library NAME refused: CODE, why`.
- `cli/__init__.py`: the merge had registered the `library` topic twice (argparse refused it); main's file is kept.
- Docs: the branch's own SPEC §2a, SECURITY and agent-guide paragraphs duplicated main's, so they are dropped. Main's
  "listed, never expanded" sentences (SPEC §2a, the §error-code list, SECURITY) now say the library is untrusted
  exactly as a folder is, and SPEC says `trees` keeps the listing for the fallback.
- `tests/test_library_fetch.py::test_untrusted_use_refused` (main's) pinned the refusal this definition forbids. It is
  now `test_untrusted_use_through_the_gate`: the structure-only use expands, marked `untrusted`, and is still listed.
  `tests/test_library_fetch_load.py` changes only the expected `unknown-template` text, `sources.check` for the old
  `fetched.split`, and the new lock case.

**docs/GAPS.md** is main's again (`git restore --source=MERGE_HEAD`, the same commit as 59600738). The entry is the
`## Entry` below, a sub-gap of `shared-libraries`. In `dev/records/shared-libraries.md`, the umbrella's "listed, its
templates never expanded" and its *Still needed* "the provenance gate and the sandbox for fetched libraries" are
replaced: fetched untrusted libraries now go through the gate, and what is left is a test that a fetched copy's
sensor run goes through the sandbox.

**Seen to fail with the guard removed (lesson 9)**, each applied, run and reverted:
- the untrusted parse note unmarked: `test_untrusted_fetched_goes_through_gate` fails;
- `RecursionError` not caught: `test_unlocked_treeless_missing_refused` fails with the `RecursionError`;
- main's outright refusal put back: `test_untrusted_fetched_goes_through_gate` and
  `test_library_fetch.py::test_untrusted_use_through_the_gate` fail;
- `"trees"` dropped from `goodmodel.keep`: `test_fetch_off_fallback_and_replay` fails (`NotKept`).

**Tests run after the merge**, each through `scripts/named_tests.py`, all passing:
- `test_library_fetch_load`, `test_library_fetch`, `test_cli_fallback`: 47;
- `test_library_untrusted`, `test_library_trust`, `test_library_provenance`: 125;
- `test_templates`, `test_spec_schema`, `test_spec_structure`: 88;
- `test_library_fetch_git`, `test_library_tree`, `test_modelling_template`: 25.
- `ruff check ergostat tests scripts`: clean.

Not run here: the whole unit suite, the four browser files (no page changed) and `demo_check` (no example touched).
One command form was refused: `git checkout --theirs -- FILES`; `git restore --source=MERGE_HEAD --worktree -- FILES`
did the same.

Size: `git diff --numstat main -- ergostat schema` gives 12 added and 10 removed, 2 net against main, within 240.
The rest of what round 1 built is now on main through `library-fetch`.

## Entry

entry-of: shared-libraries
done: 2026-11-23 A fetched library without `trust: owner` goes through the same trust and provenance gate as an untrusted folder (held, allowlisted, bounded, its notes marked), instead of being refused outright; a refused library is named with its code in `unknown-template` (`library-fetch-load`).
