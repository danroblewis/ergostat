import { ErrorNote, Loading, Page } from "../../components";
import { usePanelApi } from "../../components/panels/usePanelApi";
import ProjectionPage from "./ProjectionPage";

/* /?workbench=NAME&proposal=ID: a projection a model change drafts (the modelling subsystem's drafter, SPEC §12e),
   opened in the workbench with the draft loaded (GET /api/proposal-draft): the owner edits it there and saves it, or
   accepts the change as it is from the inbox. A projection not yet in the model opens as a new one. */
export default function ProposedProjection({ name, proposal }: { name: string; proposal: string }) {
  const got = usePanelApi<any>("proposal-draft", { id: proposal, name }, null);
  if (got.error) return <Page title={name}><ErrorNote error={`No drafted projection ${name} in change ${proposal}.`} /></Page>;
  if (!got.data) return <Loading />;
  return (
    <>
      <p className="muted small" data-testid="proposed-draft">
        The draft of change {proposal}{got.data.state ? ` (${got.data.state})` : ""}
        {got.data.verdict ? `: ${got.data.verdict}` : ""}. Edit it here and save it, or accept the change as it is.
      </p>
      <ProjectionPage key={`proposed:${proposal}:${name}`} projection={got.data.name} creating={!got.data.exists}
        proposed={got.data.yaml} />
    </>
  );
}
