import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import { lazy, Suspense, type ReactNode } from "react";

import { Spinner } from "./components/ui";
import { AuthProvider, useAuth } from "./state/auth";

// Route-level code splitting: each page ships as its own chunk.
const ComparePage = lazy(() => import("./pages/ComparePage").then((m) => ({ default: m.ComparePage })));
const DatasetsPage = lazy(() => import("./pages/Datasets").then((m) => ({ default: m.DatasetsPage })));
const DatasetDetailPage = lazy(() =>
  import("./pages/DatasetDetail").then((m) => ({ default: m.DatasetDetailPage })),
);
const EvaluatorsPage = lazy(() =>
  import("./pages/Evaluators").then((m) => ({ default: m.EvaluatorsPage })),
);
const ExperimentsPage = lazy(() =>
  import("./pages/Experiments").then((m) => ({ default: m.ExperimentsPage })),
);
const ExperimentDetailPage = lazy(() =>
  import("./pages/ExperimentDetail").then((m) => ({ default: m.ExperimentDetailPage })),
);
const ExperimentComparePage = lazy(() =>
  import("./pages/ExperimentCompare").then((m) => ({ default: m.ExperimentComparePage })),
);
const LandingPage = lazy(() => import("./pages/Landing").then((m) => ({ default: m.LandingPage })));
const LoginPage = lazy(() => import("./pages/Login").then((m) => ({ default: m.LoginPage })));
const ProjectOverviewPage = lazy(() => import("./pages/ProjectOverview").then((m) => ({ default: m.ProjectOverviewPage })));
const ProjectsPage = lazy(() => import("./pages/Projects").then((m) => ({ default: m.ProjectsPage })));
const SettingsPage = lazy(() => import("./pages/Settings").then((m) => ({ default: m.SettingsPage })));
const SharePage = lazy(() => import("./pages/SharePage").then((m) => ({ default: m.SharePage })));
const TraceDetailPage = lazy(() => import("./pages/TraceDetail").then((m) => ({ default: m.TraceDetailPage })));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 5_000, refetchOnWindowFocus: false },
  },
});

function PageFallback() {
  return (
    <div className="grid min-h-screen place-items-center">
      <Spinner />
    </div>
  );
}

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) {
    return (
      <div className="grid min-h-full place-items-center">
        <Spinner />
      </div>
    );
  }
  if (!user) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }
  return <>{children}</>;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Suspense fallback={<PageFallback />}>
          <Routes>
            <Route path="/" element={<LandingPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/share/:token" element={<SharePage />} />
            <Route
              path="/projects"
              element={
                <RequireAuth>
                  <ProjectsPage />
                </RequireAuth>
              }
            />
            <Route
              path="/projects/:projectId"
              element={
                <RequireAuth>
                  <ProjectOverviewPage />
                </RequireAuth>
              }
            />
            <Route
              path="/projects/:projectId/traces/:tracePk"
              element={
                <RequireAuth>
                  <TraceDetailPage />
                </RequireAuth>
              }
            />
            <Route
              path="/projects/:projectId/compare"
              element={
                <RequireAuth>
                  <ComparePage />
                </RequireAuth>
              }
            />
            <Route
              path="/projects/:projectId/datasets"
              element={
                <RequireAuth>
                  <DatasetsPage />
                </RequireAuth>
              }
            />
            <Route
              path="/projects/:projectId/datasets/:datasetId"
              element={
                <RequireAuth>
                  <DatasetDetailPage />
                </RequireAuth>
              }
            />
            <Route
              path="/projects/:projectId/evaluators"
              element={
                <RequireAuth>
                  <EvaluatorsPage />
                </RequireAuth>
              }
            />
            <Route
              path="/projects/:projectId/experiments"
              element={
                <RequireAuth>
                  <ExperimentsPage />
                </RequireAuth>
              }
            />
            <Route
              path="/projects/:projectId/experiments/compare"
              element={
                <RequireAuth>
                  <ExperimentComparePage />
                </RequireAuth>
              }
            />
            <Route
              path="/projects/:projectId/experiments/:experimentId"
              element={
                <RequireAuth>
                  <ExperimentDetailPage />
                </RequireAuth>
              }
            />
            <Route
              path="/projects/:projectId/settings"
              element={
                <RequireAuth>
                  <SettingsPage />
                </RequireAuth>
              }
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          </Suspense>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}
