import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";
import App from "../App.jsx";
import { TOKEN_STORAGE_KEY } from "../auth/AuthContext.jsx";

vi.mock("../services/api.js", () => ({
  getApiHealth: vi.fn(),
  register: vi.fn(),
  login: vi.fn(),
  getCurrentUser: vi.fn(),
  forgotPassword: vi.fn(),
  verifyResetToken: vi.fn(),
  resetPassword: vi.fn(),
  getDashboardSummary: vi.fn(),
  getScenarios: vi.fn(),
  getScenarioOptions: vi.fn(),
  getScenario: vi.fn(),
  createScenario: vi.fn(),
  updateScenario: vi.fn(),
  deleteScenario: vi.fn(),
  getDepots: vi.fn(),
  getDepot: vi.fn(),
  createDepot: vi.fn(),
  updateDepot: vi.fn(),
  deleteDepot: vi.fn(),
  getVehicles: vi.fn(),
  getVehicle: vi.fn(),
  createVehicle: vi.fn(),
  updateVehicle: vi.fn(),
  deleteVehicle: vi.fn(),
}));

const api = await import("../services/api.js");
const account = { id: 1, name: "Asha Rao", email: "asha@example.com" };
const depot = {
  id: 7,
  name: "Central depot",
  code: "DEP001",
  address: "Municipal address",
  latitude: 10.79,
  longitude: 78.7,
  is_active: true,
  created_at: "2026-10-31T12:00:00",
  updated_at: "2026-10-31T12:00:00",
};

function renderApp(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  localStorage.setItem(TOKEN_STORAGE_KEY, "token");
  api.getCurrentUser.mockResolvedValue(account);
  api.getDashboardSummary.mockResolvedValue({
    total_waste_kg: 0,
    storage_points_count: 0,
    available_vehicles_count: 0,
    facility_remaining_capacity_kg: 0,
    total_scenarios: 0,
    optimized_routes_count: 0,
    facility_configured: false,
    waste_overview: { total_waste_kg: 0, storage_points_count: 0, largest_point_kg: 0, average_point_kg: 0 },
    vehicle_status: { available: [], unavailable: [], available_count: 0, unavailable_count: 0, total_available_capacity_kg: 0 },
    storage_points: [],
    recent_scenarios: [],
    optimization_summary: { successful_runs: 0, failed_runs: 0, total_runs: 0, best_distance_km: null },
  });
  api.getDepots.mockResolvedValue([]);
  api.getVehicles.mockResolvedValue([]);
  api.getDepot.mockResolvedValue(depot);
});

describe("depot management", () => {
  test("lists depots and their active status", async () => {
    api.getDepots.mockResolvedValue([depot, { ...depot, id: 8, name: "Inactive", is_active: false }]);
    renderApp("/depot");

    expect(await screen.findByRole("link", { name: "Central depot" })).toHaveAttribute("href", "/depot/7");
    expect(screen.getByText("Inactive", { selector: ".pill" })).toBeInTheDocument();
  });

  test("creates a depot with real form data", async () => {
    const user = userEvent.setup();
    api.createDepot.mockResolvedValue(depot);
    renderApp("/depot/new");

    await user.type(await screen.findByLabelText("Depot name"), depot.name);
    await user.type(screen.getByLabelText("Depot code"), depot.code);
    await user.type(screen.getByLabelText("Address"), depot.address);
    await user.type(screen.getByLabelText("Latitude"), String(depot.latitude));
    await user.type(screen.getByLabelText("Longitude"), String(depot.longitude));
    await user.click(screen.getByRole("button", { name: "Add depot" }));

    await waitFor(() => expect(api.createDepot).toHaveBeenCalledWith({
      name: depot.name,
      code: depot.code,
      address: depot.address,
      latitude: depot.latitude,
      longitude: depot.longitude,
      is_active: true,
    }));
    expect(await screen.findByRole("heading", { name: depot.name })).toBeInTheDocument();
  });

  test("loads details and sends edited values", async () => {
    const user = userEvent.setup();
    const edited = { ...depot, name: "North depot", is_active: false };
    api.updateDepot.mockResolvedValue(edited);
    renderApp("/depot/7/edit");

    const name = await screen.findByLabelText("Depot name");
    await user.clear(name);
    await user.type(name, edited.name);
    await user.click(screen.getByRole("checkbox", { name: "Active" }));
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(api.updateDepot).toHaveBeenCalledWith("7", {
      name: edited.name,
      code: depot.code,
      address: depot.address,
      latitude: depot.latitude,
      longitude: depot.longitude,
      is_active: false,
    }));
  });
});
