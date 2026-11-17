/* ergostat's page: shared state, small helpers, the API, the header and routing. */
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const NS = "http://www.w3.org/2000/svg";
const elk = new ELK();
const S = { since: "1h", route: "", graphSig: "", layout: null, view: { x: 0, y: 0, k: 1 }, fitted: false,
            timer: null, status: null, sel: null, hl: null };

function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "html") el.innerHTML = v;
    else el.setAttribute(k, v);
  }
  for (const kid of kids.flat(Infinity)) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return el;
}
function s(tag, attrs = {}, ...kids) {
  const el = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) if (v != null && v !== false) {
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v); else el.setAttribute(k, v);
  }
  for (const kid of kids.flat(Infinity)) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return el;
}
/* the one number formatter: integers as they are (thousands separated from 10,000), others to three
   significant figures, a real minus */
function fmt(x) {
  if (x == null) return "?";
  if (typeof x !== "number") return String(x);
  if (!Number.isFinite(x)) return String(x);
  if (Math.abs(x) < 1e-9) x = 0;                       // floating-point dust: 1.78e-15 is nothing
  let t;
  if (Number.isInteger(x)) t = Math.abs(x) >= 10000 ? x.toLocaleString("en-US") : String(x);
  else if (Math.abs(x) >= 100) { const r = Math.round(x); t = Math.abs(r) >= 10000 ? r.toLocaleString("en-US") : String(r); }
  else t = String(+x.toPrecision(3));
  return t.replace(/^-/, "\u2212");
}
/* a condition or setpoint as it is written in print: <= as ≤, >= as ≥, == as =, != as ≠ */
const op = (x) => x == null ? "" : String(x).replaceAll("<=", "\u2264").replaceAll(">=", "\u2265").replaceAll("!=", "\u2260").replaceAll("==", "=")
  .replace(/(^|[\s(=:])-(?=\.?\d)/g, "$1\u2212");                // and a negative number's real minus
/* raw data, shown: every float to the precision that means something (the event's panel keeps it whole) */
const tidy = (v) => typeof v === "number" && !Number.isInteger(v) ? +v.toPrecision(6)
  : Array.isArray(v) ? v.map(tidy) : v && typeof v === "object" ? Object.fromEntries(Object.entries(v).map(([k, x]) => [k, tidy(x)])) : v;
/* K_p, y_m, x_{ab}: a subscript as a subscript, in HTML or in an SVG text */
const SUB = /([A-Za-z\u0370-\u03ff])_(\{[^}]+\}|[A-Za-z0-9]+)/g;
function rich(text) {
  const out = h("span"), str = String(text ?? "");
  let at = 0;
  for (const m of str.matchAll(SUB)) {
    out.append(str.slice(at, m.index) + m[1], h("sub", {}, m[2].replace(/^\{|\}$/g, "")));
    at = m.index + m[0].length;
  }
  out.append(str.slice(at));
  return out;
}
function richSvg(textEl, text) {                    // (dy, not baseline-shift: it survives a saved file in any viewer)
  const str = String(text ?? "");
  let at = 0, down = false;
  for (const m of str.matchAll(SUB)) {
    textEl.append(s("tspan", { dy: down ? -3 : null }, str.slice(at, m.index) + m[1]),
      s("tspan", { dy: 3, "font-size": "78%" }, m[2].replace(/^\{|\}$/g, "")));
    down = true;
    at = m.index + m[0].length;
  }
  textEl.append(s("tspan", { dy: down ? -3 : null }, str.slice(at)));
  return textEl;
}
function dur(x) {                                      // seconds, said shortly
  if (x == null) return "?";
  if (x < 60) return `${Math.max(1, Math.round(x))}s`;
  if (x < 3600) return `${Math.round(x / 60)}m`;
  if (x < 86400) return `${(x / 3600).toFixed(x < 36000 ? 1 : 0)}h`;
  return `${Math.round(x / 86400)}d`;
}
function ago(t) {
  if (!t) return "never";
  const d = nowS() - t;
  if (d < 60) return `${Math.max(0, Math.round(d))}s ago`;
  if (d < 3600) return `${Math.round(d / 60)}m ago`;
  if (d < 86400) return `${Math.round(d / 3600)}h ago`;
  return `${Math.round(d / 86400)}d ago`;
}
const RUNG_NAMES = ["person", "ai", "narrow-ai", "decision", "program", "rule"];
const RUNG_HINT = ["the most general agent", "a universal AI agent", "an AI agent with one job", "a short model call with fixed answers",
                   "deterministic code", "a threshold or a table", "the work designed out"];
