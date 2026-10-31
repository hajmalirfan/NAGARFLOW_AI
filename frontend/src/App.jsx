import { Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./auth/AuthContext.jsx";
import ProtectedRoute from "./auth/ProtectedRoute.jsx";
import AppLayout from "./components/AppLayout.jsx";
import DashboardPage from "./pages/DashboardPage.jsx";
import {
  DepotDetailPage,
  DepotFormPage,
  DepotListPage,
} from "./pages/DepotManagementPage.jsx";
import ForgotPasswordPage from "./pages/ForgotPasswordPage.jsx";
import PlaceholderPage from "./pages/PlaceholderPage.jsx";
import ResetPasswordPage from "./pages/ResetPasswordPage.jsx";
import {
  ScenarioDetailPage,
  ScenarioFormPage,
  ScenarioListPage,
} from "./pages/ScenarioManagementPage.jsx";
import {
  VehicleDetailPage,
  VehicleFormPage,
  VehicleListPage,
} from "./pages/VehicleManagementPage.jsx";
import SignInPage from "./pages/SignInPage.jsx";

// Sidebar destinations whose own development step has not been reached.
const UPCOMING_PAGES = [
  {
    path: "storage-points",
    title: "Storage Points",
    kicker: "COLLECTION POINTS",
    step: "Phase 7",
    description: "Register six to ten mandatory collection points and their waste quantities.",
  },
  {
    path: "facility",
    title: "Processing Facility",
    kicker: "FACILITY",
    step: "Phase 8",
    description: "Set the facility position and its shared delivery capacity.",
  },
  {
    path: "route-optimization",
    title: "Route Optimization",
    kicker: "OPTIMIZATION",
    step: "Phases 11 and 12",
    description: "Run the Greedy baseline and Google OR-Tools, then compare the routes.",
  },
  {
    path: "reports",
    title: "Reports",
    kicker: "REPORTS",
    step: "Phase 13",
    description: "Comparison reports across algorithms and scenarios.",
  },
  {
    path: "settings",
    title: "Settings",
    kicker: "SETTINGS",
    step: "Phase 15",
    description: "Account and application preferences.",
  },
];

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        {/* Public */}
        <Route path="/login" element={<SignInPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />

        {/* Signed in */}
        <Route element={<ProtectedRoute />}>
          <Route element={<AppLayout />}>
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/depot" element={<DepotListPage />} />
            <Route path="/depot/new" element={<DepotFormPage />} />
            <Route path="/depot/:depotId/edit" element={<DepotFormPage />} />
            <Route path="/depot/:depotId" element={<DepotDetailPage />} />
            <Route path="/scenarios" element={<ScenarioListPage />} />
            <Route path="/scenarios/new" element={<ScenarioFormPage />} />
            <Route path="/scenarios/:scenarioId/edit" element={<ScenarioFormPage />} />
            <Route path="/scenarios/:scenarioId" element={<ScenarioDetailPage />} />
            <Route path="/vehicles" element={<VehicleListPage />} />
            <Route path="/vehicles/new" element={<VehicleFormPage />} />
            <Route path="/vehicles/:vehicleId/edit" element={<VehicleFormPage />} />
            <Route path="/vehicles/:vehicleId" element={<VehicleDetailPage />} />
            {UPCOMING_PAGES.map((page) => (
              <Route
                key={page.path}
                path={`/${page.path}`}
                element={
                  <PlaceholderPage
                    title={page.title}
                    kicker={page.kicker}
                    step={page.step}
                    description={page.description}
                  />
                }
              />
            ))}
          </Route>
        </Route>

        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </AuthProvider>
  );
}
