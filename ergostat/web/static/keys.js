/* the diagram by keyboard: everything a click acts on is a button Tab reaches, named for a screen reader;
   Enter or Space does what its click does. A panel opened so takes the focus to its heading, and Escape
   gives it back to the part; a redraw keeps the focus on the part it was on (by its key, as it is drawn anew) */
"use strict";
const KEYS = ".node, .edge, [data-act]:not(.hull-grip), .sys-btn, .sys-hull-label, .bd-frame";
const ACT_WORDS = { close: "Close", into: "Into", open: "Open", unpin: "Unpin", "": "System" };
const nodeOf = (id) => id && S.graph?.nodes.find((x) => x.id === id);
const saidIn = (el) => [...el.querySelectorAll("text")].filter((t) => t.closest(KEYS) === el)
  .map((t) => t.textContent.replace(/[▾⤓]/g, "").trim()).filter(Boolean);
/* what a screen reader says for it: what it is, and what is written on it ('stock backlog, 13 tickets') */
function ariaOf(el, said) {
  const n = nodeOf(el.dataset.id), host = el.parentElement?.closest(".node, [data-hull]");
  if (el.matches(".node")) return [`${n?.kind || "part"} ${said.join(", ") || n?.label || ""}`, n?.status].filter(Boolean).join(", ");
  if (el.matches(".edge")) { const e = S.edgeById?.[el.dataset.id], end = (x) => String(x || "").replace(/^\w+:/, "");
    return e ? `${e.kind} line from ${end(e.source)} to ${end(e.target)}` : "line"; }
  if (el.matches(".loop-marker, .measure-row, .bd-frame")) return `${el.dataset.act || "frame"} ${said.join(", ")}`;
  const act = el.matches(".sys-btn") ? said[0] : ACT_WORDS[el.dataset.act || ""] || el.dataset.act;
  return `${act} ${nodeOf(host?.dataset.id)?.label || host?.dataset.hull || el.dataset.id || said.join(" ")}`;
}
/* after each drawing (markInteraction): each clickable part made a button, and the focus kept where it was */
function keyable(svg) {
  for (const el of svg.querySelectorAll(KEYS)) {
    if (el.matches(".k-cloud") && !nodeOf(el.dataset.id)?.beyond) continue;   // (a cloud is no control)
    const said = saidIn(el), host = el.parentElement?.closest(".node, [data-hull]");
    el.setAttribute("tabindex", "0"); el.setAttribute("role", "button"); el.setAttribute("aria-label", ariaOf(el, said));
    el.dataset.key = [el.classList[0], el.dataset.id, el.dataset.loop, el.dataset.hull, el.dataset.act, host?.dataset.id,
                      el.matches(".node, .edge") ? "" : said[0]].join("|");
  }
  const back = S.keyAt && document.activeElement === document.body && svg.querySelector(`[data-key="${CSS.escape(S.keyAt)}"]`);
  if (back) back.focus({ preventScroll: true });
}
/* Enter or Space on it: what a click on it does */
function keyPress(el) {
  S.keyBack = el.dataset.key; S.keyHead = true;          // (showDetail moves the focus to a panel it opens)
  const n = el.matches(".node") && nodeOf(el.dataset.id), e = el.matches(".edge") && S.edgeById?.[el.dataset.id];
  if (S.graph?.kind !== "blocks" && n) return partClick(n);   // a part: as pressed and let go (diagram.js)
  if (S.graph?.kind !== "blocks" && e) return openEdge(e);
  const r = el.getBoundingClientRect();                  // at its middle, as a pointer would be
  el.dispatchEvent(new MouseEvent("click", { bubbles: true, clientX: r.x + r.width / 2, clientY: r.y + r.height / 2 }));
}
document.addEventListener("keydown", (ev) => {
  const el = ev.target;
  if ((ev.key === "Enter" || ev.key === " ") && el.matches?.("svg [data-key]")) { ev.preventDefault(); keyPress(el); }
  else if (ev.key === "Escape" && S.keyBack && !$("#detail")?.hidden) {   // (main.js closes the panel)
    $(`svg.canvas [data-key="${CSS.escape(S.keyBack)}"]`)?.focus(); S.keyBack = null; }
});
document.addEventListener("focusin", (ev) => { S.keyAt = ev.target.matches?.("svg [data-key]") ? ev.target.dataset.key : null; });
document.addEventListener("pointerdown", () => { S.keyAt = S.keyHead = S.keyBack = null; }, true);