const rungColor = () => "var(--rung)";       // the rung is said in words and a letter; it has no colour of its own
const RUNG_LETTER = ["H", "A", "N", "D", "P", "R", "–"];   // human, ai, narrow-ai, decision, program, rule, retired
function rungDot(r, cx, cy, rad = 5.5) {              // the kind's colour, and its letter, so colour is never the only cue
  return s("g", {}, s("circle", { cx, cy, r: rad, fill: rungColor(r) }),
    s("text", { x: cx, y: cy + rad * 0.55, "text-anchor": "middle", class: "rung-letter", style: `font-size:${rad * 1.45}px` }, RUNG_LETTER[r] ?? "?"));
}
/* a loop's state, as a word: quiet when it holds, coloured only when it needs someone */
const statusEl = (st) => h("span", { class: `status s-${st || "unknown"}` }, st || "unknown");
const exceptional = (st) => st && st !== "holding";

/* a menu: a button and what it holds, opened under it (or above, near the bottom of the screen).
   items: [{label, onclick, checked, hint, disabled}] or nodes, or a function giving them, called on each opening */
function menu(label, items, { cls = "", title = null, right = false, up = false } = {}) {
  const pop = h("div", { class: "menu-pop", role: "menu", hidden: "" });
  const btn = h("button", { class: `menu-btn ${cls}`, type: "button", title, "aria-haspopup": "menu", "aria-expanded": "false" }, label);
  const box = h("span", { class: "menu" + (right ? " right" : "") + (up ? " up" : "") }, btn, pop);
  const close = () => { pop.hidden = true; btn.setAttribute("aria-expanded", "false"); };
  const fill = () => { const list = (typeof items === "function" ? items() : items).filter(Boolean), ticks = list.some((it) => it.checked != null);
    pop.replaceChildren(...list.map((it) => it.nodeType ? it
    : it.sep ? h("div", { class: "menu-sep" })
    : h("button", { class: "menu-item", type: "button", role: it.checked != null ? "menuitemcheckbox" : "menuitem", disabled: it.disabled ? "" : null,
                    "aria-checked": it.checked != null ? String(!!it.checked) : null,
                    onclick: (ev) => { ev.stopPropagation(); close(); it.onclick?.(); } },
        ticks ? h("span", { class: "tick" }, it.checked ? "\u2713" : "") : null, it.label, it.hint ? h("span", { class: "hint" }, it.hint) : null))); };
  btn.addEventListener("click", (ev) => {
    ev.stopPropagation();
    const open = pop.hidden;
    closeMenus();
    if (open) { fill(); pop.hidden = false; btn.setAttribute("aria-expanded", "true"); pop.querySelector("button, input")?.focus({ preventScroll: true }); }
  });
  pop.addEventListener("click", (ev) => ev.stopPropagation());
  box.close = close;
  box.button = btn;
  return box;
}
function closeMenus() { for (const m of document.querySelectorAll(".menu")) m.close?.(); }
document.addEventListener("click", closeMenus);
document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") closeMenus(); });

/* a snapshot (`ergostat snapshot`): the answers were taken once and are in the page */
const SNAP = window.SNAPSHOT || null;
function nowS() { return SNAP ? SNAP.at : Date.now() / 1000; }
function snapKey(path, params) {
  const kept = Object.entries(params).filter(([k, v]) => !["since", "at"].includes(k) && v != null && v !== "" && v !== "undefined")
    .map(([k, v]) => [k, String(v)]).sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
  return path + (kept.length ? "?" + kept.map(([k, v]) => `${k}=${v}`).join("&") : "");
}

async function api(path, params = {}) {
  if (SNAP) {
    const k = snapKey(path, params);
    if (!(k in SNAP.data)) throw new Error(`${path}: not in this snapshot`);
    return JSON.parse(JSON.stringify(SNAP.data[k]));
  }
  const q = new URLSearchParams({ since: S.since, ...(S.at ? { at: String(S.at) } : {}), ...params });
  const r = await fetch(`/api/${path}?${q}`);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

/* the page's one kind of write: the owner's answer to a proposal, or asking for estimates (never in a snapshot) */
async function apiPost(path, params = {}) {
  if (SNAP) throw new Error("a snapshot changes nothing: ergostat accept, where the model is");
  const r = await fetch(`/api/${path}?${new URLSearchParams({ since: S.since, ...params })}`, { method: "POST", headers: { "X-Ergostat-Token": document.querySelector('meta[name="ergostat-token"]')?.content || "" } });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.error || `${path}: ${r.status}`);
  return body;
}

/* the owner's words to the work in flight (SPEC §12h): the text in the body, as JSON */
async function apiSend(path, body) {
  if (SNAP) throw new Error("a snapshot changes nothing: ergostat message, where the model is");
  const r = await fetch(`/api/${path}`, { method: "POST", body: JSON.stringify(body), headers: { "Content-Type": "application/json", "X-Ergostat-Token": document.querySelector('meta[name="ergostat-token"]')?.content || "" } });
  const got = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(got.error || `${path}: ${r.status}`);
  return got;
}

