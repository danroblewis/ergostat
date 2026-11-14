/* start: the window, the time slider, routing */
"use strict";
/* ------------------------------------------------------------------ start */

$("#since").addEventListener("change", (ev) => { S.since = ev.target.value; S.graphSig = ""; route(); });

/* the time slider: the right end is now (live); anywhere else is that moment, over the window before it */
const WINDOWS = { "10m": 600, "1h": 3600, "6h": 21600, "1d": 86400, "7d": 604800 };
function sliderSpan() {
  const now = Date.now() / 1000;
  const lo = Math.max(now - WINDOWS[S.since] * 3, S.first || now - WINDOWS[S.since]);
  return [lo, now];
}
function showAt() {
  const label = $("#atlabel"), live = $("#live");
  if (!S.at) { label.textContent = "live"; live.hidden = true; $("#at").value = 1000; return; }
  const d = new Date(S.at * 1000);
  label.textContent = "as of " + d.toLocaleTimeString([], { hour12: false }) + ` (${ago(S.at)})`;
  live.hidden = false;
}
$("#at").addEventListener("input", (ev) => {
  const [lo, hi] = sliderSpan();
  const v = +ev.target.value;
  S.at = v >= 998 ? null : lo + (hi - lo) * (v / 1000);
  showAt();
});
$("#at").addEventListener("change", () => { refreshHeader(); route(); });
$("#live").addEventListener("click", () => { S.at = null; showAt(); refreshHeader(); route(); });
window.addEventListener("hashchange", route);
document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") closeDetail(); });
(async () => {
  await refreshHeader();
  setInterval(refreshHeader, 3000);
  if (!location.hash && window.innerWidth < 700) location.hash = "#/loops";   // on a phone, the loops first
  route();
})();
