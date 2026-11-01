import { useEffect, useRef, useState } from "react";
import "maplibre-gl/dist/maplibre-gl.css";

const VEHICLE_COLORS = ["#0f766e", "#c2410c"];

function numberedMarker(label, className) {
  const element = document.createElement("span");
  element.className = className;
  element.textContent = label;
  return element;
}

/**
 * Vehicle routes drawn along their real road geometry, with one colour per
 * vehicle and numbered stops. Each route starts at the depot and ends at
 * the facility.
 */
export default function RouteMap({ routes }) {
  const containerRef = useRef(null);
  const [mapError, setMapError] = useState("");

  useEffect(() => {
    if (!containerRef.current) return undefined;
    setMapError("");
    let disposed = false;
    let map;

    import("maplibre-gl")
      .then(({ LngLatBounds, Map, Marker }) => {
        if (disposed || !containerRef.current) return;
        const bounds = new LngLatBounds();
        routes.forEach((route) => route.geometry.forEach((point) => bounds.extend(point)));

        map = new Map({
          container: containerRef.current,
          bounds,
          fitBoundsOptions: { padding: 48 },
          attributionControl: true,
          style: {
            version: 8,
            sources: {
              openstreetmap: {
                type: "raster",
                tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
                tileSize: 256,
                attribution:
                  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
              },
            },
            layers: [{ id: "openstreetmap", type: "raster", source: "openstreetmap" }],
          },
        });

        map.on("load", () => {
          routes.forEach((route, index) => {
            const id = `route-${route.vehicle_id}`;
            map.addSource(id, {
              type: "geojson",
              data: {
                type: "Feature",
                properties: {},
                geometry: { type: "LineString", coordinates: route.geometry },
              },
            });
            map.addLayer({
              id,
              type: "line",
              source: id,
              layout: { "line-cap": "round", "line-join": "round" },
              paint: {
                "line-color": VEHICLE_COLORS[index % VEHICLE_COLORS.length],
                "line-width": 4,
                "line-opacity": 0.85,
              },
            });
          });
        });

        routes.forEach((route) => {
          route.stops.forEach((stop, stopIndex) => {
            new Marker({ element: numberedMarker(String(stopIndex + 1), "route-stop-marker") })
              .setLngLat([stop.longitude, stop.latitude])
              .addTo(map);
          });
        });
        const [firstRoute] = routes;
        if (firstRoute) {
          new Marker({ element: numberedMarker("D", "route-end-marker") })
            .setLngLat(firstRoute.geometry[0])
            .addTo(map);
          new Marker({ element: numberedMarker("F", "route-end-marker") })
            .setLngLat(firstRoute.geometry[firstRoute.geometry.length - 1])
            .addTo(map);
        }

        map.on("error", () => {
          setMapError(
            "Map tiles could not be loaded. Check your internet connection and try again.",
          );
        });
      })
      .catch(() => {
        if (!disposed) {
          setMapError("The map could not be initialized. Reload the page and try again.");
        }
      });

    return () => {
      disposed = true;
      map?.remove();
    };
  }, [routes]);

  return (
    <div className="storage-map-panel panel">
      <div className="panel-head">
        <div>
          <h2>Route map</h2>
          <p>D marks the depot, F the facility, and numbers show the visit order.</p>
        </div>
      </div>
      {mapError && <p className="form-error" role="alert">{mapError}</p>}
      <div
        ref={containerRef}
        className="storage-map-canvas"
        aria-label="Map of the vehicle routes"
      />
      <p className="storage-map-attribution">Map data &copy; OpenStreetMap contributors.</p>
    </div>
  );
}
