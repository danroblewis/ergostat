import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { QueryEditor } from "../../../components/query";
import { useSend } from "../../../hooks/useSend";
import { keptGet, keptSet, stepsKey } from "../../../lib/kept";
import * as D from "./draft";
import { KindsStep, type Suggestions } from "./KindsStep";
import { MappingStep, type MappingEdits } from "./MappingStep";
import { QueryStep, SPANS } from "./QueryStep";
import { ReviewStep, SidePanel, unexplained } from "./ReviewStep";
import { KeySide, WhatStep } from "./WhatStep";
import { n, Step, type QEvent } from "./common";
import { liveOf, noKeyOf, openFirst, refusedOf, splitOf, type Live, type Opened } from "./opened";
import "./workbench.css";

/* The projection workbench (docs/roadmap/projection-workbench.md; SPEC §5a, *The workbench*), the projection's page in
   edit mode: a loop the user goes round until nothing is unexplained, then saves. Five steps in the main column, an
   accordion, one open at a time, each closed one saying its state on its header (0 schema: its fields; 1 the query;
   2 the kinds of event; 3 the mapping; 4 the review), what is still unexplained kept
   in sight above them, and on the right a panel of its own (its key, the fields' distributions and the lifecycles, its
   samples (its objects) one at a time with their record and change history, the residual at the bottom); the YAML (WorkbenchYaml)
   at the very bottom of the page. The YAML is the one thing edited: a step's edit rewrites
   it (draft.ts), and the YAML typed is read back into the steps; while it does not parse, the steps keep what they
   last showed and change nothing. A new projection opens on its steps from the first; one that exists opens on its
   review, so what drifted shows. Which step is open, the span and the object shown are kept for the tab with the
   draft (lib/kept.ts, ProjectionPage.tsx). */

/** The YAML, the one thing edited: drawn at the very bottom of the page while editing (ProjectionPage.tsx), below
 *  the steps and the page's own panels. */
export function WorkbenchYaml({ text, setText, problems }: {
  text: string; setText: (t: string) => void; problems?: { line?: number | null; message: string }[];
}) {
  const parsed = useMemo(() => D.read(text), [text]);
  return (
    <section className="wb-yaml" aria-label="The projection's YAML">
      <h2 className="small">Its YAML</h2>
      <QueryEditor source="yaml" value={text} onChange={(t) => setText(t)} label="The projection's definition (YAML)" problems={problems} />
      {"error" in parsed && <p className="note lvl-error" role="alert">The YAML does not parse ({parsed.error}): the steps show it as it last parsed.</p>}
      <p className="muted small">The steps write it; what you type here is read back into them. Save writes it to the model.</p>
    </section>
  );
}

