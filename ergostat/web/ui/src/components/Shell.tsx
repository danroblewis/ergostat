import { useState, type ReactNode } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { ago, clock, dur, recordedShort } from "../lib/format";
import { dashboardHref, useDashboards } from "../state/dashboards";
import { goalsOff, useStatus, waitsOnYou, type SensorFailing } from "../state/status";
import { WINDOW_WORDS, WINDOWS, type WindowKey, useTime } from "../state/time";
import { Menu } from "./Menu";
import type { ProjectionRoute } from "../lib/routes";

/* The app's frame: the header (brand, run state, what waits for the owner, the pages, the window) and the
   page beneath it. */

const NAV: [string, string][] = [
  ["/dashboard", "Dashboard"], ["/diagram", "Diagram"], ["/goals", "Goals"], ["/agents", "Agents"], ["/record", "Record"],
];

export function Shell({ children }: { children: ReactNode }) {
  const { since } = useTime();
  const carried = since === "1h" ? "" : `?window=${since}`;   // the window chosen, carried to the page gone to
  const { list, projections } = useDashboards();   // the model's projections (each at /NAME) and dashboards with nav:
  const own = (projections || []).filter((p) => p.declared);   // the model's own, not ergostat's
  const navDashboards: [string, string][] = (list || []).filter((d) => d.nav != null)
    .map((d) => [dashboardHref(d.name), d.nav || d.title || d.name]);
  return (
    <>
      <header className="bar">
        <span className="where">
          <Link className="brand" to="/diagram">ergostat</Link>
          <RunState />
          <Failing />
          <Waits />
        </span>
        <nav id="nav">
          {NAV.map(([to, label]) => (
            <NavLink key={to} to={to + carried} className={({ isActive }) => (isActive ? "on" : undefined)}>{label}</NavLink>
          ))}
          {navDashboards.map(([to, label]) => (
            <NavLink key={to} to={to + carried} className={({ isActive }) => (isActive ? "on" : undefined)}>{label}</NavLink>
          ))}
          {own.length > 0 && <span className="nav-bar-sep" aria-hidden="true" />}
          <ProjectionNav projections={own} carried={carried} />
        </nav>
        <span id="when"><WindowMenu /></span>
      </header>
      <main id="main">{children}</main>
    </>
  );
}

/** The model's projections after a bar, each its own link to its list (/NAME); those the model gives one `group:` are
 *  one menu, labelled by the group, in the place of the group's first. */
function ProjectionNav({ projections, carried }: { projections: ProjectionRoute[]; carried: string }) {
  const navigate = useNavigate();
  const head = decodeURIComponent(useLocation().pathname.split("/")[1] || "");
  const seen = new Set<string>();
  const out: ReactNode[] = [];
  for (const p of projections) {
    if (!p.group) {
      out.push(<NavLink key={p.name} to={`/${encodeURIComponent(p.name)}${carried}`}
        className={({ isActive }) => (isActive ? "on" : undefined)}>{title(p.name)}</NavLink>);
    } else if (!seen.has(p.group)) {
      seen.add(p.group);
      const members = projections.filter((q) => q.group === p.group);
      out.push(
        <Menu key={`group:${p.group}`} label={title(p.group)} buttonClassName={members.some((q) => q.name === head) ? "on" : ""}>
          {members.map((q) => <Menu.Item key={q.name} checked={q.name === head}
            onSelect={() => navigate(`/${encodeURIComponent(q.name)}${carried}`)}>{title(q.name)}</Menu.Item>)}
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
  return <Link id="running" className={cls} to="/goals" title={tip || undefined}>{said}</Link>;
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
  return <Link id="sensors-failing" className="runstate bad" to="/diagram" title={tip}>
    {xs.length} sensor{xs.length === 1 ? "" : "s"} failing</Link>;
}

function Waits() {
  const { status } = useStatus();
  const n = (status?.attention || []).filter(waitsOnYou).length;
  return (
    <span className="waits-said" aria-live="polite" aria-atomic="true">
      {n > 0 && <Link id="waits" className="waits" to="/diagram#waiting" title={`${n} wait for you`}>{n} for you</Link>}
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
