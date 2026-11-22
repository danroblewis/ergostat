/* the diagram in hand: choosing parts and moving them.

   Choosing: what is chosen is model parts, not shapes (correspond.py: each graph says which parts each
   shape is, and which shapes stand for each part), so the choice survives a change of view and is lit
   in both panes of a split (split.js). A click chooses what its shape is; with Shift (or Command) it
   adds that or takes it away; a drag on the background with Shift (or Command) draws a box, and what
   it touches is added (as Figma's and tldraw's Shift: a plain drag still pans, and two fingers
   scroll); a loop clicked chooses its members; a click on the background, or Escape, lets them all
   go. What stands for a part chosen is marked, a region holding it (and nothing of its own) dashed;
   what a shape pointed at in the other pane is, boldly (and the rest of this pane steps back), so it is
   found at a glance.

   Moving: a part dragged moves alone, or with all the chosen ones if it is one of them; an open system
   dragged by its top moves with everything in it. While they move, their lines keep the shape they last
   had, greyed, and take their new way as libavoid answers (never a straight line across). Let go, they
   are pinned where they are (places.js) and only the lines are routed again: no new layout. A new layout
   is for parts added or taken away, or asked for (unpin) */
"use strict";

S.sel = new Set();                                     // model parts: stock.x, flow.x, goal.g, goal.g.r, block.b, system.s
S.xhover = new Set();                                  // the parts pointed at in the other pane

/* the parts a shape is, in the view drawn (the Process view's nodes are no model parts: each is itself) */
function partsOf(id) { return S.graph?.kind === "process" ? [id] : S.graph?.corr?.shapes?.[id]?.is || []; }
/* what a choice lights here: each part's shapes (own, else the region holding it: "within"), and every
   shape all of whose parts are chosen */
function litShapes(sel = S.sel, corr = S.graph?.corr) {
  const out = new Map();
  if (S.graph?.kind === "process") { for (const p of sel) out.set(p, "is"); return out; }
  if (!corr || !sel.size) return out;
  for (const p of sel) for (const id of corr.parts?.[p] || []) if (out.get(id) !== "is") out.set(id, corr.inside?.[p] ? "within" : "is");
  for (const [id, x] of Object.entries(corr.shapes || {})) if (x.is.length && x.is.every((p) => sel.has(p))) out.set(id, "is");
  return out;
}
/* choose parts: only these, or added, or taken away (a shape's parts all chosen already: taken away);
   said to the other pane (split.js) */
function choose(parts, how = "only") {
  parts = [...new Set(parts || [])];
  if (how === "only") S.sel = new Set(parts);
  else if (how === "toggle" && parts.length && parts.every((p) => S.sel.has(p))) for (const p of parts) S.sel.delete(p);
  else for (const p of parts) S.sel.add(p);
  markChosen();
  if (typeof peerSay === "function") peerSay({ type: "sel", parts: [...S.sel] });
}
function chooseShape(id, how = "only") { choose(partsOf(id), how); if (how === "only") whereElse(partsOf(id)); }

/* a part chosen that the other view draws only inside a region (a turnover inside P_service, a part
   inside a closed system): said in its panel. The other view is asked as this one was drawn */
const OTHER_VIEW = { dynamics: "blocks", blocks: "dynamics" };
const OTHER_WORDS = { blocks: "In the block diagram", dynamics: "In the dynamics view" };
async function whereElse(parts) {
  S.whereNote = null;
  const other = OTHER_VIEW[S.graph?.kind];
  if (!other || !parts.length || parts.length > 3) return;
  const key = JSON.stringify([other, S.graphQ || {}]), want = [...parts].sort().join(",");
  try {
    if (S.otherCorr?.key !== key || Date.now() - S.otherCorr.at > 15000)
      S.otherCorr = { key, at: Date.now(), corr: (await api("graph", { view: other, ...(S.graphQ || {}) })).corr };
  } catch (e) { return; }                              // (a snapshot without that view: nothing said)
  if ([...S.sel].sort().join(",") !== want) return;          // chosen otherwise meanwhile
  const inside = S.otherCorr.corr?.inside || {};
  const said = parts.filter((p) => inside[p]?.length).map((p) => [p.split(".").slice(1).join("."), inside[p].join(", ")]);
  if (!said.length) return;
  S.whereNote = { parts: want, el: () => h("p", { class: "muted where-else" }, `${OTHER_WORDS[other]}: `,
    ...said.flatMap(([name, where], i) => [i ? "; " : "", parts.length > 1 ? `${name} ` : "", "inside ", rich(where)]), ".") };
  panelNote();
}
/* the note, in the open panel of what is chosen (showDetail calls it again when the panel is built) */
function panelNote(d = $("#detail")) {
  if (!d || d.hidden) return;
  d.querySelector(".where-else")?.remove();
  const n = S.whereNote;
  if (!n || n.parts !== [...S.sel].sort().join(",")) return;
  const h2 = d.querySelector("h2");
  if (h2) h2.after(n.el());
}
function markChosen() { const svg = $("svg.canvas"); if (svg) markInteraction(svg); }

