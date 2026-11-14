/* saving the diagram as a standalone SVG file */
"use strict";
const STYLE_PROPS = ["fill", "stroke", "stroke-width", "stroke-dasharray", "stroke-linecap", "stroke-linejoin", "opacity",
                     "font-family", "font-size", "font-weight", "letter-spacing", "text-transform", "text-anchor"];
const DEFAULTS = { opacity: "1", "stroke-dasharray": "none", "stroke-linecap": "butt", "stroke-linejoin": "miter", "letter-spacing": "normal",
                   "text-transform": "none", "text-anchor": "start", "font-weight": "400", stroke: "none", "stroke-width": "1px" };
function standaloneSvg(svg, title) {
  if (!S.layout) return null;
  const clone = svg.cloneNode(true);
  const src = svg.querySelectorAll("*"), dst = clone.querySelectorAll("*");
  const font = getComputedStyle(svg).getPropertyValue("font-family");
  const drop = [];
  src.forEach((el, i) => {
    const cs = getComputedStyle(el), d = dst[i];
    if (el.classList?.contains("flowing")) drop.push(d);           // the animation does not survive a file
    // resolved values only, and only what differs from SVG's own defaults: a var() would not survive the file
    const style = STYLE_PROPS.map((p) => [p, cs.getPropertyValue(p)])
      .filter(([p, v]) => v && DEFAULTS[p] !== v && !(p === "font-family" && v === font) && !(p === "font-size" && el.tagName !== "text" && el.tagName !== "tspan"))
      .map(([p, v]) => `${p}:${v}`).join(";");
    for (const a of [...d.attributes]) if (a.value.includes("var(") || a.name.startsWith("data-") || a.name === "class") d.removeAttribute(a.name);
    if (style) d.setAttribute("style", style); else d.removeAttribute("style");
  });
  for (const f of drop) f.remove();
  clone.querySelector("#viewport").setAttribute("transform", "");
  const foot = title && svg.querySelector(".k-stock") ? 46 : 0;     // a legend under a control diagram
  const pad = 20, head = title ? 34 : 0, w = S.layout.width + pad * 2, hgt = S.layout.height + pad * 2 + head + foot;
  const x0 = (S.layout.ox || 0) - pad, y0 = (S.layout.oy || 0) - pad - head;     // outlines may reach left of or above the nodes
  clone.setAttribute("viewBox", `${x0} ${y0} ${w} ${hgt}`);
  clone.setAttribute("width", w);
  clone.setAttribute("height", hgt);
  clone.setAttribute("xmlns", NS);
  clone.removeAttribute("class");
  clone.setAttribute("style", `font-family:${font}`);
  const bg = getComputedStyle(document.body).backgroundColor, ink = getComputedStyle(document.body).color;
  clone.insertBefore(s("rect", { x: x0, y: y0, width: w, height: hgt, fill: bg }), clone.firstChild);
  if (foot) clone.append(exportLegend(x0 + pad, y0 + hgt - foot + 14, ink, getComputedStyle(document.body).getPropertyValue("--muted") || ink));
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
function exportLegend(x, y, ink, muted) {
  const css = (v) => getComputedStyle(document.body).getPropertyValue(v).trim() || ink;
  const g = s("g", { style: `font-size:11px;fill:${muted}` });
  const items = [
    [`<rect x="0" y="-9" width="20" height="12" rx="2" style="fill:${css("--stock")};stroke:${css("--stock-line")};stroke-width:1.6"/>`, "stock"],
    [`<path d="M0,-3 H20" style="stroke:${css("--pipe")};stroke-width:6"/><path d="M0,-3 H20" style="stroke:${css("--pipe-in")};stroke-width:2"/>`, "flow"],
    [`<path d="M2,-9 L10,-3 L2,3 Z M18,-9 L10,-3 L18,3 Z" style="fill:${css("--valve")}"/>`, "valve (an agent acts)"],
    [`<path d="M10,-10 L18,-3 L10,4 L2,-3 Z" style="fill:none;stroke:${css("--dist")};stroke-width:1.6"/>`, "disturbance"],
    [`<circle cx="10" cy="-3" r="7" style="fill:${css("--sensor")};stroke:${css("--sensor-line")};stroke-width:1.6"/>`, "sensor"],
    [`<rect x="0" y="-9" width="20" height="12" rx="3" style="fill:${css("--ctl")};stroke:${css("--ctl-line")};stroke-width:1.6"/>`, "controller"],
    [`<path d="M0,-3 H20" style="stroke:${css("--ok")};stroke-width:2"/>`, "loop holding"],
    [`<path d="M0,-3 H20" style="stroke:${css("--bad")};stroke-width:2"/>`, "off"],
    ["", "agents: " + RUNG_NAMES.map((k, i) => `${RUNG_LETTER[i]} ${k}`).join(" · ")],
  ];
  let cx = x;
  for (const [icon, text] of items) {
    if (icon) { const ic = s("g", { transform: `translate(${cx},${y})` }); ic.innerHTML = icon; g.append(ic); cx += 26; }
    g.append(s("text", { x: cx, y: y + 1 }, text));
    cx += textWidth(text) + 22;
  }
  return g;
}

function exportTitle() {
  const { q } = parseRoute();
  const at = new Date((S.at || nowS()) * 1000).toLocaleString([], { hour12: false, dateStyle: "medium", timeStyle: "short" });
  return [`${S.status?.name || "ergostat"} · ${q.get("system") || "everything"} · ${q.get("view") || "control"}`,
          `${S.at || SNAP ? "as of" : "live,"} ${at} · window ${S.since}`];
}

function exportSvg(svg, name) {
  const out = standaloneSvg(svg, exportTitle());
  if (out) download(new Blob([out.text], { type: "image/svg+xml" }), name);
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

