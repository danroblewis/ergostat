import { useState, type ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";
import { apiGet } from "../lib/api";
import { ago, clock, dur, recordedShort } from "../lib/format";
import { goalsOff, useStatus, waitsOnYou } from "../state/status";
import { WINDOW_WORDS, WINDOWS, type WindowKey, useTime } from "../state/time";
import { Menu } from "./Menu";

/* The app's frame: the header (brand, project, run state, what waits for the owner, the pages, the window) and the
   page beneath it. */

const NAV: [string, string][] = [
  ["/diagram", "Diagram"], ["/dashboard", "Dashboard"], ["/goals", "Goals"], ["/agents", "Agents"], ["/items", "Items"],
  ["/record", "Record"], ["/model", "Model"], ["/check", "Check"], ["/guide", "Guide"],
];

export function Shell({ children }: { children: ReactNode }) {
  const { since } = useTime();
  const carried = since === "1h" ? "" : `?window=${since}`;   // the window chosen, carried to the page gone to
  return (
    <>
      <header className="bar">
        <span className="where">
          <Link className="brand" to="/diagram">ergostat</Link>
          <ProjectSelect />
          <RunState />
          <Waits />
        </span>
        <nav id="nav">
          {NAV.map(([to, label]) => (
            <NavLink key={to} to={to + carried} className={({ isActive }) => (isActive ? "on" : undefined)}>{label}</NavLink>
          ))}
        </nav>
        <span id="when"><WindowMenu /></span>
      </header>
      <main id="main">{children}</main>
    </>
  );
}

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
  return <Link id="running" className={cls} to={edited ? "/check" : "/goals"} title={tip || undefined}>{said}</Link>;
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

/* the other projects running on this machine, to switch to; listed when the reader comes to the list */
function ProjectSelect() {
  const { status } = useStatus();
  const [list, setList] = useState<any>(null);
  const [askedAt, setAskedAt] = useState(0);
  const fresh = () => {
    if (Date.now() - askedAt < 30000) return;
    setAskedAt(Date.now());
    apiGet("projects").then(setList).catch(() => {});
  };
  const name = status?.name || "";
  const others = (list?.running || []).filter((p: any) => p.name !== name);
  return (
    <select
      id="project"
      title="Other projects on this machine"
      value=""
      onPointerEnter={fresh}
      onFocus={fresh}
      onChange={(e) => { if (e.target.value) location.href = e.target.value + location.pathname + location.search; }}
    >
      <option value="">{name}</option>
      {others.map((p: any) => {
        const bits = [
          p.goals_off?.length ? `${p.goals_off.length} off` : "",
          p.unknown?.length ? `${p.unknown.length} unknown` : "",
          p.error ? "cannot load" : p.web ? "" : "no page",
        ].filter(Boolean);
        return (
          <option key={p.name} value={p.web || ""} disabled={!p.web} title={p.error || undefined}>
            {p.name}{bits.length ? ` (${bits.join(", ")})` : ""}
          </option>
        );
      })}
      {list?.stopped ? <option value="" disabled>{list.stopped} stopped (ergostat projects)</option> : null}
    </select>
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