/* a part pressed (drawGraph's handler): a drag, or a click (which chooses it, with Shift or Command) */
function partDown(ev, n) {
  if (ev.button) return;
  const choose = ev.shiftKey || ev.metaKey;
  S.downOn = choose ? null : n.id;                     // choosing is not opening its panel
  S.nodeDrag = { id: n.id, x0: ev.clientX, y0: ev.clientY, moved: false, choose };
}

/* the chosen parts marked, and the lines waiting for libavoid greyed (after every drawing) */
function markInteraction(svg) {
  const lit = litShapes(), near = litShapes(S.xhover);
  if (typeof paintGroups === "function") paintGroups(svg);   // each shape's colours, shown when asked (colours.js)
  svg.classList.toggle("xhovering", [...near.keys()].some((id) => !lit.has(id)));   // pointed at from the other pane: the rest steps back
  const mark = (el, id) => {
    el.classList.toggle("selected", lit.has(id));
    el.classList.toggle("within", lit.get(id) === "within");
    el.classList.toggle("xhover", near.has(id) && !lit.has(id));
  };
  for (const el of svg.querySelectorAll(".node")) mark(el, el.dataset.id);
  for (const el of svg.querySelectorAll("g.hull[data-hull]")) {     // an open system's outline (dynamics) or frame (blocks):
    const id = el.dataset.hull.startsWith("frame:") ? el.dataset.hull : "hull:" + el.dataset.hull;   // a mark over it
    const how = lit.get(id), pointed = near.has(id) && !how;
    let m = el.querySelector(":scope > rect.hull-mark");
    el.classList.toggle("xhover", pointed);
    if (!how && !pointed) { m?.remove(); continue; }
    const r = el.querySelector(":scope > rect:not(.hull-grip):not(.hull-mark)");
    if (!m && r) el.append(m = s("rect", { class: "hull-mark", x: r.getAttribute("x"), y: r.getAttribute("y"), width: r.getAttribute("width"),
                                           height: r.getAttribute("height"), rx: r.getAttribute("rx") }));
    m?.classList.toggle("within", how === "within");
    m?.classList.toggle("xhover", pointed);
  }
  const stale = new Set((S.layout?.edges || []).filter((le) => le.stale).map((le) => le.id));
  for (const el of svg.querySelectorAll(".edge")) el.classList.toggle("stale", stale.has(el.dataset.id));
  sideChartsChanged();                                 // the side panel charts what is chosen (charts.js)
  if (typeof keyable === "function") keyable(svg);    // each clickable part a button, by keyboard too (keys.js)
}

/* a line with a slanted piece (a stand-in from part to part, until libavoid's way comes) drawn square
   instead, and greyed: the diagram never shows a line across */
function squareLines(lay, g) {
  for (const le of lay.edges || []) {
    const sec = (le.sections || [])[0];
    if (!sec) continue;
    const pts = [sec.startPoint, ...(sec.bendPoints || []), sec.endPoint], out = [pts[0]];
    let slant = false;
    for (let i = 1; i < pts.length; i++) {
      const a = out[out.length - 1], b = pts[i];
      if (Math.abs(a.x - b.x) > 0.5 && Math.abs(a.y - b.y) > 0.5) { out.push({ x: b.x, y: a.y }); slant = true; }
      out.push(b);
    }
    if (!slant) continue;
    le.sections = [{ startPoint: out[0], bendPoints: out.slice(1, -1), endPoint: out[out.length - 1] }];
    le.stale = true;
  }
}

