/* ergostat's page: shared state, small helpers, the API, the header and routing. */
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const NS = "http://www.w3.org/2000/svg";
const elk = new ELK();
const S = { since: "1h", route: "", graphSig: "", layout: null, view: { x: 0, y: 0, k: 1 }, fitted: false,
            timer: null, status: null, sel: null, hl: null };

/* addresses: each page is a path (/items, /item/ID, /diagram?view=blocks), so a link is an ordinary link: it
   opens in a new tab, is copied and reloaded as it is. A link is written as its path; in a snapshot (one file,
   opened with no server) the same path is kept in the hash instead, as #/items. UI_PAGES are the first parts
   of the paths the page answers (the server's UI_PAGES, the same list) */
const HASHED = !!window.SNAPSHOT || location.protocol === "file:";
const UI_PAGES = ["diagram", "loops", "agents", "items", "item", "record", "model", "check", "guide", "fit", "residuals"];
function isPagePath(path) { return path === "/" || UI_PAGES.includes(String(path).split(/[/?#]/)[1]); }
function appHref(v) { return HASHED && typeof v === "string" && v.startsWith("/") && isPagePath(v) ? "#" + v : v; }

/* an element: ``on…`` a listener (kept on the element, so a refresh in place hands it the newest one), ``key``
   what it is among its siblings (a row's item or event id: patch() matches by it), ``sig`` what it was made from
   (a part whose sig is the same is kept as it is, one whose sig differs is made again whole) */
function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "key") el.__key = String(v);
    else if (k === "sig") el.__sig = typeof v === "string" ? v : JSON.stringify(v);
    else if (k.startsWith("on")) listen(el, k.slice(2), v);
    else if (k === "html") el.innerHTML = v;
    else el.setAttribute(k, k === "href" ? appHref(v) : v);
  }
  for (const kid of kids.flat(Infinity)) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return el;
}
function s(tag, attrs = {}, ...kids) {
  const el = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) if (v != null && v !== false) {
    if (k === "key") el.__key = String(v);
    else if (k.startsWith("on")) listen(el, k.slice(2), v); else el.setAttribute(k, v);
  }
  for (const kid of kids.flat(Infinity)) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return el;
}
/* one listener of each type an element has, calling the handler it holds now */
function listen(el, type, fn) {
  if (!el.__onTypes) el.__onTypes = new Set();
  if (!el.__onTypes.has(type)) {
    el.__onTypes.add(type);
    el.addEventListener(type, function (ev) { const f = this.__on?.[type]; return f ? f.call(this, ev) : undefined; });
  }
  (el.__on ||= {})[type] = fn;
}

/* ------------------------------------------------------------------ refreshing in place */

/* a page refreshes by building what it would show and patching it into what is there: only what differs is
   touched, so a refresh that changed nothing changes nothing, and what the reader has open, selected, typed
   or scrolled to stays as it is. Rows are matched by their key, the rest by place and tag. */
function patch(parent, ...kids) {
  const list = kids.flat(Infinity).filter((k) => k != null && k !== false && k !== "")
    .map((k) => (k.nodeType ? k : document.createTextNode(String(k))));
  const anchor = anchorByHand() ? scrollAnchor(parent) : null;
  patchKids(parent, list);
  if (anchor) keepAnchor(anchor);
  return parent;
}
/* a node that lives across refreshes (a chart, a file's view, a box being written in): put in a tree being
   built, it is left where it is on the page, and only moved if its place changed */
function live(node) {
  if (!node?.nodeType) return node;
  node.__persist = true;
  if (!node.isConnected) return node;
  const stub = document.createElement("x-live");
  stub.__ref = node;
  return stub;
}
/* the text of an element, set only when it differs */
function setText(el, t) {
  t = t == null ? "" : String(t);
  if (el.textContent !== t) el.textContent = t;
  return el;
}
const alike = (o, n) => o.nodeType === n.nodeType && o.nodeName === n.nodeName && !o.__persist && !n.__persist && !n.__ref &&
  o.__key == null && n.__key == null && (o.nodeType !== 1 || o.namespaceURI === n.namespaceURI);
