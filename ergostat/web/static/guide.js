/* the Guide: a sequence of frames, one line of text each, the diagram doing the explaining. Each
   frame is a tiny model (ergostat/guide.py) drawn by the real renderers, the dynamics view's
   (diagram.js, dynamics.js) and the blocks view's (blocks.js); where it shows behaviour, a small
   graph of it, integrated here from the frame's equations (Euler). The last frame is the project's own. */
"use strict";

let GUIDE_QUEUE = Promise.resolve();          // the renderers keep their state in S: one drawing at a time

async function pageGuide(main, q) {
  const p = page(main, "Guide");
  const d = await api("guide");
  const frames = d.frames;
  const at = (k) => Math.max(0, Math.min(frames.length - 1, k));
  let i = at(parseInt(q.get("frame") || "0", 10) || 0);
  const steps = h("div", { class: "g-steps" });
  let last = null;
  frames.forEach((f, k) => {
    if (f.part !== last) {                          // a section's name: a link to its first frame
      steps.append(h("a", { class: "g-part", "data-part": f.part, href: routeUrl(`/guide?frame=${k}`),
                            onclick: (ev) => { ev.preventDefault(); show(k); } }, d.parts[f.part]));
      last = f.part;
    }
    steps.append(h("button", { class: "g-dot", "data-frame": String(k), title: f.text,
                               "aria-label": `Step ${k + 1} of ${frames.length}`, onclick: () => show(k) }));
  });
  const text = h("p", { class: "g-text" });
  const stage = h("div", { class: "g-stage" });
  const prev = h("button", { onclick: () => show(i - 1), title: "The previous frame (\u2190)", "aria-label": "Previous" }, "\u2190");
  const next = h("button", { onclick: () => show(i + 1), title: "The next frame (\u2192)", "aria-label": "Next" }, "\u2192");
  const count = h("span", { class: "muted small g-count" });
  const deck = h("div", { class: "g-deck", tabindex: "0" }, steps, text, stage, h("div", { class: "g-nav" }, prev, count, next));
  p.append(deck);
  let wheelAt = 0;
  deck.addEventListener("wheel", (ev) => {      // scrolling steps too, one frame a gesture
    if (Math.abs(ev.deltaY) < 12 || ev.ctrlKey || ev.metaKey) return;
    ev.preventDefault();
    if (Date.now() - wheelAt < 650) return;
    wheelAt = Date.now();
    show(i + (ev.deltaY > 0 ? 1 : -1));
  }, { passive: false });
  S.guideKey = (ev) => {
    if (!deck.isConnected || ev.target.closest?.("input, select, textarea")) return;
    if (ev.key === "ArrowRight" || ev.key === "PageDown") { ev.preventDefault(); show(i + 1); }
    if (ev.key === "ArrowLeft" || ev.key === "PageUp") { ev.preventDefault(); show(i - 1); }
  };
  async function show(k) {
    i = at(k);
    const f = frames[i];
    replaceRoute(`/guide?frame=${i}`);
    for (const b of steps.querySelectorAll(".g-dot")) {
      b.classList.toggle("on", +b.dataset.frame === i);
      if (+b.dataset.frame === i) b.setAttribute("aria-current", "step"); else b.removeAttribute("aria-current");
    }
    for (const s0 of steps.querySelectorAll(".g-part")) s0.classList.toggle("on", s0.dataset.part === f.part);
    text.textContent = f.text;
    count.textContent = `${i + 1} / ${frames.length}`;
    prev.disabled = i === 0; next.disabled = i === frames.length - 1;
    deck.dataset.frame = f.id;
    deck.dataset.drawn = "";
    const views = h("div", { class: "g-views" + (f.views?.length > 1 || f.id === "yours" ? " two" : "") });
    const wait = f.id === "yours" ? h("p", { class: "muted g-wait" }, "Drawing your system…") : "";   // (its graphs are asked for first)
    stage.replaceChildren(views, f.plot ? guidePlot(f.plot) : "", wait);
    const mine = i;
    const jobs = f.id === "yours" ? await guideYours(views) : (f.views || []).map((v) => guideView(views, v));
    await Promise.all(jobs);
    if (wait) wait.remove();
    if (mine === i) deck.dataset.drawn = f.id;      // (the tests wait for it)
  }
  await show(i);
}
document.addEventListener("keydown", (ev) => S.guideKey?.(ev));

