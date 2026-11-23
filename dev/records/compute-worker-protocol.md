# compute-worker-protocol: ergostat worker --stdio: the worker package, the protocol's frame, hello, beat and ping

depends-on: []

Problem: nothing on another machine can speak to the engine: there is no `ergostat worker` (ergostat/cli/__init__.py:356-369) and no protocol (compute-systems.md sections 2, 2.1, 3). The worker must run on a node with no ergostat installed, and ten later gaps add to it, so its shape is decided here: not one file but a small package of single-purpose modules, by the house rule (dev/knowledge/house-rules.md, Code). Change: ergostat/compute/worker/, standard library only, flat (its modules import each other by bare name, nothing from ergostat), with __main__.py so `python3 -I PATH/worker --stdio` runs it as a directory and a zipapp of the same folder runs the same way; `ergostat worker --stdio [--root DIR]` (new ergostat/cli/worker.py) calls the same main, and `ergostat worker --pack FILE` writes the zipapp for copying to a node. This gap makes frames.py (one JSON object a line each way, each with v (1), seq and type, at most 1 MiB; requests carry id) and serve.py (the loop and a table of message type to handler that each later gap extends with one module and one registration line). First line hello: node (a random 32-hex id kept in the root, never a host name, address or user), cpus, memory, disk.root, arch, os, backends, images, labels, slots (at most its CPUs, at most 64), runs. beat every 10 s; ping answered pong; another v answered error then exit; an unknown type answered error without ending. The root defaults to ~/.local/state/ergostat-worker/ and nothing is written elsewhere. A helper tests/compute_pipe.py starts the worker over a pipe. Done: the directory, the zipapp and the CLI entry each answer hello then pong under `python3 -I` (tested on the image's Python; if isolated mode cannot run a directory, __main__ loads its siblings by path and the test says so); a test asserts no module of the package imports outside the standard library and the package; the node id persists; seq rises by one per line; nothing written outside the root; SPEC gains a Compute systems section with one subsection per later gap to fill. Files: ergostat/compute/worker/{__main__,frames,serve}.py, ergostat/cli/worker.py, ergostat/cli/__init__.py, tests/compute_pipe.py, tests/test_compute_worker_protocol.py (eight tests), docs/SPEC.md. Budget: 240 net lines.

Area: compute. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Built, round 1. All eight acceptance tests in tests/test_compute_worker_protocol.py pass; ruff is clean;
tests/test_cli_fallback.py and tests/test_graph_cli_web.py pass with the new topic. Choices made with nobody to ask,
each the most reversible:

- Isolated mode does run a directory: Python puts the folder first on sys.path under `-I`. `__main__.py` also inserts
  the folder itself when it is missing. That is how `ergostat worker --stdio` loads it by path; there is no
  `__init__.py`, so the folder is never imported as part of ergostat.
- "Nothing written outside the root" is narrower in one case: a directory run without `-B` gets Python's own cache
  of `__main__.py` in `worker/__pycache__/`. Python writes it before any line of the worker runs, and `-I` cannot turn
  it off. The worker's own modules are never cached (`sys.dont_write_bytecode` is set first). With `-B`, and as the
  zipapp, nothing is written outside the root. The test pins all three cases and SPEC §12s says so. The zipapp is the
  form to copy to a node.
- Fail closed: a `node` file that can't be read or isn't 32 hex digits ends the worker with an `error` and is never
  replaced. A `v` other than 1 (or none), a `seq` other than the next, a line that is not a JSON object or is over
  1 MiB, or a frame with no `type`: each gets one `error` and the worker ends. An unknown type, or a request with no
  `id`, gets an `error` and the worker goes on. Unknown CPUs give 0 slots, and unreadable memory or disk is null,
  never a guess.
- `hello`'s `backends`, `images` and `runs` are `[]` and `beat`'s `runs` is `{}`: no backend exists yet. `disk.root`
  is the root's free bytes. `slots` is min(CPUs, 64); a configured lower slot count is left for the gap that starts
  runs.
- `--beat SECONDS` (hidden, 0.05 to 60) lets the tests see beats without a 10 s wait.
- SPEC §12s has ten subsections to fill. They follow the proposal's milestone (docs/proposals/compute-systems.md
  section 7), minus its demo, because the second wave's gap names are not in this clone. A later gap that splits or
  renames one changes its heading.
- A `__pycache__/__main__.cpython-312.pyc` (gitignored, untracked) is left in ergostat/compute/worker/. A CLI test run
  wrote it before the CLI loader set `sys.dont_write_bytecode`. Removing it was refused in this session.

Overrun reason: 319 net lines against 240; the extra is the fail-closed paths the review lessons ask for (an unreadable or malformed node id, a seq gap, a bool v or seq, a missing id, a handler fault answered without ending, a malformed labels.json, memory on macOS, a root that can't be made) and the CLI's --pack/--stdio checks.