function patchKids(parent, kids) {
  const keyed = new Map();
  for (let c = parent.firstChild; c; c = c.nextSibling) if (c.__key != null && !keyed.has(c.__key)) keyed.set(c.__key, c);
  let cur = parent.firstChild;
  for (const n of kids) {
    let m = null;
    if (n.__ref) m = n.__ref;
    else if (n.__key != null) {
      const o = keyed.get(n.__key);
      if (o && o.nodeName === n.nodeName && !o.__persist && !n.__persist) { m = o; keyed.delete(n.__key); }
    } else if (cur && alike(cur, n)) m = cur;
    let placed;
    if (m) {
      if (m !== cur) parent.insertBefore(m, cur);
      placed = n.__ref ? m : patchNode(m, n);
    } else {
      parent.insertBefore(n, cur);
      unstub(n);
      placed = n;
    }
    cur = placed.nextSibling;
  }
  while (cur) { const next = cur.nextSibling; parent.removeChild(cur); cur = next; }
}
function unstub(n) {                                    // a node new to the page: the live nodes it names, in their places
  if (n.nodeType === 1 && n.firstChild) for (const st of n.querySelectorAll("x-live")) st.replaceWith(st.__ref);
}
function patchNode(o, n) {
  if (o.nodeType !== 1) { if (o.nodeValue !== n.nodeValue) o.nodeValue = n.nodeValue; return o; }
  if (o.__sig !== undefined || n.__sig !== undefined) {
    if (o.__sig === n.__sig) { n.replaceChildren(); return o; }
    if (o.tagName === "DETAILS" && o.open) n.open = true;           // made again, as the reader left it
    o.parentNode.replaceChild(n, o);
    unstub(n);
    return n;
  }
  const details = o.tagName === "DETAILS";                           // open or closed: the reader's
  // by name, never through .attributes (each Attr it hands out is a node the element then keeps)
  for (const name of n.getAttributeNames()) {
    if (details && name === "open") continue;
    const v = n.getAttribute(name);
    if (o.getAttribute(name) !== v) o.setAttribute(name, v);
  }
  for (const name of o.getAttributeNames()) if (!n.hasAttribute(name) && !(details && name === "open")) o.removeAttribute(name);
  if (n.__on || o.__on) {
    for (const t of n.__onTypes || []) if (!o.__onTypes?.has(t)) listen(o, t, n.__on[t]);
    o.__on = n.__on || null;
  }
  patchKids(o, [...n.childNodes]);
  // what is left of the tree built is let go: the handlers just handed over share its scope, and would keep it
  n.replaceChildren();
  return o;
}
/* the reader's place: kept by the browser (overflow-anchor) where it can; elsewhere measured and kept here */
const anchorByHand = () => window.ERGOSTAT_ANCHOR_BY_HAND || !(window.CSS?.supports?.("overflow-anchor", "auto"));
function scrollerOf(el) {
  for (let x = el; x && x !== document.body && x !== document.documentElement; x = x.parentElement) {
    const oy = getComputedStyle(x).overflowY;
    if ((oy === "auto" || oy === "scroll") && x.scrollHeight > x.clientHeight) return x;
  }
  return document.scrollingElement;
}
function scrollAnchor(parent) {
  const sc = scrollerOf(parent);
  if (!sc || !sc.scrollTop || !parent.isConnected) return null;
  const box = sc === document.scrollingElement ? { left: 0, top: 0, width: innerWidth } : sc.getBoundingClientRect();
  for (const dy of [box.top + 8, box.top + 40, box.top + 120]) {
    const el = document.elementFromPoint(box.left + box.width / 2, dy);
    if (el && sc.contains(el) && el !== sc) return { sc, el, y: el.getBoundingClientRect().top };
  }
  return null;
}
function keepAnchor(a) {
  if (!a.el.isConnected) return;
  const dy = a.el.getBoundingClientRect().top - a.y;
  if (Math.abs(dy) >= 1) a.sc.scrollTop += dy;
}

/* a share as a percentage: one that is not zero is never written '0%' ('<1%') */
const shareText = (x) => (x > 0 && x < 0.005 ? "<1%" : `${Math.round((x || 0) * 100)}%`);
/* a goal that went off this many times in the window or more is flapping: past its bound and back, again and again */
const FLAP_AT = 20;

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
/* a rate, as it reads naturally (display only: every rate is kept per hour, rates.py): per minute above about
   60 an hour, per day below about 1 an hour, else per hour; a flow's rate-unit: (S.status.rate_units) wins */
