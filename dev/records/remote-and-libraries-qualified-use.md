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

## Where it stopped

Built, round 1. Every item of the definition is done, in 55 net lines outside tests and docs (budget 100). The five
acceptance tests are in `tests/test_library_qualified.py` and pass.

How it is built:
- `templates.lookup(got, fetched, name, inside)`: `LIB/TEMPLATE` only among `doc.fetched` with that library (shadowed
  ones too, since `doc.fetched` keeps every fetched template); a bare name first in `inside`, then `find_all`'s choice
  as before. `find_all` takes an optional `offers` map, filled by `_put` with every source of each name (`library A`,
  `ergostat's own`, `a library folder`).
- `uses.plan`: the enclosing use's record (already in the chain's steps) gives `inside`, its library. A missed
  qualified name says either `library A offers no template 'X' (it offers: ...)` or `'A' is not a library loaded
  (libraries: ...)`, plus `library A refused: CODE, WHY` when it was. The `libraries:` names are a new `doc.libraries`
  (one line in `spec/load.py`, one in `library/fetched.py`, neither in the Files list), so a library that loads with no
  template is said as offering none rather than as unknown.
- `template-ambiguous` is a finding at the `use:` line. `where.template` (the `Via`) is `tp.qualified(t)`. The record's
  `template` stays the bare name, with `library` beside it as before. A once template's used-twice check now compares
  the library too.
- `author.library` lists templates that are not fetched as before, and every fetched one as `LIB/TEMPLATE`, and takes
  either form with `name:`. `author.change` (so both `add_use` and `try_use`) resolves a bare name and writes the
  qualified one when it finds a fetched template.

Choices taken where nobody could be asked (each reversible):
- `template-ambiguous` fires only when one of the sources is a fetched library, because only then is there a qualified
  form to suggest. An owner's folder shadowing ergostat's own keeps its existing `template-library` note. It fires only
  for uses the owner wrote, or inside an owner's folder template. A use inside ergostat's own template or a fetched
  library's template has no finding, because the owner cannot fix that text, and inside a library the own-library rule
  decides.
- An ergostat template shadowed by a fetched one is not listed by `templates`, because no name in a use reaches it.
  This is unchanged from today.
- `LIB/TEMPLATE` takes the template whatever its trust. An untrusted library's template, named this way, goes through
  the same gate as before.

Each guard was broken by hand, and a test failed each time:
- the own-library lookup dropped: `test_inner_bare_name_resolves_in_own_library` failed;
- `author.change` left the bare name: `test_add_use_writes_qualified_name` failed;
- `Via` given `t.name`: `test_qualified_use_picks_library` failed.

Run, one file at a time: `tests/test_library_qualified.py` (5 passed); `tests/test_library_fetch.py`,
`tests/test_library_fetch_load.py` and `tests/test_templates.py` (67 passed); `tests/test_library_untrusted.py`,
`tests/test_library_provenance.py` and `tests/test_library_trust.py` (125 passed); `tests/test_parity.py`,
`tests/test_spec_schema.py` and `tests/test_template_exports.py` (67 passed). ruff is clean. I did not run the unit
suite or the four browser files (the factory runs them). No page or example changed. `main` has nothing newer than
this branch's base.

## Entry

entry-of: shared-libraries
done: 2026-11-24 `use: LIB/TEMPLATE` names a fetched library's template, so two libraries may each offer one name. An unknown library, a refused library or a missing template is `unknown-template` saying which. A bare name that a library and another source both offer is `template-ambiguous`. Inside a library's template, a bare name looks in its own library first. `templates` and `add_use` use the qualified form (`remote-and-libraries-qualified-use`).