/* a line routed anew while parts move: drawn again, no longer grey */
function lineCame(svg, id) {
  redrawLine(svg, id);
  const le = S.layout?.edges.find((x) => x.id === id);
  svg.querySelector(`.edge[data-id="${CSS.escape(id)}"]`)?.classList.toggle("stale", !!le?.stale);
}

/* the lines touching some parts, greyed until libavoid routes them */
function greyLines(svg, ids) {
  const g = S.graph, set = new Set(ids);
  for (const le of S.layout?.edges || []) {
    const e = g?.edges.find((x) => x.id === le.id);
    if (!e || !(set.has(e.source) || set.has(e.target))) continue;
    le.stale = true;
    svg.querySelector(`.edge[data-id="${CSS.escape(le.id)}"]`)?.classList.add("stale");
  }
}

/* parts moving: their places sent to libavoid, one routing at a time, the latest */
function follow(svg, d, list) {
  if (S.graph?.kind === "dynamics") sdMarkersFollow(svg, list.map((x) => x[0]), d.dx, d.dy, d.name);   // the loop markers go with their loops (dynamics.js)
  d.next = list;
  const send = () => {
    if (d.busy || !d.next || d.done) return;
    const now = d.next; d.next = null;
    const answer = avoidMoveMany(now);
    if (!answer) return;
    d.busy = true;
    answer.then((ids) => { d.busy = false; if (!d.done) { for (const id of ids) lineCame(svg, id); send(); } });
  };
  send();
}

/* let go: pinned where they are, the outlines and valves made right, the lines routed again; no layout */
function putDown(svg, pins, placed) {
  S.pins = { ...(S.pins || {}), ...pins };
  savePins();
  S.dropAt = performance.now();                        // (the click that ends a drag opens nothing: blocks.js)
  settle(S.layout, S.graph, placed);
  if (S.graph.kind === "blocks") { bdDraw(svg, S.graph, S.layout); bdRouteDraw(svg, S.layout); return; }   // (blocks.js)
  if (S.graph.kind === "process") { pmPutDown(svg, S.graph, S.layout); return; }                        // (process.js)
  drawGraph(svg, S.graph, S.layout);
  avoidStart(S.layout, S.graph);
}

/* what is drawn apart from a part but goes with it while it is dragged: a summing junction's signs */
function dragAlong(svg, ids, dx, dy) {
  for (const id of ids) for (const el of svg.querySelectorAll(`[data-sum="${CSS.escape(id)}"]`)) el.setAttribute("transform", `translate(${dx},${dy})`);
}

