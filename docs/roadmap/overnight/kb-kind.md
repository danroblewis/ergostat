# kb-kind: knowledge entries of six declared kinds, one markdown form, the owner's decisions as ergostat.decision items
depends-on: []

## Definition of done

- **Six kinds, declared.** A knowledge entry's `kind` is one of `component`, `rule`, `lesson`, `finding`, `question` or `source`. That fixed list is the only one accepted (an allowlist). Each file in `dev/knowledge/` (all but README) declares its kind in its front matter (`kind:`). Entries take that kind; they no longer get it from the file name. A file with a missing kind, or a kind outside the list, is refused: `knowledge.py sync` exits non-zero and records nothing, so no entry is retired because its file could not be read. `decision` is no longer a knowledge kind.
- **One markdown form.** Every knowledge file uses one form: each entry is a `## ` heading with its body, plus an optional closing *Areas:* list. `house-rules.md` moves from bold headings to that form. `review-lessons.md` keeps `## N. Title`, which `lesson.py` and the librarian rely on. The ids do not change:
  - the four house-rule entries: `rules-process`, `rules-machine`, `rules-code`, `rules-outside`
  - the lessons: `lesson-1` … `lesson-13`
  - the four new kinds: `<kind>-<slug of the heading>`
- **Decisions are `ergostat.decision` items.** `dev/knowledge/decisions.md` (front matter `kind: ergostat.decision`, migrated to the same heading form) is the one file read as decisions rather than as entries.
  - On each run, `knowledge-sync` prints an `ergostat.decision.proposed` line (SPEC §5a) with `scope` set to its *Areas*. It does this only for a decision whose `ergostat.decision` id exists in no state. The id is ergostat's own, derived from the sentence. So the collector does not propose a decision twice, does not append its words again, and does not re-propose one the owner dismissed or superseded.
  - No `knowledge/decision-*` items are made. The collector retires the existing ones the same way it retires any other entry no file holds.
- **Briefs carry decision items.** `knowledge.block` takes its decisions section from `ergostat.decision` items in the confirmed or proposed states (proposed ones are marked as proposed) whose `scope` names a word of the gap's text. It records their ids (`ergostat.decision/...`) in the brief's context. Dismissed and superseded decisions are never carried. If those items cannot be read, building the brief fails. It does not send a brief with no decisions.
- Rules and lessons are carried as before. The four new kinds are parsed and synced as items, but briefs do not carry them yet; that is out of scope here.
- **Docs and model kept current:**
  - `dev/knowledge/README.md`: the kinds, the form, decisions as items
  - the `knowledge` item kind's description in `ergostat.yaml`
  - the `knowledge-entries` description in `dev/model/knowledge.yaml`
  - one line in `docs/DECISIONS.md` on how the factory seeds its decisions

  `ergostat check` on the root model is clean.

## Files to touch

`dev/bin/knowledge.py`, `dev/knowledge/{README,house-rules,review-lessons,decisions}.md`, `ergostat.yaml`, `dev/model/knowledge.yaml`, `docs/DECISIONS.md`, `tests/test_factory_knowledge.py`.

## Risks

- **lesson-3:** a file that is unreadable or has an unknown kind gets skipped instead of refused, and sync retires all of its entries. Or a failed decision lookup sends a brief out with no decisions.
- **lesson-5:** decision ids are reused. The collector proposes again a decision the owner dismissed, or makes a `.seen` that appends words on every minute's run. Or it derives the id differently from ergostat, so it never sees the decision as existing.
- **lesson-8:** README or docs claim briefs carry the new kinds, or that decisions are carried "confirmed only", when the code does otherwise.

## Acceptance tests

All in `tests/test_factory_knowledge.py`:

- `test_knowledge_files_parse` (extended): the repository's files parse; every entry's kind is in the six; the ids `rules-process`, `rules-outside`, `lesson-1` and `lesson-13` exist; no entry has kind `decision`.
- `test_entry_kind_from_front_matter`: a fixture file for each of `component`, `finding`, `question` and `source` syncs `knowledge/<kind>-<slug>` items of that kind.
- `test_unknown_kind_refused_nothing_retired`: after a first sync, one file's kind is changed to `misc` (and in a second case the front matter is removed). Sync exits non-zero and says no `knowledge.retired` (lesson-3).
- `test_sync_proposes_each_decision_once`: `decisions.md` gives proposed `ergostat.decision` items with `scope` equal to their areas, and passes ergostat's proposal check. A second sync says nothing. After the owner dismisses one, sync does not propose it again. An active `knowledge/decision-*` item from before is retired (lesson-5).
- `test_brief_carries_knowledge_within_budget` (updated): carries a confirmed decision whose scope matches and a proposed one, marked; does not carry a dismissed one, a superseded one, or one whose scope is not named. Records `ergostat.decision/...` ids. Budget behaviour as before.
- `test_brief_fails_when_decisions_unreadable`: when the item lookup fails, `knowledge.block` raises; no brief is written (lesson-3).

For each new test, the implementor breaks the code it guards and reports that it then fails (lesson-9). Then the unit suite and the four browser files run under `scripts/suite_watch.py` with rc 0, ruff is clean, and origin/main is merged in and the suites run again.

## Size budget

150 net lines of code outside `tests/` and `docs/` (the markdown under `dev/knowledge/` not counted).

## Notes from the plan review (answer each)

- Sync-side fail-open (lesson-3 x lesson-5): 'propose only if the id exists in no state' must not treat a failed or partial ergostat.decision lookup as 'exists in no state'. If the lookup fails, sync exits non-zero and proposes nothing. Add test_sync_refuses_when_decisions_unreadable: make the lookup fail after the owner has dismissed a decision, and assert that sync is non-zero and prints no ergostat.decision.proposed line. Break the guard and report that the test fails.
- Concurrency (lesson-1): sync reads decision states, decides, then prints proposals, and it runs every minute. Either name the lock held across that read-decide-write, or show with a test that two overlapping syncs proposing the same id give one decision and append its words only once. Add lesson-1 to Risks.
- The allowlist contradicts itself: decisions.md declares kind ergostat.decision, which is not in the six. State that the accepted front-matter kinds are exactly the six plus ergostat.decision, and that ergostat.decision is accepted only in decisions.md. Test that ergostat.decision in any other file is refused, and that a decisions.md with missing or wrong front matter is refused with nothing retired.
- All or nothing: when any file is refused, sync must also print no ergostat.decision.proposed lines and record no other change. Extend test_unknown_kind_refused_nothing_retired to assert that no proposal is printed.
- Duplicate ids (lesson-5): two headings in one kind that slug to the same id must be refused, not let one overwrite the other. Add a case to the refusal test.
