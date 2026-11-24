# BRANCH: one line on what the gap is

depends-on: []

(The line above names the gaps this one waits on, by branch or gap id, e.g. `depends-on: [remote-systems, warm]`; the
factory builds it only once each is merged, and draws the tree. Leave it `[]` when it waits on nothing.)

(Only when the gap must add an `ergostat check` finding to the factory's model, a line `allows-findings: [code part:
why]` here names each, with its reason (`code: why` for one about no part); the reviewer judges each. Without it, any new finding sends the build back.)

Branch `BRANCH`, from main. Where the gap came from (its GAPS.md entry, or who asked), and why now.

## Definition of done

One paragraph: what is true when this is done, said so a reviewer can check it. A gap is a vertical slice: it works end
to end and lands on its own (record, engine, answer, page and docs for a narrow part of the feature), never one layer
that only works once another gap lands. Example: the Agent page was built as layers (`agent-spec-api`, the answer for
every rung with nothing to see, then `agent-show-page`); as slices it is /agent/work showing an ai block's prompt end
to end, then a rule's law, then a program's files, each seen working and tested on the page when it lands.

## Acceptance tests

- `tests/test_x.py::test_name`: what it shows, end to end; this gap's own test, never one another gap also names.

## Size budget

600 net lines of code outside `tests/` and `docs/` (an overrun needs a written reason here).

(The section below is the gap's docs/GAPS.md entry in the form `dev/bin/gapsdoc.py` reads: `section:` (the GAPS.md
section's heading), any `done: YYYY-MM-DD sentence` lines, then the bullet as GAPS.md shows it, its later lines
indented two spaces, no blank line inside. A sub-gap of an umbrella entry has no bullet: only `entry-of: BRANCH` (the
umbrella's record) and its `done:` lines, which are drawn under the umbrella's bullet in date order. The merge queue
writes docs/GAPS.md from these sections as it lands; never edit docs/GAPS.md itself: a branch that does is refused.)

## Entry

section: Modelling
done: 2026-11-22 What landed, in one sentence.

- **The gap's title** (open; `BRANCH`, `dev/records/BRANCH.md`): what is known to be lacking, and why it matters.
  *Left*: what stays open once this is done.
