# remote-and-libraries-libraries-listed: check and the templates tool say each library: where from, pin, trust, and whether its programs run

depends-on: [library-fetch]

Problem: after library-fetch a model can depend on several git libraries, but nothing lists them: check says only errors (library-unlocked, library-altered, ...), and the templates tool's entries carry `from` and `trust` (ergostat/library/author.py:39-50; templates.py:66-68) without the library's name, url, version or pinned commit. The parked branch's done-when asked that 'check prints a line for every library: where it comes from, its version and commit, the scripts it brings, and whether they will run'; nobody can review what a model trusts without it.
Change: one function describes each library from what load already read (no network, no git).
Definition of done:
1. ergostat/library/fetched.py gives, per libraries: entry: name, git url, version, path, commit (12 hex), tree ok or the refusal code and reason, trust (owner | untrusted), templates offered, and per template whether its programs would run on the owner's shell, in the sandbox, or are refused (from the trust gate's verdict, failing closed: anything not proven owner is said 'sandbox or refused').
2. `ergostat check` prints one note per library (`library NAME: URL @ VERSION (commit C), trust T, N templates; programs: ...`), code `library`, never an error; nothing for a model with no libraries:.
3. The templates MCP tool's entries for a fetched template carry `library: {name, version, commit}`; library text stays marked for untrusted ones.
4. `ergostat library` with no subcommand prints the same listing offline (as the old plan's 'list'), on the last good model when the YAML is broken, writing nothing.
5. SPEC §2a documents the listing.
Files: ergostat/library/fetched.py, ergostat/cli/library.py, ergostat/cli/spec_cmds.py (check's notes), ergostat/library/author.py, docs/SPEC.md, tests/test_library_fetch.py.
Acceptance tests: test_check_lists_each_library (two fetched libraries, one trusted: two notes with commit and trust); test_listing_says_refused_library (a library-altered one is listed with its reason); test_templates_tool_carries_library_pin; test_library_listing_offline (no git process run: the runner monkeypatched to fail).
Size budget: 110 net lines.

Area: remote-and-libraries. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.
