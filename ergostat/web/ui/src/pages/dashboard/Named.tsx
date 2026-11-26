import { useNavigate, useParams } from "react-router-dom";
import { Button } from "../../components";
import { DeclaredDashboard } from "../../components/panels";
import { useStatus } from "../../state/status";
import { store } from "./lib/draft";

/* A dashboard the model declares, at its own address (/d/NAME): one with `nav:` is linked from the header. Edit a copy
   makes it this browser's draft on the Dashboard page, and Keep puts it back in place. */
export default function NamedDashboard() {
  const { name = "" } = useParams();
  const { status } = useStatus();
  const navigate = useNavigate();
  return (
    <DeclaredDashboard name={name} actions={(d) => (
      <Button disabled={!d || status?.name == null} title="Make a copy of it this browser's draft, to change"
        onClick={() => { if (d && status?.name != null) { store(status.name, { ...d, name: d.name || name }); navigate("/dashboard?edit=1"); } }}>
        Edit a copy
      </Button>
    )} />
  );
}
