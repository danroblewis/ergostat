# Diagram notation: owner items 6, 8, 9 (designer's notes, 2026-11-22)

Screenshots (DESIGN/shots/): plan-notation-sf-product-dyn.png, plan-notation-sf-product-dark.png,
plan-notation-sf-product-blocks.png, plan-notation-sf-home.png, plan-notation-sf-dyn-open.png,
plan-notation-sf-blocks-open.png, plan-notation-job-openall-dyn.png, plan-notation-job-openall-blocks-fit.png (blank),
plan-notation-big-api-dyn.png, plan-notation-big-home.png, plan-notation-sf-openall-fit.png.

Live factory (:8798): unreachable during this session. GET / timed out at 60 s, `/static/style.css` at 20 s, and
`/api/graph?view=dynamics` never answered in 3 min. Whatever the cause, the server stops answering at all,
including for static files. That belongs with owner item 2. I could not see the notation at that size there,
so I used `big` and `software-factory` instead.

## What a user sees

**One ink for everything (item 8).** In Dynamics, pipes, stocks, valves, connectors, loop markers, loop names
and polarity signs are all drawn in `--sd-ink` (style.css: `.sd-connector` is 1.1 px of sd-ink, and the pipes are
8 px of sd-ink). The only other colour is the accent, used for what is pointed at. On software-factory › product
(plan-notation-sf-product-dyn.png), 18 loop markers, their names and about 25 connectors are drawn at the same
value as the six stocks and their pipes. The material path (signups → users → churn) is no easier to pick out
than the information around it. Dark mode has the same problem (plan-notation-sf-product-dark.png). DESIGN.md
already says to follow Tufte ("thin, light lines for structure so the data reads on top") and Refactoring UI
("de-emphasise to emphasise"). The drawing does not do this yet. The tokens have no second tone: `--sd-muted`
is a text colour.

**Group boxes (item 8).** There are three problems:
- In Blocks, an open subsystem frame is a full rectangle in `--muted` at 1 px, close to the wires' 1.2 px ink.
  Wires cross frames and run beside them, and the frame reads as one more wire
  (plan-notation-sf-blocks-open.png: product's and factory's frames, with y_m lines running just inside and
  across them). blocks.js already has to push lines off frame edges "or it would read as a bus on the frame"
  (blocks.js:453).
- In Dynamics, an open sector is a tinted ground with no outline. Tints add up when sectors nest (factory around
  delivery and intake in plan-notation-sf-dyn-open.png), and the sector's edge is hard to see on a large
  canvas (plan-notation-job-openall-dyn.png).
- A closed system (module) is a heavy 1.4 px ink rounded box with nearly the same weight as a stock (1.6 px). At
  the top level the system boxes are the heaviest marks on the page (plan-notation-sf-home.png).

**MIMO in Blocks, not in Dynamics (item 6).** Blocks has a mux bar, a bold vector line with a slash and a count,
and a demux bar (plan-notation-sf-product-blocks.png: u_deployed and d go into the mux, then a "2" vector into
P_product, then a "3" vector into the demux and on to y_bugs-live, y_missing-ops and y_users). This is drawn
server-side (blockdiagram.py: mux, demux, bus). Dynamics has nothing like it:
- At the top level of software-factory, seven separate curves cross the gap between product and factory, with
  their signs stacked where they arrive (this is the problem in Q25).
- Inside product, five or six connectors from distant parts converge on the churn valve, and four converge on
  regressions.

**The default side panel (item 9).** With nothing selected, the side panel shows, in this order (diagram.js
renderSide): "Not running", charts, Needs attention (up to 6 entries, each several lines), Suggestions,
charts again, the Feedback loops list (18 to 39 rows), "The model: edited …", and finally "How to read it".
That last section is a `<details>` that the code closes after the first visit (`legendBox` writes
`ergostat.legend=closed`). On big, Needs attention has 26 entries and Feedback loops has 35 rows, so the legend
is several screens down and closed. The Blocks legend (`blocksLegend`) lists every symbol whether or not it is
drawn. The Dynamics legend lists only what is drawn (its `has()` filter).

## Where the owner and the review agree, conflict or combine

