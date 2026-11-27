import { useState, type ReactNode } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { isPublic } from "../lib/api";
import { ago, clock, dur, recordedShort } from "../lib/format";
import { dashboardHref, diagramHref, projectionHref, scopeHref } from "../lib/hrefs";
import { DEFAULTS } from "../lib/pages";
import type { ProjectionRoute } from "../lib/routes";
import { ancillaryMark, scopedBy, type Scoped } from "../lib/scoped";
import { nameAt, type RouteTable } from "../lib/systemRoutes";
import { useAddress, useDashboards, type DashboardListed } from "../state/dashboards";
import { goalsOff, useStatus, waitsOnYou, type SensorFailing } from "../state/status";
import { WINDOW_WORDS, WINDOWS, type WindowKey, useTime } from "../state/time";
import { Menu } from "./Menu";

/* The app's frame: the header (brand, the System tree, run state, what waits for the owner, the chosen system's nav
   bar, the window) and the page beneath it. The system is the address's (useAddress: the scope it is read in), never
   kept anywhere else (cascading control: the nav bar is the chosen system's). The nav bar: that system's dashboards
   (its defaults, then the model's with `nav:`, then the hover +), a bar, then the projections it contains (an
   ancillary one greyer), those with one `group:` one menu labelled by the group. */

export function Shell({ children }: { children: ReactNode }) {
  const { since } = useTime();
  const carried = since === "1h" ? "" : `?window=${since}`;   // the window chosen, carried to the page gone to
  const { list, projections, table } = useDashboards();
  const { scope } = useAddress();
  const s = scopedBy(table, scope);
  const segs = table?.scopes[scope]?.segments || {};
  const defaults = DEFAULTS.filter(([d]) => !table || segs[d]);
  const navDashboards: [string, string][] = (list || []).filter((d) => d.nav != null && isScopes(d, scope, table))
    .map((d) => [dashboardHref(d.name), d.nav || d.title || d.name]);
  const shown = (projections || []).filter((p) => (s ? s.has("projections", p.name) : p.declared));
  return (
    <>
      <header className="bar">
        <span className="where">
          <Link className="brand" to={scopeHref("", "overview")}>ergostat</Link>
          <SystemTree table={table} scope={scope} carried={carried} />
          <RunState />
          <Failing />
          <Waits />
        </span>
        <nav id="nav" aria-label={`${scope || "The top level"}: its dashboards and projections`}>
          {defaults.map(([d, label]) => (
            <NavLink key={d} to={scopeHref(scope, d) + carried} className={({ isActive }) => (isActive ? "on" : undefined)}>{label}</NavLink>
          ))}
          {navDashboards.map(([to, label]) => (
            <NavLink key={to} to={to + carried} className={({ isActive }) => (isActive ? "on" : undefined)}>{label}</NavLink>
          ))}
          <NewDashboard />
          {shown.length > 0 && <span className="nav-bar-sep" aria-hidden="true" />}
          <ProjectionNav projections={shown} carried={carried} scoped={s} />
        </nav>
        <span id="when"><WindowMenu /></span>
      </header>
      <main id="main">{children}</main>
    </>
  );
}

/** Whether a dashboard the model writes is this scope's own, for its nav bar (not one in place of a default, or a
 *  projection's list there, which have their own entries). */
function isScopes(d: DashboardListed, scope: string, t: RouteTable | undefined): boolean {
  if ((d.system || "") !== scope || d.page || d.projection) return false;
  const local = scope && d.name.startsWith(scope + ".") ? d.name.slice(scope.length + 1) : d.name;
  const seg = t?.scopes[scope]?.segments[local];
  return !DEFAULTS.some(([x]) => x === local) && !seg?.projection;
}

/** The System tree, top left: the top level first (the model's name, or Everything), then each system under the one
 *  it is within; choosing one goes to its overview. */
