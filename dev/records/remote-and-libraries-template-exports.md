# remote-and-libraries-template-exports: A template declares its exports; a reference to its internals is a finding

depends-on: []

Problem: docs/proposals/external-systems.md (Deployment) says a shared module's ports are its public interface (`exports:`): internals change freely, and removing or renaming a port is a breaking change. Today any part of an instance can be named by its full name from anywhere (docs/SPEC.md:142), so a library author cannot change any internal part without breaking someone, and nothing tells a user which parts are meant to be read. Template files take only HEAD keys (ergostat/library/templates.py:24) and have no `exports`.
Change: an optional template key `exports:`, a list of the template's own refs (`stock.unanswered`, `goal.answered-in-time`, `flow.x`, `auxiliary.y`, `block.z`). Absent means all parts are exported (no change for existing templates).
Definition of done:
1. templates.read accepts `exports`; each entry must be a ref to a part the template defines (after each:/if: expansion is not needed: names written in the template's sections), else bad-template naming the entry. For an untrusted template each entry must also match the SAFE name rule.
2. After expansion, a reference from outside an instance (the owner's parts or another instance's) to a part of the instance that is not exported is a finding `template-internal-reference` at the referencing line: 'NAME is internal to instance I (template T exports: ...)'. A reference inside the instance, or an instance within it, is never a finding. Inner instances' exports count for references from outside the outer instance only if the outer re-exports them (`exports` may name an inner instance's exported ref by the inner's full template-local name).
3. The `templates` MCP tool and `author.library` show `exports` (marked as library text for an untrusted template, like the other fields).
4. One built-in template (respond-to) declares exports, with its README line, and every built-in demo still checks clean.
5. SPEC §2a documents exports and the finding; AGENT-GUIDE says to reference only exports and to write exports when writing a template.
Files: ergostat/library/templates.py, ergostat/library/uses.py (record each instance's exports in doc.uses), ergostat/spec/compile.py (the reference check), ergostat/library/author.py, ergostat/library/templates/respond-to.yaml, docs/SPEC.md, docs/AGENT-GUIDE.md, tests/test_template_exports.py (new).
Acceptance tests: test_exports_must_name_own_parts (an unknown ref is bad-template); test_reference_to_internal_part_is_finding (owner goal on a non-exported stock: finding at the goal's line; on an exported one: none); test_reference_within_instance_free; test_no_exports_means_all; test_templates_tool_shows_exports; scripts/demo_check.py passes for every demo.
Size budget: 150 net lines.

Area: remote-and-libraries. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Built, round 1 (84 net lines outside tests and docs). Every item of the definition is built and its acceptance
tests pass, except that scripts/demo_check.py was not run here: the session refused
`uv run python scripts/suite_watch.py -- uv run --with playwright==1.63.0 python scripts/demo_check.py` (background and
foreground) and `uv run python scripts/demo_check.py small-requests`. The demo run is left to the merge queue. In its
place, `test_no_example_reads_an_internal_part` reads each example whose main file uses a template that declares
exports (today only small-requests, through respond-to) and asserts it gives no template-internal-reference. No other
example can give the finding, since no other template declares exports. This test reads the model; it does not run the
demo or check its pages.

Choices made alone, each the more reversible one:
- "bad-template" for a bad `exports:` entry is a TemplateError naming the entry, as every other fault in a template
  file is: the template is unreadable (a `template-library` note), and a use of it is `unknown-template` quoting that
  note. A separate `bad-template` error code at the use line was not added.
- A template's own text names an inner use's part as `${name}-INNER-x`, because its renaming covers only its own
  names. In `exports:` the part is written `stock.INNER-x`, accepted when INNER is a key of its `uses:`. Whether the
  inner template exports x is not checked at read time, since the library is not at hand there. It needs no check: a
  reference from outside the outer instance is also outside the inner one, so the inner's exports still apply.
- The references checked are a flow's from:/to:, driven-by: and equation; an auxiliary's driven-by: and equation; a
  goal's measure; and a block's in:, out: and goal:. A system's `show:`, a loop's `through:` and a sensor's text are
  not checked. Ergostat's implied keep-GOAL blocks are skipped, because the block that names the goal is checked.
  SPEC §2a says all of this.
- A part named wholly by a parameter (`${kind}`) is the owner's name and is never internal. It cannot be listed in
  `exports:`, so counting it internal would leave it unreadable from anywhere.
- respond-to exports stock.waiting, auxiliary.oldest, flow.arriving, flow.answered and goal.on-time. Its "README
  line" went in docs/ADDING.md's respond-to entry, which is where the built-in templates are described.

Round 2 (103 net lines outside tests and docs), answering both findings of the round-1 review (both were blocking;
there were no others):
- An `exports:` entry naming an inner use's part (`stock.in-typo`, `goal.in-level` when level is a stock) is now
  checked after expansion (uses.unmade): if no inner use made the part, the use is an error `bad-template` at its
  `use:` line, naming the entry. Read time still checks the template's own sections' entries (a TemplateError). The
  check after expansion covers inner entries only, so an own part left out by an `if:` is not refused at a use.
  Test: test_exports_naming_an_inner_part_not_made_is_bad_template. Seen to fail with the check commented out.
- Each use record now holds `outer`, the instance it was planned under. The compiler's check reads `outer`, no longer
  `within` (the system placement), so an inner use that writes `within:` is still inside the outer instance. Test:
  test_inner_use_placed_elsewhere_is_still_inside asserts the inner system really sits in `elsewhere`. Seen to fail
  when the check reads `within` again.
- SPEC §2a says both.
- Not run: scripts/demo_check.py. The session refused it again, as given:
  `uv run python scripts/suite_watch.py -- uv run --with playwright==1.63.0 python scripts/demo_check.py small-requests`.
  It is left to the merge queue, with test_no_example_reads_an_internal_part standing in, as in round 1.

## Where it stopped

Parked by the factory (dead-letters, 2026-11-23 11:28).

Its runs failed past their attempts (a dead letter):
- attempt 12: nack queue: the push of af4bc34a9e4c (gap/dashboard-new-chart-forms) is requested
- attempt 13: nack queue: the push of f2f65f066ded (gap/milestone-every-gap-has-one) is requested
- attempt 14: nack queue: the push of 58471dafb951 (gap/compute-runs-on-config-continued-continued) is requested
- attempt 15: nack the implementor pool is full (run/pools.json): waits its turn

## Where it stopped

Continued, round 1 (2026-11-23). The park was the queue's (nacks and a full pool), not a review's, so no finding
was open. Main (059ff718f2d1) was merged in. It conflicted in ergostat/library/uses.py, where main had added `above`
and `owner_runs` to each use record and passed the outer instance as `above` in the inner plan() call. Both sides are
kept: the record holds `outer`, `above`, `owner_runs` and the exports fields, and the inner call passes `inst` as
`above`, with `unmade` still run after the inner uses. Ran after the merge: tests/test_template_exports.py (10 passed),
tests/test_templates.py (37 passed), tests/test_library_sandbox_sensors.py (9 passed, 4 skipped because bwrap cannot
make namespaces in this container), and ruff (clean). scripts/demo_check.py was not run here. As in rounds 1 and 2 it
is left to the merge queue.
