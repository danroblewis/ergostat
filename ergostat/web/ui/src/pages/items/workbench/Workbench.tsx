import { useEffect, useMemo, useState } from "react";
import { QueryEditor } from "../../../components/query";
import { useSend } from "../../../hooks/useSend";
import * as D from "./draft";
import { KindsStep } from "./KindsStep";
import { MappingStep, type MappingEdits } from "./MappingStep";
import { QueryStep, SPANS } from "./QueryStep";
import { ReviewStep, unexplained } from "./ReviewStep";
import { n, Step } from "./common";
import "./workbench.css";

/* The projection workbench (docs/roadmap/projection-workbench.md; SPEC §5a, *The workbench*), the projection's page in
   edit mode: a loop the user goes round until nothing is unexplained, then saves. Four steps in a column (the query,
   the kinds of event, the mapping, the review), what is still unexplained kept in sight above them, and the YAML
   beside them, the one thing edited: a step's edit rewrites the YAML (draft.ts), and the YAML typed is read back into
   the steps; while it does not parse, the steps keep what they last showed and change nothing. A new projection opens
   on its steps from the first; one that exists opens on its review, so what drifted shows. */

export function Workbench({ name, system, text, setText, creating, problems }: {
  name: string; system: string; text: string; setText: (t: string) => void; creating: boolean;
  problems?: { line?: number | null; message: string }[];
}) {
  const parsed = useMemo(() => D.read(text), [text]);
  const [good, setGood] = useState<D.Draft | null>(null);
  useEffect(() => { if ("draft" in parsed) setGood(parsed.draft); }, [parsed]);
  const draft = "draft" in parsed ? parsed.draft : good ?? { query: "", key: "", keyParts: [], time: "", fields: [], kinds: [] };
  const editable = "draft" in parsed;
  const change = (f: (t: string) => string) => { if (editable) setText(f(text)); };

  const [since, setSince] = useState("");
  const [item, setItem] = useState("");
  const [open, setOpen] = useState<Set<number>>(() => new Set(creating ? [1, 2, 3, 4] : [4]));
  const toggle = (k: number) => setOpen((s) => { const x = new Set(s); if (x.has(k)) x.delete(k); else x.add(k); return x; });

  const reviewBody = useMemo(() => (editable ? { name, yaml: text, system: system || undefined, since: since || undefined, item: item || undefined } : null),
    [editable, name, text, system, since, item]);
  const review = useSend<any>("projections/review", reviewBody, 600);
  const r = review.data;
  const left = r?.ok ? unexplained(r) : [];

  const ed: MappingEdits = {
    setTop: (k, v) => change((t) => D.setTop(t, k, v)),
    addField: (f) => change((t) => D.addField(t, f)),
    setField: (f, part, v) => change((t) => D.setField(t, f, part, v)),
    renameField: (a, b) => change((t) => D.renameField(t, a, b)),
    removeField: (f) => change((t) => D.removeField(t, f)),
    setKind: (k, e, v) => change((t) => D.setKind(t, k, e, v)),
    setKeyParts: (parts) => change((t) => D.setKeyParts(t, parts)),
    setKindKeyParts: (k, parts) => change((t) => D.setKindKeyParts(t, k, parts)),
  };

  return (
    <section className="wb" aria-label="The projection workbench">
      <div className="wb-steps">
        <p className="wb-setpoint" aria-live="polite" data-testid="unexplained">
          {!r ? <span className="muted">{review.busy ? "Reviewing…" : "Not reviewed yet."}</span>
            : !r.ok ? <span className="lvl-error">The draft does not check: see the review.</span>
            : left.length === 0 ? <strong>Nothing unexplained.</strong>
            : <><span className="lvl-warn">Unexplained:</span> {left.map(([w, c]) => `${n(c)} ${w}`).join(" · ")}</>}
          {since && <span className="muted small"> (over {SPANS.find((s) => s.value === since)?.label})</span>}
        </p>
        <Step no={1} id="wb-query" title="Query" open={open.has(1)} onToggle={() => toggle(1)}
          said={draft.query ? <code>{draft.query.length > 70 ? draft.query.slice(0, 69) + "…" : draft.query}</code> : "which events it reads"}>
          <QueryStep query={draft.query} onQuery={(q) => change((t) => D.setTop(t, "query", q))} since={since} onSince={setSince} editable={editable} />
        </Step>
        <Step no={2} id="wb-kinds" title="Kinds of event" open={open.has(2)} onToggle={() => toggle(2)}
          said={`${draft.kinds.length} kind${draft.kinds.length === 1 ? "" : "s"}${r?.ok ? `, ${n(r.residual.remainder.count)} in the remainder` : ""}`}>
          <KindsStep draft={draft} since={since} review={r?.ok ? r : null} editable={editable}
            onAdd={(ks) => change((t) => ks.reduce((x, k) => D.addKind(x, k.name, k.when), t))}
            onRename={(a, b) => change((t) => D.renameKind(t, a, b))}
            onWhen={(k, w) => change((t) => D.setKind(t, k, "when", w))}
            onRemove={(k) => change((t) => D.removeKind(t, k))} />
        </Step>
        <Step no={3} id="wb-mapping" title="Mapping" open={open.has(3)} onToggle={() => toggle(3)}
          said={`${draft.fields.length} field${draft.fields.length === 1 ? "" : "s"}`}>
          <MappingStep draft={draft} ed={ed} editable={editable} />
        </Step>
        <Step no={4} id="wb-review" title="Review" open={open.has(4)} onToggle={() => toggle(4)}
          said={r?.ok ? `${n(r.objects.count)} objects` : undefined}>
          <ReviewStep r={r} error={review.error} busy={review.busy} item={item} onItem={setItem} />
        </Step>
      </div>
      <div className="wb-yaml">
        <h2 className="small">Definition</h2>
        <QueryEditor source="yaml" value={text} onChange={setText} label="The projection's definition (YAML)" problems={problems} />
        {"error" in parsed && <p className="note lvl-error" role="alert">The YAML does not parse ({parsed.error}): the steps show it as it last parsed.</p>}
        <p className="muted small">The steps write it; what you type here is read back into them. Save writes it to the model.</p>
      </div>
    </section>
  );
}