function SystemTree({ table, scope, carried }: { table: RouteTable | undefined; scope: string; carried: string }) {
  const navigate = useNavigate();
  const { status } = useStatus();
  if (!table) return null;
  const top = status?.name || "Everything";
  const rows: [string, number][] = [];
  const add = (parent: string, depth: number) => {
    for (const x of Object.keys(table.scopes).filter((k) => k !== "" && table.scopes[k].within === parent)) {
      if (rows.some(([r]) => r === x)) continue;
      rows.push([x, depth]);
      add(x, depth + 1);
    }
  };
  add("", 1);
  return (
    <Menu label={<><span className="muted small">System </span>{scope || top}</>} className="system-menu"
      title="The system the nav bar is of: systems contain systems">
      <Menu.Item checked={scope === ""} onSelect={() => navigate(scopeHref("", "overview") + carried)}>{top}</Menu.Item>
      {rows.map(([x, depth]) => (
        <Menu.Item key={x} checked={scope === x} onSelect={() => navigate(scopeHref(x, "overview") + carried)}>
          <span className="depth" style={{ width: `${depth * 1.1}em` }} aria-hidden="true" />{table.scopes[x].name || x}
        </Menu.Item>
      ))}
    </Menu>
  );
}

/** The + at the end of the nav bar's dashboards, seen on hover: a new, empty dashboard, drawn where the page is until it
 *  is saved under its name, in the system whose nav bar it is (Resolve.tsx, components/panels/NewDashboard.tsx). */
function NewDashboard() {
  const navigate = useNavigate();
  const { pathname, search } = useLocation();
  if (isPublic()) return null;
  return (
    <button type="button" className="ghost nav-new" title="A new dashboard: saved under a name, it is in the nav bar"
      aria-label="New dashboard" onClick={() => navigate(pathname + search, { state: { newDashboard: Date.now() } })}>+</button>
  );
}

/** The scope's projections after a bar, each its own link to its list; those the model gives one `group:` are one
 *  menu, labelled by the group, in the place of the group's first. An ancillary one (defined in another system, or
 *  ergostat's own) is greyer, its title saying where it is defined. */
function ProjectionNav({ projections, carried, scoped }: { projections: ProjectionRoute[]; carried: string; scoped: Scoped | null }) {
  const navigate = useNavigate();
  const { at, table, scope } = useAddress();
  const named = (n: string) => title(nameAt(table, "projections", n, scope));   // a remote's by its short name in it
  const here = at && (at.kind === "projection" || at.kind === "item") ? at.name : at?.projection ?? null;
  const to = (name: string) => projectionHref(name, "", scoped?.system) + carried;
  const seen = new Set<string>();
  const out: ReactNode[] = [];
  for (const p of projections) {
    const mark = ancillaryMark(scoped, "projections", p.name);
    if (!p.group) {
      out.push(<NavLink key={p.name} to={to(p.name)} title={mark.title}
        className={({ isActive }) => [isActive || here === p.name ? "on" : "", mark.className || ""].join(" ").trim() || undefined}>{named(p.name)}</NavLink>);
    } else if (!seen.has(p.group)) {
      seen.add(p.group);
      const members = projections.filter((q) => q.group === p.group);
      const all = members.every((q) => ancillaryMark(scoped, "projections", q.name).className);
      out.push(
        <Menu key={`group:${p.group}`} label={title(p.group)}
          buttonClassName={[members.some((q) => q.name === here) ? "on" : "", all ? "ancillary" : ""].join(" ").trim()}>
          {members.map((q) => <Menu.Item key={q.name} checked={q.name === here}
            onSelect={() => navigate(to(q.name))}>
            <span {...ancillaryMark(scoped, "projections", q.name)}>{named(q.name)}</span></Menu.Item>)}
        </Menu>);
    }
  }
  return <>{out}</>;
}

/** A name as a link's words: ready-for-review → Ready for review. */
const title = (n: string) => { const w = n.replace(/[-_]+/g, " "); return w.charAt(0).toUpperCase() + w.slice(1); };

