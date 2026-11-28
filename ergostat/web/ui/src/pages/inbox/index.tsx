import { Muted, Page } from "../../components";
import { EditableDashboard, useEditing } from "../../components/panels/EditableDashboard";
import { pageDashboard } from "../../lib/pages";
import { useStatus, waitsOnYou } from "../../state/status";

/* The Inbox (/inbox, /SYSTEM/inbox), a dashboard made in advance (lib/pages.ts): the decisions panel
   (panels/kinds/attention.tsx), every entry `ergostat inbox` lists, each answered on its card (POST /api/inbox/ID/VERB).
   Faults (a sensor failing, a daemon down) are not decisions and are not here. Edited in place, it is saved as the
   dashboard named inbox of that system, drawn here in place of this page. */

const BASE = pageDashboard("inbox");

const EVERY = 5000;

export default function InboxPage({ system = "" }: { system?: string }) {
  const { status } = useStatus();
  const ed = useEditing({ base: BASE, target: { name: "inbox", system }, bind: { system } });
  const n = (status?.attention || []).filter(waitsOnYou).length;
  return (
    <Page title={<>Inbox{status && <Muted>{` · ${n} waiting for you`}</Muted>}</>}>
      <div className="page-edit">{ed.bar}</div>
      <EditableDashboard ed={ed} every={EVERY} />
    </Page>
  );
}
