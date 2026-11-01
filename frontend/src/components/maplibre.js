import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";

/**
 * Load MapLibre with its worker in place.
 *
 * MapLibre finds its worker relative to its own file, which bundling moves,
 * so without this every map fails with "Worker failed to load". Vite bundles
 * the worker here and supplies its real address.
 */
export async function loadMaplibre() {
  const library = await import("maplibre-gl");
  library.setWorkerUrl(workerUrl);
  return library;
}
