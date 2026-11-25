import { useState } from "react";
import { AppLink, Button, DataTable, Page, Rich, Section, Select } from "../../components";
import { useApi } from "../../hooks/useApi";
import { apiPost, isPublic } from "../../lib/api";
import { ago, dur, fmt, op } from "../../lib/format";
import { FitTable } from "./FitTable";
import { ReviewEntry } from "./Review";

/* The Model: the changes waiting for review (and calibration), what ergostat can propose, how well the model fits
   (the stocks an equation moves, the equations, the accounting), its history and the residuals. /api/fit, every 5 s.
   The old page's pageModel (pages.js). */

const sub = (r: string) => r.split(".").slice(1).join(".");

export default function ModelPage() {
  const fit = useApi<any>("fit", {}, { every: 5000 });
  const d = fit.data;
  if (d === undefined)
    return (
      <Page title="Model">
        {fit.error
          ? <p className="muted">The model is an ergostat.toml: equations and their fit come with ergostat.yaml.</p>
          : <p className="muted">Loading…</p>}
      </Page>
    );
  const span = d.until && d.since ? dur(d.until - d.since) : "";
  const judged = Object.entries<string>(d.judged_by_stock || {});
  const queue: any[] = d.queue || [];
  const waiting = queue.length + (d.held || 0);
  const why = Object.entries<string>(d.not_proposed || {});
  const r = d.residuals || {};
  const resRows = Object.entries<any>(r).sort((a, b) => (b[1].significant ? 1 : 0) - (a[1].significant ? 1 : 0));
  const history = [
    ...(d.history || []).map((v: any) => ({ t: v.first, v })),
    ...(d.accepted || []).map((a: any) => ({ t: a.time, a })),
  ].sort((x, y) => y.t - x.t).slice(0, 30);

  return (
    <Page title="Model">
      <Section title={<span id="review-queue">Changes to review</span>} note={waiting ? `${waiting} waiting` : undefined}>
        <Calibrate d={d} onDone={fit.refresh} />
        <div className="review">
          {queue.map((x) => <ReviewEntry key={x.id} e={x} onDone={() => setTimeout(fit.refresh, 600)} />)}
          {!queue.length && !d.held && <p className="muted">Nothing waiting.</p>}
          {d.held > 0 && (
            <p className="muted">
              {`${d.held} modelling request${d.held > 1 ? "s" : ""} held for you: answered in `}
              <AppLink to="/diagram">Needs attention</AppLink>.
            </p>
          )}
        </div>
        {why.length > 0 && (
          <>
            <h3>Estimates not proposed</h3>
            <DataTable
              caption="Estimates not proposed"
              className="can"
              columns={[
                { key: "p", header: "parameter", render: ([n]) => <b>{n}</b> },
                { key: "w", header: "why", className: "small", render: ([, w]) => w },
              ]}
              rows={why}
              rowKey={([n]) => n}
            />
          </>
        )}
        {d.open_loops?.length > 0 && (
          <p className="muted small">
            {`Every stock integrated still leaves open ${d.open_said}, since the replay takes what a decision sets as measured.`}
          </p>
        )}
      </Section>

      <Section title="What ergostat can propose">
        <DataTable
          caption="What ergostat can propose"
          className="can"
          columns={[
            { key: "what", header: "change" },
            { key: "how", header: "found by", className: "small" },
          ]}
          rows={d.can || []}
          rowKey={(c: any, i) => c.what + i}
        />
        <h3>Not yet</h3>
        <ul className="plain">{(d.cannot || []).map((x: string, i: number) => <li key={i}>{x}</li>)}</ul>
        <p className="muted small">
          From the residuals ergostat finds one kind of missing structure: a delay on a measured stock's inflow (as DELAY3,
          or as a stock in transit). Not a missing outflow or cause, a delay on an outflow, or a part replaced by another form.
        </p>
        {(d.not_made || []).length > 0 && (
          <>
            <h3>Found, and not proposed</h3>
            <DataTable
              caption="Found, and not proposed"
              className="can"
              columns={[
                { key: "title", header: "change" },
                { key: "why", header: "why not", className: "small" },
              ]}
              rows={d.not_made}
              rowKey={(x: any, i) => x.title + i}
            />
          </>
        )}
      </Section>

      <Section title={<span id="model-fit">How well the model fits</span>}>
        {d.modelling?.says && <p className="muted"><b>Modelling: </b>{d.modelling.says}</p>}
        {d.invalid?.length > 0 && <p className="s-off">{`The replay is not valid: ${d.invalid.join("; ")}.`}</p>}
        <h3>Model fit<span className="muted">{` the stocks an equation moves, over the last ${span} of record`}</span></h3>
        {d.stocks.length
          ? <FitTable rows={d.stocks} total={d.total} first="stock" caption="Model fit" />
          : <p className="muted">No stock is moved by an equation: nothing here tests the model's equations yet.</p>}
        {(d.partial.length > 0 || d.equations.length > 0 || judged.length > 0) && (
          <>
            <h3>Equations, inputs as measured<span className="muted"> the partial-model test</span></h3>
            {d.partial.length
              ? <FitTable rows={d.partial} first="worked out" caption="Equations, inputs as measured" />
              : <p className="muted">No equation's part is measured.</p>}
            {d.equations.length > 0 && (
              <>
                <h3>Equations, replayed<span className="muted"> every stock integrated</span></h3>
                <FitTable rows={d.equations} first="worked out" caption="Equations, replayed" />
              </>
            )}
            {judged.map(([ref, st]) => (
              <p key={ref} className="muted small">
                {`${sub(ref)} is measured from its stock's changes: judged by ${st ? sub(st) : "its stock"}'s replay, above.`}
              </p>
            ))}
          </>
        )}
        {d.accounting.length > 0 && (
          <>
            <h3>Accounting<span className="muted"> stocks moved only by measured flows</span></h3>
            <FitTable rows={d.accounting} first="stock" caption="Accounting" />
          </>
        )}
        {(d.notes || []).map((n: string, i: number) => <p key={i} className="muted small">{n}</p>)}
      </Section>

      <Section title="History">
        {history.length ? (
          <DataTable
            caption="History"
            className="fit"
            columns={[
              { key: "when", header: "when", className: "nowrap", render: ({ v, a }) => ago(v ? v.first : a.time) },
              {
                key: "version", header: "version", className: "mono",
                render: ({ v, a }) => v
                  ? <>{v.version}{v.version === d.version && <span className="muted"> now</span>}</>
                  : <span className="muted">{`${a.version_before} → ${a.version_after}`}</span>,
              },
              {
                key: "err", header: "scaled error", num: true,
                render: ({ v, a }) => v
                  ? (v.total?.nmse != null ? fmt(v.total.nmse) : "")
                  : `${a.fit_before?.nmse != null ? fmt(a.fit_before.nmse) : "–"} → ${a.fit_after?.nmse != null ? fmt(a.fit_after.nmse) : "–"}`,
              },
              { key: "over", header: "over", num: true, render: ({ v }) => (v?.window ? dur(v.window) : "") },
              {
                key: "said", header: "",
                render: ({ v, a }) => v
                  ? <span className="muted small">{`fitted ${v.fits} time${v.fits > 1 ? "s" : ""}, last ${ago(v.last)}`}</span>
                  : <>accepted: {op(a.title)}</>,
              },
            ]}
            rows={history}
            rowKey={(x, i) => `${x.t}${i}`}
          />
        ) : <p className="muted">Not fitted before.</p>}
      </Section>

      <Section title="Residuals">
        {resRows.length ? (
          <DataTable
            caption="Residuals"
            className="fit"
            columns={[
              { key: "stock", header: "stock", render: ([k]) => <b>{k}</b> },
              { key: "change", header: "changed", num: true, render: ([, v]) => fmt(v.change) },
              { key: "explained", header: "explained", num: true, render: ([, v]) => fmt(v.explained) },
              { key: "unexplained", header: "unexplained", num: true, render: ([, v]) => fmt(v.unexplained) },
              {
                key: "said", header: "",
                render: ([, v]) => v.significant
                  ? <span className="s-open">unexplained</span>
                  : v.absorbed_by.length ? <span className="muted">{`estimated as ${v.absorbed_by.join(", ")}`}</span> : "",
              },
            ]}
            rows={resRows}
            rowKey={([k]) => k}
          />
        ) : <p className="muted">No stock has two readings in this window yet.</p>}
      </Section>
      <p className="note">
        <Rich
          text={`Version ${d.version}, fitted over the last ${span} of record (at most a day, whatever the window above). ` +
            "The model is read the way the record was made: a level at its reading's moment, a counted flow by what it moved in each bucket, a rate a sensor averages by the model's own average. " +
            `Each series needs ${d.min_points} points over three of its slowest time constant to be judged. ` +
            `The total: ${d.words.nmse}. R²: ${d.words.r2}. MAPE: ${d.words.mape}. Theil's U_M: ${d.words.um}; U_S: ${d.words.us}; U_C: ${d.words.uc}; the three sum to 1. ` +
            `Accounting: ${d.words.accounting}. ` +
            "Residuals: what each stock did against what its known flows explain; a disturbance nothing measures is estimated from the rest."}
        />
      </p>
    </Page>
  );
}

/* Estimate now, or calibrate: each part alone, each system alone driven by its measured inputs, or the whole model's
   replay; each a set of proposals with the fit before and after, that join the queue above */
function Calibrate({ d, onDone }: { d: any; onDone: () => void }) {
  const [chosen, setChosen] = useState("parts");
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState("");
  const ways = (d.calibrations || []).filter((c: any) => c.key === "parts" || c.count);
  const which = ways.length > 1 ? chosen : "parts";
  const go = async () => {
    setBusy(true);
    setSaid(which === "parts" ? "Estimating…" : "Calibrating…");
    try {
      await apiPost("estimate", { calibrate: which });
      setSaid("");
    } catch (e) {
      setSaid(String((e as Error).message || e));
    }
    setBusy(false);
    onDone();
  };
  const n = d.to_estimate.length;
  return (
    <div className="actions">
      {!isPublic() && (
        <>
          <Button variant="ghost" disabled={busy} onClick={go}>{n ? "Calibrate" : "Estimate now"}</Button>
          {ways.length > 1 && (
            <Select
              aria-label="what to fit at once"
              value={chosen}
              onChange={(ev) => setChosen(ev.target.value)}
              options={ways.map((c: any) => ({
                value: c.key,
                label: c.key === "whole" && d.open_loops?.length
                  ? `${c.words} (${d.open_loops.length} loop${d.open_loops.length > 1 ? "s" : ""} left open)`
                  : c.words,
              }))}
            />
          )}
        </>
      )}
      <span className="muted small">
        {n
          ? `${n} parameter${n > 1 ? "s" : ""} to estimate${d.estimated_at ? `, last calibrated ${ago(d.estimated_at)}` : ", not calibrated yet"}`
          : "no parameter is marked estimate: true"}
      </span>
      {d.loops_analysed < d.loops && <span className="muted small">{`loops analysed for proposals: ${d.loops_analysed} of ${d.loops}`}</span>}
      {said && <span className="muted small">{said}</span>}
    </div>
  );
}