const RATE_PER_HOUR = { minute: 1 / 60, hour: 1, day: 24, week: 168 };
const RATE_SUFFIX = { minute: "/min", hour: "/h", day: "/day", week: "/week" };
const RATE_WORD = { minute: "per minute", hour: "per hour", day: "per day", week: "per week" };
function rateOver(flow) { return (flow && S.status?.rate_units?.[flow]) || null; }
function rateUnit(r, over = null) {
  if (RATE_PER_HOUR[over]) return over;
  if (r == null || !Number.isFinite(r) || r === 0) return "hour";
  return Math.abs(r) > 60 ? "minute" : Math.abs(r) < 1 ? "day" : "hour";
}
function rateIn(r, unit) { return r == null ? r : r * RATE_PER_HOUR[unit]; }
/* "12 alerts/min": a rate per hour in the unit that reads best for it (or the flow's own) */
function rateText(r, unit = "", flow = null) {
  const u = rateUnit(r, rateOver(flow));
  const tail = (unit || "") + RATE_SUFFIX[u];
  return r == null ? "?" + tail : `${fmt(rateIn(r, u))}${unit ? " " : ""}${tail}`;
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
/* what runs cost (SPEC §9.1): dollars, tokens, CPU seconds, memory; "–" when not known */
function usd(x) { return x == null ? "\u2013" : x === 0 ? "$0" : x < 0.01 ? `$${x.toFixed(4)}` : x < 100 ? `$${x.toFixed(2)}` : `$${Math.round(x).toLocaleString("en-US")}`; }
function tokensText(n) { return n == null ? "\u2013" : n === 0 ? "0" : n >= 1e6 ? `${+(n / 1e6).toPrecision(3)}M` : n >= 1e4 ? `${+(n / 1e3).toPrecision(3)}k` : String(n); }
function cpuText(x) { return x == null ? "\u2013" : x < 60 ? `${+x.toPrecision(2)}s` : dur(x); }
function bytesText(b) { return b == null ? "\u2013" : b >= 1e9 ? `${+(b / 1e9).toPrecision(3)} GB` : `${+(b / 1e6).toPrecision(3)} MB`; }
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

/* an answer as its text, and the address it came from */
async function apiText(path, params = {}) {
  if (SNAP) {
    const k = snapKey(path, params);
    if (!(k in SNAP.data)) throw new Error(`${path}: not in this snapshot`);
    return [k, JSON.stringify(SNAP.data[k])];
  }
  const q = new URLSearchParams({ since: S.since, ...(S.at ? { at: String(S.at) } : {}) });
  for (const [k, v] of Object.entries(params)) { q.delete(k); for (const x of [].concat(v)) q.append(k, x); }   // a list: the key repeated
  const url = `/api/${path}?${q}`;
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return [url, await r.text()];
}
async function api(path, params = {}) { return JSON.parse((await apiText(path, params))[1]); }
/* a page's answers, remembered: ``changed`` says whether any asked since ``begin()`` differed from the last
   time it was asked (an unchanged answer is a 304, given as the same body): a refresh that changed nothing
   then draws nothing */
function answers() {
  const last = new Map();
  const a = {
    changed: true,
    begin() { a.changed = false; },
    async api(path, params = {}) {
      const [key, text] = await apiText(path, params);
      if (last.get(key) !== text) { last.set(key, text); a.changed = true; }
      return JSON.parse(text);
    },
  };
  return a;
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
      sel.replaceChildren(h("option", { value: "" }, st.name));
      sel.addEventListener("change", () => { if (sel.value) location.href = sel.value + location.pathname + location.search; });
      // the other projects: once, and again when the reader comes to the list (each is a model loaded and a
      // snapshot of its record on the server: not asked for while the page is only left open)
      const fresh = () => { if (Date.now() - (S.projectsAt || 0) > 30000) refreshProjects(sel); };
      sel.addEventListener("pointerenter", fresh);
      sel.addEventListener("focus", fresh);
      refreshProjects(sel);
    }
    const off = Object.values(st.loops).filter((l) => l.status === "off").length;
    const run = $("#running");
    const edited = !SNAP && st.edited;                 // the edited model has errors: the last good version still runs
    const cls = "runstate" + (off || edited ? " bad" : !SNAP && !st.running ? " warn" : "");
    if (run.className !== cls) run.className = cls;
    const open = document.querySelector('meta[name="ergostat-public"]') ? " · public, read only, no login" : "";   // web: open: read
    const tip = edited ? st.edited.errors.join("\n") : open ? "This address is public and read only: anyone who reaches it reads this page, and nothing can be changed here" : "";
    if (run.title !== tip) run.title = tip;
    setText(run, (SNAP ? `Snapshot, ${new Date(SNAP.at * 1000).toLocaleString([], { hour12: false, dateStyle: "short", timeStyle: "short" })}${off ? `, ${off} off` : ""}`
      : edited ? st.edited.banner.charAt(0).toUpperCase() + st.edited.banner.slice(1)
      : off ? `${off} loop${off > 1 ? "s" : ""} off${st.running ? "" : ", not running"}` : st.running ? "Running" : "Not running") + open);
    if (document.title !== `${st.name} · ergostat`) document.title = `${st.name} · ergostat`;
    S.first = st.first;
  } catch (e) { /* the server may be restarting */ }
}

