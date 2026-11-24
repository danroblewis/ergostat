# research-design-queues-research-open-web: The researcher reads a listed set of web hosts: WebFetch and the walker through an egress proxy of its own, private addresses refused

depends-on: [research-design-queues-walk-and-demo-scripts]

Problem: the research queue is meant to answer questions with evidence from the web, but its sessions cannot open a page. The researcher has WebSearch, which the API runs (dev/bin/agents.py:57-59), but WebFetch is in DENY (agents.py:34-35). Every session sits on one internal network whose only way out is the egress proxy for [agents] hosts = ["api.anthropic.com"] (dev/factory.toml:74; agents.py:121-132). The prompt says "where your session allows it" (dev/prompts/researcher.md:14), and today it never does.

Change: add a second internal network and proxy, used only by researcher sessions. The network is ergostat-research and the proxy container is ergostat-egress-research, both started like egress(), under the same lock. It allows api.anthropic.com plus [agents] research_hosts (default ["*"]: any host). In dev/agent/egress.py, `*` allows any CONNECT host on 443 whose SNI matches, as now, but refuses a host whose resolved addresses include any that is not ipaddress.is_global (loopback, private, link-local), and logs why. The researcher's tools gain WebFetch and `Bash(uv run --with playwright==1.63.0 python scripts/walk.py:*)`, with a /shots folder as for the designer. The researcher's prompt says which tools it has, that a URL it cites must be one it opened, and that it should prefer primary sources. Every other role stays on the first network, with the same hosts.

Definition of done:
1. A researcher session runs on ergostat-research with HTTPS_PROXY pointing at the research proxy. No other role does.
2. The research proxy tunnels to a public host and refuses 127.0.0.1, 10.x, 172.16/12, 192.168/16, 169.254/16 and ::1, each logged with why. The SNI check still holds.
3. With research_hosts set to a list, only those names, plus the API, are reached.
4. The researcher's allowed tools include WebFetch and the walker. The implementor's and reviewer's are unchanged, and WebFetch stays denied for them.
5. dev/README.md and dev/prompts/researcher.md say so.

Files to touch: dev/agent/egress.py, dev/bin/agents.py, dev/factory.toml, dev/prompts/researcher.md, dev/README.md, tests/test_agents.py, tests/test_egress.py (new, or the existing egress tests).

Acceptance tests:
- tests/test_egress.py::test_star_allows_public_refuses_private (the resolver monkeypatched)
- tests/test_egress.py::test_sni_mismatch_still_refused_under_star
- tests/test_agents.py::test_researcher_on_its_own_network_and_proxy
- tests/test_agents.py::test_only_researcher_gets_webfetch
- tests/test_agents.py::test_research_hosts_list_limits_proxy_args

Size budget: 120 net lines (code and prompt; tests and docs excluded).

Area: research-design-queues. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Built, round 1. Every done item is in dev/agent/egress.py, dev/bin/agents.py, dev/factory.toml,
dev/prompts/researcher.md and dev/README.md, with the five acceptance tests (80 net lines of code, config and prompt,
inside the 120). Choices made where nobody could be asked (each the most reversible):

- The tunnel under `*` goes to the address that was checked (the first one resolved), never to a second lookup of
  the name, so DNS cannot point it at a private address between the check and the connect. Multicast is refused
  too: Python counts some multicast as global. A name that resolves to nothing, or does not resolve, is refused.
- A listed name (the API, or a research_hosts entry) is tunnelled as before, by name and without the address check,
  so the first proxy behaves exactly as it did. Only names reached through `*` are checked.
- `research_hosts = []` means the API alone, never "any host" (absent means `["*"]`). A value that is not a list of
  host names (or `"*"`) refuses the researcher's session with its reason, and only the researcher's: other roles never
  read it.
- A proxy found running with other hosts than the settings' (compared by its `.Config.Cmd`) is removed and started
  again. Otherwise narrowing research_hosts would leave the old `*` proxy running. This applies to the first proxy
  too, since both are started by the same code, so a change to `[agents] hosts` now takes effect at the next session.
- The researcher's /shots folder is made and mounted as the designer's is, but its brief gets no demo paragraph
  (agents.LOOK names demo_up, which it does not have). Its prompt names the walker and `--shots /shots` instead.
- dev/bin/research.py's source check counts URLs from WebFetch and WebSearch results, not from a walker run through
  Bash. So the prompt says a page seen only through the walker is not counted, and a page it cites must be fetched.
  Counting walker URLs would change research.py, which is outside this gap's files.
- tests/test_factory_knowledge.py::test_new_roles_read_only_in_their_containers gets a `paths.run` in its minimal
  config: the researcher now has a pictures folder under run/.

Run here: tests/test_egress.py, tests/test_agents.py, tests/test_factory.py, tests/test_factory_knowledge.py,
tests/test_shell_rule.py and tests/test_factory_sessions.py all pass. The two skips in test_factory.py need Docker
and the agent image. Ruff is clean. Each new test was seen to fail on a broken change: the tunnel dialling the name
again, only loopback refused, the SNI check dropped under `*`, every role on the research lane, `[]` read as any, and
WebFetch given to every role. Not run here: the unit suite and the four browser files (no page changed), and no real
proxy in Docker (no network in this container).
