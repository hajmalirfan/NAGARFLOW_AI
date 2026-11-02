import { useEffect, useState } from "react";
import { useCan } from "../auth/permissions.js";
import { getFacilityPreview, getRoutePreview, getScenarioNames } from "../services/api.js";
import { PageError, PageHeading } from "./ScenarioManagementPage.jsx";

const NO_ROUTE = "No saved route exists for this scenario.";

function kg(value) {
  return `${value.toLocaleString()} kg`;
}

function RouteSection({ preview }) {
  return (
    <>
      {preview.routes.map((route) => (
        <section className="panel" key={route.vehicle_name}>
          <div className="panel-head"><h2>{route.vehicle_name}</h2></div>
          <ol className="scenario-resource-list">
            {route.stops.map((stop) => (
              <li key={stop.code}>
                <span>{stop.name}</span>
                <small>{stop.quantity_kg === null ? "Quantity not available" : kg(stop.quantity_kg)}</small>
                <small>{Math.round(stop.arrival_s / 60)} min after leaving the depot</small>
              </li>
            ))}
          </ol>
        </section>
      ))}
    </>
  );
}

function FacilitySection({ preview }) {
  return (
    <section className="panel">
      <div className="panel-head"><h2>Expected load</h2></div>
      <p className="panel-note">
        {kg(preview.expected_total_kg)} expected, facility capacity {kg(preview.facility_capacity_kg)}
      </p>
      <ul className="scenario-resource-list">
        {preview.vehicles.map((vehicle) => (
          <li key={vehicle.vehicle_name}>
            <span>{vehicle.vehicle_name}</span>
            <small>{vehicle.load_kg.toLocaleString()} kg of {kg(vehicle.capacity_kg)}</small>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default function RoutePreviewPage() {
  const showsRoutes = useCan("preview.routes");
  const showsFacility = useCan("preview.facility");
  const [scenarios, setScenarios] = useState([]);
  const [scenarioId, setScenarioId] = useState("");
  const [routes, setRoutes] = useState(null);
  const [facility, setFacility] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getScenarioNames().then(setScenarios).catch((failure) => setError(failure.message));
  }, []);

  useEffect(() => {
    setRoutes(null);
    setFacility(null);
    setError("");
    if (!scenarioId) return undefined;
    let current = true;
    const report = (failure) => {
      if (current) setError(failure.status === 404 ? NO_ROUTE : failure.message);
    };
    if (showsRoutes) {
      getRoutePreview(scenarioId).then((result) => current && setRoutes(result)).catch(report);
    }
    if (showsFacility) {
      getFacilityPreview(scenarioId).then((result) => current && setFacility(result)).catch(report);
    }
    return () => {
      current = false;
    };
  }, [scenarioId, showsRoutes, showsFacility]);

  const preview = routes ?? facility;

  return (
    <section className="scenario-page">
      <PageHeading
        kicker="PREVIEW"
        title="Route Preview"
        subtitle="A read-only view of the newest saved run for a scenario."
      />
      <p className="notice"><strong>Synthetic preview, not a dispatch instruction</strong></p>
      <PageError message={error} />

      <section className="panel optimization-controls">
        <label className="scenario-field">
          <span>Scenario</span>
          <select value={scenarioId} onChange={(event) => setScenarioId(event.target.value)}>
            <option value="">Select a scenario</option>
            {scenarios.map((scenario) => (
              <option key={scenario.id} value={scenario.id}>{scenario.name}</option>
            ))}
          </select>
        </label>
      </section>

      {preview?.out_of_date && (
        <p className="notice">
          This scenario changed after the run, so this preview may no longer match it.
        </p>
      )}
      {routes && <RouteSection preview={routes} />}
      {facility && <FacilitySection preview={facility} />}
    </section>
  );
}