/* one view of a frame: its diagram, drawn by the view's own renderer, framed to fit */
function guideView(box, v, caption = null) {
  const svg = s("svg", { class: "g-canvas" });
  const cell = h("div", { class: "g-view" }, svg, caption);
  box.append(cell);
  svg.addEventListener("pointerdown", (ev) => { if (!ev.target.closest(".bd-toggle")) ev.stopPropagation(); }, true);   // no drags, no pins
  let open = false;
  const draw = () => guideDraw(svg, open && v.opened ? v.opened : v.graph, v.view, () => { open = !open; draw(); });
  return draw();
}

function guideDraw(svg, g, view, toggle) {
  const job = GUIDE_QUEUE.then(() => guideDrawNow(svg, JSON.parse(JSON.stringify(g)), view, toggle));
  GUIDE_QUEUE = job.catch(() => {});
  return job;
}

async function guideDrawNow(svg, g, view, toggle) {
  if (!svg.isConnected) return;                    // stepped past before its turn came
  Object.assign(S, { graph: g, graphSig: "", showHulls: false, pins: {}, portAt: {}, portRank: {}, anchor: null, redraw: null,
                     toggleSystem: () => toggle?.() });
  const wait = (lay) => Promise.race([lay.whenRouted || Promise.resolve(), new Promise((r) => setTimeout(r, 5000))]);
  let lay;
  if (view === "blocks") {
    S.bdNoWrap = true;
    try { lay = await bdLayout(g); } finally { S.bdNoWrap = false; }
    S.layout = lay;
    bdRoute(lay, g);
    await wait(lay);
    bdDraw(svg, g, lay);
  } else {
    lay = await layoutGraph(g, 3);                  // (wide: the frame is a row)
    S.layout = lay;
    await wait(lay);
    drawGraph(svg, g, lay);
  }
  const vp = svg.querySelector("#viewport");
  vp?.removeAttribute("transform");
  let bb = { x: lay.ox || 0, y: lay.oy || 0, width: lay.width, height: lay.height };
  try { const b = vp.getBBox(); if (b.width && b.height) bb = b; } catch (e) { /* not drawn: the layout's size */ }
  const pad = 14, w = bb.width + 2 * pad, hgt = bb.height + 2 * pad;     // framed to what is drawn, labels and all
  svg.setAttribute("viewBox", `${bb.x - pad} ${bb.y - pad} ${w} ${hgt}`);
  const views = svg.closest(".g-views"), n = views ? views.children.length : 1;
  const room = ((views?.getBoundingClientRect().width || 600) - 18 * (n - 1)) / n;     // its share of the row
  const k = Math.min(1.5, room / w, 380 / hgt);
  svg.style.width = `${Math.round(w * k)}px`;
  svg.style.height = `${Math.round(hgt * k)}px`;
  svg.dataset.drawn = view;
}

/* the last frame: the project's own model, both ways, small, each a way into its diagram */
async function guideYours(box) {
  const out = [];
  for (const [view, name] of [["dynamics", "system dynamics"], ["blocks", "control"]]) {
    let g = null;
    try { g = await api("graph", { view }); } catch (e) { g = null; }
    const link = h("a", { href: `/diagram?view=${view}` }, `Open the ${name} diagram`);
    if (!g || !g.nodes.length) {
      box.append(h("div", { class: "g-view" }, h("p", { class: "muted" }, view === "blocks" ? "Nothing controlled yet: no goal, and no block that acts." : "Your model is empty. Describe your system with ergostat chat."), link));
      continue;
    }
    out.push(guideView(box, { view, graph: g }, link));
  }
  return out;
}

/* ------------------------------------------------------------------ behaviour over time */

