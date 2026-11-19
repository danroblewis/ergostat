# Layout rules

Common-sense rules for how ergostat lays out its three diagrams: the stock-and-flow diagram (Dynamics), the block
diagram (Blocks) and the process map (Process). Each rule is stated plainly, with why it matters and a measurable
form. Each also has a detector in `tests/layout_rules.py`, which reads the drawn geometry off the page
(`scripts/layout_geometry.js`: every part's box, every line's points, every word as drawn, the loop markers, the
open systems' frames).

The rules are ordered by how bad a violation looks, worst first. A **critical** violation is one a reader notices
at once and reads wrongly: a flow that seems to go somewhere it does not, or a part hidden under another. A
**major** one makes the drawing look careless. A **minor** one costs a reader a moment.

How they are checked:

- `tests/test_diagram_rendering.py` runs the fast detectors on every view of every example it draws, and fails on
  any critical instance.
- `scripts/layout_corpus.py` runs every detector over the whole corpus: every example, plus several hundred
  generated models from `tests/diagram_corpus.py` (chains, fan-outs, joins, rework, many clouds, systems linked
  across, cascades, auxiliaries, mixes). Each model is drawn in each view: whole, everything open, each system
  open, each system alone. The run writes counts per rule and crops of the worst instances.

```
uv run --with playwright==1.63.0 python scripts/layout_corpus.py OUT --generated 300
uv run --with playwright==1.63.0 python scripts/layout_corpus.py OUT --engine ../other-checkout   # a before
```

<!-- COUNTS -->

## The rules

### 1. flow-excursion (critical, Dynamics)

**A flow takes the short way between the two things it joins.** Its pipe is at most 1.3 times the Manhattan
distance between its two ends, plus 80px (a valve's width and a jog).

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

*Measured:* the distance from the valve's centre to that box. Over 120px is critical; over 40px is major.

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

### 8. valve-orientation-mismatch (major, Dynamics)

**A valve faces the way its pipe runs.** A valve is upright when the end in line with it lies above or below it,
and level when that end lies beside it.

*Why:* a valve is a simple, common part, free to turn or flip. Its pipe should enter and leave it straight. A
level valve with its stock directly below forces the pipe to zig-zag through it.

*How it is now made:* the router routes each flow whole, from end to end, through the valve's middle as a point
(libavoid's checkpoints, no valve in the way). It turns each valve to the way the flow runs there, and only then
routes every line. So this rule holds by construction, after the layout and after every drag.

### 9. side-crowding (major, Dynamics)

**A stock's flows are spread round its sides.** At most 2 flows meet one side while a side that faces one of
their valves has none.

*Why:* several pipes squeezed into one side jog to reach their valves and run close together. In the examples,
one or two on a side is the norm (442 of 458 stock views). The 3 to 6 cases are crowded.

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

## What the layout does about them

- **Flows to and from clouds are their stock's satellites** (`satellites.js`). A flow between one stock and a
  cloud is left out of ELK's layout, together with the links into its valve. The stock is laid out as a box that
  holds room for it on its natural side: a drain below the stock (or right of it, if no flow to another stock
  leaves that way), an inflow above it (or left of it). After the layout, the valve goes on a short straight pipe
  out of the stock and the cloud just beyond. Links never pull a valve away from its pipe: they travel to it
  wherever it sits. This fixes rules 1, 4, 5, 10 and 12 for these flows.
- **Any other flow to or from a cloud that ELK left elsewhere is seated again** (`places.js` `seatCloudFlows`), in
  the first free place on the natural side.
- **A valve is placed as a point and then turned** (`avoid.js` `firstPass`, `valves.js` `turnValves`), so rule 8
  holds by construction. A stock gets a pipe point in line with any valve facing one of its sides, top and bottom
  included (rule 9).
- **A chain far wider than tall is wrapped into rows only when the rows fit the window clearly better** (by
  25%) than one row.

<!-- INSTANCES -->
