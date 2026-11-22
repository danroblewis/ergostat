# compute-pools-config: compute: pools in the model, with their check findings and ceilings

depends-on: []

Problem: a model cannot declare where runs may execute: there is no `compute:` section (ergostat/spec/compile.py:86-92; workspaces are the pattern, ergostat/workspaces/compile.py:15-41). This gap is the pools only; `runs-on:` on a block is compute-runs-on-config. Change: ergostat/compute/compile.py compiles `compute:` pools (nodes [{ssh: HOST} | {connect: [argv]}], backend process|docker, image, slots, limits {cpus, memory, pids, disk, wall, network, log}, repos, secrets {NAME: file}, labels) into a ComputePool in the IR (beside WorkspacePool, ir.py:503). Errors with their place: an unknown key; a bad size or duration; over 64 nodes or 64 slots; nodes x slots over 256 across pools; wall over a day; log over 1 GiB; `network: none` on the process backend; docker without image; a node entry naming an address or a user (`@` in ssh:). Nothing runs differently. Done: each refusal has its code; a model without compute: compiles to an identical IR; SPEC gains a compute: subsection. Files: ergostat/compute/compile.py, ergostat/spec/compile.py, ergostat/spec/ir.py, tests/test_compute_compile.py, docs/SPEC.md. Full text: wave2-compute.md (the pool half). Budget: 170 net lines.

Area: compute. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Built, round 1. `ergostat/compute/compile.py` reads `compute:` into `Spec.compute` (`ComputePool`, ergostat/spec/ir.py),
called from the spec compiler beside workspaces. tests/test_compute_compile.py: a full pool compiled (bytes, seconds);
a model without `compute:` gives the same value for every other Spec field and the same version hash; 28 refusals,
each by its code and the line it points at; the ceilings at and just past their edge (64 nodes over pools, 256 runs);
a template that writes `compute:` refused. SPEC §12k gains *Compute pools*.

Outside the Files list, needed: `ergostat/spec/load.py` (`compute` among SECTIONS, else the section is an unknown key),
`ergostat/library/trust.py` (`compute` in REFUSED: test_library_trust requires every section classified; an untrusted
library may not declare machines), `ergostat/compute/__init__.py` (the package docstring).

Choices made with no one to ask (each the more reversible one): `network:` takes `none` or `host` only; `slots`
defaults to 1; `log` defaults to 64 MiB (the proposal's), the other limits to unset; sizes are multiples of 1024; the
64-node ceiling is checked per pool and over all pools (the proposal's section 3); an `ssh:` value is an allowlist
(letters, digits, `.`, `_`, `-`, not starting with `-`), and all digits-and-dots or any `:`/`[`/`]` reads as an
address; label, repo and secret values must be non-empty text; a NaN `wall` is refused as over a day; `pids` is
capped at 2^22. Not built (other gaps): `runs-on:`, any connection, reading a secret's file, the run-time recount of
the 256 ceiling.

Overrun reason: 188 net lines against 170: the 18 over are the cross-pool ceilings (64 nodes and 256 runs summed over pools), the NaN-safe number checks, and the ssh allowlist with separate user and address codes, each covered by a test.
