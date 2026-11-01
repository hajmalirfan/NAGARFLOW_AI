import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import ErrorBoundary from "../components/ErrorBoundary.jsx";
import { getScenarios } from "../services/api.js";

function Crash() {
  throw new Error("secret detail");
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("error handling", () => {
  test("a crashing page shows the recovery screen", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});

    render(<ErrorBoundary><Crash /></ErrorBoundary>);

    expect(screen.getByRole("alert")).toHaveTextContent("This page could not be shown.");
    expect(screen.getByRole("button", { name: "Reload the page" })).toBeInTheDocument();
    expect(screen.queryByText(/secret detail/)).not.toBeInTheDocument();
  });

  test("a healthy page renders normally", () => {
    render(<ErrorBoundary><p>Fine</p></ErrorBoundary>);

    expect(screen.getByText("Fine")).toBeInTheDocument();
  });

  test("server errors show their reference", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: "Something went wrong on the server.", reference: "ab12cd34" }),
      { status: 500 },
    )));

    await expect(getScenarios()).rejects.toThrow(
      "Something went wrong on the server. Reference: ab12cd34.",
    );
  });
});
