# merge-pipeline-gaps-entries-in-records: A GAPS.md entry has a form in its gap's record, and docs/GAPS.md can be rendered from the records

depends-on: []

Problem: nearly every branch edits docs/GAPS.md (dev/knowledge/house-rules.md:33-34); the union merge from gaps-md-no-collisions turned conflicts into paragraph splices. Evidence, from the live record and to be cited by item id in this gap's record: the reviewer send-backs of 2026-11-22 on gap/relative-gain-array, gap/remote-items-record and gap/remote-process-lines each name a spliced GAPS.md paragraph. Change (format and renderer only, nothing reads or writes with them yet): new dev/bin/gapsdoc.py with parse(record) for a record's `## Entry` section (`section:`, optional `entry-of: <branch>`, `done: DATE sentence` lines, the bullet text), render(records, head) giving GAPS.md's text (sub-gaps' done lines rendered under their umbrella, in date order), split(gaps_md) as the inverse (head to dev/records/GAPS-head.md), and a CLI `render [--check]` / `split --dry-run`. Done: the round trip is pinned to a named commit, never to the moving file: a copy of docs/GAPS.md as of the commit this gap is built on is kept as tests/fixtures/gaps_md_pinned.md with its sha in the test, and render(split(fixture)) equals the fixture line for line once exact duplicate entries (the union merge's, which intake's twice() tolerates today) are removed; split reports every duplicate it drops by entry name and line, and `split --dry-run` lists them; two sub-gaps of one umbrella merge with no conflict and both render once; a malformed Entry or two entries slugging to one branch is reported by name, never skipped (`render --check` exits 1); dev/prompts/definition.md shows the Entry shape. Files: dev/bin/gapsdoc.py (new), dev/prompts/definition.md, tests/test_gapsdoc.py (new), tests/fixtures/gaps_md_pinned.md. Budget: 220 net lines in dev/bin.

Area: merge-pipeline. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Built, round 1 (60351b1a): everything the definition asks. Nothing is left open in the definition. dev/bin/gapsdoc.py
is 220 lines, exactly the budget; no overrun.

Evidence, cited by item id: the reviewer send-backs of 2026-11-22 on gap/relative-gain-array, gap/remote-items-record
and gap/remote-process-lines. Each names a spliced GAPS.md paragraph. The live record is not in this container, so
they are cited by id from the brief and were not re-read. The pinned fixture shows the splices too: the *System
architecture review* entry repeats its middle three times, and *Remote systems* has two `*Left*` clauses.

Choices made alone (no one to ask), each the most reversible one:
- GAPS-head.md is GAPS.md's skeleton: everything that is not an entry, with each entry as a line `@entry NAME`.
  GAPS.md's blank lines between entries are irregular (*Done recently* has some, other sections none), so only a
  skeleton gives the round trip line for line. A record the head does not list renders after its section's last
  listed entry, ordered by name, so a new gap need not edit the head. A section the head lacks is added at the end and
  reported.
- split names each record by its title's slug, as intake's gap id does (fac.slug, 60). The pinned copy has two
  *different* "External event logs" entries (lines 81 and 84). They are not exact duplicates, so both are kept, the
  second as `external-event-logs-2`, and split reports it. render then reports the two titles slugging to one branch,
  so `render --check` on that split exits 1. That is the "reported, never skipped" rule applied to the pinned file.
  The pinned copy has no exact duplicate entry. Duplicate dropping is tested on the pinned copy with two duplicates
  inserted, one next to its original and one in another section.
- A sub-gap's done lines render as `  - *Done DATE* (`branch`): sentence`, wrapped at 118 characters, after the
  umbrella's bullet, its own done lines included.
- A slot listed under the wrong section renders where it is listed and is reported. A slot listed twice renders once
  and is reported. A slot with no entry is reported.
- `split` without `--dry-run` exits 2: nothing writes records yet. `render` without dev/records/GAPS-head.md exits 1
  saying it is missing. The head is not committed, because the definition's Files list does not name it. On this
  tree, then, `render --check` exits 1 until a later gap writes the head and the entries.

Checked: tests/test_gapsdoc.py, 22 passed. Ruff is clean on ergostat, tests, scripts and dev/bin/gapsdoc.py. Four
breaks were each seen to fail their tests: done lines ordered by name, not date; duplicates not dropped;
slug collisions not reported; malformed entries not reported. The fixture's blob sha equals
`git rev-parse 277a9c6c:docs/GAPS.md` (50fb3b5c), and the test checks it.

Not run here: the unit suite and the browser files (the factory runs them). Running `dev/bin/gapsdoc.py` directly on
the repository's own files was refused in this session. The CLI is covered by the tests instead: `split --dry-run` as
a subprocess, `render [--check]` through main() on a temporary tree. main is this branch's base (277a9c6c), so there
was nothing to merge.
