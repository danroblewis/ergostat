# The factory's knowledge

What an agent working on ergostat should know before it starts, kept as files the factory reads into briefs.

| File | What it holds | Who reads it |
|---|---|---|
| `house-rules.md` | how work is done here: definition first, suites, the machine's limits, outside effects | every implementor and reviewer |
| `review-lessons.md` | the classes of mistake reviews keep finding, each with the check that catches it | every implementor (to check against) and reviewer (to look for) |
| `decisions.md` | the owner's standing product decisions | briefs whose gap touches the area |

Each file starts with front matter: `kind`, `about`, `use`. Entries are short and specific: a class of mistake with
where it was seen and the check, not a story.

**Kept current by the factory itself.** After each review, the findings are compared with `review-lessons.md`: a finding
of a class already listed adds a "seen as" line when it's a new shape; a class found twice that isn't listed becomes a
new entry. A lesson that briefs carried while first-pass yield did not change is a candidate to rewrite or drop.
Private or work-specific material never goes here.
