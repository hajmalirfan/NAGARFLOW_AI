import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";
import App from "../App.jsx";
import { TOKEN_STORAGE_KEY } from "../auth/AuthContext.jsx";

vi.mock("../components/RouteMap.jsx", () => ({
  default: ({ routes }) => (
    <div data-testid="route-map">{routes.map((route) => route.vehicle_name).join(",")}</div>
  ),
}));

vi.mock("../services/api.js", () => ({
  getCurrentUser: vi.fn(),
  getDashboardSummary: vi.fn(),
  getScenarios: vi.fn(),
  getScenario: vi.fn(),
  optimizeScenario: vi.fn(),
  getLatestOptimization: vi.fn(),
}));

const api = await import("../services/api.js");

const scenario = { id: 4, reference: "SC-0004", name: "Weekly collection" };

function route(name, distance) {
  return {
    vehicle_id: 1,
    vehicle_name: name,
    capacity_kg: 5000,
    load_kg: 3000,
    distance_m: distance,
    finish_s: 1800,
    stops: [{ code: "SP001", arrival_s: 600, service_s: 900, wait_s: 300 }],
    geometry: [[78.7, 10.8], [78.71, 10.81]],
  };
}

const COMPARISON = {
  scenario_id: 4,
  batch_id: "abc",
  created_at: "2026-11-03T09:00:00",
  greedy: { status: "feasible", total_distance_m: 12500, solve_ms: 2, message: "", routes: [route("Greedy truck", 12500)] },
  or_tools: { status: "feasible", total_distance_m: 10000, solve_ms: 10000, message: "", routes: [route("Solver truck", 10000)] },
  difference_m: 2500,
  difference_pct: 20,
};

const FAILED_GREEDY = {
  ...COMPARISON,
  greedy: { status: "no_solution", total_distance_m: null, solve_ms: 2, message: "No vehicle could take: SP003.", routes: [] },
  difference_m: null,
  difference_pct: null,
};

const BLOCKED_REPORT = {
  scenario_id: 4,
  validation_status: "invalid",
  can_optimize: false,
  checks: { road_connectivity: "failed" },
  errors: [{ code: "ROAD_TOO_FAR", message: "These locations are more than 200 m from a usable road: SP001." }],
  warnings: [],
  total_waste_kg: 6000,
  storage_point_count: 6,
  feasible_assignment: null,
};

function renderApp(path = "/route-optimization?scenario=4") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

async function runOptimization() {
  renderApp();
  await userEvent.click(await screen.findByRole("button", { name: /run optimization/i }));
}

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  localStorage.setItem(TOKEN_STORAGE_KEY, "token");
  api.getCurrentUser.mockResolvedValue({ id: 1, name: "Asha Rao", email: "asha@example.com" });
  api.getScenarios.mockResolvedValue([scenario]);
  api.getLatestOptimization.mockRejectedValue(Object.assign(new Error("none"), { status: 404 }));
  api.optimizeScenario.mockResolvedValue(COMPARISON);
});

describe("Route Optimization page", () => {
  test("it preselects the scenario from the URL", async () => {
    renderApp();

    await waitFor(async () => expect(await screen.findByLabelText("Scenario")).toHaveValue("4"));
    await waitFor(() => expect(api.getLatestOptimization).toHaveBeenCalledWith("4"));
  });

  test("it shows both methods after a run", async () => {
    await runOptimization();

    expect(await screen.findByRole("heading", { name: "Greedy" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "OR-Tools" })).toBeInTheDocument();
    expect(screen.getByText("12.50 km")).toBeInTheDocument();
    expect(screen.getByText("10.00 km")).toBeInTheDocument();
    expect(api.optimizeScenario).toHaveBeenCalledWith("4");
  });

  test("it shows the saved result without running again", async () => {
    api.getLatestOptimization.mockResolvedValue(COMPARISON);
    renderApp();

    expect(await screen.findByText("12.50 km")).toBeInTheDocument();
    expect(api.optimizeScenario).not.toHaveBeenCalled();
  });

  test("it states the difference when both are feasible", async () => {
    await runOptimization();

    expect(await screen.findByText(/OR-Tools is 2.50 km shorter \(20%\)/)).toBeInTheDocument();
  });

  test("it hides distance for a failed method", async () => {
    api.optimizeScenario.mockResolvedValue(FAILED_GREEDY);
    await runOptimization();

    const card = (await screen.findByRole("heading", { name: "Greedy" })).closest("article");
    expect(within(card).getByText("No route found")).toBeInTheDocument();
    expect(within(card).getByText("No vehicle could take: SP003.")).toBeInTheDocument();
    expect(within(card).queryByText(/ km$/)).not.toBeInTheDocument();
  });

  test("it hides the difference unless both are feasible", async () => {
    api.optimizeScenario.mockResolvedValue(FAILED_GREEDY);
    await runOptimization();

    await screen.findByRole("heading", { name: "Greedy" });
    expect(screen.queryByText(/shorter/)).not.toBeInTheDocument();
  });

  test("it shows validation errors when blocked", async () => {
    api.optimizeScenario.mockRejectedValue(
      Object.assign(new Error("blocked"), { status: 409, report: BLOCKED_REPORT }),
    );
    await runOptimization();

    expect(await screen.findByText("ROAD_TOO_FAR")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Greedy" })).not.toBeInTheDocument();
  });

  test("it says best found rather than optimal", async () => {
    await runOptimization();

    expect(await screen.findAllByText("Best found")).toHaveLength(2);
    expect(screen.queryByText(/optimal/i)).not.toBeInTheDocument();
  });

  test("it labels times as estimates", async () => {
    await runOptimization();

    expect(await screen.findByText(/assumed road speeds/i)).toBeInTheDocument();
  });

  test("it switches the map between algorithms", async () => {
    await runOptimization();

    expect(await screen.findByTestId("route-map")).toHaveTextContent("Solver truck");
    await userEvent.click(screen.getByRole("button", { name: "Show Greedy routes" }));
    expect(screen.getByTestId("route-map")).toHaveTextContent("Greedy truck");
  });

  test("it locks the scenario choice while a run is in progress", async () => {
    api.optimizeScenario.mockReturnValue(new Promise(() => {}));
    renderApp();

    await userEvent.click(await screen.findByRole("button", { name: "Run optimization" }));

    expect(await screen.findByLabelText("Scenario")).toBeDisabled();
  });

  test("it shows each vehicle's stops with waiting time", async () => {
    await runOptimization();

    expect(await screen.findByText("SP001")).toBeInTheDocument();
    expect(screen.getByText(/waits 5 min/)).toBeInTheDocument();
  });
});
