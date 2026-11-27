import type { ReactNode, MouseEvent, ThHTMLAttributes, TdHTMLAttributes } from "react";
import { useNavigate } from "react-router-dom";

/* A data table, composed: <Table caption="..."><Table.Head>...<Table.Th/>...</Table.Head><Table.Body>
   <Table.Row to="/item/x"><Table.Td/></Table.Row></Table.Body></Table>. Every data table has a caption for those who
   hear it (shown only to them). A row with ``to`` opens that page on click (with ctrl, cmd or shift, a new tab).
   For the common case of rows of records, <DataTable> (below) takes columns and rows. */

interface TableProps {
  caption: string;
  className?: string;
  children: ReactNode;
}

export function Table({ caption, className, children }: TableProps) {
  return (
    <div className="table-wrap">
      <table className={className}>
        <caption className="sr-only">{caption}</caption>
        {children}
      </table>
    </div>
  );
}

function Head({ children }: { children: ReactNode }) {
  return (
    <thead>
      <tr>{children}</tr>
    </thead>
  );
}

function Th({ num, sort, children, ...rest }: ThHTMLAttributes<HTMLTableCellElement> & { num?: boolean; sort?: "ascending" | "descending" }) {
  return (
    <th scope="col" aria-sort={sort} className={[num && "num", rest.className].filter(Boolean).join(" ") || undefined} {...rest}>
      {children}
    </th>
  );
}

function Td({ num, children, className, ...rest }: TdHTMLAttributes<HTMLTableCellElement> & { num?: boolean }) {
  return (
    <td className={[num && "num", className].filter(Boolean).join(" ") || undefined} {...rest}>
      {children}
    </td>
  );
}

function Body({ children, className }: { children: ReactNode; className?: string }) {
  return <tbody className={className}>{children}</tbody>;
}

interface RowProps {
  to?: string;
  onClick?: () => void;
  className?: string;
  title?: string;
  children: ReactNode;
}

function Row({ to, onClick, className, title, children }: RowProps) {
  const navigate = useNavigate();
  const clickable = !!(to || onClick);
  const open = (ev: MouseEvent) => {
    if ((ev.target as HTMLElement).closest("a, button, input, select")) return;
    if (to && (ev.metaKey || ev.ctrlKey || ev.shiftKey)) { window.open(`${to}`, "_blank"); return; }
    if (to) navigate(to);
    onClick?.();
  };
  return (
    <tr className={[clickable && "click", className].filter(Boolean).join(" ") || undefined} title={title} onClick={clickable ? open : undefined}>
      {children}
    </tr>
  );
}

Table.Head = Head;
Table.Th = Th;
Table.Body = Body;
Table.Row = Row;
Table.Td = Td;

export interface Column<R> {
  key: string;
  header: ReactNode;
  num?: boolean;
  className?: string;
  render?: (row: R, i: number) => ReactNode;
}

interface DataTableProps<R> {
  caption: string;
  columns: Column<R>[];
  rows: R[];
  rowKey: (row: R, i: number) => string;
  rowTo?: (row: R) => string | undefined;
  onRow?: (row: R) => void;
  className?: string;
  empty?: ReactNode;
}

/** Rows of records under columns: the common table, built from the parts above. */
export function DataTable<R>({ caption, columns, rows, rowKey, rowTo, onRow, className, empty }: DataTableProps<R>) {
  if (!rows.length && empty) return <>{empty}</>;
  return (
    <Table caption={caption} className={className}>
      <Table.Head>
        {columns.map((c) => <Table.Th key={c.key} num={c.num}>{c.header}</Table.Th>)}
      </Table.Head>
      <Table.Body>
        {rows.map((r, i) => (
          <Table.Row key={rowKey(r, i)} to={rowTo?.(r)} onClick={onRow ? () => onRow(r) : undefined}>
            {columns.map((c) => (
              <Table.Td key={c.key} num={c.num} className={c.className}>
                {c.render ? c.render(r, i) : String((r as any)[c.key] ?? "")}
              </Table.Td>
            ))}
          </Table.Row>
        ))}
      </Table.Body>
    </Table>
  );
}

/** Fields of one record, name against value (table.fields). */
export function Fields({ caption, fields }: { caption: string; fields: [ReactNode, ReactNode][] }) {
  return (
    <Table caption={caption} className="fields">
      <Table.Body>
        {fields.map(([k, v], i) => (
          <tr key={i}>
            <th scope="row">{k}</th>
            <td>{v}</td>
          </tr>
        ))}
      </Table.Body>
    </Table>
  );
}
