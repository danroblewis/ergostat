# remote-and-libraries-mcp-remotes-tool: Agents see the model's remotes through an MCP tool

depends-on: []

Problem: an agent modelling a system that composes a remote must know which parts are the remote's (it may not edit them; a proposal for them becomes text), whether the remote answers, and the texts waiting for its owner. All of this is only in the CLI (ergostat/cli/remote.py:17-23: status, events, proposals); ergostat/mcp.py:30-191 has no remote tool. The owner's rule is that features go to agent tools and skills, not CLIs.
Change: one read-only MCP tool, `remotes`, built on the same functions the CLI uses (no new reads of the remote; no refresh is triggered).
Definition of done:
1. `remotes` with no argument returns, per remote: name, url, version, read (seconds ago), state (ok, unreachable, unknown, as remote.box), why when failing, part count by kind, missing references (remote-reference-unresolved), and its box's show.
2. `remotes` with `name` adds the list of its parts (local name -> remote name, kind) up to 500, and `proposals: true` adds the open texts for its owner as `ergostat remote proposals NAME --json` gives them.
3. A name that is not a key of remotes: is an error naming the model's remotes. A model with none answers {remotes: []}.
4. It works on the last good model when the YAML is broken, as `remote proposals` does (goodmodel.READ_WHAT), and writes nothing.
5. The MCP tool list's description and AGENT-GUIDE §3a say when to call it (before referencing a remote's part, and before proposing a change near one).
Files: ergostat/mcp.py, ergostat/cli/remote.py (factor the status and proposals rows into functions both use), docs/AGENT-GUIDE.md, docs/SPEC.md (§4c, one line), tests/test_remote.py.
Acceptance tests: test_mcp_remotes_lists_status (a planted remote: version, state, parts by kind); test_mcp_remotes_parts_and_proposals (name given: the part map and a planted open text); test_mcp_remotes_unknown_name; test_mcp_remotes_on_broken_yaml (good model kept, YAML broken: still answers, nothing written).
Size budget: 120 net lines.

Area: remote-and-libraries. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.