function guideSimulate(run, until, dt) {
  const vals = { ...run.stocks };
  const input = (name, t) => { let v = 0; for (const [t0, x] of run.inputs[name]) if (t >= t0 - 1e-9) v = x; return v; };
  const sum = (terms, env) => terms.reduce((a, [c, vars]) => a + c * vars.reduce((x, v) => x * (env[v] ?? 0), 1), 0);
  const out = Object.fromEntries(run.series.map((x) => [x.of, []]));
  for (let n = 0, t = 0; t <= until + 1e-9; n++, t = n * dt) {
    const env = { ...vals };
    for (const k of Object.keys(run.inputs)) env[k] = input(k, t);
    for (const [k, terms] of Object.entries(run.aux)) env[k] = sum(terms, env);
    for (const x of run.series) out[x.of].push([t, env[x.of]]);
    for (const f of Object.values(run.flows)) {          // a flow runs one way: never below 0
      const rate = Math.max(0, sum(f.terms, env));
      if (f.to) vals[f.to] += rate * dt;
      if (f.from) vals[f.from] -= rate * dt;
    }
  }
  return out;
}

function guideNice(x) {                                 // a round number at or above x
  if (x <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(x)), m = x / p;
  return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 2.5 ? 2.5 : m <= 5 ? 5 : 10) * p;
}

function guidePlot(plot) {
  const W = 320, H = 190, L = 44, R = 78, T = 14, B = 34;
  const lines = [];
  for (const run of plot.runs) {
    const got = guideSimulate(run, plot.until, plot.dt);
    for (const x of run.series) lines.push({ pts: got[x.of], dash: x.dash, label: x.label || run.label });
  }
  const top = guideNice(Math.max(...lines.flatMap((l) => l.pts.map((p) => p[1]))) * 1.05);
  const X = (t) => L + (t / plot.until) * (W - L - R), Y = (v) => H - B - (Math.max(0, Math.min(v, top)) / top) * (H - T - B);
  const svg = s("svg", { class: "g-plot", viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img", "aria-label": `${plot.y} over ${plot.x}` });
  if (plot.band) {
    const [a, b, name] = plot.band;
    svg.append(s("rect", { class: "g-band", x: X(a), y: T, width: X(b) - X(a), height: H - T - B }),
               s("text", { class: "g-tick", x: (X(a) + X(b)) / 2, y: T + 12, "text-anchor": "middle" }, name));
  }
  svg.append(s("path", { class: "g-axis", d: `M${L},${T} V${H - B} H${W - R}` }),
             s("text", { class: "g-tick", x: L - 6, y: Y(0) + 4, "text-anchor": "end" }, "0"),
             s("text", { class: "g-tick", x: L - 6, y: Y(top) + 4, "text-anchor": "end" }, fmt(top)),
             s("text", { class: "g-tick", x: X(plot.until), y: H - B + 14, "text-anchor": "middle" }, String(plot.until)),
             s("text", { class: "g-tick", x: L, y: H - B + 14, "text-anchor": "middle" }, "0"),
             s("text", { class: "g-name", x: (L + W - R) / 2, y: H - 6, "text-anchor": "middle" }, plot.x),
             s("text", { class: "g-name", x: 12, y: (T + H - B) / 2, "text-anchor": "middle", transform: `rotate(-90 12 ${(T + H - B) / 2})` }, plot.y));
  const ends = [];
  for (const l of lines) {
    svg.append(s("path", { class: "g-line" + (l.dash ? " dash" : ""), d: l.pts.map(([t, v], k) => `${k ? "L" : "M"}${X(t).toFixed(1)},${Y(v).toFixed(1)}`).join("") }));
    if (!l.label) continue;
    const [t, v] = l.pts[l.pts.length - 1];
    let y = Y(v) + 4;
    while (ends.some((e) => Math.abs(e - y) < 12)) y += 12;    // labels at the lines' ends, never on each other
    ends.push(y);
    svg.append(s("text", { class: "g-tick g-label", x: X(t) + 5, y }, l.label));
  }
  return h("div", { class: "g-plotbox" }, svg);
}