export function Workbench({ name, system, text, setText, creating }: {
  name: string; system: string; text: string; setText: (t: string | ((was: string) => string)) => void; creating: boolean;
}) {
  const parsed = useMemo(() => D.read(text), [text]);
  const [good, setGood] = useState<D.Draft | null>(null);
  useEffect(() => { if ("draft" in parsed) setGood(parsed.draft); }, [parsed]);
  const draft = "draft" in parsed ? parsed.draft
    : good ?? { query: "", key: [], name: "", time: "", ignore: [], fields: [], kinds: [] };
  const editable = "draft" in parsed;
  // an edit applies to the text as it is by then: several made at once (kinds mapped the same way) all land
  const change = (f: (t: string) => string) => { if (editable) setText(f); };

  const sk = stepsKey(system, name);
  const [kept] = useState(() => keptGet<{ step?: number | null; since?: string; item?: string }>(sk));
  const [since, setSince] = useState(kept?.since ?? "");
  const [item, setItem] = useState(kept?.item ?? "");
  // an accordion: one step open at a time (0 schema … 4 review), opening one closes the others; none open is allowed
  const [step, setStep] = useState<number | null>(() => (kept && "step" in kept ? kept.step ?? null : creating ? 0 : 4));
  useEffect(() => keptSet(sk, { step, since, item }), [sk, step, since, item]);
  const toggle = (k: number) => setStep((s) => (s === k ? null : k));

  const reviewBody = useMemo(() => (editable ? { name, yaml: text, system: system || undefined, since: since || undefined, item: item || undefined } : null),
    [editable, name, text, system, since, item]);
  const review = useSend<any>("projections/review", reviewBody, 600);
  const r = review.data;
  const left = r?.ok ? unexplained(r) : [];

  // a residual group opened in the mapping step (opened.tsx): followed through each review until it is fixed; a review
  // of a draft that does not check (or none yet) leaves it as it last was
  const [opened, setOpened] = useState<Opened | null>(null);
  const tokens = useRef(0);
  const lastLive = useRef<Live | null>(null);
  const live = useMemo(() => (opened ? (r?.ok ? liveOf(r, opened) : lastLive.current) : null), [r, opened]);
  lastLive.current = live;
  const openGroup = (o: Opened | null) => {
    if (!o) return;
    setOpened(o);
    setStep(3);
  };
  const token = () => ++tokens.current;
  const openPart = (w: string) => {
    if (w === "remainder") {
      setStep(2);
      window.setTimeout(() => document.getElementById("wb-kinds-h")?.scrollIntoView({ block: "start", behavior: "smooth" }), 50);
      return;
    }
    const what = w === "no key" ? "no_key" : w === "refused" ? "refused" : w === "possible splits" ? "split" : null;
    if (what) openGroup(openFirst(r, what, token()));
  };
  const opens = (w: string) => ["remainder", "no key", "refused", "possible splits"].includes(w);
  const onOpen = (what: "no_key" | "refused" | "split", g: any) =>
    openGroup(what === "no_key" ? noKeyOf(g, token()) : what === "refused" ? refusedOf(g, token()) : splitOf(g, token()));

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
    addField: (f, type) => change((t) => D.addField(t, f, type)),
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
            : <><span className="lvl-warn">Unexplained:</span> {left.map(([w, c], i) => (
              <span key={w}>{i > 0 && " · "}{opens(w)
                ? <button type="button" className="ghost" title="Open these events to map them" onClick={() => openPart(w)}>{n(c)} {w}</button>
                : `${n(c)} ${w}`}</span>
            ))}</>}
          {since && <span className="muted small"> (over {SPANS.find((s) => s.value === since)?.label})</span>}
        </p>
        <Step no={0} id="wb-what" title="Schema" open={step === 0} onToggle={() => toggle(0)}
          said={`${draft.fields.length} field${draft.fields.length === 1 ? "" : "s"}, keyed by ${draft.key.join(" / ") || "the events' key"}`}>
          <WhatStep draft={draft} ed={ed} editable={editable} />
        </Step>
        <Step no={1} id="wb-query" title="Query" open={step === 1} onToggle={() => toggle(1)}
          said={draft.query ? <code>{draft.query.length > 70 ? draft.query.slice(0, 69) + "…" : draft.query}</code> : "which events it reads"}>
          <QueryStep query={draft.query} onQuery={(q) => change((t) => D.setTop(t, "query", q))} since={since} onSince={setSince} editable={editable}
            sugg={sugg.data} kinds={draft.kinds.length} onAccept={accept} />
        </Step>
        <Step no={2} id="wb-kinds" title="Kinds of event" open={step === 2} onToggle={() => toggle(2)}
          said={`${draft.kinds.length} kind${draft.kinds.length === 1 ? "" : "s"}${r?.ok && r.residual.remainder.count ? `, ${n(r.residual.remainder.count)} events not taken` : ""}`}>
          <KindsStep draft={draft} review={r?.ok ? r : null} sugg={sugg} editable={editable} onAdd={accept}
            onRename={(a, b) => change((t) => D.renameKind(t, a, b))}
            onWhen={(k, w) => change((t) => D.setKind(t, k, "when", w))}
            onRemove={(k) => change((t) => D.removeKind(t, k))} />
        </Step>
        <Step no={3} id="wb-mapping" title="Mapping" open={step === 3} onToggle={() => toggle(3)}
          said={nUnmapped ? `${n(nUnmapped)} path${nUnmapped === 1 ? "" : "s"} left to decide` : undefined}>
          <MappingStep draft={draft} ed={ed} editable={editable} fold={fold}
            opened={opened ? { o: opened, live, onUsual: () => setOpened(null) } : null} />
        </Step>
        <Step no={4} id="wb-review" title="Review" open={step === 4} onToggle={() => toggle(4)}
          said={r?.ok ? `${n(r.objects.count)} objects` : undefined}>
          <ReviewStep r={r} error={review.error} busy={review.busy} onIgnore={ignore} editable={editable} />
        </Step>
      </div>
      <aside className="wb-side" aria-label="The draft's objects">
        <SidePanel r={r} item={item} onItem={setItem} onOpen={onOpen} keyPart={<KeySide draft={draft} ed={ed} editable={editable} />} />
      </aside>
    </section>
  );
}
