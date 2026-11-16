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
const fmt = (x) => x == null ? "?" : (typeof x === "number" ? (Number.isInteger(x) ? String(x) : (Math.abs(x) < 100 ? x.toPrecision(3).replace(/\.?0+$/, "") : x.toFixed(0))) : String(x));
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
const rungColor = (r) => `var(--r${r})`;
const RUNG_LETTER = ["H", "A", "N", "D", "P", "R", "–"];   // human, ai, narrow-ai, decision, program, rule, retired
function rungDot(r, cx, cy, rad = 5.5) {              // the kind's colour, and its letter, so colour is never the only cue
  return s("g", {}, s("circle", { cx, cy, r: rad, fill: rungColor(r) }),
    s("text", { x: cx, y: cy + rad * 0.55, "text-anchor": "middle", class: "rung-letter", style: `font-size:${rad * 1.45}px` }, RUNG_LETTER[r] ?? "?"));
}
const statusEl = (st) => h("span", { class: `status s-${st || "unknown"}` }, st || "?");

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
    // the other projects, refreshed with the header (not while the list is open): running ones to
    // switch to, with what is off or unknown; stopped ones shown, not offered
    if (document.activeElement !== sel && (!S.projectsAt || Date.now() - S.projectsAt > 9000)) {
      S.projectsAt = Date.now();
      try {
        const opts = [h("option", { value: "" }, st.name)];
        for (const p of await api("projects")) {
          if (p.name === st.name) continue;
          const bits = [p.off?.length ? `${p.off.length} off` : "", p.unknown?.length ? `${p.unknown.length} unknown` : "",
                        p.web ? "" : "stopped"].filter(Boolean);
          opts.push(h("option", { value: p.web || "", disabled: p.web ? null : "" }, `${p.name}${bits.length ? " · " + bits.join(", ") : ""}`));
        }
        sel.replaceChildren(...opts);
      } catch (e) { if (!sel.options.length) sel.replaceChildren(h("option", { value: "" }, st.name)); }
    }
    const off = Object.values(st.loops).filter((l) => l.status === "off").length;
    const run = $("#running");
    run.className = "pill " + (SNAP ? (off ? "bad" : "unknown") : st.running ? (off ? "bad" : "ok") : "unknown");
    run.textContent = SNAP ? `snapshot ${new Date(SNAP.at * 1000).toLocaleString([], { hour12: false, dateStyle: "short", timeStyle: "short" })}${off ? ` · ${off} off` : ""}`
      : st.running ? (off ? `${off} loop${off > 1 ? "s" : ""} off` : "running") : "not running";
    document.title = `${st.name} · ergostat`;
    S.first = st.first;
  } catch (e) { /* the server may be restarting */ }
}

function parseRoute() {
  const [path, query] = (location.hash.slice(1) || "/diagram").split("?");
  return { path, q: new URLSearchParams(query || "") };
}

async function route() {
  const { path, q } = parseRoute();
  for (const a of document.querySelectorAll("#nav a")) a.classList.toggle("on", a.getAttribute("href") === "#" + path.split("/").slice(0, 2).join("/"));
  clearInterval(S.timer);
  closeDetail();
  const main = $("#main");
  main.replaceChildren();
  const pages = { "/diagram": pageDiagram, "/loops": pageLoops, "/agents": pageAgents, "/record": pageRecord, "/items": pageItems,
                  "/residuals": pageResiduals, "/check": pageCheck, "/guide": pageGuide };
  if (path.startsWith("/item/")) return pageItem(main, decodeURIComponent(path.slice(6)));
  return (pages[path] || pageDiagram)(main, q);
}

