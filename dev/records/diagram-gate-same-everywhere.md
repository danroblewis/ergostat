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
