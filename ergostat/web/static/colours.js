/* colour by correspondence (the owner, 2026-11-17: a little more colour, only on demand): every shape in
   the dynamics and block views ringed in the colour of what it is, so the parts that stand for each other
   in the two views share a colour, and different ones differ. The colour is the model part's
   (correspond.py's colours: the same in every view and both panes); a shape that is several parts (a
   controller: the block and the valves it moves) is ringed in segments of each; a closed system's box,
   and an open one's outline, in its system's. Off unless asked: the ⋯ menu's toggle (remembered), or C
   held. The same rings, thick and haloed, mark what is pointed at in the other pane (interact.js). */
"use strict";

const CORR_HUES = 10, CORR_STEPS = 3, CORR_SEG = 7;        // (correspond.py's HUES and STEPS); a segment, on the screen
const CORR = { on: false, held: false };
try { CORR.on = localStorage.getItem("ergostat.colours") === "1"; } catch (e) { /* off */ }

/* a palette slot as a colour: its hue, then toward the ink, then toward the paper (keeping --g-fade of the hue: in the
   dark theme, as much as keeps it 3:1 on the paper) */
function corrColour(i) {
  const hue = `var(--g${i % CORR_HUES})`, step = Math.floor(i / CORR_HUES) % CORR_STEPS;
  return step === 0 ? hue : step === 1 ? `color-mix(in oklab, ${hue} 62%, var(--ink))` : `color-mix(in oklab, ${hue} var(--g-fade), var(--bg))`;
}
function corrSlot(corr, p) {                              // a part's slot; an old model's: one from its name
  const i = corr?.colours?.[p];
  if (i != null) return i;
  let h = 0;
  for (const c of p) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return h % (CORR_HUES * CORR_STEPS);
}

/* the colours of a shape: its system's (a system's box or outline); else those of the parts it stands for
   here (its own, a stand-in's, or held by it and drawn nowhere else); else those it is */
const corrBy = new WeakMap();
function corrStandsFor(corr) {
  let m = corrBy.get(corr);
  if (m) return m;
  m = new Map();
  for (const [p, ids] of Object.entries(corr.parts || {})) for (const id of ids) (m.get(id) || m.set(id, []).get(id)).push(p);
  corrBy.set(corr, m);
  return m;
}
function corrColours(id, corr = S.graph?.corr) {
  const x = corr?.shapes?.[id];
  if (!x || x.aside) return [];
  const parts = x.system ? [`system.${x.system}`] : (corrStandsFor(corr).get(id) || []).length ? corrStandsFor(corr).get(id) : x.is;
  const ordered = [...x.is.filter((p) => parts.includes(p)), ...parts.filter((p) => !x.is.includes(p))];
  return [...new Set(ordered.map((p) => corrSlot(corr, p)))].map(corrColour);
}

/* the rings of one shape, over its outline: a halo (shown when pointed at from the other pane), then one
   ring per colour, each dashed to take its turn round the outline */
function corrRings(outline, colours) {
  const out = [], k = colours.length;
  const copy = (cls, colour) => {
    const c = outline.cloneNode(false);
    for (const a of ["class", "fill", "stroke", "stroke-width", "stroke-dasharray", "stroke-opacity", "fill-opacity", "style", "id"]) c.removeAttribute(a);
    c.setAttribute("class", cls);
    c.style.setProperty("--ring", colour);
    return c;
  };
  out.push(copy("corr-halo", colours[0]));
  colours.forEach((colour, i) => {
    const c = copy("corr-ring", colour);
    if (k > 1) { c.style.setProperty("--dash", `${CORR_SEG}px ${CORR_SEG * (k - 1)}px`); c.style.setProperty("--dash-at", `${-CORR_SEG * i}px`); }
    out.push(c);
  });
  return out;
}

/* every shape drawn and not ringed yet, ringed (markInteraction calls it after each drawing) */
function paintGroups(svg) {
  const corr = S.graph?.corr;
  if (!corr?.shapes) return;
  for (const el of svg.querySelectorAll(".node")) {
    if (el.querySelector(".corr-ring")) continue;
    const outline = el.querySelector(".hit"), colours = outline ? corrColours(el.dataset.id, corr) : [];
    if (colours.length) outline.after(...corrRings(outline, colours));
  }
  for (const el of svg.querySelectorAll("g.hull[data-hull]")) {
    if (el.querySelector(":scope > .corr-ring")) continue;
    const id = el.dataset.hull.startsWith("frame:") ? el.dataset.hull : "hull:" + el.dataset.hull;
    const outline = el.querySelector(":scope > rect:not(.hull-grip):not(.hull-mark)"), colours = outline ? corrColours(id, corr) : [];
    if (colours.length) el.append(...corrRings(outline, colours));
  }
}

/* shown or not: the toggle (remembered, and the same in the other pane and other tabs), or the key held */
function corrApply() { document.body.classList.toggle("corr-on", CORR.on || CORR.held); }
function corrSet(on) {
  CORR.on = !!on;
  try { localStorage.setItem("ergostat.colours", CORR.on ? "1" : "0"); } catch (e) { /* this page only */ }
  corrApply();
  if (typeof peerSay === "function") peerSay({ type: "colours", on: CORR.on });
}
function corrHold(held, tell = true) {
  if (CORR.held === held) return;
  CORR.held = held;
  corrApply();
  if (tell && typeof peerSay === "function") peerSay({ type: "colours-held", held });
}
const corrTyping = (t) => t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName));
document.addEventListener("keydown", (ev) => {
  if (ev.key !== "c" || ev.ctrlKey || ev.metaKey || ev.altKey || corrTyping(ev.target)) return;
  corrHold(true);
});
document.addEventListener("keyup", (ev) => { if (ev.key === "c" || ev.key === "C") corrHold(false); });
window.addEventListener("blur", () => corrHold(false));
window.addEventListener("storage", (ev) => { if (ev.key === "ergostat.colours") { CORR.on = ev.newValue === "1"; corrApply(); } });
corrApply();
