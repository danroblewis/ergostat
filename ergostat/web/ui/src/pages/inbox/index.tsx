import { EditableDashboard, useEditing } from "../../components/panels/EditableDashboard";
import { pageDashboard } from "../../lib/pages";
import type { PanelDef } from "../../components/panels/types";

/* The Inbox (/inbox, /SYSTEM/inbox), a dashboard made in advance (lib/pages.ts): the list page of the built-in
   projection ergostat.inbox, all panels (its summary, the page's heading; its graph of states; its items), each entry
   `ergostat inbox` lists a waiting item drawn as its card, answered there (POST /api/inbox/ID/VERB). Faults (a sensor
   failing, a daemon down) are not decisions and are not here. Edited in place, it is saved as the dashboard named
   inbox of that system, drawn here in place of this page. */

const BASE = pageDashboard("inbox");

const EVERY = 5000;

export default function InboxPage({ system = "" }: { system?: string }) {
  const ed = useEditing({ base: BASE, target: { name: "inbox", system }, bind: { system } });
  const heading = (d: PanelDef): PanelDef => (d.panel === "projection-summary" && d.projection === "ergostat.inbox" ? { ...d, heading: 1 } : d);
  return (
    <div className="page inbox-page">
      {ed.bar && <div className="page-edit">{ed.bar}</div>}
      <EditableDashboard ed={ed} every={EVERY} decorate={heading} />
    </div>
  );
}
