# ui-what-waits-for-me-is-one-step-from-every-page-an: What waits for me is one step from every page, and first on a phone

depends-on: [ui-needs-attention-is-three-headed-groups-in-a-fixe]

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q43 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** header on all pages; /loops at 390 px

**The problem:** The waiting requests exist only on the Diagram page's side list; on a phone '/' opens Loops, which has no list at all, and on the Diagram the list starts at y=665.

**The change:** Beside the goals count the header shows 'N wait for you', a link to /diagram#waiting, which scrolls to and focuses the 'Waiting for you' group. At phone width it is the first thing in the header.

**User stories it serves:** E1, H4, A4

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On /items, /agents, /loops and /record at 1440 and 390 px a link containing 'wait for you' with the right number is in the first 200 px of the page; following it shows the 'Waiting for you' heading inside the viewport.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Parked by the factory (implementor, 2026-11-22 14:16).

Stopped on its last attempt by RuntimeError: claude: success: You've hit your weekly limit · resets Nov 24, 3am (UTC)

```
Traceback (most recent call last):
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 166, in main
    return build(cfg, given, began)
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 221, in build
    got = fac.session(cfg, "implementor", prompt, work)
  File "/Users/user/ergostat-live/instance/dev/bin/fac.py", line 669, in session
    raise RuntimeError(f"claude: {out.get('subtype')}: {str(out.get('result'))[:300]}")
RuntimeError: claude: success: You've hit your weekly limit · resets Nov 24, 3am (UTC)

```
