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
