# diagram-gate-same-everywhere: The clean-drawing gate gives the same answer on every machine

tests/test_diagram_rendering.py::test_every_view_draws_cleanly_and_in_time passes on the coordinator's machine for all examples on main 617734422, and fails on 8 of 23 in the agents' container (alert-triage, big, coordinator, image-squeeze, ops, software-factory, the-job, ticket-factory: lines through parts, overlaps, crossings in a net, drawings up to 1.6x their recorded size). The gate that pins the drawings cannot judge a rewrite while its answer depends on the machine.

Change. Find what differs (fonts and text measurement, browser version, device scale, timing) and make the drawing depend on none of it: pin the font files the pages use (served with the app, not system fonts), the Chromium build, the device scale factor and viewport in the test; measure text from the pinned font. Then re-record the fault ceilings and sizes once, from the pinned setup, in tests/fixtures (layout_known.json, diagram_sizes.json), with the before and after lists in the record.

Done. The test gives the same result in the agents' container, the merge queue's container and a plain local run, on all examples, three runs each.

## Where it stopped

Round 1, 2026-11-25. **Not done: it waits for a font file that cannot be had in the agents' container.** The rest of
the change (serving the font, measuring text from it, re-recording the fixtures) depends on that file, so it was not
built on a guess.

**What differs, found.**
- *Fonts, measured.* The pages draw with the system stack (`--font: system-ui, ...` in style.css; no `@font-face`
  anywhere, and no font file in the tree or its history). Probed in this container (Playwright 1.63.0, the-job's
  whole view, with CDP `CSS.getPlatformFontsForNode`): the diagram's text is drawn in **WenQuanYi Zen Hei** (a CJK
  font that fontconfig gives for `system-ui`), with FreeSans for some glyphs; the side list too is WenQuanYi. Each
  text's drawn width over the width the layout assumes (`CH` = 6.7 px a character, diagram.js) runs from 0.71 to
  1.02 (median 0.83) over 82 texts. On the coordinator's Mac the same stack is San Francisco. So the drawn words,
  the bounding boxes the audit and the sizes read (`getBBox` of #viewport), dynamics.js's measured texts
  (`getBBox`, `getComputedTextLength`), and the canvas's own size on the screen (`svg.getBoundingClientRect()` sets
  the layout's aspect, and the side list's width beside it is set by its words) all follow the machine's fonts.
- *Chromium.* The `browser` fixture falls back to any installed Chrome (`channel="chrome"`) where Playwright's own is
  missing, and the docstring's local command took any Playwright version: the build was not pinned.
- *Device scale.* Playwright's default (1) everywhere; not written down in the test.
- *Timing.* The layout's result does not depend on time on the paths the gate takes (ELK and libavoid are
  deterministic; the worker's 15 s start give-up falls back to libavoid on the page, the same router). The gate's
  own time bound does: coordinator's `open=*` routing took 21.9 s here, past ROUTED_BOUND_MS (20 s).

**Before (this container, 2026-11-25, each example once, run alone, base 617734422 + this branch):** 22 of 23 pass,
including the 7 the definition lists as failing on layout (alert-triage, big, image-squeeze, ops, software-factory,
the-job, ticket-factory); coordinator fails only on `routing open=* took 21880ms` (bound 20000). The 8 failures the
definition names were not reproduced here; the fonts this container's fontconfig resolves (above) are one cause that
changes with the machine's installed fonts and their order, without any change in ergostat.

