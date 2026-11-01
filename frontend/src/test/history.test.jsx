import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";
import App from "../App.jsx";
import { TOKEN_STORAGE_KEY } from "../auth/AuthContext.jsx";

vi.mock("../components/RouteMap.jsx", () => ({
  default: () => <div data-testid="route-map" />,
}));

vi.mock("../services/api.js", () => ({
  getCurrentUser: vi.fn(),
  getScenarios: vi.fn(),
  getOptimizationHistory: vi.fn(),
  getOptimizationBatch: vi.fn(),
  getLatestOptimization: vi.fn(),
  optimizeScenario: vi.fn(),
}));

const api = await import("../services/api.js");

const ROW = {
  scenario_id: 4,
  scenario_name: "Weekly collection",
  batch_id: "abc",
  created_at: "2026-11-02T10:00:00",
  greedy_status: "feasible",
  greedy_distance_m: 12500,
  or_tools_status: "feasible",
  or_tools_distance_m: 10000,
  difference_m: 2500,
};

const FAILED_ROW = {
  ...ROW,
  batch_id: "def",
  scenario_name: "Tight shift",
  greedy_status: "no_solution",
  greedy_distance_m: null,
  difference_m: null,
};

const RUN = { status: "feasible", total_distance_m: 12500, solve_ms: 10, message: "", routes: [
  { vehicle_id: 1, vehicle_name: "Truck", capacity_kg: 100, load_kg: 50, distance_m: 12500,
    finish_s: 600, stops: [], geometry: [] },
] };

const COMPARISON = {
  scenario_id: 4,
  batch_id: "abc",
  created_at: "2026-11-02T10:00:00",
  input_hash: "x",
  greedy: RUN,
  or_tools: { ...RUN, total_distance_m: 10000 },
  difference_m: 2500,
  difference_pct: 20,
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
  api.getCurrentUser.mockResolvedValue({ id: 1, name: "Asha Rao", email: "asha@example.com" });
  api.getScenarios.mockResolvedValue([{ id: 4, name: "Weekly collection" }]);
  api.getOptimizationHistory.mockResolvedValue({ items: [ROW, FAILED_ROW], total: 2 });
  api.getOptimizationBatch.mockResolvedValue(COMPARISON);
  api.getLatestOptimization.mockResolvedValue(COMPARISON);
});

describe("History page", () => {
  test("it lists runs in the order the API gives", async () => {
    renderApp("/history");

    const links = await screen.findAllByRole("link", { name: /Weekly collection|Tight shift/ });
    expect(links.map((link) => link.textContent)).toEqual(["Weekly collection", "Tight shift"]);
    expect(screen.getByText("12.50 km")).toBeInTheDocument();
  });

  test("it filters by scenario", async () => {
    renderApp("/history");
    await screen.findAllByRole("link", { name: "Weekly collection" });

    await userEvent.selectOptions(screen.getByLabelText("Scenario"), "4");

    await waitFor(() => expect(api.getOptimizationHistory).toHaveBeenLastCalledWith(
      expect.objectContaining({ scenario_id: "4", offset: 0 }),
    ));
  });

  test("it filters by status", async () => {
    renderApp("/history");
    await screen.findAllByRole("link", { name: "Weekly collection" });

    await userEvent.selectOptions(screen.getByLabelText("Status"), "no_solution");

    await waitFor(() => expect(api.getOptimizationHistory).toHaveBeenLastCalledWith(
      expect.objectContaining({ status: "no_solution" }),
    ));
  });

  test("it pages through runs", async () => {
    api.getOptimizationHistory.mockResolvedValue({ items: [ROW], total: 30 });
    renderApp("/history");

    await userEvent.click(await screen.findByRole("button", { name: "Next" }));

    await waitFor(() => expect(api.getOptimizationHistory).toHaveBeenLastCalledWith(
      expect.objectContaining({ offset: 25 }),
    ));
  });

  test("it opens a saved run", async () => {
    renderApp("/history/4/abc");

    expect(await screen.findByRole("heading", { name: "Greedy" })).toBeInTheDocument();
    expect(api.getOptimizationBatch).toHaveBeenCalledWith("4", "abc");
    expect(await screen.findByTestId("route-map")).toBeInTheDocument();
  });

  test("it shows no distance for a failed method", async () => {
    renderApp("/history");

    await screen.findAllByRole("link", { name: "Tight shift" });
    expect(screen.getByRole("cell", { name: "No route found" })).toBeInTheDocument();
    expect(screen.queryByText("0.00 km")).not.toBeInTheDocument();
  });

  test("it shows an empty state", async () => {
    api.getOptimizationHistory.mockResolvedValue({ items: [], total: 0 });
    renderApp("/history");

    expect(await screen.findByText("No optimization runs yet.")).toBeInTheDocument();
  });

  test("the route page shows when a result was run", async () => {
    renderApp("/route-optimization?scenario=4");

    expect(await screen.findByText(/^Run on /)).toBeInTheDocument();
  });
});
