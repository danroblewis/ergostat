import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router-dom";
import { DetailProvider, Loading } from "./components";
import { Shell } from "./components/Shell";
import Resolve from "./Resolve";
import { DashboardsProvider } from "./state/dashboards";
import { StatusProvider } from "./state/status";
import { TimeProvider } from "./state/time";

/* The app: the shell, and every address resolved by what the model names there (Resolve.tsx, lib/routes.ts): its
   dashboards, its projections and their items, then ergostat's own pages. The server answers every path but /api, /static
   and /remote with this page (web/server.py, is_page_path). */

export default function App() {
  return (
    <TimeProvider>
      <StatusProvider>
        <DashboardsProvider>
        <DetailProvider>
          <Shell>
            <Suspense fallback={<Loading />}>
              <Routes>
                <Route path="*" element={<Resolve />} />
              </Routes>
            </Suspense>
          </Shell>
        </DetailProvider>
        </DashboardsProvider>
      </StatusProvider>
    </TimeProvider>
  );
}
