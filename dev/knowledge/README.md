# The factory's knowledge

What an agent working on ergostat should know before it starts, kept as files the factory reads into briefs.

| File | What it holds | Who reads it |
|---|---|---|
| `house-rules.md` | how work is done here: definition first, suites, the machine's limits, outside effects | every implementor and reviewer |
| `review-lessons.md` | the classes of mistake reviews keep finding, each with the check that catches it | every implementor (to check against) and reviewer (to look for) |
| `decisions.md` | the owner's standing product decisions | briefs whose gap touches the area |

Each file starts with front matter: `kind`, `about`, `use`. Entries are short and specific: a class of mistake with
where it was seen and the check, not a story. `dev/bin/knowledge.py` reads them into entries with ids: `rules-process`
(each bold heading of the house rules), `lesson-3` (each numbered lesson), `decision-<slug>` (each decision, carried
when the gap's text names one of the words in its closing *Areas:* list). Every brief carries the rules and lessons,
then, within the `[knowledge]` budget of `dev/factory.toml`, the relevant decisions, related gaps, past findings on the
files it touches and the module map; its recorded context lists the ids it carried and dropped.

**Kept current by the factory itself.** After each review, the librarian (`dev/bin/librarian.py`) compares the findings
with `review-lessons.md`: a finding of a class already listed proposes a "seen as" line when it's a new shape; a class
found in two reviews that isn't listed proposes a new entry. Each proposal waits in the inbox (`knowledge-change`);
approved, it becomes a gap whose definition is the exact edit, landed like any other. By hand: `dev/bin/lesson.py`. A lesson that briefs carried while first-pass yield did not change is a candidate to rewrite or drop.
Private or work-specific material never goes here.
