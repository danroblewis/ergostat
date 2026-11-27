import { useState } from "react";
import { AppLink, Page } from "../../components";
import { EditableDashboard, useEditing } from "../../components/panels/EditableDashboard";
import { SharedAnswers } from "../../components/panels/shared";
import { usePanelApi } from "../../components/panels/usePanelApi";
import { ITEM_PANELS as PANELS } from "../../lib/pages";
import { itemHref } from "../../lib/hrefs";
import { knownProjections } from "../../lib/routes";

/* /item/ID, a dashboard made in advance (pages.js pageItem): its panels are why it is not done, its projection, state, age
   and events; the path it took through its states; its relations both ways; its fields; what was refused; how it
   moved; its events; and each field's changes, asked for when the Changes fold is opened (or a field's "N changes").
   The page asks the item's answer once and hands it to every panel; a part with nothing to say is not drawn. Under a
   projection's address, edited in place, it is saved as the projection's show dashboard (`dashboards: show:`), drawn
   for each of its items in place of this one. */

const BASE = { title: "", panels: PANELS };


export default function ItemPage({ id, projection }: { id: string; projection?: string }) {
  const [changesOf, setChangesOf] = useState<string | null>(null);   // null: Changes folded; "": every field's
  const asked = { ...(projection ? { projection } : {}), ...(changesOf != null ? { history: changesOf || "all" } : {}) };
  const item = usePanelApi<any>(`items/${encodeURIComponent(id)}`, asked, 4000);
  const onParams = (c: Record<string, string | number | null>) => {
    if (!("history" in c)) return;
    setChangesOf(c.history == null ? null : c.history === "all" ? "" : String(c.history));
  };
  const ed = useEditing({ base: BASE, target: projection ? { projection, role: "show" } : null,
    bind: { item: id, ...(projection ? { projection } : {}) } });
  const decorate = (d: any) => ({ ...d, onParams,
    ...(d.panel === "item-changes" ? { history: changesOf == null ? undefined : changesOf || "all" } : {}) });
  return (
    <Page title={id}>
      <div className="page-edit">{ed.bar}</div>
      {item.error && !item.data ? (
        <p className="muted">Nothing is recorded about this id.</p>
      ) : (
        <SharedAnswers answers={[{ path: `items/${encodeURIComponent(id)}`, params: asked, state: item }]}>
          {item.data && !item.data.projection_of && id.includes("/") && <Unmodelled id={id} />}
          {item.data && !projection && (item.data.projections || []).length > 1 && <SeenBy id={id} d={item.data} />}
          <EditableDashboard ed={ed} decorate={decorate} />
        </SharedAnswers>
      )}
    </Page>
  );
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
      <pre>{`projections:\n  ${name}:\n    id: ${prefix}/*`}</pre>
    </div>
  );
}
