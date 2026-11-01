import { useState } from "react";
import RouteMap from "./RouteMap.jsx";

const METHODS = [
  { key: "greedy", name: "Greedy" },
  { key: "or_tools", name: "OR-Tools" },
];

// OR-Tools stops at its time limit without proving a route is the best
// possible, so a found route must never read as "optimal".
export const STATUS_TEXT = {
  feasible: "Best found",
  optimal: "Proven best",
  no_solution: "No route found",
  infeasible: "Infeasible",
  timeout: "Timed out",
  invalid_result: "Failed the result check",
};

export function formatKm(metres) {
  return `${(metres / 1000).toFixed(2)} km`;
}

// The API stores UTC without saying so.
export function formatRunDate(value) {
  const stamp = /[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`;
  return new Date(stamp).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
}

function formatMinutes(seconds) {
  return `${Math.round(seconds / 60)} min`;
}

export function hasRoutes(run) {
  return run.status === "feasible" || run.status === "optimal";
}

function MethodCard({ name, run }) {
  return (
    <article className="panel optimization-card">
      <div className="panel-head">
        <h2>{name}</h2>
        <span className={`pill ${hasRoutes(run) ? "pill-ok" : "pill-off"}`}>
          {STATUS_TEXT[run.status] ?? run.status}
        </span>
      </div>
      {hasRoutes(run) ? (
        <>
          <p className="optimization-distance">{formatKm(run.total_distance_m)}</p>
          <p className="panel-note">
            {run.routes.length} {run.routes.length === 1 ? "vehicle" : "vehicles"} used, solved in{" "}
            {(run.solve_ms / 1000).toFixed(1)} s
          </p>
        </>
      ) : (
        <p className="panel-note">{run.message}</p>
      )}
    </article>
  );
}

function DifferenceNote({ comparison }) {
  const { difference_m: difference, difference_pct: percent } = comparison;
  if (difference === null || difference === undefined) return null;
  if (difference === 0) {
    return <p className="optimization-difference">Both methods found the same distance.</p>;
  }
  const shorter = difference > 0 ? "OR-Tools" : "Greedy";
  return (
    <p className="optimization-difference">
      {shorter} is {formatKm(Math.abs(difference))} shorter ({Math.abs(percent)}%).
    </p>
  );
}

function RouteDetails({ routes }) {
  return (
    <section className="panel">
      <h2>Vehicle routes</h2>
      {routes.map((route) => (
        <div className="optimization-route" key={route.vehicle_id}>
          <h3>{route.vehicle_name}</h3>
          <p className="panel-note">
            {route.load_kg.toLocaleString("en-IN")} of{" "}
            {route.capacity_kg.toLocaleString("en-IN")} kg, {formatKm(route.distance_m)}, reaches
            the facility after {formatMinutes(route.finish_s)}
          </p>
          <ol className="row-list">
            {route.stops.map((stop) => (
              <li key={stop.code}>
                <span className="row-main">{stop.code}</span>
                <span className="row-value">
                  arrives after {formatMinutes(stop.arrival_s)}
                  {stop.wait_s > 0 ? `, waits ${formatMinutes(stop.wait_s)}` : ""}
                </span>
              </li>
            ))}
          </ol>
        </div>
      ))}
    </section>
  );
}

/** Both methods' saved result: cards, difference, map and stops. */
export default function ComparisonView({ comparison }) {
  const [shown, setShown] = useState("or_tools");
  const shownRun = comparison[shown];

  return (
    <>
      <p className="panel-note">Run on {formatRunDate(comparison.created_at)}</p>
      <div className="panel-grid">
        {METHODS.map(({ key, name }) => (
          <MethodCard key={key} name={name} run={comparison[key]} />
        ))}
      </div>
      <DifferenceNote comparison={comparison} />
      <p className="panel-note">
        Distances come from the road network. Times are estimates from assumed road speeds.
      </p>

      <div className="optimization-toggle">
        {METHODS.map(({ key, name }) => (
          <button
            key={key}
            type="button"
            aria-pressed={shown === key}
            aria-label={`Show ${name} routes`}
            onClick={() => setShown(key)}
          >
            {name}
          </button>
        ))}
      </div>

      {hasRoutes(shownRun) ? (
        <>
          <RouteMap routes={shownRun.routes} />
          <RouteDetails routes={shownRun.routes} />
        </>
      ) : (
        <p className="panel-note">This method has no route to show.</p>
      )}
    </>
  );
}
