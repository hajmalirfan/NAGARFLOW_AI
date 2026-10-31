import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";
import App from "../App.jsx";
import { TOKEN_STORAGE_KEY } from "../auth/AuthContext.jsx";

vi.mock("maplibre-gl", () => {
  class Stub {
    constructor() {}
    on(event, callback) { if (event === "load") callback(); return this; }
    fitBounds() { return this; }
    setCenter() { return this; }
    setZoom() { return this; }
    remove() {}
    setLngLat() { return this; }
    setPopup() { return this; }
    addTo() { return this; }
    setDOMContent() { return this; }
    extend() { return this; }
  }
  return { Map: Stub, Marker: Stub, Popup: Stub, LngLatBounds: Stub };
});

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
  validateScenario: vi.fn(),
  getScenarioValidations: vi.fn(),
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
  getFacilities: vi.fn(),
  getFacility: vi.fn(),
  getFacilityCapacity: vi.fn(),
  createFacility: vi.fn(),
  updateFacility: vi.fn(),
  deleteFacility: vi.fn(),
}));

const api = await import("../services/api.js");

const account = { id: 1, name: "Asha Rao", email: "asha@example.com" };

const scenario = {
  id: 4,
  reference: "SC-0004",
  name: "S01 normal feasible",
  description: "Routine collection.",
  status: "ready",
  created_at: "2026-10-31T09:00:00",
  updated_at: "2026-10-31T09:00:00",
  depot: { id: 1, name: "Central Depot" },
  processing_facility: { id: 2, name: "Central Plant", capacity_kg: 10000 },
  vehicles: [
    { id: 1, name: "Vehicle 1", capacity_kg: 5000 },
    { id: 2, name: "Vehicle 2", capacity_kg: 4000 },
  ],
  storage_points: [
    { id: 1, name: "Point 1", waste_kg: 3000, waste_type: null },
    { id: 2, name: "Point 2", waste_kg: 2500, waste_type: null },
    { id: 3, name: "Point 3", waste_kg: 1500, waste_type: null },
    { id: 4, name: "Point 4", waste_kg: 1000, waste_type: null },
    { id: 5, name: "Point 5", waste_kg: 0, waste_type: null },
    { id: 6, name: "Point 6", waste_kg: 0, waste_type: null },
  ],
};

const ALL_PASSED = {
  depot: "passed",
  vehicles: "passed",
  storage_points: "passed",
  facility: "passed",
  waste_quantity: "passed",
  vehicle_capacity: "passed",
  combined_capacity: "passed",
  facility_capacity: "passed",
  coordinates: "passed",
  vehicle_assignment: "passed",
  road_connectivity: "passed",
};

const VALID_REPORT = {
  scenario_id: 4,
  validation_status: "valid",
  can_optimize: true,
  checks: ALL_PASSED,
  errors: [],
  warnings: [],
  total_waste_kg: 8000,
  storage_point_count: 6,
  feasible_assignment: [
    {
      vehicle_id: 1, name: "Vehicle 1", capacity_kg: 5000,
      assigned_point_codes: ["SP001", "SP003"], assigned_kg: 4500,
    },
    {
      vehicle_id: 2, name: "Vehicle 2", capacity_kg: 4000,
      assigned_point_codes: ["SP002", "SP004"], assigned_kg: 3500,
    },
  ],
};

const INCOMPLETE_REPORT = {
  ...VALID_REPORT,
  validation_status: "incomplete",
  can_optimize: false,
  checks: { ...ALL_PASSED, road_connectivity: "not_checked" },
  warnings: [
    {
      code: "ROAD_NETWORK_NOT_CONFIGURED",
      message:
        "Road connectivity has not been checked because no road network is configured.",
    },
  ],
};

const INVALID_REPORT = {
  ...VALID_REPORT,
  validation_status: "invalid",
  can_optimize: false,
  checks: { ...ALL_PASSED, vehicle_capacity: "failed", road_connectivity: "not_checked" },
  errors: [
    {
      code: "STORAGE_POINT_CAPACITY",
      message: "Storage point SP004 holds 6000 kg and cannot fit into either vehicle.",
    },
  ],
  feasible_assignment: null,
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
  api.getScenario.mockResolvedValue(scenario);
});

