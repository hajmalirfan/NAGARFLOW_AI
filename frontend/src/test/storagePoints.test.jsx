import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
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
    constructor(_container, options) {
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
      return this;
    }
  }

  class MockBounds {
    extend() { return this; }
  }

  return {
    Map: MockMap,
    Marker: MockMarker,
    Popup: MockPopup,
    LngLatBounds: MockBounds,
  };
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
}));

const api = await import("../services/api.js");
const originalGeolocationDescriptor = Object.getOwnPropertyDescriptor(navigator, "geolocation");
const account = { id: 1, name: "Asha Rao", email: "asha@example.com" };
const point = {
  id: 9,
  name: "Central Market",
  point_code: "SP001",
  address: "Central Market, Trichy",
  latitude: 10.7905,
  longitude: 78.7047,
  waste_quantity_kg: 1200,
  availability_status: "available",
  description: "Municipal collection area.",
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
  api.getStoragePoints.mockResolvedValue([]);
  api.getStoragePoint.mockResolvedValue(point);
});

afterEach(() => {
  if (originalGeolocationDescriptor) {
    Object.defineProperty(navigator, "geolocation", originalGeolocationDescriptor);
  } else {
    delete navigator.geolocation;
  }
});

describe("storage point management", () => {
  test("lists and searches database points and renders map markers", async () => {
    const user = userEvent.setup();
    api.getStoragePoints.mockResolvedValue([
      point,
      {
        ...point,
        id: 10,
        name: "River Road",
        point_code: "SP002",
        address: "River Road",
        availability_status: "unavailable",
      },
    ]);
    renderApp("/storage-points");

    expect(await screen.findByRole("link", { name: "Central Market" })).toHaveAttribute(
      "href",
      "/storage-points/9",
    );
    expect(await screen.findByRole("link", { name: "River Road" })).toBeInTheDocument();
    await waitFor(() => expect(mapTools.markerAdded).toHaveBeenCalledTimes(2));
    expect(mapTools.markerCoordinates).toHaveBeenCalledWith([78.7047, 10.7905]);
    expect(mapTools.popupContents).toHaveBeenCalledTimes(2);

    await user.type(screen.getByRole("searchbox", { name: "Search storage points" }), "market");
    expect(screen.getByRole("link", { name: "Central Market" })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByRole("link", { name: "River Road" })).not.toBeInTheDocument();
    });
    await user.selectOptions(screen.getByLabelText("Availability"), "unavailable");
    expect(screen.getByText("No matching storage points")).toBeInTheDocument();
  });

  test("creates a storage point with explicit coordinates and quantity", async () => {
    const user = userEvent.setup();
    api.createStoragePoint.mockResolvedValue(point);
    renderApp("/storage-points/new");

    await user.type(await screen.findByLabelText("Storage point name"), point.name);
    await user.type(screen.getByLabelText("Point code"), point.point_code);
    await user.type(screen.getByLabelText("Latitude"), String(point.latitude));
    await user.type(screen.getByLabelText("Longitude"), String(point.longitude));
    await user.type(screen.getByLabelText("Waste quantity (kg)"), "1200");
    await user.click(screen.getByRole("button", { name: "Add storage point" }));

    await waitFor(() => expect(api.createStoragePoint).toHaveBeenCalledWith({
      available_from: null,
      name: "Central Market",
      point_code: "SP001",
      address: "",
      latitude: 10.7905,
      longitude: 78.7047,
      waste_quantity_kg: 1200,
      availability_status: "available",
      description: "",
    }));
    expect(await screen.findByRole("heading", { name: "Storage point details" })).toBeInTheDocument();
  });

  test("updates waste and availability for a configured point", async () => {
    const user = userEvent.setup();
    api.updateStoragePoint.mockResolvedValue({
      ...point,
      waste_quantity_kg: 1400.5,
      availability_status: "unavailable",
    });
    renderApp("/storage-points/9/edit");

    const quantity = await screen.findByLabelText("Waste quantity (kg)");
    await user.clear(quantity);
    await user.type(quantity, "1400.5");
    await user.selectOptions(screen.getByLabelText("Availability"), "unavailable");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(api.updateStoragePoint).toHaveBeenCalledWith("9", {
      available_from: null,
      name: "Central Market",
      point_code: "SP001",
      address: "Central Market, Trichy",
      latitude: 10.7905,
      longitude: 78.7047,
      waste_quantity_kg: 1400.5,
      availability_status: "unavailable",
      description: "Municipal collection area.",
    }));
  });

  test("fills storage point coordinates from the browser location", async () => {
    const user = userEvent.setup();
    Object.defineProperty(navigator, "geolocation", {
      configurable: true,
      value: {
        getCurrentPosition: vi.fn((onSuccess) => onSuccess({
          coords: { latitude: 10.89918, longitude: 79.54393, accuracy: 12.4 },
        })),
      },
    });
    renderApp("/storage-points/new");

    await user.click(await screen.findByRole("button", { name: "Use my location" }));

    expect(await screen.findByRole("status")).toHaveTextContent("accuracy about 12 m");
    expect(screen.getByLabelText("Latitude")).toHaveValue(10.89918);
    expect(screen.getByLabelText("Longitude")).toHaveValue(79.54393);
  });

  test("explains when location permission is denied for a storage point", async () => {
    const user = userEvent.setup();
    Object.defineProperty(navigator, "geolocation", {
      configurable: true,
      value: {
        getCurrentPosition: vi.fn((_onSuccess, onError) => onError({ code: 1 })),
      },
    });
    renderApp("/storage-points/new");

    await user.click(await screen.findByRole("button", { name: "Use my location" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Location permission was denied",
    );
    expect(screen.getByLabelText("Latitude")).toHaveValue(null);
  });

  test("deletes a point after confirmation", async () => {
    const user = userEvent.setup();
    api.deleteStoragePoint.mockResolvedValue(undefined);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderApp("/storage-points/9");

    await user.click(await screen.findByRole("button", { name: "Delete" }));
    await waitFor(() => expect(api.deleteStoragePoint).toHaveBeenCalledWith(9));
    expect(await screen.findByRole("heading", { name: "No storage points registered" })).toBeInTheDocument();
  });

  test("saves when waste becomes available", async () => {
    const user = userEvent.setup();
    api.updateStoragePoint.mockResolvedValue(point);
    renderApp("/storage-points/9/edit");

    const field = await screen.findByLabelText("Waste available from");
    fireEvent.change(field, { target: { value: "2026-11-03T09:30" } });
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(api.updateStoragePoint).toHaveBeenCalledWith(
      "9",
      expect.objectContaining({ available_from: "2026-11-03T09:30" }),
    ));
  });
});
