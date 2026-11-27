import { Page } from "../ui";
import { EditableDashboard, useEditing } from "./EditableDashboard";

/* A new dashboard (the nav bar's +): empty, edited from the first; Save asks its name and writes it under `dashboards:`
   with `nav: true`, so it is in the nav bar at /NAME. Nothing is kept until then. */
export default function NewDashboard({ onSaved, onCancel }: { onSaved: (name: string) => void; onCancel: () => void }) {
  const ed = useEditing({ base: { title: "New dashboard", panels: [] }, target: { name: "", new: true }, start: true,
    onDone: (name) => onSaved(name), onCancel });
  return (
    <Page title="New dashboard" className="dash" actions={<span className="dash-actions">{ed.bar}</span>}>
      <EditableDashboard ed={ed} />
    </Page>
  );
}
