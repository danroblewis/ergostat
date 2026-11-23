# research-design-queues-sessions-see-a-demo: Implementor and designer sessions may start a demo and walk it, with a pictures folder and the CPUs it needs

depends-on: [research-design-queues-walk-and-demo-scripts]

Problem: even with the scripts, a session cannot use them. The implementor's allowlist (dev/bin/agents.py:38-46) names only named_tests and the browser files. Its clone is /work, and a reviewer-like role's clone is read-only (agents.py:149-150), so screenshots have nowhere to go that leaves the container: /tmp is tmpfs and is removed with it (agents.py:53-54). Every session gets session_cpus = 1.5 (dev/factory.toml:78), and an engine plus Chromium on 1.5 CPUs fails stories that are about time ("Open shows something within one second") for the machine's sake. run_args sets NO_PROXY empty (agents.py:153).

Change: in agents.py, add a role `designer` (read-only clone, like the reviewer). Its tools are the reviewer's plus `Bash(uv run python scripts/demo_up.py:*)` and `Bash(uv run --with playwright==1.63.0 python scripts/walk.py:*)`. The implementor gets the same two commands, so a UI gap's implementor can see its change. Each implementor or designer session gets its own host folder run/shots/<session>/, mounted read-write at /shots, and both roles are told in their brief to pass `--shots /shots`. Add `[agents] designer_cpus` (default 3; held to (0, 4]) as the --cpus of designer sessions, and of implementor sessions whose brief says the gap touches ergostat/web/. Set NO_PROXY=127.0.0.1,localhost. Add designer_model and designer_session_usd to factory.toml ($2), a timeout in TIMEOUTS (3600), and a stand-in answer in fac.STANDIN.

Definition of done:
1. A designer session's docker run argv mounts /work read-only and run/shots/<session> read-write at /shots, and nothing else new.
2. Its allowed tools are exactly the reviewer's plus the two script commands. The implementor's gain those two.
3. designer_cpus sets --cpus for designers and for web-touching implementors, and a bad value refuses the session with its reason.
4. NO_PROXY names the loopback names.
5. dev/README.md ("Sessions in containers") says what a session can now run and where its pictures land.

Files to touch: dev/bin/agents.py, dev/bin/fac.py (STANDIN), dev/factory.toml, dev/README.md, tests/test_agents.py.

Acceptance tests (tests/test_agents.py):
- test_designer_session_argv_mounts_shots_and_readonly_work
- test_designer_and_implementor_may_run_demo_and_walk
- test_designer_cpus_bounds
- test_no_proxy_names_loopback
- test_reviewer_tools_unchanged (the reviewer gains nothing)

Size budget: 90 net lines (code and config; tests and docs excluded).

Area: research-design-queues. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.
