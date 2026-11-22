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