/* ------------------------------------------------------------------ header and routing */

async function refreshHeader() {
  try {
    const st = await api("status");
    S.status = st;
    const sel = $("#project");
    if (!sel.dataset.filled) {
      sel.dataset.filled = "1";
      sel.addEventListener("change", () => { if (sel.value) location.href = sel.value + "/" + location.hash; });
    }
    // the other projects, now and then (not while the list is open): running ones to switch to, with
    // what is off or unknown; stopped ones shown, not offered. Not waited for: the header goes on
    if (document.activeElement !== sel && (!S.projectsAt || Date.now() - S.projectsAt > 60000)) {
      S.projectsAt = Date.now();
      if (!sel.options.length) sel.replaceChildren(h("option", { value: "" }, st.name));
      api("projects").then((ps) => {
        const opts = [h("option", { value: "" }, st.name)];
        for (const p of ps) {
          if (p.name === st.name) continue;
          const bits = [p.off?.length ? `${p.off.length} off` : "", p.unknown?.length ? `${p.unknown.length} unknown` : "",
                        p.web ? "" : "stopped"].filter(Boolean);
          opts.push(h("option", { value: p.web || "", disabled: p.web ? null : "" }, `${p.name}${bits.length ? " (" + bits.join(", ") + ")" : ""}`));
        }
        if (document.activeElement !== sel) sel.replaceChildren(...opts);
      }).catch(() => { /* kept as it was */ });
    }
    const off = Object.values(st.loops).filter((l) => l.status === "off").length;
    const run = $("#running");
    run.className = "runstate" + (off ? " bad" : !SNAP && !st.running ? " warn" : "");
    run.textContent = SNAP ? `Snapshot, ${new Date(SNAP.at * 1000).toLocaleString([], { hour12: false, dateStyle: "short", timeStyle: "short" })}${off ? `, ${off} off` : ""}`
      : off ? `${off} loop${off > 1 ? "s" : ""} off${st.running ? "" : ", not running"}` : st.running ? "Running" : "Not running";
    document.title = `${st.name} · ergostat`;
    S.first = st.first;
  } catch (e) { /* the server may be restarting */ }
}

/* a page's refresh: ``fn`` again ``ms`` after the last one finished (never two at once, however slow
   the server), not while the tab is hidden (at once when it is shown again), and never after its page
   is gone (``el`` no longer in the document): a page left while its first answer was on its way
   stops by itself. ``ERGOSTAT_POLL_SPEED`` shortens every wait (the tests' lever). */
const POLLS = new Set();
function poll(fn, ms, el = null) {
  const p = { timer: null, running: false, stopped: false, stop() { p.stopped = true; clearTimeout(p.timer); POLLS.delete(p); } };
  const gone = () => p.stopped || (el && !el.isConnected);
  p.run = async () => {
    clearTimeout(p.timer); p.timer = null;
    if (gone()) return p.stop();
    if (document.hidden || p.running) return;          // shown again: run at once (below)
    p.running = true;
    try { await fn(); } catch (e) { /* the server may be restarting: the next one asks again */ }
    p.running = false;
    if (gone()) return p.stop();
    p.timer = setTimeout(p.run, ms / (window.ERGOSTAT_POLL_SPEED || 1));
  };
  POLLS.add(p);
  p.timer = setTimeout(p.run, ms / (window.ERGOSTAT_POLL_SPEED || 1));
  return p;
}
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) for (const p of [...POLLS]) if (!p.timer && !p.running) p.run();
});

function parseRoute() {
  const [path, query] = (location.hash.slice(1) || "/diagram").split("?");
  return { path, q: new URLSearchParams(query || "") };
}

async function route() {
  const { path, q } = parseRoute();
  for (const a of document.querySelectorAll("#nav a")) a.classList.toggle("on", a.getAttribute("href") === "#" + path.split("/").slice(0, 2).join("/"));
  S.timer?.stop?.();
  closeDetail();
  const main = $("#main");
  main.replaceChildren();
  const pages = { "/diagram": pageDiagram, "/loops": pageLoops, "/agents": pageAgents, "/record": pageRecord, "/items": pageItems,
                  "/model": pageModel, "/check": pageCheck, "/guide": pageGuide };
  if (path === "/fit" || path === "/residuals") return location.replace(`#/model${q.toString() ? `?${q}` : ""}`);   // the Model page's old names
  if (path.startsWith("/item/")) return pageItem(main, decodeURIComponent(path.slice(6)));
  return (pages[path] || pageDiagram)(main, q);
}

