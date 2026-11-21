# knowledge-seen-lesson-5-1e43a6ca: lesson-5 seen as a new shape

depends-on: []

Branch `knowledge-seen-lesson-5-1e43a6ca`, from main. Asked by the librarian, approved by the coordinator.

## Definition of done

`dev/knowledge/review-lessons.md`: lesson-5 seen as a new shape, as below, and nothing else changed.

Add to its "Seen as:" (a new line under its first paragraph if it has none), in its style: two distinct approved facts truncated to the same 32-char slug share one id, so block() merges both texts and sync flip-flops knowledge.changed each pass

From:

> dev/bin/knowledge.py:46 (lesson-5): a fact's id is `fact-` + fac.slug(m[1], 32), the decisions' rule, but a fact's title is the whole model-written sentence, so two approved facts sharing their first ~5-6 words ("The merge queue takes one gap at a time." and "The merge queue takes one gap per lease and ..." both give fact-the-merge-queue-takes-one-gap) get the same id. block() then carries both texts under one id, and knowledge.py sync (lines 187-203: diffs each entry against the same snapshot `it`) records knowledge.changed back and forth on every pass, every minute, forever, while the briefs' carried/dropped ids can't tell the two apart. Nothing at proposal or request time stops it (lesson.py checks only that the definition file doesn't exist yet). Give facts an id that can't collide (e.g. `fact-<the 12-hex hash>`, the same as the proposal's, written into the entry or worked out from its text), or refuse a request whose slug is already held by an entry, and add a test with two facts sharing a 32-character prefix.

## Acceptance tests

- `tests/test_factory_knowledge.py::test_knowledge_files_parse`: the knowledge files still parse into entries with ids.

## Size budget

0 net lines of code (knowledge only).
