import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import App from "../App.jsx";
import { TOKEN_STORAGE_KEY } from "../auth/AuthContext.jsx";

// The API module is the one boundary these tests replace: the endpoints
// themselves are covered by the backend suite. Everything inside the
// React app runs for real, including routing and the auth guard.
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

const USER = { id: 1, name: "Asha Rao", email: "asha@example.com", role: "planner" };

const EMPTY_SUMMARY = {
  total_waste_kg: 0,
  storage_points_count: 0,
  available_vehicles_count: 0,
  facility_remaining_capacity_kg: 0,
  total_scenarios: 0,
  optimized_routes_count: 0,
  facility_configured: false,
  waste_overview: {
    total_waste_kg: 0,
    storage_points_count: 0,
    largest_point_kg: 0,
    average_point_kg: 0,
  },
  vehicle_status: {
    available: [],
    unavailable: [],
    available_count: 0,
    unavailable_count: 0,
    total_available_capacity_kg: 0,
  },
  storage_points: [],
  recent_scenarios: [],
  optimization_summary: {
    successful_runs: 0,
    failed_runs: 0,
    total_runs: 0,
    best_distance_km: null,
  },
};

const POPULATED_SUMMARY = {
  ...EMPTY_SUMMARY,
  total_waste_kg: 4510.5,
  storage_points_count: 6,
  available_vehicles_count: 1,
  facility_remaining_capacity_kg: 7000,
  total_scenarios: 1,
  optimized_routes_count: 2,
  facility_configured: true,
  waste_overview: {
    total_waste_kg: 4510.5,
    storage_points_count: 6,
    largest_point_kg: 1200,
    average_point_kg: 751.75,
  },
  vehicle_status: {
    available: [
      { id: 1, name: "Vehicle 1", capacity_kg: 3000, is_available: true, scenario_reference: "SC-9001" },
    ],
    unavailable: [
      { id: 2, name: "Vehicle 2", capacity_kg: 3000, is_available: false, scenario_reference: "SC-9001" },
    ],
    available_count: 1,
    unavailable_count: 1,
    total_available_capacity_kg: 3000,
  },
  storage_points: [
    {
      id: 1,
      name: "Ward 4 market",
      latitude: 11.0168,
      longitude: 76.9558,
      waste_kg: 1200,
      waste_type: null,
      available_from: null,
      scenario_reference: "SC-9001",
    },
  ],
  recent_scenarios: [
    {
      id: 1,
      reference: "SC-9001",
      name: "S01 normal feasible",
      status: "draft",
      created_at: "2026-10-31T09:15:00",
      storage_points_count: 6,
      vehicles_count: 2,
    },
  ],
  optimization_summary: {
    successful_runs: 2,
    failed_runs: 1,
    total_runs: 3,
    best_distance_km: 17.45,
  },
};

function renderApp(path = "/dashboard") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

/**
 * Find one summary card by its label.
 *
 * Several card labels are also sidebar link labels, so the search is
 * confined to the card grid.
 */
async function findCard(label) {
  const grid = await screen.findByTestId("stat-grid");
  return within(grid).getByText(label).closest("article");
}

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
});

afterEach(() => {
  localStorage.clear();
});

describe("protected routes", () => {
  test("an unauthenticated visitor to the dashboard is sent to the login page", async () => {
    renderApp("/dashboard");

    expect(await screen.findByRole("heading", { name: /good to see you/i })).toBeInTheDocument();
    expect(api.getDashboardSummary).not.toHaveBeenCalled();
  });

  test("a stored token that the API rejects does not open the dashboard", async () => {
    localStorage.setItem(TOKEN_STORAGE_KEY, "expired-token");
    api.getCurrentUser.mockRejectedValue(
      Object.assign(new Error("Your session has expired."), { status: 401 }),
    );

    renderApp("/dashboard");

    expect(await screen.findByRole("heading", { name: /good to see you/i })).toBeInTheDocument();
    expect(localStorage.getItem(TOKEN_STORAGE_KEY)).toBeNull();
  });

  test("a stored token that the API accepts opens the dashboard", async () => {
    localStorage.setItem(TOKEN_STORAGE_KEY, "good-token");
    api.getCurrentUser.mockResolvedValue(USER);
    api.getDashboardSummary.mockResolvedValue(EMPTY_SUMMARY);
    api.getScenarios.mockResolvedValue([]);
    api.getDepots.mockResolvedValue([]);
    api.getVehicles.mockResolvedValue([]);

    renderApp("/dashboard");

    expect(await screen.findByRole("heading", { name: /good to see you, asha/i })).toBeInTheDocument();
  });
});

