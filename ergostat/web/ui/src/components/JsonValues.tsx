/* A JSON value laid out as its paths, each value a button when `onPick` is given (an event's data: click a value to
   narrow a query by it, or to read a field from it). `path` is where the value sits, its first part the root's name
   (`data`); the picker is given the path and the value. Lists past 20 members say how many more.
   Given `mark`, each path says what reads it: a value read into a field carries a tag (→ state), a value nothing reads
   stands out, and an ignored path (and all under it) is hidden unless `showIgnored`. */

export type JsonPath = (string | number)[];
/** What reads a path: `to` the field (or key) it fills; `ignored` known not to matter. */
export interface PathMark { to?: string; ignored?: boolean }
type Marker = (p: JsonPath) => PathMark | undefined;

const MOST = 20;

function Leaf({ v, path, onPick, picked, mark }: {
  v: unknown; path: JsonPath; onPick?: (p: JsonPath, v: unknown) => void; picked?: string; mark?: Marker;
}) {
  const text = v === undefined ? "" : JSON.stringify(v);
  const m = mark?.(path);
  const cls = `jv-val jv-${v === null ? "null" : typeof v}${mark ? (m?.to ? " jv-mapped" : m?.ignored ? " jv-ignored" : " jv-unmapped") : ""}`;
  const tag = m?.to ? <span className="jv-to"> → {m.to}</span> : null;
  if (!onPick) return <><span className={cls}>{text}</span>{tag}</>;
  const id = JSON.stringify(path);
  return (
    <>
      <button type="button" className={`${cls}${picked === id ? " on" : ""}`} data-path={id} title="Use this value"
        onClick={() => onPick(path, v)}>{text}</button>{tag}
    </>
  );
}

export function JsonValues({ value, path, onPick, picked, mark, showIgnored }: {
  value: unknown; path: JsonPath; onPick?: (p: JsonPath, v: unknown) => void;
  /** the path picked last (JSON of it), marked */
  picked?: string;
  mark?: Marker; showIgnored?: boolean;
}) {
  if (value === null || typeof value !== "object" || (mark?.(path)?.to && path.length > 1)) {
    return <Leaf v={value} path={path} onPick={onPick} picked={picked} mark={mark} />;
  }
  const entries: [string | number, unknown][] = Array.isArray(value) ? value.map((v, i) => [i, v]) : Object.entries(value);
  // an empty list or map is a value like any other: shown, marked, and pickable (to map or to ignore)
  if (!entries.length) return <Leaf v={value} path={path} onPick={onPick} picked={picked} mark={mark} />;
  const shown = mark && !showIgnored ? entries.filter(([k]) => !mark([...path, k])?.ignored) : entries;
  return (
    <ul className="jv">
      {shown.slice(0, MOST).map(([k, v]) => (
        <li key={String(k)} className={mark?.([...path, k])?.ignored ? "jv-ignored" : undefined}>
          <span className="jv-key">{typeof k === "number" ? `[${k}]` : k}</span>{" "}
          <JsonValues value={v} path={[...path, k]} onPick={onPick} picked={picked} mark={mark} showIgnored={showIgnored} />
        </li>
      ))}
      {shown.length > MOST && <li className="muted">{shown.length - MOST} more</li>}
    </ul>
  );
}
