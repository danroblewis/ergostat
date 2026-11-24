/* the app shell: the header (the project, the two counts, the navigation, the window) as Preact components, the router
   (router.js) and the timing overlay (timing.js); then the old start (main.js startPage), which fills the project list
   and the window's menu into the header drawn here, asks for the status and routes the first page (docs/frontend.md).
   A snapshot or a page opened from a file loads no ES module: main.js starts by itself on index.html's own header. */
import { html, render, store, sync, useStore } from "/static/app/core.js";
import { leave, loaded, mount } from "/static/app/router.js";
import { Timing } from "/static/app/timing.js";

const NAV = [["/diagram", "Diagram"], ["/dashboard", "Dashboard"], ["/goals", "Goals"], ["/agents", "Agents"], ["/items", "Items"],
             ["/record", "Record"], ["/model", "Model"], ["/check", "Check"], ["/guide", "Guide"]];

/* the two counts, each a link with its full wording as its title (util.js headerCounts, from the store's status) */
function Status() {
  const c = headerCounts(useStore((s) => s.status));
  return html`<a id="running" class=${c.cls} href=${c.href} title=${c.tip || undefined}>${c.said}</a><span class="waits-said"
    aria-live="polite" aria-atomic="true"><a id="waits" class="waits" href=${appHref("/diagram#waiting")} hidden=${!c.n}
    title=${c.waitsTitle || undefined}>${c.waitsTitle ? `${c.n} for you` : ""}</a></span>`;
}

/* the navigation: the page shown marked (its top path, as route() reads it) */
function Nav() {
  const top = useStore((s) => s.route);
  return html`<nav id="nav">${NAV.map(([to, name]) => {
    const on = routeOfHref(to) === top;
    return html`<a href=${appHref(to)} class=${on ? "on" : undefined} aria-current=${on ? "page" : undefined}>${name}</a>`;
  })}</nav>`;
}

/* the header: drawn once; the project list and the window's menu in it are main.js's (filled after), never redrawn */
const Header = () => html`<span class="where"><a class="brand" href=${appHref("/diagram")}>ergostat</a><select id="project"
  title="Other projects on this machine"></select><${Status} /></span><${Nav} /><span id="when"></span>`;

if (!HASHED && typeof startPage === "function") {
  const bar = document.querySelector("header.bar");
  bar.replaceChildren();                          // index.html's header (the served page's and a snapshot's), drawn anew
  render(html`<${Header} />`, bar);
  const overlay = document.body.appendChild(document.createElement("div"));
  render(html`<${Timing} />`, overlay);
  window.ergostatApp = { sync, mount, leave, store };
  await loaded;                                   // each page's module known before the first page is routed
  startPage();
}