function RunState() {
  const { status: st } = useStatus();
  if (!st) return <span className="runstate" />;
  const { off, upkeep } = goalsOff(st);
  const edited = st.edited;
  const cls = "runstate" + (off || edited ? " bad" : !st.running ? " warn" : "");
  const said = edited ? "Model errors" : off || upkeep ? `${off} off` : st.running ? "Running" : "Not running";
  const names = !off ? [] : Object.entries(st.loops || {}).filter(([, l]: [string, any]) => l.state === "off" && !l.upkeep).map(([n]) => `${n}: off`);
  const tip = [
    edited ? `${edited.banner}:\n${edited.errors.join("\n")}` : off || upkeep ? `${off} goal${off === 1 ? "" : "s"} off${st.running ? "" : ", not running"}` : "",
    upkeep ? `model upkeep ${upkeep}` : "",
    ...names,
  ].filter(Boolean).join("\n");
  if (edited) return <ModelErrors cls={cls} said={said} banner={edited.banner} errors={edited.errors || []} />;
  return <Link id="running" className={cls} to={scopeHref("", "goals")} title={tip || undefined}>{said}</Link>;
}

/* the model file's errors, said in a small note under the run state (`ergostat check` says the same in a terminal) */
function ModelErrors({ cls, said, banner, errors }: { cls: string; said: string; banner: string; errors: string[] }) {
  return (
    <Menu label={said} buttonClassName={`${cls} model-errors`} title={banner}>
      <Menu.Block>
        <div id="model-errors" className="model-errors-note">
          <strong>{banner}</strong>
          <ul>{errors.map((e, i) => <li key={i}>{e}</li>)}</ul>
          <span className="muted small">ergostat check says the same in a terminal.</span>
        </div>
      </Menu.Block>
    </Menu>
  );
}

/** The sensors whose newest read failed: their parts are unmeasured, said in the header whatever page is open. */
function Failing() {
  const { status } = useStatus();
  const xs: SensorFailing[] = status?.sensors_failing || [];
  if (!xs.length) return null;
  const tip = xs.map((x) => `${x.sensor}: ${x.why}`).join("\n");
  return <Link id="sensors-failing" className="runstate bad" to={diagramHref()} title={tip}>
    {xs.length} sensor{xs.length === 1 ? "" : "s"} failing</Link>;
}

function Waits() {
  const { status } = useStatus();
  const n = (status?.attention || []).filter(waitsOnYou).length;
  return (
    <span className="waits-said" aria-live="polite" aria-atomic="true">
      {n > 0 && <Link id="waits" className="waits" to={`${diagramHref()}#waiting`} title={`${n} wait for you`}>{n} for you</Link>}
    </span>
  );
}

/* the window the page looks over, and the moment it shows: the slider's right end is now (live) */
function WindowMenu() {
  const { since, at, seconds, setSince, setAt } = useTime();
  const { status } = useStatus();
  const r = status?.window === seconds ? recordedShort(status) : null;
  const label = (at ? `${since} to ${clock(at)}` : `Last ${since}`) + (r != null ? ` (${dur(r)} recorded)` : "");
  const now = Date.now() / 1000;
  const lo = Math.max(now - seconds * 3, status?.first || now - seconds);
  const hi = now;
  const [drag, setDrag] = useState<number | null>(null);
  const shown = drag ?? at;
  return (
    <Menu label={label} right buttonClassName={at ? "past" : ""} title="The window the page looks over, and the moment it shows">
      <Menu.Label>Window</Menu.Label>
      {(Object.keys(WINDOWS) as WindowKey[]).map((k) => (
        <Menu.Item key={k} checked={since === k} onSelect={() => setSince(k)}>{WINDOW_WORDS[k]}</Menu.Item>
      ))}
      <Menu.Sep />
      <Menu.Block>
        <Menu.Label>Moment</Menu.Label>
        <input
          type="range"
          min={0}
          max={1000}
          aria-label="The moment shown"
          defaultValue={at ? Math.round(((at - lo) / (hi - lo || 1)) * 1000) : 1000}
          onInput={(e) => { const v = +(e.target as HTMLInputElement).value; setDrag(v >= 998 ? null : lo + (hi - lo) * (v / 1000)); }}
          onChange={(e) => { const v = +e.target.value; setAt(v >= 998 ? null : lo + (hi - lo) * (v / 1000)); setDrag(null); }}
        />
        <span className="muted small">{shown ? `${clock(shown)}, ${ago(shown)}` : "Live"}</span>
      </Menu.Block>
      {at && <Menu.Item onSelect={() => setAt(null)}>Back to live</Menu.Item>}
    </Menu>
  );
}
