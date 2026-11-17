/* two views at once, linked (the owner, 2026-11-16): a second diagram pane, revealed by dragging in from
   any edge of the canvas (left or right: side by side; top or bottom: stacked), behind a separator that
   resizes it (double-click: half and half; dragged back to the edge: closed), remembered in this browser.

   The second pane is the page itself in a frame (?pane=1): a whole diagram with its own pan, zoom, open
   systems and view (by default the other one), its own Dynamics, Blocks and Wiring switch, and nothing
   of the header. The panes share what is chosen (model parts, interact.js) and say what is pointed at,
   by message: a shape pointed at in one lights what it is, lightly, in the other; a click chooses it in
   both. While the split is open, the side panel is drawn over the pane clicked in, so the diagrams keep
   the whole width. Narrower than a tablet, there is no split. */
"use strict";

const PANE = new URLSearchParams(location.search).has("pane");      // this page is the second pane, in a frame
const SPLIT_MIN = 240, SPLIT_CLOSE = 96, SPLIT_NARROW = 700;
const SPLIT_EDGES = ["left", "right", "top", "bottom"];
const SPLIT = (() => {
  const d = { open: false, edge: "right", frac: 0.5 };
  try { return { ...d, ...JSON.parse(localStorage.getItem("ergostat.split") || "{}") }; } catch (e) { return d; }
})();
function splitSave() {
  try { localStorage.setItem("ergostat.split", JSON.stringify({ open: SPLIT.open, edge: SPLIT.edge, frac: SPLIT.frac })); }
  catch (e) { /* not remembered: it lasts this visit */ }
}
let splitPane = null, splitSep = null, splitFrame = null;

