import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useCan } from "../auth/permissions.js";
import { useAuth } from "../auth/AuthContext.jsx";
import { getDashboardSummary } from "../services/api.js";

const integer = new Intl.NumberFormat("en-IN");
const decimal = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 1 });
// Distances keep two decimals: the gap between the Greedy baseline and the
// OR-Tools route is the headline result, and rounding to 0.1 km can hide it.
const kilometres = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });

function formatKg(value) {
  return `${decimal.format(value)} kg`;
}

function formatDate(value) {
  if (!value) return "—";
  // Timestamps are stored as UTC without an offset, so mark them as UTC
  // before formatting rather than letting the browser assume local time.
  const parsed = new Date(/[zZ]|[+-]\d{2}:?\d{2}$/.test(value) ? value : `${value}Z`);
  if (Number.isNaN(parsed.getTime())) return "—";
  return parsed.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function SummaryCard({ label, value, hint, tone = "" }) {
  return (
    <article className={`stat-card${tone ? ` stat-${tone}` : ""}`}>
      <p className="stat-label">{label}</p>
      <p className="stat-value">{value}</p>
      <p className="stat-hint">{hint}</p>
    </article>
  );
}

function Panel({ title, action, children }) {
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

function EmptyState({ message, actionLabel, actionTo }) {
  return (
    <div className="empty-state">
      <p>{message}</p>
      {actionTo && <Link className="empty-action" to={actionTo}>{actionLabel}</Link>}
    </div>
  );
}

export default function DashboardPage() {
  const { user } = useAuth();
  const canRead = useCan("records.read");
  const canWrite = useCan("records.write");
  const canOpenRoutes = useCan("optimization.read");
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let active = true;
    getDashboardSummary()
      .then((data) => {
        if (active) setSummary(data);
      })
      .catch((requestError) => {
        if (active) setError(requestError.message);
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  if (isLoading) {
    return (
      <div className="page-loading">
        <span className="loading-dot" />
        <p>Loading your municipality's figures…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page-error" role="alert">
        <h2>The dashboard could not load.</h2>
        <p>{error}</p>
      </div>
    );
  }

  const firstName = user.name.trim().split(" ")[0];
  const { waste_overview: waste, vehicle_status: vehicles, optimization_summary: runs } = summary;
  const hasAnyData = summary.total_scenarios > 0;

  return (
    <div className="dashboard-page">
      <div className="page-head">
        <div>
          <p className="page-kicker">DASHBOARD</p>
          <h1>Good to see you, {firstName}.</h1>
          <p className="page-subtitle">
            Waste transportation status for your municipality, read live from the database.
          </p>
        </div>
        {canWrite && (
          <Link className="primary-action" to="/scenarios">
            New scenario<span aria-hidden="true">→</span>
          </Link>
        )}
      </div>

      {!hasAnyData && (
        <div className="notice">
          <strong>Nothing is configured yet.</strong> Every figure below is zero because no
          scenario has been created. They come from your saved records, not sample data.
        </div>
      )}

      <div className="stat-grid" data-testid="stat-grid">
        <SummaryCard
          label="Total Waste"
          value={formatKg(summary.total_waste_kg)}
          hint={`Across ${integer.format(summary.storage_points_count)} storage point${summary.storage_points_count === 1 ? "" : "s"}`}
          tone="teal"
        />
        <SummaryCard
          label="Storage Points"
          value={integer.format(summary.storage_points_count)}
          hint="Mandatory collection points"
        />
        <SummaryCard
          label="Available Vehicles"
          value={integer.format(summary.available_vehicles_count)}
          hint={`${integer.format(vehicles.unavailable_count)} unavailable`}
        />
        <SummaryCard
          label="Facility Capacity"
          value={summary.facility_configured ? formatKg(summary.facility_remaining_capacity_kg) : "Not configured"}
          hint={summary.facility_configured ? "Remaining shared capacity" : "Add a processing facility"}
          tone={summary.facility_configured ? "" : "muted"}
        />
        <SummaryCard
          label="Total Scenarios"
          value={integer.format(summary.total_scenarios)}
          hint="Saved planning scenarios"
        />
        <SummaryCard
          label="Optimized Routes"
          value={integer.format(summary.optimized_routes_count)}
          hint="Successful optimization runs"
          tone="gold"
        />
      </div>

      <div className="panel-grid">
        <Panel title="Waste Overview">
          {waste.storage_points_count === 0 ? (
            <EmptyState
              message="No waste quantities recorded yet. Add storage points to a scenario to see the breakdown here."
              actionLabel="Add storage points"
              actionTo={canRead ? "/storage-points" : undefined}
            />
          ) : (
            <dl className="detail-list">
              <div><dt>Total waste</dt><dd>{formatKg(waste.total_waste_kg)}</dd></div>
              <div><dt>Storage points</dt><dd>{integer.format(waste.storage_points_count)}</dd></div>
              <div><dt>Largest point</dt><dd>{formatKg(waste.largest_point_kg)}</dd></div>
              <div><dt>Average per point</dt><dd>{formatKg(waste.average_point_kg)}</dd></div>
            </dl>
          )}
        </Panel>

        <Panel title="Vehicle Status">
          {vehicles.available_count + vehicles.unavailable_count === 0 ? (
            <EmptyState
              message="No vehicles registered yet. The MVP uses two vehicles, each making at most one trip."
              actionLabel="Register vehicles"
              actionTo={canRead ? "/vehicles" : undefined}
            />
          ) : (
            <>
              <div className="split-stat">
                <div><strong>{integer.format(vehicles.available_count)}</strong><span>Available</span></div>
                <div><strong>{integer.format(vehicles.unavailable_count)}</strong><span>Unavailable</span></div>
                <div><strong>{formatKg(vehicles.total_available_capacity_kg)}</strong><span>Usable capacity</span></div>
              </div>
              <ul className="row-list">
                {[...vehicles.available, ...vehicles.unavailable].map((vehicle) => (
                  <li key={vehicle.id}>
                    <span className="row-main">{vehicle.name}</span>
                    <span className="row-meta">{formatKg(vehicle.capacity_kg)}</span>
                    <span className={`pill ${vehicle.is_available ? "pill-ok" : "pill-off"}`}>
                      {vehicle.is_available ? "Available" : "Unavailable"}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </Panel>

        <Panel title="Storage Point Overview">
          {summary.storage_points.length === 0 ? (
            <EmptyState
              message="No storage points registered yet. A scenario needs six to ten points."
              actionLabel="Add storage points"
              actionTo={canRead ? "/storage-points" : undefined}
            />
          ) : (
            <ul className="row-list">
              {summary.storage_points.map((point) => (
                <li key={point.id}>
                  <span className="row-main">{point.name}</span>
                  <span className="row-meta">
                    {point.latitude.toFixed(4)}, {point.longitude.toFixed(4)}
                  </span>
                  <span className="row-value">{formatKg(point.waste_kg)}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel title="Recent Scenarios" action={canRead && <Link className="panel-link" to="/scenarios">View all</Link>}>
          {summary.recent_scenarios.length === 0 ? (
            <EmptyState
              message="No scenarios saved yet. Create one to start planning collection routes."
              actionLabel="Create a scenario"
              actionTo={canRead ? "/scenarios" : undefined}
            />
          ) : (
            <ul className="row-list">
              {summary.recent_scenarios.map((scenario) => (
                <li key={scenario.id}>
                  <span className="row-main">
                    {scenario.name}
                    <small>{scenario.reference}</small>
                  </span>
                  <span className="row-meta">
                    {integer.format(scenario.storage_points_count)} points ·{" "}
                    {integer.format(scenario.vehicles_count)} vehicles
                  </span>
                  <span className="row-meta">{formatDate(scenario.created_at)}</span>
                  <span className="pill pill-neutral">{scenario.status}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel title="Optimization Summary" action={canOpenRoutes && <Link className="panel-link" to="/route-optimization">Open</Link>}>
          {runs.total_runs === 0 ? (
            <EmptyState
              message="No optimization has been run yet. Results appear here only after an algorithm actually runs."
              actionLabel="Open route optimization"
              actionTo={canOpenRoutes ? "/route-optimization" : undefined}
            />
          ) : (
            <>
              <div className="split-stat">
                <div><strong>{integer.format(runs.successful_runs)}</strong><span>Successful</span></div>
                <div><strong>{integer.format(runs.failed_runs)}</strong><span>Failed</span></div>
                <div>
                  <strong>{runs.best_distance_km === null ? "—" : `${kilometres.format(runs.best_distance_km)} km`}</strong>
                  <span>Best distance</span>
                </div>
              </div>
              <p className="panel-note">
                {integer.format(runs.total_runs)} run{runs.total_runs === 1 ? "" : "s"} recorded in total.
              </p>
            </>
          )}
        </Panel>
      </div>
    </div>
  );
}
