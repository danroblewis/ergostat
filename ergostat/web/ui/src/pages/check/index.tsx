import { Fragment, type ReactNode } from "react";
import { AppLink, DataTable, Page, Section, type Column } from "../../components";
import { useApi } from "../../hooks/useApi";
import { dur, fmt, op } from "../../lib/format";
import { useStatus } from "../../state/status";

/* Check: the static check's findings (errors, then warnings, a kind said once above a row per part), the notes, the
   coherence of the three views, and the model's counts. The old page's pageCheck (pages.js). */

interface Finding {
  level: string;
  message: string;
  code?: string;
  where?: string;
  about?: string;
  [k: string]: any;
}

const two = (x: number | null | undefined) => (x == null ? "" : x.toFixed(2));

/** A link to a part on the diagram (the old page's toolLink to the Dynamics view). */
export const PartLink = ({ about }: { about: string }) => (
  <AppLink to={`/diagram?${new URLSearchParams({ view: "dynamics", open: "*", part: about })}`} title="on the diagram">
    {about.replace(".", " ")}
  </AppLink>
);

interface Kind {
  title: string;
  advice: string;
  code: string;
  rows: Finding[];
  cols: Column<Finding>[];
}

/* the findings that come many of a kind (/api/exercised): what each kind says, its columns, and which is worst */
const FINDING_KINDS: Record<string, { title: string; advice: string; cols: Column<Finding>[]; worst: (a: Finding, b: Finding) => number }> = {
  "not-exercised": {
    title: "Not exercised by the record",
    advice: "Its rate cannot be identified from this record, which is not evidence it is absent: it is kept, and nothing is " +
      "estimated or judged from it until the record moves it (a step test or a planned disturbance would).",
    cols: [
      { key: "why", header: "why", className: "small", render: (c) => c.says },
      { key: "record", header: "record", num: true, render: (c) => dur(c.span) },
      { key: "points", header: "points", num: true, render: (c) => c.readings },
    ],
    worst: (a, b) => (a.why === "never-moved" ? 0 : 1) - (b.why === "never-moved" ? 0 : 1) || b.span - a.span,
  },
  "calibration-worse-than-mean": {
    title: "Equations that fit worse than their mean",
    advice: "Its equation fits its record worse than holding it at its mean: calibrate it, or write it again.",
    cols: [
      { key: "r2", header: "R²", num: true, render: (c) => two(c.r2 ?? 0) },
      { key: "nmse", header: "scaled error", num: true, render: (c) => fmt(c.nmse) },
      { key: "n", header: "points", num: true, render: (c) => c.n },
    ],
    worst: (a, b) => b.nmse - a.nmse,
  },
};
const SAID = /^(?:(\S+:\d+): )?(stock|flow|auxiliary|parameter|goal|block|items|agent) ([^\s:]+): (.+)$/s; // file:line: kind name: what
const cap = (x: string) => x[0].toUpperCase() + x.slice(1);