const OTHER_PAGES = ["/loops", "/agents", "/record", "/items", "/fit", "/residuals", "/check", "/guide", "/item/"];
function diagramHash(hash) {
  const path = (String(hash || "").replace(/^#/, "") || "/diagram").split("?")[0];
  return !OTHER_PAGES.some((p) => path === p || (p.endsWith("/") && path.startsWith(p)));
}
function splitShown() { return !PANE && SPLIT.open && diagramHash(location.hash) && innerWidth >= SPLIT_NARROW; }

/* the other pane, and what is said to it */
function peerWin() { return PANE ? window.parent : splitFrame && splitShown() ? splitFrame.contentWindow : null; }
function peerSay(msg) {
  const w = peerWin();
  if (w && w !== window) w.postMessage({ ergostat: "split", ...msg }, "*");
}
window.addEventListener("message", (ev) => {
  const m = ev.data;
  if (!m || m.ergostat !== "split" || ev.source !== (PANE ? window.parent : splitFrame?.contentWindow)) return;
  if (m.type === "sel") {                              // chosen there: chosen here, and this pane's panel lets go
    S.sel = new Set(m.parts || []);
    S.whereNote = null;
    if (!$("#detail")?.hidden) closeDetail();
    markChosen();
  } else if (m.type === "hover") {
    S.xhover = new Set(m.parts || []);
    markChosen();
  } else if (m.type === "hello" && !PANE) {
    peerSay({ type: "sel", parts: [...S.sel] });
  } else if (m.type === "go" && !PANE) {
    location.hash = m.hash;                            // a page that is not a diagram opens in the page itself
  }
});

/* ---------------------------------------------------------------- the page with a second pane */

function otherView() {
  const q = new URLSearchParams((location.hash.split("?")[1]) || "");
  const view = q.get("view") || "dynamics";
  const p = new URLSearchParams({ view: view === "blocks" ? "dynamics" : "blocks" });       // the same system, the same ones open
  for (const k of ["system", "open"]) if (q.has(k)) p.set(k, q.get(k));
  return `#/diagram?${p}`;
}
function splitMake() {
  if (splitPane) return;
  splitFrame = h("iframe", { title: "The second view", src: `${location.pathname}?pane=1${otherView()}` });
  splitPane = h("div", { class: "split-pane" }, splitFrame);
  splitSep = h("div", { class: "split-sep", role: "separator", title: "Drag to resize; double-click for half and half; drag to the edge to close",
                        onpointerdown: (ev) => splitDrag(ev, SPLIT.edge, true),
                        ondblclick: () => { SPLIT.frac = 0.5; splitSave(); splitLayout(); } });
  document.body.append(splitPane, splitSep);
}
function splitTop() { return document.querySelector("header.bar")?.getBoundingClientRect().bottom || 0; }
function splitTotal(edge) { return edge === "left" || edge === "right" ? innerWidth : innerHeight - splitTop(); }

/* where everything goes: the pane on its edge at its size, the separator beside it, the main pane in the
   rest (its margin), and the box of the main pane, for the panels drawn over it */
function splitLayout(loose = false) {
  const on = splitShown();
  const B = document.body;
  const shown = on && !B.classList.contains("split-on");
  B.classList.toggle("split-on", on);
  for (const e of SPLIT_EDGES) B.classList.toggle(`split-${e}`, on && SPLIT.edge === e);
  if (splitPane) { splitPane.hidden = !on; splitSep.hidden = !on; }
  if (!on) { S.xhover = new Set(); return; }
  if (shown && splitPane) peerSay({ type: "sel", parts: [...S.sel] });    // shown again: what is chosen now (when new, it asks)
  splitMake();
  const top = splitTop(), total = splitTotal(SPLIT.edge);
  const want = Math.round(SPLIT.frac * total);
  const size = loose ? Math.max(0, Math.min(total, want)) : Math.max(SPLIT_MIN, Math.min(total - SPLIT_MIN, want));
  const sep = splitSep.getBoundingClientRect()[SPLIT.edge === "left" || SPLIT.edge === "right" ? "width" : "height"] || 8;
  const px = (v) => `${Math.round(v)}px`;
  B.style.setProperty("--split-top", px(top));
  B.style.setProperty("--split-size", px(size));
  B.style.setProperty("--main-top", px(SPLIT.edge === "top" ? top + size + sep : top));
  B.style.setProperty("--main-right", px(SPLIT.edge === "right" ? size + sep : 0));
  B.style.setProperty("--main-bottom", px(SPLIT.edge === "bottom" ? size + sep : 0));
  B.style.setProperty("--main-left", px(SPLIT.edge === "left" ? size + sep : 0));
}

/* an edge's grip, or the separator, dragged: the pane follows the pointer; let go near the edge, it closes */
function splitDrag(ev, edge, isSep = false) {
  if (ev.button) return;
  ev.preventDefault();
  ev.stopPropagation();
  const x0 = ev.clientX, y0 = ev.clientY, was = { ...SPLIT };
  let moved = false;
  document.body.classList.add("split-dragging");      // (the frame lets the pointer through meanwhile)
  const at = (e) => ({ right: innerWidth - e.clientX, left: e.clientX, top: e.clientY - splitTop(), bottom: innerHeight - e.clientY }[edge]);
  const move = (e) => {
    if (!moved && Math.hypot(e.clientX - x0, e.clientY - y0) < 4) return;
    moved = true;
    SPLIT.edge = edge; SPLIT.open = true;
    SPLIT.frac = Math.max(0, at(e)) / splitTotal(edge);
    splitLayout(true);
  };
  const up = (e) => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", up);
    window.removeEventListener("pointercancel", up);
    document.body.classList.remove("split-dragging");
    if (!moved) { Object.assign(SPLIT, was); splitLayout(); return; }
    const size = Math.max(0, at(e));
    if (size < SPLIT_CLOSE) SPLIT.open = false;
    else SPLIT.frac = Math.max(SPLIT_MIN, Math.min(splitTotal(edge) - SPLIT_MIN, size)) / splitTotal(edge);
    splitSave();
    splitLayout();
    if (!SPLIT.open) peerSay({ type: "hover", parts: [] });
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", up);
  window.addEventListener("pointercancel", up);
  if (isSep) splitSep.setPointerCapture?.(ev.pointerId);
}

/* the four grips on the canvas's edges (pageDiagram calls it); none in the second pane */
function splitGrips(wrap) {
  if (PANE) return;
  for (const edge of SPLIT_EDGES) {
    wrap.append(h("div", { class: "split-grip", "data-edge": edge, title: "Drag in to show a second view beside this one",
                           onpointerdown: (ev) => splitDrag(ev, edge) }));
  }
}

if (PANE) {
  /* the second pane: no header; the side panel over it; a page that is not a diagram opens in the page */
  document.body.classList.add("pane", "split-on");
  for (const k of ["--main-top", "--main-right", "--main-bottom", "--main-left"]) document.body.style.setProperty(k, "0px");
  document.addEventListener("click", (ev) => {
    const a = ev.target.closest?.("a[href^='#/']");
    if (a && !diagramHash(a.getAttribute("href"))) { ev.preventDefault(); ev.stopPropagation(); peerSay({ type: "go", hash: a.getAttribute("href") }); }
  }, true);
  window.addEventListener("hashchange", () => {
    if (!diagramHash(location.hash)) { peerSay({ type: "go", hash: location.hash }); history.back(); }
  });
  peerSay({ type: "hello" });                         // what is chosen already, please
} else {
  window.addEventListener("resize", () => splitLayout());
  window.addEventListener("hashchange", () => splitLayout());
  const bar = document.querySelector("header.bar");
  if (bar && typeof ResizeObserver === "function") new ResizeObserver(() => splitLayout()).observe(bar);
  splitLayout();
}
