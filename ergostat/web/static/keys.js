/* the diagram by keyboard: everything a click acts on is a button, named for a screen reader; Enter or Space
   does what its click does. A panel opened so takes the focus to its heading, and Escape gives it back to the
   part; a redraw keeps the focus on the part it was on (by its key, as it is drawn anew). The diagram is one
   tab stop (roving: one part tabindex 0, the rest -1; the last one on remembered per view), and the arrows
   follow its structure (walk); Shift and an arrow step through every part in drawing order instead */
"use strict";
const KEYS = ".node, .edge, [data-act]:not(.hull-grip), .sys-btn, .sys-hull-label, .bd-frame";
const ACT_WORDS = { close: "Close", into: "Into", open: "Open", unpin: "Unpin", "": "System" };
const SIGN_WORDS = { "+": "sign positive (+)", "-": "sign negative (−)" };
const nodeOf = (id) => id && S.graph?.nodes.find((x) => x.id === id);
const saidIn = (el) => [...el.querySelectorAll("text")].filter((t) => t.closest(KEYS) === el)
  .map((t) => t.textContent.replace(/[▾⤓]/g, "").trim()).filter(Boolean);
/* what a screen reader says for it: what it is, and what is written on it ('stock backlog, 13 tickets') */
function ariaOf(el, said) {
  const n = nodeOf(el.dataset.id), host = el.parentElement?.closest(".node, [data-hull]");
  // Dynamics and Blocks: the part's name in its discipline's words, with its state and loops (dynamics.js, blocks.js)
  const spoken = { dynamics: typeof sdSpoken === "function" && sdSpoken, blocks: typeof bdSpoken === "function" && bdSpoken }[S.graph?.kind];
  const part = !spoken ? null : el.matches(".node") ? n : el.matches(".bd-frame") ? (S.graph.frames || []).find((f) => f.id === el.dataset.hull)
    : el.matches(".edge") ? S.edgeById?.[el.dataset.id] || S.graph.edges.find((e) => e.id === el.dataset.id) : null;
  const mark = el.matches(".node") && untrustedSays(n);     // (an untrusted library's part says so after its name)
  if (part && mark) return `${spoken(part, S.graph)}, ${mark}`;
  if (part) return spoken(part, S.graph);
  if (el.matches(".node")) return [`${n?.kind || "part"} ${said.join(", ") || n?.label || ""}`, n?.status, untrustedSays(n)].filter(Boolean).join(", ");
  if (el.matches(".edge")) { const e = S.edgeById?.[el.dataset.id], end = (x) => String(x || "").replace(/^\w+:/, "");
    const sign = SIGN_WORDS[e?.polarity] || (e?.kind === "connector" ? "sign not known" : "");
    return e ? [`${e.kind} line from ${end(e.source)} to ${end(e.target)}`, sign].filter(Boolean).join(", ") : "line"; }
  if (el.matches(".loop-marker, .measure-row, .bd-frame")) return `${el.dataset.act || "frame"} ${said.join(", ")}`;
  const act = el.matches(".sys-btn") ? said[0] : ACT_WORDS[el.dataset.act || ""] || el.dataset.act;
  return `${act} ${nodeOf(host?.dataset.id)?.label || host?.dataset.hull || el.dataset.id || said.join(" ")}`;
}
const roveKey = () => S.pinKey || location.search;        // (per view: the view, the system and what it is around)
/* after each drawing (markInteraction): each clickable part made a button, one of them the diagram's tab stop,
   and the focus kept where it was (or taken where I or Escape sent it) */