describe("validating a scenario", () => {
  test("no report is shown until validation is run", async () => {
    renderApp("/scenarios/4");
    await screen.findByRole("heading", { name: scenario.name });

    expect(screen.queryByText(/scenario validation report/i)).not.toBeInTheDocument();
    expect(api.validateScenario).not.toHaveBeenCalled();
  });

  test("clicking Validate Scenario calls the backend", async () => {
    api.validateScenario.mockResolvedValue(VALID_REPORT);
    renderApp("/scenarios/4");
    await screen.findByRole("heading", { name: scenario.name });

    await userEvent.click(screen.getByRole("button", { name: /validate scenario/i }));

    await waitFor(() => expect(api.validateScenario).toHaveBeenCalledWith("4"));
    expect(await screen.findByText(/scenario validation report/i)).toBeInTheDocument();
  });

  test("a valid scenario reports every check as passed", async () => {
    api.validateScenario.mockResolvedValue(VALID_REPORT);
    renderApp("/scenarios/4");
    await screen.findByRole("heading", { name: scenario.name });
    await userEvent.click(screen.getByRole("button", { name: /validate scenario/i }));

    const report = (await screen.findByText(/scenario validation report/i))
      .closest("section");
    for (const label of [
      "Depot", "Vehicle configuration", "Storage point count", "Processing facility",
      "Individual vehicle capacity", "Combined vehicle capacity", "Facility capacity",
      "Coordinates", "Vehicle capacity assignment", "Road connectivity",
    ]) {
      const row = within(report).getByText(label).closest("li");
      expect(within(row).getByText("Passed")).toBeInTheDocument();
    }
    expect(within(report).getByText(/scenario is feasible/i)).toBeInTheDocument();
  });

  test("the workable assignment is shown so the split is visible", async () => {
    api.validateScenario.mockResolvedValue(VALID_REPORT);
    renderApp("/scenarios/4");
    await screen.findByRole("heading", { name: scenario.name });
    await userEvent.click(screen.getByRole("button", { name: /validate scenario/i }));

    expect(await screen.findByText("SP001, SP003")).toBeInTheDocument();
    expect(screen.getByText("4,500 / 5,000 kg")).toBeInTheDocument();
    expect(screen.getByText("3,500 / 4,000 kg")).toBeInTheDocument();
  });
});

describe("errors and warnings", () => {
  test("a failing check is shown with its error code and message", async () => {
    api.validateScenario.mockResolvedValue(INVALID_REPORT);
    renderApp("/scenarios/4");
    await screen.findByRole("heading", { name: scenario.name });
    await userEvent.click(screen.getByRole("button", { name: /validate scenario/i }));

    expect(await screen.findByText("STORAGE_POINT_CAPACITY")).toBeInTheDocument();
    expect(screen.getByText(/cannot fit into either vehicle/i)).toBeInTheDocument();
    const row = screen.getByText("Individual vehicle capacity").closest("li");
    expect(within(row).getByText("Failed")).toBeInTheDocument();
  });

  test("an unchecked road network is shown as a warning, not a pass", async () => {
    api.validateScenario.mockResolvedValue(INCOMPLETE_REPORT);
    renderApp("/scenarios/4");
    await screen.findByRole("heading", { name: scenario.name });
    await userEvent.click(screen.getByRole("button", { name: /validate scenario/i }));

    expect(await screen.findByText("ROAD_NETWORK_NOT_CONFIGURED")).toBeInTheDocument();
    const row = screen.getByText("Road connectivity").closest("li");
    expect(within(row).getByText("Not checked")).toBeInTheDocument();
    expect(screen.getByText(/validation incomplete/i)).toBeInTheDocument();
  });

  test("a failed request is surfaced and no report is shown", async () => {
    api.validateScenario.mockRejectedValue(new Error("Unable to reach the NagarFlow API."));
    renderApp("/scenarios/4");
    await screen.findByRole("heading", { name: scenario.name });

    await userEvent.click(screen.getByRole("button", { name: /validate scenario/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/unable to reach/i);
    expect(screen.queryByText(/scenario validation report/i)).not.toBeInTheDocument();
  });
});

describe("Proceed to Optimization", () => {
  test("it is disabled before any validation has run", async () => {
    renderApp("/scenarios/4");
    await screen.findByRole("heading", { name: scenario.name });

    expect(screen.getByRole("button", { name: /proceed to optimization/i })).toBeDisabled();
  });

  test("it stays disabled when validation fails", async () => {
    api.validateScenario.mockResolvedValue(INVALID_REPORT);
    renderApp("/scenarios/4");
    await screen.findByRole("heading", { name: scenario.name });
    await userEvent.click(screen.getByRole("button", { name: /validate scenario/i }));
    await screen.findByText("STORAGE_POINT_CAPACITY");

    expect(screen.getByRole("button", { name: /proceed to optimization/i })).toBeDisabled();
  });

  test("it stays disabled when validation is incomplete", async () => {
    api.validateScenario.mockResolvedValue(INCOMPLETE_REPORT);
    renderApp("/scenarios/4");
    await screen.findByRole("heading", { name: scenario.name });
    await userEvent.click(screen.getByRole("button", { name: /validate scenario/i }));
    await screen.findByText("ROAD_NETWORK_NOT_CONFIGURED");

    expect(screen.getByRole("button", { name: /proceed to optimization/i })).toBeDisabled();
  });

  test("it is enabled only once every check passes", async () => {
    api.validateScenario.mockResolvedValue(VALID_REPORT);
    renderApp("/scenarios/4");
    await screen.findByRole("heading", { name: scenario.name });
    await userEvent.click(screen.getByRole("button", { name: /validate scenario/i }));
    await screen.findByText(/scenario is feasible/i);

    expect(screen.getByRole("button", { name: /proceed to optimization/i })).toBeEnabled();
  });
});
