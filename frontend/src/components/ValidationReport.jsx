const decimal = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });

// The order the engine documents, with the label shown for each check.
const CHECK_LABELS = [
  ["depot", "Depot"],
  ["vehicles", "Vehicle configuration"],
  ["storage_points", "Storage point count"],
  ["facility", "Processing facility"],
  ["waste_quantity", "Waste quantities"],
  ["vehicle_capacity", "Individual vehicle capacity"],
  ["combined_capacity", "Combined vehicle capacity"],
  ["facility_capacity", "Facility capacity"],
  ["coordinates", "Coordinates"],
  ["availability", "Waste availability"],
  ["vehicle_assignment", "Vehicle capacity assignment"],
  ["road_connectivity", "Road connectivity"],
];

const RESULT_TEXT = {
  passed: "Passed",
  failed: "Failed",
  not_checked: "Not checked",
};

const RESULT_PILL = {
  passed: "pill-ok",
  failed: "pill-off",
  not_checked: "pill-neutral",
};

const STATUS_SUMMARY = {
  valid: {
    heading: "Scenario is feasible",
    detail: "Every hard constraint passed. Optimization can run.",
    tone: "valid",
  },
  invalid: {
    heading: "Scenario is not feasible",
    detail: "Fix the errors below, then validate again.",
    tone: "invalid",
  },
  incomplete: {
    heading: "Validation incomplete",
    detail:
      "Nothing failed, but a required check could not run yet, so the scenario is not "
      + "marked feasible and optimization stays blocked.",
    tone: "incomplete",
  },
};

export default function ValidationReport({ report }) {
  if (!report) return null;
  const summary = STATUS_SUMMARY[report.validation_status] ?? STATUS_SUMMARY.invalid;

  return (
    <section className="panel validation-report">
      <div className="panel-head">
        <div>
          <h2>Scenario Validation Report</h2>
          <p>
            {decimal.format(report.total_waste_kg)} kg across{" "}
            {report.storage_point_count} storage points.
          </p>
        </div>
        <span className={`pill ${report.can_optimize ? "pill-ok" : "pill-off"}`}>
          {report.can_optimize ? "Can optimize" : "Optimization blocked"}
        </span>
      </div>

      <div className={`validation-summary validation-${summary.tone}`} role="status">
        <strong>{summary.heading}</strong>
        <p>{summary.detail}</p>
      </div>

      <ul className="validation-checks">
        {CHECK_LABELS.filter(([key]) => key in report.checks).map(([key, label]) => (
          <li key={key}>
            <span>{label}</span>
            <span className={`pill ${RESULT_PILL[report.checks[key]] ?? "pill-neutral"}`}>
              {RESULT_TEXT[report.checks[key]] ?? report.checks[key]}
            </span>
          </li>
        ))}
      </ul>

      {report.errors.length > 0 && (
        <div className="validation-messages">
          <h3>Errors</h3>
          <ul>
            {report.errors.map((error) => (
              <li key={`${error.code}-${error.message}`}>
                <code>{error.code}</code>
                <span>{error.message}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {report.warnings.length > 0 && (
        <div className="validation-messages validation-warnings">
          <h3>Warnings</h3>
          <ul>
            {report.warnings.map((warning) => (
              <li key={`${warning.code}-${warning.message}`}>
                <code>{warning.code}</code>
                <span>{warning.message}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {report.feasible_assignment && (
        <div className="validation-assignment">
          <h3>A workable assignment</h3>
          <p className="panel-note">
            One valid split of whole storage points. The optimizer may choose a
            different one, but this proves a feasible assignment exists.
          </p>
          <ul className="row-list">
            {report.feasible_assignment.map((load) => (
              <li key={load.vehicle_id}>
                <span className="row-main">
                  {load.name}
                  <small>
                    {load.assigned_point_codes.length
                      ? load.assigned_point_codes.join(", ")
                      : "no points assigned"}
                  </small>
                </span>
                <span className="row-value">
                  {decimal.format(load.assigned_kg)} / {decimal.format(load.capacity_kg)} kg
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
