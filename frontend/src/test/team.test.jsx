import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";
import App from "../App.jsx";
import { TOKEN_STORAGE_KEY } from "../auth/AuthContext.jsx";

vi.mock("../services/api.js");

const api = await import("../services/api.js");

const MEMBER = { id: 5, name: "Ravi", email: "ravi@example.com", role: "reviewer" };

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/team"]}>
      <App />
    </MemoryRouter>,
  );
}

async function fillForm(user) {
  await user.type(await screen.findByLabelText("Name"), "Mala");
  await user.type(screen.getByLabelText("Email"), "mala@example.com");
  await user.selectOptions(screen.getByLabelText("Role"), "driver");
  await user.type(screen.getByLabelText("Temporary password"), "temporary-password-1");
  await user.click(screen.getByRole("button", { name: "Add account" }));
}

beforeEach(() => {
  vi.resetAllMocks();
  localStorage.setItem(TOKEN_STORAGE_KEY, "token");
  api.getCurrentUser.mockResolvedValue({
    id: 1, name: "Asha Rao", email: "asha@example.com", role: "planner",
  });
  api.getTeam.mockResolvedValue([MEMBER]);
});

describe("team page", () => {
  test("lists team accounts and adds one", async () => {
    const user = userEvent.setup();
    api.createTeamMember.mockResolvedValue({ ...MEMBER, id: 6, name: "Mala" });
    renderPage();

    expect(await screen.findByText("ravi@example.com")).toBeInTheDocument();
    await fillForm(user);

    await waitFor(() => expect(api.createTeamMember).toHaveBeenCalledWith({
      name: "Mala", email: "mala@example.com", role: "driver", password: "temporary-password-1",
    }));
    expect(api.getTeam).toHaveBeenCalledTimes(2);
  });

  test("does not offer Planner as a team role", async () => {
    renderPage();

    const options = within(await screen.findByLabelText("Role")).getAllByRole("option");
    expect(options.map((option) => option.textContent)).toEqual([
      "Reviewer", "Management", "Driver preview", "Facility preview",
    ]);
  });

  test("changes a role", async () => {
    const user = userEvent.setup();
    api.updateTeamMemberRole.mockResolvedValue({ ...MEMBER, role: "management" });
    renderPage();

    await user.selectOptions(await screen.findByLabelText("Role for Ravi"), "management");

    await waitFor(() => expect(api.updateTeamMemberRole).toHaveBeenCalledWith(5, "management"));
  });

  test("removes an account after confirming", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    api.deleteTeamMember.mockResolvedValue(undefined);
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Remove Ravi" }));

    await waitFor(() => expect(api.deleteTeamMember).toHaveBeenCalledWith(5));
  });

  test("keeps an account when the removal is cancelled", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(false);
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Remove Ravi" }));

    expect(api.deleteTeamMember).not.toHaveBeenCalled();
  });

  test("shows a server refusal on the team page", async () => {
    const user = userEvent.setup();
    api.createTeamMember.mockRejectedValue(new Error("An account with this email already exists."));
    renderPage();

    await fillForm(user);

    expect(await screen.findByText("An account with this email already exists.")).toBeInTheDocument();
  });
});
