# Layout rules

Common-sense rules for how ergostat lays out its three diagrams: the stock-and-flow diagram (Dynamics), the block
diagram (Blocks) and the process map (Process). Each rule is stated plainly, with why it matters and a measurable
form. Each also has a detector in `tests/layout_rules.py`, over a diagram's drawn geometry (every part's box,
every line's points, every word as drawn, the loop markers, the open systems' frames, and in Blocks the take-off
dots, the hops and the vectors' slashes).

The rules are ordered by how bad a violation looks, worst first. A **critical** violation is one a reader notices
at once and reads wrongly: a flow that seems to go somewhere it does not, or a part hidden under another. A
**major** one makes the drawing look careless. A **minor** one costs a reader a moment.

How they are checked: the detectors are tested on geometry written by hand (`tests/test_layout_rules.py`). The
geometry reader and the corpus run that measured the old page (`tests/layout_geometry.js`, `tests/layout_corpus.py`)
were removed with it (2026-11-25), when the React page (`ergostat/web/ui`) became the page; reading the React
diagram's geometry is not written yet.

<!-- COUNTS -->

## The rules

### 1. flow-excursion (critical, Dynamics)

**A flow takes the short way between the two things it joins.** Its pipe is at most 1.3 times the Manhattan
distance between its two ends, plus 80px (a valve's width and a jog). A flow back up a chain (rework), or one
between stocks stacked one over the other, runs in a lane beside them and is allowed 240px more (there and back).

*Why:* in system dynamics the pipe is the material, the conserved quantity moving from one stock to another
(Sterman, *Business Dynamics*, ch. 6). A pipe that runs across the diagram and back reads as a flow through
everything it passes, and the eye follows the long line instead of the short relation. This is the owner's first
example: a stock right next to its cloud, with the valve placed under ten other parts, so that a fat pipe runs
down through them and back up.

*Measured:* the length of the pipe in, through the valve, and the pipe out, against `|dx| + |dy|` between its two
end points.

### 2. line-through-part (critical, all views)

**No line passes through a part that is not one of its ends.** No segment of any line lies inside another part's
box (shrunk by 3px) for more than 4px.

*Why:* a line through a part reads as joined to it. A pipe through a stock reads as a flow into it.

### 3. part-overlap (critical, all views)

**No part lies on another.** The boxes (shrunk by 2px) share no area.

*Why:* a hidden part is a missing part.

### 4. valve-between-ends (critical, Dynamics)

**A valve lies between the two things its flow joins.** Its centre is inside the box spanned by its two pipe
ends, grown by 30px. When the ends are in line, the valve is on that line.

*Why:* a valve is the tap on a pipe (Forrester; Sterman). Placed off to one side, it turns the pipe into a detour
that runs out to the valve and back. This is the owner's second example: a valve an unreasonable distance from
its stock, with the cloud off in a corner.

*Measured:* the distance from the valve's centre to that box. Over 120px is critical; over 40px is major. A valve
outside the box but on a pipe no longer than rule 1 allows (in a lane beside its ends) is minor: what matters is
the pipe it makes.

### 5. cloud-by-valve (major; critical past 220px, Dynamics)

**A cloud sits next to its valve.** The gap between their boxes is at most 70px, about one layout step (ELK's
56px between layers, plus a margin).

*Why:* a cloud is not a part of the model. It marks where the boundary is crossed (a source or a sink) and
belongs to its one flow. A cloud far away reads as the end of some other flow, or as a part of its own.

### 6. line-overlap (major; critical for two pipes, all views)

**No two lines share a track.** Two lines of different nets never run along each other for more than 20px. Lines
from one point, or into one point, form a net and may share a track.

*Why:* lines on one track become one line, and the reader cannot tell which one goes where.

### 7. frame-membership (major, all views)

**A part sits inside each open system it belongs to, and inside no other.** Frames either nest or stay apart.

*Why:* an open system's outline is a claim about what is in it.

A frame is drawn by its corners in every view (L marks joined by a hairline, no fill, its name on the top edge),
so a line never runs along a frame's edge (Blocks moves such a stretch at least 10px off it): on the hairline it
would read as part of the frame. The frames read from the page (`tests/layout_geometry.js`) are the hairline
rectangles, `rect.frame`, as laid out.

### 8. valve-orientation-mismatch (major, Dynamics)

**A valve faces the way its pipe runs.** No pipe leaves a valve by a stub (under 16px) and then turns at once to
run across the valve's axis: that is a zig-zag through a valve facing the wrong way.

*Why:* a valve is a simple, common part, free to turn or flip. Its pipe should enter and leave it straight. A
level valve with its stock directly below forces the pipe to zig-zag through it.

*How it is now made:* the router routes each flow whole, from end to end, through the valve's middle as a point
(libavoid's checkpoints, no valve in the way). It turns each valve to the way the flow runs there, and only then
routes every line. So this rule holds by construction, after the layout and after every drag.

### 9. side-crowding (major, Dynamics)

**A stock's flows are spread round its sides.** At most 2 flows meet one side while a side that faces one of
their valves has none.

*Why:* several pipes squeezed into one side jog to reach their valves and run close together. One or two on a
side is the norm: 442 of the 457 stocks drawn across the examples' views on main. The 3 to 6 cases are crowded.

### 10. flow-bends (major, Dynamics)

**A flow is straight.** A flow to or from a cloud has no bend. A flow between stocks has at most a jog (2 bends),
and a flow back up a chain (rework) at most 4.

*Why:* a straight pipe reads as one thing moving. Every bend asks the eye to follow.

### 11. label-collision (major; minor for signs and counts, all views)

**No word is drawn over a line, a part or another word that is not its own.** This covers a valve's name and
rate, a cloud's "from …", a loop's name, a signal's name and a count on a process line.

*Why:* a word struck through by a line, or two words on top of each other, cannot be read.

*Measured:* every text element's box as drawn, against every line's segments (over 3px clipped), every part's box
(over 15% of the word's area), and every other word's box (over 10% of the smaller one).

### 12. cloud-side (minor, Dynamics)

**A cloud is on the natural side of its valve, and in line with it.** An outflow's cloud is right of or below its
valve. An inflow's cloud is left of or above it. The cloud's centre is within 6px of the valve's axis.

*Why:* the eye reads stock-and-flow diagrams left to right and top to bottom. Material should arrive from up or
left and leave down or right. This is the downward preference for drains in the earlier layout work.

### 13. marker-collision (minor, Dynamics)

**A loop marker (R or B in its circular arrow) lies on no line and no part.**

*Why:* the marker names the loop it sits inside (Sterman's loop identifiers). Over a pipe, it hides the pipe and
reads as a part.

### 14. pipe-crossing (minor, Dynamics)

**Two flows do not cross.** A link crossing a pipe is allowed (it hops it).

*Why:* crossing pipes read as a junction, and stock-and-flow diagrams have no junctions.

### 15. signal-backwards (minor, Blocks)

**A forward signal runs left to right.** Only a feedback path, through a sensor, runs back.

*Why:* this is the block diagram convention (Franklin, Powell and Emami-Naeini; Ogata). The forward path runs
left to right and the feedback returns beneath it. A forward line drawn right to left wraps round and reads as
feedback.

*Measured:* a line not into or out of a sensor whose target's centre is over 60px left of its source's, and which
runs over 40px longer than its straight distance.

### 16. line-detour (minor, all views)

**An information line (a link, a signal, a process line) is at most twice its straight distance, plus 160px.**
For block diagrams, it is twice plus 240px, since the feedback path runs back beneath by design.

### 17. line-bends (minor, all views)

**An information line has at most 6 bends.**

### 18. satellite-far (minor, Dynamics)

**A goal stays by what it acts on.** A goal's desired level is within 160px of its gap, and the gap is within
160px of the valve it drives.

*Why:* the desired level, the gap and the valve read as one decision: Sterman's anchoring-and-adjustment
structure.

### 19. stranded-part (minor, all views)

**Every part is within 420px of something it is joined to.**

*Why:* a part far from everything it joins makes the drawing big and its lines long.

### 20. fit (minor, all views)

**A drawing that does not fit the screen at zoom 0.7 is at most 4 times longer one way than the other.** Beyond
that, it runs off the screen one way while the screen is empty the other.

The three Blocks rules below came later. Two of them are critical, and they are numbered last so that the numbers
above, which the rest of this document cites, stay the same.

### 21. crossing-without-hop (critical, Blocks)

**Two lines that cross are drawn as a crossing.** A crossing is a level stretch of one line and an upright stretch of
another, each passing through the point (a line that ends on another is a take-off, not a crossing). The level
line has a small half-circle hop over the other line there, and there is no dot. Where the crossing is under the level
line's arrowhead (within 12px of its end), the upright line hops sideways instead. Where two crossings fall at one
place, or within a hop of each other, one hop covers them, and the line is never drawn back along itself beneath it.

*Why:* in a block diagram a plain cross reads as a connection, and a dot at it says so outright. A control engineer
has to be able to tell a junction from two signals that pass each other.

*Measured:* one instance for each crossing with no hop within 2px on the line that should carry it, or with a dot
within 4px; and one for each place a line's drawn path turns back along the move before it (a plain cross drawn
again under a hop). The line's last move back to its arrowhead's base, 10px or less, is not counted: it is under the
head.

### 22. dot-not-at-takeoff (critical, Blocks)

**A dot is drawn only where one signal's lines part.** A take-off is a point of one net's lines (all the lines from
one output port) that is a bend of one of them, or the port itself, where three ways meet. The port's block counts
as one of the three. Two lines of one signal that only pass through each other are a crossing, and get a hop.

*Why:* a dot says "this is one signal, taken off here". At any other point it is a connection that does not exist.

*Measured:* one instance for each dot more than 2px from every take-off.

### 23. slash-on-crossing (major, Blocks)

**A vector's slash and count stay clear of crossings.** The slash goes in the middle of the line's longest stretch
that has no crossing or bend in it, so it is at least half that stretch's length from either end. The rule asks for
12px.

*Why:* a slash at a crossing reads as a mark on the other line, or as the hop itself.

*Measured:* one instance for each slash within 12px of a crossing (the score is how much nearer it is).

All three are checked in every Blocks view of every example
(`test_the_control_view_draws_every_example_cleanly_as_a_block_diagram`), and again after a block is dragged and in
the exported SVG (`test_blocks_crossings_hop_dots_only_at_takeoffs_slashes_clear_and_a_drag_and_the_export_keep_them`).
The two critical rules also gate the generated models' Blocks views. While a part is being dragged, only the lines
being dragged are drawn again, so the hops on the other lines are not updated until the part is let go and every
line is redrawn.

## What the layout does about them

- **Flows to and from clouds are their stock's satellites** (`satellites.js`). A flow between one stock and a
  cloud is left out of ELK's layout, together with the links into its valve. The stock is laid out as a box that
  holds room for it on its natural side: a drain below the stock (or right of it, if no flow to another stock
  leaves that way), an inflow above it (or left of it). The box has ports level with the stock itself, so the chain
  lines up with the stock, not the box. After the layout the valve goes on a short straight pipe out of the stock
  and the cloud just beyond. Links never pull a valve away from its pipe: they travel to it wherever it sits. The
  one exception is the link from the goal that drives the valve, which ELK is given as driving the stock, so the
  goal is laid out by what it holds. A stock dragged takes its satellites along (`interact.js`). This fixes rules
  1, 4, 5, 10 and 12 for these flows.
- **Any other flow to or from a cloud that ELK left elsewhere is seated again** (`places.js` `seatCloudFlows`), in
  the first free place on the natural side.
- **A valve between two stocks that ELK left outside their span is moved between them** (`centreValves`), with
  its goal where there is room, else alone: level with one of the stocks, else midway, else in a lane under, over
  or beside them.
- **Rework is laid out backwards.** The pipes of a flow into a stock declared before the one it leaves are given to
  ELK reversed, so the chain is laid out left to right and the rework runs back.
- **A valve is placed as a point and then turned** (`avoid.js` `firstPass`, `valves.js` `turnValves`). Each
  flow is routed whole, from end to end, through its valve's middle (libavoid's checkpoints). A flow that turns on
  the valve itself is routed again straight through it, on whichever axis gives fewer corners. The valve faces
  that way, toward the far end. Only then is every line routed, with each valve's pins and name where its turn
  puts them. Rule 8 (a stub on the pipe into the stock) holds by construction, after the layout and after a drag.
- **A valve whose flow turns just past it is slid along its pipe**, off the corner, by up to the room for half a
  valve and a stub (48px from its middle), where the stretch is long enough and the valve lands clear. Never one
  put there by hand.
- **A stock gets a pipe point in line with any valve facing one of its sides**, top and bottom included (rule 9).
  Its pipe points are at least 9px apart, one track each, and none twice in one place. No pipe's end is slid next
  to another's.
- **A cloud's words go beyond it**, away from its valve: never on its pipe.
- **A pipe's small nudging jogs are taken out** where its run can go on in line (onto its own net's track at most);
  a jog by the pipe's end, by moving the stretch before it onto the end's line.
- **A valve moved off a pipe drawn by hand between wrapped rows has that pipe routed** like any other, from where
  the valve now is.
- **A chain far wider than tall is wrapped into rows only when the rows fit the window clearly better** (by 25%)
  than one row.
- **A crossing costs the router less where a view has over 150 lines.** Its search is most of the routing time,
  and the bigger views' routing must stay within the page's bound.
- **A large view's lines are routed in groups of at most 100, and a crossing is weighed only within a group**
  (`routeparts.js`). Over 150 lines, each open system's own lines form a group and the rest a shared one, as before;
  a group of more than 100 (the shared one included, which holds every line of a one-system view) is then parted. The
  lines at a part with more than 8 of the group's lines (a hub), lines with an end that has no position, and, in the
  shared group, lines at a part that also has a line of a system's group, stay shared. The rest are split where they
  share no part, and a piece of more than 100 is cut into bands along its wider side, the lines between two bands
  shared. What it guarantees: (i) every group but the shared one has at most 100 lines; (ii) two lines that share a
  part and are both outside the shared group are in one group, so a net is split only between the shared group and
  one other, at a hub, a band's edge or a part with lines of two groups; (iii) a group of n lines becomes at most
  2·⌈n/100⌉ + 1 groups; (iv) a group of at most 100 lines is left as it was, so a view whose groups all are is
  grouped as before. The shared group is not bounded by this: a cut where a chain runs across the band's axis can
  share many lines. Past 100 lines it is routed with no weight on crossings, and the spacing pass that follows the
  groups reroutes, unweighed, two lines of one point that cross.

## Fit against main

Recorded sizes (`tests/fixtures/diagram_sizes.json`) were written again for the new layouts. These are the views that
fit the screen worse than on main, with before and after screenshots in `~/ergostat-wt/layout-shots/`
(`fit-<example>-<view>-before.png`, `-after.png`; main's fit, then this branch's):

| view | main | branch | why |
|---|---|---|---|
| the-job system=delivery | 1.40 (rows) | 0.80 | main's rows hold the owner's first antipattern: nudges-drafted's pipe runs up and round through the valve placed over the row. The branch draws the chain left to right in one row; it is not straight: nudges-drafted jogs up into my-prs-nudged, and a long connector runs under it. Its rows fit only 24% better, under the 25% a wrap must gain. Known instance, not fixed: the names "nudges-drafted" and "reviewed-after-nudge" collide with a "0 prs/h" rate (label-collision). |
| coordinator, image-squeeze, the-job system=modelling | 0.99 | 0.86 | main is the owner's own case: model-mended's drain runs across the whole drawing to a cloud in a corner, and changes-made's valve sits far from its stock. Now both are short satellites, and the chain is one row, a little wider. |
| image-squeeze open=lab | 0.53 | 0.46 | 16 drains and inflows stood beside their stocks (the satellites' room) where main left valves and clouds in other layers. The room is kept only when the drawing loses no more than 10% of its fit to it. Here it loses less than that, and the rest is the same layout's different layering. Not fixed. |
| software-factory open=* | 0.74 | 0.60 | worse than the number suggests: the after shot runs past the window's edge. No satellites' room kept here (it cost more than 10%). The loss is the rework laid out backwards (the chain left to right) and valves put between their stocks, which change ELK's layering. Not fixed. |

The other views the review named are back to main's fit or better: software-factory system=product 1.31 (main 1.31);
ops open=* 1.02 (0.88). The remaining ones are within 15%: small-requests system=review-reminders 1.02 (1.10), big
open=data 0.91 (1.02), big system=api and system=web 1.28 (1.38). Two changes brought them back:

- **The satellites' room is optional.** The layout is computed with and without it, and the room is kept only if
  it costs at most 10% of the fit.
- **Wrapping follows the screen.** A chain counts as far wider than the screen when it is wider than the canvas,
  not wider than a fixed 1,600px.

## Ceilings

Two rules with no gate of their own have ceilings: `valve-orientation-mismatch` and `satellite-far`. An example's
instances of each, over all its views, may not exceed the counts recorded in `tests/fixtures/layout_known.json`
(`ceilings`), written with `RECORD_LAYOUT=1`.

## Instances found on main (before)

From the corpus run on main's engine (1,812 views of 320 models: the 20 examples and 300 generated). Up to
five of the worst per rule, one per view. *Should be* says where the part belongs.

**flow-excursion** (58). Should be: its valve between its two ends, on a short pipe.

- coordinator [dynamics system-modelling]: flow model-mended: 2536px of pipe between ends 1058px apart
- image-squeeze [dynamics system-modelling]: flow model-mended: 2536px of pipe between ends 1058px apart
- the-job [dynamics system-modelling]: flow model-mended: 2536px of pipe between ends 1058px apart
- coordinator [dynamics open-all]: flow model-mended: 2564px of pipe between ends 1100px apart
- coordinator [dynamics open-modelling]: flow model-mended: 2564px of pipe between ends 1100px apart

**line-through-part** (2). Should be: routed round the part, or the part moved off the line.

- gen-aux-1-167 [dynamics]: pipe pipe:flow:s2-to-s3->stock:s3 through gap:s2-ok for 28px

**valve-between-ends** (382). Should be: on the pipe between its two ends (beside its stock for a cloud's flow).

- coordinator [dynamics system-modelling]: valve model-mended 660px outside the span of its ends
- image-squeeze [dynamics system-modelling]: valve model-mended 660px outside the span of its ends
- the-job [dynamics system-modelling]: valve model-mended 660px outside the span of its ends
- coordinator [dynamics open-all]: valve model-mended 653px outside the span of its ends
- coordinator [dynamics open-modelling]: valve model-mended 653px outside the span of its ends

**cloud-by-valve** (743). Should be: one step from its valve, on the valve's line, beyond it.

- coordinator [dynamics open-all]: cloud of model-mended 1125px from its valve
- coordinator [dynamics open-modelling]: cloud of model-mended 1125px from its valve
- image-squeeze [dynamics open-all]: cloud of model-mended 1125px from its valve
- image-squeeze [dynamics open-modelling]: cloud of model-mended 1125px from its valve
- the-job [dynamics open-all]: cloud of model-mended 1125px from its valve

**line-overlap** (6). Should be: on a track of its own, at least 7px apart.

- gen-aux-1-007 [dynamics]: pipe:flow:s0-to-s1->stock:s1 on pipe:flow:s2-to-s3->stock:s3 for 133px
- gen-chain-1-140 [dynamics]: pipe:flow:s1-to-s2->stock:s2 on pipe:stock:s2->flow:s2-to-s3 for 28px
- gen-chain-1-240 [dynamics]: pipe:flow:s2-to-s3->stock:s3 on pipe:stock:s3->flow:s3-to-s4 for 28px
- gen-fanout-1-211 [dynamics]: pipe:flow:split-0->stock:b0x0 on pipe:stock:b0x0->flow:b0x0-to-b0x1 for 28px

**flow-bends** (1040). Should be: straight: the valve and the far end in line with the stock.

- coordinator [dynamics open-all]: flow expired: 8 bends (2 allowed)
- coordinator [dynamics open-observer]: flow compacted: 6 bends (0 allowed)
- gen-chain-1-130 [dynamics]: flow s2-to-s3: 10 bends (4 allowed)
- gen-fanout-1-011 [dynamics]: flow b0x0-done: 6 bends (0 allowed)
- image-squeeze [dynamics open-rollout]: flow offset-steps: 6 bends (0 allowed)

**label-collision** (3618). Should be: on a free side of its part, clear of every line.

- software-factory [dynamics open-all]: 'all-live via regressions' over connector:stock:users->flow:filed-features, connector:stock:missing-ops->flow:churn, connector:stock:users->flow:asks
- alert-triage [dynamics open-all]: 'escalations-answered via' over pipe:flow:alerts-reopened->stock:alerts-triaged, connector:gap:escalations-answered->flow:alerts-reopened, connector:g
- small-requests [dynamics system-review-reminders]: 'review-reminders-reminded' over connector:gap:review-reminders-reminded->flow:review-reminders-giving-up, connector:gap:review-reminders-reminded->fl
- gen-aux-1-267 [dynamics]: 's0 via s-arrive and s1' over connector:stock:s1->stock:load1, connector:stock:load1->flow:s0-to-s1, connector:gap:s0-ok->flow:s0-to-s1
- software-factory [dynamics system-product]: 'all-live via shipped and' over connector:stock:bugs-live->flow:churn, connector:stock:missing-ops->flow:churn, flow:churn

**valve-orientation-mismatch** (103). Should be: turned to its pipe, so the pipe runs straight through.

- gen-mixed-1-228 [dynamics open-all]: valve handoff: its pipe leaves by 5px and turns to run 606px across its axis
- gen-mixed-1-218 [dynamics open-all]: valve handoff: its pipe leaves by 5px and turns to run 453px across its axis
- gen-cross-1-125 [dynamics open-all]: valve hand-1: its pipe leaves by 5px and turns to run 419px across its axis
- gen-mixed-1-208 [dynamics open-all]: valve handoff: its pipe leaves by 5px and turns to run 402px across its axis
- gen-mixed-1-258 [dynamics open-all]: valve handoff: its pipe leaves by 5px and turns to run 397px across its axis

**side-crowding** (60). Should be: some of the flows on the free side that faces their valve.

- coordinator [dynamics system-work]: stock:ready-work: 6 flows on its left side; its up side, facing flow:admitted, has none
- coordinator [dynamics open-all]: stock:runs-in-flight: 4 flows on its right side; its down side, facing flow:reported, has none
- gen-fanout-1-051 [dynamics]: stock:in1: 4 flows on its right side; its up side, facing flow:split-0, has none
- gen-fanout-1-081 [dynamics]: stock:in1: 4 flows on its right side; its up side, facing flow:split-1, has none
- gen-fanout-1-191 [dynamics]: stock:in1: 4 flows on its right side; its up side, facing flow:split-0, has none

**cloud-side** (143). Should be: right of or below an outflow's valve; left of or above an inflow's.

- gen-fanout-1-011 [dynamics]: outflow cloud of b0x0-done runs left, 380px off the valve's line
- coordinator [dynamics system-work]: inflow cloud of proposed runs up, 184px off the valve's line
- coordinator [dynamics open-observer]: inflow cloud of context-filled runs up, 136px off the valve's line
- coordinator [dynamics system-modelling]: outflow cloud of model-mended runs left, 126px off the valve's line
- image-squeeze [dynamics system-modelling]: outflow cloud of model-mended runs left, 126px off the valve's line

**marker-collision** (894). Should be: inside its loop, in free space.

- ticket-factory [dynamics open-all]: loop marker review-asked via review-changes over connector:stock:review-asked->flow:repinging, connector:stock:review-asked->stock:cycle-hours, connec
- ticket-factory [dynamics system-review]: loop marker opened-asked over pipe:stock:pr-open->flow:ask-review~~c, connector:stock:pr-open->flow:ask-review~, connector:stock:pr-open->gap:opened-a
- alert-triage [dynamics open-all]: loop marker new-alerts via alerts-triaged over pipe:stock:new-alerts->flow:alerts-dismissed, connector:stock:new-alerts->flow:alerts-dismissed, connec
- coordinator [dynamics system-observer]: loop marker knowledge-recorded over pipe:stock:unrecorded-corrections->flow:externalised, pipe:stock:unrecorded-corrections->flow:lost-at-cut, connect
- coordinator [dynamics system-work]: loop marker ready-work over connector:stock:owner-present->desired:runs-within-limit~, connector:stock:ready-work->decision:admission

**pipe-crossing** (133). Should be: the two flows untangled (one of the stocks moved).

- alert-triage [dynamics open-alerts]: pipe:flow:alerts-investigated->stock:alerts-summarising crosses pipe:flow:alerts-reopened->stock:alerts-triaged
- alert-triage [dynamics open-all]: pipe:flow:alerts-investigated->stock:alerts-summarising crosses pipe:flow:escalations-handled->cloud:escalations-handled:out
- coordinator [dynamics open-all]: pipe:cloud:directed:in->flow:directed crosses pipe:flow:leased->stock:runs-in-flight
- coordinator [dynamics open-modelling]: pipe:stock:model-error->flow:model-mended crosses pipe:flow:changes-accepted->stock:accepted-changes
- coordinator [dynamics open-observer]: pipe:flow:compacted->cloud:compacted:out crosses pipe:stock:unrecorded-corrections->flow:lost-at-cut

**signal-backwards** (384). Should be: the target block right of its source, the forward path left to right.

- coordinator [blocks open-all]: w24:proc:stock.durable-knowledge|out|stock.durable-knowledge>mux:quality|in|stock.durable-knowledge: 4819px right to left, wrapping round
- image-squeeze [blocks open-all]: w49:blk:rollout|out|flow.adopted>jsum:tuner|in|flow.adopted: 2489px right to left, wrapping round
- ticket-factory [blocks open-all]: w121:proc:stock.located|out|stock.located>out:stock.located|in|stock.located: 1736px right to left, wrapping round
- image-squeeze [blocks open-rollout]: w30:sys:service|out|meas.stock.failures.main>sum:no-failures|in|y: 1514px right to left, wrapping round
- gen-mixed-1-238 [blocks open-all]: w21:proc:auxiliary.pressure|out|auxiliary.pressure>gen:stock.f0|in|auxiliary.pressure: 1155px right to left, wrapping round

**line-bends** (11). Should be: a straighter way.

- image-squeeze [dynamics open-all]: connector connector:flow:dropped->flow:failures-cleared: 12 bends
- image-squeeze [blocks open-all]:  w31:blk:rollout|out|stock.rollout-share>mux:service|in|stock.rollout-share: 8 bends
- gen-cross-1-005 [blocks open-all]:  w10:dist:flow.hand-1|out|flow.hand-1>psum:stock.c0x2|in|flow.hand-1: 7 bends
- image-squeeze [blocks open-lab]:  w34:sys:benchmark|out|meas.stock.capabilities.main>sum:every-case|in|y: 7 bends

**satellite-far** (165). Should be: stacked over the valve it drives.

- gen-mixed-1-238 [dynamics open-all]: excess f2 2069px from handoff
- gen-mixed-1-128 [dynamics open-all]: excess f2 2036px from handoff
- gen-mixed-1-268 [dynamics open-all]: excess f2 2027px from handoff
- gen-mixed-1-138 [dynamics open-all]: excess f2 2022px from handoff
- gen-mixed-1-278 [dynamics open-all]: excess f2 1987px from handoff

**stranded-part** (61). Should be: beside what it is joined to.

- coordinator [dynamics open-all]: stock:oldest-silence: nothing it joins nearer than 2909px
- coordinator [blocks open-all]: out:auxiliary.oldest-silence: nothing it joins nearer than 2202px
- ticket-factory [blocks open-all]: out:stock.located: nothing it joins nearer than 1679px
- ticket-factory [dynamics open-all]: stock:prs-awaiting-review: nothing it joins nearer than 1573px
- coordinator [dynamics open-modelling]: cloud:model-mended:out: nothing it joins nearer than 1125px

**fit** (88). Should be: wrapped, or the systems stacked.

- gen-chain-1-040 [process by-events kinds-ks]: 2346x121: aspect 19.4, fit 0.46
- gen-chain-1-040 [process kinds-ks]: 2346x121: aspect 19.4, fit 0.46
- gen-chain-1-130 [process by-events kinds-ks]: 2346x121: aspect 19.4, fit 0.46
- gen-chain-1-130 [process kinds-ks]: 2346x121: aspect 19.4, fit 0.46
- gen-chain-1-200 [process by-events kinds-ks]: 2346x121: aspect 19.4, fit 0.46

