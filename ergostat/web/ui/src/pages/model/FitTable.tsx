import { Rich, Table } from "../../components";
import { fmt } from "../../lib/format";

/* How well the model fits a set of series (pages.js fitRows/fitHead): n, R², MAPE (or the error as a share), and
   Theil's U_M, U_S, U_C; the total judged on its scaled error. */

const two = (x: number | null | undefined) => (x == null ? "" : x.toFixed(2));
const pct = (x: number | null | undefined) => (x == null ? "" : `${Math.round(x * 100)}%`);
/* MAPE where it means something; else the mean absolute error as a share of the readings' mean or range */
const errorText = (s: any) => (s.mape != null ? pct(s.mape) : s.error_share != null ? `${pct(s.error_share)} of ${s.error_of}` : "");

export function FitTable({ rows, total, first, caption }: { rows: any[]; total?: any; first: string; caption: string }) {
  return (
    <Table caption={caption} className="fit">
      <Table.Head>
        <Table.Th>{first}</Table.Th>
        {["n", "R²", "MAPE", "U_M", "U_S", "U_C"].map((l) => <Table.Th key={l} num><Rich text={l} /></Table.Th>)}
        <Table.Th />
      </Table.Head>
      <Table.Body>
        {rows.map((s, i) => (
          <tr key={s.ref ?? s.name ?? i}>
            <td>
              <b>{s.name}</b>
              {s.unit && <span className="muted">{` ${s.unit}`}</span>}
            </td>
            {s.n == null ? (
              <td className="muted" colSpan={7}>too few points to say</td>
            ) : s.too_little ? (
              <>
                <td className="num">{s.n}</td>
                <td className="muted small" colSpan={6}>{`too little record: ${s.too_little}`}</td>
              </>
            ) : s.exact ? (
              <>
                <td className="num">{s.n}</td>
                <td className="muted" colSpan={6}>no error: the replay is the record</td>
              </>
            ) : (
              <>
                <td className="num">{s.n ?? ""}</td>
                <td className="num">{two(s.r2)}</td>
                <td className="num nowrap">{errorText(s)}</td>
                <td className="num">{two(s.um)}</td>
                <td className="num">{two(s.us)}</td>
                <td className="num">{two(s.uc)}</td>
                <td className="small">{s.says || ""}</td>
              </>
            )}
          </tr>
        ))}
        {total && (
          <tr className="total">
            <td><b>total</b></td>
            <td className="num">{total.n ?? ""}</td>
            <td />
            <td />
            <td className="num">{two(total.um)}</td>
            <td className="num">{two(total.us)}</td>
            <td className="num">{two(total.uc)}</td>
            <td
              className="small"
              title="each stock's mean squared error over its own size (mean square measured), averaged: what a calibration minimises"
            >
              {total.nmse != null ? `scaled error ${fmt(total.nmse)}` : ""}
            </td>
          </tr>
        )}
      </Table.Body>
    </Table>
  );
}
