# ui-no-command-yaml-line-or-spec-section-on-the-read: No command, YAML line or SPEC section on the reader's pages

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q12 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram side panel, /loops, /agents, /items, loop and controller panels

**The problem:** Reader pages tell people to run a command or edit configuration: '`ergostat actions` lists them', '(SPEC §9.7)', '(SPEC §12e)', 'a kind declares them under relations: (blocked_by: ticket)', 'write it in the goal's process:'. People only read here.

**The change:** Replace each with what the reader can see or do: the waiting acts are listed in the row itself; 'These items do not wait on one another, so there is no critical path'; drop the SPEC references; the Harris row says what is missing ('needs the loop's dead time'). Absolute log paths in an agent's panel shorten to the file name.

**User stories it serves:** A4, F5, G7

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On all six demos the text of /diagram, /loops, /agents and /items (and any panel opened from them) matches none of: /SPEC §/, /ergostat\.yaml/, /`ergostat /, /relations:/, /under with:/, /\/private\/tmp/.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Round 1, built. About +1 net line of code outside `tests/` (10 lines changed in place).

**What changed**
- `ergostat/web/static/pages.js`: the Items page's Graph and Timeline, for a system whose kinds have no relations, now
  say "These items do not wait on one another, so there is no critical path." in place of the `relations:` hint.
  The note about items that match no kind no longer names `ergostat.yaml` ("match no kind of the model's").
  The Agents page's Daemons note drops "(SPEC §9.7)".
- `ergostat/web/static/control.js`: when the loop's dead time is not known (the server's `needs_theta`), the Harris
  row says "needs the loop's dead time". `control/monitor.py` is unchanged, so the CLI still says where to write it.
- `ergostat/web/static/details.js`: the agent panel's log row shows only the file name (`worker.log`).
- Five library templates' top-level `description:` lose their "(SPEC §…)" note: modelling, interventions, repair,
  upkeep, collect. The modelling one is what /items showed on every demo that uses modelling. The descriptions are the
  only source of that text, so the fix goes there even though they sit outside `ergostat/web/`. This is the most
  reversible fix: only text, no page code that filters text. Their part descriptions (`steps.yaml`, the modelling
  parts) are not changed. No demo showed them.

**Choices made without anyone to ask**
- "The six demos" is not defined anywhere in the repository. The test uses first-loop, image-squeeze, roadmap,
  software-factory, the-job and ticket-factory (`READERS_DEMOS`). roadmap and ticket-factory are the two with
  relations.
- The demos are served, not run, as the other page tests do. Run-only text (the Harris row, held actions) is not
  produced there. The Harris row has its own test, which feeds the page what `control.monitor.performance` returns.
- The definition quotes "'`ergostat actions` lists them'", and the waiting acts "listed in the row itself". That
  text is not in the page code or in any server answer on main (searched `ergostat/` for "lists them" and
  "ergostat actions"). The only near match is a `notify-failing` finding in `spec/watch.py` ("ergostat actions lists
  their output"), which has no backticks and is not on a demo page. So nothing was changed for it.
- `openSystem`'s "`ergostat explain system.X` says the same in sentences" (details.js) is left as it is. No current
  view reaches that function: the Dynamics view uses `sdOpenSystem` and the Blocks view uses `openBlock`. A reader
  never sees it, and removing it would be a change the test cannot see. The test still checks for "ergostat explain "
  in case a view starts reaching it.
- Not changed: the item page (`/item/…`: `ergostat item … --history`, `ergostat lease ITEM --redrive`) and the review
  and equation panels (`ergostat accept`, shown only in snapshots). They are outside the pages this gap names.

**Tests** (each run alone, under `scripts/suite_watch.py`, with Playwright 1.63.0)
- `tests/test_diagram_rendering.py::test_the_readers_pages_name_no_command_yaml_line_or_spec_section[6 demos]`
  covers:
  - /diagram: the side panel, every part's panel in Dynamics and in Blocks with every system open, and each system's
    panel with the systems closed.
  - /loops and each loop's panel, including its controller box.
  - /agents and each agent's panel.
  - /items in its list and its graph.

  The text must match none of the acceptance patterns, nor the test's temporary folder (on this Linux box the
  equivalent of `/private/tmp`, under which the project and its logs lie). 6 passed (545 s, rc 0, together with the
  Harris test).
- `tests/test_diagram_rendering.py::test_the_harris_row_says_what_is_missing_not_where_to_write_it`: passed.
- `tests/test_agents_page.py`: the daemons test now also checks for no "SPEC §". 3 passed.
- `tests/test_items_page.py`: 21 passed (rc 0, no skips).
- `tests/test_modelling_template.py`, `tests/test_interventions.py`, `tests/test_mirror.py`: 50 passed.
- `ruff check ergostat tests scripts`: clean.

**Breaks seen to fail** (lesson 9)
- With the full log path back, the six-demo test failed on first-loop, naming every agent's `…/logs/*.log`.
- Before the fixes it failed on the "(SPEC §12e)" template text (first-loop, roadmap, ticket-factory and others) and
  on the `relations:` hint (image-squeeze, ticket-factory and others).
- With `needs_theta` ignored, the Harris test failed on the long `why`.
- With "(SPEC §9.7)" back, the agents-page daemons test failed.

**Not run here:** the unit suite, the four browser files as a whole, `demo_check`, and an origin/main merge (local
`main` is the branch's base, so there is nothing to merge). The merge queue runs these.
