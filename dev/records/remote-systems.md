## Entry

section: Remote systems and libraries

- **Remote systems** (first slice done, 72da4e1, merged from `remote`; what is left below is open;
  `docs/proposals/remote-systems.md`, SPEC §4c): a system run by
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
    (`remote-reference-unresolved` with a stand-in, `remote-output`, `remote-unreachable`,
    `remote-insecure`); drawn in Dynamics, Blocks and Process, marked remote with version and age;
    `ergostat remote` (status, token, events, refresh); edits to remote parts refused; the demo
    `examples/remote-pair/` and its two-instance test; a parameter estimate or an equation for one remote's
    parts written as text for its owner, in its names, against the version read, never applied or sent
    (`remote-proposals-text`; `ergostat remote proposals`, SPEC §4c "Proposals for its owner"). A remote's
    measures on its closed box (done on `remote-box-measures`): its top systems' served `show:`, or a `show:`
    on its `remotes:` entry in its own names (`remote-show-unresolved` for one it does not serve), each marked
    stale with its age when the remote or the reading is not current. A remote composed of remotes (done on
    `remote-of-remotes`): instance ids, each served part's `via` chain, cycles cut, depth (3), parts (2,000),
    via length (8) and answer size (16 MB) capped, local names winning, and readings served on with their age
    at the origin. Mutual TLS (done on `remote-mtls`): `web: mtls:` serves the remote API alone on its own
    listener (16 connections, 10 s handshake and idle, GET of `/remote/v1/` only, the token still needed) to
    certificates `client-ca` signed; a `remotes:` entry's `tls:` reads it (`mtls-unreadable`). Lines in the
    process map between our items and theirs (done on `remote-process-lines`): a relation may name a remote's
    kind (`blocked_by: incidents-incident`, never precedence); the remote says the step each named item was
    last at (`at=`, at most 200 ids, chosen by id), and a link not drawn is counted by its reason
    (`unlinked`), never dropped.
  - *Left*: the remote's events in the Items and Record pages (the cursor cache exists, only the CLI reads
    it); serving the IR beside `ergostat-model/1` once it exists.
    measures on its closed box (done on `remote-box-measures`): its top systems' served `show:`, or a
    `show:` on its `remotes:` entry in its own names (`remote-show-unresolved` for one it does not serve),
    each marked stale with its age when the remote or the reading is not current. Mutual TLS (done on
    `remote-mtls`): `web: mtls:` serves the remote API alone on its own listener (16 connections, 10 s
    handshake and idle, GET of `/remote/v1/` only, the token still needed) to certificates `client-ca` signed;
    a `remotes:` entry's `tls:` reads it (`mtls-unreadable`). Lines in the process map between our items and
    theirs (done on `remote-process-lines`): a relation may name a remote's kind (`blocked_by:
    incidents-incident`, never precedence); the remote says the step each named item was last at (`at=`, at
    most 200 ids, chosen by id), and a link not drawn is counted by its reason (`unlinked`), never dropped. A
    remote's items in the Items page and its events in the Record page (`remote=NAME`), read in place within 8
    requests a remote a period, failing closed (`remote-items-record`).
  - *Left*: serving the IR beside `ergostat-model/1` once it exists; a remote that is itself composed of
    remotes (its imported parts are not served).
