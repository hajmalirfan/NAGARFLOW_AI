import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";
import App from "../App.jsx";
import { TOKEN_STORAGE_KEY } from "../auth/AuthContext.jsx";

const mapTools = vi.hoisted(() => ({
  markerAdded: vi.fn(),
  markerCoordinates: vi.fn(),
  popupContents: vi.fn(),
  fitBounds: vi.fn(),
  mapOptions: vi.fn(),
  mapRemoved: vi.fn(),
}));

vi.mock("maplibre-gl", () => {
  class MockMap {
    constructor(options) {
      mapTools.mapOptions(options);
    }

    on(event, callback) {
      if (event === "load") callback();
      return this;
    }

    fitBounds(bounds, options) {
      mapTools.fitBounds(bounds, options);
      return this;
    }

    setCenter() { return this; }
    setZoom() { return this; }
    remove() { mapTools.mapRemoved(); }
  }

  class MockMarker {
    setLngLat(coordinates) {
      mapTools.markerCoordinates(coordinates);
      return this;
    }

    setPopup(popup) {
      mapTools.popupContents(popup);
      return this;
    }

    addTo() {
      mapTools.markerAdded();
      return this;
    }
  }

  class MockPopup {
    setDOMContent(content) {
      this.content = content;
      mapTools.popupContents(content);
      return this;
    }
  }

  class MockBounds {
    extend() { return this; }
  }

  return { Map: MockMap, Marker: MockMarker, Popup: MockPopup, LngLatBounds: MockBounds, setWorkerUrl() {} };
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

const account = { id: 1, name: "Asha Rao", email: "asha@example.com", role: "planner" };

const facility = {
  id: 7,
  name: "Central Waste Processing Plant",
  facility_code: "FAC001",
  address: "Trichy Industrial Area",
  latitude: 10.815,
  longitude: 78.685,
  total_capacity_kg: 10000,
  status: "active",
  description: "Primary municipal processing plant.",
  created_at: "2026-10-31T12:00:00",
  updated_at: "2026-10-31T12:00:00",
};

const capacity = {
  id: 7,
  name: facility.name,
  facility_code: facility.facility_code,
  total_capacity_kg: 10000,
  allocated_kg: 9000,
  remaining_capacity_kg: 1000,
  is_within_capacity: true,
  status: "active",
  scenarios: [
    { id: 1, reference: "SC-0001", name: "S01 normal feasible", allocated_kg: 9000 },
  ],
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
  api.getFacilities.mockResolvedValue([]);
  api.getFacility.mockResolvedValue(facility);
  api.getFacilityCapacity.mockResolvedValue(capacity);
});

describe("processing facility list", () => {
  test("an empty database says no facility is configured", async () => {
    renderApp("/facility");

    expect(await screen.findByText(/no facility configured yet/i)).toBeInTheDocument();
  });

  test("registered facilities are listed from the database", async () => {
    api.getFacilities.mockResolvedValue([facility]);
    renderApp("/facility");

    expect(await screen.findByText("Central Waste Processing Plant")).toBeInTheDocument();
    expect(screen.getByText("FAC001")).toBeInTheDocument();
    expect(screen.getByText("10,000 kg")).toBeInTheDocument();
  });

  test("the list shows remaining shared capacity per facility", async () => {
    api.getFacilities.mockResolvedValue([facility]);
    renderApp("/facility");

    expect(await screen.findByText("1,000 kg left")).toBeInTheDocument();
  });

  test("search narrows the list", async () => {
    const other = { ...facility, id: 8, name: "Northern Plant", facility_code: "FAC002" };
    api.getFacilities.mockResolvedValue([facility, other]);
    renderApp("/facility");
    await screen.findByText("Central Waste Processing Plant");

    await userEvent.type(screen.getByLabelText(/search facilities/i), "Northern");

    expect(screen.getByText("Northern Plant")).toBeInTheDocument();
    expect(screen.queryByText("Central Waste Processing Plant")).not.toBeInTheDocument();
  });

  test("the status filter separates active from inactive", async () => {
    const inactive = {
      ...facility, id: 8, name: "Retired Plant", facility_code: "FAC002", status: "inactive",
    };
    api.getFacilities.mockResolvedValue([facility, inactive]);
    renderApp("/facility");
    await screen.findByText("Central Waste Processing Plant");

    await userEvent.selectOptions(screen.getByLabelText(/^status$/i), "inactive");

    expect(screen.getByText("Retired Plant")).toBeInTheDocument();
    expect(screen.queryByText("Central Waste Processing Plant")).not.toBeInTheDocument();
  });

  test("facilities are drawn on the map", async () => {
    api.getFacilities.mockResolvedValue([facility]);
    renderApp("/facility");
    await screen.findByText("Central Waste Processing Plant");

    await waitFor(() => expect(mapTools.markerAdded).toHaveBeenCalled());
    expect(mapTools.markerCoordinates).toHaveBeenCalledWith([78.685, 10.815]);
  });
});

describe("processing facility detail", () => {
  test("the details and shared capacity are shown", async () => {
    renderApp("/facility/7");

    expect(await screen.findByRole("heading", { name: facility.name })).toBeInTheDocument();
    const details = (await screen.findByText("Facility code")).closest("dl");
    expect(within(details).getByText("FAC001")).toBeInTheDocument();
    expect(within(details).getByText("Trichy Industrial Area")).toBeInTheDocument();
  });

  test("the capacity monitor reports the shared pool, not a per-vehicle figure", async () => {
    renderApp("/facility/7");
    const monitor = (await screen.findByRole("heading", { name: /shared capacity/i }))
      .closest("section");

    const tile = (label) => within(monitor).getByText(label).closest("div");
    expect(within(tile("Total capacity")).getByText("10,000 kg")).toBeInTheDocument();
    expect(within(tile("Committed by scenarios")).getByText("9,000 kg")).toBeInTheDocument();
    expect(within(tile("Remaining capacity")).getByText("1,000 kg")).toBeInTheDocument();
    expect(within(monitor).getByText(/within capacity/i)).toBeInTheDocument();
  });

  test("an over-committed facility is flagged", async () => {
    api.getFacilityCapacity.mockResolvedValue({
      ...capacity, total_capacity_kg: 8000, allocated_kg: 9000,
      remaining_capacity_kg: -1000, is_within_capacity: false,
    });
    renderApp("/facility/7");

    expect(await screen.findByText(/over capacity/i)).toBeInTheDocument();
  });

  test("the scenarios committing capacity are listed", async () => {
    renderApp("/facility/7");

    expect(await screen.findByText("S01 normal feasible")).toBeInTheDocument();
    expect(screen.getByText("SC-0001")).toBeInTheDocument();
  });

  test("deactivating an active facility calls the API with inactive status", async () => {
    api.updateFacility.mockResolvedValue({ ...facility, status: "inactive" });
    renderApp("/facility/7");
    await screen.findByRole("heading", { name: facility.name });

    await userEvent.click(screen.getByRole("button", { name: /deactivate/i }));

    await waitFor(() =>
      expect(api.updateFacility).toHaveBeenCalledWith(
        "7", expect.objectContaining({ status: "inactive" }),
      ),
    );
    expect(await screen.findByRole("button", { name: /activate/i })).toBeInTheDocument();
  });

  test("a refused deactivation shows the reason and keeps the facility active", async () => {
    api.updateFacility.mockRejectedValue(
      Object.assign(
        new Error("This facility is linked to a scenario. Update or remove that scenario before deactivating the facility."),
        { status: 409 },
      ),
    );
    renderApp("/facility/7");
    await screen.findByRole("heading", { name: facility.name });

    await userEvent.click(screen.getByRole("button", { name: /deactivate/i }));

    await waitFor(() =>
      expect(
        screen.getAllByRole("alert").some((node) => /linked to a scenario/i.test(node.textContent)),
      ).toBe(true),
    );
    expect(screen.getByRole("button", { name: /deactivate/i })).toBeInTheDocument();
  });

  test("a refused delete explains why", async () => {
    api.deleteFacility.mockRejectedValue(
      Object.assign(
        new Error("This facility is linked to a scenario. Update or remove that scenario first."),
        { status: 409 },
      ),
    );
    renderApp("/facility/7");
    await screen.findByRole("heading", { name: facility.name });

    await userEvent.click(screen.getByRole("button", { name: /delete/i }));

    await waitFor(() =>
      expect(
        screen.getAllByRole("alert").some((node) => /linked to a scenario/i.test(node.textContent)),
      ).toBe(true),
    );
  });
});

describe("processing facility form", () => {
  test("a new facility is created from the entered values", async () => {
    api.createFacility.mockResolvedValue(facility);
    renderApp("/facility/new");
    await screen.findByRole("heading", { name: /add processing facility/i });

    await userEvent.type(screen.getByLabelText(/facility name/i), facility.name);
    await userEvent.type(screen.getByLabelText(/facility code/i), "FAC001");
    await userEvent.type(screen.getByLabelText(/address/i), facility.address);
    await userEvent.type(screen.getByLabelText(/latitude/i), "10.8150");
    await userEvent.type(screen.getByLabelText(/longitude/i), "78.6850");
    await userEvent.type(screen.getByLabelText(/total capacity/i), "10000");
    await userEvent.click(screen.getByRole("button", { name: /create facility/i }));

    await waitFor(() =>
      expect(api.createFacility).toHaveBeenCalledWith({
        name: facility.name,
        facility_code: "FAC001",
        address: facility.address,
        latitude: 10.815,
        longitude: 78.685,
        total_capacity_kg: 10000,
        status: "active",
        description: "",
      }),
    );
  });

  test("zero capacity is refused before the request is sent", async () => {
    renderApp("/facility/new");
    await screen.findByRole("heading", { name: /add processing facility/i });

    await userEvent.type(screen.getByLabelText(/facility name/i), "Plant");
    await userEvent.type(screen.getByLabelText(/facility code/i), "FAC001");
    await userEvent.type(screen.getByLabelText(/latitude/i), "10.8150");
    await userEvent.type(screen.getByLabelText(/longitude/i), "78.6850");
    await userEvent.type(screen.getByLabelText(/total capacity/i), "0");
    await userEvent.click(screen.getByRole("button", { name: /create facility/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/greater than zero/i);
    expect(api.createFacility).not.toHaveBeenCalled();
  });

  test("an out-of-range latitude is refused before the request is sent", async () => {
    renderApp("/facility/new");
    await screen.findByRole("heading", { name: /add processing facility/i });

    await userEvent.type(screen.getByLabelText(/facility name/i), "Plant");
    await userEvent.type(screen.getByLabelText(/facility code/i), "FAC001");
    await userEvent.type(screen.getByLabelText(/latitude/i), "95");
    await userEvent.type(screen.getByLabelText(/longitude/i), "78.6850");
    await userEvent.type(screen.getByLabelText(/total capacity/i), "10000");
    await userEvent.click(screen.getByRole("button", { name: /create facility/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/latitude must be between/i);
    expect(api.createFacility).not.toHaveBeenCalled();
  });

  test("a duplicate facility code from the API is surfaced", async () => {
    api.createFacility.mockRejectedValue(
      Object.assign(
        new Error("A processing facility with this code already exists."), { status: 409 },
      ),
    );
    renderApp("/facility/new");
    await screen.findByRole("heading", { name: /add processing facility/i });

    await userEvent.type(screen.getByLabelText(/facility name/i), "Plant");
    await userEvent.type(screen.getByLabelText(/facility code/i), "FAC001");
    await userEvent.type(screen.getByLabelText(/latitude/i), "10.8150");
    await userEvent.type(screen.getByLabelText(/longitude/i), "78.6850");
    await userEvent.type(screen.getByLabelText(/total capacity/i), "10000");
    await userEvent.click(screen.getByRole("button", { name: /create facility/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/already exists/i);
  });

  test("editing loads the stored values and sends an update", async () => {
    api.updateFacility.mockResolvedValue({ ...facility, total_capacity_kg: 12000 });
    renderApp("/facility/7/edit");
    await screen.findByRole("heading", { name: /edit processing facility/i });

    const capacityInput = screen.getByLabelText(/total capacity/i);
    expect(capacityInput).toHaveValue("10000");
    await userEvent.clear(capacityInput);
    await userEvent.type(capacityInput, "12000");
    await userEvent.click(screen.getByRole("button", { name: /save facility/i }));

    await waitFor(() =>
      expect(api.updateFacility).toHaveBeenCalledWith(
        "7", expect.objectContaining({ total_capacity_kg: 12000 }),
      ),
    );
  });

  test("a capacity reduction the API refuses is explained", async () => {
    api.updateFacility.mockRejectedValue(
      Object.assign(
        new Error("Scenario SC-0001 already commits 9000 kg to this facility, so the shared capacity cannot be reduced to 8000 kg."),
        { status: 409 },
      ),
    );
    renderApp("/facility/7/edit");
    await screen.findByRole("heading", { name: /edit processing facility/i });

    const capacityInput = screen.getByLabelText(/total capacity/i);
    await userEvent.clear(capacityInput);
    await userEvent.type(capacityInput, "8000");
    await userEvent.click(screen.getByRole("button", { name: /save facility/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/already commits 9000 kg/i);
  });
});

describe("sidebar", () => {
  test("Processing Facility is a real page, not a placeholder", async () => {
    renderApp("/facility");
    await screen.findByText(/no facility configured yet/i);

    expect(screen.queryByText(/not built yet/i)).not.toBeInTheDocument();
  });
});

describe("evaluation input wording", () => {
  test("the list never asks for real or actual records", async () => {
    renderApp("/facility");
    await screen.findByRole("heading", { name: /processing facility management/i });

    expect(screen.queryByText(/\breal\b|\bactual\b|verified location/i)).not.toBeInTheDocument();
  });

  test("the form marks entries as evaluation inputs, not verified records", async () => {
    renderApp("/facility/new");
    await screen.findByRole("heading", { name: /add processing facility/i });

    expect(screen.getByText(/not verified municipal records/i)).toBeInTheDocument();
    expect(screen.queryByText(/\breal\b|\bactual\b|verified location/i)).not.toBeInTheDocument();
  });
});
