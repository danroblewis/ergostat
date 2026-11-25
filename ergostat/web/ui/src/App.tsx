import { lazy, Suspense } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { DetailProvider, Loading } from "./components";
import { Shell } from "./components/Shell";
import { StatusProvider } from "./state/status";
import { TimeProvider } from "./state/time";

/* The app: the shell, and a route for each page. Each page lives in pages/<name>/ and is loaded when first shown.
   The paths are the old page's (/diagram, /items/KIND, /item/ID, /agent/NAME...), served by
   ergostat's server at each of them (web/server.py, UI_PAGES). */

const Diagram = lazy(() => import("./pages/diagram"));
const Dashboard = lazy(() => import("./pages/dashboard"));
const Goals = lazy(() => import("./pages/goals"));
const Agents = lazy(() => import("./pages/agents"));
const Agent = lazy(() => import("./pages/agents/AgentPage"));
const Items = lazy(() => import("./pages/items"));
const Kind = lazy(() => import("./pages/items/KindPage"));
const Item = lazy(() => import("./pages/items/ItemPage"));
const Record = lazy(() => import("./pages/record"));

function KeepQuery({ to }: { to: string }) {
  const { search } = useLocation();
  return <Navigate replace to={to + search} />;
}

export default function App() {
  return (
    <TimeProvider>
      <StatusProvider>
        <DetailProvider>
          <Shell>
            <Suspense fallback={<Loading />}>
              <Routes>
                <Route path="/" element={<KeepQuery to="/diagram" />} />
                <Route path="/diagram" element={<Diagram />} />
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/goals" element={<Goals />} />
                <Route path="/loops" element={<KeepQuery to="/goals" />} />
                <Route path="/agents" element={<Agents />} />
                <Route path="/agent/:name" element={<Agent />} />
                <Route path="/items" element={<Items />} />
                <Route path="/items/:kind" element={<Kind />} />
                <Route path="/item/:id" element={<Item />} />
                <Route path="/record" element={<Record />} />
                <Route path="*" element={<KeepQuery to="/diagram" />} />
              </Routes>
            </Suspense>
          </Shell>
        </DetailProvider>
      </StatusProvider>
    </TimeProvider>
  );
}