function keyable(svg) {
  for (const el of svg.querySelectorAll(KEYS)) {
    if (el.matches(".k-cloud") && !nodeOf(el.dataset.id)?.beyond) continue;   // (a cloud is no control)
    if (el.matches(".loop-marker.minor")) continue;    // (drawn only while chosen: its row in the side list is its button)
    const said = saidIn(el), host = el.parentElement?.closest(".node, [data-hull]");
    el.setAttribute("tabindex", "-1"); el.setAttribute("role", "button"); el.setAttribute("aria-label", ariaOf(el, said));
    el.dataset.key = [el.classList[0], el.dataset.id, el.dataset.loop, el.dataset.hull, el.dataset.act, host?.dataset.id,
                      el.matches(".node, .edge") ? "" : said[0]].join("|");
  }
  const by = (k) => k && svg.querySelector(`[data-key="${CSS.escape(k)}"]`), now = document.activeElement;
  const go = S.keyGo && S.keyGo.from !== svg && svg.isConnected && sentTo(svg, S.keyGo);
  const back = S.keyAt && now === document.body && by(S.keyAt);
  const stop = go || (svg.contains(now) && now.matches("[data-key]") ? now : back || by(S.roveAt?.[roveKey()]) || homeOf(svg));
  stop?.setAttribute("tabindex", "0");
  if (go) { S.keyGo = null; go.focus({ preventScroll: true }); } else if (back) back.focus({ preventScroll: true });
}
/* the first part of the first chain: of the parts a chain line leaves and none comes into, the top one (then the left) */
function homeOf(svg) {
  const parts = [...svg.querySelectorAll(".node[data-key]")], ids = new Set(parts.map((el) => el.dataset.id));
  const chain = (S.graph?.edges || []).filter((e) => chainLine(e) && ids.has(e.source) && ids.has(e.target));
  const into = new Set(chain.map((e) => e.target)), from = new Set(chain.map((e) => e.source));
  const at = new Map(parts.map((el) => { const r = el.getBoundingClientRect(); return [el, [r.y, r.x]]; }));
  const heads = parts.filter((el) => from.has(el.dataset.id) && !into.has(el.dataset.id));
  return (heads.length ? heads : parts).sort((a, b) => { const [ay, ax] = at.get(a), [by, bx] = at.get(b);
    return Math.abs(ay - by) > 20 ? ay - by : ax - bx; })[0] || svg.querySelector("[data-key]");
}
const onReturn = (id) => ["sensor", "collector", "bus"].includes(nodeOf(id)?.role);   // (as blocks.js lays them out)
const returnLine = (e) => e.feedback || onReturn(e.source) || onReturn(e.target);
/* the line a chain goes along: a pipe in Dynamics, the forward path in Blocks, any line elsewhere */
function chainLine(e) {
  const k = S.graph?.kind;
  return k === "blocks" ? !returnLine(e) : k === "dynamics" || k === "control" ? e.kind === "pipe" : true;
}
/* where an arrow from the focused element goes, along the structure (null: nowhere that way) */
function walk(el, key) {
  const svg = el.closest("svg"), edges = S.graph?.edges || [], q = (sel) => svg.querySelector(sel);
  const part = (id) => id && q(`.node[data-id="${CSS.escape(id)}"][data-key]`);
  const end = (e, w) => part(e[w]) || part(original(e[w], e[w + "Port"]));
  const line = (id) => q(`.edge[data-id="${CSS.escape(id)}"][data-key]`);
  const first = (list, w) => list.map((e) => end(e, w)).find(Boolean) || null;
  if (el.matches(".measure-row")) {                      // a goal row: Down and Up through the box's rows, Up out of it
    const box = el.closest(".node"), rows = [...box.querySelectorAll(".measure-row[data-key]")], i = rows.indexOf(el);
    return key === "ArrowDown" ? rows[i + 1] || null : key === "ArrowUp" ? rows[i - 1] || box : null;
  }
  if (el.matches(".edge")) {                             // a line: Right and Left to its ends, Down and Up to the next line
    const e = S.edgeById?.[el.dataset.id], list = S.walkLines || [], i = list.indexOf(el.dataset.id);
    if (!e) return null;
    if (key === "ArrowRight" || key === "ArrowLeft") return end(e, key === "ArrowRight" ? "target" : "source");
    return i < 0 ? null : line(list[(i + (key === "ArrowDown" ? 1 : list.length - 1)) % list.length]);
  }
  const id = el.closest(".node")?.dataset.id;
  if (!id) return null;
  const rows = el.querySelectorAll(".measure-row[data-key]");
  if (key === "ArrowDown" && rows.length) return rows[0];   // a closed box with goal rows: Down enters them
  const mine = (e, w) => e[w] === id || original(e[w], e[w + "Port"]) === id;
  const outs = edges.filter((e) => mine(e, "source")), ins = edges.filter((e) => mine(e, "target"));
  const k = S.graph?.kind;
  if (k === "blocks") {
    if (nodeOf(id)?.role === "comparator") S.walkLoop = id;   // the loop walked: the one round this junction
    const steps = (a, b) => {                            // lines from a to b, the shortest way (Infinity: none)
      const far = { [a]: 0 }, todo = [a];
      for (let x = todo.shift(); x != null && x !== b; x = todo.shift())
        for (const e of edges) if (e.source === x && !(e.target in far)) { far[e.target] = far[x] + 1; todo.push(e.target); }
      return far[b] ?? Infinity;
    };
    const near = (list, w) => {                          // of several ways on, the one on the shortest way round the loop
      const got = list.map((e) => end(e, w)).filter(Boolean), round = (x) => (!S.walkLoop ? 0
        : w === "target" ? steps(x.dataset.id, S.walkLoop) : steps(S.walkLoop, x.dataset.id));
      return got.map((x) => [round(x), x]).sort((p, q) => p[0] - q[0])[0]?.[1] || null;
    };
    const lines = { ArrowRight: [outs.filter(chainLine), "target"], ArrowLeft: [ins.filter(chainLine), "source"],
                    ArrowDown: [outs.filter(returnLine), "target"], ArrowUp: [ins.filter(returnLine), "source"] }[key];
    const to = near(...lines);
    // a process's own summing point (where its flows add, disturbances with them): passed through, to P or what drives it
    return to && nodeOf(to.dataset.id)?.role === "process-sum" && key.match(/Right|Left/) ? walk(to, key) || to : to;
  }
  if (key === "ArrowRight") return first(outs.filter(chainLine), "target") || first(outs, "target");
  if (key === "ArrowLeft") return first(ins.filter(chainLine), "source") || first(ins, "source");
  if (k !== "dynamics" && k !== "control") return null;
  // Dynamics: Down and Up step through the connectors into, then out of, this part (each says its other end and sign)
  S.walkLines = [...ins, ...outs].filter((e) => e.kind === "connector" && line(e.id)).map((e) => e.id);
  return line(S.walkLines[key === "ArrowDown" ? 0 : S.walkLines.length - 1]) || null;
}
/* the system a focused element stands for: a closed box, or an open one's outline or frame */
function systemOf(el) {
  const n = nodeOf(el.closest(".node")?.dataset.id);
  if (n) return n.kind === "system" || n.role === "subsystem" ? n.label : null;   // (a part within one is not it)
  const hull = el.closest("[data-hull]")?.dataset.hull, f = (S.graph?.frames || []).find((x) => x.id === hull);
  return f ? (f.frame === "system" ? f.label : null) : hull || null;
}
/* where I or Escape sent the focus, in the view drawn after it: its first part, or the system come out of */
function sentTo(svg, to) {
  if (to.home) return homeOf(svg);
  const box = [...svg.querySelectorAll(".node[data-key]")].find((el) => systemOf(el) === to.sys && el.matches(".node"));
  const f = (S.graph?.frames || []).find((x) => x.frame === "system" && x.label === to.sys);
  const hull = svg.querySelector(`[data-hull="${CSS.escape(f ? f.id : to.sys)}"]`);
  return box || hull?.querySelector('[data-act="into"][data-key]') || (hull?.matches("[data-key]") ? hull : hull?.querySelector("[data-key]")) || null;
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
const ARROWS = new Set(["ArrowRight", "ArrowLeft", "ArrowUp", "ArrowDown"]);
document.addEventListener("keydown", (ev) => {
  const el = ev.target, on = el.matches?.("svg [data-key]"), plain = !ev.ctrlKey && !ev.metaKey && !ev.altKey;
  if ((ev.key === "Enter" || ev.key === " ") && on) { ev.preventDefault(); keyPress(el); }
  else if (ev.key === "Escape" && S.keyBack && !$("#detail")?.hidden) {   // (main.js closes the panel)
    $(`svg.canvas [data-key="${CSS.escape(S.keyBack)}"]`)?.focus(); S.keyBack = null; }
  else if (on && plain && (ARROWS.has(ev.key) || ev.key === "Home")) {
    ev.preventDefault();
    const all = [...el.closest("svg").querySelectorAll("[data-key]")], i = all.indexOf(el);
    const to = ev.shiftKey ? all[(i + (ev.key === "ArrowRight" || ev.key === "ArrowDown" ? 1 : all.length - 1)) % all.length]
      : ev.key === "Home" ? homeOf(el.closest("svg")) : walk(el, ev.key);
    to?.focus();
  } else if (on && plain && !ev.shiftKey && ev.key.toLowerCase() === "i" && systemOf(el) && S.drill) {   // Into it
    ev.preventDefault(); S.keyGo = { home: true, from: el.closest("svg") }; S.drill(systemOf(el));
  } else if (on && plain && (ev.key === "Escape" || ev.key === "Backspace") && S.here && S.drill && $("#detail")?.hidden !== false) {
    ev.preventDefault(); S.keyGo = { sys: S.here, from: el.closest("svg") }; S.drill(S.graph?.tree?.[S.here]?.within || "");
  }
});
document.addEventListener("focusin", (ev) => {
  const el = ev.target, on = el.matches?.("svg [data-key]");
  S.keyAt = on ? el.dataset.key : null;
  if (!on) return;                                       // the tab stop moves with the focus, and is remembered
  for (const o of el.closest("svg").querySelectorAll('[data-key][tabindex="0"]')) if (o !== el) o.setAttribute("tabindex", "-1");
  el.setAttribute("tabindex", "0");
  (S.roveAt ||= {})[roveKey()] = el.dataset.key;
});
document.addEventListener("pointerdown", () => { S.keyAt = S.keyHead = S.keyBack = null; }, true);
