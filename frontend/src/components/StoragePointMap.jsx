import { useEffect, useRef, useState } from "react";
import "maplibre-gl/dist/maplibre-gl.css";

const INITIAL_CENTER = [79.54393, 10.89918];

function pointPopup(point) {
  const content = document.createElement("div");
  const title = document.createElement("strong");
  title.textContent = point.name;
  const code = document.createElement("p");
  code.textContent = `Code: ${point.point_code}`;
  const waste = document.createElement("p");
  waste.textContent = `Waste: ${Number(point.waste_quantity_kg).toLocaleString()} kg`;
  const status = document.createElement("p");
  status.textContent = `Status: ${point.availability_status}`;
  const coordinates = document.createElement("p");
  coordinates.textContent = `Coordinates: ${point.latitude}, ${point.longitude}`;
  content.append(title, code, waste, status, coordinates);
  return content;
}

export default function StoragePointMap({ points }) {
  const containerRef = useRef(null);
  const [mapError, setMapError] = useState("");

  useEffect(() => {
    if (!containerRef.current) return undefined;
    setMapError("");
    let disposed = false;
    let map;

    import("maplibre-gl")
      .then(({ LngLatBounds, Map, Marker, Popup }) => {
        if (disposed || !containerRef.current) return;
        map = new Map({
          container: containerRef.current,
          center: INITIAL_CENTER,
          zoom: 14,
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
            layers: [
              {
                id: "openstreetmap",
                type: "raster",
                source: "openstreetmap",
              },
            ],
          },
        });

        const validPoints = points.filter(
          (point) =>
            Number.isFinite(Number(point.latitude))
            && Number.isFinite(Number(point.longitude)),
        );
        const bounds = new LngLatBounds();
        validPoints.forEach((point) => {
          const markerElement = document.createElement("button");
          markerElement.type = "button";
          markerElement.className = "storage-point-marker";
          markerElement.setAttribute("aria-label", `Show ${point.name} details`);
          new Marker({ element: markerElement })
            .setLngLat([Number(point.longitude), Number(point.latitude)])
            .setPopup(new Popup({ offset: 18 }).setDOMContent(pointPopup(point)))
            .addTo(map);
          bounds.extend([Number(point.longitude), Number(point.latitude)]);
        });

        if (validPoints.length > 1) {
          map.on("load", () => map.fitBounds(bounds, { padding: 48, maxZoom: 14 }));
        } else if (validPoints.length === 1) {
          map.on("load", () => {
            map.setCenter([Number(validPoints[0].longitude), Number(validPoints[0].latitude)]);
            map.setZoom(14);
          });
        }

        map.on("error", () => {
          setMapError("Map tiles could not be loaded. Check your internet connection and try again.");
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
  }, [points]);

  return (
    <div className="storage-map-panel panel">
      <div className="panel-head">
        <div>
          <h2>Storage point map</h2>
          <p>Map view centered on 10.89918, 79.54393 when no points are registered.</p>
        </div>
        <a
          className="scenario-row-link"
          href="https://www.openstreetmap.org/#map=14/10.89918/79.54393"
          target="_blank"
          rel="noreferrer"
        >
          OpenStreetMap ↗
        </a>
      </div>
      {mapError && <p className="form-error" role="alert">{mapError}</p>}
      {!points.length && <p className="storage-map-empty">No registered points to display yet.</p>}
      <div className="storage-map-canvas" ref={containerRef} aria-label="Map of registered storage points" />
      <p className="storage-map-attribution">Map data &copy; OpenStreetMap contributors.</p>
    </div>
  );
}
