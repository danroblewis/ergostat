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
  const pad = 20, head = title ? 34 : 0, w = S.layout.width + pad * 2, hgt = S.layout.height + pad * 2 + head;
  const x0 = (S.layout.ox || 0) - pad, y0 = (S.layout.oy || 0) - pad - head;     // outlines may reach left of or above the nodes
  clone.setAttribute("viewBox", `${x0} ${y0} ${w} ${hgt}`);
  clone.setAttribute("width", w);
  clone.setAttribute("height", hgt);
  clone.setAttribute("xmlns", NS);
  clone.removeAttribute("class");
  clone.setAttribute("style", `font-family:${font}`);
  const bg = getComputedStyle(document.body).backgroundColor, ink = getComputedStyle(document.body).color;
  clone.insertBefore(s("rect", { x: x0, y: y0, width: w, height: hgt, fill: bg }), clone.firstChild);
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

