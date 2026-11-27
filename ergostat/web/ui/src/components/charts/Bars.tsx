import type { ReactNode } from "react";

/** Counts as a table of horizontal bars, each row its label, its count and a bar as long as its share of the most
    (a field's top values, a histogram's buckets, a lifecycle's transitions). `onRow` makes each label a button. */
export function Bars({ rows, label, onRow, note }: {
  rows: { key: string; label: ReactNode; n: number; title?: string; extra?: ReactNode }[];
  label: string;
  onRow?: (key: string) => void;
  note?: ReactNode;
}) {
  const most = Math.max(1, ...rows.map((r) => r.n));
  return (
    <table className="bars" aria-label={label}>
      <tbody>
        {rows.map((r) => (
          <tr key={r.key} title={r.title}>
            <th scope="row">{onRow ? <button type="button" className="ghost" onClick={() => onRow(r.key)}>{r.label}</button> : r.label}</th>
            <td className="bars-n">{r.n.toLocaleString()}</td>
            <td className="bars-bar"><span style={{ width: `${(100 * r.n) / most}%` }} /></td>
            {r.extra !== undefined && <td className="muted small">{r.extra}</td>}
          </tr>
        ))}
      </tbody>
      {note && <caption className="muted small">{note}</caption>}
    </table>
  );
}
