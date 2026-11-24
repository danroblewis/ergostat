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

## Where it stopped

Round 1: built. Every definition-of-done item is in the code; the four named acceptance tests pass, and so does the
rest of tests/test_library_fetch.py, tests/test_library_fetch_load.py, tests/test_cli_fallback.py,
tests/test_templates.py and tests/test_library_tree.py (run one file at a time with scripts/named_tests.py). Ruff is
clean. About 80 net lines outside tests/, docs/ and dev/ (`git diff --stat`: 90 added, 10 removed), within the 110
budget. `main` has not moved since the clone, so there was nothing to merge. The unit suite and the browser files were
not run here: the factory runs them after this session. No page was changed.

What was built:
- `ergostat/library/fetched.py`: `described()` gives each `libraries:` entry from what `take()` already read (no
  network, no git): name, git, version, path, commit (12 hex, None unless the lock's is 40 or 64 hex), `tree` (`ok` or
  the refusal code) and `reason`, trust, and per template `owner's shell` or `sandbox or refused`. `line()` formats it.
  `take()` keeps the descriptions on `Document.libraries`.
- `ergostat check`: one dim line per library, after the remote lines and before any error (so a refused library is
  listed beside its error). In `--json` each is a `found` entry, level `note`, code `library`, about `library.NAME`, and
  is counted in `notes`. It is never an error and never changes rc. With no `libraries:` there is no line.
- The `templates` tool (author.library): each fetched template's entry, in the list and in the single view, carries
  `library: {name, version, commit}`. That key is not in `TEXT`, so it is not marked; the library's text is still marked.
- `ergostat library` with no subcommand (`what` is now optional): the same lines. When the main file reads, they come
  from `spec.load.load` (the doc, so a refused library is listed too). When it does not, they come from the last good
  model (`goodmodel.fallback`, said on stderr), or rc 2 if none is kept. It starts no process and writes nothing of its
  own. `library` stays out of `goodmodel.READS`, so `library fetch` still never runs on the fallback.
- SPEC §2a, *The listing*.

Choices taken alone (the most reversible option, said here):
- Files outside the definition's list: one line each in `spec/load.py` (the `Document.libraries` field),
  `spec/ir.py` (`Spec.libraries`) and `spec/compile.py` (copying it). check reads only the spec, and the last good model
  gives back only a spec, so a listing kept on the doc alone would not reach check or the fallback.
- The per-template verdict is binary and fails closed. `owner's shell` is given only when `templates.trusted(t)` (the
  gate's own test) holds. Everything else, including an untrusted template with no programs at all, is `sandbox or
  refused`. Which of the two happens is decided per use, after expansion with its `with:` values (uses.plan,
  trust.owner_runs). The listing has no use to expand, so it does not split them. Telling `no programs` apart would need
  a scan of the body for program keys. That scan is a denylist, so it was not written.
- A refused untrusted library's reason (which can name files in the copy, such as a FIFO's name) is printed with
  `printable` and marked as a `library file`, and check and `ergostat library` print SAYS after it. An owner library's
  reason is printed with `printable` only.
- Limit, said in SPEC: a model with `remotes:` may still have its load refresh a remote's cached model over the network,
  as every load does (section 4c). The listing claims only that it starts no git process and writes nothing of its own.

Each test was broken on purpose and seen to fail: `tp.trusted(t)` replaced by `True` fails
test_check_lists_each_library (b said `owner's shell`). `commit` dropped from the pin fails
test_templates_tool_carries_library_pin. A `subprocess.Popen` added to the listing fails test_library_listing_offline.
All three breaks were reverted.

Left: nothing in the definition.

Round 2: the review's one finding answered (it was the only finding, blocking; no non-blocking ones were raised).
- Finding: a `libraries:` map refused as a whole by `sources.check` (one bad entry, name or key, or more than 16) left
  `doc.libraries` empty, so `ergostat library` said `has no libraries:` with rc 0 and check printed no library note.
  Changed: `fetched.take()` now describes every raw entry of a refused map as refused, with the section's code and a
  reason naming the field (`the libraries: section is refused at FIELD, so none of its libraries is used`); its values
  are kept only when they are strings, and `line()` prints name, git, version and path through `printable` (`no git URL`
  / `no version` when absent). That reason comes from the owner's own file, not a library copy, so it is not marked
  (`SECTION` codes). check lists them as notes beside the section's error. `ergostat library` prints the same lines,
  says the section's error on stderr and exits 1; a `libraries:` that is not a map lists nothing, says the error, exits
  1, never `has no libraries:`. SPEC §2a says so.
- Test: test_listing_says_refused_section (a good entry beside a malformed one and one with an escape in its URL; then
  a list in place of the map). Broken on purpose and seen to fail twice: the raw-entry loop emptied (no lines), and the
  rc held at 0. Both reverted.
- Size: about 14 net lines more in ergostat/ (`git diff --stat` of this round: fetched.py +12 -4, cli/library.py +11 -5),
  about 94 in all, within 110.
- Run: tests/test_library_fetch.py (27), tests/test_library_fetch_load.py (7), tests/test_cli_fallback.py (18),
  tests/test_templates.py (38), tests/test_library_tree.py (6), one file at a time, all pass; ruff clean. `main` has not
  moved since the clone (nothing to merge). The unit suite and browser files were not run here; no page changed.

Round 3: main (d0f95413c74d) merged in; its conflicts in docs/SPEC.md, ergostat/library/author.py,
ergostat/library/fetched.py and ergostat/spec/load.py resolved, keeping both sides. No review finding was raised for
this round beyond the conflicts.
- Main added `Document.libraries` as a list of the names under `libraries:` (uses.py reads it for `use: LIB/TEMPLATE`).
  The branch's dict of descriptions clashed with it under the same name, so main's list is kept as it is and the
  descriptions moved to a new field, `Document.listed` (fetched.take, compile's copy into `Spec.libraries`, `ergostat
  library` and the templates tool read it). A refused `libraries:` section is described in `listed` only, so main's
  list, and so the `LIB/TEMPLATE` messages, behave as on main.
- The templates tool: main now names every fetched template `LIB/TEMPLATE` and lists each one; each such entry, in the
  list and the single view, still carries `library: {name, version, commit}`. test_templates_tool_carries_library_pin
  now looks entries up by `a/greet` and `b/other` (main's names); what it asserts is unchanged.
- SPEC §2a keeps both paragraphs, *The listing* and main's `use: LIB/TEMPLATE`.
- Size: `git diff --stat main -- ergostat`: 96 added, 9 removed, about 87 net, within 110.
- Run, one file at a time or three at most: tests/test_library_fetch.py (27), tests/test_library_fetch_load.py,
  tests/test_library_qualified.py and tests/test_templates.py (58), tests/test_cli_fallback.py,
  tests/test_library_tree.py and tests/test_library_provenance.py (78), all pass; ruff clean. The unit suite and the
  browser files were not run here; no page changed.

## Entry

entry-of: shared-libraries
done: 2026-11-24 `ergostat check` prints one note per fetched library (code `library`): its URL, version, the commit it
is pinned to, its trust, its templates, and whether each template's programs run on the owner's shell or are left to
the sandbox or refused. `ergostat library` alone prints the same list without running git, from the last good model
when the YAML is broken. The templates tool gives each fetched template `library: {name, version, commit}`
(`remote-and-libraries-libraries-listed`).
