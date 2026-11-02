import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";
import App from "../App.jsx";
import { TOKEN_STORAGE_KEY } from "../auth/AuthContext.jsx";

vi.mock("../services/api.js", () => ({
  getCurrentUser: vi.fn(),
  loadEvaluationScenarios: vi.fn(),
  getEvaluationReport: vi.fn(),
  downloadEvaluationCsv: vi.fn(),
  optimizeScenario: vi.fn(),
}));

const api = await import("../services/api.js");

const METHOD = {
  status: "feasible",
  message: "",
  distance_m: 12500,
  vehicle_loads: [{ vehicle_name: "Truck", load_kg: 500, capacity_kg: 6000 }],
  facility_load_kg: 500,
  facility_capacity_kg: 20000,
};

function row(number, overrides = {}) {
  const code = `S${String(number).padStart(2, "0")}`;
  return {
    code,
    name: `SYNTH-${code} Case`,
    purpose: "Purpose",
    state: "not_run",
    scenario_id: number,
    errors: [],
    greedy: null,
    or_tools: null,
    difference_m: null,
    difference_pct: null,
    input_hash: null,
    provenance: null,
    edited: false,
    matches_expected: null,
    ...overrides,
  };
}

function report(overrides = {}) {
  return {
    rows: Array.from({ length: 10 }, (_, index) => row(index + 1, overrides[index + 1])),
    summary: {
      not_loaded: 0, not_run: 10, blocked: 0, ran: 0, both_routes: 0,
      mean_difference_m: null, mean_difference_pct: null,
    },
    catalog_version: "1",
    synthetic: true,
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/reports"]}>
      <App />
    </MemoryRouter>,
  );
}

function rowOf(code) {
  return screen.getByRole("row", { name: new RegExp(`^${code}\\b`) });
}

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  localStorage.setItem(TOKEN_STORAGE_KEY, "token");
  api.getCurrentUser.mockResolvedValue({ id: 1, name: "Asha Rao", email: "asha@example.com", role: "planner" });
  api.getEvaluationReport.mockResolvedValue(report());
  api.loadEvaluationScenarios.mockResolvedValue([]);
  api.optimizeScenario.mockResolvedValue({});
});

