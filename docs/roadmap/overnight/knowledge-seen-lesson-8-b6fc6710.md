# knowledge-seen-lesson-8-b6fc6710: lesson-8 seen as a new shape

depends-on: []

Branch `knowledge-seen-lesson-8-b6fc6710`, from main. Asked by the librarian, approved by the coordinator.

## Definition of done

`dev/knowledge/review-lessons.md`: lesson-8 seen as a new shape, as below, and nothing else changed.

Add to its "Seen as:" (a new line under its first paragraph if it has none), in its style: SPEC §9.5 says the schema is the machine-checkable form of the spec, but the schema still types `pool` as an integer only, so the documented mapping form and the factory's own building.yaml are refused and no test checks it

From:

> schema/ergostat.schema.json:1590 (lesson-8): `pool` is still `{"type": "integer", "minimum": 1}`. docs/SPEC.md:5 says this schema is 'the machine-checkable form of this document', and the schema tracks every other block key (unblocked, daemon, on-stale, workspace). The branch adds `pool: {now: stock.NAME, most: N}` to SPEC §9.5, the help and the factory's own dev/model/building.yaml, so the published schema now refuses a valid model, the factory's included, in any editor or validator that uses it. tests/test_spec_schema.py only checks docs/spec-examples/*.yaml, so nothing catches it. Fix: let `pool` be either an integer of 1 or more or an object {now: string matching ^stock\., most: integer of 1 or more}, with both keys required and no others, and add a spec example (or a schema test) that uses the mapping form.

## Acceptance tests

- `tests/test_factory_knowledge.py::test_knowledge_files_parse`: the knowledge files still parse into entries with ids.

## Size budget

0 net lines of code (knowledge only).

## Where it stopped

Built: lesson-8's "Seen as:" in dev/knowledge/review-lessons.md gains the pool-schema shape. Nothing else changed
(`git diff main --stat`: that file and this one).

The factory's `unit` run was reported failed, but its tail stops at 36% of the progress lines with no failing test,
error or traceback in it. That looks like the run was cut off (a timeout or the watchdog), not a test failing. The only
test that reads dev/knowledge/ is tests/test_factory_knowledge.py. All 22 of its tests pass (run alone, serially, after
the report). The branch changes no code, so no code fix applies. I did not re-run the whole unit suite myself: the
house rules leave that to the factory, under the watchdog. If the next run fails again, the test it names is what to
look at.