- **Tones and the review.** The review and DESIGN.md keep the diagrams monochrome, with colour only for status
  or for what is pointed at ("Blocks stays monochrome"). A second tone of the same ink is still monochrome, so
  the owner's request fits. In Blocks, status stays a word and a bold e (R4.7). The tone carries importance,
  never status.
- **Off systems and outline weight.** Q27 (filed) draws a heavier outline on a system that holds an off goal.
  This combines with the owner's lighter frames: by default a closed box's outline is in tone 2, and a box with
  an off goal gets the full-ink, heavier outline. The heavy outline then means something.
- **modelling.** Q13 (filed) gives the modelling box a dashed outline. In the new frame grammar, modelling's
  hairline is dashed and its corners stay solid.
- **Bus in Dynamics, conflict.** The intent says "never mix the notations", and Dynamics is meant to follow
  Sterman. A bus is not in Sterman's notation; the owner asks for it explicitly.
  - Resolution: a confluent bundle in SD style. Connectors that run between the same two systems (or into one
    part from far away) share one trunk in the connector tone. Each branch keeps its own arrowhead and its
    polarity sign near its own end, so the SD reading at each end does not change. There are no mux or demux
    bars: those are blocks and stay in Blocks.
  - The slash and count on the trunk is the one sign borrowed from Blocks, and the Dynamics legend defines it.
  - Whether the trunk carries slash-and-count or a plain "3 links" label is a question for the owner.
- **Bus combines with R8.8.** R8.8 routes long connectors leaving an opened system along its frame. A bus
  leaving a sector does exactly that.
- **Bus and Q25.** Q25 (filed) puts each sign beside its own arrowhead. The bus keeps that rule: a branch is the
  link's own unshared segment, and its sign sits there. Q25 has to be built so that a bundled link's sign
  stays on its branch. Q25 makes the signs readable at the top level, and the bus removes most of the crossings
  that caused the problem.
- **Bus and R5.4.** R5.4 (fold minor loops) reduces the clutter of connectors and markers from the other side.
  The two complement each other.
- **Legend first, combined with the review.** Q42 (filed) turns the side list's Needs attention into three
  groups. Q43 (filed) puts "what waits for me" one step from every page, in the header. R1 puts goal status on
  the boxes. With those in place, the default side panel does not need to repeat the alarms. Q42's three groups
  should live where Q43 sends the reader (the header list and the Goals page), and the side panel keeps a
  one-line count that links there.
  - Q80 (filed) makes suggestions wait for a verdict. Suggestions move into the goal's evidence panel and leave
    the default panel.
  - Q62 and Q64 (filed) change the wording of the loop list. The list stays, folded, under the legend.
  - Q68 (filed) and Q35 (filed) add legend rows. Q70 (filed) puts the legend into the export. The legend's rows
    should come from one source used by the side panel, the export and the Guide.
- **Dependencies on other clusters.** Owner items 5 and 7 (stale lines after toggles and drags) and 10 (a faster
  layout, and re-arranging) touch the same routing. A bus has to be redrawn on drag like any other line. The
  bus build gap should follow the fix for stale and dragged lines.
- **Seen in passing.** the-job › Blocks › Open all systems was still a blank canvas after 10 s and a Fit
  (plan-notation-job-openall-blocks-fit.png). This belongs to items 2 and 10, and R8.1 (never blank).

## Gaps proposed

1. `diagram-line-tones`: a second tone of each ink, with information links, secondary signals and loop names in it.
2. `diagram-frames-corners`: system frames drawn as corner marks joined by a hairline, in both views; a closed
   system's outline in tone 2, and heavier only when it holds an off goal.
3. `diagram-side-panel-legend-first`: the default side panel opens with the symbol legend of what is drawn,
   then one summary line, then the folded loop list. One source for the legend rows (side panel, export, Guide).
4. `dynamics-connector-bus-proposal` (proposal): when connectors are bundled, how a bundle looks, how it
   behaves when selected, traced, dragged and in Flows only, and the measured acceptance checks. It ends with a
   prototype on software-factory and big.
5. `dynamics-connector-bus`: build what the proposal settled.

Order: 1 → 2 → 3 (3 can start in parallel with 1, adding the tone and frame rows when they land). 4 starts now,
in parallel. 5 waits for 4, 1, 2, and the stale-line fix from items 5 and 7.
