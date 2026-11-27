/* A JSON value laid out as its paths, each value a button when `onPick` is given (an event's data: click a value to
   narrow a query by it, or to read a field from it). `path` is where the value sits, its first part the root's name
   (`data`); the picker is given the path and the value. Lists past 20 members say how many more. */

export type JsonPath = (string | number)[];

const MOST = 20;

function Leaf({ v, path, onPick, picked }: { v: unknown; path: JsonPath; onPick?: (p: JsonPath, v: unknown) => void; picked?: string }) {
  const text = v === undefined ? "" : JSON.stringify(v);
  const cls = `jv-val jv-${v === null ? "null" : typeof v}`;
  if (!onPick) return <span className={cls}>{text}</span>;
  const id = JSON.stringify(path);
  return (
    <button type="button" className={`${cls}${picked === id ? " on" : ""}`} data-path={id} title="Use this value"
      onClick={() => onPick(path, v)}>{text}</button>
  );
}

export function JsonValues({ value, path, onPick, picked }: {
  value: unknown; path: JsonPath; onPick?: (p: JsonPath, v: unknown) => void;
  /** the path picked last (JSON of it), marked */
  picked?: string;
}) {
  if (value === null || typeof value !== "object") return <Leaf v={value} path={path} onPick={onPick} picked={picked} />;
  const entries: [string | number, unknown][] = Array.isArray(value) ? value.map((v, i) => [i, v]) : Object.entries(value);
  if (!entries.length) return <span className="jv-val">{Array.isArray(value) ? "[]" : "{}"}</span>;
  return (
    <ul className="jv">
      {entries.slice(0, MOST).map(([k, v]) => (
        <li key={String(k)}>
          <span className="jv-key">{typeof k === "number" ? `[${k}]` : k}</span>{" "}
          <JsonValues value={v} path={[...path, k]} onPick={onPick} picked={picked} />
        </li>
      ))}
      {entries.length > MOST && <li className="muted">{entries.length - MOST} more</li>}
    </ul>
  );
}