**Built (tests only, 0 lines outside tests/ and dev/).** tests/test_diagram_rendering.py: the gate test asserts the
pinned Chromium build (`GATE_CHROMIUM` = 153.0.8010.12, Playwright 1.63.0's chromium-1243) and opens its page with
`GATE_PAGE` (viewport 1600x1000, `device_scale_factor` 1); the docstring's command pins `playwright==1.63.0`. Seen
to fail: with `GATE_CHROMIUM` set to 152.0.0.0 the autoscaler case failed on the assert; restored, autoscaler and
the-job pass.

**Left, and why it stopped.**
1. *The font file.* The definition asks for font files served with the app. None is in the tree; this container has
   no network, and the implementor's tools are confined to /work (a read or `ls` of /usr/share/fonts is refused), so
   no font can be brought in honestly; extracting one through a test run would work around that confinement, and was
   not done. Needed from the owner (a host with network): a sans with an open licence and Latin glyphs plus the few
   symbols the diagrams draw (among them ▾ · › × …), regular and bold (the diagram draws 500 and 600 weights), as woff2,
   with its licence, e.g. Inter or Liberation Sans (SIL OFL 1.1). The reversible choice taken: wait for it, rather
   than draw with a font made up here or stretch every text to `CH` with SVG `textLength` (both change every page's
   look, and neither is what the definition asks).
2. *Then, in this gap:* ergostat/web/static/fonts/ with an `@font-face` (`font-display: block`) and `--font`/`--mono`
   naming it first; text measured from it (a canvas `measureText` with the loaded face, after `document.fonts.load`,
   in place of `CH`, refusing to draw rather than measuring a fallback); the gate test waiting for
   `document.fonts.ready` and checking that the drawn text's platform font is the served one (`isCustomFont`), so a
   missing file fails rather than passes on system fonts; RECORD_LAYOUT=1 and RECORD_SIZES=1 once over all examples,
   with the before and after lists here; three runs each in the agents' container, the merge queue's and a plain
   local run (the last two can only be run by the owner or the queue).
3. *Timing.* coordinator's routing bound (21.9 s against 20 s here) is load- and machine-dependent; the definition's
   "same result" includes it. Not changed here (lesson 10: not only raising a bound); a review should say whether it
   belongs in this gap or its own.

## Where it stopped

Parked by the factory (review/diagram-gate-same-everywhere-1, 2026-11-24 16:13).

Done: the cause found and measured (system-ui is drawn as WenQuanYi Zen Hei with FreeSans in the agents' container, 0.71-1.02x of the CH width the layout assumes; San Francisco on the Mac); the gate test pins Playwright 1.63.0's Chromium (153.0.8010.12, checked by an assert that was seen to fail), a 1600x1000 window and device scale 1. Left: a font file in ergostat/web/static/fonts/ with @font-face (font-display: block) named first in --font/--mono; text measured from the loaded face in place of CH; the gate test waiting for document.fonts.ready and checking the drawn text's platform font is the served one; RECORD_LAYOUT=1 and RECORD_SIZES=1 once over all examples with before/after lists; coordinator's routing time judged (load or code); three runs in each of the three places. Why it stops: the tree holds no font file and the agents' container has no network, so the font cannot be brought in honestly from here.

## Where it stopped

Round 2, 2026-11-25 (unparked: the coordinator added Inter on this branch, baaf79282, and decided that the font is for
the browser tests only and the app keeps its system stack). **The font, Chromium build, window and device scale are
pinned, and the fixtures are re-recorded. Left: coordinator's routing time, which depends on the machine's speed, and
the runs in the queue's container and a plain local run, which only the queue and the owner can do.**

**Built (tests and fixtures only: 0 lines outside tests/ and dev/).** tests/test_diagram_rendering.py:
- `gate_page(browser)`: a page with `GATE_PAGE` (1600x1000, device scale 1) and an init script (`FONT_SCRIPT`) that,
  before any of the page's scripts run, makes `FontFace`s named GateInter from the bytes of
  tests/fixtures/fonts/inter-latin-{400,600,700}-normal.woff2 (inlined as base64, so nothing is fetched and no route
  can miss), adds them to `document.fonts`, and adds a stylesheet setting `--font: GateInter, sans-serif` and
  `--mono: GateInter, monospace` (`!important`) on `:root`. Every font-family in the app's CSS goes through these two
  variables (style.css, plots.css, panel-editor.css; buttons, inputs and selects `font: inherit`), and the canvases
  read `--font` too. A FontFace made from bytes has its status set at once: the script records the three statuses as
  it makes them, and they read `loaded`, so no text is measured in a fallback font first. This is why
  `document.fonts.ready` is not awaited.
- `font_unpinned(pg)`: the faces must be `loaded`, and for every element on the page with words of its own
  (its text and its `::before`/`::after` content), Chromium's own record of the fonts it drew them in
  (CDP `CSS.getPlatformFontsForNode`) must be Inter alone when all the characters are in Inter's latin subset, and
  must include Inter when only some are (`Last 1h ▾`). Words with no character in the subset (`⋯`, `⤓`) may be drawn
  in any font.
- The gate test opens its page with `gate_page` and asserts `font_unpinned` is empty after the first draw. It still
  asserts the Chromium build (`GATE_CHROMIUM`). test_every_product_goal_is_drawn_in_product_and_its_stock_panel_names_the_same
  also reads layout_known.json, so it uses `gate_page` too (passes).
- Text measurement: the layout's own width estimate is `CH` (6.7 px a character), a constant that does not depend on
  the machine. What the page measures (`getBBox`, `getComputedTextLength`, the side list's width, the canvas's size)
  is now measured in Inter. The app's code is unchanged, as the coordinator decided.
- Choices, all reversible: the other page tests in the four browser files still draw in the machine's fonts, because
  only the gate and the test above read the recorded fixtures (`gate_page` is the one call to switch any of them).
  Weight 500, which the diagram uses, is drawn with the 400 face (the CSS matching rule; no 500 file was supplied).
  Characters outside Inter's latin subset (▾, the arrows, ⋯) still fall back to the machine's sans-serif. They are a
  few single glyphs, and the check above names any text that is wrongly in a fallback font.

**Seen to fail (lesson 9).** With the stylesheet line disabled, the autoscaler case failed: `'ergostat' drawn in
['WenQuanYi Zen Hei']`, and 9 more texts were listed. With the font bytes cut (a broken file), it failed: `Inter's faces are
['error', 'error', 'error'], not loaded`. Both breaks were then removed. Round 1's Chromium assert was seen to fail then.

**Before (this container, pinned setup with Inter, the fixtures as on main 617734422, each example once):** 22 of 23
pass; coordinator fails only on `routing open=* took 21579ms` (bound 20000). main's fixtures (recorded in system fonts)
still pass here under Inter, because the size rule judges only drawings too big to fit (fit < 1), and no
ceiling was exceeded.

**Re-recorded once** (RECORD_LAYOUT=1 RECORD_SIZES=1, every example, this container, pinned setup).
layout_known.json, the ceilings that changed (all the others are the same; known critical faults are the same, one:
small-requests `[system=regressions] flow-excursion` on regressions-draft-revert-taken):

| example | satellite-far before -> after | valve-orientation-mismatch before -> after |
|---|---|---|
| big | 18 -> 16 | 4 -> 0 |
| coordinator | 30 -> 30 | 4 -> 1 |
| image-squeeze | 27 -> 27 | 3 -> 1 |
| small-requests | 31 -> 27 | 5 -> 1 |
| ticket-factory | 15 -> 15 | 2 -> 0 |
| daemon-demo, todo-list | (absent, read as 0) -> 0 | (absent) -> 0 |

No ceiling rose. diagram_sizes.json, per example (the ratio of each view's area and fit, new over old; `whole` is
[width, height, fit]):

| example | views | area ratio | fit ratio | whole before -> after |
|---|---|---|---|---|
| alert-triage | 8 | 0.81-1.14 | 0.94-1.00 | [599, 292, 2.072] -> [599, 296, 2.072] |
| autoscaler | 0 -> 6 | (new) | | |
| backups | 4 | 1.00 | 1.00 | unchanged |
| big | 16 | 0.69-1.02 | 0.98-1.16 | [520, 504, 1.71] -> [520, 512, 1.684] |
| coordinator | 16 | 1.00-1.09 | 0.89-1.00 | [572, 312, 2.168] -> [572, 320, 2.168] |
| daemon-demo | 0 -> 2 | (new) | | |
| deps | 6 | 1.00 | 1.00 | unchanged |
| disk-space | 4 | 1.00 | 1.00 | unchanged |
| docs-fresh | 6 | 1.00-1.02 | 1.00 | [640, 571, 1.509] -> [651, 571, 1.509] |
| file-queue | 4 | 1.00 | 1.00 | unchanged |
| first-loop | 4 | 1.00 | 1.00 | unchanged |
| git-hygiene | 4 | 1.00 | 1.00 | unchanged |
| image-squeeze | 12 -> 14 | 1.00-1.28 | 0.92-1.02 | [955, 597, 1.298] -> [1038, 704, 1.194] |
| ops | 10 | 0.96-1.92 | 0.75-1.00 | [552, 232, 2.246] -> [552, 368, 2.246] |
| plain-crontab | 4 | 1.00-1.09 | 0.99-1.00 | [2003, 1184, 0.619] -> [2032, 1274, 0.61] |
| roadmap | 6 | 1.00 | 1.00 | unchanged |
| small-requests | 16 | 0.83-1.58 | 0.88-1.21 | [576, 574, 1.502] -> [587, 574, 1.502] |
| software-factory | 12 | 0.89-1.44 | 0.68-1.05 | [553, 332, 2.243] -> [553, 344, 2.243] |
| talking-scripts | 4 | 1.00-1.02 | 0.98-1.00 | [2003, 1184, 0.619] -> [2035, 1191, 0.609] |
| the-job | 26 | 0.71-1.58 | 0.82-1.67 | [884, 710, 1.214] -> [905, 718, 1.201] |
| this-mac | 4 | 1.00 | 1.00 | unchanged |
| ticket-factory | 16 | 1.00-1.05 | 0.97-1.00 | [552, 352, 2.246] -> [552, 368, 2.246] |
| todo-list | 0 -> 6 | (new) | | |

**After: three runs in the agents' container** (every example, from the committed fixtures, each run in 8 calls of at
most 3 examples): each run gave the same result. 22 of 23 pass. coordinator draws with no layout, size or font fault
and fails only on its routing time: `routing open=* took` 20945, 21970 and 22746 ms (bound 20000; 21579 and 20958 ms in
the before and record runs).

**Left.**
1. *coordinator's routing time.* It is past ROUTED_BOUND_MS in every run here (20.9-22.7 s, with coordinator run alone
   in its call), and under it on the Mac. This is libavoid's routing in a worker, so the time depends on the machine's
   speed, not on fonts or the drawing. As a bound in wall time, it cannot give the same answer on a slower machine.
   Not changed here: raising the bound alone is what lesson 10 rules out, and the reversible choice is to leave it.
   The options for the owner: (a) a bound relative to a calibration workload timed on the same machine; (b) a larger
   bound for HEAVY examples only, with a separate perf gap to bring coordinator's `open=*` routing down; or (c) routing
   time judged in its own test, apart from the clean-drawing gate. Until one is chosen, the gate's layout answer is the
   same here as on the Mac, but its time answer for coordinator is not.