function interactions(svg) {
  const byId = () => Object.fromEntries((S.graph?.nodes || []).map((n) => [n.id, n]));

  window.addEventListener("pointermove", (ev) => {      // a part (or the chosen ones) dragged
    const d = S.nodeDrag;
    if (!d || !S.layout) return;
    if (!d.moved && Math.hypot(ev.clientX - d.x0, ev.clientY - d.y0) < 5) return;
    if (!d.moved) {
      const lit = litShapes();                          // (the shapes standing for the parts chosen)
      const ids = lit.get(d.id) === "is" ? [...lit].filter(([, how]) => how === "is").map(([id]) => id) : [d.id];
      for (const n of S.graph?.nodes || []) {          // a stock's flows to and from clouds go with it: its satellites (satellites.js)
        const sat = (n.kind === "valve" || n.kind === "disturbance") && !ids.includes(n.id) && drainOf(S.graph, n.id);
        if (sat && ids.includes(sat.stock) && !S.pins?.[n.id] && !S.pins?.[sat.cloud]) ids.push(n.id, sat.cloud);
      }
      d.parts = S.layout.children.filter((k) => ids.includes(k.id)).map((k) => ({ id: k.id, x: k.x, y: k.y }));
      greyLines(svg, d.parts.map((p) => p.id));
      d.moved = true;
      S.downOn = null;                                  // a drag is not a click
      svg.classList.add("dragging-part");
    }
    const dx = (ev.clientX - d.x0) / S.view.k, dy = (ev.clientY - d.y0) / S.view.k;
    for (const p of d.parts) svg.querySelector(`.node[data-id="${CSS.escape(p.id)}"]`)?.setAttribute("transform", `translate(${p.x + dx},${p.y + dy})`);
    dragAlong(svg, d.parts.map((p) => p.id), dx, dy);
    d.dx = dx; d.dy = dy;
    follow(svg, d, d.parts.map((p) => [p.id, Math.round(p.x + dx), Math.round(p.y + dy)]));
  });
  window.addEventListener("pointerup", () => {
    const d = S.nodeDrag;
    S.nodeDrag = null;
    if (!d) return;
    d.done = true;
    svg.classList.remove("dragging-part");
    if (!d.moved) {                                     // a click: with Shift or Command, chosen or let go
      if (d.choose) chooseShape(d.id, "toggle");
      return;
    }
    const nodes = byId(), box = Object.fromEntries(S.layout.children.map((k) => [k.id, k])), pins = {};
    for (const p of d.parts) {
      const k = box[p.id];
      if (!k) continue;
      k.x = Math.round(p.x + d.dx); k.y = Math.round(p.y + d.dy); k.slid = false;   // (may slide off a new corner: avoid.js)
      const id = pinId(p.id, nodes[p.id]);                // (a system's box: its own, else the part's)
      pins[id] = pinFor(S.layout, S.graph, id, k.x, k.y);
    }
    putDown(svg, pins, d.parts.map((p) => p.id));
  });

  window.addEventListener("pointermove", (ev) => {      // an open system dragged by its top: it and all in it follow
    const d = S.hullDrag;
    if (!d || !S.layout) return;
    if (!d.moved && Math.hypot(ev.clientX - d.x0, ev.clientY - d.y0) < 5) return;
    if (!d.moved) {                                     // what goes with it: its parts, and the systems open inside it
      const nodes = byId();
      d.parts = S.layout.children.filter((k) => (nodes[k.id]?.systems || []).includes(d.name)).map((k) => ({ id: k.id, x: k.x, y: k.y }));
      d.hulls = (S.layout.containers || []).filter((o) => o.name === d.name || within(S.graph, o.name, d.name)).map((o) => o.name);
      // (the block diagram's frames' titles are in the lines' way too: blocks.js)
      d.titles = S.graph.kind === "blocks" ? S.layout.containers.filter((o) => d.hulls.includes(o.name)).map((o) => ({ id: o.id + ":title", x: o.x + 4, y: o.y + 4 })) : [];
      greyLines(svg, d.parts.map((p) => p.id));
      d.moved = true;
      svg.classList.add("dragging-part");
    }
    const dx = (ev.clientX - d.x0) / S.view.k, dy = (ev.clientY - d.y0) / S.view.k;
    for (const name of d.hulls) svg.querySelector(`g.hull[data-hull="${CSS.escape(name)}"]`)?.setAttribute("transform", `translate(${dx},${dy})`);
    for (const p of d.parts) svg.querySelector(`.node[data-id="${CSS.escape(p.id)}"]`)?.setAttribute("transform", `translate(${p.x + dx},${p.y + dy})`);
    dragAlong(svg, d.parts.map((p) => p.id), dx, dy);
    d.dx = dx; d.dy = dy;
    follow(svg, d, [...d.parts, ...d.titles].map((p) => [p.id, Math.round(p.x + dx), Math.round(p.y + dy)]));
  });
  window.addEventListener("pointerup", () => {
    const d = S.hullDrag;
    S.hullDrag = null;
    if (!d) return;
    d.done = true;
    if (!d.moved) return;
    svg.classList.remove("dragging-part");
    const box = Object.fromEntries(S.layout.children.map((k) => [k.id, k]));
    for (const p of d.parts) if (box[p.id]) { box[p.id].x = Math.round(p.x + d.dx); box[p.id].y = Math.round(p.y + d.dy); }
    for (const o of S.layout.containers || []) {
      if (!d.hulls.includes(o.name)) continue;
      o.x += d.dx; o.y += d.dy;
      if (o.bx != null) { o.bx += d.dx; o.by += d.dy; }
    }
    const c = S.layout.containers.find((o) => o.name === d.name);
    putDown(svg, { ["hull:" + d.name]: pinFor(S.layout, S.graph, "hull:" + d.name, c.bx ?? c.x, c.by ?? c.y) }, d.parts.map((p) => p.id));
  });

  // a box drawn with Shift (or Command) on the background: what it touches is chosen too
  let band = null;
  svg.addEventListener("pointerdown", (ev) => {
    const act = ev.target.closest("[data-act]");          // (a loop marker is no control a box may not start on)
    if (!(ev.shiftKey || ev.metaKey) || ev.button || ev.target.closest(".node") || (act && act.dataset.act !== "loop")) return;
    ev.preventDefault();
    const r = svg.getBoundingClientRect();
    band = { x0: ev.clientX - r.left, y0: ev.clientY - r.top, el: s("rect", { class: "band" }) };
    S.dragged = false;
    svg.append(band.el);
    svg.setPointerCapture(ev.pointerId);
  });
  svg.addEventListener("pointermove", (ev) => {
    if (!band) return;
    const r = svg.getBoundingClientRect(), x = ev.clientX - r.left, y = ev.clientY - r.top;
    band.x1 = x; band.y1 = y;
    if (Math.hypot(x - band.x0, y - band.y0) > 4) S.dragged = true;
    for (const [k, v] of Object.entries({ x: Math.min(x, band.x0), y: Math.min(y, band.y0), width: Math.abs(x - band.x0), height: Math.abs(y - band.y0) }))
      band.el.setAttribute(k, v);
  });
  svg.addEventListener("pointerup", () => {
    if (!band) return;
    const b = band;
    band = null;
    b.el.remove();
    if (b.x1 == null || !S.layout) return;
    const k = S.view.k, at = (sx, sy) => ({ x: (sx - S.view.x) / k, y: (sy - S.view.y) / k });
    const p0 = at(Math.min(b.x0, b.x1), Math.min(b.y0, b.y1)), p1 = at(Math.max(b.x0, b.x1), Math.max(b.y0, b.y1));
    const touched = [];
    for (const c of S.layout.children) {
      if (S.graph?.nodes.find((n) => n.id === c.id)?.kind === "cloud") continue;
      if (c.x < p1.x && c.x + c.width > p0.x && c.y < p1.y && c.y + c.height > p0.y) touched.push(...partsOf(c.id));
    }
    choose(touched, "add");
  });
  svg.addEventListener("click", (ev) => {               // the background clicked: first the chosen ones are let go
    if (!S.sel.size || S.dragged || ev.shiftKey || ev.metaKey || ev.target.closest(".node") || ev.target.closest("[data-act]") ||
        document.elementFromPoint(ev.clientX, ev.clientY)?.closest(".edge")) return;
    choose([]);
    if ($("#detail")?.hidden) ev.stopImmediatePropagation();   // (a panel open closes with it, at the same click)
  }, true);
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && S.sel.size) choose([]);
  });
  // pointing at a shape: what it is lit lightly in the other pane (split.js), nothing chosen
  let over = null;
  const point = (id) => {
    if (id === over) return;
    over = id;
    if (typeof peerSay === "function") peerSay({ type: "hover", parts: id ? partsOf(id) : [] });
  };
  svg.addEventListener("pointerover", (ev) => {
    if (S.dragging || S.nodeDrag?.moved) return;
    const el = ev.target.closest?.(".node") || ev.target.closest?.("g.hull[data-hull]");
    point(el ? (el.dataset.id || (el.dataset.hull.startsWith("frame:") ? el.dataset.hull : "hull:" + el.dataset.hull)) : null);
  });
  svg.addEventListener("pointerleave", () => point(null));
}

/* a system about to be opened or closed: where it is, so the new layout puts it there again */
function rememberAnchor(name) {
  const lay = S.layout, g = S.graph;
  if (!lay || !g) return;
  const at = anchorOf(lay, g, name);                   // (places.js)
  S.anchor = at ? { name, x: at.x, y: at.y } : null;
}
