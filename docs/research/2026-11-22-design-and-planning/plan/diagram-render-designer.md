# Diagram correctness and speed (owner items 5, 7, 10): designer's notes

Read-only, 2026-11-22. Walked the demos in a headless browser with a probe that reads every drawn line in the
visible SVG and measures how far each of its two ends is from the drawn box of the part it joins ("dangling":
more than 22 diagram px away). The live factory (:8798) was opened read-only (page loads and its GET polls only;
no click that acts, no POST: the probe logged zero non-GET requests). Probe scripts:
`scratchpad/drprobe/` (probe.py, scan.py, live.py, livewatch.py). Screenshots: `shots/plan-dr-*.png`.
The diagram-render engineer's notes (`plan/diagram-render-engineer.md`) found the code causes; this note
confirms them from a reader's side, adds the live factory, and sets the design the gaps must deliver.

## What a user sees

### Item 5: lines that connect to nothing

- **Every re-layout shows broken lines first.** After Wrap, Open all, Close+Open on big (:8797, 175 lines)
  30 of 175 drawn lines end in mid air for about 1 s (`plan-dr-big-wrapwatch-1.png`: api-q0's pipe stops in
  empty space left of the stock; api-q2-out's pipe heads for where the valve was). They are greyed, but a
  greyed pipe that stops in empty space still reads as a flow to nowhere.
- **On the live factory it does not end.** `?view=dynamics&open=*`: 746 lines, drawn 1 s after the graph
  arrived with **84 lines dangling and 344 greyed**; libavoid had not answered after 3 minutes (sampled every 15 s:
  unchanged). `plan-dr-live-openall-drawn.png`: pipes into nothing (changes-made-by-redesigner's arrow at
  x≈490), connectors ending at x≈808 in empty space. This is the owner's "flow lines connect to nothing": not a
  flicker but the steady state of the large case.
- One persistent instance on a demo after routing finished: image-squeeze `system=lab`, connector
  `gap:one-running → flow:submitted` 49 px off its valve.
- Renderer parameters: `?layout=` has 12 presets (tight, bk, stress, force, mrtree ...). Each multiplies what
  the layout rules must hold for; readers never need them.

### Item 7: lines do not follow a drag

- On a freshly loaded page a dragged stock's lines stay at the old place, greyed, for the length of a libavoid
  move (about 1 s on ticket-factory open=*), then come (`plan-dr-tf-drag-mid.png`).
- **After any toggle (one `route()`), they do not grey and do not move**: `plan-dr-tf-drag-after-route-mid.png`
  shows changes-testing dragged 150 px down with its pipes still black and ending where it was, an arrowhead
  pointing into nothing. After the drop 121 lines were briefly off, then the whole drawing re-routed (1.7 s on
  ticket-factory; on the live factory a drop restarts the unbounded routing). Confirms the engineer's cause:
  window listeners added per page and never removed, so the oldest handler works on a detached SVG.
- A dragged stock leaves its open system's tinted frame (same shot: changes-testing sits below `modelling`'s
  frame), breaking layout rule 7 (frame-membership) by hand.
- A drop re-routes every line in the view (`putDown` → `avoidStart`), though the code comment says "only the
  lines are routed again".

### Item 10: time, and Flows only

| case | lines | to an attached, final drawing |
|---|---|---|
| ticket-factory open=* | 155 | 1.3-1.8 s (libavoid 0.7 s) |
| the-job open=* | 240 | 2.9 s; 4.9 s with wrap |
| image-squeeze open=* | 202 | **9.3 s; 19 s with wrap** (libavoid 8.3 s) |
| software-factory open=* | 92 | 1.8 s; 3.4 s with wrap |
| big open=* | 175 | 2.0-2.6 s |
| live factory open=* | 746 | **not reached in 3+ min**; first (broken) drawing at 5.6 s |

The time is the router, not ELK (ELK about 1 s on the live case, though on the main thread). While the server is
busy (owner item 2) the live page also waited 20-100 s for any answer; that is the performance cluster's, and it
adds to this one only on first load.

**Flows only** is a CSS class: the pipes keep the places the full diagram gave them. On image-squeeze `lab`
(`plan-dr-is-lab-flowsonly.png`) the small chains float in the space hidden auxiliaries left, the main chain
(ideas → building → experiments → improvements) sits at the bottom, and a kept link from `failures-cleared` runs
down and across the whole drawing around parts that are no longer drawn. Nothing here makes "the flow of an item"
obvious.

## The design (what the gaps must deliver)