2. *The other two places.* Three runs each in the merge queue's container and in a plain local run were not run.
   They cannot be run from here, and the queue and the owner run them. The definition's Done needs them.

## Where it stopped

Round 3, 2026-11-25. **The routing bound is now relative to the machine, and the gate passes on all 23 examples in
three runs here. Left: the measurement in the other two places, asked for by name below; it can only be run by the
coordinator and the owner.**

**The findings of review 2, each answered (lesson 12).**
1. *coordinator's routing time against a fixed 20 s (tests/test_diagram_rendering.py:52,256).* Fixed in the branch, as
   the review suggested: the bound is relative to a calibration workload timed on the same machine (below).
2. *The queue's and a local run are not asked for by name.* Asked for below.

**What the time depended on, measured first** (this container, Playwright 1.63.0's Chromium, the gate's page, two
routings each, `TIMED`'s full routing in ms):

| workload | routing (ms) | parts / lines |
|---|---|---|
| stress model 16x6 (`big_model(16, 6)`), `open=*` | 16814, 16765 | 417 / 526 |
| stress model 24x8, `open=*` | 118056, 122098 | 817 / 1030 |
| coordinator, `open=*`, in Inter (the gate's font) | 24493, 22987 | 129 / 188 |
| coordinator, `open=*`, in the system fonts | 23569, 24213 | 129 / 188 |

So the font plays no part in coordinator's routing time. The time follows the machine and its load: the fixed 20 s was
about 1.2 times the stress model's routing here. On the Mac it held coordinator just under it, and records of other gaps
show 20-44 s under parallel load. coordinator is also costly for its size: 1.4 times the stress model's time with a third
of its lines. A perf gap of its own could bring that down. That is not this gap's.

**Built (tests only: 0 lines outside tests/ and dev/).** tests/test_diagram_rendering.py:
- `routing_pace(browser, tmp_path)`: the *pace*, libavoid's routing of the generated stress model `PACE_MODEL` (16x6,
  everything open) on the gate's pinned page. It is timed with `TIMED`, the same as each example's views, in the same
  browser, just after the example's views. A slower machine, or a busier one (the queue's `-n 4`), slows both alike.