describe("signing in", () => {
  test("the dashboard opens after a successful login", async () => {
    api.login.mockResolvedValue({ access_token: "fresh-token", user: USER });
    api.getDashboardSummary.mockResolvedValue(EMPTY_SUMMARY);
    renderApp("/login");

    await userEvent.type(screen.getByLabelText(/email address/i), USER.email);
    const password = screen.getByLabelText(/^password$/i);
    await userEvent.type(password, "original-password-123");
    await userEvent.click(
      within(password.closest("form")).getByRole("button", { name: /sign in/i }),
    );

    expect(await screen.findByRole("heading", { name: /good to see you, asha/i })).toBeInTheDocument();
    expect(localStorage.getItem(TOKEN_STORAGE_KEY)).toBe("fresh-token");
  });

  test("a rejected login keeps the user on the login page and shows the reason", async () => {
    api.login.mockRejectedValue(
      Object.assign(new Error("Email or password is incorrect."), { status: 401 }),
    );
    renderApp("/login");

    await userEvent.type(screen.getByLabelText(/email address/i), USER.email);
    const password = screen.getByLabelText(/^password$/i);
    await userEvent.type(password, "wrong-password");
    await userEvent.click(
      within(password.closest("form")).getByRole("button", { name: /sign in/i }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(/incorrect/i);
    expect(localStorage.getItem(TOKEN_STORAGE_KEY)).toBeNull();
  });
});

describe("summary cards", () => {
  beforeEach(() => {
    localStorage.setItem(TOKEN_STORAGE_KEY, "good-token");
    api.getCurrentUser.mockResolvedValue(USER);
  });

  test("an empty database shows zero on every card", async () => {
    api.getDashboardSummary.mockResolvedValue(EMPTY_SUMMARY);
    renderApp("/dashboard");

    const cards = {
      "Total Waste": "0 kg",
      "Storage Points": "0",
      "Available Vehicles": "0",
      "Total Scenarios": "0",
      "Optimized Routes": "0",
    };
    for (const [label, value] of Object.entries(cards)) {
      const card = await findCard(label);
      expect(within(card).getByText(value)).toBeInTheDocument();
    }
  });

  test("an unconfigured facility reads 'Not configured' rather than zero", async () => {
    api.getDashboardSummary.mockResolvedValue(EMPTY_SUMMARY);
    renderApp("/dashboard");

    const card = await findCard("Facility Capacity");
    expect(within(card).getByText("Not configured")).toBeInTheDocument();
  });

  test("the cards show the values the API returned", async () => {
    api.getDashboardSummary.mockResolvedValue(POPULATED_SUMMARY);
    renderApp("/dashboard");

    const expected = {
      "Total Waste": "4,510.5 kg",
      "Storage Points": "6",
      "Available Vehicles": "1",
      "Facility Capacity": "7,000 kg",
      "Total Scenarios": "1",
      "Optimized Routes": "2",
    };
    for (const [label, value] of Object.entries(expected)) {
      const card = await findCard(label);
      expect(within(card).getByText(value)).toBeInTheDocument();
    }
  });

  test("a failing request shows an error instead of zeros", async () => {
    api.getDashboardSummary.mockRejectedValue(new Error("Unable to reach the NagarFlow API."));
    renderApp("/dashboard");

    expect(await screen.findByRole("alert")).toHaveTextContent(/unable to reach/i);
    expect(screen.queryByText("Total Waste")).not.toBeInTheDocument();
  });
});

describe("dashboard sections", () => {
  beforeEach(() => {
    localStorage.setItem(TOKEN_STORAGE_KEY, "good-token");
    api.getCurrentUser.mockResolvedValue(USER);
  });

  test("all five sections are present", async () => {
    api.getDashboardSummary.mockResolvedValue(POPULATED_SUMMARY);
    renderApp("/dashboard");

    for (const title of [
      "Waste Overview",
      "Vehicle Status",
      "Storage Point Overview",
      "Recent Scenarios",
      "Optimization Summary",
    ]) {
      expect(await screen.findByRole("heading", { name: title })).toBeInTheDocument();
    }
  });

  test("sections list the real rows from the API", async () => {
    api.getDashboardSummary.mockResolvedValue(POPULATED_SUMMARY);
    renderApp("/dashboard");

    expect(await screen.findByText("Ward 4 market")).toBeInTheDocument();
    expect(screen.getByText("S01 normal feasible")).toBeInTheDocument();
    expect(screen.getByText("SC-9001")).toBeInTheDocument();
    expect(screen.getByText("Vehicle 1")).toBeInTheDocument();
    expect(screen.getByText("17.45 km")).toBeInTheDocument();
  });

  test("empty sections say so instead of showing invented rows", async () => {
    api.getDashboardSummary.mockResolvedValue(EMPTY_SUMMARY);
    renderApp("/dashboard");

    expect(await screen.findByText(/no waste quantities recorded yet/i)).toBeInTheDocument();
    expect(screen.getByText(/no vehicles registered yet/i)).toBeInTheDocument();
    expect(screen.getByText(/no storage points registered yet/i)).toBeInTheDocument();
    expect(screen.getByText(/no scenarios saved yet/i)).toBeInTheDocument();
    expect(screen.getByText(/no optimization has been run yet/i)).toBeInTheDocument();
  });
});

describe("sidebar navigation", () => {
  beforeEach(() => {
    localStorage.setItem(TOKEN_STORAGE_KEY, "good-token");
    api.getCurrentUser.mockResolvedValue(USER);
    api.getDashboardSummary.mockResolvedValue(EMPTY_SUMMARY);
  });

  test("every sidebar destination is listed", async () => {
    renderApp("/dashboard");
    const nav = await screen.findByRole("navigation", { name: /main navigation/i });

    for (const label of [
      "Dashboard",
      "Scenarios",
      "Depot Management",
      "Vehicles",
      "Storage Points",
      "Processing Facility",
      "Route Optimization",
      "Reports",
      "Settings",
    ]) {
      expect(within(nav).getByRole("link", { name: label })).toBeInTheDocument();
    }
    expect(screen.getByRole("button", { name: /logout/i })).toBeInTheDocument();
  });

  test("clicking a sidebar link navigates to that page", async () => {
    renderApp("/dashboard");
    const nav = await screen.findByRole("navigation", { name: /main navigation/i });

    await userEvent.click(within(nav).getByRole("link", { name: "Scenarios" }));

    expect(await screen.findByRole("heading", { name: "Scenarios" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "No scenarios yet" })).toBeInTheDocument();
  });

  test("the current page is marked as active for assistive technology", async () => {
    renderApp("/dashboard");
    const nav = await screen.findByRole("navigation", { name: /main navigation/i });

    expect(within(nav).getByRole("link", { name: "Dashboard" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });
});

describe("logout", () => {
  test("logging out clears the session and returns to the login page", async () => {
    localStorage.setItem(TOKEN_STORAGE_KEY, "good-token");
    api.getCurrentUser.mockResolvedValue(USER);
    api.getDashboardSummary.mockResolvedValue(EMPTY_SUMMARY);
    renderApp("/dashboard");

    await screen.findByRole("heading", { name: /good to see you, asha/i });
    await userEvent.click(screen.getByRole("button", { name: /logout/i }));

    await waitFor(() => {
      expect(localStorage.getItem(TOKEN_STORAGE_KEY)).toBeNull();
    });
    expect(await screen.findByRole("heading", { name: /good to see you\./i })).toBeInTheDocument();
  });
});

describe("password reset link", () => {
  test("opening a reset link verifies the token and shows the new-password form", async () => {
    api.verifyResetToken.mockResolvedValue({ valid: true, email: USER.email });
    renderApp("/reset-password?token=a-real-token");

    expect(await screen.findByRole("heading", { name: /choose a new password/i })).toBeInTheDocument();
    expect(api.verifyResetToken).toHaveBeenCalledWith("a-real-token");
  });

  test("a rejected reset link explains itself instead of showing the form", async () => {
    api.verifyResetToken.mockRejectedValue(
      Object.assign(new Error("This password reset link is invalid or has expired."), { status: 400 }),
    );
    renderApp("/reset-password?token=stale-token");

    expect(await screen.findByRole("heading", { name: /no longer works/i })).toBeInTheDocument();
    expect(screen.queryByLabelText(/new password/i)).not.toBeInTheDocument();
  });
});
