/* the diagram in hand: choosing parts and moving them.

   Choosing: a click with Shift (or Command) adds a part to the chosen ones or takes it away; a drag on
   the background with Shift (or Command) draws a box, and what it touches is added (as Figma's and
   tldraw's Shift: a plain drag still pans, and two fingers scroll); a click on the background, or
   Escape, lets them all go. They are marked.

   Moving: a part dragged moves alone, or with all the chosen ones if it is one of them; an open system
   dragged by its top moves with everything in it. While they move, their lines keep the shape they last
   had, greyed, and take their new way as libavoid answers (never a straight line across). Let go, they
   are pinned where they are (places.js) and only the lines are routed again: no new layout. A new layout
   is for parts added or taken away, or asked for (unpin) */
"use strict";

S.sel = new Set();

/* a part pressed (drawGraph's handler): a drag, or a click (which chooses it, with Shift or Command) */
function partDown(ev, n) {
  if (ev.button) return;
  const choose = ev.shiftKey || ev.metaKey;
  S.downOn = choose ? null : n.id;                     // choosing is not opening its panel
  S.nodeDrag = { id: n.id, x0: ev.clientX, y0: ev.clientY, moved: false, choose };
}

/* the chosen parts marked, and the lines waiting for libavoid greyed (after every drawing) */
function markInteraction(svg) {
  for (const el of svg.querySelectorAll(".node")) el.classList.toggle("selected", S.sel.has(el.dataset.id));
  const stale = new Set((S.layout?.edges || []).filter((le) => le.stale).map((le) => le.id));
  for (const el of svg.querySelectorAll(".edge")) el.classList.toggle("stale", stale.has(el.dataset.id));
}

/* a line with a slanted piece (a stand-in from part to part, until libavoid's way comes) drawn square
   instead, and greyed: the diagram never shows a line across */
function squareLines(lay, g) {
  if (g?.kind === "wiring") return;
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
  settle(S.layout, S.graph, placed);
  drawGraph(svg, S.graph, S.layout);
  if (S.graph.kind !== "wiring") avoidStart(S.layout, S.graph);
}

function interactions(svg) {
  const byId = () => Object.fromEntries((S.graph?.nodes || []).map((n) => [n.id, n]));

  window.addEventListener("pointermove", (ev) => {      // a part (or the chosen ones) dragged
    const d = S.nodeDrag;
    if (!d || !S.layout) return;
    if (!d.moved && Math.hypot(ev.clientX - d.x0, ev.clientY - d.y0) < 5) return;
    if (!d.moved) {
      const ids = S.sel.has(d.id) ? [...S.sel] : [d.id];
      d.parts = S.layout.children.filter((k) => ids.includes(k.id)).map((k) => ({ id: k.id, x: k.x, y: k.y }));
      greyLines(svg, d.parts.map((p) => p.id));
      d.moved = true;
      S.downOn = null;                                  // a drag is not a click
      svg.classList.add("dragging-part");
    }
    const dx = (ev.clientX - d.x0) / S.view.k, dy = (ev.clientY - d.y0) / S.view.k;
    for (const p of d.parts) svg.querySelector(`.node[data-id="${CSS.escape(p.id)}"]`)?.setAttribute("transform", `translate(${p.x + dx},${p.y + dy})`);
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
      if (d.choose) { if (S.sel.has(d.id)) S.sel.delete(d.id); else S.sel.add(d.id); markInteraction(svg); }
      return;
    }
    const nodes = byId(), box = Object.fromEntries(S.layout.children.map((k) => [k.id, k])), pins = {};
    for (const p of d.parts) {
      const k = box[p.id];
      if (!k) continue;
      k.x = Math.round(p.x + d.dx); k.y = Math.round(p.y + d.dy);
      const id = pinId(p.id, nodes[p.id]);
      pins[id] = pinFor(S.layout, S.graph, nodes[p.id]?.kind === "system" ? id : p.id, k.x, k.y);
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
      greyLines(svg, d.parts.map((p) => p.id));
      d.moved = true;
      svg.classList.add("dragging-part");
    }
    const dx = (ev.clientX - d.x0) / S.view.k, dy = (ev.clientY - d.y0) / S.view.k;
    for (const name of d.hulls) svg.querySelector(`g.hull[data-hull="${CSS.escape(name)}"]`)?.setAttribute("transform", `translate(${dx},${dy})`);
    for (const p of d.parts) svg.querySelector(`.node[data-id="${CSS.escape(p.id)}"]`)?.setAttribute("transform", `translate(${p.x + dx},${p.y + dy})`);
    d.dx = dx; d.dy = dy;
    follow(svg, d, d.parts.map((p) => [p.id, Math.round(p.x + dx), Math.round(p.y + dy)]));
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
    for (const c of S.layout.children) {
      if (S.graph?.nodes.find((n) => n.id === c.id)?.kind === "cloud") continue;
      if (c.x < p1.x && c.x + c.width > p0.x && c.y < p1.y && c.y + c.height > p0.y) S.sel.add(c.id);
    }
    markInteraction(svg);
  });
  svg.addEventListener("click", (ev) => {               // the background clicked: first the chosen ones are let go
    if (!S.sel.size || S.dragged || ev.shiftKey || ev.metaKey || ev.target.closest(".node") || ev.target.closest("[data-act]") ||
        document.elementFromPoint(ev.clientX, ev.clientY)?.closest(".edge")) return;
    S.sel.clear();
    markInteraction(svg);
    ev.stopImmediatePropagation();
  }, true);
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && S.sel.size) { S.sel.clear(); markInteraction(svg); }
  });
}

/* a system about to be opened or closed: where it is, so the new layout puts it there again */
function rememberAnchor(name) {
  const lay = S.layout, g = S.graph;
  if (!lay || !g) return;
  const c = (lay.containers || []).find((o) => o.name === name);
  const box = lay.children.find((k) => g.nodes.find((n) => n.id === k.id && n.kind === "system" && n.label === name));
  const at = c || box;
  S.anchor = at ? { name, x: at.x, y: at.y } : null;
}
