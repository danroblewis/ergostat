import { useCallback, useEffect, useMemo, useState } from "react";
import { QueryEditor } from "../../../components/query";
import { useSend } from "../../../hooks/useSend";
import * as D from "./draft";
import { KindsStep, type Suggestions } from "./KindsStep";
import { MappingStep, type MappingEdits } from "./MappingStep";
import { QueryStep, SPANS } from "./QueryStep";
import { ReviewStep, SidePanel, unexplained } from "./ReviewStep";
import { WhatStep } from "./WhatStep";
import { n, Step, type QEvent } from "./common";
import "./workbench.css";

/* The projection workbench (docs/roadmap/projection-workbench.md; SPEC §5a, *The workbench*), the projection's page in
   edit mode: a loop the user goes round until nothing is unexplained, then saves. Five steps in the main column (what
   it is: its key and fields; the query; the kinds of event; the mapping; the review), what is still unexplained kept
   in sight above them, the YAML below them, and on the right a panel of its own (one object's record and lifespan,
   the residual, the lifecycles, the fields' distributions). The YAML is the one thing edited: a step's edit rewrites
   it (draft.ts), and the YAML typed is read back into the steps; while it does not parse, the steps keep what they
   last showed and change nothing. A new projection opens on its steps from the first; one that exists opens on its
   review, so what drifted shows. */

