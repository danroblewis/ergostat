# remote-systems: the Remote systems entry says what is built, once, and hands the IR serving to the IR's entry

depends-on: []

## Definition of done
- Everything the gap can build today is on main: the read-only remote API, `remotes:`, source `ergostat`, its findings, drawing, the CLI, proposals text, box measures, a remote of remotes (`via`, imported parts served), mTLS, process lines, and the Items and Record pages read in place (`remote-items-record`). The one piece left, serving the IR beside `ergostat-model/1` (`?format=ir`), needs an IR that does not exist (the IR entry is open, waiting on the owner). So this gap builds no code. It ends the splice and the stale "open" state.
- In `docs/GAPS.md`, *Remote systems* appears once. Its head's first clause begins with `done`, so `dev/bin/intake.py` `gaps_md` says `done` and `twice` does not name it. It has one *Done* clause, each sub-gap's sentence in it once (box measures, remote of remotes, mTLS, process lines, items and record). It has no *Left* clause, or one that only points to the IR entry. There is no dangling fragment, and nothing says the Items/Record pages or a remote composed of remotes is left.
- *The IR and a Rust runtime* entry carries, as one of its own items, serving the IR on `/remote/v1/model?format=ir` beside `ergostat-model/1` (SPEC §4c, `docs/proposals/remote-systems.md`).
- `docs/proposals/remote-systems.md` "Left for later" no longer lists the event cache feeding the Items and Record pages. It says that landed (`remote-items-record`) and leaves only the IR.
- `dev/records/remote-systems.md` holds an `## Entry` section in the shape `dev/prompts/definition.md` shows (`section: Remote systems and libraries`). `dev/bin/gapsdoc.py` parses it with no problem reported, and its bullet is the same text as the GAPS.md entry.
- Every path the entry cites exists, and every commit it cites is on main.

## Relation to other work
- merge-pipeline-gaps-intake-reads-records: builds before it. The record's Entry section is the one that gap's intake will read, so it must parse with gapsdoc as it is now.
- merge-pipeline-gaps-deps-read-records: same. The Entry has no `entry-of:`, because Remote systems is the umbrella.
- The IR and a Rust runtime (open, no branch yet): this gap hands it the remote IR serving and does not touch its code.

## Files to touch
- `docs/GAPS.md`
- `docs/proposals/remote-systems.md`
- `dev/records/remote-systems.md` (new)
- `tests/test_gaps_doc.py`

## Risks
- lesson-7: a later merge of main splices the entry again. The tests read the merged file, so a splice (a second *Left*, a duplicated sentence) fails them after the merge of origin/main.
- lesson-8: the entry says "done" more widely than main supports, for example claiming imported parts are served or the Items/Record pages are read in place. Each Done sentence names a branch whose tests exist (`tests/test_remote_items.py`, `tests/test_remote.py`). The test checks that those cited paths exist.
- lesson-9: tests that pass on the spliced file. Each test must be seen to fail on the current main text, which has two *Left* clauses, the "first slice" head and the duplicated mTLS sentence. Say so in the report.

## Acceptance tests
- `tests/test_gaps_doc.py::test_remote_systems_entry_is_found_done_by_intake`: `intake.gaps_md` lists *Remote systems* once with `gaps_says == "done"`, and `intake.twice` does not name it. It fails on main's current head ("first slice done").
- `tests/test_gaps_doc.py::test_remote_systems_entry_has_one_done_and_no_stale_left`: one `*Done*`, at most one `*Left*`, and any *Left* names only the IR. Each of `remote-box-measures`, `remote-of-remotes`, `remote-mtls`, `remote-process-lines` and `remote-items-record` appears exactly once. It fails on the spliced text.
- `tests/test_gaps_doc.py::test_ir_entry_holds_remote_ir_serving`: the *The IR and a Rust runtime* entry names `format=ir` and `ergostat-model/1`.
- `tests/test_gaps_doc.py::test_remote_systems_record_entry_matches_gaps_md`: `gapsdoc.parse` of `dev/records/remote-systems.md` reports no problem, gives section *Remote systems and libraries*, and gives a bullet equal to the GAPS.md entry's lines.
- `tests/test_gaps_doc.py::test_remote_systems_entry_cites_only_paths_and_commits_that_exist`: every backticked path in the entry exists, and every hash (`72da4e1`) is an ancestor of the main ref.