1. **A line is attached on every frame.** Whatever stage the layout is at (first draw, toggle, drag, drop, poll),
   each drawn line starts on its source and ends on its target. When the final route is not known yet, the line
   is a plain orthogonal stand-in computed from where the parts are now, drawn in the lighter tone (the second
   tone the notation designers propose for item 8; not dashed, which means doubt or delay in Dynamics). Never the
   old route. The test reads the drawn SVG, not `S.layout`, so it catches a stale drawing.
2. **A drag moves the lines with the part, in the same frame.** The router's answer refines them; the rest of the
   drawing neither moves nor greys. A drop re-routes only the lines the drop touched. A part stays inside its open
   system: the frame grows to hold it.
3. **Speed: attached at once, tidy soon, never "routing" forever.** A fast routing (the engineer measured 183 ms
   for image-squeeze with no crossing weight, against 7-15 s with it) is drawn first; the careful one runs in the
   background within a bound and is swapped in only if it is still the current drawing. ELK runs once per change,
   in a worker. Targets: every demo attached in under 1 s after the graph arrives; the live factory open=* in
   under 3 s; the careful routing done or given up within 10 s.
4. **Flows only arranges the flows.** Turning it on lays out only what it shows (stocks, valves, clouds, systems,
   the kept links), each chain an item moves along on one row in the order items move, upstream first, top-left;
   inflows from clouds above or before, drains below, rework in a lane under the row. The parts glide to their new
   places (about 300 ms, none with `prefers-reduced-motion`) so the reader can follow; turning it off glides back.
   Hand placements in Flows only are kept apart from the full diagram's. Flows only is in the address
   (`flows=1`). "Unpin all parts" becomes **Re-arrange** in the ⋯ menu: forget hand placements here and lay this
   view out afresh. That is the owner's re-arrange button, in both modes, without a new control on the canvas.
5. **A rewrite only after numbers.** The broken lines are specific bugs and the slowness is mostly one router
   setting and repeated ELK runs: fix those first (gaps 1 to 4). The rewrite question is real for Dynamics: a
   domain layout (chains as rows, auxiliaries beside what they drive, connectors as arcs, as Vensim and Stella
   draw) would replace ELK plus fifteen correcting passes and is what R5 and R8 piece 7 ask for. Flows only's
   chain layout (gap 4) is its pilot. A proposal decides with the corpus and the live case measured.

## Where the owner's request and the review agree or combine

- Agree: R8 ("never blank; frame what was asked for; chains upstream first; opening one system leaves the others
  where they were"), R5 piece 9 (short pipes), R4 piece 6 (rows upstream first). Item 10's "flow of an item clear
  and obvious" is R8 piece 7 applied to Flows only.
- Combine: Q11 (gap/ui-open-into-and-every-panel-link-show-that-somethi) keeps the old drawing dimmed until the new
  one is ready; with gap 1 the new one is "ready" as soon as its lines are attached (stand-ins), so Q11's wait is
  short. Wrap and Open all blank the canvas and side list today (`plan-dr-big-wrap.png`): that is Q11's case.
- Combine: Q71 (gap/ui-open-frames-what-was-opened-fit-includes-every-w): Fit uses every wire's bounds; stale lines
  far from their parts inflate those bounds, so gap 1 makes Q71 correct.
- Combine: Q81 (gap/ui-the-diagram-loads-without-console-errors): ELK's failure fallback and the pin offset; the
  fallback layout is one of the passes gap 5 counts.
- Combine: Q36 (gap/ui-the-address-holds-what-is-selected-and-the-windo): Flows only joins the address state.
- Conflict, resolved: the code's rule "Flows only is a class, not a re-layout: nothing moves" against the owner's
  re-arrange. The owner's request wins; moving is made followable by the glide and reversible by turning it off.
- Item 8 (second tone): the stand-in lines use it; if item 8's tones land later, the stand-in uses today's grey.

## Gaps proposed

1. `diagram-lines-stay-attached` (5): stand-ins from current places, a drawn-SVG rule, a generation guard, cut lines.
2. `diagram-drag-moves-lines` (7): listeners once per page, per-frame stand-ins, drop re-routes only what it touched, frame grows.
3. `diagram-large-case-fixture` (5, 7, 10): the live factory's graph as a test fixture with time budgets.
4. `diagram-routes-fast-then-refined` (10): fast routing first, bounded refinement, one ELK run in a worker.
5. `flows-only-arranges-the-flows` (10): its own chain layout, glide, own pins, `flows=1`, Re-arrange.
6. `diagram-layout-engine-proposal` (10): rewrite or not, decided with numbers (large: proposal first).

Parallel: 1, 2, 3 and 5 can start at once; 4 after 1 and 3; 6 after 4 and 5.

## Questions for the owner (one sentence each)

- May Flows only move parts (gliding) when turned on, rather than wait for a Re-arrange click?
- May a drawing's lines tidy themselves a second or two after it appears (fast first, careful after)?
