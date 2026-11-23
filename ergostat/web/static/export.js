/* saving the diagram as a standalone SVG file */
"use strict";
const STYLE_PROPS = ["fill", "stroke", "stroke-width", "stroke-dasharray", "stroke-linecap", "stroke-linejoin", "opacity",
                     "font-family", "font-size", "font-weight", "letter-spacing", "text-transform", "text-anchor",
                     "font-style", "paint-order", "fill-opacity", "stroke-opacity"];   // (halos: paint-order strokes)
const DEFAULTS = { opacity: "1", "stroke-dasharray": "none", "stroke-linecap": "butt", "stroke-linejoin": "miter", "letter-spacing": "normal",
                   "text-transform": "none", "text-anchor": "start", "font-weight": "400", stroke: "none", "stroke-width": "1px",
                   "font-style": "normal", "paint-order": "normal", "fill-opacity": "1", "stroke-opacity": "1" };
/* a saved picture is drawn light, whatever the page's theme: the dark tokens step aside while it is read (style.css) */
function standaloneSvg(svg, title) {
  document.documentElement.classList.add("export-light");
  try { return standaloneSvgLight(svg, title); } finally { document.documentElement.classList.remove("export-light"); }
}
function standaloneSvgLight(svg, title) {
  if (!S.layout) return null;
  const clone = svg.cloneNode(true);
  const src = svg.querySelectorAll("*"), dst = clone.querySelectorAll("*");
  const font = getComputedStyle(svg).getPropertyValue("font-family");
  const drop = [];
  src.forEach((el, i) => {
    const cs = getComputedStyle(el), d = dst[i];
    if (el.classList?.contains("flowing") || cs.display === "none") drop.push(d);   // nor the animation, nor what is hidden
    // resolved values only, and only what differs from SVG's own defaults: a var() would not survive the file
    const style = STYLE_PROPS.map((p) => [p, cs.getPropertyValue(p)])
      .filter(([p, v]) => v && DEFAULTS[p] !== v && !(p === "font-family" && v === font) && !(p === "font-size" && el.tagName !== "text" && el.tagName !== "tspan"))
      .map(([p, v]) => `${p}:${v}`).join(";");
    for (const a of [...d.attributes]) if (a.value.includes("var(") || a.name.startsWith("data-") || a.name === "class") d.removeAttribute(a.name);
    if (style) d.setAttribute("style", style); else d.removeAttribute("style");
  });
  for (const f of drop) f.remove();
  clone.querySelector("#viewport").setAttribute("transform", "");
  const lw = S.layout.width;
  // a legend under the diagram, each view's own, wrapped to its width
  const legend = !title ? null : svg.classList.contains("bd") ? bdExportLegend(Math.max(360, lw)) : !svg.querySelector(".k-stock") ? null
    : S.graph?.kind === "dynamics" ? sdExportLegend(Math.max(360, lw)) : exportLegend(0, 0, getComputedStyle(document.body).color, getComputedStyle(document.body).getPropertyValue("--muted") || "#666",
                   svg.classList.contains("design"), Math.max(360, lw));
  const foot = legend ? legend.h + 24 : 0;
  const pad = 20, head = title ? 34 : 0, w = lw + pad * 2, hgt = S.layout.height + pad * 2 + head + foot;
  const x0 = (S.layout.ox || 0) - pad, y0 = (S.layout.oy || 0) - pad - head;     // outlines may reach left of or above the nodes
  clone.setAttribute("viewBox", `${x0} ${y0} ${w} ${hgt}`);
  clone.setAttribute("width", w);
  clone.setAttribute("height", hgt);
  clone.setAttribute("xmlns", NS);
  clone.removeAttribute("class");
  clone.setAttribute("style", `font-family:${font}`);
  const bg = getComputedStyle(document.body).backgroundColor, ink = getComputedStyle(document.body).color;
  clone.insertBefore(s("rect", { x: x0, y: y0, width: w, height: hgt, fill: bg }), clone.firstChild);
  if (legend) { legend.g.setAttribute("transform", `translate(${x0 + pad},${y0 + hgt - foot + 14})`); clone.append(legend.g); }
  if (title) {                                   // a file on its own says what it is and when
    const muted = getComputedStyle(document.body).getPropertyValue("--muted") || ink;
    clone.append(s("text", { x: x0 + pad, y: y0 + 24, style: `fill:${ink};font-size:15px;font-weight:700` }, title[0]),
                 s("text", { x: x0 + w - pad, y: y0 + 24, style: `fill:${muted};font-size:12px;text-anchor:end` }, title[1]));
  }
  return { text: new XMLSerializer().serializeToString(clone), w, hgt };
}

