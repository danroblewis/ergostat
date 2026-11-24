# remote-and-libraries-qualified-use: use: LIBRARY/TEMPLATE names which library a template comes from

depends-on: [library-fetch]

Problem: library-fetch looks templates up by bare name in order (the owner's folders, then fetched libraries in config order, then ergostat's) and notes shadowing. With two libraries offering a template of one name (both teams' keep-under), only the first can be used, and a use does not say where its template comes from, so a reader of ergostat.yaml cannot tell, and adding a library can silently change which template an existing use gets. The parked libraries branch planned `use: NAME/TEMPLATE` (docs/roadmap/overnight/libraries.md on origin/libraries).
Change: `use:` takes `LIB/TEMPLATE` for a fetched library's template; a bare name works as today.
Definition of done:
1. `use: LIB/TEMPLATE` resolves only in fetched library LIB (a key of libraries:); LIB unknown or not loaded is unknown-template naming the libraries and, when LIB was refused, its refusal reason. TEMPLATE not offered by LIB is unknown-template listing what LIB offers.
2. A bare name that two or more sources offer is still resolved as today, and check adds a finding `template-ambiguous` naming each source and suggesting the qualified form.
3. Nested uses inside a library's template may use `LIB/TEMPLATE` too; a bare name inside a library's template resolves first in its own library.
4. The `templates` MCP tool lists each fetched template under its qualified name, and add_use writes the qualified name for one.
5. Instance naming is unchanged (the instance's key names its parts); where.template records the qualified name.
6. SPEC §2a and AGENT-GUIDE document it.
Files: ergostat/library/uses.py, ergostat/library/templates.py (lookup), ergostat/library/author.py, ergostat/mcp.py (add_use), docs/SPEC.md, docs/AGENT-GUIDE.md, tests/test_library_fetch.py or tests/test_library_qualified.py (new).
Acceptance tests: test_qualified_use_picks_library (two file:// libraries offering keep-under: each qualified use expands its own); test_bare_name_ambiguous_finding; test_unknown_library_or_template_said; test_inner_bare_name_resolves_in_own_library; test_add_use_writes_qualified_name.
Size budget: 100 net lines.

Area: remote-and-libraries. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.
