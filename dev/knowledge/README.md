# The factory's knowledge

What an agent working on ergostat should know before it starts, kept as files the factory reads into briefs.

| File | What it holds | Who reads it |
|---|---|---|
| `house-rules.md` | how work is done here: definition first, suites, the machine's limits, outside effects | every implementor and reviewer |
| `review-lessons.md` | the classes of mistake reviews keep finding, each with the check that catches it | every implementor (to check against) and reviewer (to look for) |
| `decisions.md` | the owner's standing product decisions, seeded as `ergostat.decision` items | briefs whose gap touches the area |

**Kinds.** Each file starts with front matter: `kind`, `about`, `use`. `kind` is one of `component`, `rule`, `lesson`,
`finding`, `question` or `source` (an allowlist), and its entries take it; `decisions.md`, and only it, is
`kind: ergostat.decision`. A file whose kind is missing or any other is refused: `knowledge.py sync` exits non-zero and
records nothing (no entry is retired, no decision proposed), and so does a lesson not headed `## N. Title` or two
headings of one id.

**One form.** Each entry is a `## ` heading with its body, and an optional closing *Areas:* list. Entries are short and
specific: a class of mistake with where it was seen and the check, not a story. Their ids: `rules-process` (the first
word of each house-rule heading), `lesson-3` (each `## 3. Title`), and `<kind>-<slug of the heading>` for the other
kinds (`finding-stale-cache`). Every brief carries the rules and lessons, then, within the `[knowledge]` budget of
`dev/factory.toml`, for an implementor, a reviewer and a planner first the gap's answered research (below), then the relevant decisions, related gaps, past findings on the files it touches and the module map
(cached by main's sha in `run/modules/`, safe for sessions starting together: one read, a missing or half-written file
made again, a whole write renamed into place, and a prune that keeps its own sha's file and skips one already gone; a temp file left by a killed session is removed after ten minutes); its
recorded context lists the ids it carried and dropped. Entries of the four other kinds are synced as items but not yet
carried in briefs. Each entry is an item, `knowledge/<id>` (active, or retired once no file holds it), kept by the
collector `knowledge-sync` (`knowledge.py sync`) from the running version's files, with how many briefs carried it
(`carried`); the stock `knowledge-entries` counts the active ones, so its panel links to them on /items.

**Research for this gap.** A brief for an implementor, a reviewer or a planner carries, under "Research for this
gap", each answered `research/...` item the gap or a parent of it lists in its `research` field (a planner's
questions), or whose `gap` field names one of them (`dev/bin/ask.py --gap GAP`, which refuses a gap the record does
not hold): its question, summary and report (from `run/research/`) in `<report>` tags, the report cut at a line to
`[knowledge] research_chars` (6000). A question still asked or dead, or whose report cannot be read, is not carried.
Each is whole or not at all: one that does not fit the role's budget is dropped and its id recorded as dropped.

**Decisions are items.** Each heading of `decisions.md` is a decision, its body the owner's words, its *Areas* the
scope: `knowledge-sync` proposes it (`ergostat.decision.proposed`) only while its `ergostat.decision/...` id (ergostat's
own, from the heading) exists in no state, so it is proposed once and never again after the owner dismisses or
supersedes it; if the decisions cannot all be read, the sync stops with nothing recorded. The owner confirms, dismisses
or supersedes it as any decision (`docs/DECISIONS.md`). A brief carries the confirmed and the proposed ones (marked
proposed) whose scope names a word of the gap's text, recording their `ergostat.decision/...` ids; never a dismissed or
superseded one. If the items cannot be read, the brief is not built. Editing a heading makes a new decision; editing
only the body changes nothing already proposed.

**What an entry is about.** An entry may end with an *About:* line naming the parts of the root model (`ergostat.yaml`
and `dev/model/`) it bears on, comma-separated: `*About:* goal.first-pass-good, goal.few-fix-rounds.` `knowledge.py
sync` puts the names on the item's `about` field (the whole list each time; the line taken out, or the entry retired
and back without it, clears it), and the `knowledge` kind declares `about: about` (SPEC §5a, *About*). So `ergostat
explain goal.first-pass-good` ends with the open (active) entries about that goal, at most 5 and "and N more"; retired
ones are not listed. An off loop in `ergostat` names at most 3 (and "+N"), and a `check` finding about the goal
carries their ids. A name that is no part of the model is the finding `about-missing-part`. The lessons about the
pipeline (4, 6, 7, 8, 9, 10, 12, 13) and the Process and Machine rules name the goals they bear on;
`tests/test_factory_knowledge.py` checks every name is a part of the root model.

**Kept current by the factory itself.** After each review, the librarian (`dev/bin/librarian.py`) compares the findings
with `review-lessons.md`: a finding of a class already listed proposes a "seen as" line when it's a new shape; a class
found in two reviews that isn't listed proposes a new entry. Each proposal waits in the inbox (`knowledge-change`);
approved, it becomes a gap whose definition is the exact edit, landed like any other. By hand: `dev/bin/lesson.py`. A lesson that briefs carried while first-pass yield did not change is a candidate to rewrite or drop.
Private or work-specific material never goes here.