## Size budget
0 net lines (docs, the gap's record and tests only; no code outside `tests/` and `docs/`)
size: S (confidence: high)

## Entry

section: Remote systems and libraries

- **Remote systems** (done, 72da4e1, merged from `remote`, and the sub-gaps below; only serving the IR is left,
  an item of *The IR and a Rust runtime*; `docs/proposals/remote-systems.md`, SPEC §4c): a system run by
  another ergostat instance, composed into a local model. Its model is served by the remote instance and changes
  while it runs; its event log and metrics are queried where they live; its agents run on the remote machine,
  never locally. The local model reads it, links to its parts, and draws it as a subsystem; it never runs it.
  (Owner, 2026-11-18.)
  - *Done*: the read-only remote API on every page server (`/remote/v1/`: status, model with
    version and ETag, events by cursor, items, counts, readings, series, process; bearer tokens per consumer,
    hashed at rest, rate-limited); `remotes:` in the YAML (fetched, cached, refreshed on `every:` and when a
    reading says the version moved; parts brought in as an external subsystem, blocks never run, sensors
    reading the remote, `systems:` to narrow); source type `ergostat` (one batched request per remote a
    period, stale readings refused); local references checked against the remote's current model
    (`remote-reference-unresolved` with a stand-in, `remote-output`, `remote-unreachable`, `remote-stale`,
    `remote-insecure`); drawn in Dynamics, Blocks and Process, marked remote with version and age;
    `ergostat remote` (status, token, events, refresh); edits to remote parts refused; the demo
    `examples/remote-pair/` and its two-instance test (`tests/test_remote.py`, `tests/test_remote_pair.py`); a
    parameter estimate or an equation for one remote's parts written as text for its owner, in its names,
    against the version read, never applied or sent (`remote-proposals-text`; `ergostat remote proposals`,
    SPEC §4c "Proposals for its owner"; `tests/test_remote_proposals.py`). A remote's measures on its closed box
    (done on `remote-box-measures`, `tests/test_remote_box_measures.py`): its top systems' served `show:`, or a
    `show:` on its `remotes:` entry in its own names (`remote-show-unresolved` for one it does not serve), each
    marked stale with its age when the remote or the reading is not current. A remote composed of remotes
    (done on `remote-of-remotes`, `tests/test_remote_chain.py`): its imported parts served on with instance
    ids and each part's `via` chain, cycles cut, depth (3), parts (2,000), via length (8) and answer size
    (16 MB) capped, local names winning, and readings served on with their age at the origin. Mutual TLS (done
    on `remote-mtls`, `tests/test_remote_mtls.py`): `web: mtls:` serves the remote API alone on its own
    listener (16 connections, 10 s handshake and idle, GET of `/remote/v1/` only, the token still needed) to
    certificates `client-ca` signed; a `remotes:` entry's `tls:` reads it (`mtls-unreadable`). Lines in the
    process map between our items and theirs (done on `remote-process-lines`, `tests/test_remote_lines.py`): a
    relation may name a remote's kind (`blocked_by: incidents-incident`, never precedence); the remote says the
    step each named item was last at (`at=`, at most 200 ids, chosen by id), and a link not drawn is counted by
    its reason (`unlinked`), never dropped. A remote's items in the Items page and its events in the Record
    page (done on `remote-items-record`, `tests/test_remote_items.py`): `remote=NAME`, read in place within 8
    requests a remote a period, failing closed.
  - *Left*: only serving the IR beside `ergostat-model/1` (`?format=ir`), once the IR exists; it is an item
    of *The IR and a Rust runtime*.