- The gate test asserts the slowest view's routing is under `ROUTED_PACES` (1.75) paces, in place of
  `ROUTED_BOUND_MS`. The failure names the time, the paces and the pace. An example whose slowest routing is under
  `PACE_SKIP_MS` (4 s) is not paced, which saves about 17 s for each of the small ones. That gives the same answer
  wherever the pace is over 4 / 1.75 = 2.3 s, which is 7 times faster than this container.
- Why 1.75 (a choice, reversible as one constant): coordinator routes in 1.31-1.46 paces here (two measurements above
  and the break below), and the fixed 20 s was about 1.2 paces here. 1.75 leaves about 20% above coordinator's highest.
  Only a doubling of an example's routing relative to the stress model fails it. That is what the bound was for: "to
  catch the layout going quadratic", now for one drawing's structure rather than for the machine. Said plainly
  (lesson 8): a change that slows *all* routing alike (the stress model too) passes this gate. The stress test
  (`test_a_big_tangled_model_lays_out_in_time_and_cleanly`, still on `ROUTED_BOUND_MS`, 16.8 s here against 20 s)
  is what would show that. It and the other test that reads `ROUTED_BOUND_MS` (line 7746) are outside this gate and
  unchanged.
- `LAYOUT_BUDGET_MS` (the first draw, 2.5 s) is still absolute. It passed in every run here. Its margin was not read
  (the runs print only on failure), so it is not claimed to hold the same everywhere.

