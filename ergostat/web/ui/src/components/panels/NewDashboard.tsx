import { Page } from "../ui";
import { EditableDashboard, useEditing } from "./EditableDashboard";

/* A new dashboard (the nav bar's +): empty, edited from the first; Save asks its name and writes it under `dashboards:`
   with `nav: true` in the system whose nav bar made it (its file; the main file for the top level), so it is in that
   nav bar at /SYSTEM/NAME (/NAME). Nothing is kept until then. */
export default function NewDashboard({ system = "", onSaved, onCancel }: {
  system?: string; onSaved: (name: string) => void; onCancel: () => void;
}) {
  const ed = useEditing({ base: { title: "New dashboard", panels: [] }, target: { name: "", new: true, system }, start: true,
    bind: { system }, onDone: (name) => onSaved(name), onCancel });
  return (
    <Page title="New dashboard" className="dash" actions={<span className="dash-actions">{ed.bar}</span>}>
      <EditableDashboard ed={ed} />
    </Page>
  );
}
