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
import {
  FacilityDetailPage,
  FacilityFormPage,
  FacilityListPage,
} from "./pages/ProcessingFacilityManagementPage.jsx";
import ForgotPasswordPage from "./pages/ForgotPasswordPage.jsx";
import PlaceholderPage from "./pages/PlaceholderPage.jsx";
import { HistoryPage, HistoryRunPage } from "./pages/HistoryPage.jsx";
import ReportsPage from "./pages/ReportsPage.jsx";
import RouteOptimizationPage from "./pages/RouteOptimizationPage.jsx";
import ResetPasswordPage from "./pages/ResetPasswordPage.jsx";
import {
  StoragePointDetailPage,
  StoragePointFormPage,
  StoragePointListPage,
} from "./pages/StoragePointManagementPage.jsx";
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
            <Route path="/route-optimization" element={<RouteOptimizationPage />} />
            <Route path="/reports" element={<ReportsPage />} />
            <Route path="/history" element={<HistoryPage />} />
            <Route path="/history/:scenarioId/:batchId" element={<HistoryRunPage />} />
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
            <Route path="/facility" element={<FacilityListPage />} />
            <Route path="/facility/new" element={<FacilityFormPage />} />
            <Route path="/facility/:facilityId/edit" element={<FacilityFormPage />} />
            <Route path="/facility/:facilityId" element={<FacilityDetailPage />} />
            <Route path="/storage-points" element={<StoragePointListPage />} />
            <Route path="/storage-points/new" element={<StoragePointFormPage />} />
            <Route path="/storage-points/:pointId/edit" element={<StoragePointFormPage />} />
            <Route path="/storage-points/:pointId" element={<StoragePointDetailPage />} />
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
