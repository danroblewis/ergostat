# Known gaps

What ergostat is known to lack, kept current as work lands. Each entry says where it came from and its
state: **open**, **in progress** (with the branch), or **done** (with the commit, then removed at the next
review into *Done recently*). Newest decisions from the owner first within each section. Last reviewed 2026-11-18.

## Remote systems and libraries

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
    requests a remote a period, failing closed. A remote's parts are data here (done on
    `remote-and-libraries-remote-parts-are-data`, `tests/test_remote_analysis.py`): its stocks given, never
    integrated, in the replay and the projection (open and closed loop), and left out of the fit's total (listed
    under `remote`), the residuals and the not-exercised findings; its flows' equations still serve the texts
    for its owner.
  - *Left*: only serving the IR beside `ergostat-model/1` (`?format=ir`), once the IR exists; it is an item
    of *The IR and a Rust runtime*.

## Runtime, scale and latency

- **The IR and a Rust runtime** (open; `docs/proposals/ir-and-runtime.md`, 12 questions for the owner). One of
  its items, handed over by *Remote systems*: serving the IR on `/remote/v1/model?format=ir` beside
  `ergostat-model/1` (SPEC §4c, `docs/proposals/remote-systems.md`).

## Done recently

- **From upkeep's fault injection** (done on main; found by upkeep's fault injection,
  `docs/roadmap/overnight-2026-11-19.md` at 01:30, whose proposal was not merged to main): the first four problems
  from `resilience-core` (`docs/roadmap/overnight/resilience-core.md`, tests in `tests/test_resilience.py`), the fifth
  from `cli-fallback` (`docs/roadmap/overnight/cli-fallback.md`, tests in `tests/test_cli_fallback.py`).
  - **Nothing restarts a dead engine; `status` shows a dead engine's last reading as alive** (3e106ee:
    `ergostat run --service [--install]`, the outer watcher; "engine not running (last seen ...)").
  - **The watchdog restarts without finding the cause; a hang while starting is unseen; a wedged pool is found
    late** (3e106ee: the index lock's holder dumped; restarts that did not help back off; a startup deadline).
  - **An `alarm` block lights nothing** (3e106ee: one line in needs attention, "alarm raised" on its block).
  - **Block logs, `threads.txt`, `transcripts.json` and `run.log` grow without limit; old project folders pile up**
    (3e106ee: `storage: logs:`; `ergostat compact --projects`).
  - **The CLI refuses to run while the YAML is broken** (75e7687, the merge of `cli-fallback`; 366241d and 6affe4f
    class `block --reset` and `block --check-warm` as acting): the engine keeps the model it takes as one snapshot
    of every file its loading read; commands that read fall back to that snapshot alone, with a warning; commands
    that act, `event --add` among them, refuse naming the YAML's error.
