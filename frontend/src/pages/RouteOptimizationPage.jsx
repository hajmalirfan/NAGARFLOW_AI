import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import RouteMap from "../components/RouteMap.jsx";
import ValidationReport from "../components/ValidationReport.jsx";
import { getLatestOptimization, getScenarios, optimizeScenario } from "../services/api.js";
import { PageError, PageHeading } from "./ScenarioManagementPage.jsx";

const METHODS = [
  { key: "greedy", name: "Greedy" },
  { key: "or_tools", name: "OR-Tools" },
];

// OR-Tools stops at its time limit without proving a route is the best
// possible, so a found route must never read as "optimal".
const STATUS_TEXT = {
  feasible: "Best found",
  optimal: "Proven best",
  no_solution: "No route found",
  infeasible: "Infeasible",
  timeout: "Timed out",
  invalid_result: "Failed the result check",
};

function formatKm(metres) {
  return `${(metres / 1000).toFixed(2)} km`;
}

function formatMinutes(seconds) {
  return `${Math.round(seconds / 60)} min`;
}

function hasRoutes(run) {
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

export default function RouteOptimizationPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const scenarioId = searchParams.get("scenario") ?? "";
  const [scenarios, setScenarios] = useState([]);
  const [comparison, setComparison] = useState(null);
  const [blockedReport, setBlockedReport] = useState(null);
  const [shown, setShown] = useState("or_tools");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getScenarios().then(setScenarios).catch((failure) => setError(failure.message));
  }, []);

  useEffect(() => {
    setComparison(null);
    setBlockedReport(null);
    if (!scenarioId) return undefined;
    let current = true;
    getLatestOptimization(scenarioId)
      .then((result) => {
        if (current) setComparison(result);
      })
      .catch((failure) => {
        // A 404 simply means this scenario has not been run yet.
        if (current && failure.status !== 404) setError(failure.message);
      });
    return () => {
      current = false;
    };
  }, [scenarioId]);

  async function run() {
    setError("");
    setBlockedReport(null);
    setComparison(null);
    setRunning(true);
    try {
      setComparison(await optimizeScenario(scenarioId));
    } catch (failure) {
      if (failure.status === 409 && failure.report) {
        setBlockedReport(failure.report);
      } else {
        setError(failure.message);
      }
    } finally {
      setRunning(false);
    }
  }

  const shownRun = comparison?.[shown];

  return (
    <section className="scenario-page">
      <PageHeading
        kicker="OPTIMIZATION"
        title="Route Optimization"
        subtitle="Run Greedy and Google OR-Tools on identical inputs, then compare their routes."
      />
      <PageError message={error} />

      <section className="panel optimization-controls">
        <label className="scenario-field">
          <span>Scenario</span>
          <select
            value={scenarioId}
            disabled={running}
            onChange={(event) => setSearchParams(
              event.target.value ? { scenario: event.target.value } : {},
            )}
          >
            <option value="">Select a scenario</option>
            {scenarios.map((scenario) => (
              <option key={scenario.id} value={scenario.id}>{scenario.name}</option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="primary-action"
          onClick={run}
          disabled={!scenarioId || running}
        >
          {running ? "Running both algorithms…" : "Run optimization"}
        </button>
      </section>

      {blockedReport && (
        <>
          <p className="panel-note">
            Fix these problems in the <Link to={`/scenarios/${scenarioId}`}>scenario</Link>, then
            run it again.
          </p>
          <ValidationReport report={blockedReport} />
        </>
      )}

      {comparison && (
        <>
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
      )}
    </section>
  );
}
