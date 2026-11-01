import { expect, test, vi } from "vitest";

const setWorkerUrl = vi.fn();

vi.mock("maplibre-gl", () => ({ setWorkerUrl, Map: class {} }));

test("maps are given the bundled worker before use", async () => {
  const { loadMaplibre } = await import("../components/maplibre.js");

  const library = await loadMaplibre();

  expect(setWorkerUrl).toHaveBeenCalledOnce();
  expect(setWorkerUrl.mock.calls[0][0]).toContain("maplibre-gl-worker");
  expect(library.Map).toBeDefined();
});
