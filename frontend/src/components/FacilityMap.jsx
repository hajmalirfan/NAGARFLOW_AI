import LocationMap from "./LocationMap.jsx";

/**
 * Facility markers.
 *
 * ``capacityById`` optionally supplies the live shared-capacity figures,
 * so a marker can show how much of the pool is still available.
 */
export default function FacilityMap({ facilities, capacityById = {} }) {
  const markers = facilities.map((facility) => {
    const capacity = capacityById[facility.id];
    const details = [
      `Code: ${facility.facility_code}`,
      `Address: ${facility.address || "Not recorded"}`,
      `Coordinates: ${facility.latitude}, ${facility.longitude}`,
      `Total capacity: ${Number(facility.total_capacity_kg).toLocaleString()} kg`,
    ];
    details.push(
      capacity
        ? `Available capacity: ${Number(capacity.remaining_capacity_kg).toLocaleString()} kg`
        : "Available capacity: not calculated yet",
    );
    details.push(`Status: ${facility.status}`);
    return {
      id: facility.id,
      name: facility.name,
      latitude: facility.latitude,
      longitude: facility.longitude,
      details,
    };
  });

  return (
    <LocationMap
      markers={markers}
      title="Processing facility map"
      description="Map view centered on 10.8050, 78.6856 when no facility is registered."
      emptyMessage="No registered facility to display yet."
      ariaLabel="Map of registered processing facilities"
      markerClassName="facility-marker"
    />
  );
}