describe("Reports page", () => {
  test("it shows all ten cases", async () => {
    renderPage();

    await screen.findByText("SYNTH-S01 Case");
    expect(screen.getByText("SYNTH-S10 Case")).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(11);
  });

  test("it labels the results synthetic", async () => {
    renderPage();

    expect(await screen.findByText(/synthetic/i)).toBeInTheDocument();
  });

  test("it loads the scenarios", async () => {
    renderPage();
    await screen.findByText("SYNTH-S01 Case");

    await userEvent.click(screen.getByRole("button", { name: "Load evaluation scenarios" }));

    await waitFor(() => expect(api.loadEvaluationScenarios).toHaveBeenCalledOnce());
    await waitFor(() => expect(api.getEvaluationReport).toHaveBeenCalledTimes(2));
  });

  test("run all goes through each case in order and skips unloaded ones", async () => {
    api.getEvaluationReport.mockResolvedValue(report({
      3: { state: "not_loaded", scenario_id: null },
    }));
    renderPage();
    await screen.findByText("SYNTH-S01 Case");

    await userEvent.click(screen.getByRole("button", { name: "Run all" }));

    await waitFor(() => expect(api.optimizeScenario).toHaveBeenCalledTimes(9));
    expect(api.optimizeScenario.mock.calls.map(([id]) => id)).toEqual(
      [1, 2, 4, 5, 6, 7, 8, 9, 10],
    );
    await waitFor(() => expect(api.getEvaluationReport).toHaveBeenCalledTimes(2));
  });

  test("it shows progress during a run", async () => {
    api.optimizeScenario.mockReturnValue(new Promise(() => {}));
    renderPage();
    await screen.findByText("SYNTH-S01 Case");

    await userEvent.click(screen.getByRole("button", { name: "Run all" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Running S01, 1 of 10");
  });

  test("a blocked case does not stop the run", async () => {
    api.optimizeScenario.mockImplementation(async (id) => {
      if (id === 4) throw Object.assign(new Error("Blocked"), { status: 409 });
      return {};
    });
    renderPage();
    await screen.findByText("SYNTH-S01 Case");

    await userEvent.click(screen.getByRole("button", { name: "Run all" }));

    await waitFor(() => expect(api.optimizeScenario).toHaveBeenCalledTimes(10));
    await waitFor(() => expect(api.getEvaluationReport).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  test("a server error on one case does not stop the run and is shown", async () => {
    api.optimizeScenario.mockImplementation(async (id) => {
      if (id === 2) throw Object.assign(new Error("Server broke."), { status: 500 });
      return {};
    });
    renderPage();
    await screen.findByText("SYNTH-S01 Case");

    await userEvent.click(screen.getByRole("button", { name: "Run all" }));

    await waitFor(() => expect(api.optimizeScenario).toHaveBeenCalledTimes(10));
    expect(await screen.findByRole("alert")).toHaveTextContent("S02: Server broke.");
  });

  test("a busy optimizer fails that case and the run carries on", async () => {
    api.optimizeScenario.mockImplementation(async (id) => {
      if (id === 3) {
        throw Object.assign(new Error("The optimizer is busy. Try again shortly."), { status: 503 });
      }
      return {};
    });
    renderPage();
    await screen.findByText("SYNTH-S01 Case");

    await userEvent.click(screen.getByRole("button", { name: "Run all" }));

    await waitFor(() => expect(api.optimizeScenario).toHaveBeenCalledTimes(10));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "S03: The optimizer is busy. Try again shortly.",
    );
  });

  test("it shows no distance for a blocked case", async () => {
    api.getEvaluationReport.mockResolvedValue(report({
      5: {
        state: "blocked",
        errors: [{ code: "FACILITY_CAPACITY", message: "Too much waste." }],
      },
    }));
    renderPage();
    await screen.findByText("SYNTH-S01 Case");

    const blocked = rowOf("S05");
    expect(within(blocked).getByText("Blocked")).toBeInTheDocument();
    expect(within(blocked).getByText(/Too much waste\./)).toBeInTheDocument();
    expect(blocked).not.toHaveTextContent(/\bkm\b/);
  });

  test("it shows the difference only where both found routes", async () => {
    api.getEvaluationReport.mockResolvedValue(report({
      1: {
        state: "ran", greedy: METHOD, or_tools: { ...METHOD, distance_m: 10000 },
        difference_m: 2500, difference_pct: 20,
      },
      2: {
        state: "ran",
        greedy: { ...METHOD, status: "no_solution", message: "No route.", distance_m: null },
        or_tools: METHOD,
      },
    }));
    renderPage();
    await screen.findByText("SYNTH-S01 Case");

    expect(rowOf("S01")).toHaveTextContent("2.50 km (20%)");
    expect(rowOf("S02")).toHaveTextContent("No route found");
    expect(rowOf("S02")).not.toHaveTextContent("%");
  });

  test("it marks an out of date run", async () => {
    api.getEvaluationReport.mockResolvedValue(report({
      1: { state: "out_of_date", greedy: METHOD, or_tools: METHOD },
    }));
    renderPage();
    await screen.findByText("SYNTH-S01 Case");

    expect(rowOf("S01")).toHaveTextContent("Out of date");
    expect(rowOf("S01")).toHaveTextContent("changed after this run");
  });

  test("it flags an edited case and an unexpected outcome", async () => {
    api.getEvaluationReport.mockResolvedValue(report({
      1: { state: "ran", greedy: METHOD, or_tools: METHOD, edited: true, matches_expected: false },
    }));
    renderPage();
    await screen.findByText("SYNTH-S01 Case");

    expect(rowOf("S01")).toHaveTextContent("Edited since loading");
    expect(rowOf("S01")).toHaveTextContent("Differs from the expected outcome");
  });

  test("it never says optimal", async () => {
    api.getEvaluationReport.mockResolvedValue(report({
      1: { state: "ran", greedy: METHOD, or_tools: METHOD, difference_m: 0, difference_pct: 0 },
    }));
    renderPage();
    await screen.findByText("SYNTH-S01 Case");

    expect(screen.queryByText(/optimal/i)).not.toBeInTheDocument();
  });

  test("it downloads the CSV", async () => {
    renderPage();
    await screen.findByText("SYNTH-S01 Case");

    await userEvent.click(screen.getByRole("button", { name: "Download CSV" }));

    expect(api.downloadEvaluationCsv).toHaveBeenCalledOnce();
  });

  test("it locks the buttons during a run", async () => {
    api.optimizeScenario.mockReturnValue(new Promise(() => {}));
    renderPage();
    await screen.findByText("SYNTH-S01 Case");

    await userEvent.click(screen.getByRole("button", { name: "Run all" }));

    expect(await screen.findByRole("button", { name: "Load evaluation scenarios" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Run all" })).toBeDisabled();
  });
});
