# Wave 2: remote systems and shared libraries, made complete and usable

Area: the owner said remote systems and shared libraries "were actually very important". Sources compared:
`docs/proposals/remote-systems.md`, `docs/proposals/external-systems.md`, SPEC §2a and §4c, `docs/GAPS.md`
(*Remote systems and libraries*), the code on main (`ergostat/remote/`, `ergostat/library/`, `ergostat/numbers/`,
`ergostat/spec/explain.py`, `ergostat/mcp.py`), and the filed gaps (all-gaps.json; the live definitions of
library-fetch, library-sandbox-sensors and library-sandbox-blocks were read so nothing here repeats them).

## Where things stand

**Remote systems**: nearly all of the proposal is on main: the API, tokens, `remotes:`, composition, readings,
box measures, remote-of-remotes, mTLS, process lines, items and events in the pages, texts for the owner. Left:

- *Analysis across the boundary is not what the spec says.* remote-systems.md §6 and SPEC §4c say a remote's
  stocks are data here (never integrated) and that the local residuals, coherence and "not exercised" leave its
  parts out. On main the served flows keep their equations (`remote/serve.py:26`), compose drops an equation
  only when it names a part left out (`remote/compose.py:440`), and `numbers/simulate.py:96` integrates every
  stock that has flows, so a remote's stocks are integrated in the local replay and projection, and
  `numbers/fit.py:211-217` counts them in the local fit total. `numbers/exercised.py:56-117` judges remote parts
  as "not exercised". `remote/__init__.py:18-21` claims the exclusion, but only `state.py:193` and `:623` apply it.
- *`explain` says nothing about remotes.* The proposal (§6) says "`explain` names the remote parts on it" for a loop
  across the boundary; `spec/explain.py:141-157` lists loops with no remote marking, and no part or system
  explanation says it is a remote's.
- *Agents cannot see remotes.* `mcp.py:30-191` has no remote tool; everything is in the CLI
  (`cli/remote.py:17-23`). The memory rule "integrations, not CLI" asks for an agent tool.
- *`remote-stale` was designed and never built.* remote-systems.md §5 names it for `check`; only
  `remote-unreachable` exists (`remote/compose.py:180-188`), and failing readings (`remote/cache.py:108-116`,
  `read_ok`) reach only the status's attention (`remote/__init__.py:40`).
- Serving the IR stays parked (remote-serves-ir, research); nothing here depends on it.

**Shared libraries**: the trust machinery for untrusted folders is on main; library-fetch (building) adds git
libraries pinned in a lock, but refuses every use of a fetched library without `trust: owner`, finds templates by
bare name with shadowing, and lists nothing about libraries; library-sandbox-sensors/-blocks run untrusted programs
in the sandbox. Left to make it usable:

- fetched untrusted libraries held by the same gate as untrusted folders instead of refused outright;
- `use: LIBRARY/TEMPLATE`, so two libraries' templates of one name can both be used and a use says where it is from;
- each library said by `check` and by the `templates` tool (source, pin, trust, whether its programs run);
- a template's public interface (`exports:`), from external-systems.md "Deployment": internals change freely;
- an update reviewed before it is taken: what a new version breaks and changes (external-systems.md: "`ergostat
  check` against the new version lists what broke");
- a worked example and a guide to writing a library for others.

**External systems (the library of known controllers)**: identification is built (SPEC §12d) and a demo is filed
(demo-observed-external-controller). Not filed: the "library of known controllers" (`law: kubernetes-hpa`, declared
and tested against the record, run in the projection), the HPA's multiplicative rule as its own identified family
(GAPS: *Identifying existing controllers*, *Left*), and the known controllers shipped as templates.

Not planned (noted): a Kubernetes source type (a `command` source with kubectl reads it today); a library's scripts
re-verified against the lock when they run (library-fetch explicitly does not claim it; security beyond correctness is
out of the owner's scope); a serve mode that recalibrates and publishes a reference model (ergostat never pushes);
remote `exports:` (after template exports, if wanted).

## The milestone: remote-and-libraries

Wave A (no dependencies, start now): remote-parts-are-data, explain-remote-parts, mcp-remotes-tool,
remote-stale-finding, template-exports, known-controller-laws.
Wave B (after library-fetch): fetched-untrusted-held, qualified-use, libraries-listed, library-update-check.
Wave B' (after known-controller-laws): declared-law-tested, declared-law-projected, hpa-ratio-family,
autoscaler-template.
Wave C: shared-library-demo (after library-sandbox-sensors and template-exports).

Every definition is in the structured result (house shape: problem with evidence, change, numbered definition of
done, files, acceptance tests, size budget).

| Gap | Size | Depends on |
|---|---|---|
| remote-and-libraries-remote-parts-are-data | incremental, 140 | none |
| remote-and-libraries-explain-remote-parts | quick, 80 | none |
| remote-and-libraries-mcp-remotes-tool | incremental, 120 | none |
| remote-and-libraries-remote-stale-finding | quick, 50 | none |
| remote-and-libraries-template-exports | incremental, 150 | none |
| remote-and-libraries-fetched-untrusted-held | quick, 80 | library-fetch |
| remote-and-libraries-qualified-use | incremental, 100 | library-fetch |
| remote-and-libraries-libraries-listed | incremental, 110 | library-fetch |
| remote-and-libraries-library-update-check | large, 260 | library-fetch |
| remote-and-libraries-known-controller-laws | large, 220 | none |
| remote-and-libraries-declared-law-tested | incremental, 150 | known-controller-laws |
| remote-and-libraries-declared-law-projected | incremental, 90 | known-controller-laws |
| remote-and-libraries-hpa-ratio-family | incremental, 140 | known-controller-laws |
| remote-and-libraries-autoscaler-template | incremental, 130 | known-controller-laws |
| remote-and-libraries-shared-library-demo | incremental, 200 | library-sandbox-sensors, template-exports |
