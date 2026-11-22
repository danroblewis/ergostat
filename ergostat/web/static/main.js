/* start: the window and the moment (one control), routing */
"use strict";
/* ------------------------------------------------------------------ start */

/* the window, and the moment the page shows: the slider's right end is now (live); anywhere else is
   that moment, over the window before it. One control in the header; its menu holds both */
const WINDOWS = { "10m": 600, "1h": 3600, "6h": 21600, "1d": 86400, "7d": 604800 };
const WINDOW_WORDS = { "10m": "Last 10 minutes", "1h": "Last hour", "6h": "Last 6 hours", "1d": "Last day", "7d": "Last 7 days" };
function sliderSpan() {
  const now = nowS();
  const lo = Math.max(now - WINDOWS[S.since] * 3, S.first || now - WINDOWS[S.since]);
  return [lo, now];
}
const clock = (t) => new Date(t * 1000).toLocaleTimeString([], { hour12: false, hour: "2-digit", minute: "2-digit" });
function whenLabel() { return S.at ? `${S.since} to ${clock(S.at)}` : `Last ${S.since}`; }
const whenMenu = menu(whenLabel(), () => {
  const [lo, hi] = sliderSpan();
  const readout = h("span", { class: "muted small", id: "atlabel" }, S.at ? `${clock(S.at)}, ${ago(S.at)}` : "Live");
  const slider = h("input", { type: "range", id: "at", min: 0, max: 1000, "aria-label": "The moment shown",
                              value: S.at ? Math.round(((S.at - lo) / ((hi - lo) || 1)) * 1000) : 1000 });
  slider.addEventListener("input", () => {
    const v = +slider.value;
    S.at = v >= 998 ? null : lo + (hi - lo) * (v / 1000);
    readout.textContent = S.at ? `${clock(S.at)}, ${ago(S.at)}` : "Live";
    showAt();
  });
  slider.addEventListener("change", () => { refreshHeader(); route(); });
  return [
    h("div", { class: "menu-label" }, "Window"),
    ...Object.keys(WINDOWS).map((k) => ({ label: WINDOW_WORDS[k], checked: S.since === k, onclick: () => setWindow(k) })),
    { sep: true },
    h("div", { class: "menu-block" }, h("div", { class: "menu-label" }, "Moment"), slider, readout),
    S.at ? { label: "Back to live", onclick: () => { S.at = null; showAt(); refreshHeader(); route(); } } : null,
  ];
}, { right: true, title: "The window the page looks over, and the moment it shows" });
$("#when").append(whenMenu);
/* a window chosen: in the address (the Record's own window=1 kept), the page asked again with its panel left open */
function setWindow(k) {
  S.since = k; S.graphSig = ""; showAt();
  if (parseRoute().q.get("window") !== "1") setQuery({ window: k === "1h" ? null : k });
  return route(true).then(() => S.again?.());
}
function showAt() {
  whenMenu.button.textContent = whenLabel();
  whenMenu.button.classList.toggle("past", !!S.at);
}
window.addEventListener("popstate", route);                  // back and forward
window.addEventListener("hashchange", () => { if (HASHED || oldAddress()) route(); });   // a snapshot's route; an old #/ address
document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") shutDetail(); });
if (SNAP) {                                   // one moment, one window: nothing to slide or switch
  for (const el of [$("#when"), $("#project")]) el.style.display = "none";
  S.since = SNAP.since;
} else if (Object.hasOwn(WINDOWS, parseRoute().q.get("window") || "")) { S.since = parseRoute().q.get("window"); showAt(); }   // a link's window
(async () => {
  await refreshHeader();
  poll(refreshHeader, 5000);
  oldAddress();                                                // #/items, an old address: shown at /items
  const bare = HASHED ? !location.hash.startsWith("#/") : location.pathname === "/";
  if (bare && window.innerWidth < 700) replaceRoute("/loops");    // on a phone, the loops first
  route();
})();