/* the other projects on this machine, in the header's list: running ones to switch to, with what is off
   or unknown; stopped ones shown, not offered. Not waited for, and not changed while the list is open */
function refreshProjects(sel) {
  S.projectsAt = Date.now();
  api("projects").then((ps) => {
    const name = S.status?.name || "";
    const opts = [h("option", { value: "" }, name)];
    for (const p of ps) {
      if (p.name === name) continue;
      const bits = [p.off?.length ? `${p.off.length} off` : "", p.unknown?.length ? `${p.unknown.length} unknown` : "",
                    p.web ? "" : "stopped"].filter(Boolean);
      opts.push(h("option", { value: p.web || "", disabled: p.web ? null : "" }, `${p.name}${bits.length ? " (" + bits.join(", ") + ")" : ""}`));
    }
    if (document.activeElement !== sel) sel.replaceChildren(...opts);
  }).catch(() => { /* kept as it was */ });
}

/* a page's refresh: ``fn`` again ``ms`` after the last one finished (never two at once, however slow
   the server), not while the tab is hidden (at once when it is shown again), and never after its page
   is gone (``el`` no longer in the document): a page left while its first answer was on its way
   stops by itself. ``ERGOSTAT_POLL_SPEED`` shortens every wait (the tests' lever). */
const POLLS = new Set();
function poll(fn, ms, el = null, first = null) {
  // ``fn`` may say how long to wait before the next ({ wait: ms }: later when its answer was slow); else ``ms``
  const p = { timer: null, running: false, stopped: false, stop() { p.stopped = true; clearTimeout(p.timer); POLLS.delete(p); } };
  const gone = () => p.stopped || (el && !el.isConnected);
  const wait = (x) => (x && typeof x.wait === "number" && x.wait >= 0 ? x.wait : ms) / (window.ERGOSTAT_POLL_SPEED || 1);
  p.run = async () => {
    clearTimeout(p.timer); p.timer = null;
    if (gone()) return p.stop();
    if (document.hidden || p.running) return;          // shown again: run at once (below)
    p.running = true;
    let next;
    try { next = await fn(); } catch (e) { /* the server may be restarting: the next one asks again */ }
    p.running = false;
    if (gone()) return p.stop();
    p.timer = setTimeout(p.run, wait(next));
  };
  POLLS.add(p);
  p.timer = setTimeout(p.run, wait(first));
  return p;
}
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) for (const p of [...POLLS]) if (!p.timer && !p.running) p.run();
});

/* the route: the page's path and query ("/item/a%2Fb", "/diagram?view=blocks"), from the address; in a
   snapshot, from the hash. The second pane's own mark (?pane=1) is not part of it */
