import { useEffect, useState } from "react";
import { STATUS_TEXT, formatKm } from "../components/ComparisonView.jsx";
import {
  downloadEvaluationCsv,
  getEvaluationReport,
  loadEvaluationScenarios,
  optimizeScenario,
} from "../services/api.js";
import { PageError, PageHeading } from "./ScenarioManagementPage.jsx";

const STATE_TEXT = {
  not_loaded: "Not loaded",
  not_run: "Not run",
  blocked: "Blocked",
  ran: "Ran",
  out_of_date: "Out of date",
};

function MethodCell({ method }) {
  if (!method) return <td />;
  if (method.distance_m === null) {
    return (
      <td>
        {STATUS_TEXT[method.status] ?? method.status}
        {method.message && <p className="panel-note">{method.message}</p>}
      </td>
    );
  }
  return (
    <td>
      {formatKm(method.distance_m)}
      <p className="panel-note">
        {method.facility_load_kg.toLocaleString("en-IN")} of{" "}
        {method.facility_capacity_kg.toLocaleString("en-IN")} kg delivered
      </p>
    </td>
  );
}

function ReportRow({ row }) {
  return (
    <tr>
      <th scope="row">{row.code}</th>
      <td>{row.name}</td>
      <td>
        {STATE_TEXT[row.state]}
        {row.errors.map((error) => (
          <p className="panel-note" key={error.code}>{error.message}</p>
        ))}
        {row.state === "out_of_date" && (
          <p className="panel-note">A record changed after this run. Run it again.</p>
        )}
        {row.edited && <p className="panel-note">Edited since loading.</p>}
        {row.matches_expected === false && (
          <p className="panel-note">Differs from the expected outcome.</p>
        )}
      </td>
      <MethodCell method={row.greedy} />
      <MethodCell method={row.or_tools} />
      <td>
        {row.difference_m !== null && `${formatKm(row.difference_m)} (${row.difference_pct}%)`}
      </td>
    </tr>
  );
}

function SourceNote({ rows }) {
  const provenance = rows.find((row) => row.provenance)?.provenance;
  if (!provenance) return null;
  return (
    <p className="panel-note">
      Road data {provenance.road_dataset ?? "not recorded"}, OR-Tools {provenance.ortools_version},
      time limit {provenance.time_limit_s} s, road snap limit {provenance.snap_limit_m} m.
    </p>
  );
}

export default function ReportsPage() {
  const [report, setReport] = useState(null);
  const [progress, setProgress] = useState("");
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState([]);

  async function refresh() {
    setReport(await getEvaluationReport());
  }

  useEffect(() => {
    getEvaluationReport()
      .then(setReport)
      .catch((failure) => setErrors([failure.message]));
  }, []);

  async function act(action) {
    setErrors([]);
    setBusy(true);
    try {
      await action();
      await refresh();
    } catch (failure) {
      setErrors((current) => [...current, failure.message]);
    } finally {
      setBusy(false);
      setProgress("");
    }
  }

  async function runCases() {
    const cases = report.rows.filter((row) => row.scenario_id !== null);
    for (const [index, row] of cases.entries()) {
      setProgress(`Running ${row.code}, ${index + 1} of ${cases.length}`);
      try {
        await optimizeScenario(row.scenario_id);
      } catch (failure) {
        // A 409 is a blocked case, which the report itself shows.
        if (failure.status !== 409) {
          setErrors((current) => [...current, `${row.code}: ${failure.message}`]);
        }
      }
    }
  }

  return (
    <section className="scenario-page">
      <PageHeading
        kicker="REPORTS"
        title="Evaluation Report"
        subtitle="Greedy and OR-Tools across the S01 to S10 cases, including those with no route."
      />
      <PageError message={errors.join(" ")} />

      <section className="panel report-actions">
        <button
          type="button"
          className="secondary-action"
          disabled={busy}
          onClick={() => act(loadEvaluationScenarios)}
        >
          Load evaluation scenarios
        </button>
        <button
          type="button"
          className="primary-action"
          disabled={busy || !report}
          onClick={() => act(runCases)}
        >
          Run all
        </button>
        <button
          type="button"
          className="secondary-action"
          disabled={busy}
          onClick={() => act(downloadEvaluationCsv)}
        >
          Download CSV
        </button>
        {progress && <span role="status">{progress}</span>}
      </section>

      <p className="panel-note">
        All waste, capacity and time values here are synthetic. Locations are OpenStreetMap road
        positions, not municipal sites. Travel times use assumed speeds. OR-Tools reports the best
        route found within its time limit. Truck limits and turn restrictions are not checked.
      </p>

      {report && (
        <>
          <p className="optimization-difference">
            {report.summary.ran} ran, {report.summary.out_of_date} out of date,{" "}
            {report.summary.blocked} blocked, {report.summary.not_run} not run,{" "}
            {report.summary.not_loaded} not loaded.
            {report.summary.mean_difference_m !== null &&
              ` Across the ${report.summary.both_routes} cases where both found routes, Greedy minus OR-Tools averages ${formatKm(report.summary.mean_difference_m)} (${report.summary.mean_difference_pct}%).`}
          </p>
          <section className="panel report-scroll">
            <table className="report-table">
              <thead>
                <tr>
                  <th scope="col">Case</th>
                  <th scope="col">Name</th>
                  <th scope="col">Outcome</th>
                  <th scope="col">Greedy</th>
                  <th scope="col">OR-Tools</th>
                  <th scope="col">Greedy minus OR-Tools</th>
                </tr>
              </thead>
              <tbody>
                {report.rows.map((row) => <ReportRow key={row.code} row={row} />)}
              </tbody>
            </table>
          </section>
          <SourceNote rows={report.rows} />
        </>
      )}
    </section>
  );
}