function sortFindings(check: Finding[], quiet: Finding[]) {
  const all = [...check, ...quiet.map((x) => ({ ...x, level: "warn" }))];
  const info = all.filter((c) => c.level === "info");
  const found = all.filter((c) => c.level !== "info");
  const alike: Record<string, Finding[]> = {};
  for (const c of [...found, ...info]) {
    const m = !c.code && c.level !== "error" && SAID.exec(c.message);
    if (m) {
      c.where = m[1] || "";
      c.about = `${m[2]}.${m[3]}`;
      (alike[`${c.level}\n${m[4]}`] ||= []).push(c);
    }
  }
  const kinds: Kind[] = [
    ...Object.entries(FINDING_KINDS).map(([code, k]) => ({ ...k, code, rows: found.filter((c) => c.code === code).sort(k.worst) })),
    ...Object.entries(alike)
      .filter(([, cs]) => cs.length > 1)
      .map(([key, cs]) => {
        const what = key.split("\n")[1];
        return {
          title: cap(what.split(/[,:(]/)[0]),
          advice: `${cap(what)}.`,
          code: "alike",
          rows: cs,
          cols: [{ key: "where", header: "where", className: "mono small", render: (c: Finding) => c.where }],
        };
      }),
  ].filter((k) => k.rows.length);
  const grouped = (c: Finding) => kinds.some((k) => k.rows.includes(c));
  return { found, info, kinds, one: found.filter((c) => !grouped(c)), notes: info.filter((c) => !grouped(c)) };
}

export default function CheckPage() {
  const { status } = useStatus();
  const exercised = useApi<Finding[]>("exercised");
  const coherence = useApi<any>("coherence", {}, { every: 30000 });
  if (!status) return <Page title="Check"><p className="muted">Loading…</p></Page>;

  const { found, kinds, one, notes } = sortFindings((status.check as Finding[]) || [], exercised.data || []);
  const errors = found.filter((c) => c.level === "error").length;
  const warnings = found.length - errors;
  const words = [errors ? `${errors} error${errors > 1 ? "s" : ""}` : "", warnings ? `${warnings} warning${warnings > 1 ? "s" : ""}` : ""].filter(Boolean);
  const coh = coherence.data;

  return (
    <Page title={words.length ? `Check: ${words.join(", ")}` : "The model is whole"}>
      {one.length > 0 && (
        <div className="att">
          {one.map((c, i) => (
            <div key={i}>
              <b className={c.level === "error" ? "lvl-error" : "lvl-warning"}>{c.level === "error" ? "Error" : "Warning"}</b> {op(c.message)}
            </div>
          ))}
        </div>
      )}
      {kinds.map((k, ki) => {
        const word = k.rows[0].level === "info" ? "note" : "warning";
        return (
          <Fragment key={ki}>
            <h3>
              {k.title}
              <span className={word === "note" ? "muted" : "lvl-warning"}>{` · ${k.rows.length} ${word}s`}</span>
            </h3>
            <p>{k.advice}</p>
            <DataTable
              caption={`fit findings ${k.code}`}
              className={`fit findings ${k.code}`}
              columns={[{ key: "part", header: "part", render: (c) => (c.about ? <PartLink about={c.about} /> : c.ref ?? "") }, ...k.cols]}
              rows={k.rows}
              rowKey={(c, i) => `${c.about ?? c.ref ?? ""}${i}`}
            />
          </Fragment>
        );
      })}
      {notes.length > 0 && (
        <>
          <h3>Notes</h3>
          <ul className="extremes-status">
            {notes.map((c, i) => <li key={i}>{op(c.message)}</li>)}
          </ul>
        </>
      )}
      {coh && Object.keys(coh.kinds || {}).length > 0 && <Coherence coh={coh} />}
      <Section title="Counts">
        <dl className="counts">
          {Object.entries(status.counts || {}).map(([k, v]) => (
            <Fragment key={k}>
              <dt>{k}</dt>
              <dd>{fmt(v)}</dd>
            </Fragment>
          ))}
        </dl>
      </Section>
    </Page>
  );
}

/* Coherence: each kind's score (agreements of comparisons, or the record it still needs), then each mismatch grouped
   by the pair of views that disagrees, with its file and line, its fix and the check findings it is linked to */
function Coherence({ coh }: { coh: any }) {
  const finds: any[] = coh.findings || [];
  const pairs: ReactNode[] = [];
  for (const [pair, title] of Object.entries<string>(coh.pairs || {})) {
    const mine = finds.filter((f) => f.pair === pair);
    if (!mine.length) continue;
    const bad = mine.filter((f) => f.level === "mismatch").length;
    pairs.push(
      <Fragment key={pair}>
        <h3>
          {title}
          <span className="muted">{bad ? ` ${bad} mismatch${bad > 1 ? "es" : ""}` : " notes only"}</span>
        </h3>
        <div className="att">
          {mine.map((f, i) => (
            <div key={i} className={f.level === "note" ? "muted" : undefined}>
              <b className={f.level === "note" ? undefined : "lvl-warning"}>{f.code}</b>{" "}
              {f.file && <span className="muted">{`${f.file.split("/").pop()}:${f.line} `}</span>}
              {op(f.message)}
              {f.fix && <div className="note">Fix: {op(f.fix)}</div>}
              {f.links?.length > 0 && <div className="note">See: {f.links.join(", ")}</div>}
            </div>
          ))}
        </div>
      </Fragment>,
    );
  }
  return (
    <section className="coherence">
      <h2>
        Coherence<span className="muted"> the Process, Dynamics and Blocks views held against each other, over the record</span>
      </h2>
      <ul className="coh-scores">
        {Object.entries<any>(coh.kinds).map(([k, x]) => {
          const all = x.compared && x.agree === x.compared;
          const cls = x.compared ? (all ? "s-holding" : "s-open") : "muted";
          return (
            <li key={k}>
              <b>{k}</b> {x.compared ? <span className={cls}>{`${x.agree} of ${x.compared} agree`}</span> : ""}
              {x.needs && <span className="muted">{`${x.compared ? "; the record not compared yet: " : ""}needs ${x.needs}`}</span>}
            </li>
          );
        })}
      </ul>
      {pairs}
    </section>
  );
}
