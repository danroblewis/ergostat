# compute-pools-config: compute: pools in the model, with their check findings and ceilings

depends-on: []

Problem: a model cannot declare where runs may execute: there is no `compute:` section (ergostat/spec/compile.py:86-92; workspaces are the pattern, ergostat/workspaces/compile.py:15-41). This gap is the pools only; `runs-on:` on a block is compute-runs-on-config. Change: ergostat/compute/compile.py compiles `compute:` pools (nodes [{ssh: HOST} | {connect: [argv]}], backend process|docker, image, slots, limits {cpus, memory, pids, disk, wall, network, log}, repos, secrets {NAME: file}, labels) into a ComputePool in the IR (beside WorkspacePool, ir.py:503). Errors with their place: an unknown key; a bad size or duration; over 64 nodes or 64 slots; nodes x slots over 256 across pools; wall over a day; log over 1 GiB; `network: none` on the process backend; docker without image; a node entry naming an address or a user (`@` in ssh:). Nothing runs differently. Done: each refusal has its code; a model without compute: compiles to an identical IR; SPEC gains a compute: subsection. Files: ergostat/compute/compile.py, ergostat/spec/compile.py, ergostat/spec/ir.py, tests/test_compute_compile.py, docs/SPEC.md. Full text: wave2-compute.md (the pool half). Budget: 170 net lines.

Area: compute. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.
