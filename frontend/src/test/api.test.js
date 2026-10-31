import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { getDashboardSummary, login } from "../services/api.js";

/**
 * The error text these tests pin down is a diagnostic, not decoration.
 *
 * A stale FastAPI process answers the current frontend's /api/v1 routes
 * with a bare 404 {"detail":"Not Found"}, which reads as a generic
 * failure and is easy to mistake for a database outage. The message has
 * to name the real cause.
 */
describe("API error messages", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    localStorage.clear();
  });

  test("a 404 says the endpoint is missing and suggests restarting the API", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "Not Found" }), { status: 404 }),
    );

    await expect(login({ email: "a@b.com", password: "xxxxxxxx" })).rejects.toThrow(
      /does not have this endpoint.*restart/is,
    );
  });

  test("the 404 message names the endpoint that was missing", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "Not Found" }), { status: 404 }),
    );

    await expect(getDashboardSummary()).rejects.toThrow(/\/api\/v1\/dashboard\/summary/);
  });

  test("a network failure still reports that the API is unreachable", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));

    await expect(getDashboardSummary()).rejects.toThrow(/unable to reach/i);
  });

  test("a real API error message is passed through unchanged", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "Email or password is incorrect." }), { status: 401 }),
    );

    await expect(login({ email: "a@b.com", password: "wrong" })).rejects.toThrow(
      "Email or password is incorrect.",
    );
  });

  test("a 500 from the API is reported as a server error, not a missing endpoint", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "Internal Server Error" }), { status: 500 }),
    );

    await expect(getDashboardSummary()).rejects.toThrow(/server error/i);
  });
});
