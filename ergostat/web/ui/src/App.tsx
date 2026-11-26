import { lazy, Suspense, type ReactNode } from "react";
import { Navigate, Route, Routes, useLocation, useParams } from "react-router-dom";
import { DetailProvider, Loading } from "./components";
import { InPlace } from "./components/panels/InPlace";
import { Shell } from "./components/Shell";
import { DashboardsProvider } from "./state/dashboards";
import { StatusProvider } from "./state/status";
import { TimeProvider } from "./state/time";

/* The app: the shell, and a route for each page. Each page lives in pages/<name>/ and is loaded when first shown.
   The paths are the old page's (/diagram, /items/KIND, /item/ID, /agent/NAME...), served by
   ergostat's server at each of them (web/server.py, UI_PAGES). A dashboard the model declares with `nav:` is at
   /d/NAME; one declared with `page:` is drawn in that page's place (InPlace), given the address's agent, item or kind. */

const Diagram = lazy(() => import("./pages/diagram"));
const Dashboard = lazy(() => import("./pages/dashboard"));
const Goals = lazy(() => import("./pages/goals"));
const Agents = lazy(() => import("./pages/agents"));
const Agent = lazy(() => import("./pages/agents/AgentPage"));
const Items = lazy(() => import("./pages/items"));
const Kind = lazy(() => import("./pages/items/KindPage"));
const Item = lazy(() => import("./pages/items/ItemPage"));
const Record = lazy(() => import("./pages/record"));
const Named = lazy(() => import("./pages/dashboard/Named"));

/** A page, or the dashboard declared in its place; `word`: the address's part its panels' $WORD stands for. */
function Own({ page, word, param, children }: { page: string; word?: string; param?: string; children: ReactNode }) {
  const p = useParams();
  return <InPlace page={page} bind={word && param && p[param] != null ? { [word]: p[param]! } : undefined}>{children}</InPlace>;
}

function KeepQuery({ to }: { to: string }) {
  const { search } = useLocation();
  return <Navigate replace to={to + search} />;
}

export default function App() {
  return (
    <TimeProvider>
      <StatusProvider>
        <DashboardsProvider>
        <DetailProvider>
          <Shell>
            <Suspense fallback={<Loading />}>
              <Routes>
                <Route path="/" element={<KeepQuery to="/diagram" />} />
                <Route path="/diagram" element={<Diagram />} />
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/d/:name" element={<Named />} />
                <Route path="/goals" element={<Own page="goals"><Goals /></Own>} />
                <Route path="/loops" element={<KeepQuery to="/goals" />} />
                <Route path="/agents" element={<Own page="agents"><Agents /></Own>} />
                <Route path="/agent/:name" element={<Own page="agent" word="agent" param="name"><Agent /></Own>} />
                <Route path="/items" element={<Own page="items"><Items /></Own>} />
                <Route path="/items/:kind" element={<Own page="kind" word="kind" param="kind"><Kind /></Own>} />
                <Route path="/item/:id" element={<Own page="item" word="item" param="id"><Item /></Own>} />
                <Route path="/record" element={<Own page="record"><Record /></Own>} />
                <Route path="*" element={<KeepQuery to="/diagram" />} />
              </Routes>
            </Suspense>
          </Shell>
        </DetailProvider>
        </DashboardsProvider>
      </StatusProvider>
    </TimeProvider>
  );
}
