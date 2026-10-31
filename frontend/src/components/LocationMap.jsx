import { useEffect, useRef, useState } from "react";
import "maplibre-gl/dist/maplibre-gl.css";

const INITIAL_CENTER = [79.54393, 10.89918];

function markerPopup(marker) {
  const content = document.createElement("div");
  const title = document.createElement("strong");
  title.textContent = marker.name;
  content.append(title);
  marker.details.forEach((detail) => {
    const line = document.createElement("p");
    line.textContent = detail;
    content.append(line);
  });
  return content;
}

/**
 * An OpenStreetMap view of registered locations.
 *
 * Each marker carries its own popup lines, so storage points, facilities
 * and depots can share one map without this component knowing what they
 * are. maplibre-gl is imported lazily to keep it off the login path.
 */
export default function LocationMap({
  markers,
  title,
  description,
  emptyMessage,
  ariaLabel,
  markerClassName = "storage-point-marker",
}) {
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

        const validMarkers = markers.filter(
          (marker) =>
            Number.isFinite(Number(marker.latitude))
            && Number.isFinite(Number(marker.longitude)),
        );
        const bounds = new LngLatBounds();
        validMarkers.forEach((marker) => {
          const markerElement = document.createElement("button");
          markerElement.type = "button";
          markerElement.className = markerClassName;
          markerElement.setAttribute("aria-label", `Show ${marker.name} details`);
          new Marker({ element: markerElement })
            .setLngLat([Number(marker.longitude), Number(marker.latitude)])
            .setPopup(new Popup({ offset: 18 }).setDOMContent(markerPopup(marker)))
            .addTo(map);
          bounds.extend([Number(marker.longitude), Number(marker.latitude)]);
        });

        if (validMarkers.length > 1) {
          map.on("load", () => map.fitBounds(bounds, { padding: 48, maxZoom: 14 }));
        } else if (validMarkers.length === 1) {
          map.on("load", () => {
            map.setCenter([
              Number(validMarkers[0].longitude),
              Number(validMarkers[0].latitude),
            ]);
            map.setZoom(14);
          });
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
  }, [markers, markerClassName]);

  return (
    <div className="storage-map-panel panel">
      <div className="panel-head">
        <div>
          <h2>{title}</h2>
          <p>{description}</p>
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
      {!markers.length && <p className="storage-map-empty">{emptyMessage}</p>}
      <div className="storage-map-canvas" ref={containerRef} aria-label={ariaLabel} />
      <p className="storage-map-attribution">Map data &copy; OpenStreetMap contributors.</p>
    </div>
  );
}
