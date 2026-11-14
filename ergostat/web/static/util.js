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
function ago(t) {
  if (!t) return "never";
  const d = Date.now() / 1000 - t;
  if (d < 60) return `${Math.max(0, Math.round(d))}s ago`;
  if (d < 3600) return `${Math.round(d / 60)}m ago`;
  if (d < 86400) return `${Math.round(d / 3600)}h ago`;
  return `${Math.round(d / 86400)}d ago`;
}
const RUNG_NAMES = ["person", "ai", "narrow-ai", "decision", "program", "rule"];
const RUNG_HINT = ["the most general agent", "a universal AI agent", "an AI agent with one job", "a short model call with fixed answers",
                   "deterministic code", "a threshold or a table", "the work designed out"];
const rungColor = (r) => `var(--r${r})`;
const statusEl = (st) => h("span", { class: `status s-${st || "unknown"}` }, st || "?");

async function api(path, params = {}) {
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
      sel.replaceChildren(h("option", { value: "" }, st.name));
      try {
        for (const p of await api("projects")) {
          if (p.name === st.name || !p.web) continue;
          sel.append(h("option", { value: p.web }, `${p.name}${p.off?.length ? " · " + p.off.length + " off" : ""}`));
        }
      } catch (e) { /* the list is a convenience */ }
      sel.addEventListener("change", () => { if (sel.value) location.href = sel.value + "/" + location.hash; });
    }
    const off = Object.values(st.loops).filter((l) => l.status === "off").length;
    const run = $("#running");
    run.className = "pill " + (st.running ? (off ? "bad" : "ok") : "unknown");
    run.textContent = st.running ? (off ? `${off} loop${off > 1 ? "s" : ""} off` : "running") : "not running";
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
  const pages = { "/diagram": pageDiagram, "/loops": pageLoops, "/agents": pageAgents, "/parts": pageParts, "/record": pageRecord,
                  "/residuals": pageResiduals, "/check": pageCheck, "/guide": pageGuide };
  if (path.startsWith("/item/")) return pageItem(main, decodeURIComponent(path.slice(6)));
  return (pages[path] || pageDiagram)(main, q);
}

