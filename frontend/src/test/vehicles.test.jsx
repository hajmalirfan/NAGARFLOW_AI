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
  getStoragePoints: vi.fn(),
  getStoragePoint: vi.fn(),
  createStoragePoint: vi.fn(),
  updateStoragePoint: vi.fn(),
  deleteStoragePoint: vi.fn(),
}));

const api = await import("../services/api.js");
const account = { id: 1, name: "Asha Rao", email: "asha@example.com" };
const depot = {
  id: 5,
  name: "North depot",
  code: "DEP001",
  latitude: 11.2,
  longitude: 77.3,
  is_active: true,
};
const vehicle = {
  id: 12,
  vehicle_number: "TN50AB1234",
  name: "Truck 01",
  vehicle_type: "Truck",
  capacity_kg: 5000,
  depot,
  status: "available",
  is_available: true,
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
  api.getDepots.mockResolvedValue([depot]);
  api.getVehicles.mockResolvedValue([]);
  api.getVehicle.mockResolvedValue(vehicle);
});

describe("vehicle management", () => {
  test("lists vehicles with depot and maintenance status", async () => {
    api.getVehicles.mockResolvedValue([
      vehicle,
      { ...vehicle, id: 13, vehicle_number: "TN50AB5678", name: "Truck 02", status: "maintenance", is_available: false },
    ]);
    renderApp("/vehicles");

    expect(await screen.findByRole("link", { name: "Truck 01" })).toHaveAttribute("href", "/vehicles/12");
    expect(screen.getAllByText("North depot")).toHaveLength(2);
    expect(screen.getByText("maintenance", { selector: ".pill" })).toBeInTheDocument();
  });

  test("creates a vehicle using the active depot", async () => {
    const user = userEvent.setup();
    api.createVehicle.mockResolvedValue(vehicle);
    renderApp("/vehicles/new");

    await user.type(await screen.findByLabelText("Vehicle number"), "TN50AB1234");
    await user.type(screen.getByLabelText("Vehicle name"), "Truck 01");
    await user.type(screen.getByLabelText("Capacity (kg)"), "5000");
    await user.selectOptions(screen.getByLabelText("Depot"), "5");
    await user.click(screen.getByRole("button", { name: "Add vehicle" }));

    await waitFor(() => expect(api.createVehicle).toHaveBeenCalledWith({
      vehicle_number: "TN50AB1234",
      name: "Truck 01",
      vehicle_type: "Truck",
      capacity_kg: 5000,
      depot_id: 5,
      status: "available",
    }));
    expect(await screen.findByRole("heading", { name: "Truck 01" })).toBeInTheDocument();
  });

  test("edits vehicle capacity and status", async () => {
    const user = userEvent.setup();
    api.updateVehicle.mockResolvedValue({ ...vehicle, capacity_kg: 6000, status: "maintenance" });
    renderApp("/vehicles/12/edit");

    const capacity = await screen.findByLabelText("Capacity (kg)");
    await user.clear(capacity);
    await user.type(capacity, "6000");
    await user.selectOptions(screen.getByLabelText("Status"), "maintenance");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(api.updateVehicle).toHaveBeenCalledWith("12", {
      vehicle_number: "TN50AB1234",
      name: "Truck 01",
      vehicle_type: "Truck",
      capacity_kg: 6000,
      depot_id: 5,
      status: "maintenance",
    }));
  });

  test("allows managing vehicles beyond the two selected by an individual scenario", async () => {
    api.getVehicles.mockResolvedValue([vehicle, { ...vehicle, id: 13 }, { ...vehicle, id: 14 }]);
    renderApp("/vehicles/new");

    expect(await screen.findByRole("button", { name: "Add vehicle" })).toBeEnabled();
  });
});
