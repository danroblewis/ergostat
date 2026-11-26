import { useState } from "react";
import { useParams } from "react-router-dom";
import { Page } from "../../components";
import { DashboardView } from "../../components/panels/DashboardView";
import { SharedAnswers } from "../../components/panels/shared";
import { usePanelApi } from "../../components/panels/usePanelApi";
import { ITEM_PANELS as PANELS } from "../../lib/pages";

/* /item/ID, a dashboard made in advance (pages.js pageItem): its panels are why it is not done, its kind, state, age
   and events; the path it took through its states; its relations both ways; its fields; what was refused; how it
   moved; its events; and each field's changes, asked for when the Changes fold is opened (or a field's "N changes").
   The page asks the item's answer once and hands it to every panel; a part with nothing to say is not drawn. */


export default function ItemPage() {
  const { id = "" } = useParams();
  const [changesOf, setChangesOf] = useState<string | null>(null);   // null: Changes folded; "": every field's
  const asked = changesOf != null ? { history: changesOf || "all" } : {};
  const item = usePanelApi<any>(`items/${encodeURIComponent(id)}`, asked, 4000);
  const onParams = (c: Record<string, string | number | null>) => {
    if (!("history" in c)) return;
    setChangesOf(c.history == null ? null : c.history === "all" ? "" : String(c.history));
  };
  const panels = PANELS.map((d) => ({ ...d, item: id, onParams,
    ...(d.panel === "item-changes" ? { history: changesOf == null ? undefined : changesOf || "all" } : {}) }));
  return (
    <Page title={id}>
      {item.error && !item.data ? (
        <p className="muted">Nothing is recorded about this id.</p>
      ) : (
        <SharedAnswers answers={[{ path: `items/${encodeURIComponent(id)}`, params: asked, state: item }]}>
          <DashboardView panels={panels} />
        </SharedAnswers>
      )}
    </Page>
  );
}