**Seen to fail (lesson 9).** With `ROUTED_PACES` at 1.2 (the old 20 s here), coordinator failed:
`coordinator: routing open=* took 22429ms, 1.31 paces (the stress model's 17142ms here; the bound is 1.2)`. Restored
to 1.75.

**After: three runs in the agents' container** (every example, the fixtures as committed in round 2, each run in 8
calls of at most 3 examples, `named_tests.py` under `suite_watch.py`): **23 of 23 pass in each run.** Which examples were paced was not printed (the runs print
only on failure). The three calls that hold coordinator, image-squeeze and the-job took 110-143 s, and the other five took 32-50 s,
which suggests those three were paced. main has nothing newer than this
branch's base (`git log factory/diagram-gate-same-everywhere..main` is empty), so there was nothing to merge.

**Left: the measurement in the other two places (the definition's Done), asked for by name.**
- The merge queue's container, from the coordinator, on this branch's head:
  `python3 dev/bin/manage.py measure-runs gap/diagram-gate-same-everywhere --runs 3 --load 4 --tests "-n 4 tests/test_diagram_rendering.py::test_every_view_draws_cleanly_and_in_time"`
  (`-n 4` and the load as the queue's browser suite runs it; coordinator stays `serial`, and its pace with it).
- A plain local run, by the owner on the Mac, three times:
  `uv run --with playwright==1.63.0 python -m pytest -q tests/test_diagram_rendering.py::test_every_view_draws_cleanly_and_in_time`.
  On the Mac, `GATE_CHROMIUM` asserts the same Chromium build, so a run on another build fails at once rather than
  judging other drawings.
Not run here: these two, the unit suite, and the four browser files whole (the queue runs them).

**The entry.** This record has no `## Entry`. The rules allow only this section to be appended, and the change is in
the tests alone, with nothing a user sees. So no line for docs/GAPS.md was written. If the queue needs one, the
coordinator can add it.
