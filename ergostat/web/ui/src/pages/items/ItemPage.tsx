import { AppLink, Page } from "../../components";
import { EditableDashboard, useEditing } from "../../components/panels/EditableDashboard";
import { SharedAnswers } from "../../components/panels/shared";
import { usePanelApi } from "../../components/panels/usePanelApi";
import { ITEM_PANELS as PANELS } from "../../lib/pages";
import { dashboardHref, eventsHref, itemHref } from "../../lib/hrefs";
import { knownProjections } from "../../lib/routes";

/* /item/ID, a dashboard made in advance (lib/pages.ts ITEM_PANELS): its panels are why it is not done (a line, while
   something known holds it), its projection, state, age and what it belongs to; its states over time; its numbers over
   time; its events over time; its relations both ways; its fields; and its history (each event with what it changed).
   The page asks the item's answer once, its fields' changes with it, and hands it to every panel; a part with nothing
   to say is not drawn. Under a
   projection's address, edited in place, it is saved as the projection's show dashboard (`dashboards: show:`), drawn
   for each of its items in place of this one. */

const BASE = { title: "", panels: PANELS };


export default function ItemPage({ id, projection }: { id: string; projection?: string }) {
  const asked = { ...(projection ? { projection } : {}), history: "all" };   // (its history's changes, and its charts')
  const item = usePanelApi<any>(`items/${encodeURIComponent(id)}`, asked, 4000);
  const ed = useEditing({ base: BASE, target: projection ? { projection, role: "show" } : null,
    bind: { item: id, ...(projection ? { projection } : {}) } });
  return (
    <Page title={item.data?.name || id}>
      {item.data?.name && <p className="muted small item-key" data-testid="item-key">{id}</p>}
      <div className="page-edit">{ed.bar}</div>
      {item.error && !item.data ? (
        <p className="muted">Nothing is recorded about this id.</p>
      ) : (
        <SharedAnswers answers={[{ path: `items/${encodeURIComponent(id)}`, params: asked, state: item }]}>
          {item.data && !item.data.projection_of && id.includes("/") && <Unmodelled id={id} />}
          {item.data && !projection && (item.data.projections || []).length > 1 && <SeenBy id={id} d={item.data} />}
          {item.data?.fields?.drafted && typeof item.data.fields.drafted === "object" && <Drafted id={id} drafted={item.data.fields.drafted} />}
          {item.data?.projection === UNEXPLAINED && <Unexplained f={item.data.fields || {}} />}
          <EditableDashboard ed={ed} />
        </SharedAnswers>
      )}
    </Page>
  );
}

/** A model change that drafts projections (the modelling subsystem's drafter, SPEC §12e): each opened in the workbench
 *  with the draft loaded (/?workbench=NAME&proposal=ID), to edit before saving, or accepted as it is. */
function Drafted({ id, drafted }: { id: string; drafted: Record<string, string> }) {
  const pid = id.slice(id.indexOf("/") + 1);
  return (
    <div className="unmodelled-note" role="note" data-testid="drafted">
      <p>This change drafts {Object.keys(drafted).length === 1 ? "a projection" : "projections"}:{" "}
        {Object.keys(drafted).map((n, i) => (
          <span key={n}>{i ? ", " : ""}<AppLink to={`/?workbench=${encodeURIComponent(n)}&proposal=${encodeURIComponent(pid)}`}>
            open {n} in the workbench</AppLink></span>
        ))}{" "}(edit it there before saving, or accept the change as it is).</p>
    </div>
  );
}

const UNEXPLAINED = "ergostat.unexplained";

