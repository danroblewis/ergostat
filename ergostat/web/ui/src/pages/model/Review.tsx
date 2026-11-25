import { useState, type ReactNode } from "react";
import { AppLink, Button, Fields, Rich } from "../../components";
import { apiPost, isPublic } from "../../lib/api";
import { dur, fmt, op } from "../../lib/format";

/* One change waiting for review (review.js reviewEntry), in short: what it is, where, who made it and why, how it was
   found, its benefit, its diff; Accept shows the diff and writes it only on a second answer, carrying its hash back;
   Dismiss takes an optional reason. Not ported here: the effect's charts (proposal-effect), the redesign's scorecard
   and "Show on diagram". */

const PART_WORDS: Record<string, string> = { stock: "stock", flow: "flow", auxiliary: "auxiliary", parameter: "parameter", goal: "goal", block: "block" };
const nm = (v: number | null | undefined) => (v == null ? "–" : fmt(v));
const r2s = (v: number | null | undefined) => (v == null ? "–" : v.toFixed(2));

function PartWords({ refs, max = 6 }: { refs: string[]; max?: number }) {
  return (
    <>
      {refs.slice(0, max).map((r, i) => {
        const [k, ...rest] = r.split(".");
        return (
          <span key={r}>
            {i ? ", " : ""}
            <span className="part-ref"><span className="muted">{`${PART_WORDS[k] || k} `}</span>{rest.join(".")}</span>
          </span>
        );
      })}
      {refs.length > max && <span className="muted">{` and ${refs.length - max} more`}</span>}
    </>
  );
}

function Diff({ text }: { text: string }) {
  return (
    <pre className="diff">
      {String(text || "").replace(/\n$/, "").split("\n").map((l, i) => (
        <div
          key={i}
          className={l.startsWith("+++") || l.startsWith("---") || l.startsWith("@@") ? "muted" : l.startsWith("+") ? "add" : l.startsWith("-") ? "del" : undefined}
        >
          {l || " "}
        </div>
      ))}
    </pre>
  );
}

function benefit(b: any): ReactNode[] {
  if (!b) return [];
  const rows: ReactNode[] = [];
  if (b.said) rows.push(<div key="s" className={b.better === false ? "s-open" : undefined}>{`scaled error: ${b.said}`}</div>);
  else if (b.nmse_before != null || b.nmse_after != null)
    rows.push(
      <div key="s">
        {`scaled error ${nm(b.nmse_before)} → ${nm(b.nmse_after)}`}
        <span className="muted">
          {b.nmse_after != null && b.nmse_before != null ? (b.nmse_after < b.nmse_before ? ", better" : b.nmse_after > b.nmse_before ? ", worse" : ", the same") : ""}
        </span>
      </div>,
    );
  for (const x of b.parts || [])
    if (x.r2_before != null || x.r2_after != null)
      rows.push(
        <div key={x.ref} className="small">
          <span className="muted">{`${x.ref.split(".").slice(1).join(".")} `}</span>
          <Rich text={`R² ${r2s(x.r2_before)} → ${r2s(x.r2_after)}`} />
        </div>,
      );
  return rows;
}

