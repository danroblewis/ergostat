/* saving the diagram as a standalone SVG file */
"use strict";
const STYLE_PROPS = ["fill", "stroke", "stroke-width", "stroke-dasharray", "stroke-linecap", "stroke-linejoin", "opacity",
                     "font-family", "font-size", "font-weight", "letter-spacing", "text-transform", "text-anchor"];
function standaloneSvg(svg) {
  if (!S.layout) return null;
  const clone = svg.cloneNode(true);
  const src = svg.querySelectorAll("*"), dst = clone.querySelectorAll("*");
  src.forEach((el, i) => {
    const cs = getComputedStyle(el);
    const style = STYLE_PROPS.map((p) => `${p}:${cs.getPropertyValue(p)}`).join(";");
    dst[i].setAttribute("style", style);          // resolved values only: a var() would not survive the file
    dst[i].classList?.remove("dim");
  });
  for (const f of clone.querySelectorAll(".flowing")) f.remove();          // the animation does not survive a file
  clone.querySelector("#viewport").setAttribute("transform", "");
  const pad = 20, w = S.layout.width + pad * 2, hgt = S.layout.height + pad * 2;
  clone.setAttribute("viewBox", `${-pad} ${-pad} ${w} ${hgt}`);
  clone.setAttribute("width", w);
  clone.setAttribute("height", hgt);
  clone.setAttribute("xmlns", NS);
  clone.removeAttribute("class");
  const bg = getComputedStyle(document.body).backgroundColor;
  clone.insertBefore(s("rect", { x: -pad, y: -pad, width: w, height: hgt, fill: bg }), clone.firstChild);
  return { text: new XMLSerializer().serializeToString(clone), w, hgt };
}

function download(blob, name) {
  const a = h("a", { href: URL.createObjectURL(blob), download: name });
  document.body.append(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
}

function exportSvg(svg, name) {
  const out = standaloneSvg(svg);
  if (out) download(new Blob([out.text], { type: "image/svg+xml" }), name);
}

/* the same picture as a PNG at twice the size, for slides and chat */
function exportPng(svg, name) {
  const out = standaloneSvg(svg);
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

