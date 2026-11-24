/* the router's half in the new code: which page an address is, and that page's new module mounted into #main when it
   exports ``page``; otherwise route() (util.js) calls the page's old function, so each page moves on its own and every
   page always works (docs/frontend.md). route() keeps the rest: the redirects of old addresses, the window, the panel. */
import { html, render } from "/static/app/core.js";

/* the pages with a module of their own, app/pages/<name>/index.js (panel-editor's is the Dashboard's to use: no
   address of its own) */
export const PAGE_NAMES = ["dashboard", "panel-editor", "diagram", "items", "item", "goals", "agents", "record", "model"];
const PATHS = { "/diagram": "diagram", "/dashboard": "dashboard", "/goals": "goals", "/agents": "agents",
                "/record": "record", "/model": "model", "/items": "items" };
const OLD_ONLY = ["/check", "/guide"];   // no module yet: their old functions (and /agent/NAME's)

/* the page an address shows, and what in its path names a thing (an item's id, a kind): as route() reads them */
export function pageOf(path) {
  if (path.startsWith("/item/")) return { name: "item", id: decodeURIComponent(path.slice(6)) };
  if (path.startsWith("/items/")) return { name: "items", id: decodeURIComponent(path.slice(7)) };
  if (path.startsWith("/agent/") || OLD_ONLY.includes(path)) return null;
  return { name: PATHS[path] || "diagram", id: null };   // (any other address: the Diagram, as route() does)
}

/* each page's module, asked for once at the start: its ``page`` export, or nothing (a stub, or a module that failed to
   load: said in the console, and the old page shown) */
const PAGES = {};
export const loaded = Promise.allSettled(PAGE_NAMES.map((n) => import(`/static/app/pages/${n}/index.js`).then((m) => {
  if (typeof m.page === "function") PAGES[n] = m.page;
}, (e) => console.error(`app/pages/${n}/index.js did not load; its old page is shown`, e))));

/* the page drawn into ``main`` when it has moved: true; false leaves it to its old function */
const mounted = new WeakSet();
export function mount(path, q, main) {
  const at = pageOf(path), Page = at && PAGES[at.name];
  if (!Page) return false;
  mounted.add(main);
  render(html`<${Page} path=${path} q=${q} id=${at.id} />`, main);
  return true;
}

/* the page left: unmounted, so its effects end (useApi aborts its calls, stops its polls) */
export function leave(main) {
  if (!mounted.delete(main)) return;
  render(null, main);
}
