import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";
import App from "../App.jsx";
import { TOKEN_STORAGE_KEY } from "../auth/AuthContext.jsx";

vi.mock("../services/api.js");

const api = await import("../services/api.js");

const BANNER = "Synthetic preview, not a dispatch instruction";
const ROUTES = {
  scenario_name: "Plan", method: "or_tools", out_of_date: false,
  routes: [{
    vehicle_name: "Truck 1",
    stops: [{ code: "P1", name: "Market", quantity_kg: 250, arrival_s: 600, wait_s: 0 }],
  }],
};
const FACILITY = {
  scenario_name: "Plan", method: "or_tools", out_of_date: false, expected_total_kg: 900,
  facility_capacity_kg: 20000,
  vehicles: [{ vehicle_name: "Truck 1", load_kg: 900, capacity_kg: 6000 }],
};

function missing() {
  const failure = new Error("The API does not have this endpoint.");
  failure.status = 404;
  return failure;
}

async function openAs(role) {
  const user = userEvent.setup();
  api.getCurrentUser.mockResolvedValue({ id: 1, name: "A", email: "a@example.com", role });
  render(
    <MemoryRouter initialEntries={["/route-preview"]}>
      <App />
    </MemoryRouter>,
  );
  await user.selectOptions(await screen.findByLabelText("Scenario"), await screen.findByRole("option", { name: "Plan" }));
}

beforeEach(() => {
  vi.resetAllMocks();
  localStorage.setItem(TOKEN_STORAGE_KEY, "token");
  api.getScenarioNames.mockResolvedValue([{ id: 7, name: "Plan" }]);
  api.getRoutePreview.mockResolvedValue(ROUTES);
  api.getFacilityPreview.mockResolvedValue(FACILITY);
});

describe("route preview page", () => {
  test("always shows the synthetic preview banner", async () => {
    api.getCurrentUser.mockResolvedValue({ id: 1, name: "A", email: "a@example.com", role: "driver" });
    render(
      <MemoryRouter initialEntries={["/route-preview"]}>
        <App />
      </MemoryRouter>,
    );

    expect(await screen.findByText(BANNER)).toBeInTheDocument();
  });

  test("shows a driver stops, quantities and planned times but no facility section", async () => {
    await openAs("driver");

    expect(await screen.findByText("Market")).toBeInTheDocument();
    expect(screen.getByText("250 kg")).toBeInTheDocument();
    expect(screen.getByText("10 min after leaving the depot")).toBeInTheDocument();
    expect(api.getFacilityPreview).not.toHaveBeenCalled();
  });

  test("shows a facility account loads against capacity but no stops", async () => {
    await openAs("facility");

    expect(await screen.findByText("900 kg of 6,000 kg")).toBeInTheDocument();
    expect(screen.getByText("900 kg expected, facility capacity 20,000 kg")).toBeInTheDocument();
    expect(api.getRoutePreview).not.toHaveBeenCalled();
  });

  test("shows a planner both sections", async () => {
    await openAs("planner");

    expect(await screen.findByText("Market")).toBeInTheDocument();
    expect(screen.getByText("900 kg of 6,000 kg")).toBeInTheDocument();
  });

  test("says no saved route exists on a 404, not that the server is old", async () => {
    api.getRoutePreview.mockRejectedValue(missing());
    await openAs("driver");

    expect(await screen.findByText("No saved route exists for this scenario.")).toBeInTheDocument();
    expect(screen.queryByText(/does not have this endpoint/)).not.toBeInTheDocument();
  });

  test("shows other failures plainly", async () => {
    api.getRoutePreview.mockRejectedValue(new Error("Something went wrong on the server."));
    await openAs("driver");

    expect(await screen.findByText("Something went wrong on the server.")).toBeInTheDocument();
  });

  test("flags an out-of-date preview", async () => {
    api.getRoutePreview.mockResolvedValue({ ...ROUTES, out_of_date: true });
    await openAs("driver");

    await waitFor(() => expect(
      screen.getByText("This scenario changed after the run, so this preview may no longer match it."),
    ).toBeInTheDocument());
  });
});
