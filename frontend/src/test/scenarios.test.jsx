import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
const user = { id: 1, name: "Asha Rao", email: "asha@example.com" };
const configuredOptions = {
  depots: [{ id: 1, name: "North depot" }],
  facilities: [{ id: 2, name: "Central facility", capacity_kg: 9000 }],
  vehicles: [
    { id: 3, name: "Truck 1", capacity_kg: 5000, is_available: true, depot_id: 1 },
    { id: 4, name: "Truck 2", capacity_kg: 5000, is_available: true, depot_id: 1 },
  ],
  storage_points: Array.from({ length: 6 }, (_, index) => ({
    id: index + 10,
    name: `Point ${index + 1}`,
    waste_kg: 100,
    waste_type: "",
  })),
};
const createdScenario = {
  id: 20,
  reference: "SC-ABC123",
  name: "Weekly collection",
  description: "Routine service",
  status: "ready",
  depot: configuredOptions.depots[0],
  processing_facility: configuredOptions.facilities[0],
  vehicles: configuredOptions.vehicles,
  storage_points: configuredOptions.storage_points,
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
  api.getCurrentUser.mockResolvedValue(user);
  api.getScenarios.mockResolvedValue([]);
  api.getScenarioOptions.mockResolvedValue({
    depots: [],
    facilities: [],
    vehicles: [],
    storage_points: [],
  });
  api.getScenario.mockResolvedValue(createdScenario);
  api.getDepots.mockResolvedValue([]);
  api.getVehicles.mockResolvedValue([]);
});

describe("scenario management", () => {
  test("lists scenarios from the API", async () => {
    api.getScenarios.mockResolvedValue([createdScenario]);
    renderApp("/scenarios");

    expect(await screen.findByRole("link", { name: "Weekly collection" })).toHaveAttribute(
      "href",
      "/scenarios/20",
    );
    expect(screen.getByText("2 vehicles · 6 points")).toBeInTheDocument();
  });

  test("does not fabricate missing setup records", async () => {
    renderApp("/scenarios/new");

    expect(await screen.findByText(/database does not yet contain depots/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create scenario" })).toBeDisabled();
  });

  test("submits a scenario using exactly two vehicles and six storage points", async () => {
    const userEventInstance = userEvent.setup();
    api.getScenarioOptions.mockResolvedValue(configuredOptions);
    api.createScenario.mockResolvedValue(createdScenario);
    renderApp("/scenarios/new");

    await userEventInstance.type(await screen.findByLabelText("Scenario name"), "Weekly collection");
    await userEventInstance.type(screen.getByLabelText("Description"), "Routine service");
    await userEventInstance.selectOptions(screen.getByLabelText("Depot"), "1");
    await userEventInstance.selectOptions(screen.getByLabelText("Processing facility"), "2");
    await userEventInstance.click(screen.getByRole("checkbox", { name: /Truck 1/ }));
    await userEventInstance.click(screen.getByRole("checkbox", { name: /Truck 2/ }));
    for (let index = 1; index <= 6; index += 1) {
      await userEventInstance.click(screen.getByRole("checkbox", { name: new RegExp(`Point ${index}`) }));
    }
    await userEventInstance.selectOptions(screen.getByLabelText("Status"), "ready");
    await userEventInstance.click(screen.getByRole("button", { name: "Create scenario" }));

    await waitFor(() => expect(api.createScenario).toHaveBeenCalledWith({
      shift_start: null,
      shift_end: null,
      name: "Weekly collection",
      description: "Routine service",
      depot_id: 1,
      facility_id: 2,
      vehicle_ids: [3, 4],
      storage_point_ids: [10, 11, 12, 13, 14, 15],
      status: "ready",
    }));
    expect(await screen.findByRole("heading", { name: "Weekly collection" })).toBeInTheDocument();
  });
});

test("it saves shift times on a scenario", async () => {
  api.getCurrentUser.mockResolvedValue(user);
  api.getScenarioOptions.mockResolvedValue(configuredOptions);
  api.getScenario.mockResolvedValue({
    ...createdScenario,
    shift_start: "2026-11-03T06:00:00",
    shift_end: "2026-11-03T14:00:00",
  });
  api.updateScenario.mockResolvedValue(createdScenario);
  renderApp("/scenarios/4/edit");

  expect(await screen.findByLabelText("Shift start")).toHaveValue("2026-11-03T06:00");
  fireEvent.change(screen.getByLabelText("Shift end"), { target: { value: "2026-11-03T15:00" } });
  await userEvent.click(screen.getByRole("button", { name: /save/i }));

  await waitFor(() => expect(api.updateScenario).toHaveBeenCalledWith(
    "4",
    expect.objectContaining({
      shift_start: "2026-11-03T06:00",
      shift_end: "2026-11-03T15:00",
    }),
  ));
});
