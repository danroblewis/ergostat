/* saving the diagram as a standalone SVG file */
"use strict";
const STYLE_PROPS = ["fill", "stroke", "stroke-width", "stroke-dasharray", "stroke-linecap", "stroke-linejoin", "opacity",
                     "font-family", "font-size", "font-weight", "letter-spacing", "text-transform", "text-anchor"];
function exportSvg(svg, name) {
  if (!S.layout) return;
  const clone = svg.cloneNode(true);
  const src = svg.querySelectorAll("*"), dst = clone.querySelectorAll("*");
  src.forEach((el, i) => {
    const cs = getComputedStyle(el);
    const style = STYLE_PROPS.map((p) => `${p}:${cs.getPropertyValue(p)}`).join(";");
    dst[i].setAttribute("style", style + (dst[i].getAttribute("style") ? ";" + dst[i].getAttribute("style") : ""));
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
  const blob = new Blob([new XMLSerializer().serializeToString(clone)], { type: "image/svg+xml" });
  const a = h("a", { href: URL.createObjectURL(blob), download: name });
  document.body.append(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
}

