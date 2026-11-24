/* the side panel (#detail), opened from a new page: openPanel({ kind, title, body }) shows ``body`` (a component's
   drawing, html`<${Goal} name=${n} />`, or an element made the old way, through Dom) under its kind and title, in the
   one panel frame the old openers use too (details.js showDetail: its ×, Escape, the focus to its heading when opened
   by keyboard, "About this" last). Its body stays a live component: its useApi calls are asked again when the window
   changes, and it is unmounted (its calls aborted) when the panel is closed or another is opened in its place */
import { html, render } from "/static/app/core.js";
import { Dom } from "/static/app/components/dom.js";

const open = new Set();
let watching = null;
function unmountGone() {
  for (const box of open) if (!box.isConnected) { open.delete(box); render(null, box); }
}

export function openPanel({ kind, title, body }) {
  const panel = document.getElementById("detail");
  if (!watching) (watching = new MutationObserver(unmountGone)).observe(panel, { childList: true });
  const box = document.createElement("div");
  box.className = "panel-body";
  render(body?.nodeType ? html`<${Dom} node=${body} />` : body, box);
  open.add(box);
  const head = document.createElement("div"), h2 = document.createElement("h2");
  head.className = "kind";
  head.textContent = kind;
  h2.textContent = title;
  showDetail(head, h2, box);
  return box;
}

/* the panel closed, as its × does */
export const closePanel = () => shutDetail();