export function ReviewEntry({ e, onDone }: { e: any; onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [asking, setAsking] = useState<"accept" | "dismiss" | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState<{ text: string; bad?: boolean } | null>(null);
  const where = e.where || { parts: [], new: [], gone: [], files: [], select: [] };
  const files = e.diff?.files?.length ? e.diff.files.map((f: any) => f.file).join(", ") : "the model";

  async function answer(what: "accept" | "dismiss") {
    setBusy(true);
    setSaid({ text: what === "accept" ? "Writing the change…" : "" });
    try {
      const got = await apiPost(`proposals/${encodeURIComponent(e.id)}/${what}`, what === "accept" ? { expect: e.diff.hash } : { reason });
      setSaid({
        text: what === "accept"
          ? `Accepted: ${files} written.` + (got.applied ? ` Fit in total: scaled error ${nm(got.applied.fit_before?.nmse)} → ${nm(got.applied.fit_after?.nmse)}.` : "")
          : "Dismissed: it is not proposed again unchanged.",
      });
      onDone();
    } catch (err) {
      setSaid({ text: String((err as Error).message || err), bad: true });
      setBusy(false);
    }
  }

  const how = e.how || {};
  const howBits = [how.method || "–", how.span ? `over ${dur(how.span)} of record` : "", how.n ? `${how.n} points` : ""].filter(Boolean).join(", ");
  const ben = benefit(e.benefit);
  const fields = ([
    ["where", (
      <div>
        <div><PartWords refs={where.parts || []} /></div>
        {where.new?.length > 0 && <div className="small muted">new: <PartWords refs={where.new} /></div>}
        {where.gone?.length > 0 && <div className="small muted">removed: <PartWords refs={where.gone} /></div>}
        {where.files?.length > 0 && <div className="small muted mono">{where.files.map((f: any) => `${f.file}:${f.lines.join(",")}`).join("  ")}</div>}
      </div>
    )],
    ["made by", e.by_block
      ? <span className="part-ref"><span className="muted">{`${e.made_by_rung || "block"} `}</span>{e.made_by}{e.confidence != null && <span className="muted small">{` · ${Math.round(e.confidence * 100)}% sure`}</span>}</span>
      : e.made_by === "owner" ? (e.kind === "display" ? "you (Keep, on the Dashboard)" : "you (a what-if)") : null],
    ["why", e.by_block && (e.reasons || []).length
      ? <ul className="plain">{e.reasons.map((r: any, i: number) => <li key={i}>{r.says}{(r.verified || r.evidence || []).map((v: string, j: number) => <div key={j} className="small muted">{v}</div>)}</li>)}</ul>
      : e.why],
    ["judged", e.verdict ? <div className={e.verdict.verdict === "dropped" ? "s-open small" : "small"}>{`${e.verdict.verdict}: ${e.verdict.why}`}</div> : null],
    ["how found", <div><div>{howBits}</div>{how.confidence && <div className="small muted">{how.confidence}</div>}</div>],
    [e.benefit?.better === false ? "effect" : "benefit", ben.length ? <div>{ben}</div> : null],
    ["conflicts", e.conflicts?.length ? <div>{e.conflicts.map((c: any) => <div key={c.id} className="s-open small">{`with ${c.id}: ${c.why}`}</div>)}</div> : null],
  ] as [ReactNode, ReactNode][]).filter(([, v]) => v != null && v !== "");

  return (
    <article className="entry" data-id={e.id} data-kind={e.kind}>
      <h3>{e.what}</h3>
      <p className="entry-change">{op(e.title || "").replaceAll(" * ", " × ")}</p>
      <Fields caption={`The change ${e.id}`} fields={fields} />
      <div className="actions">
        <Button variant="ghost" aria-expanded={open} onClick={() => setOpen(!open)}>{open ? "Hide the diff" : "The diff"}</Button>
        <AppLink className="muted small mono" to={`/item/${encodeURIComponent(`ergostat.model-change/${e.id}`)}`} title="Its item: every event of this change">
          {e.id}
        </AppLink>
      </div>
      {open && (
        <div className="entry-body">
          {!e.simulable && <p className="muted small">{`Not simulated: ${e.not_simulated || "nothing it changes is replayed"}.`}</p>}
          <div className="entry-label">The change</div>
          {e.diff?.error
            ? <p className="s-open small">{`ergostat cannot make this edit (${e.diff.error}); write it by hand.`}</p>
            : <Diff text={e.diff?.unified} />}
        </div>
      )}
      {!isPublic() && !e.diff?.error && (
        <div className="actions">
          <Button disabled={busy} onClick={() => { setOpen(true); setAsking("accept"); }}>Accept</Button>
          <Button variant="ghost" disabled={busy} onClick={() => setAsking("dismiss")}>Dismiss</Button>
        </div>
      )}
      {asking === "accept" && (
        <div className="actions confirm">
          <span className="small">{`This writes exactly the diff above to ${files}.`}</span>
          <Button disabled={busy} onClick={() => answer("accept")}>Write it</Button>
          <Button variant="ghost" disabled={busy} onClick={() => setAsking(null)}>Cancel</Button>
        </div>
      )}
      {asking === "dismiss" && (
        <div className="actions confirm">
          <input
            type="text"
            className="reason"
            placeholder="Why not (optional): remembered with it"
            aria-label="Why not"
            value={reason}
            autoFocus
            onChange={(ev) => setReason(ev.target.value)}
          />
          <Button disabled={busy} onClick={() => answer("dismiss")}>Dismiss it</Button>
          <Button variant="ghost" disabled={busy} onClick={() => setAsking(null)}>Cancel</Button>
        </div>
      )}
      {said && <p className={said.bad ? "s-open small" : "small"}>{said.text}</p>}
    </article>
  );
}