function currentRoute() {
  if (HASHED) return location.hash.startsWith("#/") ? location.hash.slice(1) : "/diagram";
  const q = new URLSearchParams(location.search);
  q.delete("pane");
  const path = location.pathname === "/" ? "/diagram" : location.pathname;
  return path + (q.toString() ? "?" + q : "");
}
function parseRoute() {
  const r = currentRoute(), i = r.indexOf("?");
  return { path: i < 0 ? r : r.slice(0, i), q: new URLSearchParams(i < 0 ? "" : r.slice(i + 1)) };
}
/* the address a route is shown at (the second pane keeps its mark) */
function routeUrl(r) {
  if (HASHED) return "#" + r;
  if (!PANE) return r;
  return r + (r.includes("?") ? "&" : "?") + "pane=1";
}
/* go to a route in this page: a new entry in the history (or, ``replace``, the same entry changed), then the
   page drawn for it. The same route again does nothing, as a link to where one is. A page that is not a
   diagram asked for in the second pane opens in the page itself */
function navigate(r, replace = false) {
  if (PANE && !diagramHash(r)) return peerSay({ type: "go", route: r });
  if (r === currentRoute()) return;
  history[replace ? "replaceState" : "pushState"](null, "", routeUrl(r));
  route();
}
/* the address changed without drawing (a page's filters, the guide's frame): the history entry only */
function replaceRoute(r) { history.replaceState(null, "", routeUrl(r)); }
/* a link's route, when it is one of the page's own: "/items", "#/items" (an old address), or the same as a full URL */
function routeOfHref(href) {
  if (!href) return null;
  if (href.startsWith("#/")) return href.slice(1);
  if (HASHED) return null;
  let u;
  try { u = new URL(href, location.href); } catch (e) { return null; }
  if (u.origin !== location.origin || !isPagePath(u.pathname)) return null;
  if (u.hash.startsWith("#/")) return u.hash.slice(1);
  return (u.pathname === "/" ? "/diagram" : u.pathname) + u.search;
}
/* a plain left click on a link to one of the page's own: drawn here, with no reload. A click with ctrl, cmd,
   shift or alt, the middle button, or on a link to another tab is left to the browser (a new tab, a window) */
document.addEventListener("click", (ev) => {
  if (ev.defaultPrevented || ev.button !== 0 || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) return;
  const a = ev.target.closest?.("a[href]");
  if (!a || (a.target && a.target !== "_self") || a.hasAttribute("download")) return;
  const r = routeOfHref(a.getAttribute("href"));
  if (r == null) return;
  ev.preventDefault();
  navigate(r);
});
/* a table row that opens a page: a click goes there; with ctrl, cmd or shift, or the middle button, a new tab
   opens on it (the row's own link, its first cell, is the ordinary link) */
function rowLink(r) {
  return {
    onclick: (ev) => {
      if (ev.target.closest?.("a")) return;
      if (ev.metaKey || ev.ctrlKey || ev.shiftKey) window.open(appHref(r), "_blank");
      else navigate(r);
    },
    onauxclick: (ev) => { if (ev.button === 1 && !ev.target.closest?.("a")) window.open(appHref(r), "_blank"); },
  };
}
/* an old address (#/items, from a bookmark, a message, a brief) is shown at its path; the page's own header
   links in a snapshot are kept in the hash */
function oldAddress() {
  if (!HASHED && location.hash.startsWith("#/")) { history.replaceState(null, "", routeUrl(location.hash.slice(1))); return true; }
  return false;
}
if (HASHED) for (const a of document.querySelectorAll("a[href^='/']")) a.setAttribute("href", appHref(a.getAttribute("href")));

async function route() {
  oldAddress();
  const { path, q } = parseRoute();
  const top = path.split("/").slice(0, 2).join("/");
  for (const a of document.querySelectorAll("#nav a")) a.classList.toggle("on", routeOfHref(a.getAttribute("href")) === top);
  S.timer?.stop?.();
  closeDetail();
  if (typeof splitLayout === "function" && !PANE) splitLayout();
  const main = $("#main");
  main.replaceChildren();
  const pages = { "/diagram": pageDiagram, "/loops": pageLoops, "/agents": pageAgents, "/record": pageRecord, "/items": pageItems,
                  "/model": pageModel, "/check": pageCheck, "/guide": pageGuide };
  if (path === "/fit" || path === "/residuals") { replaceRoute(`/model${q.toString() ? `?${q}` : ""}`); return route(); }   // the Model page's old names
  if (path.startsWith("/item/")) return pageItem(main, decodeURIComponent(path.slice(6)), q);
  return (pages[path] || pageDiagram)(main, q);
}