export function Workbench({ name, system, text, setText, creating, problems }: {
  name: string; system: string; text: string; setText: (t: string) => void; creating: boolean;
  problems?: { line?: number | null; message: string }[];
}) {
  const parsed = useMemo(() => D.read(text), [text]);
  const [good, setGood] = useState<D.Draft | null>(null);
  useEffect(() => { if ("draft" in parsed) setGood(parsed.draft); }, [parsed]);
  const draft = "draft" in parsed ? parsed.draft
    : good ?? { query: "", key: [], time: "", ignore: [], fields: [], kinds: [] };
  const editable = "draft" in parsed;
  const change = (f: (t: string) => string) => { if (editable) setText(f(text)); };

  const [since, setSince] = useState("");
  const [item, setItem] = useState("");
  const [open, setOpen] = useState<Set<number>>(() => new Set(creating ? [1, 2, 3, 4, 5] : [5]));
  const toggle = (k: number) => setOpen((s) => { const x = new Set(s); if (x.has(k)) x.delete(k); else x.add(k); return x; });

  const reviewBody = useMemo(() => (editable ? { name, yaml: text, system: system || undefined, since: since || undefined, item: item || undefined } : null),
    [editable, name, text, system, since, item]);
  const review = useSend<any>("projections/review", reviewBody, 600);
  const r = review.data;
  const left = r?.ok ? unexplained(r) : [];

  // the kinds of event the query's result holds, of the events no accepted kind takes (none that would take nothing)
  const whens = draft.kinds.map((k) => k.when).join("\n");
  const suggBody = useMemo(() => (draft.query.trim()
    ? { query: draft.query, since: since || undefined, taken: whens ? whens.split("\n") : [] } : null), [draft.query, since, whens]);
  const asked = useSend<Suggestions>("events/kinds", suggBody, 600);
  const current = asked.data && asked.data.query === draft.query && (asked.data.taken || []).join("\n") === whens;
  const sugg = { data: current ? asked.data : null, error: asked.error };    // an answer to an earlier draft is not shown
  const accept = (ks: { name: string; when: string }[]) => change((t) => ks.reduce((x, k) => D.addKind(x, k.name, k.when), t));
  const ignore = (p: string) => change((t) => D.setIgnore(t, [...draft.ignore.filter((x) => x !== p), p]));
  const fold = useCallback((evs: QEvent[]) => (editable ? { name, yaml: text, system: system || undefined, events: evs } : null),
    [editable, name, text, system]);

  const ed: MappingEdits = {
    setTop: (k, v) => change((t) => D.setTop(t, k, v)),
    addField: (f) => change((t) => D.addField(t, f)),
    setField: (f, part, v) => change((t) => D.setField(t, f, part, v)),
    renameField: (a, b) => change((t) => D.renameField(t, a, b)),
    removeField: (f) => change((t) => D.removeField(t, f)),
    setKind: (k, e, v) => change((t) => D.setKind(t, k, e, v)),
    setKinds: (k, pairs) => change((t) => pairs.reduce((x, [f, e]) => D.setKind(x, k, f, e), t)),
    createAndMap: (k, f, type, e) => change((t) => D.setKind(D.addField(t, f, type), k, f, e)),
    ignore,
    setKey: (names) => change((t) => D.setKey(t, names)),
  };
  const nUnmapped = r?.ok ? r.unmapped?.count ?? 0 : 0;

  return (
    <section className="wb" aria-label="The projection workbench">
      <div className="wb-main">
        <p className="wb-setpoint" aria-live="polite" data-testid="unexplained">
          {!r ? <span className="muted">{review.busy ? "Reviewing…" : "Not reviewed yet."}</span>
            : !r.ok ? <span className="lvl-error">The draft does not check: see the review.</span>
            : left.length === 0 ? <strong>✓ Nothing unexplained.</strong>
            : <><span className="lvl-warn">Unexplained:</span> {left.map(([w, c]) => `${n(c)} ${w}`).join(" · ")}</>}
          {since && <span className="muted small"> (over {SPANS.find((s) => s.value === since)?.label})</span>}
        </p>
        <Step no={1} id="wb-what" title="What it is" open={open.has(1)} onToggle={() => toggle(1)}
          said={`${draft.fields.length} field${draft.fields.length === 1 ? "" : "s"}, keyed by ${draft.key.join(" / ") || "the events' key"}`}>
          <WhatStep draft={draft} ed={ed} editable={editable} />
        </Step>
        <Step no={2} id="wb-query" title="Query" open={open.has(2)} onToggle={() => toggle(2)}
          said={draft.query ? <code>{draft.query.length > 70 ? draft.query.slice(0, 69) + "…" : draft.query}</code> : "which events it reads"}>
          <QueryStep query={draft.query} onQuery={(q) => change((t) => D.setTop(t, "query", q))} since={since} onSince={setSince} editable={editable}
            sugg={sugg.data} kinds={draft.kinds.length} onAccept={accept} />
        </Step>
        <Step no={3} id="wb-kinds" title="Kinds of event" open={open.has(3)} onToggle={() => toggle(3)}
          said={`${draft.kinds.length} kind${draft.kinds.length === 1 ? "" : "s"}${r?.ok && r.residual.remainder.count ? `, ${n(r.residual.remainder.count)} events not taken` : ""}`}>
          <KindsStep draft={draft} review={r?.ok ? r : null} sugg={sugg} editable={editable} onAdd={accept}
            onRename={(a, b) => change((t) => D.renameKind(t, a, b))}
            onWhen={(k, w) => change((t) => D.setKind(t, k, "when", w))}
            onRemove={(k) => change((t) => D.removeKind(t, k))} />
        </Step>
        <Step no={4} id="wb-mapping" title="Mapping" open={open.has(4)} onToggle={() => toggle(4)}
          said={nUnmapped ? `${n(nUnmapped)} path${nUnmapped === 1 ? "" : "s"} left to decide` : undefined}>
          <MappingStep draft={draft} ed={ed} editable={editable} fold={fold} />
        </Step>
        <Step no={5} id="wb-review" title="Review" open={open.has(5)} onToggle={() => toggle(5)}
          said={r?.ok ? `${n(r.objects.count)} objects` : undefined}>
          <ReviewStep r={r} error={review.error} busy={review.busy} onIgnore={ignore} editable={editable} />
        </Step>
        <div className="wb-yaml">
          <h2 className="small">Definition</h2>
          <QueryEditor source="yaml" value={text} onChange={setText} label="The projection's definition (YAML)" problems={problems} />
          {"error" in parsed && <p className="note lvl-error" role="alert">The YAML does not parse ({parsed.error}): the steps show it as it last parsed.</p>}
          <p className="muted small">The steps write it; what you type here is read back into them. Save writes it to the model.</p>
        </div>
      </div>
      <aside className="wb-side" aria-label="The draft's objects">
        <SidePanel r={r} item={item} onItem={setItem} />
      </aside>
    </section>
  );
}
