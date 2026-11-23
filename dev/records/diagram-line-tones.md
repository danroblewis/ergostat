# diagram-line-tones: A second tone of each ink: information links and secondary signals drawn lighter than the material path; the colour rules written once

depends-on: []

Problem: the owner: 'only two colours ... a second tone of each colour for non-critical lines and information links'. Dynamics draws stocks, valves, pipes, modules, 1.1 px connectors, heads, loop markers, names and signs all in --sd-ink (ergostat/web/static/style.css:510-528); Blocks draws every wire and bar in --ink (style.css:454-476). No second-tone token exists (--sd-muted is a text colour). On :8796 ?system=product about 25 connectors and 18 loop markers have the same value as the six stocks and their pipes (shots/plan-notation-sf-product-dyn.png, -dark.png, plan-notation-tf-dyn-open-dark.png). DESIGN.md already asks for 'thin, light lines for structure'. Tones of one ink keep decision 2 (Blocks stays monochrome; tone carries importance, never status). Three later gaps would otherwise give the accent three meanings (a traced loop, an off goal, selection).
Change: tokens in both themes' token block: --sd-ink-2 (sd-ink mixed toward the paper: about 55% light, 50% dark; contrast 3.0-4.5:1 on the paper), --ink-2-line for Blocks, --accent-2 (the accent's lighter tone). Dynamics: connector lines and heads, loop names, shadow variables and stubs use tone 2; stocks, pipes, valves, clouds, part names and values, polarity signs and the loop marker stay full ink; the connector from a goal's gap to the flow it drives stays full ink (a class on it). Blocks: each edge group gets a bd-<signal.what> class (blocks.js:821); wires with what=record, the bus bars, wires to or from port pills and disturbance inputs use tone 2; r, e, u, y, y_m stay ink. A lit (selected or traced) loop draws pipes in --accent and connectors in --accent-2. Legends (SD_LEGEND dynamics.js:450, the Blocks legend blocks.js:1099, export.js:58-68, the SD export legend dynamics.js:753) gain 'a lighter line: information, not material', and the Guide frame that shows connectors is updated. DESIGN.md's Colour section is rewritten as the one place for the rules: (i) the accent and its tone mean selection or trace, in both views, and nothing else; (ii) --bad together with the printed word means a goal is off, in Dynamics and on lists only; Blocks carries status in text and weight, never colour; (iii) tone carries importance, never status. It drops the stale 'action purple' and 'green holding' (DESIGN.md:146-148).
Definition of done:
1. The tokens exist for light and dark; tests/test_style_tokens.py passes; no colour is written outside the block.
2. In Dynamics every .sd-connector stroke and .sd-head fill computes to --sd-ink-2 except each goal's gap -> flow link; every pipe, stock and valve stroke and every .polarity fill computes to --sd-ink.
3. In Blocks a record wire's stroke differs from a reference or error wire's.
4. Tone 2 has contrast between 3.0:1 and 4.5:1 on the paper and the ink at least 10:1, in both themes.
5. Exported SVG and PNG keep the tones; /guide?frame=2 and frame=12 render in both themes.
6. DESIGN.md's Colour section states rules (i)-(iii).
Files: ergostat/web/static/style.css, dynamics.js, blocks.js, export.js, ergostat/guide.py, docs/DESIGN.md, tests/test_style_tokens.py, tests/test_diagram_rendering.py.
Acceptance tests: check `line-tones` on :8796 ?system=product and ?view=blocks&open=product,factory in light and dark (getComputedStyle per class; structure only); a token contrast unit test; the render audit over every example and view passes.
Budget: 100 net lines.

Milestone: diagram-notation. Owner items: 8 (line tones). From the owner's list and the design review of 2026-11-22.

## Where it stopped

