import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";
import App from "../App.jsx";
import { TOKEN_STORAGE_KEY } from "../auth/AuthContext.jsx";
import { can } from "../auth/permissions.js";

vi.mock("../services/api.js");

const api = await import("../services/api.js");

const DEPOT = {
  id: 1, name: "Main", code: "D1", address: "Trichy", latitude: 10.8, longitude: 78.7,
  is_active: true, created_at: "2026-01-01T00:00:00", updated_at: "2026-01-01T00:00:00",
};
const SCENARIO = {
  id: 1, reference: "S-1", name: "Plan", description: "", status: "draft", depot: DEPOT,
  processing_facility: null, vehicles: [], storage_points: [],
  created_at: "2026-01-01T00:00:00", updated_at: "2026-01-01T00:00:00",
};
const SAVED_VALIDATION = {
  id: 9, scenario_id: 1, validation_status: "invalid", can_optimize: false, checks: {},
  errors: [{ code: "FACILITY_CAPACITY", message: "Too much waste." }], warnings: [],
  total_waste_kg: 100, storage_point_count: 6,
};
const REPORT = {
  rows: [],
  synthetic: true,
  summary: {
    ran: 0, out_of_date: 0, blocked: 0, not_run: 0, not_loaded: 10, both_routes: 0,
    mean_difference_m: null, mean_difference_pct: null,
  },
};
const HISTORY = {
  total: 1, limit: 25, offset: 0,
  items: [{
    batch_id: "b1", scenario_id: 1, scenario_name: "Saved plan",
    created_at: "2026-01-01T00:00:00", greedy_status: "feasible", greedy_distance_m: 1000,
    or_tools_status: "feasible", or_tools_distance_m: 900, difference_m: 100,
  }],
};

const SIDEBARS = [
  ["reviewer", ["Dashboard", "Scenarios", "Depot Management", "Vehicles", "Storage Points",
    "Processing Facility", "Route Optimization", "History", "Reports", "Settings"]],
  ["management", ["Dashboard", "History", "Reports", "Settings"]],
  ["driver", ["Route Preview", "Settings"]],
  ["facility", ["Route Preview", "Settings"]],
];

function renderAt(path, role) {
  api.getCurrentUser.mockResolvedValue({ id: 1, name: "Asha Rao", email: "a@example.com", role });
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

async function sidebarLabels() {
  const nav = await screen.findByRole("navigation", { name: "Main navigation" });
  return within(nav).getAllByRole("link").map((link) => link.textContent);
}

beforeEach(() => {
  vi.resetAllMocks();
  localStorage.setItem(TOKEN_STORAGE_KEY, "token");
  api.getDashboardSummary.mockRejectedValue(new Error("Not needed here."));
  api.getDepots.mockResolvedValue([DEPOT]);
  api.getDepot.mockResolvedValue(DEPOT);
  api.getScenarios.mockResolvedValue([SCENARIO]);
  api.getScenario.mockResolvedValue(SCENARIO);
  api.getScenarioValidations.mockResolvedValue([]);
  api.getEvaluationReport.mockResolvedValue(REPORT);
  api.getOptimizationHistory.mockResolvedValue(HISTORY);
  api.getScenarioNames?.mockResolvedValue([]);
});

describe("role access", () => {
  test("treats an unknown role as having no access", () => {
    expect(can({ role: "admin" }, "records.read")).toBe(false);
    expect(can({}, "records.read")).toBe(false);
    expect(can(null, "records.read")).toBe(false);
  });

  test.each(SIDEBARS)("shows %s only its pages in the sidebar", async (role, labels) => {
    renderAt("/settings", role);

    expect(await sidebarLabels()).toEqual(labels);
  });

  test("shows a planner Team and Route Preview", async () => {
    renderAt("/settings", "planner");

    const labels = await sidebarLabels();
    expect(labels).toContain("Team");
    expect(labels).toContain("Route Preview");
  });

  test("sends a driver from /dashboard to /route-preview without a redirect loop", async () => {
    renderAt("/dashboard", "driver");

    expect(await screen.findByRole("heading", { name: "Route Preview" })).toBeInTheDocument();
    expect(api.getDashboardSummary).not.toHaveBeenCalled();
  });

  test("sends management from /depot to /dashboard", async () => {
    renderAt("/depot", "management");

    await waitFor(() => expect(api.getDashboardSummary).toHaveBeenCalled());
    expect(api.getDepots).not.toHaveBeenCalled();
  });

  test("sends a reviewer away from a form page", async () => {
    renderAt("/depot/new", "reviewer");

    await waitFor(() => expect(api.getDashboardSummary).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: /save|create/i })).not.toBeInTheDocument();
  });

  test("hides create from a reviewer on a list page", async () => {
    renderAt("/depot", "reviewer");

    expect(await screen.findByText("Main")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /add depot/i })).not.toBeInTheDocument();
  });

  test("hides edit and delete from a reviewer on a detail page", async () => {
    renderAt("/depot/1", "reviewer");

    expect(await screen.findByRole("heading", { name: "Main" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /edit depot/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /delete/i })).not.toBeInTheDocument();
  });

  test("hides Validate and Run from a reviewer on the scenario page", async () => {
    renderAt("/scenarios/1", "reviewer");

    expect(await screen.findByRole("heading", { name: "Plan" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /validate/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /proceed/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /edit scenario/i })).not.toBeInTheDocument();
  });

  test("shows a reviewer the newest saved validation", async () => {
    api.getScenarioValidations.mockResolvedValue([{
      ...SAVED_VALIDATION, created_at: "2026-02-02T00:00:00",
    }]);
    renderAt("/scenarios/1", "reviewer");

    expect(await screen.findByText("Scenario is not feasible")).toBeInTheDocument();
    expect(screen.getByText("Too much waste.")).toBeInTheDocument();
  });

  test("tells a reviewer when no validation has been saved", async () => {
    renderAt("/scenarios/1", "reviewer");

    expect(await screen.findByText("This scenario has not been validated yet.")).toBeInTheDocument();
  });

  test("flags a saved validation older than the scenario", async () => {
    api.getScenarioValidations.mockResolvedValue([{
      ...SAVED_VALIDATION, created_at: "2025-01-01T00:00:00",
    }]);
    renderAt("/scenarios/1", "reviewer");

    expect(await screen.findByText(
      "The scenario changed after this check, so it may no longer apply.",
    )).toBeInTheDocument();
  });

  test("hides Run from a reviewer on the route page", async () => {
    renderAt("/route-optimization", "reviewer");

    expect(await screen.findByRole("heading", { name: "Route Optimization" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /run optimization/i })).not.toBeInTheDocument();
  });

  test("hides Load and Run all from a reviewer on the report page", async () => {
    renderAt("/reports", "reviewer");

    expect(await screen.findByRole("button", { name: "Download CSV" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /load evaluation/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Run all" })).not.toBeInTheDocument();
  });

  test("shows management the history list without links to run details", async () => {
    renderAt("/history", "management");

    expect(await screen.findByText("Saved plan")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Saved plan" })).not.toBeInTheDocument();
    expect(api.getScenarios).not.toHaveBeenCalled();
    expect(screen.queryByLabelText("Scenario")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  test("still links history rows for a reviewer", async () => {
    renderAt("/history", "reviewer");

    expect(await screen.findByRole("link", { name: "Saved plan" })).toBeInTheDocument();
  });

  test("shows the role label instead of Municipal coordinator", async () => {
    renderAt("/settings", "driver");

    expect(await screen.findByText("Driver preview")).toBeInTheDocument();
    expect(screen.queryByText("Municipal coordinator")).not.toBeInTheDocument();
  });
});
