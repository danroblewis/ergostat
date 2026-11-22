## Entry

section: Modelling

- **A reviewer in the modelling template** (landing, `modelreview`, continued as `gap/modelreview-continued`;
  `docs/roadmap/overnight/modelreview.md`; owner: "I don't see a reviewer"): an `ai` block that reads each structural
  change and redesign the judge passed, and passes it, sends it back to its author, or rejects it, with the authors'
  prompts carrying its verdicts. The continued gap stamps each review with the verdict and edit it read (held by
  equality, recorded under the changes' lock only if the change is still that one), and keeps the shared daily cap
  closed: each call's estimated most is checked against what is left, read again before each call, and held against
  the cap while it runs, so the reviewer and the redesigner running at once do not both start calls on one remainder.
  Open: the estimate is not a bound (`claude -p` is given no output limit), so a call that writes more than 16,000
  tokens can take the day a little past the cap.