Round 1: built (commit 0c7e68af), 36 net lines of code. Decisions taken alone, each the most reversible:
- "A goal's gap -> flow link": a connector from a gap (role gap) straight into a valve or disturbance gets the class
  sd-drive and stays full ink. A gap that drives its flow through an auxiliary (a block's output) keeps tone 2 on that
  link; the chain is not followed. On software-factory ?system=product no gap is drawn at all, so
  test_line_tones_information_lighter_than_the_material_path checks the full-ink case on first-loop (two such links).
- ?view=blocks&open=product,factory has no record wire, and no r or e wire (no collector, no loop closes inside). There
  the test checks that u, y and y_m are ink and that port and disturbance lines are tone 2. Definition of done 3 (a record
  wire against r and e) is checked on the-job ?view=blocks&system=incidents, which has a collector.
- The tone hexes were worked out by hand from WCAG luminance, because scratch scripts outside the repository were
  refused: --sd-ink-2 #84898e / #6f7479 (3.5 / 3.7:1), --ink-2-line #858a90 / #71767b, --accent-2 #5f90cf / #4f77a8. The
  unit test checks the 3.0-4.5:1 window and the ink at 10:1 or more, not the exact mix percentage.
- Rule (i) is stated for the two diagram views. The page chrome's accent for links and focus is unchanged.
- The text of shadow variables and stubs moved from --sd-muted to --sd-ink-2 (.k-terminal only; a cloud's name keeps
  --sd-muted). On a lit loop the heads take --accent-2 with their connectors, and polarity signs stay --accent.
- export.js's control legend gains the row. Its "loop holding" and "off" rows are left alone (outside this gap). A
  Blocks export draws no legend (unchanged).
- Exports: the test checks that the saved SVG text carries both resolved tones. The PNG is drawn from that same text and
  was not checked pixel by pixel.
- The Guide's "links" frame (frame 4) now says a link is information, drawn lighter than the pipe.

Tests run on the branch: tests/test_style_tokens.py and tests/test_guide.py pass (the new contrast test was seen to fail
with --sd-ink-2 set to the ink). test_line_tones_information_lighter_than_the_material_path[light,dark],
test_flows_only_export_legend_lists_only_what_is_shown and test_the_guide_draws_every_frame_live_and_in_a_snapshot pass.
The line-tones test was seen to fail on three breaks: no sd-drive, record wires in ink, connectors in ink. ruff is clean.
Render audit (test_every_view_draws_cleanly_and_in_time and
test_the_control_view_draws_every_example_cleanly_as_a_block_diagram): 40 passed, 2 failed, the same two in each of
two runs: [coordinator] and [image-squeeze], each on the libavoid routing bound only ("routing open=* took 36361ms" /
"36107ms", bound 20000). Every layout-fault check in them passed. I think the branch did not cause these: it changes
colours and adds classes, not geometry, layout or routing. That is unproven: the same two cases were not run on main
(the checkout of main's static files was refused). The merge queue's run on clean main must settle it. Not run: the unit
suite and the other three browser files (left to the factory, as the rules say).

Round 2: the merge of main (2f08c24e) is finished (commit 945d24a4). Each conflict keeps both sides:
- blocks.js: the bd-<what> and bd-aside classes with main's hop crossings (bdEdgeContent(e, pts, cross)). Main made the
  Blocks legend list only what is drawn, so the lighter-line row is listed when a record wire, a port or a disturbance
  is drawn.
- dynamics.js: sd-drive sits next to main's driven-by (dashed) class. sdDrives follows main's sdPlaceSigns. The legend's
  new "dashed" and "?" connector samples are drawn in --sd-ink-2 and the polarity text stays in ink. The nounit row is
  kept.
- style.css: the tone-2 connector rules keep main's dashed driven-by rule. DESIGN.md takes main's text for the loop
  state on Blocks' error label, which agrees with rule (ii).
- tests: both sides' tests are kept. Three changes to the tests follow from main:
  (a) A saved picture is now drawn light whatever the theme (export-light), so the line-tones test compares the file
  with the light tokens.
  (b) Main draws a loop of unknown polarity (.pol-unknown) in --sd-muted, which is outside this gap, so the full-ink and
  tone-2 checks on loop markers leave those out.
  (c) In main's PNG export test the "dark pixel" bound (r+g+b < 420) sat just above tone 2's own value (#84898e, 411).
  The antialiased tone-2 loop names hardly counted, so the bound is now < 500 (the ink or its second tone).
- The round-1 line "A Blocks export draws no legend" is stale: main's export now carries the Blocks legend, and that
  legend includes the new row.

Tests run after the merge: ruff is clean and tests/test_style_tokens.py passes (15). tests/test_guide.py and
test_flows_only_export_legend_lists_only_what_is_shown pass. test_line_tones_information_lighter_than_the_material_path
[light, dark] passes. The changed parts of that test were not broken on purpose to watch them fail this round.
test_the_exported_png_shows_every_loop_name_the_values_and_its_legend_on_white_in_dark_mode passes its Dynamics half.
Its Blocks half fails on `len(rows) > 10`: product's Blocks legend has 7 rows. That assertion came in with 5f4090ba,
and the conditional legend came in with 6b822868. Those two commits are parallel on main, so I think the test fails
on main too (about 6 rows, since this branch adds one). That is unproven: the scratch worktree of main
(`git worktree add --detach /tmp/mainwt main`) was refused. The fix is outside this gap.
Render audit: 40 passed, 6 failed, of which 5 were named in the output: [coordinator] and [image-squeeze] on the
routing time bound (20121 and 22588 ms, bound 20000), and [autoscaler] satellite-far 6 (ceiling 0), [the-job]
valve-orientation-mismatch 3 (ceiling 2), [ticket-factory] satellite-far 15 (ceiling 14). Before the merge every
layout-fault check passed. The branch changes no geometry, so I think these come with main's layout changes. That is
also unproven on clean main, which the queue must settle. Not run: the unit suite and the four browser files in full.