function download(blob, name) {
  const a = h("a", { href: URL.createObjectURL(blob), download: name });
  document.body.append(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
}

/* the legend of a control diagram, in one row, with colours resolved: a picture on its own in a document */
function exportLegend(x, y, ink, muted, design = false, width = 1e9) {
  const css = (v) => getComputedStyle(document.body).getPropertyValue(v).trim() || ink;
  const g = s("g", { style: `font-size:11px;fill:${muted}` });
  const items = [
    [`<rect x="0" y="-9" width="20" height="12" rx="2" style="fill:${css("--stock")};stroke:${css("--stock-line")};stroke-width:1.6"/>`, "stock"],
    [`<path d="M0,-3 H20" style="stroke:${css("--pipe")};stroke-width:6"/><path d="M0,-3 H20" style="stroke:${css("--pipe-in")};stroke-width:2"/>`, "flow"],
    [`<path d="M2,-9 L10,-3 L2,3 Z M18,-9 L10,-3 L18,3 Z" style="fill:${css("--valve")}"/>`, "valve (an agent acts)"],
    [`<path d="M10,-10 L18,-3 L10,4 L2,-3 Z" style="fill:none;stroke:${css("--dist")};stroke-width:1.6"/>`, "disturbance"],
    [`<circle cx="10" cy="-3" r="7" style="fill:${css("--sensor")};stroke:${css("--sensor-line")};stroke-width:1.6"/>`, "sensor"],
    [`<rect x="0" y="-9" width="20" height="12" rx="3" style="fill:${css("--ctl")};stroke:${css("--ctl-line")};stroke-width:1.6"/>`, "controller"],
    [`<path d="M0,-3 H20" style="stroke:${css("--ok")};stroke-width:2"/>`, "goal holding"],
    [`<path d="M0,-3 H20" style="stroke:${css("--bad")};stroke-width:2"/>`, "off"],
    ["", "agents: " + RUNG_NAMES.map((k, i) => `${RUNG_LETTER[i]} ${k}`).join(" · ")],
  ];
  let cx = x, cy = y;
  for (const [icon, text] of items.filter(([, t]) => !design || !["goal holding", "off"].includes(t))) {
    const need = (icon ? 26 : 0) + text.length * 6.2;
    if (cx > x && cx + need > x + width) { cx = x; cy += 20; }         // the next row
    if (icon) { const ic = s("g", { transform: `translate(${cx},${cy})` }); ic.innerHTML = icon; g.append(ic); cx += 26; }
    g.append(s("text", { x: cx, y: cy + 1 }, text));
    cx += text.length * 6.2 + 20;
  }
  return { g, h: cy - y + 20 };
}

/* the Blocks legend in a saved picture: each row's symbol, then its words wrapped to the width */
function bdExportLegend(width) {
  const ink = getComputedStyle(document.body).color, per = Math.max(30, Math.floor((width - 36) / 6.2));
  const g = s("g", { style: `font-size:11px;fill:${ink};color:${ink}` }), kids = [...blocksLegend().children];
  let y = 0;
  for (let i = 0; i + 1 < kids.length; i += 2) {
    const icon = kids[i].querySelector("svg"), lines = [];
    for (const word of kids[i + 1].textContent.split(" "))
      if (lines.length && (lines.at(-1) + " " + word).length <= per) lines[lines.length - 1] += " " + word; else lines.push(word);
    const ic = s("g", { transform: `translate(0,${y - 13})` });
    if (icon) ic.innerHTML = icon.innerHTML; else lines[0] = kids[i].textContent + "  " + lines[0];
    g.append(ic, ...lines.map((t, j) => s("text", { x: 36, y: y + j * 14 }, t)));
    y += lines.length * 14 + 8;
  }
  return { g, h: y };
}

function exportTitle() {
  const { q } = parseRoute();
  const at = new Date((S.at || nowS()) * 1000).toLocaleString([], { hour12: false, dateStyle: "medium", timeStyle: "short" });
  const view = !q.get("view") || q.get("view") === "control" ? "dynamics" : q.get("view");
  return [`${S.status?.name || "ergostat"} · ${q.get("system") || "everything"} · ${view}`,
          `${S.at || SNAP ? "as of" : "live,"} ${at} · window ${S.since}`];
}

function exportSvg(svg, name, design = false) {
  if (design) svg.classList.add("design");               // the parts and how they connect: for a document
  const title = exportTitle();
  if (design) title[1] = "the design: parts, flows, roles and schedules";
  const out = standaloneSvg(svg, title);
  if (design) svg.classList.remove("design");
  if (out) download(new Blob([out.text], { type: "image/svg+xml" }), name);
}

/* the model behind the picture, as Markdown (export_api.py): the server writes it for the system drawn, so a
   snapshot file, which has no server, says it cannot */
async function exportMarkdown(view) {
  if (SNAP) { alert("A snapshot file cannot export the model: it has no server. Export it from ergostat web, where the model is."); return; }
  const q = new URLSearchParams({ view, format: "json", since: S.since, ...(S.at ? { at: String(S.at) } : {}) });
  for (const [k, v] of Object.entries(S.graphQ || {})) if (v) q.set(k, v);
  const r = await fetch(`/api/export?${q}`);
  if (!r.ok) { alert(`The export failed: ${r.status}`); return; }
  const d = await r.json();
  download(new Blob([d.markdown], { type: "text/markdown" }), d.file);
}

/* the same picture as a PNG at twice the size, for slides and chat */
function exportPng(svg, name) {
  const out = standaloneSvg(svg, exportTitle());
  if (!out) return;
  const img = new Image();
  img.onload = () => {
    const k = 2, canvas = document.createElement("canvas");
    canvas.width = out.w * k; canvas.height = out.hgt * k;
    const ctx = canvas.getContext("2d");
    ctx.scale(k, k);
    ctx.drawImage(img, 0, 0);
    canvas.toBlob((b) => download(b, name.replace(/\.svg$/, ".png")), "image/png");
  };
  img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(out.text);
}

