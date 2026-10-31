import LocationMap from "./LocationMap.jsx";

export default function StoragePointMap({ points }) {
  const markers = points.map((point) => ({
    id: point.id,
    name: point.name,
    latitude: point.latitude,
    longitude: point.longitude,
    details: [
      `Code: ${point.point_code}`,
      `Waste: ${Number(point.waste_quantity_kg).toLocaleString()} kg`,
      `Status: ${point.availability_status}`,
      `Coordinates: ${point.latitude}, ${point.longitude}`,
    ],
  }));

  return (
    <LocationMap
      markers={markers}
      title="Storage point map"
      description="Map view centered on 10.89918, 79.54393 when no points are registered."
      emptyMessage="No registered points to display yet."
      ariaLabel="Map of registered storage points"
    />
  );
}
