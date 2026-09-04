import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import type { ReactNode } from "react";

import { Spinner } from "./components/ui";
import { ComparePage } from "./pages/ComparePage";
import { LoginPage } from "./pages/Login";
import { ProjectOverviewPage } from "./pages/ProjectOverview";
import { ProjectsPage } from "./pages/Projects";
import { SettingsPage } from "./pages/Settings";
import { SharePage } from "./pages/SharePage";
import { TraceDetailPage } from "./pages/TraceDetail";
import { AuthProvider, useAuth } from "./state/auth";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 5_000, refetchOnWindowFocus: false },
  },
});

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
          <Routes>
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
              path="/projects/:projectId/settings"
              element={
                <RequireAuth>
                  <SettingsPage />
                </RequireAuth>
              }
            />
            <Route path="*" element={<Navigate to="/projects" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}
