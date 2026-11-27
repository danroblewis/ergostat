import { GoalDetail, Page } from "../../components";

/* A goal's own address (/goals/NAME, /SYSTEM/goals/NAME, in the top-most scope that contains it): its detail, as the
   Goals page shows it beside the list. */
export default function GoalPage({ name }: { name: string }) {
  return (
    <Page title={name} className="goal-page">
      <GoalDetail name={name} />
    </Page>
  );
}
