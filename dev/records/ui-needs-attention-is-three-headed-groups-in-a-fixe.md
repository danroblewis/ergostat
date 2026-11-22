# ui-needs-attention-is-three-headed-groups-in-a-fixe: Needs attention is three headed groups in a fixed order

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q42 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram side list

**The problem:** 'Needs attention 4' beside '2 loops off': one list mixes goals that are off, asks of a person, requests and model notes, told apart only by red or amber. On big 24 requests bury the one alarm.

**The change:** Three headings, always in this order, each with its count: 'Waiting for you 3', 'Goals off 2' (the system's first, modelling's after a rule), 'Model housekeeping 25' (collapsed). Each entry starts with its state word ('off ·', 'unknown ·') so colour is not the only cue. The count in the header equals the 'Goals off' group.

**User stories it serves:** E1, B2, H5

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8791/ the side list has three headings in that order, each ending in a number; the 'Goals off' number equals the header's; no entry's kind is conveyed only by colour (each begins with a state or kind word).

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