/** A literal of the event query (the workbench's language): quoted as written, or as JSON when it holds a quote. */
const lit = (v: unknown) => { const t = String(v ?? ""); return /['\\]/.test(t) ? JSON.stringify(t) : `'${t}'`; };

/** The event query of a group of unexplained events: its source and type. */
export const groupQuery = (f: Record<string, any>) => `source == ${lit(f.source)} and type == ${lit(f.type)}`;

/** A group of the events no projection takes (the built-in ergostat.unexplained, SPEC §12e): its events on the Events
 *  dashboard (q=: by its source and type; the unexplained ones alone with unexplained()), the change that drafts a
 *  projection for it (opened in the workbench), and its examples, shown whole. Its modelling request is bookkeeping:
 *  never linked, the group is the one thing the owner watches. */
function Unexplained({ f }: { f: Record<string, any> }) {
  const q = groupQuery(f);
  const pid = typeof f.change === "string" ? f.change.slice(f.change.indexOf("/") + 1) : "";
  return (
    <div className="unmodelled-note" role="note" data-testid="unexplained">
      <p>
        <AppLink to={eventsHref("q=" + encodeURIComponent(q))}>all its events</AppLink>
        {" · "}<AppLink to={eventsHref("q=" + encodeURIComponent(`${q} and unexplained()`))}>the unexplained ones</AppLink>
        {f.shape ? <span className="muted"> (shaped {"{"}{f.shape}{"}"})</span> : null}

        {f.change && <>{" · "}<AppLink to={itemHref(f.change)}>its draft{f.round > 1 ? ` (round ${f.round})` : ""}</AppLink></>}
        {f.state === "waiting" && <>{" · "}<AppLink to={dashboardHref("inbox")}>it waits for you in the Inbox</AppLink></>}
        {f.state === "waiting" && pid && (f.drafts || []).map((n: string) => (
          <span key={n}>{" · "}<AppLink to={`/?workbench=${encodeURIComponent(n)}&proposal=${encodeURIComponent(pid)}`}>
            Open {n} in the workbench</AppLink></span>
        ))}
      </p>
      {(f.why || f.latest) && <p className="muted small">{f.state}: {f.why || f.latest}</p>}
      {(f.examples || []).length > 0 && (
        <details open>
          <summary>Its newest {f.examples.length === 1 ? "event" : `${f.examples.length} events`}, whole</summary>
          {(f.examples as string[]).map((e) => <Example key={e} id={e} />)}
        </details>
      )}
    </div>
  );
}

function Example({ id }: { id: string }) {
  const got = usePanelApi<any>(`events/${encodeURIComponent(id)}`, {}, null);
  return <pre className="small" data-testid="unexplained-example">{got.data ? JSON.stringify(got.data, null, 2) : id}</pre>;
}

/** An id several projections see (/item/ID): an item of each, each at its projection's address; this page shows the
 *  first's (its answer names it, ``projection``). */
function SeenBy({ id, d }: { id: string; d: any }) {
  return (
    <div className="unmodelled-note" role="note">
      <p>{d.projections.length} projections see {id}, each folding its events its own way:{" "}
        {d.projections.map((k: string, n: number) => (
          <span key={k}>{n ? ", " : ""}<AppLink to={itemHref(id, undefined, k)}>{k}</AppLink>{k === d.projection ? " (shown here)" : ""}</span>
        ))}.</p>
    </div>
  );
}

/** An id no projection of the model matches: its events are on the record, but the model does not say what they are.
 *  Says so, and the projection that would take it in (its id's first part, PREFIX/*), as YAML to add. */
function Unmodelled({ id }: { id: string }) {
  const prefix = id.includes("/") ? id.slice(0, id.indexOf("/")) : id;
  const name = prefix.toLowerCase().replace(/[^a-z0-9-]+/g, "-").replace(/^-+|-+$/g, "") || "thing";
  const own = knownProjections().filter((p) => p.declared);
  return (
    <div className="unmodelled-note" role="note">
      <p><b className="lvl-warn">Not in the model.</b> No projection matches {id}
        {own.length ? <> (the model's: {own.map((p) => `${p.name} matches ${p.id}`).join(", ")})</> : null}.
        {" "}Its events are on the record; this page folds them as they are. To model it, add a projection:</p>
      <pre>{`projections:\n  ${name}:\n    query: key.startswith('${prefix}/')`}</pre>
    </div>
  );
}
